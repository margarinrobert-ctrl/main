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
  * the flatten is written on the bar whose fill would land at or after flatMin;
  * the 09:00 range (bars whose open is in [orb_start, orb_end) NY) is complete from the close of
    the first bar ending at or after orb_end; "close" mode needs the cross bar to close beyond it,
    "either" mode fires on whichever of cross / close-beyond comes second within orb_win minutes;
  * the breakeven arms at a bar CLOSE when that bar's favourable extreme reached be_pts from the
    fill (the fill bar included) and binds from the next bar, a stop filling at the WORSE of its
    level and the bar's open -- so a stop written through the market fills at the open.
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


def orb_arrays(d, nymin, tf, start=540, end=545):
    """Per bar: the day's 09:00 range high/low once complete, else NaN."""
    day = d["ny"].dt.strftime("%Y%m%d").astype(int).to_numpy()
    h = d["high"].to_numpy(); l = d["low"].to_numpy()
    hi = np.full(len(h), np.nan); lo = np.full(len(h), np.nan)
    ch = cl = np.nan; last = -1
    for i in range(len(h)):
        if day[i] != last:
            last = day[i]; ch = cl = np.nan
        if start <= nymin[i] < end:
            ch = h[i] if ch != ch else max(ch, h[i])
            cl = l[i] if cl != cl else min(cl, l[i])
        if ch == ch and nymin[i] + tf >= end:
            hi[i] = ch; lo[i] = cl
    return hi, lo, day


def run(d, fT="LinReg", fL=13, sT="EMA", sL=48, side="Both", xmode="cross",
        stop_atr=2.0, tgt_atr=None, atr_n=14, flat=None, win=None,
        orb=None, orb_start=540, orb_end=545, orb_win=30.0, orb_once=False,
        be_pts=None, be_off=5.0, cross_mode="bar", fresh_min=15.0, rev=True, stats=None):
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
    ohi, olo, day = orb_arrays(d, nymin, tf, orb_start, orb_end)
    tms = (ny.values.astype("datetime64[s]").astype(np.int64) + tf * 60.0)  # bar close, seconds
    bu = np.nan_to_num(c > ohi) .astype(bool) & np.isfinite(ohi)
    bd = np.nan_to_num(c < olo).astype(bool) & np.isfinite(olo)
    # last crossover time per side, forward-filled and including the current bar
    tup = pd.Series(np.where(up, tms, np.nan)).ffill().to_numpy()
    tdn = pd.Series(np.where(dn, tms, np.nan)).ffill().to_numpy()
    if cross_mode == "fresh":
        with np.errstate(invalid="ignore"):
            bl = (f > s) & (tms - tup <= fresh_min * 60.0)
            bs = (f < s) & (tms - tdn <= fresh_min * 60.0)
    else:
        bl, bs = up.copy(), dn.copy()
    if orb is None:
        sl_, ss_ = bl.copy(), bs.copy()
    else:
        sl_ = np.zeros(len(c), bool); ss_ = np.zeros(len(c), bool)
        lxu = lxd = lbu = lbd = np.nan; lastd = -1
        for i in range(len(c)):
            if day[i] != lastd:
                lastd = day[i]; lxu = lxd = lbu = lbd = np.nan
            if orb == "close":
                sl_[i] = bl[i] and bu[i]; ss_[i] = bs[i] and bd[i]
            else:
                w = orb_win * 60.0
                fu = bu[i] and not (i > 0 and bu[i - 1]); fd = bd[i] and not (i > 0 and bd[i - 1])
                sl_[i] = (up[i] and (bu[i] or (lbu == lbu and tms[i] - lbu <= w))) or \
                         (fu and f[i] > s[i] and lxu == lxu and tms[i] - lxu <= w) or \
                         (bl[i] and bu[i])
                ss_[i] = (dn[i] and (bd[i] or (lbd == lbd and tms[i] - lbd <= w))) or \
                         (fd and f[i] < s[i] and lxd == lxd and tms[i] - lxd <= w) or \
                         (bs[i] and bd[i])
            if up[i]: lxu = tms[i]
            if dn[i]: lxd = tms[i]
            if bu[i]: lbu = tms[i]
            if bd[i]: lbd = tms[i]
    if stats is not None:
        stats.update(cross_up=int(up.sum()), cross_dn=int(dn.sum()),
                     sig_l=int(sl_.sum()), sig_s=int(ss_.sum()),
                     ready_bars=int(np.isfinite(ohi).sum()),
                     days_with_range=int(len(np.unique(day[np.isfinite(ohi)]))),
                     days=int(len(np.unique(day))),
                     up_beyond_on_cross=float(bu[up & np.isfinite(ohi)].mean()) if (up & np.isfinite(ohi)).any() else np.nan,
                     up_beyond_all=float(bu[np.isfinite(ohi)].mean()) if np.isfinite(ohi).any() else np.nan,
                     dn_beyond_on_cross=float(bd[dn & np.isfinite(olo)].mean()) if (dn & np.isfinite(olo)).any() else np.nan,
                     dn_beyond_all=float(bd[np.isfinite(olo)].mean()) if np.isfinite(olo).any() else np.nan)
    took_l = took_s = False; lastday = -1
    armed = False; be_n = 0
    used_u = used_d = np.nan
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
                pos = sd; ent = o[i]; armed = False
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
        if day[i] != lastday:
            lastday = day[i]; took_l = took_s = False
        if be_pts is not None and pos != 0 and not armed:
            fav = h[i] - ent if pos > 0 else ent - l[i]
            if fav >= be_pts:
                armed = True; be_n += 1
                stp = ent + pos * be_off
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
        once = orb_once and orb is not None
        fresh_u = not (tup[i] == used_u); fresh_d = not (tdn[i] == used_d)   # one trade per cross
        want_l = sl_[i] and fresh_u and can_l and inwin and not (once and took_l)
        want_s = ss_[i] and fresh_d and can_s and inwin and not (once and took_s)
        if xmode == "cross":
            if pos > 0 and dn[i] and not (want_s and rev):
                pend = ("close", 0, np.nan, np.nan)
            if pos < 0 and up[i] and not (want_l and rev):
                pend = ("close", 0, np.nan, np.nan)
        rev_ok = pos == 0 or (xmode == "cross" and rev)
        if want_l and pos <= 0 and rev_ok:
            pend = ("rev" if pos < 0 else "open", 1, sdist, tdist); took_l = True; used_u = tup[i]
        elif want_s and pos >= 0 and rev_ok:
            pend = ("rev" if pos > 0 else "open", -1, sdist, tdist); took_s = True; used_d = tdn[i]
    if stats is not None:
        stats["be_armed"] = be_n
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
        st = {}
        run(d, orb="close", stats=st)
        print(f"  sessions {st['days']}, with a complete 09:00 range {st['days_with_range']}")
        print(f"  base rate, close beyond range: up cross {st['up_beyond_on_cross']:.3f} vs all "
              f"post-range bars {st['up_beyond_all']:.3f} (lift "
              f"{st['up_beyond_on_cross']/st['up_beyond_all']:.2f}); down cross "
              f"{st['dn_beyond_on_cross']:.3f} vs {st['dn_beyond_all']:.3f} (lift "
              f"{st['dn_beyond_on_cross']/st['dn_beyond_all']:.2f})")
        cfgs = [
            ("defaults: LinReg13 x EMA48, both, opp cross, 2N stop", {}),
            ("EMA13 x LinReg48", dict(fT="EMA", sT="LinReg")),
            ("+ range: cross closes beyond", dict(orb="close")),
            ("+ range: either order, 30 min", dict(orb="either")),
            ("+ range close, one per side per day", dict(orb="close", orb_once=True)),
            ("+ range close, window 09:05-12:00, flat 16:00", dict(orb="close", win=(545, 720), flat=960)),
            ("+ breakeven 50 / secure 5", dict(be_pts=50, be_off=5)),
            ("+ range close + breakeven 50/5", dict(orb="close", be_pts=50, be_off=5)),
            ("opp-cross exit, NO reverse", dict(rev=False)),
            ("fresh cross <= 15 min (no range)", dict(cross_mode="fresh", fresh_min=15)),
            ("fresh cross <= 15 min, no reverse", dict(cross_mode="fresh", fresh_min=15, rev=False)),
            ("fresh <= 30 min + range close", dict(cross_mode="fresh", fresh_min=30, orb="close")),
            ("fresh <= 30 min + range close, 1/side/day", dict(cross_mode="fresh", fresh_min=30, orb="close", orb_once=True)),
        ]
        for lab, kw in cfgs:
            st = {}
            r = run(d, stats=st, **kw)
            print(f"  {lab:<46s} {summ(r)}  signals L/S {st['sig_l']}/{st['sig_s']}"
                  f"  BE armed {st['be_armed']}")
