"""V63 -- a trend-following design on a VWAP, a triple EMA cross and ATR.

THE DESIGN, DECLARED BEFORE ANYTHING RAN.

  TRIGGER   a TRIPLE EMA CROSS: the bar on which EMA(f) > EMA(m) > EMA(s) becomes true having not
            been true on the previous bar. A cross is an EVENT; a stack is a STATE, and entering on
            every bar of a state is a different strategy. The two are joined by one axis -- `win`,
            how many bars after the fresh stack an entry is still allowed, with the stack still
            holding. win = 0 is the cross bar alone and win = 30 approximates the state.

  TREND     the VWAP, as a LEVEL. `STUDY_V40` and `STUDY_V51` both found a moving average is priced
            by its DISTANCE and is a FLOOR, not support, and that the "not extended" CEILING form
            inverts. Both forms are declared here so the same question is asked of the VWAP.
            Two anchors (the 09:30 New York session, and the 18:00 exchange roll) and -- the
            component test that matters -- two WEIGHTINGS: volume, and none. If the unweighted
            twin scores the same, the V in VWAP is doing nothing, and that is worth knowing before
            a script depends on a volume feed.

  ATR       the stop (a multiple of ATR14 at the SIGNAL bar, which is the only one knowable when
            the order is sent), an optional CHANDELIER TRAIL from the running high, an optional
            target, and an expansion gate.

  NOT SWEPT, on evidence already in hand: no session window and no hard flatten (destructive on
  eleven separate measurements here), one unit, market entry at the next open (the limit mechanic
  was corrected to null in `STUDY_V34`), long only (81% of bars on this sample are in a daily
  uptrend, so the short side is close to untestable).

SEARCHED ON US100's RESEARCH BLOCK ONLY -- 2016-11 to 2022-01, the era with the most history and
the one furthest from NQ's sample. Then frozen and read ONCE on US100's later blocks, on the WHOLE
of US30, and on the WHOLE of NQ. US30 and NQ choose nothing, which is what makes them a test.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit, prange

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63feeds as FD  # noqa: E402

TFS = (15, 30, 60)
FEEDSORDER = ("US100", "US30", "NQ")
EMAS = ((5, 13, 21), (8, 21, 55), (9, 21, 50), (13, 34, 89), (10, 30, 60))
WINS = (0, 3, 10, 30)
ANCHORS = ("session", "roll")            # 09:30 New York, and the 18:00 exchange roll
WEIGHTS = ("vol", "flat")                # flat is the unweighted twin: the "does the V matter" test
VWAP_READS = ("off", "above", "above and rising", "dist>=0.5", "0<dist<=2.0")
ATR_GATES = ("off", "atr>=mean", "atr>=1.1x mean")
STOPS = (1.5, 2.0, 2.5, 3.0)
TRAILS = (0.0, 2.5, 3.5)                 # 0 = a fixed stop only
TPS = (0.0, 2.0, 3.0, 4.0)
HOLD = 480
SLIP_TICKS = 1.0
TICK = {"NQ": 0.25, "US100": 0.1, "US30": 0.1}


# ------------------------------------------------------------------ indicators
def _anchor_key(ix, kind):
    ts = pd.DatetimeIndex(ix)
    mod = (ts.hour * 60 + ts.minute).to_numpy()
    day = (ts.year * 10000 + ts.month * 100 + ts.day).to_numpy()
    if kind == "session":
        # a new anchor at 09:30 New York; bars before it belong to the previous anchor
        k = np.where(mod >= 570, day, day - 1)
    else:
        k = np.where(mod >= 1080, day + 1, day)      # the 18:00 exchange roll
    return k


def _running(num, den, key):
    """Cumulative sums that reset whenever `key` changes. Causal by construction."""
    n = len(num)
    out = np.empty(n)
    a = b = 0.0
    prev = key[0] - 1
    for i in range(n):
        if key[i] != prev:
            a = b = 0.0
            prev = key[i]
        a += num[i]
        b += den[i]
        out[i] = a / b if b > 0 else np.nan
    return out


def build(market, tf):
    f = FD.bars(market, tf)
    o, h, l, c, v = (f[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    n = len(c)
    ix = f.index
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    atr_mean = pd.Series(atr).rolling(50).mean().to_numpy()
    tp = (h + l + c) / 3.0
    vw = {}
    for anc in ANCHORS:
        key = _anchor_key(ix, anc)
        vw[(anc, "vol")] = _running(tp * v, v, key)
        vw[(anc, "flat")] = _running(tp, np.ones(n), key)
    S = pd.Series(c)
    ema = {}
    for trio in EMAS:
        e = [S.ewm(span=x, adjust=False).mean().to_numpy() for x in trio]
        stack = (e[0] > e[1]) & (e[1] > e[2])
        fresh = stack & ~np.concatenate(([False], stack[:-1]))
        since = np.full(n, 10 ** 6, np.int64)
        last = -10 ** 6
        for i in range(n):
            if fresh[i]:
                last = i
            since[i] = i - last
        ema[trio] = dict(stack=stack, since=since, slow=e[2],
                         slow_up=np.concatenate(([False], np.diff(e[2]) > 0)))
    cost, pv = FD.COST[market]
    return dict(market=market, tf=tf, n=n, o=o, h=h, l=l, c=c, v=v, ix=ix, atr=atr,
                atr_mean=atr_mean, vw=vw, ema=ema, cost=cost, pv=pv,
                slip=SLIP_TICKS * TICK[market], blocks=FD.blocks(market, ix))


# ------------------------------------------------------------------ the exit tensor
@njit(cache=True, parallel=True)
def _tensor(o, h, l, c, atr, rows, g_stop, g_trail, g_tp, cost, slip, hold, m):
    N = len(rows)
    G = len(g_stop)
    xb = np.full((N, G), -1, np.int32)
    pts = np.full((N, G), np.nan, np.float32)
    for kk in prange(N):
        i = rows[kk]
        a = i + 1
        anc = atr[i]
        if a < 2 or a >= m - 2 or not np.isfinite(anc) or anc <= 0:
            continue
        px = o[a] + slip
        for gg in range(G):
            risk = g_stop[gg] * anc
            fixed = px - risk
            tgt = px + g_tp[gg] * anc if g_tp[gg] > 0.0 else 1e18
            end = a + hold
            if end > m - 2:
                end = m - 2
            run_hi = -1e18
            out = np.nan
            j = a
            while j <= end:
                lvl = fixed
                if g_trail[gg] > 0.0 and run_hi > -1e17:
                    t = run_hi - g_trail[gg] * anc
                    if t > lvl:
                        lvl = t
                cap = c[j - 1]
                if np.isfinite(cap) and lvl > cap:
                    lvl = cap
                if l[j] <= lvl:
                    out = (lvl if o[j] > lvl else o[j]) - slip
                    break
                if h[j] >= tgt:
                    out = (tgt if o[j] < tgt else o[j]) - slip
                    break
                if h[j] > run_hi:
                    run_hi = h[j]
                j += 1
            if not np.isfinite(out):
                j = end
                out = c[j] - slip
            xb[kk, gg] = j
            pts[kk, gg] = out - px - cost
    return xb, pts


@njit(cache=True, parallel=True)
def _sweep(offs, vals, sig_bar, xb, pts, epx, blk, nblk, G):
    S = len(offs) - 1
    stat = np.zeros((S, G, nblk, 5), np.float32)
    for s in prange(S):
        a0, a1 = offs[s], offs[s + 1]
        for g in range(G):
            free = -1
            for t in range(a0, a1):
                k = vals[t]
                if xb[k, g] < 0 or not np.isfinite(pts[k, g]) or sig_bar[k] <= free:
                    continue
                free = xb[k, g]
                b = blk[sig_bar[k]]
                if b < 0:
                    continue
                pc = 100.0 * pts[k, g] / epx[k]
                stat[s, g, b, 0] += 1.0
                stat[s, g, b, 1] += pc
                stat[s, g, b, 2] += pc * pc
                if pc > 0:
                    stat[s, g, b, 3] += pc
                    stat[s, g, b, 4] += 1.0
                else:
                    stat[s, g, b, 3] += 0.0
    return stat


@njit(cache=True, parallel=True)
def _sweep_loss(offs, vals, sig_bar, xb, pts, epx, blk, nblk, G):
    S = len(offs) - 1
    out = np.zeros((S, G, nblk), np.float32)
    for s in prange(S):
        a0, a1 = offs[s], offs[s + 1]
        for g in range(G):
            free = -1
            for t in range(a0, a1):
                k = vals[t]
                if xb[k, g] < 0 or not np.isfinite(pts[k, g]) or sig_bar[k] <= free:
                    continue
                free = xb[k, g]
                b = blk[sig_bar[k]]
                if b < 0:
                    continue
                pc = 100.0 * pts[k, g] / epx[k]
                if pc <= 0:
                    out[s, g, b] += -pc
    return out


# ------------------------------------------------------------------ assembling
def geometry():
    return pd.DataFrame([dict(stop=s, trail=t, tp=p)
                         for s in STOPS for t in TRAILS for p in TPS])


def vwap_mask(D, rows, anc, wt, read):
    if read == "off":
        return np.ones(len(rows), bool)
    w = D["vw"][(anc, wt)][rows]
    c, a = D["c"][rows], D["atr"][rows]
    d = (c - w) / np.maximum(a, 1e-9)
    ok = np.isfinite(w) & np.isfinite(a) & (a > 0)
    if read == "above":
        return ok & (c > w)
    if read == "above and rising":
        wp = D["vw"][(anc, wt)][np.maximum(rows - 1, 0)]
        return ok & (c > w) & np.isfinite(wp) & (w > wp)
    if read == "dist>=0.5":
        return ok & (d >= 0.5)
    return ok & (d > 0) & (d <= 2.0)


def signal_sets(D):
    n = D["n"]
    any_sig = np.zeros(n, bool)
    for trio in EMAS:
        e = D["ema"][trio]
        any_sig |= e["stack"] & (e["since"] <= max(WINS))
    any_sig[:300] = False
    any_sig[-(HOLD + 5):] = False
    any_sig &= np.isfinite(D["atr"]) & (D["atr"] > 0) & np.isfinite(D["atr_mean"])
    rows = np.flatnonzero(any_sig)
    trig = {}
    for trio in EMAS:
        e = D["ema"][trio]
        for w in WINS:
            trig[(trio, w)] = e["stack"][rows] & (e["since"][rows] <= w)
    vm = {("off", "-", "-"): np.ones(len(rows), bool)}
    for read in VWAP_READS:
        if read == "off":
            continue
        for anc in ANCHORS:
            for wt in WEIGHTS:
                vm[(read, anc, wt)] = vwap_mask(D, rows, anc, wt, read)
    am = {"off": np.ones(len(rows), bool),
          "atr>=mean": D["atr"][rows] >= D["atr_mean"][rows],
          "atr>=1.1x mean": D["atr"][rows] >= 1.1 * D["atr_mean"][rows]}
    offs, vals, keys = [0], [], []
    for trio in EMAS:
        for w in WINS:
            for vk, vmask in vm.items():
                for ak, amask in am.items():
                    idx = np.flatnonzero(trig[(trio, w)] & vmask & amask)
                    vals.append(idx)
                    offs.append(offs[-1] + len(idx))
                    keys.append(dict(ema=f"{trio[0]}/{trio[1]}/{trio[2]}", win=w, vwap=vk[0],
                                     anchor=vk[1], weight=vk[2], atrg=ak))
    return (rows, np.asarray(offs, np.int64), np.concatenate(vals).astype(np.int64),
            pd.DataFrame(keys))


def run_market(market, tf):
    D = build(market, tf)
    Gd = geometry()
    rows, offs, vals, K = signal_sets(D)
    names = list(D["blocks"].keys())
    blk = np.full(D["n"], -1, np.int64)
    for i, nm in enumerate(names):
        blk[np.asarray(D["blocks"][nm], bool)] = i
    xb, pts = _tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64),
                      Gd["stop"].to_numpy(float), Gd["trail"].to_numpy(float),
                      Gd["tp"].to_numpy(float), D["cost"], D["slip"], HOLD, D["n"])
    epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
    st = _sweep(offs, vals, rows.astype(np.int64), xb, pts, epx, blk, len(names), len(Gd))
    ls = _sweep_loss(offs, vals, rows.astype(np.int64), xb, pts, epx, blk, len(names), len(Gd))
    return dict(D=D, G=Gd, K=K, stat=st, loss=ls, rows=rows, xb=xb, pts=pts, epx=epx,
                offs=offs, vals=vals, names=names, blk=blk)


# block lengths in years, for the annualised trade Sharpe
YEARS = {("US100", "research"): 5.13, ("US100", "validation"): 2.00, ("US100", "test"): 1.75,
         ("US30", "research"): 5.19, ("US30", "validation"): 2.00, ("US30", "test"): 1.54,
         ("NQ", "research"): 1.92, ("NQ", "locked"): 1.04}


def table(res, market, tf):
    K, Gd, st, ls, names = res["K"], res["G"], res["stat"], res["loss"], res["names"]
    S, G, B, _ = st.shape
    ki = np.repeat(np.arange(S), G)
    gi = np.tile(np.arange(G), S)
    d = pd.DataFrame()
    for bi, nm in enumerate(names):
        f = st[:, :, bi, :].reshape(S * G, 5)
        lo = ls[:, :, bi].reshape(S * G)
        n = f[:, 0]
        m = np.where(n > 0, f[:, 1] / np.maximum(n, 1), np.nan)
        var = f[:, 2] / np.maximum(n, 1) - np.nan_to_num(m) ** 2
        d[f"n_{nm}"] = n
        d[f"pct_{nm}"] = m
        d[f"pf_{nm}"] = np.where(lo > 0, f[:, 3] / np.maximum(lo, 1e-9), np.nan)
        d[f"win_{nm}"] = np.where(n > 0, f[:, 4] / np.maximum(n, 1), np.nan)
        d[f"tot_{nm}"] = n * np.nan_to_num(m)
        yrs = YEARS.get((market, nm), 1.0)
        d[f"sh_{nm}"] = np.where(n > 2, np.nan_to_num(m) / np.sqrt(np.maximum(var, 1e-12))
                                 * np.sqrt(np.maximum(n, 1) / yrs), np.nan)
    for col in K.columns:
        d[col] = K[col].to_numpy()[ki]
    for col in ("stop", "trail", "tp"):
        d[col] = Gd[col].to_numpy()[gi]
    d["tf"] = tf
    d["market"] = market
    return d
