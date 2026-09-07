"""Two new signal families, built to be tested by the machinery this repo already has.

  SAM -- SEMIVARIANCE ASYMMETRY. Baruník, Kocenda & Vacha (SSRN 2815151) split realized variance
  into the part contributed by up moves (RS+) and by down moves (RS-). Their signal is daily:
  when bad volatility dominated the last W days, go long. This is the intraday scalping version --
  the unit is a BAR rather than a day, and the position is a 1R barrier trade rather than an
  overnight hold. Two estimators:
      SAMi   intrabar: from the 1-minute returns inside each bar, faithful to the paper's use of
             30-minute returns inside a day. Needs lower-timeframe data in Pine.
      SAMb   bar-return: from the last W bar-to-bar returns on the chart itself. Coarser, and
             trivially computable live. Whether the extra resolution is worth anything is
             measured rather than assumed.

  EFF -- EFFICIENCY FLIP. Kaufman's efficiency ratio over N bars, |net change| / sum |changes|,
  is 1 for a straight line and near 0 for noise. The claim is that the transition from noisy to
  directional marks the start of a move worth joining, in the direction that is emerging.

DIRECTION IS NOT FREE on this sample (RESEARCH_PROTOCOL.md 4c): NQ rose 89%, so a long gets paid
for existing. Both sides of every signal are enumerated and each is scored against the base win
rate of ITS OWN side and geometry, computed from the population. The paper's direction is a prior,
not a permission.

Everything is causal: a bar's own close is used, never the next bar's, and fills are at the open
of the bar after the signal.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import indicators as I
from bos_choch import prep
from nqdata import load_bars, minute_of_day, session_index

_C = {}


# ---- SAM ----------------------------------------------------------------------------------------
def intrabar_semivar(tf, path="data/NQ_1m.csv"):
    """RS+ and RS- for every bar of timeframe `tf`, from the 1-minute returns inside it.

    The first 1-minute bar of a chart bar uses open->close, so a gap between chart bars never
    enters either semivariance -- the same guard the daily version uses for the overnight gap.
    """
    key = ("ib", tf, path)
    if key in _C:
        return _C[key]
    d = prep(tf)
    m1 = load_bars(path)
    t_min = m1.index.to_numpy()
    t_bar = d["df"].index.to_numpy()
    o1 = m1["open"].to_numpy(float); c1 = m1["close"].to_numpy(float)
    # which chart bar each 1-minute bar belongs to: the last bar STARTING at or before it
    owner = np.searchsorted(t_bar, t_min, side="right") - 1
    r = np.zeros(len(c1))
    first = np.r_[True, owner[1:] != owner[:-1]]
    r[first] = np.log(c1[first] / o1[first])
    r[~first] = np.log(c1[~first] / c1[:-1][~first[1:]] if False else 1.0)
    prev = np.r_[c1[0], c1[:-1]]
    r = np.where(first, np.log(c1 / np.maximum(o1, 1e-12)),
                 np.log(c1 / np.maximum(prev, 1e-12)))
    n = len(d["c"])
    rp = np.zeros(n); rn = np.zeros(n); cnt = np.zeros(n)
    ok = (owner >= 0) & (owner < n) & np.isfinite(r)
    np.add.at(rp, owner[ok & (r > 0)], r[ok & (r > 0)] ** 2)
    np.add.at(rn, owner[ok & (r < 0)], r[ok & (r < 0)] ** 2)
    np.add.at(cnt, owner[ok], 1.0)
    out = (rp, rn, cnt, d)
    _C[key] = out
    return out


def bar_semivar(d):
    """RS+ and RS- contributed by each bar's own close-to-close return."""
    c = d["c"]
    r = np.r_[0.0, np.diff(np.log(np.maximum(c, 1e-12)))]
    return np.where(r > 0, r * r, 0.0), np.where(r < 0, r * r, 0.0)


def sam(d, w, mode="bar", tf=None):
    """Rolling SAM over w bars: sum(RS+) - sum(RS-). Negative = bad volatility dominated."""
    if mode == "intrabar":
        rp, rn, cnt, _ = intrabar_semivar(tf)
    else:
        rp, rn = bar_semivar(d)
    return I.rsum(rp, w) - I.rsum(rn, w)


# ---- EFF ------------------------------------------------------------------------------------------
def efficiency(c, n):
    """Kaufman's efficiency ratio over n bars: |net| / sum|step|. 1 = straight line, 0 = noise."""
    a = np.abs(c - I.shift(c, n))
    step = np.abs(np.r_[0.0, np.diff(c)])
    return a / np.maximum(I.rsum(step, n), 1e-12)


def eff_flip(c, n, lo, hi, k=3):
    """Was the market noisy k bars ago and is it directional now? Plus the emerging direction."""
    er = efficiency(c, n)
    was_noisy = I.shift(er, k) < lo
    now_dir = er > hi
    up = c > I.shift(c, n)
    flip = was_noisy & now_dir
    return flip & up, flip & ~up, er


# ---- the condition sets the sweeps enumerate --------------------------------------------------------
def sam_masks(d, tf, mode="bar", windows=(2, 3, 5, 8, 13, 21, 34)):
    """Both the STATE the paper uses and the CROSS a scalper would trade.

    The paper's signal is a state -- hold long while the rolling SAM is negative -- rebalanced
    once a day. Held as a state under a 1R barrier it becomes "re-enter whenever flat and the
    regime still holds", which is a legitimate scalping reading. The cross is the other reading:
    trade the moment bad volatility takes over. Both are enumerated; research picks.
    """
    out = {}
    for w in windows:
        s = sam(d, w, mode=mode, tf=tf)
        prev = I.shift(s, 1)
        tag = mode[0]
        out[f"SAM{tag}{w} < 0"] = s < 0            # bad volatility dominated
        out[f"SAM{tag}{w} > 0"] = s > 0            # good volatility dominated
        out[f"SAM{tag}{w} crosses below 0"] = (s < 0) & (prev >= 0)
        out[f"SAM{tag}{w} crosses above 0"] = (s > 0) & (prev <= 0)
    return out


def eff_masks(d, lens=(10, 20, 30, 50), los=(0.2, 0.3, 0.4), his=(0.5, 0.6, 0.7), k=3):
    c = d["c"]
    out = {}
    for n in lens:
        for lo in los:
            for hi in his:
                if hi <= lo:
                    continue
                u, dn, _er = eff_flip(c, n, lo, hi, k)
                out[f"EFF{n} flip {lo:g}->{hi:g} up"] = u
                out[f"EFF{n} flip {lo:g}->{hi:g} down"] = dn
    return out


if __name__ == "__main__":
    for tf in (15, 30):
        d = prep(tf)
        rp, rn, cnt, _ = intrabar_semivar(tf)
        print(f"{tf}m: {len(d['c']):,} bars, median {np.median(cnt[cnt>0]):.0f} 1-minute "
              f"returns per bar")
        sb = sam(d, 8, "bar"); si = sam(d, 8, "intrabar", tf)
        ok = np.isfinite(sb) & np.isfinite(si)
        print(f"     SAM8 bar-return  < 0 on {100*np.nanmean(sb[ok]<0):.1f}% of bars")
        print(f"     SAM8 intrabar    < 0 on {100*np.nanmean(si[ok]<0):.1f}% of bars")
        print(f"     they agree on the sign {100*np.mean((sb[ok]<0)==(si[ok]<0)):.1f}% of the time,"
              f" rank correlation {np.corrcoef(np.argsort(np.argsort(sb[ok])), np.argsort(np.argsort(si[ok])))[0,1]:+.2f}")
        er = efficiency(d["c"], 20)
        print(f"     efficiency ratio(20): median {np.nanmedian(er):.2f}, "
              f"{100*np.nanmean(er<0.3):.0f}% below 0.3, {100*np.nanmean(er>0.6):.0f}% above 0.6")
        M = eff_masks(d)
        print(f"     {len(M)} efficiency-flip conditions, hit rate "
              f"{100*np.mean([v.mean() for v in M.values()]):.2f}% mean\n")
