"""ADVERSARIAL AUDIT of PREWIN_ADX26 (Donchian-20 breakout, NAS 15m, 07:00-11:00 NY,
gated on Wilder ADX(14) read at the last pre-07:00 bar of the session > 26).

Everything below is written from the RULE TEXT. No helper from agent_trend.py is
imported. Only `data` (the canonical bars) and `lab.sig_gate` (the sanctioned
matched-control scorer) are borrowed, plus lab's engine for a cross-check against
my own bar-by-bar simulator.

RESEARCH BLOCK ONLY. lab.reveal() is never called.
"""
import numpy as np, pandas as pd, sys
import data as D
import lab

np.set_printoptions(suppress=True)
SYM = "NAS"
COST, SLIP = 2.0, 0.25
WIN = (420, 660)


# ============================================================ my own indicators
def my_wilder(x, n):
    a = 1.0 / n
    out = np.empty(len(x), float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def my_ema(x, n):
    a = 2.0 / (n + 1.0)
    out = np.empty(len(x), float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def my_tr(h, l, c):
    pc = np.empty(len(c)); pc[0] = c[0]; pc[1:] = c[:-1]
    return np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))


def my_adx(df, n=14):
    """Wilder ADX. Written from the definition, not copied."""
    h, l, c = df.high.values, df.low.values, df.close.values
    uh = np.zeros(len(h)); uh[1:] = h[1:] - h[:-1]
    dl = np.zeros(len(l)); dl[1:] = l[:-1] - l[1:]
    pdm = np.where((uh > dl) & (uh > 0), uh, 0.0)
    ndm = np.where((dl > uh) & (dl > 0), dl, 0.0)
    atr_ = my_wilder(my_tr(h, l, c), n)
    den = np.where(atr_ > 0, atr_, np.nan)
    pdi = 100.0 * my_wilder(pdm, n) / den
    ndi = 100.0 * my_wilder(ndm, n) / den
    s = pdi + ndi
    dx = 100.0 * np.abs(pdi - ndi) / np.where(s > 0, s, np.nan)
    dx = np.where(np.isnan(dx), 0.0, dx)
    return my_wilder(dx, n), pdi, ndi


def my_atr(df, n=14):
    return my_ema(my_tr(df.high.values, df.low.values, df.close.values), n)


def my_donchian(df, n):
    """Upper/lower over the n bars ENDING AT THE PREVIOUS BAR (current excluded)."""
    h, l = df.high.values, df.low.values
    N = len(h)
    up = np.full(N, np.nan); lo = np.full(N, np.nan)
    hs = pd.Series(h); ls = pd.Series(l)
    up[n:] = hs.rolling(n).max().values[n - 1:-1]
    lo[n:] = ls.rolling(n).min().values[n - 1:-1]
    return up, lo


def my_prewin(df, feat, cut=420):
    """feat at the LAST bar of the session whose tod < cut, broadcast to the
    whole session. NaN for sessions with no pre-cut bar."""
    tod, sess = df.tod.values, df.sess.values
    pre = np.flatnonzero(tod < cut)
    if len(pre) == 0:
        return np.full(len(df), np.nan)
    s = sess[pre]
    islast = np.empty(len(pre), bool); islast[-1] = True
    islast[:-1] = s[1:] != s[:-1]
    last = pre[islast]
    val = np.full(sess.max() + 2, np.nan)
    val[sess[last]] = feat[last]
    return val[sess]


# ============================================================ my own signals/sim
def my_signals(df, n_entry=20, win=WIN, atr_n=14):
    up, lo = my_donchian(df, n_entry)
    a = my_atr(df, atr_n)
    c, tod = df.close.values, df.tod.values
    inwin = (tod >= win[0]) & (tod < win[1])
    ok = inwin & np.isfinite(up) & np.isfinite(a) & (a > 0)
    L = (c > up) & ok
    S = (c < lo) & ok
    idx = np.flatnonzero(L | S)
    side = np.where(L[idx], 1, -1).astype(np.int64)
    return idx, side, a


def first_per_session(df, idx, side):
    s = df.sess.values[idx]
    keep = np.empty(len(idx), bool); keep[0] = True
    keep[1:] = s[1:] != s[:-1]
    return idx[keep], side[keep]


def my_sim(df, idx, side, a, stop_mult=1.5, targ_mult=2.0, max_hold=16,
           flat_tod=660, cost=COST, slip=SLIP):
    """Bar-by-bar python loop. Deliberately slow and obvious.
    Priority at the deciding bar: forced flatten > stop > target (ambiguous bar
    booked as the loss). Gap through the stop fills at the bar open when worse."""
    o, h, l, c = (df.open.values, df.high.values, df.low.values, df.close.values)
    tod, sess = df.tod.values, df.sess.values
    N = len(df)
    rows = []
    for k in range(len(idx)):
        i = idx[k]
        if i + 1 >= N:
            continue
        sd = float(side[k])
        entry = o[i + 1] + sd * slip
        av = a[i]
        stop = entry - sd * stop_mult * av
        targ = entry + sd * targ_mult * av
        s0 = sess[i + 1]
        ex = None; rsn = None; nb = 0
        for step in range(max_hold):
            j = i + 1 + step
            if j >= N:
                break
            nb = step + 1
            if sess[j] != s0 or tod[j] >= flat_tod:
                ex, rsn = o[j], "flatten"; break
            hs = (l[j] <= stop) if sd > 0 else (h[j] >= stop)
            ht = (h[j] >= targ) if sd > 0 else (l[j] <= targ)
            if hs:
                px = min(o[j], stop) if sd > 0 else max(o[j], stop)
                ex, rsn = px, "stop"; break
            if ht:
                ex, rsn = targ, "target"; break
            if step == max_hold - 1:
                ex, rsn = c[j], "time"; break
        if ex is None:
            continue
        rows.append((i, int(sd), entry, ex, sd * (ex - entry) - cost, nb, rsn,
                     sess[i], tod[i]))
    return pd.DataFrame(rows, columns=["sig_bar", "side", "entry", "exit", "net",
                                       "bars", "reason", "sess", "tod"])


def hr(t=""):
    print("\n" + "=" * 100)
    if t: print(t); print("=" * 100)


df, walk, RMASK = lab.research(SYM)
SPLIT = D.split_point(df)
print(f"NAS 15m: {len(df):,} bars, sessions 0..{df.sess.max()}, "
      f"research = sessions < {SPLIT} ({df.ts[RMASK].min().date()} -> {df.ts[RMASK].max().date()})")
