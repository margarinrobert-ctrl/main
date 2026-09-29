"""SIX DECLARED FEATURE FAMILIES, fixed before any scoring so the family count is not itself a
search. Everything is read at the SIGNAL BAR -- `STUDY_AUCTION` recorded what reading at the FILL
bar costs: a holdout result at p 0.0005 that replicated across nine strategies and was pure leakage.

    vol   volatility level, ratio, expansion, Parkinson, Garman-Klass, vol-of-vol -- and the same
          quantities against a CAUSAL TIME-OF-DAY baseline. Never a trailing mean:
          `STUDY_VWAP_STOCH_ATR` measured that on a 24-hour tape an RTH bar clears its own 50-bar
          trailing ATR mean 98.9% of the time against 25.1% for an overnight bar, so `atr/sma(atr)`
          is a clock feature wearing a volatility name, and every rung of it is inert on a
          session-restricted trigger.
    hmm   a Gaussian HMM fitted by Baum-Welch on the RESEARCH BLOCK ONLY and read through the
          FILTERED posterior only. `STUDY_V27_HMM`: both fixes are needed, and the smoothed
          posterior is computed here for exactly one purpose -- a leakage diagnostic.
    ffd   fixed-width fractional differencing, `d` chosen by ADF ON THE RESEARCH BLOCK ONLY.
    str   breakout structure: where this bar sits in its own channel, its own range, its session.
    mom   momentum at several horizons, plus the two readings the primary itself does not use.
    par   participation against the same causal time-of-day baseline.

    ctx   session clock. DECLARED SEPARATELY and flagged: inside a fixed 07:00-11:00 window this
          takes sixteen values and a model can memorise the window rather than the market.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "research"), os.path.join(ROOT, "research/v27"),
          os.path.join(ROOT, "research/v18")):
    if p not in sys.path:
        sys.path.insert(0, p)

import v27hmm as H          # noqa: E402
from v18diag import adf     # noqa: E402

D_LADDER = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


# ------------------------------------------------------------------ fracdiff
def ffd_weights(d, tau=1e-4, max_k=3000):
    w = [1.0]
    for k in range(1, max_k):
        nw = -w[-1] * (d - k + 1) / k
        if abs(nw) < tau:
            break
        w.append(nw)
    return np.array(w[::-1])


def ffd(x, d, tau=1e-4):
    """out[t] uses a FIXED number of prior bars and nothing after."""
    w = ffd_weights(d, tau)
    Lw = len(w)
    out = np.full(len(x), np.nan)
    if Lw <= len(x):
        out[Lw - 1:] = np.convolve(np.asarray(x, float), w[::-1], mode="valid")
    return out, Lw


def choose_d(x, mask, tau=1e-4):
    rows, pick, got = [], D_LADDER[-1], False
    for d in D_LADDER:
        fv, Lw = ffd(x, d, tau)
        s = fv[mask & np.isfinite(fv)][::4][-20000:]
        t, crit, _ = adf(s)
        c5 = crit["5%"] if isinstance(crit, dict) else -2.86
        ok = bool(np.isfinite(t) and t < c5)
        rows.append(dict(d=d, window=Lw, adf_t=t, crit5=c5, stationary=ok))
        if not got and ok:
            pick, got = d, True
    return pick, pd.DataFrame(rows)


# ------------------------------------------------------------------ HMM
def hmm_obs(c):
    r = np.zeros(len(c))
    r[1:] = np.diff(np.log(np.maximum(c, 1e-9)))
    rv = pd.Series(r).rolling(96).std().to_numpy()
    return np.column_stack([r * 100.0, np.nan_to_num(rv * 100.0, nan=0.0)])


def hmm_fit(c, mask_fit, K=3, seed=0, thin=6):
    x = hmm_obs(c)[mask_fit]
    pi, A, mu, var, ll = H.fit(x[::thin], K=K, iters=40, seed=seed)
    return dict(pi=pi, A=A, mu=mu, var=var, ll=ll, order=np.argsort(mu[:, 0]), K=K)


# ------------------------------------------------------------------ helpers
def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _rank(x, n):
    return pd.Series(x).rolling(n).rank(pct=True).to_numpy()


def _tod(x, mod):
    """CAUSAL time-of-day baseline: for each minute-of-day, the expanding mean of PRIOR days."""
    return pd.DataFrame({"x": x, "m": mod}).groupby("m")["x"].transform(
        lambda s: s.shift(1).expanding().mean()).to_numpy()


def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    return 100.0 - 100.0 / (1.0 + up / np.maximum(dn, 1e-12))


def _dmi(h, l, c, n=14):
    up = np.diff(h, prepend=h[0])
    dn = -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    a = lambda z: pd.Series(z).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    atr = np.maximum(a(tr), 1e-12)
    return 100 * a(pdm) / atr, 100 * a(ndm) / atr


def _er(c, n):
    d = np.abs(np.diff(c, prepend=c[0]))
    net = np.abs(c - np.concatenate((np.full(n, np.nan), c[:-n])))
    return net / np.maximum(pd.Series(d).rolling(n).sum().to_numpy(), 1e-12)


def _chop(h, l, c, n=14):
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    st = pd.Series(tr).rolling(n).sum().to_numpy()
    rng = pd.Series(h).rolling(n).max().to_numpy() - pd.Series(l).rolling(n).min().to_numpy()
    with np.errstate(all="ignore"):
        return 100.0 * np.log10(st / np.maximum(rng, 1e-12)) / np.log10(n)


def _sojourn(lab):
    """Bars the current argmax state has been held, causal by construction."""
    out = np.zeros(len(lab))
    run = 0
    prev = -1
    for i in range(len(lab)):
        run = run + 1 if lab[i] == prev else 1
        prev = lab[i]
        out[i] = run
    return out


# ------------------------------------------------------------------ the build
def build(f, mask_research=None, frozen=None, want_smoothed=False):
    o = f["open"].to_numpy(float)
    h = f["high"].to_numpy(float)
    l = f["low"].to_numpy(float)
    c = f["close"].to_numpy(float)
    v = f["volume"].to_numpy(float)
    atr = f["atr"].to_numpy(float)
    mod = f["mod"].to_numpy().astype(int)
    n = len(c)
    lc = np.log(np.maximum(c, 1e-9))
    F = {}

    if frozen is None:
        d, dtab = choose_d(lc, mask_research)
        hp = hmm_fit(c, mask_research, K=3, seed=0)
    else:
        d, dtab, hp = frozen["d"], frozen.get("d_table"), frozen["hmm"]

    # ---------------- vol
    ap = atr / np.maximum(c, 1e-12)
    F["vol.atr_pct"] = ap
    F["vol.atr_rank250"] = _rank(ap, 250)
    F["vol.atr_rank1000"] = _rank(ap, 1000)
    F["vol.atr_tod"] = atr / np.maximum(_tod(atr, mod), 1e-9)
    r1 = np.zeros(n)
    r1[1:] = np.diff(lc)
    rv = pd.Series(r1).rolling(96).std().to_numpy()
    F["vol.rv96"] = rv * 100.0
    F["vol.rv_ratio"] = rv / np.maximum(pd.Series(r1).rolling(480).std().to_numpy(), 1e-12)
    F["vol.rv_tod"] = np.abs(r1) / np.maximum(_tod(np.abs(r1), mod), 1e-9)
    with np.errstate(all="ignore"):
        pk = np.sqrt(pd.Series((np.log(h / np.maximum(l, 1e-12)) ** 2)
                               / (4 * np.log(2))).rolling(48).mean().to_numpy())
        gk = np.sqrt(pd.Series(0.5 * np.log(h / np.maximum(l, 1e-12)) ** 2
                               - (2 * np.log(2) - 1) * np.log(c / np.maximum(o, 1e-12)) ** 2
                               ).rolling(48).mean().to_numpy())
    F["vol.parkinson"] = pk * 100.0
    F["vol.garman_klass"] = np.nan_to_num(gk, nan=np.nan) * 100.0
    F["vol.vol_of_vol"] = pd.Series(rv).rolling(96).std().to_numpy() / np.maximum(rv, 1e-12)
    F["vol.range_tod"] = (h - l) / np.maximum(_tod(h - l, mod), 1e-9)

    # ---------------- hmm  (FILTERED only)
    x = hmm_obs(c)
    filt = H.posterior_filtered(x, hp["pi"], hp["A"], hp["mu"], hp["var"])[:, hp["order"]]
    F["hmm.bear"], F["hmm.side"], F["hmm.bull"] = filt[:, 0], filt[:, 1], filt[:, 2]
    F["hmm.edge"] = filt[:, 2] - filt[:, 0]
    F["hmm.conf"] = filt.max(axis=1)
    with np.errstate(all="ignore"):
        F["hmm.entropy"] = -np.sum(filt * np.log(np.maximum(filt, 1e-12)), axis=1)
    lab = filt.argmax(axis=1)
    F["hmm.sojourn"] = np.log1p(_sojourn(lab))
    A = hp["A"][np.ix_(hp["order"], hp["order"])]
    F["hmm.fwd12"] = (filt @ np.linalg.matrix_power(A, 12))[:, 2] - \
                     (filt @ np.linalg.matrix_power(A, 12))[:, 0]

    # ---------------- ffd
    fd, Lw = ffd(lc, d)
    F["ffd.price"] = fd
    F["ffd.z250"] = (fd - pd.Series(fd).rolling(250).mean().to_numpy()) / np.maximum(
        pd.Series(fd).rolling(250).std().to_numpy(), 1e-12)
    F["ffd.z1000"] = (fd - pd.Series(fd).rolling(1000).mean().to_numpy()) / np.maximum(
        pd.Series(fd).rolling(1000).std().to_numpy(), 1e-12)
    fdr, _ = ffd(np.log(np.maximum(h - l, 1e-6)), d)
    F["ffd.range"] = fdr

    # ---------------- str
    hi20 = pd.Series(h).rolling(20).max().shift(1).to_numpy()
    lo20 = pd.Series(l).rolling(20).min().shift(1).to_numpy()
    F["str.excess"] = (c - hi20) / np.maximum(atr, 1e-12)
    F["str.ch_width"] = (hi20 - lo20) / np.maximum(atr, 1e-12)
    F["str.pos_in_ch"] = (c - lo20) / np.maximum(hi20 - lo20, 1e-12)
    F["str.close_pos"] = (c - l) / np.maximum(h - l, 1e-12)
    F["str.body"] = np.abs(c - o) / np.maximum(atr, 1e-12)
    F["str.upper_wick"] = (h - np.maximum(o, c)) / np.maximum(h - l, 1e-12)
    F["str.range_atr"] = (h - l) / np.maximum(atr, 1e-12)
    F["str.gap_open"] = (o - np.concatenate(([c[0]], c[:-1]))) / np.maximum(atr, 1e-12)
    hi55 = pd.Series(h).rolling(55).max().shift(1).to_numpy()
    F["str.d_hi55"] = (c - hi55) / np.maximum(atr, 1e-12)
    lo96 = pd.Series(l).rolling(96).min().to_numpy()
    hi96 = pd.Series(h).rolling(96).max().to_numpy()
    F["str.pos96"] = (c - lo96) / np.maximum(hi96 - lo96, 1e-12)
    F["str.chop14"] = _chop(h, l, c, 14)
    F["str.chop48"] = _chop(h, l, c, 48)

    # ---------------- mom
    for k in (4, 16, 48, 192):
        F[f"mom.roc{k}"] = (c - np.concatenate((np.full(k, np.nan), c[:-k]))) / np.maximum(atr, 1e-12)
    F["mom.rsi14"] = _rsi(c, 14)
    F["mom.rsi48"] = _rsi(c, 48)
    e12, e26 = _ema(c, 12), _ema(c, 26)
    F["mom.macd_hist"] = (e12 - e26 - _ema(e12 - e26, 9)) / np.maximum(atr, 1e-12)
    pdi, ndi = _dmi(h, l, c, 14)
    F["mom.di_diff"] = pdi - ndi
    F["mom.er20"] = _er(c, 20)
    F["mom.er60"] = _er(c, 60)
    up = (c > o).astype(float)
    F["mom.up_share20"] = pd.Series(up).rolling(20).mean().to_numpy()
    e50, e200 = _ema(c, 50), _ema(c, 200)
    F["mom.d_ema200"] = (c - e200) / np.maximum(atr, 1e-12)
    F["mom.d_ema50"] = (c - e50) / np.maximum(atr, 1e-12)

    # ---------------- par
    F["par.vs_tod"] = v / np.maximum(_tod(v, mod), 1e-9)
    F["par.z_tod"] = np.log1p(np.maximum(v, 0)) - np.log1p(np.maximum(_tod(v, mod), 0))
    F["par.trend20"] = (pd.Series(v).rolling(20).mean().to_numpy()
                        / np.maximum(pd.Series(v).rolling(100).mean().to_numpy(), 1e-9))
    upv = np.where(c > o, v, 0.0)
    F["par.up_share20"] = pd.Series(upv).rolling(20).sum().to_numpy() / np.maximum(
        pd.Series(v).rolling(20).sum().to_numpy(), 1e-9)
    F["par.per_range"] = v / np.maximum(_tod(v, mod), 1e-9) / np.maximum(
        (h - l) / np.maximum(_tod(h - l, mod), 1e-9), 1e-9)

    # ---------------- ctx  (declared separately; a fixed window makes this near-categorical)
    F["ctx.mins_in_win"] = (mod - 420).astype(float)
    F["ctx.dow"] = f.index.dayofweek.to_numpy().astype(float)

    X = pd.DataFrame(F, index=f.index).replace([np.inf, -np.inf], np.nan)
    smoo = None
    if want_smoothed:
        smoo = H.posterior_smoothed(x, hp["pi"], hp["A"], hp["mu"], hp["var"])[:, hp["order"]]
    return X, dict(d=d, d_table=dtab, ffd_window=Lw, hmm=hp, filt=filt, smoothed=smoo)


FAMILIES = ("vol", "hmm", "ffd", "str", "mom", "par", "ctx")


def fam(col):
    return col.split(".")[0]
