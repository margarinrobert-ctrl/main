"""V51 -- a FRESH single-entry / single-exit Donchian with four declared filters, swept whole.

WHAT WAS ASKED FOR, and what each piece is:
  * ONE entry and ONE exit. No System 2, no pyramid ladder. A Donchian breakout in, an ATR stop
    or a Donchian channel out, whichever is nearer the market, and nothing else.
  * MA 200 AS SUPPORT/RESISTANCE. Not just `close > MA200`: this branch has twice found that a
    "not extended" ceiling INVERTS into a floor (STUDY_TURTLE_15M took PF 0.94 -> 1.58 by requiring
    EMA100 distance >= 3.0 ATR rather than <=). So the mode axis carries BOTH readings -- near the
    average and far from it -- and the sweep decides which, if either, earns a place.
  * A 13 x 48 CROSS for momentum. The lengths are FIXED at the user's 13/48 and the MA is fixed to
    an EMA, because STUDY_MA_LAG measured MA type and MA length as non-degrees-of-freedom here
    (13/48 vs 12/48 vs 15/48 all land within 0.03 PF). Only the READING is swept: the state, or a
    fresh cross within K bars.
  * ABSORPTION, from the user's own chart: a large-volume UP bar that closes well off its high is
    sellers absorbing the buying. Its mirror is buyers absorbing the selling. THIS IS A PROXY AND
    IT IS LABELLED ONE -- real absorption needs bid/ask volume at price and no feed here carries
    it. The filter axis includes REQUIRE and AVOID for both directions, so the sign is measured
    rather than asserted; this branch has already found volume spikes hurt longs MONOTONICALLY
    (-2.45 pts at 1.5x the baseline, -17.88 at 2.0x), which is the same mechanism read from the
    other side.
  * A SESSION WINDOW with an optional flatten. The flatten fills at the NEXT BAR'S OPEN, because
    `strategy.close_all()` cannot sell the close of the bar that triggers it and the engine was
    changed to match the script, not the other way round.

NO TAKE PROFIT and a 480-bar max hold are DECLARED, not swept: no-target has beaten every target
tested on this branch ten times, and the intraday-constraint studies have failed seven.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
import v38feeds as F        # noqa: E402

# Round turn in INDEX POINTS plus a per-fill slippage, the branch's CFD assumptions.
COSTS = {"US100L": dict(cost=1.00, slip=0.25), "US30L": dict(cost=2.00, slip=0.50)}

ENT_N = (10, 20, 30, 55)
EXIT_N = (5, 10, 20, 30)
STOP_N = (1.5, 2.0, 2.5, 3.0)
MAX_HOLD = 480
VOL_MULT = (1.5, 2.0)                      # the branch's own volume-spike rungs
WICK = 0.40                                # close inside the lower 40% of the bar's range

# (start, stop) in MINUTES from New York midnight. Index 0 is "all hours".
WINDOWS = ((0, 1440), (7 * 60, 11 * 60), (8 * 60, 12 * 60), (9 * 60 + 30, 12 * 60),
           (9 * 60 + 30, 16 * 60))
# A session config is (window index, flatten). Flatten is only meaningful inside a window.
SESS = [(0, 0)] + [(w, f) for w in range(1, len(WINDOWS)) for f in (0, 1)]
# The exit tensor only needs the FLATTEN, not the entry window: flatten config 0 is "never".
FLAT_CFG = [0] + list(range(1, len(WINDOWS)))

MA200_MODES = ("off", "above", "near1.5", "near3.0", "far1.5", "far3.0")
CROSS_MODES = ("off", "state", "recent5", "recent20")
ABS_MODES = ("off", "req_buy5", "req_buy20", "avoid_sell5", "avoid_sell20",
             "req_sell5", "req_sell20")


def rma(x, n):
    return pd.Series(x).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def true_range(h, l, c):
    pc = np.concatenate(([c[0]], c[:-1]))
    return np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))


def recent(mask, k):
    """True at bar i if `mask` fired on any of bars i-k+1 .. i. Causal by construction."""
    s = pd.Series(np.asarray(mask, float))
    return (s.rolling(k, min_periods=1).max().to_numpy() > 0.5)


def frame(market, tf):
    """`v38feeds.frame` drops the volume column and absorption needs it, so re-derive here from
    the same loader and the same resample rule."""
    f = F.resample(F.load(market), tf)
    return dict(o=f["open"].to_numpy(float), h=f["high"].to_numpy(float),
                l=f["low"].to_numpy(float), c=f["close"].to_numpy(float),
                vol=f["volume"].to_numpy(float),
                ts=f.index.values.astype("datetime64[ns]").astype(np.int64),
                day=(f.index.normalize().values.astype("datetime64[D]").astype(np.int64)),
                mod=(f.index.hour * 60 + f.index.minute).to_numpy(np.int64))


def build(market, tf):
    d = frame(market, tf)
    o, h, l, c, mod = d["o"], d["h"], d["l"], d["c"], d["mod"]
    atr = rma(true_range(h, l, c), 14)
    S = pd.Series(c)
    ema200 = S.ewm(span=200, adjust=False).mean().to_numpy()
    e13 = S.ewm(span=13, adjust=False).mean().to_numpy()
    e48 = S.ewm(span=48, adjust=False).mean().to_numpy()
    P = dict(o=o, h=h, l=l, c=c, mod=mod, atr=atr, n=len(c), ts=d["ts"], day=d["day"],
             ema200=ema200, e13=e13, e48=e48, vol=d["vol"])

    # --- entry and exit channels, both shifted so bar i reads only bars up to i-1 --------------
    P["ent_hi"] = {n: pd.Series(h).rolling(n).max().shift(1).to_numpy() for n in ENT_N}
    P["exit_lo"] = {n: pd.Series(l).rolling(n).min().shift(1).to_numpy() for n in EXIT_N}

    # --- MA200 as a level: the distance in ATR, signed ----------------------------------------
    with np.errstate(invalid="ignore", divide="ignore"):
        P["ma_dist"] = (c - ema200) / np.where(atr > 0, atr, np.nan)

    # --- the 13 x 48 cross --------------------------------------------------------------------
    st = e13 > e48
    P["cx_state"] = st
    fresh = st & ~np.concatenate(([False], st[:-1]))
    P["cx_recent"] = {k: recent(fresh, k) for k in (5, 20)}

    # --- ABSORPTION, the user's definition, as a PROXY on OHLCV --------------------------------
    rng = np.maximum(h - l, 1e-9)
    pos = (c - l) / rng                       # where the close sits inside the bar
    base = pd.Series(P["vol"]).rolling(200, min_periods=50).mean().shift(1).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        volrat = P["vol"] / np.where(base > 0, base, np.nan)
    up = c > o
    P["absorb"] = {}
    for m in VOL_MULT:
        hv = np.nan_to_num(volrat, nan=0.0) >= m
        sell = hv & up & (pos <= WICK)         # buyers pushed, sellers absorbed, close off the high
        buy = hv & ~up & (pos >= 1.0 - WICK)   # sellers pushed, buyers absorbed, close off the low
        P["absorb"][m] = dict(sell=sell, buy=buy,
                              sell_r={k: recent(sell, k) for k in (5, 20)},
                              buy_r={k: recent(buy, k) for k in (5, 20)})
    return P


def entry_mask(P, n):
    m = P["h"] > P["ent_hi"][n]
    m = np.asarray(m, bool).copy()
    m[:300] = False
    m[-(MAX_HOLD + 5):] = False
    m &= np.isfinite(P["atr"]) & (P["atr"] > 0) & np.isfinite(P["ma_dist"])
    return m


def filter_masks(P, sig):
    """Every filter reading, evaluated AT THE SIGNAL BAR, as (mode, n_signal) boolean matrices."""
    d = P["ma_dist"][sig]
    MA = np.zeros((len(MA200_MODES), len(sig)), bool)
    MA[0] = True
    MA[1] = d > 0
    MA[2] = (d > 0) & (d <= 1.5)
    MA[3] = (d > 0) & (d <= 3.0)
    MA[4] = d >= 1.5
    MA[5] = d >= 3.0

    CX = np.zeros((len(CROSS_MODES), len(sig)), bool)
    CX[0] = True
    CX[1] = P["cx_state"][sig]
    CX[2] = P["cx_recent"][5][sig]
    CX[3] = P["cx_recent"][20][sig]

    AB = np.zeros((len(VOL_MULT) * len(ABS_MODES), len(sig)), bool)
    for vi, m in enumerate(VOL_MULT):
        a = P["absorb"][m]
        b = vi * len(ABS_MODES)
        AB[b + 0] = True
        AB[b + 1] = a["buy_r"][5][sig]
        AB[b + 2] = a["buy_r"][20][sig]
        AB[b + 3] = ~a["sell_r"][5][sig]
        AB[b + 4] = ~a["sell_r"][20][sig]
        AB[b + 5] = a["sell_r"][5][sig]
        AB[b + 6] = a["sell_r"][20][sig]

    md = P["mod"][sig]
    SS = np.zeros((len(SESS), len(sig)), bool)
    for i, (w, _f) in enumerate(SESS):
        a, b = WINDOWS[w]
        SS[i] = np.ones(len(sig), bool) if w == 0 else ((md >= a) & (md < b))
    return MA, CX, AB, SS
