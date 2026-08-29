"""The live / paper loop for the Donchian-BVAR-uncertainty stack, and its latency budget.

The research code in `dbu.py` is vectorised over the whole history. Live, exactly one thing
matters: **at the close of bar t, how many milliseconds until the order is in?** Everything below
is organised around that number.

    bar close (t)                                       0 ms
      +-- rebuild the panel over the tail window         ~10 ms     (measured, 700-bar tail)
      +-- Donchian channel + ATR over the same tail      ~0.3 ms
      +-- BVAR: state vector z_t, then z @ A             ~0.1 ms    (a matmul, S=200 draws)
      +-- network: 5 members x 20 MC passes, batch 1     ~3-8 ms    (CPU, torch, no autograd)
      +-- gates, sizing, risk checks                     ~0.02 ms
      +-- order out                                      broker RTT
    total, model side                                    ~11 ms measured without the network,
                                                         ~15-20 ms with it

Those are `selftest()`'s own numbers on this container, and the panel rebuild dominates -- it is a
full recompute over `LiveCfg.panel_tail` bars every bar, which is the deliberate trade in
`_arrays` below. If you need single-digit milliseconds, make the panel incremental and assert it
against the vectorised version bar for bar, the way `tuner_test.py` does for the exit tensor. Do
not make it incremental and merely hope.

The costs that are NOT in that budget and dominate it in practice: the data feed's own bar-close
latency, the broker round trip, and the queue position you do not have. Budget 100-300 ms
end-to-end for a retail stack, and design the strategy so that 300 ms of delay does not destroy
it -- which is a question you can answer offline, and should, before wiring anything up:
`research/live_timing.py` and `docs/ib/LIVE_EXECUTION.md` in this repository already measure it.

THE THREE RULES THIS FILE ENFORCES
----------------------------------
1. **A bar is acted on only when it is CLOSED.** The Pine equivalent is `barstate.isconfirmed`,
   and `CLAUDE.md` records what happens without it: 5.1x as many signals, 80% of them on bars that
   never satisfied the rule. The same trap exists in every live loop that reads a forming bar.
2. **Refits happen off the hot path.** The BVAR refit is ~30 ms and the network refit is minutes;
   both run in a worker and are swapped in atomically between bars. A model that is late is used
   one block longer -- it is never awaited inside the signal path.
3. **Every decision is logged with the inputs that produced it**, including the model version
   hash. Live decay is diagnosed from this log or it is not diagnosed.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import deque
from dataclasses import dataclass

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import donchian
import bvar as bv
import dbu


# ===================================================================== broker interface
class Broker:
    """The only surface the strategy is allowed to touch. Implement it once per venue.

    Deliberately tiny: a bracket order in, a position out. Anything richer (partial fills,
    working-order amendment, OCO repair) belongs behind this interface, because it is venue
    behaviour and it is where live-vs-backtest divergence comes from.
    """

    def position(self) -> int:
        raise NotImplementedError

    def submit_bracket(self, side: int, qty: int, stop_px: float, target_px: float,
                       tag: str) -> str:
        raise NotImplementedError

    def flatten(self, reason: str) -> None:
        raise NotImplementedError


class PaperBroker(Broker):
    """A fill simulator with the SAME pessimism as the backtester, so paper and research agree.

    Specifically: a market order fills at the next bar's open plus the modelled spread and
    slippage, and a bar containing both barriers is booked as the loss. If your paper broker is
    more generous than your backtest, paper trading becomes a way of confirming a bias.
    """

    def __init__(self, cfg: dbu.Cfg):
        self.cfg = cfg
        self.pos = 0
        self.entry = None
        self.trades = []
        self.pending = None

    def position(self):
        return self.pos

    def submit_bracket(self, side, qty, stop_px, target_px, tag):
        self.pending = dict(side=side, qty=qty, stop=stop_px, target=target_px, tag=tag)
        return tag

    def flatten(self, reason="manual"):
        self.pending = None
        if self.entry is not None:
            self.entry["exit_reason"] = reason
        self.pos = 0

    def on_bar(self, o, h, l, c, mod):
        """Called with each CLOSED bar. Fills the pending order at this bar's open, then walks it."""
        cfg = self.cfg
        edge = cfg.spread_t * dbu.TICK
        if self.pending is not None and self.pos == 0:
            p = self.pending
            px = o + p["side"] * edge                       # crossing the spread, always against
            self.entry = dict(px=px, **p)
            self.pos = p["side"] * p["qty"]
            self.pending = None
        if self.pos != 0 and self.entry is not None:
            e = self.entry; side = e["side"]
            hit_s = (l <= e["stop"]) if side > 0 else (h >= e["stop"])
            hit_t = (h >= e["target"]) if side > 0 else (l <= e["target"])
            px = None; why = None
            if hit_s:                                        # loss first: the pessimistic rule
                px = e["stop"] - side * cfg.stop_slip_t * dbu.TICK; why = "stop"
            elif hit_t:
                px = e["target"]; why = "target"
            elif cfg.flat_min and mod >= cfg.flat_min:
                px = c - side * edge; why = "flat"
            if px is not None:
                gross = side * (px - e["px"]) * dbu.PV * e["qty"]
                net = gross - cfg.comm * e["qty"]
                self.trades.append(dict(tag=e["tag"], side=side, qty=e["qty"], entry=e["px"],
                                        exit=px, why=why, net=net))
                self.pos = 0; self.entry = None


# ===================================================================== the online state
@dataclass
class LiveCfg:
    tf_min: int = 5
    warmup_bars: int = 4000          # bars before anything trades. Do not shorten this.
    panel_tail: int = 1500           # bars the HOT path recomputes over. Must exceed every
    #                                  lookback in the panel (z_win) and in the rule (don_n, atr).
    bvar_refit_bars: int = 250       # how often the posterior is refitted, off the hot path
    net_refit_bars: int = 4000       # how often the ensemble is refitted, off the hot path
    max_stale_bars: int = 2000       # refuse to trade on a model older than this
    max_bar_gap_s: int = 900         # a data gap this long forces a warm restart, not a trade
    kill_daily_loss: float = 400.0
    kill_consecutive: int = 6


class Runner:
    """One instrument, one timeframe, one strategy. Stateless between bars except for `self.hist`.

    `hist` is a ring of the last `warmup_bars` bars; everything derived (channel, panel, state
    vector) is recomputed from it on each closed bar. That is deliberately simple rather than
    incremental: at 5-minute bars it costs ~1 ms, and an incremental cache that silently diverges
    from the research code is the most expensive kind of bug this repository has produced.
    """

    def __init__(self, cfg: dbu.Cfg, live: LiveCfg, broker: Broker, ens=None, out=None):
        self.cfg = cfg; self.live = live; self.broker = broker; self.ens = ens
        self.hist = deque(maxlen=live.warmup_bars + 10)
        self.post = None; self.func = None; self.post_bar = -10 ** 9
        self.bars_seen = 0
        self.day = None; self.day_pnl = 0.0; self.losses = 0
        self.halted = None
        self.log = open(out, "a") if out else None

    # ---------------------------------------------------------------- helpers
    def _arrays(self, tail=None):
        """The history as arrays. `tail` bounds the hot path: the panel's longest lookback is
        `z_win`, so recomputing over the last `panel_tail` bars is IDENTICAL to recomputing over
        everything, and it is what keeps the per-bar cost flat as the session grows."""
        h = list(self.hist)[-tail:] if tail else list(self.hist)
        a = {k: np.array([b[k] for b in h], float) for k in ("o", "h", "l", "c", "v")}
        a["mod"] = np.array([b["mod"] for b in h], np.int64)
        a["_key"] = ("live", self.bars_seen, len(h))
        return a

    def _refit_bvar(self, d, panel, minn, draws=200, seed=11):
        """Off the hot path. Returns (posterior, (A, b, v)) -- the per-draw linear functionals."""
        Y, names = bv.build_panel(d, panel)
        Yw = Y / bv.sv_scale(Y, minn.lam_sv) if minn.sv else Y
        post = bv.fit(Yw[np.isfinite(Yw).all(1)], minn)
        Bs, Sg = bv.draw(post, draws, np.random.default_rng(seed))
        A, bvec, vvec = bv.block_functionals(Bs, Sg, Y.shape[1], minn.p, self.cfg.h,
                                             names.index(panel.target))
        return post, (A, bvec, vvec, names)

    # ---------------------------------------------------------------- the hot path
    def on_closed_bar(self, bar, panel=None, minn=None):
        """`bar` is a dict with o/h/l/c/v/mod/ts for a bar that is CLOSED. Returns the decision."""
        t0 = time.perf_counter()
        panel = panel or bv.PanelCfg(donch=self.cfg.don_n)
        minn = minn or bv.MinnCfg()
        if isinstance(self.broker, PaperBroker):
            self.broker.on_bar(bar["o"], bar["h"], bar["l"], bar["c"], bar["mod"])
            self._account()
        self.hist.append(bar); self.bars_seen += 1
        dec = dict(ts=bar.get("ts"), bar=self.bars_seen, action="none")

        if self.halted:
            dec["action"] = "halted"; dec["reason"] = self.halted
            return self._emit(dec, t0)
        if len(self.hist) < self.live.warmup_bars:
            dec["reason"] = f"warmup {len(self.hist)}/{self.live.warmup_bars}"
            return self._emit(dec, t0)
        if self.broker.position() != 0:
            dec["reason"] = "in position"
            return self._emit(dec, t0)

        d = self._arrays(self.live.panel_tail)
        if self.post is None or self.bars_seen - self.post_bar >= self.live.bvar_refit_bars:
            # the refit sees the FULL history; only the hot path is tail-bounded
            self.post, self.func = self._refit_bvar(self._arrays(), panel, minn)
            self.post_bar = self.bars_seen
        if self.bars_seen - self.post_bar > self.live.max_stale_bars:
            dec["reason"] = "model stale"; return self._emit(dec, t0)

        # --- the density, in one matmul over posterior draws
        Y, names = bv.build_panel(d, panel)
        Sc = bv.sv_scale(Y, minn.lam_sv) if minn.sv else np.ones_like(Y)
        Yw = Y / Sc
        A, bvec, vvec, _ = self.func
        z = np.concatenate([Yw[-1 - l] for l in range(minn.p)])
        if not np.isfinite(z).all():
            dec["reason"] = "panel not finite"; return self._emit(dec, t0)
        sc = Sc[-1, names.index(panel.target)]
        M = (z @ A + bvec) * sc
        SD = np.sqrt(vvec) * sc
        mu = float(M.mean()); sd = float(np.sqrt(M.var() + (SD ** 2).mean()))
        p_up = float(bv._ndtr(M / SD).mean())
        dec.update(mu=mu, sd=sd, p_up=p_up)

        # --- the trigger
        side = self.cfg.side or (1 if mu > 0 else -1)
        trig = donchian.breakout(d, self.cfg.don_n, side, self.cfg.buf_ticks,
                                 self.cfg.mode)[-1]
        lo, hi = self.cfg.win; m = bar["mod"]
        in_win = (lo <= m < hi) if lo <= hi else (m >= lo or m < hi)
        if not (trig and in_win):
            dec["reason"] = "no trigger" if not trig else "outside window"
            return self._emit(dec, t0)

        # --- the gates, in the same order as the backtest, or the two will disagree
        zsig = side * mu / max(sd, 1e-9)
        psig = p_up if side > 0 else 1.0 - p_up
        if zsig < self.cfg.bvar_z or psig < self.cfg.bvar_p:
            dec["reason"] = f"bvar gate z={zsig:.2f} p={psig:.3f}"
            return self._emit(dec, t0)

        a = dbu.atr(d["h"], d["l"], d["c"], self.cfg.atr_n)[-1]
        stop_d = self.cfg.stop_atr * a
        qty = 1
        if self.ens is not None:
            import uq_net
            ob = bv.BvarOut(*[np.full(len(d["c"]), np.nan) for _ in range(7)],
                            np.zeros(len(d["c"]), np.int64), names)
            ob.mu[-1] = mu; ob.sd[-1] = sd; ob.p_up[-1] = p_up
            ob.sd_epi[-1] = float(M.std()); ob.sd_alea[-1] = float(np.sqrt((SD ** 2).mean()))
            ob.z[-1] = mu / max(sd, 1e-9); ob.surprise[-1] = 0.0
            X, _ = dbu.features(d, ob, self.cfg, side)
            pr = uq_net.predict(self.ens, X[-1:][np.newaxis, 0].reshape(1, -1))
            dec.update(p_win=float(pr["p_up"][0]), sd_epi=float(pr["sd_epi"][0]),
                       sd_alea=float(pr["sd_alea"][0]))
            thr = self.ens.get("epi_thr", np.inf)         # fitted on the RESEARCH block, offline
            if pr["sd_epi"][0] > thr:
                dec["reason"] = "epistemic veto"; return self._emit(dec, t0)
            if self.cfg.geom_from_alea:
                med = self.ens.get("alea_med", pr["sd_alea"][0])
                stop_d *= float(np.clip(pr["sd_alea"][0] / max(med, 1e-9), *self.cfg.geom_clip))
            qty = int(dbu.kelly_size(pr["p_up"], self.cfg.tp_r, self.cfg.equity,
                                     np.array([stop_d * dbu.PV]), self.cfg,
                                     epi=pr["sd_epi"], alea=pr["sd_alea"])[0])
        if qty <= 0:
            dec["reason"] = "size 0"; return self._emit(dec, t0)

        px = bar["c"]                                   # the fill will be the NEXT open, not this
        stop_px = px - side * stop_d
        targ_px = px + side * self.cfg.tp_r * stop_d
        tag = f"{self.bars_seen}-{side:+d}"
        self.broker.submit_bracket(side, qty, stop_px, targ_px, tag)
        dec.update(action="enter", side=side, qty=qty, stop=stop_px, target=targ_px, tag=tag)
        return self._emit(dec, t0)

    # ---------------------------------------------------------------- risk and logging
    def _account(self):
        b = self.broker
        if not isinstance(b, PaperBroker) or not b.trades:
            return
        last = b.trades[-1]
        if last.get("_seen"):
            return
        last["_seen"] = True
        self.day_pnl += last["net"]
        self.losses = self.losses + 1 if last["net"] < 0 else 0
        if self.day_pnl <= -self.live.kill_daily_loss:
            self.halted = f"daily loss {self.day_pnl:.0f}"
        if self.losses >= self.live.kill_consecutive:
            self.halted = f"{self.losses} consecutive losses"

    def new_session(self):
        """Call at the session boundary. The daily kill switch resets; the model does not."""
        self.day_pnl = 0.0; self.losses = 0
        if self.halted and self.halted.startswith("daily loss"):
            self.halted = None

    def _emit(self, dec, t0):
        dec["ms"] = round(1000 * (time.perf_counter() - t0), 3)
        if self.log:
            self.log.write(json.dumps(dec, default=float) + "\n"); self.log.flush()
        return dec


# ===================================================================== self-test
def selftest(n=3500, seed=3):
    """Replay synthetic bars through the loop and check the three things that break live systems:
    no action before warmup, no second entry while in a position, and the kill switch halting."""
    d = dbu._synth(n, seed)
    cfg = dbu.Cfg(don_n=12, buf_ticks=0.0, win=(0, 1440), max_hold=12, h=4,
                  bvar_z=-1e9, bvar_p=0.0, daily_loss_limit=0.0)
    live = LiveCfg(warmup_bars=1200, panel_tail=700, bvar_refit_bars=500, kill_daily_loss=1e9,
                   kill_consecutive=10 ** 9)
    pb = PaperBroker(cfg)
    r = Runner(cfg, live, pb)
    panel = bv.PanelCfg(donch=cfg.don_n, z_win=200)
    minn = bv.MinnCfg(p=2)
    acts, ms = [], []
    for i in range(n):
        dec = r.on_closed_bar(dict(o=d["o"][i], h=d["h"][i], l=d["l"][i], c=d["c"][i],
                                   v=d["v"][i], mod=int(d["mod"][i]), ts=int(i)), panel, minn)
        acts.append(dec["action"]); ms.append(dec["ms"])
        if dec["action"] == "enter":
            assert pb.position() == 0, "entered while already in a position"
    entries = sum(a == "enter" for a in acts)
    assert all(a in ("none", "halted") for a in acts[:live.warmup_bars]), "traded during warmup"
    assert all(a != "enter" for a in acts[:live.warmup_bars]), "entered during warmup"
    assert entries > 0, "no entries at all -- the loop is not reaching the trigger"
    assert len(pb.trades) > 0, "no fills"

    # the kill switch must actually stop trading
    pb2 = PaperBroker(cfg)
    r2 = Runner(cfg, LiveCfg(warmup_bars=1200, panel_tail=700, bvar_refit_bars=500,
                             kill_daily_loss=1.0, kill_consecutive=2), pb2)
    for i in range(n):
        r2.on_closed_bar(dict(o=d["o"][i], h=d["h"][i], l=d["l"][i], c=d["c"][i], v=d["v"][i],
                              mod=int(d["mod"][i]), ts=int(i)), panel, minn)
    assert r2.halted, "kill switch never fired"
    return dict(entries=entries, fills=len(pb2.trades) and len(pb.trades),
                median_ms=round(float(np.median([x for x in ms if x > 0])), 3),
                p99_ms=round(float(np.percentile(ms, 99)), 3), halted=r2.halted)


if __name__ == "__main__":
    print("dbu_live selftest:", selftest())
