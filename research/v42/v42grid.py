"""V42 -- the Turtle parameter space, scored by the MEDIAN OF ITS WALK-FORWARD FOLDS.

THE OBJECTIVE, chosen by the user and not by me: a configuration's score is the MEDIAN of its
per-fold result across chronological folds, not its aggregate. A config carried by one lucky
period has a low median even when its total is the grid's best. That is the whole point of the
statistic and it is why the aggregate columns are computed but never ranked on.

THE SEARCH RUNS ON US100 ONLY. US30 and NQ are held back and are not read until a configuration
is frozen. `STUDY_TURTLE` measured this exact system's ENTRY against a risk-matched random-entry
control and found +0.595 against +0.601, excess -0.005 at p 0.475 -- so nothing here is expected
to come from the breakout, and whatever is carried forward gets that same control run on it.

TWO AXES INTERACT TO PRODUCE DUPLICATE CELLS, and the effective count is what a multiplicity
correction must use. The ladder is OFF whenever `pyramid_step == 0` OR `max_units == 1`, and in
that state the other axis does nothing. Of the 16 (pyramid_step, max_units) pairs, 7 are
ladder-off and collapse to one, so 16 -> 10 distinct. Nominal 1,843,200 cells; EFFECTIVE
1,152,000.

THE CACHED-EXIT-TENSOR TRICK DOES NOT APPLY HERE. `core.run` re-anchors the stop to each new
fill, so a trade's outcome depends on the whole add sequence and not just its signal bar and
geometry. Every cell is a full walk of the bars. Measured at 0.131 ms per config on 240-minute
bars, which is what makes a seven-figure sweep affordable at all.

Usage: imported by run_v42.py
"""
from __future__ import annotations

import sys
from itertools import product

import numpy as np

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
import indicators as I       # noqa: E402
import core                  # noqa: E402
import data as TD            # noqa: E402

TFS = (60, 120, 240)
ENTRY1 = (10, 15, 20, 30, 40)
ENTRY2 = (40, 55, 70, 100)
EXIT1 = (5, 10, 15, 20)
EXIT2 = (10, 20, 30)
ATR_MULT = (1.5, 2.0, 2.5, 3.0, 4.0)
PYR_STEP = (0.0, 0.25, 0.5, 1.0)
MAX_UNITS = (1, 2, 3, 4)
ADX_GATE = ("off", "adx<22", "adx>=20", "adx>=25")
EXT_GATE = ("off", "ext<3.193", "ext<3.964", "ext>=3.0")
SKIP_WIN = (True, False)

N_NOMINAL = (len(TFS) * len(ENTRY1) * len(ENTRY2) * len(EXIT1) * len(EXIT2) * len(ATR_MULT)
             * len(PYR_STEP) * len(MAX_UNITS) * len(ADX_GATE) * len(EXT_GATE) * len(SKIP_WIN))
_LADDER_PAIRS = len(PYR_STEP) * len(MAX_UNITS)
_OFF = len(MAX_UNITS) + len(PYR_STEP) - 1          # pyr==0 or units==1
N_EFFECTIVE = N_NOMINAL // _LADDER_PAIRS * (_LADDER_PAIRS - _OFF + 1)

N_FOLDS = 8
MIN_TRADES_PER_FOLD = 8


def ladder_off(pyr, units):
    return pyr == 0.0 or units == 1


def prep(inst, tf):
    """Bars plus every series any cell can ask for, computed once per (instrument, timeframe)."""
    d = TD.bars(inst, tf)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr = I.rma(I.true_range(h, l, c), 20)          # Wilder, as ta.atr and the Turtle spec
    adx, _p, _m = I.adx_di(h, l, c, 14)
    ema100 = I.ema(c, 100)
    with np.errstate(divide="ignore", invalid="ignore"):
        ext = np.where(atr > 0, (c - ema100) / atr, 0.0)
    P = dict(o=o, h=h, l=l, c=c, atr=atr, n=len(c), inst=inst, tf=tf,
             idx=np.asarray(d["idx"]).astype("datetime64[ns]").astype("int64"),
             cost=TD.COSTS[inst])
    P["hi"] = {k: I.shift(I.rmax(h, k), 1) for k in set(ENTRY1) | set(ENTRY2)}
    P["lo"] = {k: I.shift(I.rmin(l, k), 1) for k in set(EXIT1) | set(EXIT2)}
    P["gate"] = {}
    for a in ADX_GATE:
        ga = (np.ones(len(c), np.bool_) if a == "off" else
              adx < 22.0 if a == "adx<22" else
              adx >= 20.0 if a == "adx>=20" else adx >= 25.0)
        for e in EXT_GATE:
            ge = (np.ones(len(c), np.bool_) if e == "off" else
                  ext < 3.193 if e == "ext<3.193" else
                  ext < 3.964 if e == "ext<3.964" else ext >= 3.0)
            P["gate"][(a, e)] = np.ascontiguousarray(ga & ge & np.isfinite(atr) & (atr > 0))
    # fold edges over the instrument's own calendar, fixed once so every cell is folded alike
    P["fold"] = np.searchsorted(np.quantile(P["idx"], np.linspace(0, 1, N_FOLDS + 1)[1:-1]),
                                P["idx"])
    return P


def run_cell(P, cfg):
    """One configuration. Returns per-trade points, risk and the entry bar.

    `core.run` (the njit kernel) returns NINE arrays -- pnl, risk, units, system, why, bar_in,
    bar_out, mfe, mae. The four-value return further down that file belongs to `run_random`."""
    pnl, risk, _u, _sy, _w, tin, _bo, _mfe, _mae = core.run(
        P["o"], P["h"], P["l"], P["c"],
        P["hi"][cfg["entry1"]], P["hi"][cfg["entry2"]],
        P["lo"][cfg["exit1"]], P["lo"][cfg["exit2"]], P["atr"], 120,
        float(cfg["atr_mult"]), float(cfg["pyr"]), int(cfg["units"]),
        bool(cfg["skip"]), True, True,
        P["cost"]["cost_pts"], P["cost"]["slip_pts"],
        P["gate"][(cfg["adx"], cfg["ext"])], True)
    return pnl, risk, tin


def fold_score(P, pnl, risk, tin):
    """THE OBJECTIVE: the median across folds of per-trade R, plus the aggregates for reference.

    A fold with fewer than MIN_TRADES_PER_FOLD trades contributes NaN rather than a number built
    on nothing; a cell whose folds are mostly empty scores NaN overall and is dropped."""
    if len(pnl) < N_FOLDS * MIN_TRADES_PER_FOLD // 2:
        return None
    R = pnl / np.maximum(risk, 1e-9)
    f = P["fold"][tin]
    per = np.full(N_FOLDS, np.nan)
    for k in range(N_FOLDS):
        m = f == k
        if m.sum() >= MIN_TRADES_PER_FOLD:
            per[k] = R[m].mean()
    ok = np.isfinite(per)
    if ok.sum() < N_FOLDS - 2:
        return None
    w, lo = pnl[pnl > 0], pnl[pnl < 0]
    return dict(median_fold=float(np.nanmedian(per)),
                min_fold=float(np.nanmin(per)), max_fold=float(np.nanmax(per)),
                folds_scored=int(ok.sum()), folds_positive=int((per[ok] > 0).sum()),
                n=len(pnl), agg_R=float(R.mean()),
                pf=float(w.sum() / abs(lo.sum())) if len(lo) else np.nan,
                pts=float(pnl.mean()))


def configs():
    for tf, e1, e2, x1, x2, am, pyr, mu, ax, ex, sk in product(
            TFS, ENTRY1, ENTRY2, EXIT1, EXIT2, ATR_MULT, PYR_STEP, MAX_UNITS,
            ADX_GATE, EXT_GATE, SKIP_WIN):
        yield dict(tf=tf, entry1=e1, entry2=e2, exit1=x1, exit2=x2, atr_mult=am,
                   pyr=pyr, units=mu, adx=ax, ext=ex, skip=sk,
                   dup=ladder_off(pyr, mu) and not (pyr == 0.0 and mu == 1))
