"""Donchian x BVAR x deep-uncertainty: the strategy layer, the simulator, and the gates.

This is the module that assembles the other three (`donchian`, `bvar`, `uq_net`) into something
that produces trades, and then tries hard to kill it. Read `CLAUDE.md` first; the short version of
what this repository has already measured, and which this design is shaped by:

  * a rule read at the FILL bar is leakage, so every feature here is read at the SIGNAL bar and
    the fill is the next open. `sig_bar`, never `ent_bar`.
  * a win rate means nothing without its base rate, and the base rate for a given geometry must be
    computed from the population, not assumed. `base_rate()` below.
  * the honest benchmark is a MATCHED CONTROL -- random entries with the same side, geometry and
    minute-of-day distribution -- and it is a GATE, run first, not a final check. `control()`.
  * no calendar conditions in the search. Weekday and month partition the sample and hand the
    search a free lottery.
  * the split is the first 65% of SESSIONS, and the locked block is read once, at the end.

WHAT THE THREE PARTS ARE ACTUALLY DOING
---------------------------------------
Donchian supplies the EVENT: an n-bar extreme is broken. That is a well-defined, cheap, sparse
trigger with a real microstructure story behind it (resting stops above the high get run), and it
is also one of the most heavily mined patterns in existence -- so it is treated as a candidate
population, not as an edge.

The BVAR supplies the CONDITIONAL DENSITY of the next h bars given the joint state of return,
flow, volume and volatility. It is a filter and a veto: it can say "this break is happening into a
flow shock whose impulse response dies in two bars", which a univariate rule cannot say. Its
`p_up` prices drift, and its `surprise` term flags the bars where its own model just broke.

The network supplies the SECOND MOMENT and the model's own confidence in it. Aleatoric sd sets the
geometry (a wider expected outcome distribution needs a wider stop and a further target to keep
the same barrier probabilities); epistemic sd sets the veto and the size (an unfamiliar state is
one to sit out or to take small).

The order matters: trigger -> density -> uncertainty -> size. Each stage can only REMOVE trades or
shrink them. Nothing downstream can invent a trade the Donchian rule did not fire.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import donchian
import bvar as bv

TICK = 0.25
PV = 2.0                       # $ per point, MNQ. NQ is 5.0 (and `research/tuner.py` uses 2.0)
COMM = 1.0                     # $ per contract round turn


# ===================================================================== configuration
@dataclass
class Cfg:
    # -- trigger
    don_n: int = 20            # Donchian lookback, in bars
    buf_ticks: float = 2.0     # ticks price must clear the band by
    mode: str = "close"        # "close" (next-open fill) or "touch" (resting stop, fills at level)
    side: int = 0              # 0 = both sides, +1 long only, -1 short only
    win: tuple = (570, 660)    # New York minutes. 09:30-11:00. See CLAUDE.md on why not 07:00.
    # -- geometry
    atr_n: int = 14
    stop_atr: float = 1.5      # stop distance, in ATR units, BEFORE the uncertainty adjustment
    tp_r: float = 1.0          # target, in R
    max_hold: int = 24         # bars
    flat_min: int = 0          # New York minute to flatten at; 0 = never
    # -- BVAR gate
    h: int = 6                 # forecast horizon, in bars. Set it from the IRF, not from a grid.
    bvar_z: float = 0.15       # require |mu| / sd above this, signed with the trade
    bvar_p: float = 0.52       # require P(move in my direction) above this
    surprise_max: float = 3.0  # veto when the VAR's own one-step innovation is this many sd out
    # -- uncertainty gate
    epi_q: float = 0.80        # veto above this quantile of epistemic sd (fitted on RESEARCH only)
    p_win_min: float = 0.0     # optional floor on the network's calibrated P(win); 0 = off
    geom_from_alea: bool = True  # scale the stop by the predicted aleatoric sd
    geom_clip: tuple = (0.7, 1.6)
    # -- sizing
    equity: float = 25000.0          # account equity the Kelly fraction is applied to
    risk_per_trade: float = 100.0    # hard cap on $ risked at the stop, whatever Kelly says
    kelly_frac: float = 0.25
    max_contracts: int = 3
    daily_loss_limit: float = 400.0
    # -- costs
    spread_t: float = 2.0      # ticks each side (crossing)
    stop_slip_t: float = 1.0   # extra ticks when the exit is a stop
    comm: float = COMM
    cost_mult: float = 1.0


STOP, TARGET, FLAT, HOLD, NOFILL = 1, 2, 3, 4, 5


# ===================================================================== bars and the split
def atr(h, l, c, n):
    """ema(true_range, n) -- the repository's definition, NOT Wilder's, NOT `ta.atr`."""
    h, l, c = (np.asarray(x, float) for x in (h, l, c))
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    a = np.empty(len(tr)); a[:] = np.nan
    k = 2.0 / (n + 1.0)
    acc = tr[:n].mean() if len(tr) >= n else np.nan
    for i in range(len(tr)):
        acc = tr[i] if i == 0 else k * tr[i] + (1 - k) * acc
        if i >= n:
            a[i] = acc
    return a


def split(sess, frac=0.65):
    """Index of the first bar of the LOCKED block: the first 65% of sessions are research."""
    us = np.unique(sess)
    cut = us[int(frac * len(us))]
    return int(np.searchsorted(sess, cut))


# ===================================================================== the simulator
def walk(d, trig, side, stop_px, targ_px, max_hold, flat_min, cfg: Cfg):
    """Triple-barrier walk from each candidate signal bar. Returns (exit_bar, reason, gross_$).

    Pessimism, matching `test_suite.sim_core`: when one bar contains BOTH barriers the trade is
    booked as the LOSS, because the intrabar path is unknown. `docs/RESEARCH_PROTOCOL.md` Stage 0
    prices how often that fires, and it is the reason the engine's null is conservative by a KNOWN
    amount rather than an unknown one.
    """
    o, h, l, c, mod = (np.asarray(d[k], float) for k in ("o", "h", "l", "c", "mod"))
    n = len(c)
    xb = np.full(n, -1, np.int64); why = np.zeros(n, np.int8); raw = np.zeros(n)
    for i in trig:
        e = i + 1
        if e >= n or not np.isfinite(stop_px[i]) or not np.isfinite(targ_px[i]):
            continue
        px = o[e]
        sp = px - side * abs(px - stop_px[i])
        tp = px + side * abs(targ_px[i] - px)
        end = min(e + max_hold, n - 1)
        j = e
        done = False
        while j <= end:
            hit_s = (l[j] <= sp) if side > 0 else (h[j] >= sp)
            hit_t = (h[j] >= tp) if side > 0 else (l[j] <= tp)
            if hit_s:                                  # loss first, always, when both are in-bar
                xb[i] = j; why[i] = STOP; raw[i] = side * (sp - px) * PV; done = True; break
            if hit_t:
                xb[i] = j; why[i] = TARGET; raw[i] = side * (tp - px) * PV; done = True; break
            if flat_min and mod[j] >= flat_min:
                xb[i] = j; why[i] = FLAT; raw[i] = side * (c[j] - px) * PV; done = True; break
            j += 1
        if not done:
            xb[i] = end; why[i] = HOLD; raw[i] = side * (c[end] - px) * PV
    return xb, why, raw


def book(d, trig, xb, why, raw, sizes, cfg: Cfg, sess=None):
    """Sequential no-overlap selection, costs applied at read time, one row per taken trade.

    Costs are affine in the gross move, which is why they are applied HERE and not inside the walk:
    a cost-sensitivity sweep then costs nothing, and that is the test most likely to kill a
    scalping result.
    """
    fixed = (cfg.comm + 2.0 * cfg.spread_t * TICK * PV) * cfg.cost_mult
    slip = cfg.stop_slip_t * TICK * PV * cfg.cost_mult
    free_at = -1
    day_pnl = {}
    rows = []
    for i in trig:
        if xb[i] < 0 or i <= free_at:
            continue
        q = int(sizes[i]) if sizes is not None else 1
        if q <= 0:
            continue
        s = 0 if sess is None else int(sess[i])
        if cfg.daily_loss_limit and day_pnl.get(s, 0.0) <= -cfg.daily_loss_limit:
            continue
        net = q * (raw[i] - fixed - (slip if why[i] == STOP else 0.0))
        day_pnl[s] = day_pnl.get(s, 0.0) + net
        rows.append((i, xb[i], why[i], q, raw[i] * q, net))
        free_at = xb[i]
    dt = np.dtype([("sig", "i8"), ("exit", "i8"), ("why", "i1"), ("q", "i8"),
                   ("gross", "f8"), ("net", "f8")])
    return np.array(rows, dtype=dt) if rows else np.zeros(0, dtype=dt)


def stats(tr, sess=None, cut=None):
    if len(tr) == 0:
        return dict(n=0, net=0.0, per=0.0, win=0.0, pf=0.0, dd=0.0)
    net = tr["net"]
    eq = np.cumsum(net)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0
    gw = net[net > 0].sum(); gl = -net[net < 0].sum()
    out = dict(n=len(tr), net=float(net.sum()), per=float(net.mean()),
               win=100.0 * float((net > 0).mean()), pf=float(gw / gl) if gl > 0 else np.inf,
               dd=dd)
    if cut is not None:
        r = tr[tr["sig"] < cut]; k = tr[tr["sig"] >= cut]
        out["research"] = dict(n=len(r), net=float(r["net"].sum()),
                               per=float(r["net"].mean()) if len(r) else 0.0)
        out["locked"] = dict(n=len(k), net=float(k["net"].sum()),
                             per=float(k["net"].mean()) if len(k) else 0.0)
    return out


# ===================================================================== base rate and control
def base_rate(d, side, stop_atr, tp_r, max_hold, flat_min, cfg: Cfg, eligible=None):
    """The win rate of the GEOMETRY on this population -- what any rule has to beat.

    Not 1/(1+R): costs push it down, drift lifts longs and sinks shorts, and the flatten time moves
    it again. Computed from every eligible bar, which is the only version of this number that
    means anything.
    """
    a = atr(d["h"], d["l"], d["c"], cfg.atr_n)
    c = np.asarray(d["c"], float)
    sp = c - side * stop_atr * a
    tp = c + side * tp_r * stop_atr * a
    idx = np.flatnonzero(np.isfinite(a) if eligible is None else (eligible & np.isfinite(a)))
    xb, why, raw = walk(d, idx, side, sp, tp, max_hold, flat_min, cfg)
    ok = xb[idx] >= 0
    fixed = (cfg.comm + 2.0 * cfg.spread_t * TICK * PV) * cfg.cost_mult
    slip = cfg.stop_slip_t * TICK * PV * cfg.cost_mult
    net = raw[idx][ok] - fixed - np.where(why[idx][ok] == STOP, slip, 0.0)
    w = why[idx][ok]
    bar = np.isin(w, (STOP, TARGET))
    return dict(n=int(ok.sum()), win=100.0 * float((net > 0).mean()), per=float(net.mean()),
                barrier_win=100.0 * float((w[bar] == TARGET).mean()) if bar.any() else np.nan,
                barrier_share=100.0 * float(bar.mean()),
                exits={int(k): int((w == k).sum()) for k in np.unique(w)})


def control(d, trig, side, stop_px, targ_px, cfg: Cfg, sess=None, draws=400, seed=7,
            eligible=None):
    """Matched control: random entries with the SAME side, geometry and minute-of-day mix.

    This prices drift, costs, barrier width and session timing in one number. Run it as a gate on
    every configuration; `CLAUDE.md` records what happened both times it was run last instead.
    """
    mod = np.asarray(d["mod"])
    n = len(mod)
    elig = np.ones(n, bool) if eligible is None else np.asarray(eligible, bool)
    elig &= np.isfinite(stop_px) & np.isfinite(targ_px)
    pool = {}
    for m in np.unique(mod[np.asarray(trig, np.int64)]):
        pool[int(m)] = np.flatnonzero(elig & (mod == m))
    counts = {int(m): int((mod[np.asarray(trig, np.int64)] == m).sum()) for m in pool}
    rng = np.random.default_rng(seed)
    per = np.empty(draws)
    for s in range(draws):
        pick = []
        for m, cnt in counts.items():
            p = pool[m]
            if len(p) == 0:
                continue
            pick.append(rng.choice(p, size=min(cnt, len(p)), replace=False))
        idx = np.sort(np.concatenate(pick)) if pick else np.zeros(0, np.int64)
        xb, why, raw = walk(d, idx, side, stop_px, targ_px, cfg.max_hold, cfg.flat_min, cfg)
        tr = book(d, idx, xb, why, raw, None, cfg, sess)
        per[s] = tr["net"].mean() if len(tr) else 0.0
    return per


def p_value(sample, actual):
    """One-sided: how often does the control beat what we measured."""
    return float((np.asarray(sample) >= actual).mean())


# ===================================================================== features and labels
def features(d, out_bv, cfg: Cfg, side):
    """The network's inputs, all read at the SIGNAL bar. No calendar variables, by protocol.

    Deliberately small. 134 features were tried on this instrument and ONE survived FDR
    (`docs/ib/STUDY_FEATURES.md`), and 134 of them turned out to be 28 principal components. A
    wide feature matrix here would be a way of hiding a search, not of adding information.
    """
    a = atr(d["h"], d["l"], d["c"], cfg.atr_n)
    c = np.asarray(d["c"], float)
    up, dn, mid, w = donchian.channel(d["h"], d["l"], cfg.don_n)
    cols = {
        "donch_pos": donchian.position(d["h"], d["l"], c, cfg.don_n),
        "donch_w_atr": w / np.where(a > 1e-9, a, np.nan),
        "donch_age": donchian.bars_since_new(d["h"], d["l"], cfg.don_n, side),
        "break_size": side * (c - (up if side > 0 else dn)) / np.where(a > 1e-9, a, np.nan),
        "close_in_bar": (c - d["l"]) / np.where(d["h"] - d["l"] > 1e-9, d["h"] - d["l"], np.nan),
        "atr_ratio": a / np.where(np.roll(a, 60) > 1e-9, np.roll(a, 60), np.nan),
        "bvar_mu": side * out_bv.mu,
        "bvar_z": side * out_bv.z,
        "bvar_sd": out_bv.sd,
        "bvar_epi_share": out_bv.sd_epi / np.maximum(out_bv.sd, 1e-9),
        "bvar_p": np.where(side > 0, out_bv.p_up, 1.0 - out_bv.p_up),
        "bvar_surprise": out_bv.surprise,
    }
    cols["atr_ratio"][:60] = np.nan
    names = list(cols)
    X = np.column_stack([cols[k] for k in names])
    return X, names


def labels(d, side, cfg: Cfg, stop_px=None, targ_px=None, eligible=None):
    """(y, lab): outcome in R and a 1/0 barrier label, for EVERY eligible bar.

    Labels come from the same walk the strategy trades, so the network is trained on the thing it
    is used to predict. Training on a raw h-bar forward return instead is the classic mistake: the
    barrier ORDER is what pays, and a forward return does not know about it.
    """
    a = atr(d["h"], d["l"], d["c"], cfg.atr_n)
    c = np.asarray(d["c"], float)
    if stop_px is None:
        stop_px = c - side * cfg.stop_atr * a
    if targ_px is None:
        targ_px = c + side * cfg.tp_r * cfg.stop_atr * a
    n = len(c)
    idx = np.flatnonzero(np.isfinite(a) if eligible is None else (eligible & np.isfinite(a)))
    xb, why, raw = walk(d, idx, side, stop_px, targ_px, cfg.max_hold, cfg.flat_min, cfg)
    risk = np.abs(c - stop_px) * PV
    y = np.full(n, np.nan); lab = np.full(n, np.nan)
    ok = idx[xb[idx] >= 0]
    y[ok] = raw[ok] / np.maximum(risk[ok], 1e-9)
    lab[ok] = (why[ok] == TARGET).astype(float)
    return y, lab


# ===================================================================== sizing
def kelly_size(p_win, tp_r, equity, stop_dollars, cfg: Cfg, epi=None, alea=None):
    """Contracts, from a fractional Kelly on the barrier bet, shrunk by model disagreement.

    f* = (p(1+R) - 1) / R for a bet that wins R and loses 1. Three deliberate departures from
    textbook Kelly, all of which matter more than the formula:

      * `kelly_frac` at 0.25. Kelly assumes the probability is KNOWN; it is estimated here, and
        the variance of an estimated-p Kelly is enormous. A quarter is the usual compromise and is
        still aggressive.
      * the epistemic shrink. p is pulled toward the base rate in proportion to the ensemble's own
        disagreement, so an unfamiliar state cannot produce a large bet just because one member is
        confident. This is the single most important line in the module.
      * a hard contract cap and an integer floor. Futures do not size continuously, and the whole
        exercise is pointless if the answer rounds to 1 contract every time -- which, on a small
        account, it will. `CLAUDE.md`: sizing creates no edge; it manages ruin.
    """
    p = np.asarray(p_win, float)
    if epi is not None:
        base = 1.0 / (1.0 + tp_r)                    # the driftless barrier probability
        e = np.nan_to_num(epi, nan=np.inf)
        ratio = e / np.maximum(np.nan_to_num(alea, nan=1.0), 1e-9) if alea is not None else e
        p = base + (p - base) / (1.0 + ratio)        # p -> base as disagreement -> irreducible
    f = (p * (1.0 + tp_r) - 1.0) / max(tp_r, 1e-9)      # fraction of equity to risk
    f = np.clip(f, 0.0, 1.0) * cfg.kelly_frac
    sd_ = np.maximum(stop_dollars, 1e-9)
    q = np.floor(f * equity / sd_)
    q = np.minimum(q, np.floor(cfg.risk_per_trade / sd_))   # the hard per-trade risk cap wins
    return np.clip(np.nan_to_num(q), 0, cfg.max_contracts).astype(np.int64)


# ===================================================================== the assembled signal
def signal(d, cfg: Cfg, side, out_bv=None, uq=None, research_mask=None, verbose=False):
    """Trigger -> BVAR gate -> uncertainty gate. Returns (trig, stop_px, targ_px, sizes, parts).

    `parts` records how many bars each stage removed, which is the only way to notice that a gate
    is doing nothing (and should be dropped) or everything (and is the whole strategy).
    """
    n = len(d["c"])
    a = atr(d["h"], d["l"], d["c"], cfg.atr_n)
    c = np.asarray(d["c"], float)
    mod = np.asarray(d["mod"])
    lo, hi = cfg.win
    wm = (mod >= lo) & (mod < hi) if lo <= hi else (mod >= lo) | (mod < hi)

    parts = {}
    m = donchian.breakout(d, cfg.don_n, side, cfg.buf_ticks, cfg.mode) & wm & np.isfinite(a)
    parts["trigger"] = int(m.sum())

    if out_bv is not None:
        z = side * out_bv.z
        p = np.where(side > 0, out_bv.p_up, 1.0 - out_bv.p_up)
        m &= np.nan_to_num(z) >= cfg.bvar_z
        parts["+bvar_z"] = int(m.sum())
        m &= np.nan_to_num(p) >= cfg.bvar_p
        parts["+bvar_p"] = int(m.sum())
        m &= np.nan_to_num(out_bv.surprise, nan=0.0) <= cfg.surprise_max
        parts["+surprise"] = int(m.sum())

    scale = np.ones(n)
    sizes = np.ones(n, np.int64)
    if uq is not None:
        rm = np.ones(n, bool) if research_mask is None else research_mask
        epi = uq["sd_epi"]
        # the veto threshold is a quantile of the RESEARCH block only; using the whole sample
        # here would put the locked block inside the selection
        pool = epi[rm & np.isfinite(epi)]
        if len(pool) < 100:
            # not enough research-block coverage to set a threshold. Skipping loudly is right:
            # calibrating it on the locked block instead would be exactly the error CLAUDE.md
            # says has already been made twice here.
            parts["+epistemic"] = "skipped: %d research rows" % len(pool)
        else:
            m &= np.nan_to_num(epi, nan=np.inf) <= np.quantile(pool, cfg.epi_q)
            parts["+epistemic"] = int(m.sum())
        if cfg.p_win_min > 0:
            m &= np.nan_to_num(uq["p_up"]) >= cfg.p_win_min
            parts["+p_win"] = int(m.sum())
        if cfg.geom_from_alea:
            ap = uq["sd_alea"][rm & np.isfinite(uq["sd_alea"])]
            med = float(np.median(ap)) if len(ap) >= 100 else 1.0
            scale = np.clip(np.nan_to_num(uq["sd_alea"] / max(med, 1e-9), nan=1.0),
                            *cfg.geom_clip)

    stop_d = cfg.stop_atr * a * scale
    stop_px = c - side * stop_d
    targ_px = c + side * cfg.tp_r * stop_d
    if uq is not None:
        sizes = kelly_size(uq["p_up"], cfg.tp_r, cfg.equity, stop_d * PV, cfg,
                           epi=uq["sd_epi"], alea=uq["sd_alea"])
        sizes = np.maximum(sizes, 0)
        parts["+size>0"] = int((m & (sizes > 0)).sum())
    m &= sizes > 0
    trig = np.flatnonzero(m).astype(np.int64)
    if verbose:
        print("  " + "  ".join(f"{k} {v:,}" for k, v in parts.items()))
    return trig, stop_px, targ_px, sizes, parts


def evaluate(d, cfg: Cfg, side, out_bv=None, uq=None, sess=None, draws=200, seed=7,
             verbose=True):
    """One configuration, end to end, with the split and the matched control -- never one number."""
    sess = np.asarray(d.get("sess", np.zeros(len(d["c"])))) if sess is None else sess
    cut = split(sess)
    rm = np.arange(len(d["c"])) < cut
    trig, sp, tp, sz, parts = signal(d, cfg, side, out_bv, uq, research_mask=rm)
    xb, why, raw = walk(d, trig, side, sp, tp, cfg.max_hold, cfg.flat_min, cfg)
    tr = book(d, trig, xb, why, raw, sz, cfg, sess)
    st = stats(tr, sess, cut)
    st["parts"] = parts
    if len(tr) > 3 and draws:
        mod = np.asarray(d["mod"]); lo, hi = cfg.win
        elig = ((mod >= lo) & (mod < hi)) if lo <= hi else ((mod >= lo) | (mod < hi))
        ctrl = control(d, trig, side, sp, tp, cfg, sess, draws, seed, eligible=elig)
        st["control_per"] = float(ctrl.mean())
        st["p_vs_control"] = p_value(ctrl, st["per"])
    if verbose:
        print(f"  trades {st['n']:,}  ${st['net']:,.0f}  ${st['per']:.2f}/trade  "
              f"win {st['win']:.1f}%  pf {st['pf']:.2f}")
        if "control_per" in st:
            print(f"  matched control ${st['control_per']:.2f}/trade  "
                  f"p={st['p_vs_control']:.3f}")
        if "research" in st:
            print(f"  research ${st['research']['per']:.2f} x{st['research']['n']}   "
                  f"locked ${st['locked']['per']:.2f} x{st['locked']['n']}"
                  + ("   <-- WRONG SHAPE: better on locked than on research"
                     if st["locked"]["per"] > st["research"]["per"] else ""))
    return st, tr


# ===================================================================== the whole pipeline
def pipeline(d, cfg: Cfg, side=1, panel: "bv.PanelCfg" = None, minn: "bv.MinnCfg" = None,
             uq_cfg=None, folds=6, win=6000, refit_every=250, draws=200, seed=11, verbose=True,
             use_uq=True):
    """Bars -> BVAR density -> labels -> purged walk-forward uncertainty -> trades.

    Every stage is out of sample by construction: the BVAR's coefficients at bar t come from a
    window ending before t's refit block, and the network's outputs at bar t come from a fold
    trained on rows before t, purged by the label horizon. There is no step here in which the
    whole sample is fitted and then scored.
    """
    import uq_net
    sess = np.asarray(d.get("sess", np.zeros(len(d["c"]), np.int64)))
    cut = split(sess)
    panel = panel or bv.PanelCfg(donch=cfg.don_n)
    minn = minn or bv.MinnCfg()
    if verbose:
        print(f"  bvar: k={len(bv.build_panel(d, panel)[1])} p={minn.p} h={cfg.h} "
              f"win={win:,} refit={refit_every}")
    ob = bv.rolling(d, panel, minn, h=cfg.h, win=win, refit_every=refit_every, draws=draws,
                    seed=seed, verbose=verbose)
    uq = None
    if use_uq:
        X, names = features(d, ob, cfg, side)
        y, lab = labels(d, side, cfg)
        ok = np.isfinite(X).all(1) & np.isfinite(y) & np.isfinite(lab)
        idx = np.flatnonzero(ok)
        if verbose:
            print(f"  uq: {len(idx):,} usable rows x {len(names)} features, "
                  f"{folds} purged folds")
        wf = uq_net.walk_forward(X[idx], y[idx], lab[idx], uq_cfg or uq_net.UQCfg(),
                                 folds=folds, h=cfg.max_hold, verbose=verbose)
        uq = {k: np.full(len(d["c"]), np.nan) for k in wf}
        for k, v in wf.items():
            uq[k][idx] = v
    st, tr = evaluate(d, cfg, side, ob, uq, sess, verbose=verbose)
    return dict(stats=st, trades=tr, bvar=ob, uq=uq, cut=cut)


# ===================================================================== self-test
def _synth(n=20000, seed=9, bars_per_sess=390):
    """Bars with a plausible microstructure but NO edge, which is the point: the whole stack run
    over a driftless series must not find one. This is Stage 0 of the protocol in miniature."""
    rng = np.random.default_rng(seed)
    vol = 0.5 * np.exp(0.4 * np.sin(np.arange(n) / 400.0) + 0.2 * rng.normal(size=n).cumsum() / 60)
    r = rng.normal(0, 1, n) * vol
    c = 15000 + np.cumsum(r)
    rg = np.abs(rng.normal(0, 1, n)) * vol + 0.25
    up = rg * rng.uniform(0.1, 0.9, n)
    h = c + up; l = c - (rg - up); o = np.r_[c[0], c[:-1]]
    v = np.abs(rng.normal(800, 250, n)) + 1.0
    mod = (570 + np.arange(n) % bars_per_sess).astype(np.int64) % 1440
    sess = (np.arange(n) // bars_per_sess).astype(np.int64)
    c = np.round(c / TICK) * TICK; h = np.round(h / TICK) * TICK
    l = np.round(l / TICK) * TICK; o = np.round(o / TICK) * TICK
    return dict(o=o, h=np.maximum(h, np.maximum(o, c)), l=np.minimum(l, np.minimum(o, c)),
                c=c, v=v, mod=mod, sess=sess, _key=("synth", seed))


def selftest(quick=True):
    d = _synth(12000 if quick else 40000)
    cfg = Cfg(don_n=20, win=(0, 1440), max_hold=12, stop_atr=1.5, tp_r=1.0)

    # 1. the geometry's base rate is close to the theoretical bound, adjusted by costs
    br = base_rate(d, 1, cfg.stop_atr, cfg.tp_r, cfg.max_hold, cfg.flat_min, cfg)
    # a 1R geometry on a driftless series resolves at its barriers near 50/50; the PESSIMISTIC
    # ambiguous-bar rule biases it below 50, and costs move the NET win rate a long way below
    # both -- which is the arithmetic the whole protocol exists to respect
    assert 30.0 < br["barrier_win"] < 55.0, f"barrier win rate {br['barrier_win']:.1f}%"
    assert br["per"] < 0.0, "a driftless series showed a positive per-trade edge after costs"

    # 2. Stage 0: a driftless series must not produce a significant result against the control
    st, tr = evaluate(d, cfg, 1, draws=60, verbose=False)
    assert st["n"] > 20, "trigger produced too few trades to test"
    assert st["p_vs_control"] > 0.01, \
        f"a driftless series beat its matched control at p={st['p_vs_control']:.4f} -- bug"

    # 3. costs must actually be charged, and doubling them must hurt
    cfg2 = Cfg(**{**cfg.__dict__, "cost_mult": 2.0})
    st2, _ = evaluate(d, cfg2, 1, draws=0, verbose=False)
    assert st2["per"] < st["per"], "doubling costs did not reduce per-trade P&L"

    # 4. sizing: Kelly must decline a fair bet and take a favourable one, and must never exceed
    #    the contract cap however confident the model claims to be
    assert kelly_size(np.array([0.50]), 1.0, cfg.equity, np.array([50.0]), cfg)[0] == 0
    assert kelly_size(np.array([0.70]), 1.0, cfg.equity, np.array([50.0]), cfg)[0] >= 1
    assert kelly_size(np.array([0.99]), 1.0, 1e6, np.array([1.0]), cfg)[0] == cfg.max_contracts
    #    and disagreement must shrink the bet toward the base rate
    big = kelly_size(np.array([0.70]), 1.0, cfg.equity, np.array([50.0]), cfg,
                     epi=np.array([0.01]), alea=np.array([1.0]))[0]
    small = kelly_size(np.array([0.70]), 1.0, cfg.equity, np.array([50.0]), cfg,
                       epi=np.array([5.0]), alea=np.array([1.0]))[0]
    assert small <= big, "epistemic shrink did not reduce the bet"

    # 5. no trade may be entered before its signal bar, or overlap another
    assert np.all(tr["exit"] > tr["sig"]), "a trade exited on or before its signal bar"
    assert np.all(tr["sig"][1:] > tr["exit"][:-1]), "overlapping trades"

    return dict(base_rate=br, trades=st["n"], per=round(st["per"], 2),
                p_vs_control=st["p_vs_control"], parts=st["parts"])


def demo(n=24000, seed=9):
    """The whole stack on synthetic bars, so the wiring is exercised without the data file."""
    d = _synth(n, seed)
    import uq_net
    cfg = Cfg(don_n=12, buf_ticks=0.0, win=(0, 1440), max_hold=12, h=6, epi_q=0.9,
              bvar_z=0.0, bvar_p=0.50)
    return pipeline(d, cfg, 1, win=2500, refit_every=400, draws=60, folds=4,
                    uq_cfg=uq_net.UQCfg(members=3, mc=8, epochs=20))["stats"]


if __name__ == "__main__":
    if "--demo" in sys.argv:
        print("dbu demo:", demo())
    else:
        print("dbu selftest:", selftest())
