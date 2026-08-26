"""Verification for `turtle_sim`: an independent reference, a null calibration, a leakage probe.

Three things have to be true before any number the engine produces is worth reading, and each is
checked here rather than asserted in prose.

1. **The fast kernel is the Pine.**  `reference()` is a deliberately slow, deliberately dumb
   transcription written straight from the Pine source -- an explicit order book, one branch per
   line of the script -- and it is compared to `turtle_sim.run` trade for trade.  Two
   implementations agreeing is weak evidence when one was copied from the other, so this one was
   written from the .pine file and not from the kernel.

2. **There is no look-ahead.**  On a synthetic random walk with costs switched off the engine must
   earn zero within sampling error.  The protocol's Stage 0: anything significantly profitable on
   a series with no edge by construction is a bug, not a strategy.  The truncation probe is the
   sharper version -- re-running on `bars[:k]` must reproduce every decision the full run made up
   to k, which is what fails the instant a condition reads a bar it should not.

3. **Costs are actually charged.**  Same random walk, costs on: the mean per-trade result must
   equal minus the modelled round turn, to within sampling error.  A cost that is configured but
   never applied is the single easiest way to manufacture a scalping edge.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_sim as T
from turtle_sim import P, Series, run


# ================================================================= a slow, literal reference

def reference(s: Series, p: P) -> list[dict]:
    """A transcription of the Pine, one branch per line, with an explicit order book."""
    atr = s.atr(p.atr_len)
    # Entry channels use the ENTRY lengths, trailing-exit channels the EXIT lengths.  The Pine is
    # long-only, so its `chanLo` is only ever an exit channel and its `chanHi` only ever an entry
    # one; mirroring it for shorts means swapping which side each length is measured on, not
    # reusing the same arrays.  Getting that wrong here is what the short-mirror case caught.
    hi1, hi2 = s.hi(p.entry1), s.hi(p.entry2)          # long entry
    lo1, lo2 = s.lo(p.exit1), s.lo(p.exit2)            # long trailing exit
    slo1, slo2 = s.lo(p.entry1), s.lo(p.entry2)        # short entry
    shi1, shi2 = s.hi(p.exit1), s.hi(p.exit2)          # short trailing exit
    adx = s.adx(14) if p.adx_max > 0 else np.zeros(s.n)
    ema = s.ema(p.ema_len) if p.ext_max > 0 else np.zeros(s.n)
    side = p.side

    trades: list[dict] = []
    orders: dict = {"entry": None, "stop": None, "tp": None, "flat": False}
    pos: dict | None = None
    last_win = False
    sess_traded = -1

    for i in range(s.n):
        new_sess = i > 0 and s.sess[i] != s.sess[i - 1]

        # ---- open: market orders issued last bar
        if orders["entry"] is not None:
            if new_sess and p.flatten_min >= 0:
                orders["entry"] = None
            else:
                kind, sysno, a = orders["entry"]
                fill = s.o[i]
                if pos is None:
                    pos = {"units": 1, "avg": fill, "first": fill, "sys": sysno, "bar": i,
                           "risk": p.atr_mult * a,
                           "stop": fill - side * p.atr_mult * a,
                           "add": fill + side * p.pyr_step * a,
                           "tp": fill + side * p.tp_r * p.atr_mult * a if p.tp_r > 0 else None}
                    if p.one_shot:
                        sess_traded = s.sess[i]
                else:
                    pos["avg"] = (pos["avg"] * pos["units"] + fill) / (pos["units"] + 1)
                    pos["units"] += 1
                    pos["stop"] = fill - side * p.atr_mult * a
                    pos["add"] = fill + side * p.pyr_step * a
                orders["entry"] = None

        # ---- intrabar: the stop / take-profit issued last bar
        if pos is not None:
            if p.armed_stop and i == pos["bar"] and orders.get("armed") is not None:
                orders["stop"] = orders["armed"]
            st, tp = orders["stop"], orders["tp"]
            hit_stop = st is not None and (s.l[i] <= st[0] if side > 0 else s.h[i] >= st[0])
            hit_tp = tp is not None and (s.h[i] >= tp if side > 0 else s.l[i] <= tp)
            reason, px = None, None
            if orders["flat"]:
                reason, px = ("max_hold" if orders["flat"] == "hold" else "session_flatten"), s.o[i]
            elif hit_stop:
                reason = "chan_stop" if st[1] else "atr_stop"
                px = (min(s.o[i], st[0]) if side > 0 else max(s.o[i], st[0])) - side * p.stop_slip
            elif hit_tp:
                reason = "take_profit"
                px = max(s.o[i], tp) if side > 0 else min(s.o[i], tp)
            if reason is not None:
                gross = side * (px - pos["avg"]) * pos["units"]
                cost = pos["units"] * (p.cost_abs + p.cost_bp * 1e-4 * pos["avg"])
                if reason == "take_profit" and p.tp_rests:
                    cost *= 0.5
                trades.append({"entry_bar": pos["bar"], "exit_bar": i, "units": pos["units"],
                               "pnl": gross - cost, "reason": reason, "risk": pos["risk"],
                               "sys": pos["sys"]})
                last_win = side * (s.c[i] - pos["first"]) > 0
                pos = None
                orders = {"entry": None, "stop": None, "tp": None, "flat": False}

        # ---- close: the script runs
        orders["stop"] = orders["tp"] = None
        orders["flat"] = False
        orders["armed"] = None
        a = atr[i]
        if np.isnan(a) or a <= 0:
            continue

        if pos is None:
            if p.one_shot and s.sess[i] == sess_traded:
                continue
            if not (p.sess_start <= s.ny_min[i] < p.sess_end):
                continue
            if p.adx_max > 0 and (np.isnan(adx[i]) or adx[i] >= p.adx_max):
                continue
            if p.ext_max > 0 and (np.isnan(ema[i]) or side * (s.c[i] - ema[i]) / a >= p.ext_max):
                continue
            if i < 1:
                continue
            if side > 0:
                l2, l1 = hi2[i - 1], hi1[i - 1]
                s2 = not np.isnan(l2) and s.h[i] > l2 + p.break_ticks
                s1 = not np.isnan(l1) and s.h[i] > l1 + p.break_ticks
            else:
                l2, l1 = slo2[i - 1], slo1[i - 1]
                s2 = not np.isnan(l2) and s.l[i] < l2 - p.break_ticks
                s1 = not np.isnan(l1) and s.l[i] < l1 - p.break_ticks
            if s2:
                orders["entry"] = ("new", 2, a)
            elif s1:
                if p.skip_win and last_win:
                    last_win = False
                else:
                    orders["entry"] = ("new", 1, a)
            if orders["entry"] is not None and p.armed_stop:
                orders["armed"] = (s.c[i] - side * p.atr_mult * a, False)
            continue

        if pos["units"] < p.max_units and p.pyr_step > 0:
            if (s.h[i] >= pos["add"]) if side > 0 else (s.l[i] <= pos["add"]):
                orders["entry"] = ("add", pos["sys"], a)

        ok_next = (i + 1 < s.n and s.sess[i + 1] == s.sess[i]
                   and s.ny_min[i + 1] <= p.flatten_min + p.flat_grace)
        want_flat = p.flatten_min >= 0 and s.ny_min[i] >= p.flatten_min
        hold_out = p.max_hold > 0 and (i - pos["bar"]) >= p.max_hold
        if p.flatten_min < 0:
            if hold_out:
                orders["flat"], orders["entry"] = "hold", None
        elif want_flat or hold_out or not ok_next:
            orders["entry"] = None
            if ok_next:
                orders["flat"] = "hold" if (hold_out and not want_flat) else True
            else:
                px = s.c[i]
                gross = side * (px - pos["avg"]) * pos["units"]
                cost = pos["units"] * (p.cost_abs + p.cost_bp * 1e-4 * pos["avg"])
                trades.append({"entry_bar": pos["bar"], "exit_bar": i, "units": pos["units"],
                               "pnl": gross - cost,
                               "reason": "max_hold" if (hold_out and not want_flat)
                                         else "session_flatten",
                               "risk": pos["risk"], "sys": pos["sys"]})
                last_win = side * (s.c[i] - pos["first"]) > 0
                pos = None
                orders = {"entry": None, "stop": None, "tp": None, "flat": False, "armed": None}
                continue

        if not orders["flat"]:
            lvl, from_chan = pos["stop"], False
            if p.use_chan_exit:
                ch = (lo1[i] if pos["sys"] == 1 else lo2[i]) if side > 0 else \
                     (shi1[i] if pos["sys"] == 1 else shi2[i])
                if not np.isnan(ch):
                    if (ch > lvl) if side > 0 else (ch < lvl):
                        lvl, from_chan = ch, True
            orders["stop"] = (lvl, from_chan)
            orders["tp"] = pos["tp"]

    if pos is not None:
        px = s.c[s.n - 1]
        gross = side * (px - pos["avg"]) * pos["units"]
        cost = pos["units"] * (p.cost_abs + p.cost_bp * 1e-4 * pos["avg"])
        trades.append({"entry_bar": pos["bar"], "exit_bar": s.n - 1, "units": pos["units"],
                       "pnl": gross - cost, "reason": "data_end", "risk": pos["risk"],
                       "sys": pos["sys"]})
    return trades


def compare(s: Series, p: P, label: str = "") -> tuple[bool, str]:
    fast = run(s, p)
    slow = reference(s, p)
    if len(fast) != len(slow):
        return False, f"{label}: trade count {len(fast)} vs {len(slow)}"
    for k, (a, b) in enumerate(zip(range(len(fast)), slow)):
        if fast.entry_bar[k] != b["entry_bar"] or fast.exit_bar[k] != b["exit_bar"]:
            return False, (f"{label}: trade {k} bars ({fast.entry_bar[k]},{fast.exit_bar[k]}) "
                           f"vs ({b['entry_bar']},{b['exit_bar']})")
        if fast.units[k] != b["units"]:
            return False, f"{label}: trade {k} units {fast.units[k]} vs {b['units']}"
        if abs(fast.pnl[k] - b["pnl"]) > 1e-8 * max(1.0, abs(b["pnl"])):
            return False, f"{label}: trade {k} pnl {fast.pnl[k]} vs {b['pnl']}"
        if T.EXIT_NAMES[fast.reason[k]] != b["reason"]:
            return False, (f"{label}: trade {k} reason {T.EXIT_NAMES[fast.reason[k]]} "
                           f"vs {b['reason']}")
    return True, f"{label}: {len(fast)} trades identical"


# ================================================================= synthetic series

def random_walk(n_sess: int = 400, bars: int = 96, sigma: float = 0.0015, seed: int = 20250822,
                start: float = 20_000.0, drift: float = 0.0, sub: int = 60) -> Series:
    """A driftless martingale, aggregated to bars from a fine intrabar PATH.

    The first version of this generator drew the wick lengths as independent noise around the
    open-to-close leg.  That is not a martingale path, and the engine correctly reported a large
    loss on it: a stop filled at a low the path never actually visited on its way to the next
    open books a price that is systematically worse than the price at that instant, so every
    stop-out harvested the fabricated wick.  -20 points per unit on a driftless series, from the
    data generator alone.

    Building each bar from `sub` sub-steps of the same walk and taking the running max/min removes
    it: every high and low is a price the path really traded, in order, so a stop level touched
    inside the bar is a genuine stopping time and the optional-stopping expectation is zero.
    """
    rng = np.random.default_rng(seed)
    n = n_sess * bars
    steps = rng.normal(drift / sub, sigma / np.sqrt(sub), n * sub)
    path = (start * np.exp(np.cumsum(steps))).reshape(n, sub)
    o = np.concatenate(([start], path[:-1, -1]))
    c = path[:, -1]
    h = np.maximum(path.max(axis=1), o)
    l = np.minimum(path.min(axis=1), o)
    ny_min = np.tile(np.arange(bars) * 5 + 360, n_sess)
    sess = np.repeat(np.arange(n_sess), bars)
    ts = np.arange(n, dtype=np.int64) * 5
    return Series(o, h, l, c, np.ones(n), ny_min, sess, ts, name="RW", tf=5)


# ================================================================= the checks

def check_mirror(series_list) -> list[str]:
    """Fast kernel vs the literal reference, across the corners of the parameter space."""
    cases = [
        ("spec defaults", P()),
        ("T1 preset", P(adx_max=22.0, ext_max=3.964)),
        ("session-gated", P(sess_start=420, sess_end=660, flatten_min=660)),
        ("scalp + tp", P(sess_start=420, sess_end=660, flatten_min=660, tp_r=2.0,
                         entry1=10, entry2=20, exit1=5, exit2=8, atr_len=14, atr_mult=1.5)),
        ("no pyramid", P(pyr_step=0.0, max_units=1, sess_start=420, sess_end=660, flatten_min=660)),
        ("no chan exit", P(use_chan_exit=False, sess_start=420, sess_end=660, flatten_min=660,
                           tp_r=1.5)),
        ("armed stop", P(armed_stop=True, sess_start=420, sess_end=660, flatten_min=660)),
        ("one shot", P(one_shot=True, sess_start=420, sess_end=660, flatten_min=660, max_hold=12)),
        ("costs on", P(sess_start=420, sess_end=660, flatten_min=660, cost_abs=2.0,
                       stop_slip=1.0, tp_r=2.0, tp_rests=True)),
        ("bp costs", P(sess_start=420, sess_end=660, flatten_min=660, cost_bp=10.0,
                       stop_slip=0.0005)),
        ("short mirror", P(side=-1, sess_start=420, sess_end=660, flatten_min=660, tp_r=2.0)),
        ("break ticks", P(break_ticks=2.0, sess_start=420, sess_end=660, flatten_min=660)),
    ]
    out = []
    for s in series_list:
        for label, p in cases:
            ok, msg = compare(s, p, f"{s.name}{s.tf}m/{label}")
            out.append(("OK  " if ok else "FAIL") + "  " + msg)
    return out


NULL_SUB = 480
"""Sub-steps per bar in the null generator.

At 60 the null reads +4.69 points per position (t=5.28, 2.3 bp of price) and at 480 it reads +0.81
(t=0.90, 0.4 bp) on the same configuration -- it converges to zero as the generated path refines.
That is the signature of stop-fill overshoot in the GENERATOR: with coarse sub-steps the walk jumps
past the stop level and the engine, like every bar-level backtest, books the fill at the level
rather than at the price the jump reached.  It is not an engine defect and it does not vanish on
real data, where the bar is all there is; it is the reason `stop_slip` is a per-instrument cost
input rather than zero, and every instrument's `stop_slip` is set larger than the artifact.
"""


def _null_run(p: P, reps: int, drift: float = 0.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Gross position P&L (costs added back), units, and the take-profit share, over `reps` walks.

    The quantity with a zero expectation on a martingale is the TOTAL P&L of a position, not its
    P&L per unit.  Optional stopping makes every (fill, exit) pair fair, so the sum over units is
    fair -- but dividing by the unit count re-weights the sample by an outcome-correlated number.
    Pyramiding adds units exactly when price has run in favour, so the per-unit average
    systematically underweights the winners: on a driftless walk the engine reports -16 per unit
    with a total P&L that is statistically zero.  That is a property of the ratio, and testing it
    would have condemned a correct engine.
    """
    gross, units, tp = [], [], []
    per_unit_cost = p.cost_abs + p.cost_bp * 1e-4 * 20_000.0
    for k in range(reps):
        s = random_walk(seed=1000 + k, drift=drift, sub=NULL_SUB)
        r = run(s, p)
        if len(r):
            gross.append(r.pnl + r.units * per_unit_cost)
            units.append(r.units.astype(float))
            tp.append((r.reason == T.EX_TP).astype(float))
    return np.concatenate(gross), np.concatenate(units), np.concatenate(tp)


def check_null(reps: int = 12) -> list[str]:
    """Stage 0: a martingale must pay zero gross, and exactly minus the modelled cost net.

    The stop-only variants are the clean null -- nothing for the engine to resolve ambiguously, so
    the gross expectation is exactly zero and a significant deviation is a bug.  The take-profit
    variant carries the engine's one deliberate pessimism (a bar holding both barriers is booked at
    the stop), so it is reported with the size of that pessimism rather than gated on zero.
    """
    out = []
    base = P(sess_start=420, sess_end=660, flatten_min=660, entry1=10, entry2=20,
             exit1=5, exit2=8, atr_len=14, atr_mult=1.5)
    cases = [
        ("long, stop only, no cost", T.replace(base), True),
        ("short, stop only, no cost", T.replace(base, side=-1), True),
        ("long, stop only, cost 20", T.replace(base, cost_abs=20.0), True),
        ("long, bp cost 10", T.replace(base, cost_bp=10.0), True),
        ("long, no pyramid", T.replace(base, pyr_step=0.0, max_units=1), True),
        ("long, no chan exit", T.replace(base, use_chan_exit=False), True),
        ("long, armed stop", T.replace(base, armed_stop=True), True),
        ("long, one shot + hold cap", T.replace(base, one_shot=True, max_hold=12), True),
        ("long, +2R tp, no cost", T.replace(base, tp_r=2.0), False),
        ("long, +1R tp, no cost", T.replace(base, tp_r=1.0), False),
    ]
    for tag, pp, gate in cases:
        g, u, tp = _null_run(pp, reps)
        se = g.std(ddof=1) / np.sqrt(len(g))
        t = g.mean() / se
        flag = ("OK  " if abs(t) < 3.0 else "FAIL") if gate else "note"
        extra = f"  tp exits {tp.mean():5.1%}" if pp.tp_r > 0 else ""
        out.append(f"{flag}  null {tag:<26} n={len(g):6,d}  gross/position {g.mean():+8.3f}  "
                   f"t={t:+5.2f}  units {u.mean():.2f}{extra}")

    # Power check: a planted drift must be detected, and detection must scale with it.
    for d in (0.0, 0.00003, 0.00010):
        g, _, _ = _null_run(T.replace(base), reps, drift=d)
        t = g.mean() / (g.std(ddof=1) / np.sqrt(len(g)))
        out.append(f"note  power  drift/bar {d:.5f}  gross/position {g.mean():+9.3f}  t={t:+6.2f}")
    return out


def check_truncation(s: Series, p: P, cuts=(0.3, 0.5, 0.75)) -> list[str]:
    """Re-run on a truncated series: every decision before the cut must be unchanged.

    This is the test that catches a condition reading a bar it has not reached.  A rule that
    peeks -- at the fill bar, at a future ATR, at a same-bar close it should not have -- gives a
    different answer when the future is removed, and gives it here.
    """
    full = run(s, p)
    out = []
    for frac in cuts:
        k = int(s.n * frac)
        sub = Series(s.o[:k], s.h[:k], s.l[:k], s.c[:k], s.v[:k], s.ny_min[:k], s.sess[:k],
                     s.ts[:k], name=s.name, tf=s.tf)
        part = run(sub, p)
        # Compare every trade that closed strictly before the cut, ignoring the one the truncation
        # forces to close at the artificial data end.
        keep_f = full.exit_bar < k - 1
        keep_p = part.exit_bar < k - 1
        a = np.stack([full.entry_bar[keep_f], full.exit_bar[keep_f], full.units[keep_f]])
        b = np.stack([part.entry_bar[keep_p], part.exit_bar[keep_p], part.units[keep_p]])
        same = a.shape == b.shape and np.array_equal(a, b) and np.allclose(
            full.pnl[keep_f], part.pnl[keep_p], atol=1e-9)
        out.append(("OK  " if same else "FAIL") +
                   f"  truncation {frac:.0%}: {a.shape[1]} vs {b.shape[1]} trades before cut")
    return out


def check_window(s: Series, lo: int, hi: int) -> list[str]:
    """A windowed Series must produce exactly the trades the full series produces.

    The search evaluates each configuration against thousands of control draws, which is only
    affordable on the ~10% of bars inside the session window.  That is a correctness claim, not a
    speed one: the window has to carry the channel and ATR readings computed on the bars it drops,
    and the flatten has to land on a bar the window still contains.  If either is wrong the fast
    path quietly trades a different strategy from the one that was verified.
    """
    out = []
    w = s.window(lo, hi)
    cases = [
        ("plain", P(sess_start=420, sess_end=660, flatten_min=660)),
        ("tp+gates", P(sess_start=420, sess_end=660, flatten_min=660, tp_r=2.0, adx_max=22.0,
                       ext_max=3.9, entry1=10, entry2=30, exit1=4, exit2=8, atr_mult=1.5)),
        ("short", P(side=-1, sess_start=570, sess_end=660, flatten_min=660, max_hold=8)),
        ("costs", P(sess_start=420, sess_end=600, flatten_min=660, cost_abs=2.0, stop_slip=1.0,
                    one_shot=True)),
    ]
    for tag, p in cases:
        a, b = run(s, p), run(w, p)
        # Bar indices differ between the two (the window renumbers), so compare on timestamps.
        ok = (len(a) == len(b)
              and np.array_equal(s.ts[a.entry_bar], w.ts[b.entry_bar])
              and np.array_equal(s.ts[a.exit_bar], w.ts[b.exit_bar])
              and np.array_equal(a.units, b.units)
              and np.allclose(a.pnl, b.pnl, atol=1e-9)
              and np.array_equal(a.reason, b.reason))
        out.append(("OK  " if ok else "FAIL") +
                   f"  window {tag:<10} full {len(a):5,d} trades, windowed {len(b):5,d}")
    return out


def check_forced(s: Series) -> list[str]:
    """The forced-entry channel must reproduce the rule when fed the rule's own triggers."""
    out = []
    for tag, p in (("plain", P(sess_start=420, sess_end=660, flatten_min=660)),
                   ("tp", P(sess_start=420, sess_end=660, flatten_min=660, tp_r=2.0)),
                   ("short", P(side=-1, sess_start=420, sess_end=660, flatten_min=660))):
        # skip_win must be off: the forced channel carries no notion of which system fired for a
        # signal the state machine chose to ignore, so the two would legitimately diverge.
        pp = T.replace(p, skip_win=False)
        a = run(s, pp)
        b = run(s, pp, forced=T.signal_bars(s, pp))
        ok = (len(a) == len(b) and np.array_equal(a.entry_bar, b.entry_bar)
              and np.allclose(a.pnl, b.pnl, atol=1e-9))
        out.append(("OK  " if ok else "FAIL") +
                   f"  forced {tag:<7} rule {len(a):5,d} trades, replayed {len(b):5,d}")
    return out


def main() -> None:
    import turtle_bars as B

    print("=" * 78, "\nKernel vs literal Pine transcription\n", "=" * 78)
    series = [random_walk(n_sess=250, seed=7)]
    for nm, tf, nsess in (("US30", 5, 500), ("XAU", 15, 500), ("BTC", 15, 500)):
        s = B.load(nm, tf)
        k = int(np.searchsorted(s.sess, nsess))
        series.append(Series(s.o[:k], s.h[:k], s.l[:k], s.c[:k], s.v[:k], s.ny_min[:k],
                             s.sess[:k], s.ts[:k], name=nm, tf=tf))
    fails = 0
    for line in check_mirror(series):
        if line.startswith("FAIL"):
            fails += 1
            print(line)
    print(f"  {len(series) * 12 - fails} / {len(series) * 12} configurations identical")

    print("\n" + "=" * 78, "\nStage 0 -- null calibration on a martingale\n", "=" * 78)
    for line in check_null():
        print("  " + line)
        fails += line.startswith("FAIL")

    print("\n" + "=" * 78, "\nLook-ahead probe -- truncate and re-decide\n", "=" * 78)
    for nm, tf in (("US30", 5), ("XAU", 15), ("BTC", 15)):
        s = B.load(nm, tf)
        k = int(np.searchsorted(s.sess, 800))
        sub = Series(s.o[:k], s.h[:k], s.l[:k], s.c[:k], s.v[:k], s.ny_min[:k], s.sess[:k],
                     s.ts[:k], name=nm, tf=tf)
        p = P(sess_start=420, sess_end=660, flatten_min=660, adx_max=22.0, ext_max=3.9,
              tp_r=2.0, cost_abs=1.0)
        for line in check_truncation(sub, p):
            print(f"  {nm} {tf}m  " + line)
            fails += line.startswith("FAIL")

    print("\n" + "=" * 78, "\nWindowed evaluation == full evaluation\n", "=" * 78)
    for nm, tf in (("US30", 5), ("XAU", 15), ("BTC", 15)):
        s = B.load(nm, tf)
        k = int(np.searchsorted(s.sess, 900))
        sub = Series(s.o[:k], s.h[:k], s.l[:k], s.c[:k], s.v[:k], s.ny_min[:k], s.sess[:k],
                     s.ts[:k], name=nm, tf=tf)
        for line in check_window(sub, 420, 720):
            print(f"  {nm} {tf}m  " + line)
            fails += line.startswith("FAIL")
        for line in check_forced(sub):
            print(f"  {nm} {tf}m  " + line)
            fails += line.startswith("FAIL")

    print("\n" + ("ALL CHECKS PASS" if fails == 0 else f"{fails} FAILURES"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
