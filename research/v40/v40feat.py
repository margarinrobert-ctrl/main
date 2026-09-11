"""V40 -- feature engineering and an INDEPENDENCE matrix for a Donchian 40/25 long, 07:00-11:00 NY.

THE SPEC IS THE USER'S AND IS NOT SEARCHED: Donchian 40 entry / 25 exit, 1.5 x ATR(14) stop,
MA(200) as support/resistance, long only, entries 07:00-11:00 New York with a hard flatten at
11:00. The only thing searched is WHICH ADDITIONAL FILTERS to add, and the requirement is that
they be independent of one another.

TWO THINGS THIS BRANCH HAS LEARNED THAT DECIDE HOW INDEPENDENCE IS MEASURED:

  1. MEASURE CORRELATION OVER THE SIGNAL BARS, NOT OVER ALL BARS. A filter only ever acts on
     breakout bars inside the window. Two conditions can be near-orthogonal across the whole tape
     and near-identical on the bars that matter -- and it is the second number that decides whether
     adding both buys anything. `STUDY_V21_ADX_CHOP` measured exactly this: 68.3% of the bars CHOP
     keeps already pass ADX, so on breakout bars they are largely one filter.

  2. A |rho| THRESHOLD DOES NOT CATCH CONCEPTUAL REDUNDANCY. `STUDY_TURTLE_FEATURES` records five
     of six "independent" picks all turning out to be volatility level. So every candidate here is
     declared into a CONCEPT FAMILY by hand, and the selection takes AT MOST ONE PER FAMILY before
     any correlation is looked at. Correlation is the second gate, not the first.

  3. ADX AND THE EFFICIENCY RATIO ARE THE SAME FILTER (rho 0.642 on this branch) and stacking them
     halved the sample for no information. They are therefore in the same family here by
     declaration, so the machinery cannot pick both.

Families, each a genuinely different question about the bar:
    TREND     how strong is the directional move            ADX, DI spread, efficiency ratio
    CHOP      how much of the range was spent going nowhere  CHOP14, range efficiency
    VOLLEVEL  how big is volatility in its own history       ATR percentile, BB width rank
    VOLCHG    is volatility expanding or contracting         ATR vs its mean, TR vs ATR
    LOCATION  where is price against a structural level      distance to MA200, to session levels
    PARTIC    how many participants                          volume vs its time-of-day baseline
    SHAPE     what does THIS candle look like                body share, wick share, close position
    CLOCK     where in the session                           minutes since the window opened

Usage: imported by run_v40.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v20")
sys.path.insert(0, "research/v38")
import indicators as I           # noqa: E402
import v38grid as G              # noqa: E402
from v20linreg import linreg     # noqa: E402

# The user fixed entry 40, exit 25, MA 200, long, 07:00-11:00 with an 11:00 flatten, and then
# explicitly handed the STOP back: "the atr you could manage it the way you see its the most
# lowest matrix correlated and profiable". So `stop_n` is the one geometry axis that is swept,
# on the RESEARCH block only, and read by its MARGINAL CURVE rather than its top cell -- this
# branch has the stop axis running monotone toward wider on every market it has tested, so a
# single best cell there is exactly the kind of number that does not survive.
SPEC = dict(entry_n=40, exit_n=25, stop_n=1.5, tp_r=0.0, ma_n=200, atr_len=14)
STOP_SWEEP = (1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5)
WINDOW = (420, 660)              # 07:00 -> 11:00 New York, minutes of day
FLAT = 660                       # hard flatten at 11:00


def chop(h, l, c, n=14):
    tr = I.true_range(h, l, c)
    return (100 * np.log10(I.rsum(tr, n) / np.maximum(I.rmax(h, n) - I.rmin(l, n), 1e-9))
            / np.log10(n))


def pct_rank(x, n):
    """Percentile of x within its own trailing n bars, exclusive of the current value's future."""
    return pd.Series(x).rolling(n).apply(lambda w: float((w[:-1] <= w[-1]).mean()),
                                         raw=True).to_numpy()


def tod_baseline(x, mod, n=20):
    """A quantity against its own EXPANDING time-of-day mean, shifted so today is excluded.

    A raw volume threshold on an intraday series is mostly a clock: 09:30 is always heavy. Dividing
    by the same minute's own history removes the clock and leaves the surprise."""
    df = pd.DataFrame(dict(x=np.asarray(x, float), m=np.asarray(mod)))
    g = df.groupby("m")["x"]
    base = g.transform(lambda s: s.shift(1).rolling(n, min_periods=5).mean())
    return np.asarray(df["x"] / np.maximum(base, 1e-9))


def features(P):
    """Every candidate feature as a CONTINUOUS series, plus the family it belongs to.

    Continuous, not boolean, because the correlation matrix has to be computed on the underlying
    quantity -- two booleans cut at different thresholds from the same series would show a
    misleadingly low correlation while being the same reading."""
    o, h, l, c = P["o"], P["h"], P["l"], P["c"]
    atr, mod = P["atr"], P["mod"]
    v = P.get("v")
    F = {}

    adx, pdi, mdi = I.adx_di(h, l, c, 14)
    F["adx14"] = ("TREND", adx, "higher = stronger")
    F["di_spread"] = ("TREND", pdi - mdi, "higher = stronger up")
    move = np.abs(c - I.shift(c, 20))
    path = I.rsum(np.abs(np.diff(c, prepend=c[0])), 20)
    F["eff_ratio20"] = ("TREND", move / np.maximum(path, 1e-9), "higher = straighter")

    F["chop14_inv"] = ("CHOP", -chop(h, l, c, 14), "higher = trending")
    F["range_eff14"] = ("CHOP", (I.rmax(h, 14) - I.rmin(l, 14)) / np.maximum(I.rsum(
        I.true_range(h, l, c), 14), 1e-9), "higher = directional")

    F["atr_rank250"] = ("VOLLEVEL", pct_rank(atr, 250), "higher = volatile for this market")
    bup, _bm, blo, _bw = I.bollinger(c, 20, 2.0)
    F["bbwidth_rank250"] = ("VOLLEVEL", pct_rank((bup - blo) / np.maximum(c, 1e-9), 250),
                            "higher = wide bands")

    F["atr_vs_mean"] = ("VOLCHG", atr / np.maximum(I.sma(atr, 20), 1e-9), "higher = expanding")
    F["tr_vs_atr"] = ("VOLCHG", I.true_range(h, l, c) / np.maximum(atr, 1e-9),
                      "higher = this bar is big")

    ma = I.sma(c, SPEC["ma_n"])
    F["dist_ma200_atr"] = ("LOCATION", (c - ma) / np.maximum(atr, 1e-9),
                           "higher = further above support")
    F["ma200_slope_atr"] = ("LOCATION", (ma - I.shift(ma, 20)) / np.maximum(atr, 1e-9),
                            "higher = support rising")

    if v is not None:
        F["vol_vs_tod"] = ("PARTIC", tod_baseline(v, mod, 20), "higher = unusual participation")
        F["vol_trend5"] = ("PARTIC", I.sma(v, 5) / np.maximum(I.sma(v, 20), 1e-9),
                           "higher = building")

    rng = np.maximum(h - l, 1e-9)
    F["body_share"] = ("SHAPE", np.abs(c - o) / rng, "higher = decisive candle")
    F["close_pos"] = ("SHAPE", (c - l) / rng, "higher = closed on the high")
    F["upwick_share"] = ("SHAPE", -(h - np.maximum(o, c)) / rng, "higher = LESS rejection above")

    F["mins_into_window"] = ("CLOCK", (mod - WINDOW[0]).astype(float), "higher = later")
    return F


def signal_bars(P):
    """The bars the filters will actually act on: a Donchian 40 breakout inside 07:00-11:00."""
    brk = P["c"] > I.shift(I.rmax(P["h"], SPEC["entry_n"]), 1)
    inw = (P["mod"] >= WINDOW[0]) & (P["mod"] < WINDOW[1])
    return brk & inw & np.isfinite(P["atr"]) & np.isfinite(I.sma(P["c"], SPEC["ma_n"]))


def corr_matrix(F, mask):
    """Spearman correlation of every feature pair, computed ON THE SIGNAL BARS ONLY."""
    cols = {k: np.asarray(vv[1], float)[mask] for k, vv in F.items()}
    D = pd.DataFrame(cols).replace([np.inf, -np.inf], np.nan)
    return D.corr(method="spearman"), D


def pick_independent(C, fam, score, rho_max=0.35):
    """At most ONE per concept family, then a hard |rho| ceiling against everything already picked.

    Family first and correlation second, in that order, because the recorded failure mode is a set
    of picks that pass a |rho| ceiling and are all the same idea."""
    order = sorted(score, key=lambda k: -score[k])
    picked, used_fam, rejected = [], set(), []
    for k in order:
        if fam[k] in used_fam:
            rejected.append((k, f"family {fam[k]} already represented by "
                                f"{[p for p in picked if fam[p] == fam[k]][0]}"))
            continue
        bad = [(p, float(C.loc[k, p])) for p in picked if abs(C.loc[k, p]) > rho_max]
        if bad:
            rejected.append((k, f"|rho| {abs(bad[0][1]):.3f} against {bad[0][0]}"))
            continue
        picked.append(k)
        used_fam.add(fam[k])
    return picked, rejected
