"""Feature engineering, regime detection and IC for the MA-cross + Donchian programme.

WHAT IS FIXED BY THE BRIEF: Donchian entry 30 / exit 20; MA crosses 13/48 and 12/100; ADX as the
chop/distribution filter; BOTH SIDES. Nothing here searches those.

FOUR MARKETS, AND THE SPLIT MATTERS MORE THAN THE FEATURES.
  US100_LONG  206,703 bars, 2016-11 -> 2025-10, NY+7 corrected. The RESEARCH market. Nine years.
  US100_ISO    46,700 bars, 2024-08 -> 2026-08. A DIFFERENT PROVIDER (median level gap 11.1 pts,
               return correlation 0.9399 at the -7h alignment). Its 2026 tail post-dates the long
               file entirely, which makes it a genuine forward block.
  US30_ISO     48,937 bars. A second instrument.
  XAU          494,235 bars, 2004 -> 2026. A different asset class and four extra market cycles.

EVERY FEATURE IS CAUSAL AND SCALE-FREE. A moving-average distance in points cannot be compared
across nine years of a index that tripled, let alone across gold; every distance here is divided by
ATR, and every rank is a TRAILING percentile, never a whole-sample one.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0,"research"); sys.path.insert(0,"research/turtleshort")
sys.path.insert(0,"research/turtle15"); sys.path.insert(0,"research/v8opt")
import mirror, indicators as I, fastbars  # noqa: E402

DON_E, DON_X = 30, 20
MA_PAIRS = [(13, 48), (12, 100)]

def _ema(x, n): return I.ema(np.asarray(x, float), n)

def _trail_pct(x, win=2000):
    """Trailing percentile rank. A whole-sample rank leaks the future into every early bar."""
    s = pd.Series(x)
    return s.rolling(win, min_periods=200).rank(pct=True).to_numpy()

def _slope(x, n):
    x = np.asarray(x, float)
    return (x - I.shift(x, n)) / n

def load(path, tf=15):
    df = pd.read_csv(path, parse_dates=["ny"]).set_index("ny").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df = df.rename(columns={"open":"o","high":"h","low":"l","close":"c","volume":"v"})
    ix = df.index
    d = dict(o=df["o"].to_numpy(float), h=df["h"].to_numpy(float), l=df["l"].to_numpy(float),
             c=df["c"].to_numpy(float), v=df["v"].to_numpy(float),
             mod=(ix.hour*60+ix.minute).to_numpy(np.int64),
             sess=np.asarray(ix.normalize().values).astype("datetime64[ns]").astype(np.int64),
             ts=ix.values.astype("datetime64[ns]").astype(np.int64), n=len(df))
    return d, ix


def build(d):
    """Every feature the brief asks for, plus the regime layer. All causal."""
    o,h,l,c = d["o"],d["h"],d["l"],d["c"]
    atr  = mirror.wilder_atr(h,l,c,20)
    A    = np.maximum(atr, 1e-9)
    F = {}
    # ---- MA CROSSES, the two pairs named in the brief -------------------------------------
    for s_,l_ in MA_PAIRS:
        ms, ml = _ema(c,s_), _ema(c,l_)
        tag = f"ma{s_}_{l_}"
        F[f"{tag}_state"]  = np.where(ms > ml, 1.0, -1.0)          # +1 short MA above long MA
        F[f"{tag}_gap"]    = (ms - ml) / A                          # separation in ATR, scale-free
        F[f"{tag}_gap_pct"]= _trail_pct((ms-ml)/A)
        F[f"{tag}_slope_s"]= _slope(ms,5)/A
        F[f"{tag}_slope_l"]= _slope(ml,20)/A
        F[f"{tag}_px_vs_s"]= (c - ms)/A
        F[f"{tag}_px_vs_l"]= (c - ml)/A
        st = F[f"{tag}_state"]
        F[f"{tag}_cross"]  = np.r_[0.0, np.diff(st)]/2.0            # +1 golden, -1 death, on the bar
        # bars since the last cross: a cross is information that DECAYS
        bs = np.zeros(len(c)); k = 0
        for i in range(len(c)):
            k = 0 if F[f"{tag}_cross"][i] != 0 else k+1
            bs[i] = k
        F[f"{tag}_bars_since"] = bs
        F[f"{tag}_fresh"] = (bs <= 8).astype(float)
    # ---- ADX / DI, the brief's chop filter -------------------------------------------------
    adx, pdi, mdi = I.adx_di(h,l,c,14)
    F["adx"]=adx; F["di_spread"]=pdi-mdi; F["di_ratio"]=pdi/np.maximum(pdi+mdi,1e-9)
    F["adx_slope"]=_slope(adx,5); F["adx_pct"]=_trail_pct(adx)
    # ---- CHOP INDEX: the brief says "chopping or distributing" -----------------------------
    tr = I.true_range(h,l,c)
    for n in (14,28):
        s_tr = pd.Series(tr).rolling(n).sum().to_numpy()
        rng  = pd.Series(h).rolling(n).max().to_numpy() - pd.Series(l).rolling(n).min().to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            F[f"chop{n}"] = 100*np.log10(s_tr/np.maximum(rng,1e-9))/np.log10(n)
    # ---- volatility / structure ------------------------------------------------------------
    atr_l = pd.Series(atr).rolling(200, min_periods=50).mean().to_numpy()
    F["atr_ratio"]=atr/np.maximum(atr_l,1e-9); F["atr_pct"]=_trail_pct(atr)
    F["ef_ratio"]=np.abs(c-I.shift(c,20))/np.maximum(pd.Series(np.abs(np.r_[0,np.diff(c)])).rolling(20).sum().to_numpy(),1e-9)
    hi30 = I.shift(I.rmax(h,DON_E),1); lo30 = I.shift(I.rmin(l,DON_E),1)
    F["don_pos"] = (c-lo30)/np.maximum(hi30-lo30,1e-9)             # where in the channel we sit
    F["don_width"]=(hi30-lo30)/A
    F["close_pos"]=(c-l)/np.maximum(h-l,1e-9)
    F["ret20_atr"]=(c-I.shift(c,20))/np.maximum(20*A,1e-9)
    # ---- REGIME LABEL: the layer the brief calls "chopping or distributing" ----------------
    # Trend = ADX above its floor AND the efficiency ratio high AND CHOP low. Three independent
    # readings of the same idea; requiring all three is what makes it a REGIME and not a filter.
    F["regime_trend"] = ((np.nan_to_num(adx,nan=0) >= 25) &
                         (np.nan_to_num(F["ef_ratio"],nan=0) >= 0.30) &
                         (np.nan_to_num(F["chop14"],nan=100) <= 55)).astype(float)
    F["regime_chop"]  = ((np.nan_to_num(adx,nan=100) < 20) |
                         (np.nan_to_num(F["chop14"],nan=0) >= 61.8)).astype(float)
    return atr, F


def channels(d):
    return mirror.channels(d["h"], d["l"], DON_E, 55, DON_X, DON_X)


_NQ_FRAC = None
def cost_for(atr):
    """A cost is a FRACTION of risk. Charge every market the fraction MNQ pays on its own 2N."""
    global _NQ_FRAC
    if _NQ_FRAC is None:
        b = fastbars.bars(15)
        _NQ_FRAC = 1.72 / (2*float(np.nanmedian(mirror.wilder_atr(b["h"],b["l"],b["c"],20))))
    return _NQ_FRAC * 2 * float(np.nanmedian(atr))


def split65(d):
    sess = np.asarray(d["sess"]); us = np.unique(sess); cut = us[int(0.65*len(us))]
    return sess < cut, sess >= cut


def sharpe(t, d):
    if len(t) < 8: return np.nan
    g = pd.Series(t.pnl.to_numpy()).groupby(np.asarray(d["sess"])[t.ent.to_numpy()]).sum()
    if len(g) < 8 or g.std(ddof=1) == 0: return np.nan
    return float(g.mean()/g.std(ddof=1)*np.sqrt(252))
