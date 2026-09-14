"""V34 -- the entry MECHANIC, pre-registered, on the true 1-minute path, intraday only.

WHY THIS AND NOT ANOTHER SIGNAL SEARCH. Three independent measurements on this branch now say
in-sample ranking carries no information about out-of-sample ranking here: V30's surrogate (research
surface fitted at rho 0.96, locked predicted at 0.07), V31's cross-family (research-to-locked R
correlation +0.215), V33's negative train-to-validation rank transfer (-0.05 to -0.375 over 207,360
configurations). A fourth search of the same family finds a fourth spurious maximum. So this is not
a search. It is FIVE DECLARED HYPOTHESES about the one effect on this branch large enough to survive
being looked for:

  A resting limit 1.0xATR in your favour is worth +0.24 to +0.43 R/trade across four markets
  (`research/atme/`), against a best-ever SIGNAL of +0.043 R. Six to ten times. It is monotone in
  depth, present on BOTH SIDES so it is not drift, and it INVERTS as a stop entry -- chasing a
  breakout is the most reliably destructive choice in the whole search.

THE HYPOTHESES, WRITTEN BEFORE THE FIRST RUN:

  H1  On the same signals, same barriers, same intraday flatten, a resting limit beats a market
      order at the next open. Measured PER SIGNAL, not per trade -- an unfilled limit earns nothing
      and per-trade accounting hides that.
  H2  The advantage is MONOTONE in depth over 0.25 / 0.50 / 0.75 / 1.00 x ATR(5).
  H3  It is present on BOTH SIDES. If it only works long it is drift, not a mechanic.
  H4  It beats a MINUTE-OF-DAY MATCHED CONTROL -- random entries at the same minutes, identical
      geometry, identical flatten, same one-order policy.
  H5  It holds on the LOCKED block, and survives `through_ticks=4` and 1.5x cost.

32 declared cells: 2 signal sets x 2 timeframes x 4 depths x 2 sides. Plus 8 market-order twins.
The count is stated here, before the results, and carried into the reporting.

THE INTRADAY CONSTRAINT IS THE USER'S, AND IT IS EXPENSIVE. Seven measurements on this branch put
the cost of a hard daily flatten at up to 88% of the result: winners run a median 2.1h against
losers' 0.8h, overnight trades supplied 338% of net P&L in one study, and in another 0 of 1,027
trades ever reached a 5R target because the clock closed them first. It is run as specified, and an
unconstrained variant is run beside it so the size of the constraint is measured rather than argued.

WHAT MAKES THE NUMBER TRUSTWORTHY HERE and did not before:
  * TRUE 1-MINUTE PATH. `STUDY_ATME_LIVE` cut a selected configuration from +0.331 R to -0.003
    purely by resolving exit ORDER at minute resolution instead of by rule. A limit-entry result on
    bar data measures intrabar ordering, not edge.
  * ONE LIVE ORDER. `_walk_limit` holds a single resting order with a position lock. `eem.run`'s
    model filled eight simultaneous orders and kept 24-47% of its R when corrected.
  * REAL COSTS. `limit_entry` ships the old broker-only stack, so `cost_mult=1.44` is passed
    everywhere; `entry_ec_mult=1.0` makes the limit pay the SAME entry friction as the market order,
    which is conservative -- a resting order should pay less.
  * THROUGH-FILLS. An order at the exact low of a swing is the LEAST likely to fill in reality.
    `through_ticks` requires price to trade through the level.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import indicators as I        # noqa: E402
import intrabar as IB         # noqa: E402
import limit_entry as LE      # noqa: E402
sys.path.insert(0, "research/v34")
import v34one as O           # noqa: E402

COST_MULT = 1.44              # the real MNQ stack; the module ships broker-only
STOP_MULT = 2.0
TP_R = 2.0                    # target = 4.0N. Declared, not swept.
WIN_START, WIN_END = 570, 900     # entries 09:30-15:00 New York
CANCEL_MOD = 900                  # the resting order is cancelled at 15:00
FLAT_MIN = 955                    # the position is flattened at 15:55
EXPIRY = 2                        # chart bars the order may rest for
DEPTHS = (0.25, 0.50, 0.75, 1.00)
TFS = (5, 15)
SIDES = (1, -1)
SIGNALS = ("everybar", "donch")
SPLIT = 0.65


def prep(tf):
    m = IB.minute_map(tf)
    return m, m["d"]


def blocks(tf):
    _m, d = prep(tf)
    sess = d["sess"] if "sess" in d else None
    if sess is None:
        idx = d["df"].index
        sess = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy()
    u = np.unique(sess)
    cut = u[int(len(u) * SPLIT)]
    return sess < cut, sess >= cut, sess


def signals(kind, tf, side, intraday=True):
    """Trigger BAR INDICES -- `limit_entry` takes indices, not a mask."""
    _m, d = prep(tf)
    h, l, c = d["h"], d["l"], d["c"]
    mod = d["mod"] if "mod" in d else None
    if mod is None:
        idx = d["df"].index
        mod = (idx.hour * 60 + idx.minute).to_numpy(np.int64)
    ok = np.isfinite(d["atr"]) & (d["atr"] > 0)
    if kind == "everybar":
        m = ok.copy()
    else:
        ent_hi = I.shift(I.rmax(h, 30), 1)
        ent_lo = I.shift(I.rmin(l, 30), 1)
        m = ok & ((h > ent_hi) if side > 0 else (l < ent_lo))
        m &= np.isfinite(ent_hi if side > 0 else ent_lo)
    if intraday:
        m &= (mod >= WIN_START) & (mod < WIN_END)
    m[-3:] = False
    return np.flatnonzero(m).astype(np.int64), mod


def run_limit(tf, trig, side, depth, through=0.0, cost=COST_MULT, intraday=True, one=True):
    """`one=True` uses the CORRECTED walker, in which a resting order holds the lock until it
    fills or expires. `limit_entry._walk_limit` releases the lock only on EXIT, so an unfilled
    resting order blocks nothing and the backtest holds a BOOK of simultaneous orders -- a mean of
    2.45 at expiry 2 and 15.9 at expiry 18 (`order_audit.py`). A script holds one. Everything V34
    reports is scored with `one=True`; `one=False` exists only to measure the artifact."""
    fn = O.run_1m_one if one else LE.run_1m
    kw = {} if one else dict(lim_atr_n=5)
    pnl, sb, xb, why, nfill, ntry = fn(
        tf, trig, side=side, lim_mult=depth, lim_atr_n=5, stop_mult=STOP_MULT, tp_r=TP_R,
        flat_min=FLAT_MIN if intraday else 0, expiry=EXPIRY,
        cancel_mod=CANCEL_MOD if intraday else 0, cost_mult=cost, entry_ec_mult=1.0,
        through_ticks=through)
    return dict(pnl=pnl, sig=sb, why=why, nfill=int(nfill), ntry=int(ntry))


def run_market(tf, trig, side, cost=COST_MULT, intraday=True):
    """The same signals taken as a MARKET order at the next open, same 1-minute path, same costs."""
    m, d = prep(tf)
    pnl, eb, xb, why, amb = IB._walk(
        m["o"], m["h"], m["l"], m["c"], m["mod"], m["lo"], m["hi"], d["atr"],
        np.asarray(trig, np.int64), np.int64(side), float(STOP_MULT), float(TP_R),
        np.int64(FLAT_MIN if intraday else 0), np.int64(0),
        LE.PV, LE.COMM * cost, LE.EC * cost, LE.SE * cost)
    return dict(pnl=pnl, sig=eb - 1, why=why, nfill=len(pnl), ntry=len(trig), amb=amb)


def stat(res, n_signals):
    """PER SIGNAL is the honest denominator: an unfilled limit earns nothing but consumed the
    opportunity. Per-trade is reported beside it, never instead of it."""
    p = res["pnl"]
    if len(p) == 0:
        return None
    return dict(n=len(p), signals=int(n_signals), fill=len(p) / max(n_signals, 1),
                per_signal=float(p.sum() / max(n_signals, 1)),
                per_trade=float(p.mean()), total=float(p.sum()),
                win=float((p > 0).mean()),
                pf=float(p[p > 0].sum() / abs(p[p < 0].sum())) if (p < 0).any() else np.nan)


def control(tf, side, depth, mod, block_mask, n_draw, pool_mod, draws=200, seed=17,
            through=0.0):
    """MINUTE-OF-DAY MATCHED CONTROL: random entry bars drawn to match the signal's minute-of-day
    histogram, then run through the IDENTICAL mechanic, geometry, flatten and one-order policy."""
    rng = np.random.default_rng(seed)
    _m, d = prep(tf)
    ok = np.isfinite(d["atr"]) & (d["atr"] > 0) & block_mask
    ok[-3:] = False
    by_mod = {}
    for mm in np.unique(pool_mod):
        cand = np.flatnonzero(ok & (mod == mm))
        if len(cand):
            by_mod[int(mm)] = cand
    counts = pd.Series(pool_mod).value_counts()
    out = []
    for _ in range(draws):
        parts = []
        for mm, k in counts.items():
            pool = by_mod.get(int(mm))
            if pool is None or not len(pool):
                continue
            parts.append(rng.choice(pool, size=min(int(k), len(pool)), replace=False))
        if not parts:
            continue
        t = np.sort(np.concatenate(parts)).astype(np.int64)
        r = run_limit(tf, t, side, depth, through=through)
        s = stat(r, len(t))
        if s:
            out.append((s["per_signal"], s["per_trade"], s["pf"]))
    a = np.array(out)
    return dict(per_signal=a[:, 0], per_trade=a[:, 1], pf=a[:, 2])
