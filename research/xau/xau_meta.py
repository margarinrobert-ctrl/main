"""PHASE 3 -- the META LAYER's feature set. Every feature is read at the SIGNAL bar and nothing
here is ever a standalone signal: the primary decides WHETHER an event exists, the meta layer only
scores events the primary has already emitted.

FRACDIFF. Lopez de Prado's fixed-width fractional differencing: the memory-preserving transform
that makes a price series stationary WITHOUT differencing away its level information. The weight
sequence w_k = -w_{k-1} * (d - k + 1)/k is truncated where |w_k| < tau, giving a FIXED window, so
bar t's value depends on a fixed number of PRIOR bars and nothing after it. The order d is chosen
by ADF ON BLOCK A ONLY -- the smallest d on a declared ladder whose ADF t clears the 5% MacKinnon
value -- and then frozen. Choosing d on the block the meta layer trains on would be selection.

HMM. `research/v27/v27hmm.py`, hand-rolled Baum-Welch, used the ONLY way this branch permits:
parameters fitted on BLOCK A and FILTERED posteriors P(s_t | data up to t) everywhere else.
`posterior_smoothed` and Viterbi read the future -- STUDY_V27 measured what that is worth
(locked PF 1.351 smoothed against 0.973 causal on NEARLY IDENTICAL TRADE COUNTS, so the leak is
invisible in the count and shows only in which bars got labelled). The smoothed posterior is
computed here too, and used for exactly one thing: a leakage diagnostic that must be reported.

Everything else is the branch's standard causal material -- volatility state, trend location,
breakout context, the clock, and the primary's own recent outcomes.
"""
import os, sys, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v27", "research/v18"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v27hmm as H
from v18diag import adf

D_LADDER = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def ffd_weights(d, tau=1e-4, max_k=2000):
    w = [1.0]
    for k in range(1, max_k):
        nw = -w[-1] * (d - k + 1) / k
        if abs(nw) < tau:
            break
        w.append(nw)
    return np.array(w[::-1])


def ffd(x, d, tau=1e-4):
    """Fixed-width fractional difference. out[t] uses x[t-L+1..t] only."""
    w = ffd_weights(d, tau)
    L = len(w)
    out = np.full(len(x), np.nan)
    if L > len(x):
        return out, L
    # rolling dot product
    s = pd.Series(x)
    v = np.convolve(np.asarray(x, float), w[::-1], mode="valid")
    out[L - 1:] = v
    return out, L


def choose_d(x, mask, tau=1e-4):
    """Smallest d on the declared ladder whose ADF t clears the 5% value, ON THE SUPPLIED MASK
    ONLY (block A). Returns (d, table)."""
    rows = []
    pick = D_LADDER[-1]
    got = False
    for d in D_LADDER:
        f, L = ffd(x, d, tau)
        s = f[mask & np.isfinite(f)]
        s = s[::8][-20000:]          # thin: ADF on 15m bars is autocorrelated and slow
        t, crit, lag = adf(s)
        rows.append(dict(d=d, window=L, adf_t=t, crit5=crit["5%"] if isinstance(crit, dict) else np.nan,
                         stationary=bool(np.isfinite(t) and t < (crit["5%"] if isinstance(crit, dict) else -2.86))))
        if not got and rows[-1]["stationary"]:
            pick, got = d, True
    return pick, pd.DataFrame(rows)


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    return 100.0 - 100.0 / (1.0 + up / np.maximum(dn, 1e-12))


def _chop(h, l, c, n=14):
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    st = pd.Series(tr).rolling(n).sum().to_numpy()
    rng = pd.Series(h).rolling(n).max().to_numpy() - pd.Series(l).rolling(n).min().to_numpy()
    with np.errstate(all="ignore"):
        return 100.0 * np.log10(st / np.maximum(rng, 1e-12)) / np.log10(n)


def _adx(h, l, c, n=14):
    up = np.diff(h, prepend=h[0]); dn = -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    a = lambda z: pd.Series(z).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    atr = np.maximum(a(tr), 1e-12)
    pdi = 100 * a(pdm) / atr; ndi = 100 * a(ndm) / atr
    dx = 100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-12)
    return a(dx), pdi, ndi


def _hmm_obs(D):
    c = D["c"]
    r = np.zeros_like(c); r[1:] = np.diff(np.log(c))
    rv = pd.Series(r).rolling(48).std().to_numpy()
    return np.column_stack([r * 100.0, np.nan_to_num(rv * 100.0, nan=0.0)])


def hmm_fit(D, mask_fit, K=3, seed=0):
    """Baum-Welch on BLOCK A ONLY. Returns the frozen parameter set."""
    x = _hmm_obs(D)[mask_fit]
    pi, A, mu, var, ll = H.fit(x[::4], K=K, iters=40, seed=seed)    # thin for speed; same series
    order = np.argsort(mu[:, 0])                                    # bear, side, bull by drift
    return dict(pi=pi, A=A, mu=mu, var=var, ll=ll, order=order, K=K)


def hmm_states(D, hp, want_smoothed=False):
    """FILTERED posteriors under FROZEN parameters. The smoothed posterior is computed only when
    asked and only as a LEAKAGE DIAGNOSTIC -- it must never become a feature."""
    x = _hmm_obs(D)
    filt = H.posterior_filtered(x, hp["pi"], hp["A"], hp["mu"], hp["var"])[:, hp["order"]]
    smoo = H.posterior_smoothed(x, hp["pi"], hp["A"], hp["mu"], hp["var"])[:, hp["order"]] if want_smoothed else None
    return filt, smoo


def build_features(D, mask_A=None, d_tau=1e-4, seed=0, frozen=None, want_smoothed=False):
    """All causal. Returns (DataFrame indexed by bar, meta dict).

    `frozen` supplies the fracdiff order and the HMM parameters already chosen on block A, so the
    truncation audit re-runs the TRANSFORM on truncated history without re-running the FIT -- which
    is the correct test, because block A ends before every probe bar and the fit is not a function
    of the probe's own history."""
    o, h, l, c, v = D["o"], D["h"], D["l"], D["c"], D["v"]
    atr = D["atr"]; n = D["n"]
    F = {}
    lc = np.log(c)

    if frozen is None:
        d, dtab = choose_d(lc, mask_A, d_tau)
        hp = hmm_fit(D, mask_A, K=3, seed=seed)
    else:
        d, dtab, hp = frozen["d"], frozen.get("d_table"), frozen["hmm"]
    fd, L = ffd(lc, d, d_tau)
    F["ffd"] = fd
    F["ffd_z"] = (fd - pd.Series(fd).rolling(500).mean().to_numpy()) / np.maximum(pd.Series(fd).rolling(500).std().to_numpy(), 1e-12)

    filt, smoo = hmm_states(D, hp, want_smoothed=want_smoothed)
    F["hmm_bear"], F["hmm_side"], F["hmm_bull"] = filt[:, 0], filt[:, 1], filt[:, 2]
    F["hmm_edge"] = filt[:, 2] - filt[:, 0]

    ap = atr / np.maximum(c, 1e-12)
    F["atr_pct"] = ap
    F["atr_rank500"] = pd.Series(ap).rolling(500).rank(pct=True).to_numpy()
    F["atr_ratio100"] = atr / np.maximum(pd.Series(atr).rolling(100).mean().to_numpy(), 1e-12)
    r1 = np.zeros(n); r1[1:] = np.diff(np.log(c))
    F["rv48"] = pd.Series(r1).rolling(48).std().to_numpy() * 100.0
    F["rv_ratio"] = F["rv48"] / np.maximum(pd.Series(r1).rolling(480).std().to_numpy() * 100.0, 1e-12)

    e50, e200 = _ema(c, 50), _ema(c, 200)
    F["d_ema50"] = (c - e50) / np.maximum(atr, 1e-12)
    F["d_ema200"] = (c - e200) / np.maximum(atr, 1e-12)
    F["ema_slope200"] = (e200 - np.concatenate((np.full(50, np.nan), e200[:-50]))) / np.maximum(atr, 1e-12)
    F["rsi14"] = _rsi(c, 14)
    F["roc20"] = 100.0 * (c / np.concatenate((np.full(20, np.nan), c[:-20])) - 1.0)
    F["roc96"] = 100.0 * (c / np.concatenate((np.full(96, np.nan), c[:-96])) - 1.0)

    ch = D["ent_hi"][70 - 2]
    F["excess"] = (h - ch) / np.maximum(atr, 1e-12)
    F["ch_width"] = (D["ent_hi"][70 - 2] - D["ent_lo"][70 - 2]) / np.maximum(atr, 1e-12)
    F["close_pos"] = (c - l) / np.maximum(h - l, 1e-12)
    F["body"] = np.abs(c - o) / np.maximum(atr, 1e-12)
    F["chop14"] = _chop(h, l, c, 14)
    ax, pdi, ndi = _adx(h, l, c, 14)
    F["adx14"] = ax; F["di_diff"] = pdi - ndi
    F["vol_ratio"] = v / np.maximum(pd.Series(v).rolling(96).mean().to_numpy(), 1e-12)

    mod = D["ix"].hour * 60 + D["ix"].minute
    F["hour_sin"] = np.sin(2 * np.pi * mod / 1440.0)
    F["hour_cos"] = np.cos(2 * np.pi * mod / 1440.0)
    F["dow"] = D["ix"].dayofweek.to_numpy().astype(float)

    X = pd.DataFrame(F)
    meta = dict(d=d, d_table=dtab, ffd_window=L, hmm=hp, smoothed=smoo)
    return X, meta


def audit(D, X, frozen, probes=200, seed=1):
    """TRUNCATION AUDIT. Recompute the whole feature block on history that ENDS at bar i and require
    every value at i to match. The only honest leakage test on this branch."""
    rng = np.random.default_rng(seed)
    lo = max(3000, np.flatnonzero(D["blk"] == 1)[0])
    hi = D["n"] - 10
    idx = rng.choice(np.arange(lo, hi), size=probes, replace=False)
    bad, checked = [], 0
    for i in sorted(idx):
        cut = dict(D)
        for k in ("o", "h", "l", "c", "v", "atr", "blk"):
            cut[k] = D[k][:i + 1]
        cut["ix"] = D["ix"][:i + 1]; cut["n"] = i + 1
        cut["ent_hi"] = D["ent_hi"][:, :i + 1]; cut["ent_lo"] = D["ent_lo"][:, :i + 1]
        Xi, _ = build_features(cut, frozen=frozen)
        a, b = X.iloc[i], Xi.iloc[-1]
        for col in X.columns:
            va, vb = a[col], b[col]
            if not np.isfinite(va) and not np.isfinite(vb):
                continue
            checked += 1
            if not np.isclose(va, vb, rtol=1e-6, atol=1e-8):
                bad.append((i, col, va, vb))
    return bad, checked, len(idx)
