"""S3 flow exhaustion at TEN MINUTES on MNQ -- the shared machinery for the battery.

Everything the study needs in one place so the five run scripts cannot drift apart: the 10-minute
build, a cell runner, the two nulls, the four Monte Carlos and the daily-P&L series the correlation
matrices are computed on.

THE ONE THING THAT CHANGES WHEN THE BAR SIZE CHANGES. `k` and `w` are BAR COUNTS. Carried
unchanged from 5m to 10m they DOUBLE their reach in minutes -- k3 goes from a 15-minute pivot to a
30-minute one and w20 from a 100-minute window to 200. `STUDY_V57_REVERSE_ENGINEER` recorded that
exact failure in the other direction. So both readings are tested and named: CARRY (the same
numbers) and MATCHED (the same minutes).
"""
import sys, os
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5")
import numpy as np, pandas as pd
import s5data as S, s5sig as SG, s5walk as W

TF = 10
CARRY = dict(k=3, w=20)          # the 5-minute numbers, unchanged -> 30 and 200 minutes
MATCHED = dict(k=2, w=10)        # the same MINUTES as the 5m rule (30/100 -> 20/100)
GEOM = dict(stop=3.0, tgt=0.0, be=1.0, be_off=0.25, arm=1.0, tr=1.0)


def build(tf=TF):
    base = S.load_1m()
    D = S.assemble(S.resample(base, tf), tf)
    F = SG.build(D, base)
    D["days"] = {0: D["all_days"][D["all_days"] < D["cut_day"]],
                 1: D["all_days"][D["all_days"] >= D["cut_day"]]}
    return D, F, base


def run(D, sig_l, sig_s, g=GEOM, rt=None, slip=None, o=None, h=None, l=None, c=None, atr=None):
    """One walk. Overridable price arrays so the jitter Monte Carlo can reuse it untouched."""
    rt = S.RT_POINTS if rt is None else rt
    slip = S.SLIP_POINTS if slip is None else slip
    o = D["o"] if o is None else o
    h = D["h"] if h is None else h
    l = D["l"] if l is None else l
    c = D["c"] if c is None else c
    atr = D["atr"] if atr is None else atr
    sig = sig_l | sig_s
    side = np.where(sig_l, 1, -1).astype(np.int64)
    n = int(sig.sum())
    z = lambda t: np.zeros(max(n, 1), t)
    oi, ox, oR, op, ow = z(np.int64), z(np.int64), z(float), z(float), z(np.int64)
    oa, of, ob = z(float), z(float), z(np.int64)
    m = W.walk(o, h, l, c, atr, sig, side, D["last_win"], rt, slip,
               g["stop"], g["tgt"], g["be"], g["be_off"], g["arm"], g["tr"],
               oi, ox, oR, op, ow, oa, of, ob)
    t = pd.DataFrame(dict(sig=oi[:m], exit=ox[:m], R=oR[:m], pts=op[:m], why=ow[:m],
                          mae=oa[:m], mfe=of[:m], amb=ob[:m]))
    t["side"] = side[t.sig.to_numpy()]
    t["blk"] = D["blk"][t.sig.to_numpy()]
    t["day"] = D["day"][t.sig.to_numpy()]
    return t


def stats(t, D, blk):
    s = t[t.blk == blk]
    days = D["days"][blk]
    r = s.pts.to_numpy()
    if len(r) < 5:
        return dict(n=len(r), per_yr=np.nan, pts=np.nan, pf=np.nan, win=np.nan,
                    sharpe=np.nan, dd=np.nan, ret_dd=np.nan, total=np.nan, hold=np.nan)
    shp, dser = S.day_sharpe(s.day.to_numpy(), r, days)
    eq = np.cumsum(dser.to_numpy() if hasattr(dser, "to_numpy") else dser)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else np.nan
    return dict(n=len(r), per_yr=len(r) / (len(days) / 252), pts=r.mean(),
                pf=r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9), win=(r > 0).mean(),
                sharpe=shp, dd=dd, ret_dd=r.sum() / max(dd, 1e-9), total=r.sum(),
                hold=float(np.median(s.exit - s.sig) * TF))


def daily(t, D, blk):
    """Points per SESSION, zero-filled on days that did not trade -- a leg is not paid for
    trading less, and a correlation matrix over traded days only is a matrix over a moving set."""
    days = D["days"][blk]
    s = t[t.blk == blk]
    ser = s.groupby("day").pts.sum()
    out = pd.Series(0.0, index=pd.Index(days))
    common = ser.index.intersection(out.index)
    out.loc[common] = ser.loc[common]
    return out


# ---------------------------------------------------------------- the two nulls
def control_random_entry(D, t, blk, g=GEOM, n_draw=1000, seed=0):
    """Random bars in the SAME window at the SAME rate with the SAME side mix and geometry, run
    through the SAME walk so the position lock rejects them exactly as it rejects real signals.

    The sampled bars are SORTED before the walk: they come out in draw order, not chronological
    order, and an unsorted control has the lock reject an arbitrary share (STUDY_V59)."""
    rng = np.random.default_rng(seed)
    elig = np.flatnonzero(D["inw"] & (D["blk"] == blk) & np.isfinite(D["atr"]) & (D["atr"] > 0))
    s = t[t.blk == blk]
    n_t = len(s)
    p_long = float((s.side > 0).mean()) if n_t else 0.5
    # rate over ELIGIBLE bars, not all bars (STUDY_V42)
    out = np.empty(n_draw)
    for b in range(n_draw):
        pick = np.sort(rng.choice(elig, min(n_t, len(elig)), replace=False))
        lg = np.zeros(D["n"], bool); sh = np.zeros(D["n"], bool)
        isl = rng.random(len(pick)) < p_long
        lg[pick[isl]] = True; sh[pick[~isl]] = True
        q = run(D, lg, sh, g)
        q = q[q.blk == blk]
        out[b] = q.pts.mean() if len(q) else np.nan
    real = s.pts.mean()
    return real, out, float(np.nanmean(out >= real))


def control_coin_side(D, sig_l, sig_s, blk, g=GEOM, n_draw=1000, seed=1):
    """Keep the rule's own BARS and flip a coin for the side. Isolates the direction call from the
    exposure: if this fails, whatever the rule earns is the window and the geometry."""
    rng = np.random.default_rng(seed)
    sig = sig_l | sig_s
    idx = np.flatnonzero(sig)
    t = run(D, sig_l, sig_s, g)
    real = t[t.blk == blk].pts.mean()
    out = np.empty(n_draw)
    for b in range(n_draw):
        isl = rng.random(len(idx)) < 0.5
        lg = np.zeros(D["n"], bool); sh = np.zeros(D["n"], bool)
        lg[idx[isl]] = True; sh[idx[~isl]] = True
        q = run(D, lg, sh, g)
        q = q[q.blk == blk]
        out[b] = q.pts.mean() if len(q) else np.nan
    return real, out, float(np.nanmean(out >= real))


# ---------------------------------------------------------------- the Monte Carlos
def mc_bootstrap(t, D, blk, n=2000, seed=2):
    """Day-block bootstrap for the EDGE: resample whole SESSIONS with their trades attached."""
    rng = np.random.default_rng(seed)
    s = t[t.blk == blk]
    grp = {d: g.pts.to_numpy() for d, g in s.groupby("day")}
    keys = list(grp)
    out = np.empty(n)
    for b in range(n):
        pick = rng.choice(len(keys), len(keys))
        out[b] = np.concatenate([grp[keys[j]] for j in pick]).mean()
    return out, float((out <= 0).mean()), np.percentile(out, [2.5, 97.5])


def mc_permute(t, D, blk, n=2000, seed=3):
    """Permutation for the PATH: reordering realised trades cannot change the endpoint, so this
    answers a DRAWDOWN question only (STUDY_V31)."""
    rng = np.random.default_rng(seed)
    r = t[t.blk == blk].pts.to_numpy()
    eq = np.cumsum(r)
    real_dd = float(np.max(np.maximum.accumulate(eq) - eq))
    out = np.empty(n)
    for b in range(n):
        e = np.cumsum(rng.permutation(r))
        out[b] = np.max(np.maximum.accumulate(e) - e)
    return real_dd, out, float((out <= real_dd).mean())


def mc_execution(D, sig_l, sig_s, blk, n=400, seed=4):
    """Execution noise: slippage U(0, 2x) and cost U(0.5x, 2x) applied INSIDE the walk, so the
    exits move rather than the P&L being scaled afterwards."""
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    for b in range(n):
        t = run(D, sig_l, sig_s, rt=S.RT_POINTS * rng.uniform(0.5, 2.0),
                slip=S.SLIP_POINTS * rng.uniform(0.0, 2.0))
        q = t[t.blk == blk]
        out[b] = q.pts.sum() if len(q) else np.nan
    return out


def mc_jitter(D, base, blk, p, ticks=1.0, n=200, seed=5, g=GEOM):
    """Price jitter with the SIGNAL RECOMPUTED. Every OHLC is nudged independently, the bar is
    repaired (high = max of the four, low = min), and ATR, the pivots and the CVD are all rebuilt
    from the jittered bars -- otherwise this prices execution noise a second time and not the
    fragility of the rule itself."""
    rng = np.random.default_rng(seed)
    tick = 0.25
    out = np.empty(n)
    D2 = dict(D)
    for b in range(n):
        j = lambda x: x + rng.normal(0, ticks * tick, len(x))
        o, h, l, c = j(D["o"]), j(D["h"]), j(D["l"]), j(D["c"])
        hi = np.maximum.reduce([o, h, l, c]); lo = np.minimum.reduce([o, h, l, c])
        tr = np.maximum(hi - lo, np.maximum(np.abs(hi - np.roll(c, 1)), np.abs(lo - np.roll(c, 1))))
        tr[0] = hi[0] - lo[0]
        atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
        D2["o"], D2["h"], D2["l"], D2["c"], D2["atr"] = o, hi, lo, c, atr
        F2 = dict(cvd=SG.cvd_proxy(D2, base))
        lg, sh = SG.s3_flow_exhaustion(D2, F2, p)
        t = run(D2, lg, sh, g, o=o, h=hi, l=lo, c=c, atr=atr)
        q = t[t.blk == blk]
        out[b] = q.pts.sum() if len(q) else np.nan
    return out


# ---------------------------------------------------------------- fast paths for the jitter MC
def pivots_fast(x, k):
    """Vectorised twin of s5sig._pivots. A pivot at i is STAMPED at i+k, never at i.

    The reference implementation is a Python loop over every bar, which makes a jitter Monte Carlo
    that must recompute the pivots on every draw cost hours. Asserted identical to it before use --
    a faster kernel that disagrees is a different study, not a faster one."""
    from numpy.lib.stride_tricks import sliding_window_view
    n = len(x)
    lo = np.zeros(n, bool); hi = np.zeros(n, bool)
    if n < 2 * k + 1:
        return lo, hi
    win = sliding_window_view(x, 2 * k + 1)          # win[j] covers x[j : j+2k+1], centre j+k
    ctr = x[k:n - k]
    lo[2 * k:n] = ctr == np.nanmin(win, axis=1)
    hi[2 * k:n] = ctr == np.nanmax(win, axis=1)
    return lo, hi


def s3_fast(D, cvd, p):
    """s5sig.s3_flow_exhaustion on the vectorised pivots. Same semantics, same output."""
    k, w = p["k"], p["w"]
    plo, _ = pivots_fast(D["l"], k)
    _, pho = pivots_fast(D["h"], k)
    n = D["n"]
    lg = np.zeros(n, bool); sh = np.zeros(n, bool)
    li = np.flatnonzero(plo)
    if len(li) > 1:
        a, b = li[:-1], li[1:]
        m = (b - a <= w) & (D["l"][b - k] < D["l"][a - k]) & (cvd[b - k] > cvd[a - k])
        lg[b[m]] = True
    hj = np.flatnonzero(pho)
    if len(hj) > 1:
        a, b = hj[:-1], hj[1:]
        m = (b - a <= w) & (D["h"][b - k] > D["h"][a - k]) & (cvd[b - k] < cvd[a - k])
        sh[b[m]] = True
    return lg & D["inw"], sh & D["inw"]


def mc_jitter_fast(D, base, blk, p, ticks=1.0, n=200, seed=5, g=GEOM):
    """Price jitter with ATR, the pivots and the CVD all rebuilt from the jittered bars."""
    rng = np.random.default_rng(seed)
    tick = 0.25
    out = np.empty(n)
    D2 = dict(D)
    for b in range(n):
        j = lambda x: x + rng.normal(0, ticks * tick, len(x))
        o, h, l, c = j(D["o"]), j(D["h"]), j(D["l"]), j(D["c"])
        hi = np.maximum.reduce([o, h, l, c]); lo = np.minimum.reduce([o, h, l, c])
        tr = np.maximum(hi - lo, np.maximum(np.abs(hi - np.roll(c, 1)), np.abs(lo - np.roll(c, 1))))
        tr[0] = hi[0] - lo[0]
        atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
        D2["o"], D2["h"], D2["l"], D2["c"], D2["atr"] = o, hi, lo, c, atr
        cvd = SG.cvd_proxy(D2, base)
        lg, sh = s3_fast(D2, cvd, p)
        t = run(D2, lg, sh, g, o=o, h=hi, l=lo, c=c, atr=atr)
        q = t[t.blk == blk]
        out[b] = q.pts.sum() if len(q) else np.nan
    return out
