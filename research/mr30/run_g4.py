"""TIMING WITH THE EXPOSURE HELD FIXED -- the one question US30 has never been asked cleanly.

Three primaries have now died in three runs, all the same way: the fade is negative before any
barrier with its own gradient inverted; its mirror beats drift on both sides on research and
inverts on both on the holdout; and the overnight premium is beaten by a RANDOM WINDOW OF THE SAME
LENGTH on all three blocks (p 0.405 / 0.782 / 0.383). That last null is the sharp instrument this
market needs, because US30 rose 144% and every long-biased rule here earns roughly what an
arbitrary entry with the same holding period earns.

So hold the exposure FIXED and ask only about the timing. Enter long at the next open, hold exactly
L bars, exit at an open. No stop, no target, no barrier tie-break, nothing to fit -- so the ONLY
thing a condition can change is WHEN, and cost is identical in both arms and cancels exactly.

THE NULL IS A CIRCULAR SHIFT OF THE CONDITION'S OWN MASK. A condition selects clustered bars (high
volatility comes in runs), so a control drawn as independent random bars has too narrow a spread
and passes everything -- the defect that made 17,121 of 27,786 tests "pass" in `research/edgelab`,
and the one `STUDY_V67` had to fix with block permutation. Shifting the mask circularly keeps its
run-length structure and its count EXACTLY and destroys only its alignment with price.

20 DECLARED CONDITIONS in seven families -- every family that has ever cleared anything on this
branch -- x 3 holding lengths = 60 cells, research block only, BH at q 0.10, survivors read ONCE
on the holdout and ONCE on the reserved ISO forward block.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mr30 import mr30core as M  # noqa: E402

LS = (16, 64, 256)            # 4 hours, 16 hours, ~2.7 trading days
RTH0, RTH1 = 570, 960
NDRAW = 1000


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def tod_baseline(f, col, min_obs=20):
    """Causal time-of-day mean: this minute-of-day's mean over PRIOR sessions only. Required on a
    24-hour tape -- `STUDY_VWAP_STOCH_ATR` measured an RTH bar clearing its own trailing ATR mean
    98.9% of the time, which makes every trailing-mean rung inert."""
    d = pd.DataFrame(dict(v=f[col].to_numpy(), mod=f["mod"].to_numpy()),
                     index=f.index)
    out = np.full(len(d), np.nan)
    for m, g in d.groupby("mod"):
        cs = g["v"].expanding().mean().shift(1)
        cnt = np.arange(len(g))
        vals = cs.to_numpy()
        vals[cnt < min_obs] = np.nan
        out[np.flatnonzero(d["mod"].to_numpy() == m)] = vals
    return out


def prior_session(f):
    """Prior COMPLETED RTH session high / low / close, frozen at the session end."""
    g = f.copy()
    g["day"] = g.index.normalize()
    inr = (g["mod"] >= RTH0) & (g["mod"] < RTH1)
    r = g[inr]
    agg = r.groupby("day").agg(hi=("high", "max"), lo=("low", "min"), cl=("close", "last"),
                               n=("close", "size"))
    agg = agg[agg.n >= 20].shift(1)
    m = g["day"].map(agg["hi"]).to_numpy(), g["day"].map(agg["lo"]).to_numpy(), \
        g["day"].map(agg["cl"]).to_numpy()
    return m


def conditions(f):
    c = f["close"].to_numpy(); at = f["atr"].to_numpy(); mod = f["mod"].to_numpy()
    v = f["volume"].to_numpy()
    s = pd.Series(at)
    pct250 = s.rolling(250).rank(pct=True).shift(1).to_numpy()
    ratio = (at / s.rolling(100).mean().to_numpy())
    ratio = np.r_[np.nan, ratio[:-1]]
    e200 = ema(c, 200)
    dma = (c - e200) / np.where(at > 0, at, np.nan)
    vb = tod_baseline(f, "volume")
    vr = v / np.where(vb > 0, vb, np.nan)
    hi, lo, pcl = prior_session(f)
    d16 = M.displacement(f, 16)
    dl = pd.Series(c).diff()
    up = dl.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-dl.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy()
    C = {
        "vol.pct250<=0.2": pct250 <= 0.2,
        "vol.pct250>=0.8": pct250 >= 0.8,
        "vol.atr/sma100>=1.2": ratio >= 1.2,
        "vol.atr/sma100<=0.8": ratio <= 0.8,
        "clk.0930-1100": (mod >= 570) & (mod < 660),
        "clk.1500-1600": (mod >= 900) & (mod < 960),
        "clk.overnight": (mod < RTH0) | (mod >= RTH1),
        "lvl.>prior sess high": c > hi,
        "lvl.<prior sess low": c < lo,
        "lvl.near prior close": np.abs(c - pcl) <= 0.5 * at,
        "ma.d200>=+1.5": dma >= 1.5,
        "ma.d200<=-1.5": dma <= -1.5,
        "ma.|d200|<=0.5": np.abs(dma) <= 0.5,
        "vlm.tod>=1.5": vr >= 1.5,
        "vlm.tod<=0.7": vr <= 0.7,
        "dsp.d16<=-1.5": d16 <= -1.5,
        "dsp.d16>=+1.5": d16 >= 1.5,
        "trn.close>EMA200": c > e200,
        "mom.rsi14<=30": rsi <= 30,
        "mom.rsi14>=70": rsi >= 70,
    }
    return {k: np.nan_to_num(x, nan=False).astype(bool) for k, x in C.items()}


def fwd(f, L):
    o = f["open"].to_numpy()
    nxt = np.r_[o[1:], np.nan]
    ex = np.r_[o[1 + L:], np.full(1 + L, np.nan)]
    with np.errstate(invalid="ignore"):
        return 100.0 * (ex - nxt) / nxt


def shift_null(mask, blockmask, r, n=NDRAW, seed=5):
    """Circularly shift the mask WITHIN the block: same count, same run structure, no alignment."""
    rng = np.random.default_rng(seed)
    idx = np.flatnonzero(blockmask & np.isfinite(r))
    if len(idx) < 200:
        return np.array([np.nan])
    m = mask[idx]
    x = r[idx]
    k = int(m.sum())
    if k < 30:
        return np.array([np.nan])
    out = np.empty(n)
    for i in range(n):
        out[i] = x[np.roll(m, int(rng.integers(1, len(m))))].mean()
    return out


def bh(ps, q=0.10):
    p = np.asarray(ps, float)
    o = np.argsort(p)
    n = len(p)
    keep = np.zeros(n, bool)
    thr = 0.0
    for r, i in enumerate(o, 1):
        if p[i] <= q * r / n:
            thr = p[i]
    keep[p <= thr] = thr > 0
    return keep


def main():
    f = M.load("US30L")
    blk = M.blocks(f)
    C = conditions(f)
    res = blk["A_research"]
    print(f"US30L research block, {int(res.sum())} bars. Long, enter next open, hold L bars, exit "
          f"at an open. Cost is identical in both arms and cancels.")
    print("Excess = condition mean minus the circularly-shifted null's median, in % of price.\n")
    rows = []
    for L in LS:
        r = fwd(f, L)
        base = float(np.nanmean(r[res & np.isfinite(r)]))
        print(f"  L={L:<4d} ({L * 15 / 60:.1f}h)   unconditional {base:+.4f}%")
        for nm, m in C.items():
            sel = m & res & np.isfinite(r)
            if sel.sum() < 200:
                continue
            mu = float(r[sel].mean())
            null = shift_null(m, res, r)
            if not np.isfinite(null).any():
                continue
            p = float(np.mean(null >= mu))
            rows.append(dict(L=L, cond=nm, n=int(sel.sum()), mu=mu,
                             null=float(np.median(null)), exc=mu - float(np.median(null)), p=p))
    d = pd.DataFrame(rows)
    d["pass"] = bh(d.p.to_numpy())
    d = d.sort_values("p")
    print(f"\n  {'cond':<24}{'L':>5}{'n':>8}{'mean %':>10}{'null %':>10}"
          f"{'excess':>10}{'p':>8}{'BH':>5}")
    for _, x in d.iterrows():
        print(f"  {x['cond']:<24}{int(x.L):>5}{int(x.n):>8}{x.mu:>10.4f}{x.null:>10.4f}"
              f"{x.exc:>10.4f}{x.p:>8.3f}{'  *' if x['pass'] else '':>5}")
    k = int(d.p.le(0.05).sum())
    print(f"\n  {k} of {len(d)} cells clear p<=0.05 against {0.05 * len(d):.1f} expected by "
          f"chance; {int(d['pass'].sum())} survive BH at q 0.10")
    d.to_csv("research/mr30/g4_research.csv", index=False)


if __name__ == "__main__":
    main()
