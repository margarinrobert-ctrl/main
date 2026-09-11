"""META-LAYER FEATURES for the IB primary -- every one stamped at or before the moment the order
is placed, side-oriented, in six declared families, with a truncation audit.

WHEN IS THE DECISION MADE. The plan (IB high/low, ATR, everything the first hour says) is fixed at
the last IB bar. The ORDER is placed at the BREAK bar. So two stamps are legal: plan-bar features
(family ib, ctx, trend, vol, regime) and break-bar features (family brk). Nothing reads the fill
bar or anything after it -- `STUDY_AUCTION`'s `ent_bar` leak is structurally impossible here.

SIDE-ORIENTED. Signed readings are multiplied by +1 for a long and -1 for a short, so 'higher is
more favourable to the side taken' means one thing on both sides (`v58ib` convention).

FRACDIFF AND HMM ARE META FEATURES ONLY. FFD on the daily close with d chosen by ADF on the
research days alone; a 3-state Gaussian HMM fitted on research daily returns and read FILTERED --
the smoothed posterior is computed only as a leakage diagnostic (`STUDY_V27`).

CALENDAR CONDITIONS ARE BANNED. No weekday, no month.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.path.join(ROOT, "research", "v27"), os.path.join(ROOT, "research", "v18")):
    if p not in sys.path:
        sys.path.insert(0, p)
from research.ibopt import ibcore as C      # noqa: E402
import v27hmm as H                           # noqa: E402
from v18diag import adf                      # noqa: E402

D_LADDER = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
FAMILIES = ("ib", "ctx", "trend", "vol", "regime", "brk")


# ------------------------------------------------------------------ helpers
def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = pd.Series(up).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    ad = pd.Series(dn).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    return 100 - 100 / (1 + au / np.maximum(ad, 1e-12))


def _adx(h, l, c, n=14):
    up, dn = np.diff(h, prepend=h[0]), -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    pdi = 100 * pd.Series(pdm).ewm(alpha=1 / n, adjust=False).mean().to_numpy() / np.maximum(atr, 1e-9)
    ndi = 100 * pd.Series(ndm).ewm(alpha=1 / n, adjust=False).mean().to_numpy() / np.maximum(atr, 1e-9)
    dx = 100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-9)
    return pd.Series(dx).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def _er(c, n):
    ch = np.abs(c - np.concatenate((np.full(n, np.nan), c[:-n])))
    path = pd.Series(np.abs(np.diff(c, prepend=c[0]))).rolling(n).sum().to_numpy()
    return ch / np.maximum(path, 1e-12)


def _chop(h, l, c, n=14):
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    s = pd.Series(tr).rolling(n).sum().to_numpy()
    hh = pd.Series(h).rolling(n).max().to_numpy(); ll = pd.Series(l).rolling(n).min().to_numpy()
    return 100 * np.log10(s / np.maximum(hh - ll, 1e-12)) / np.log10(n)


def _slope(c, n=20):
    x = np.arange(n) - (n - 1) / 2
    return pd.Series(c).rolling(n).apply(lambda w: float(np.dot(x, w - w.mean()) / np.dot(x, x)), raw=True).to_numpy()


def ffd_weights(d, tau=1e-4, max_k=2000):
    w = [1.0]
    for k in range(1, max_k):
        wk = -w[-1] * (d - k + 1) / k
        if abs(wk) < tau:
            break
        w.append(wk)
    return np.array(w)


def ffd(x, d, tau=1e-4):
    w = ffd_weights(d, tau); L = len(w)
    out = np.full(len(x), np.nan)
    for i in range(L - 1, len(x)):
        seg = x[i - L + 1:i + 1]
        if np.all(np.isfinite(seg)):
            out[i] = float(np.dot(w[::-1], seg))
    return out, L


def choose_d(x, mask):
    for d in D_LADDER:
        f, L = ffd(x, d)
        s = f[mask & np.isfinite(f)]
        if len(s) < 100:
            continue
        t, crit, _ = adf(s)
        c5 = crit["5%"] if isinstance(crit, dict) else -2.86
        if t < c5:
            return d, float(t)
    return D_LADDER[-1], np.nan


# ------------------------------------------------------------------ the daily frame (causal)
def daily_frame(F):
    """Per session: cash open (09:30 bar open), cash close (last bar before 16:00), RTH high/low,
    overnight range. Everything is derived from the session's OWN bars."""
    o, h, l, c, v, mod = F["o"], F["h"], F["l"], F["c"], F["v"], F["mod"]
    D = F["D"]
    rows = []
    for d in range(D):
        a, b = F["starts"][d], F["ends"][d]
        m = mod[a:b]
        rth = np.flatnonzero((m >= C.IB_OPEN) & (m < 960))
        pre = np.flatnonzero(m < C.IB_OPEN)
        post = np.flatnonzero(m >= 960)
        i0 = a + rth[0]; i1 = a + rth[-1]
        rows.append(dict(open=o[i0], close=c[i1], high=h[a + rth].max(), low=l[a + rth].min(),
                         pre_hi=h[a + pre].max() if len(pre) else np.nan,
                         pre_lo=l[a + pre].min() if len(pre) else np.nan,
                         post_hi=h[a + post].max() if len(post) else np.nan,
                         post_lo=l[a + post].min() if len(post) else np.nan,
                         rth_vol=v[a + rth].sum()))
    return pd.DataFrame(rows)


def build_features(F, t, hmm=None, d_ffd=None, mask_fit=None, want_smoothed=False):
    """Features for the event table `t` (from ibcore.run). Returns (X, meta) with `meta` carrying
    the frozen HMM / d so the audit can re-run the TRANSFORM without re-running the FIT."""
    o, h, l, c, v, mod = F["o"], F["h"], F["l"], F["c"], F["v"], F["mod"]
    atr = F["atr"]
    e13, e48, e200 = _ema(c, 13), _ema(c, 48), _ema(c, 200)
    rsi = _rsi(c); adx = _adx(h, l, c); er20 = _er(c, 20); chop = _chop(h, l, c); slope = _slope(c, 20)
    atr_roll = pd.Series(atr).rolling(100).mean().to_numpy()
    DF = daily_frame(F)
    dc = DF["close"].to_numpy(); do_ = DF["open"].to_numpy()
    dret = np.zeros(len(dc)); dret[1:] = np.diff(np.log(dc))
    rv20 = pd.Series(dret).rolling(20).std().to_numpy()
    rv_rank = pd.Series(rv20).rolling(250, min_periods=60).rank(pct=True).to_numpy()
    # HMM on daily (return, rv) -- fitted on research days only, read FILTERED
    obs = np.column_stack([dret * 100.0, np.nan_to_num(rv20 * 100.0, nan=0.0)])
    if hmm is None:
        pi, A, mu, var, ll = H.fit(obs[mask_fit], K=3, iters=60, seed=0)
        hmm = dict(pi=pi, A=A, mu=mu, var=var, order=np.argsort(mu[:, 0]))
    filt = H.posterior_filtered(obs, hmm["pi"], hmm["A"], hmm["mu"], hmm["var"])[:, hmm["order"]]
    smoo = H.posterior_smoothed(obs, hmm["pi"], hmm["A"], hmm["mu"], hmm["var"])[:, hmm["order"]] if want_smoothed else None
    # FFD on the daily log close, d chosen on research
    lc = np.log(dc)
    if d_ffd is None:
        d_ffd, _t = choose_d(lc, mask_fit)
    fd, _L = ffd(lc, d_ffd)
    fz = (fd - pd.Series(fd).rolling(100, min_periods=40).mean().to_numpy()) / \
        np.maximum(pd.Series(fd).rolling(100, min_periods=40).std().to_numpy(), 1e-9)
    # per-DAY Initial Balance range and per-bar volume for the primary's own IB length, so the
    # trailing readings are functions of PRIOR DAYS and not of which days happened to trade
    rows = []
    day_rng = np.full(F["D"], np.nan); day_vol = np.full(F["D"], np.nan)
    if len(t):
        first_plan_mod = mod[int(t.plan.iloc[0])]
        for d in range(F["D"]):
            a, b = F["starts"][d], F["ends"][d]; m = mod[a:b]
            k = np.flatnonzero((m >= C.IB_OPEN) & (m <= first_plan_mod))
            if len(k):
                day_rng[d] = h[a + k].max() - l[a + k].min(); day_vol[d] = v[a + k].sum() / len(k)
    rng_med = pd.Series(day_rng).rolling(20, min_periods=10).median().shift(1).to_numpy()
    vol_exp = pd.Series(day_vol).expanding(min_periods=10).mean().shift(1).to_numpy()
    for _, r in t.iterrows():
        d = int(r.day); plan = int(r.plan); fill = int(r.fill); s = 1.0 if r.side == 0 else -1.0
        a, b = F["starts"][d], F["ends"][d]
        m = mod[a:b]
        ibsel = np.flatnonzero((m >= C.IB_OPEN) & (a + np.arange(len(m)) <= plan))
        ib_idx = a + ibsel
        hi, lo = h[ib_idx].max(), l[ib_idx].min(); rng = hi - lo
        A = atr[plan]
        # the break bar: first bar after plan that exceeds the traded edge
        brk = -1
        for i in range(plan + 1, fill):
            if (s > 0 and h[i] > hi) or (s < 0 and l[i] < lo):
                brk = i; break
        if brk < 0:
            brk = fill - 1 if fill - 1 > plan else plan + 1
        edge = hi if s > 0 else lo
        # prior-day and daily context: everything indexed d-1 or earlier
        pd_ret = dret[d]                      # close[d-1] vs close[d-2]: dret[d] = log(dc[d]/dc[d-1]) is TODAY -- use d-1
        pd_ret = dret[d - 1] if d >= 1 else np.nan
        pdr = (DF.high[d - 1] - DF.low[d - 1]) if d >= 1 else np.nan
        pdc = ((DF.close[d - 1] - DF.low[d - 1]) / max(pdr, 1e-9)) if d >= 1 else np.nan
        on_hi = np.nanmax([DF.post_hi[d - 1] if d >= 1 else np.nan, DF.pre_hi[d]])
        on_lo = np.nanmin([DF.post_lo[d - 1] if d >= 1 else np.nan, DF.pre_lo[d]])
        ret5 = (np.log(dc[d - 1]) - np.log(dc[d - 6])) if d >= 6 else np.nan
        ret20 = (np.log(dc[d - 1]) - np.log(dc[d - 21])) if d >= 21 else np.nan
        rel = rng / rng_med[d] if np.isfinite(rng_med[d]) and rng_med[d] > 0 else np.nan
        ibv = v[ib_idx].sum()
        vrel = (ibv / max(len(ib_idx), 1)) / vol_exp[d] if np.isfinite(vol_exp[d]) and vol_exp[d] > 0 else np.nan
        f = dict(
            ev=int(_), day=d, side=int(r.side), blk=int(r.blk), pct=float(r.pct), R=float(r.R),
            **{"ib.range_atr": rng / A, "ib.range_rel": rel,
               "ib.cpos": s * ((c[plan] - lo) / rng - 0.5),
               "ib.hour_dir": s * (c[plan] - o[ib_idx[0]]) / rng,
               "ib.edge_bar": (np.argmax(h[ib_idx]) if s > 0 else np.argmin(l[ib_idx])) / max(len(ib_idx) - 1, 1),
               "ib.vol_rel": vrel,
               "ctx.gap": s * (o[ib_idx[0]] - dc[d - 1]) / A if d >= 1 else np.nan,
               "ctx.on_range": (on_hi - on_lo) / A if np.isfinite(on_hi) and np.isfinite(on_lo) else np.nan,
               "ctx.pd_ret": s * pd_ret * dc[d - 1] / A if d >= 1 else np.nan,
               "ctx.pd_range": pdr / A if d >= 1 else np.nan,
               "ctx.pd_cpos": s * (pdc - 0.5) if d >= 1 else np.nan,
               "ctx.ret5": s * ret5 * dc[d - 1] / (A * np.sqrt(5)) if d >= 6 else np.nan,
               "ctx.ret20": s * ret20 * dc[d - 1] / (A * np.sqrt(20)) if d >= 21 else np.nan,
               "trend.ema13_48": s * (e13[plan] - e48[plan]) / A,
               "trend.ema200": s * (c[plan] - e200[plan]) / A,
               "trend.adx14": adx[plan], "trend.er20": er20[plan],
               "trend.rsi14": rsi[plan] if s > 0 else 100 - rsi[plan],
               "trend.slope20": s * slope[plan] / A,
               "vol.atr_ratio100": A / max(atr_roll[plan], 1e-9),
               "vol.rv20_rank": rv_rank[d - 1] if d >= 1 else np.nan,
               "vol.chop14": chop[plan],
               "regime.hmm_side": s * (filt[d - 1, 2] - filt[d - 1, 0]) if d >= 1 else np.nan,
               "regime.hmm_mid": filt[d - 1, 1] if d >= 1 else np.nan,
               "regime.ffd_z": s * fz[d - 1] if d >= 1 else np.nan,
               "brk.minutes": (brk - plan) * 15.0,
               "brk.dist": s * ((h[brk] if s > 0 else l[brk]) - edge) / A,
               "brk.body": s * (c[brk] - o[brk]) / max(h[brk] - l[brk], 1e-9),
               "brk.close_through": s * (c[brk] - edge) / A,
               "brk.vol_rel": v[brk] / max(ibv / max(len(ib_idx), 1), 1e-9)})
        rows.append(f)
    X = pd.DataFrame(rows)
    meta = dict(hmm=hmm, d_ffd=d_ffd, smoothed=smoo)
    return X, meta


def feature_cols(X):
    return [k for k in X.columns if "." in k]


def truncation_audit(F, t, X, meta, n_probe=40, seed=3):
    """Recompute each probed event's features on a history that ENDS at its break bar and
    require the value to match. Frozen HMM and d, so only the transform is re-run."""
    rng = np.random.default_rng(seed)
    ev = rng.choice(len(t), size=min(n_probe, len(t)), replace=False)
    bad = 0; checked = 0
    for k in ev:
        r = t.iloc[k]
        end = int(r.fill)                       # truncate strictly before the fill bar
        d = int(r.day)
        Ft = dict(F)
        for key in ("o", "h", "l", "c", "v", "mod", "atr"):
            Ft[key] = F[key][:end]
        Ft["starts"] = F["starts"][:d + 1]; Ft["ends"] = np.concatenate([F["ends"][:d], [end]])
        Ft["D"] = d + 1; Ft["blk"] = F["blk"][:d + 1]; Ft["dates"] = F["dates"][:d + 1]
        tt = t.iloc[[k]].copy()
        try:
            Xt, _ = build_features(Ft, tt, hmm=meta["hmm"], d_ffd=meta["d_ffd"])
        except Exception:
            bad += 1; checked += 1; continue
        for col in feature_cols(X):
            a, b = X.iloc[k][col], Xt.iloc[0][col]
            checked += 1
            if not ((np.isnan(a) and np.isnan(b)) or np.isclose(a, b, rtol=1e-8, atol=1e-10)):
                bad += 1
    return bad, checked
