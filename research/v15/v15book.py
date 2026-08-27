"""The combined book: two legs, two mechanics, one account.

THE HYPOTHESIS THIS TESTS. Every study on this branch that beat its own control did so with one of
two mechanics, and they point in OPPOSITE directions:

  LONG  -- a MARKET order into a Donchian breakout, inside a confirmed trend regime. V11 (NQ) and
           V13 (US100/US30/XAU) both beat a random entry this way. The edge is in the IMMEDIACY of
           a breakout continuing, which is exactly why a resting limit destroys it (STUDY_LIMIT_ENTRY).
  SHORT -- a RESTING LIMIT above the market, selling a rally back up. V14 found the market-order
           short at profit factor 0.77 and the identical rules with a limit at 1.44. The edge is
           short-horizon mean reversion, which is why the immediacy mechanic fails it.

So the book is not one strategy applied to both sides; it is two mechanics, each on the side that
measured well for it. That is a claim with a shape, and the shape is falsifiable: if the legs were
really the same edge, swapping their mechanics would not matter. It does.

WHAT THIS IS NOT. Neither leg is a one-bar scalp. 180 IC tests put the largest |IC| at 0.0305 and
showed a one-bar edge needs |IC| >= 0.10 to clear a 1.2-point round turn. Holds here are intraday
to a few hours. Anything sold as a 15-minute scalp on these indicators is arithmetically dead
before its rules are written.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0,"research"); sys.path.insert(0,"research/turtleshort")
sys.path.insert(0,"research/v8opt"); sys.path.insert(0,"research/v14")
import mirror, indicators as I, fastbars, eem  # noqa: E402

JUDGE = pd.Timestamp("2026-01-01")
_FRAC = None

def cost_frac():
    global _FRAC
    if _FRAC is None:
        b = fastbars.bars(15)
        _FRAC = 1.72/(2*float(np.nanmedian(mirror.wilder_atr(b["h"],b["l"],b["c"],20))))
    return _FRAC

def load(path):
    df = pd.read_csv(path, parse_dates=["ny"]).set_index("ny").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    ix = df.index
    d = dict(o=df["open"].to_numpy(float), h=df["high"].to_numpy(float),
             l=df["low"].to_numpy(float), c=df["close"].to_numpy(float),
             mod=(ix.hour*60+ix.minute).to_numpy(np.int64),
             sess=np.asarray(ix.normalize().values).astype("datetime64[ns]").astype(np.int64))
    return d, ix

def feats(d):
    h,l,c = d["h"],d["l"],d["c"]
    atr  = mirror.wilder_atr(h,l,c,20)
    atr5 = I.ema(I.true_range(h,l,c),5)
    adx,pdi,mdi = I.adx_di(h,l,c,14)
    tr = I.true_range(h,l,c)
    s14 = pd.Series(tr).rolling(14).sum().to_numpy()
    r14 = pd.Series(h).rolling(14).max().to_numpy()-pd.Series(l).rolling(14).min().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        chop = 100*np.log10(s14/np.maximum(r14,1e-9))/np.log10(14)
    net = np.abs(c-I.shift(c,20))
    tot = pd.Series(np.abs(np.r_[0,np.diff(c)])).rolling(20).sum().to_numpy()
    er = net/np.maximum(tot,1e-9)
    return dict(atr=atr, atr5=atr5, adx=adx, chop=chop, er=er,
                e13=I.ema(c,13), e34=I.ema(c,34), e48=I.ema(c,48),
                e12=I.ema(c,12), e100=I.ema(c,100))

def legs(d, F, block, win_short=(420,660)):
    """The two masks. Long = V13's regime. Short = V14's window rules."""
    b = lambda x: np.nan_to_num(np.asarray(x,float),nan=0).astype(bool)
    fin = np.isfinite(F["atr"]) & (F["atr"] > 0)
    regime = b(F["adx"]>=25) & b(F["er"]>=0.30) & b(F["chop"]<=55)
    up = b(F["e13"]>F["e48"]) & b(F["e12"]>F["e100"])
    lo,hi = win_short
    inwin = (d["mod"]>=lo) & (d["mod"]<hi)
    dn = b(F["e13"]<F["e34"]) & b(F["adx"]>=22)
    return dict(long=block&fin&regime&up, short=block&fin&inwin&dn)

LONG_GEO  = dict(side=1,  atr_mult=2.0, max_units=1, tp_r=None, skip_win=False)
SHORT_GEO = dict(side=-1, atr_mult=2.5, max_units=1, tp_r=2.0,  skip_win=False)

def run_leg(d, F, C, mask, which, cost, lim=True):
    """One leg. `lim` switches the ENTRY MECHANIC on BOTH sides -- it is the variable the
    falsification test moves, so it cannot be wired to one leg only."""
    kw = dict(LONG_GEO if which == "long" else SHORT_GEO)
    key = "long" if which == "long" else "short"
    if lim:
        kw.update(lim_mult=0.75, lim_atr=F["atr5"], lim_wait=8)
    return eem.run(d, F["atr"], C[key], mask, cost=cost, **kw)

def channels(d):
    return dict(long=mirror.channels(d["h"],d["l"],30,55,20,20),
                short=mirror.channels(d["h"],d["l"],30,55,25,25))

def daily(t, d):
    if len(t)==0: return pd.Series(dtype=float)
    return pd.Series(t.pnl.to_numpy()).groupby(np.asarray(d["sess"])[t.ent.to_numpy()]).sum()

def stats_of(series):
    if len(series)<8: return dict(n=0)
    eq = series.cumsum(); dd = float((eq.cummax()-eq).max())
    p = series.to_numpy()
    return dict(days=len(series), net=float(p.sum()), dd=dd,
                sharpe=float(p.mean()/p.std(ddof=1)*np.sqrt(252)) if p.std(ddof=1)>0 else np.nan,
                retdd=float(p.sum()/dd) if dd>0 else np.nan)
