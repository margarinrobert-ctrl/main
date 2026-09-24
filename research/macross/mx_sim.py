"""The shipped MA_CROSS_SELECT Pine's order model, transliterated, run on real bars.

Not a test of the idea -- STUDY_V24 / V25 / V59 already measured MA crossovers here and found
nothing. It answers one question the linter cannot: does the script TRADE, reverse, stop and
flatten the way its source says, on a real feed ("a port that compiles and does nothing looks
exactly like a port that compiles and works", CLAUDE.md).

Order model, line for line with the script:
  * signals on the CLOSED bar; entries fill at the NEXT bar's open;
  * the bracket is fill-relative in ticks and is live on the fill bar itself;
  * a bar touching stop and target is resolved as the STOP (branch convention);
  * Side=Both with exits on the opposite cross REVERSES at the next open;
  * the flatten is written on the bar whose fill would land at or after flatMin.
LinReg is computed as 3*WMA - 2*SMA, which is the least-squares line's value at the current bar
exactly (ta.linreg(src, n, 0)). ATR is ema(tr, n), as the script uses.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "research", "us30s"))
sys.path.insert(0, os.path.join(ROOT, "research"))
import us30s  # noqa: E402

TICK = 0.1
COST = 2.29          # US30 round turn in points, the figure every US30 study here uses


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def sma(x, n):
    return pd.Series(x).rolling(n).mean().to_numpy()


def wma(x, n):
    w = np.arange(1, n + 1, dtype=float)
    return pd.Series(x).rolling(n).apply(lambda v: np.dot(v, w) / w.sum(), raw=True).to_numpy()


def ma(x, n, typ):
    if typ == "SMA":
        return sma(x, n)
    if typ == "EMA":
        return ema(x, n)
    if typ == "WMA":
        return wma(x, n)
    if typ == "LinReg":
        return 3.0 * wma(x, n) - 2.0 * sma(x, n)
    if typ == "DEMA":
        e1 = ema(x, n)
        return 2 * e1 - ema(e1, n)
    raise ValueError(typ)


def linreg_check(x, n=13):
    """3*WMA - 2*SMA against an explicit least-squares fit on the last n bars."""
    a = 3.0 * wma(x, n) - 2.0 * sma(x, n)
    t = np.arange(n, dtype=float)
    idx = np.arange(n + 5, n + 505)
    err = 0.0
    for i in idx:
        y = x[i - n + 1:i + 1]
        b1, b0 = np.polyfit(t, y, 1)
        err = max(err, abs((b0 + b1 * (n - 1)) - a[i]))
    return err


def run(d, fT="LinReg", fL=13, sT="EMA", sL=48, side="Both", xmode="cross",
        stop_atr=2.0, tgt_atr=None, atr_n=14, flat=None, win=None):
    o = d["open"].to_numpy(); h = d["high"].to_numpy(); l = d["low"].to_numpy()
    c = d["close"].to_numpy()
    ny = d["ny"]
    nymin = (ny.dt.hour * 60 + ny.dt.minute + ny.dt.second / 60.0).to_numpy()
    tf = float(np.median(np.diff(ny.values).astype("timedelta64[s]").astype(float)) / 60.0)
    f = ma(c, fL, fT); s = ma(c, sL, sT)
    up = (f > s) & (np.roll(f, 1) <= np.roll(s, 1)); up[0] = False
    dn = (f < s) & (np.roll(f, 1) >= np.roll(s, 1)); dn[0] = False
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    atr = ema(tr, atr_n)
    can_l = side in ("Long", "Both"); can_s = side in ("Short", "Both")
    pos = 0; ent = 0.0; stp = tgt = np.nan
    pend = None       # action to execute at the next bar's open
    trades = []
    n = len(c)
    for i in range(n):
        # 1. pending order fills at this bar's open
        if pend is not None:
            act, sd, sdist, tdist = pend
            if pos != 0 and act in ("close", "rev"):
                trades.append(pos * (o[i] - ent) - COST); pos = 0
            if act in ("open", "rev"):
                pos = sd; ent = o[i]
                stp = ent - sd * sdist if sdist == sdist else np.nan
                tgt = ent + sd * tdist if tdist == tdist else np.nan
            pend = None
        # 2. bracket inside the bar (live on the fill bar too); stop first on a tie
        if pos != 0:
            hit_s = (pos > 0 and l[i] <= stp) or (pos < 0 and h[i] >= stp)
            hit_t = (pos > 0 and h[i] >= tgt) or (pos < 0 and l[i] <= tgt)
            if hit_s:
                px = min(stp, o[i]) if pos > 0 else max(stp, o[i])
                trades.append(pos * (px - ent) - COST); pos = 0
            elif hit_t:
                trades.append(pos * (tgt - ent) - COST); pos = 0
        # 3. decisions on the closed bar
        if not (np.isfinite(f[i]) and np.isfinite(s[i]) and np.isfinite(atr[i])):
            continue
        fill = nymin[i] + tf
        past = flat is not None and fill >= flat
        inwin = win is None or (win[0] <= fill < win[1])
        sdist = stop_atr * atr[i] if stop_atr else np.nan
        tdist = tgt_atr * atr[i] if tgt_atr else np.nan
        if past:
            if pos != 0:
                pend = ("close", 0, np.nan, np.nan)
            continue
        if xmode == "cross":
            if pos > 0 and dn[i] and not (can_s and inwin):
                pend = ("close", 0, np.nan, np.nan)
            if pos < 0 and up[i] and not (can_l and inwin):
                pend = ("close", 0, np.nan, np.nan)
        rev_ok = pos == 0 or xmode == "cross"
        if up[i] and can_l and inwin and pos <= 0 and rev_ok:
            pend = ("rev" if pos < 0 else "open", 1, sdist, tdist)
        elif dn[i] and can_s and inwin and pos >= 0 and rev_ok:
            pend = ("rev" if pos > 0 else "open", -1, sdist, tdist)
    return np.asarray(trades)


def summ(r):
    if len(r) == 0:
        return "n 0"
    w = r > 0
    pf = r[w].sum() / -r[~w].sum() if (~w).any() else np.nan
    return f"n {len(r):5d}  {r.mean():+7.2f} pts/trade  win {w.mean():.3f}  PF {pf:.3f}"


if __name__ == "__main__":
    d0 = us30s.load(tf=0.5)
    print(f"linreg == 3*WMA - 2*SMA, max |error| {linreg_check(d0['close'].to_numpy()):.2e}")
    for tf in (5, 15):
        d = us30s.load(tf=tf)
        print(f"\nUS30_30s resampled to {tf}m, {d['ny'].min().date()}..{d['ny'].max().date()}, "
              f"{len(d)} bars -- a MECHANICS check, not a test")
        cfgs = [
            ("defaults: LinReg13 x EMA48, both, opp cross, 2N stop", {}),
            ("long only", dict(side="Long")),
            ("stop/target only, 3N target", dict(xmode="bracket", tgt_atr=3.0)),
            ("window 09:30-16:00 + flat 16:00", dict(win=(570, 960), flat=960)),
            ("EMA13 x EMA48 (same slow, EMA fast)", dict(fT="EMA")),
            ("LinReg13 x LinReg48", dict(sT="LinReg")),
        ]
        for lab, kw in cfgs:
            print(f"  {lab:<44s} {summ(run(d, **kw))}")
