"""The PIN mixture as a FEATURE FAMILY -- `pin.*` -- causal, and never able to fire a trade.

`STUDY_PIN_BAYES` established what the Bayesian PIN actually measures on an index future: the
DISPERSION of the buy and sell series, not information. The placebo is unambiguous -- PIN 0.107 and
0.149 on negative-binomial data with B and S drawn independently at var/mean 10 and 20, against NQ's
measured 0.155 at var/mean 14.7-18.9.

That verdict kills it as a primary and does NOT decide the question here, because a dispersion
statistic can still be a useful CONDITIONING variable. Overdispersion in signed flow is a real
property of a bar; whether it says anything about the outcome of a breakout entered on that bar is
a separate measurement. So the family carries both readings deliberately:

    pin.pin, pin.alpha, pin.delta, pin.mu, pin.ratio   the fitted mixture
    pin.pin_sd, pin.ci_w                               the posterior's own uncertainty, which is
                                                       the paper's contribution and which an MLE
                                                       cannot supply at all
    pin.pg, pin.pb, pin.pnone, pin.entropy             the latent-state posterior at this bar
    pin.dispB, pin.dispS                               var/mean of B and S in the fit window --
                                                       the thing PIN was shown to be tracking,
                                                       stated openly so a model can prefer it
    pin.imb                                            the plain signed imbalance, as the control:
                                                       if the mixture adds nothing over this, the
                                                       whole apparatus is decoration

EVERY VALUE AT BAR i IS FITTED ON SESSIONS STRICTLY BEFORE bar i's SESSION. The rolling window
closes at the previous session's close, so no bar reads its own day, and the truncation audit in
`run_d2` checks that rather than trusting it.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/pin", "research/scalp5"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

import pin_bayes as PB      # noqa: E402

COLS = ["pin.pin", "pin.alpha", "pin.delta", "pin.mu", "pin.ratio", "pin.pin_sd", "pin.ci_w",
        "pin.pg", "pin.pb", "pin.pnone", "pin.entropy", "pin.dispB", "pin.dispS", "pin.imb"]


def _bs_1m(path=None):
    """B and S from one-minute bars, volume-weighted by an EXPANDING mean so nothing is
    full-sample. The B/S proxy is named a proxy everywhere: no feed here carries quotes or
    aggressor tags, so a minute is signed by its own direction (EKOP footnote 7 counts trades and
    ignores size, so a count is the faithful unit; the volume weighting is what makes the mixture
    identifiable at all -- STUDY_PIN)."""
    import s5data as S
    b = S.load_1m() if path is None else S.load_1m(path)
    c, o = b["close"].to_numpy(), b["open"].to_numpy()
    v = b["volume"].to_numpy().astype(float)
    cs, cn = np.cumsum(v), np.arange(1, len(v) + 1, dtype=float)
    vbar = np.concatenate([[np.nan], (cs[:-1] / cn[:-1])])
    with np.errstate(invalid="ignore", divide="ignore"):
        w = np.where(np.isfinite(vbar) & (vbar > 0), v / vbar, np.nan)
    up, dn = c > o, c < o
    return b.index, np.where(up, w, 0.0), np.where(dn, w, 0.0), b


def build(D, window=120, sweeps=700, burn=250, seed=0):
    """One fit per session on the previous `window` sessions; then per-bar latent-state posteriors.

    Returns a DataFrame aligned to D['ix'] with the `pin.*` columns, all NaN before the window
    fills. The heavy part is one Gibbs run per session, not per bar.
    """
    ix1, bw, sw, b1 = _bs_1m()
    on1 = np.isfinite(bw) & np.isfinite(sw)
    # sess_core labels a session YYYYMMDD as an int; use ITS convention, not a second one. The
    # first draft used epoch-days here, the two never joined, and every pin.* value came out NaN --
    # which reads downstream as "no signal", not as an error (the recursive-indicator trap in
    # STUDY_V54, reached through a different door).
    day1 = (ix1.year * 10000 + ix1.month * 100 + ix1.day).to_numpy()
    f = pd.DataFrame({"b": np.where(on1, bw, 0.0), "s": np.where(on1, sw, 0.0), "d": day1},
                     index=ix1)
    agg = f[on1].groupby("d").agg(B=("b", "sum"), S=("s", "sum")).sort_index()
    days = agg.index.to_numpy()
    Bd, Sd = agg.B.to_numpy(), agg.S.to_numpy()

    fits = {}
    for i in range(len(days)):
        lo = max(0, i - window)
        if i - lo < 30:
            fits[int(days[i])] = None
            continue
        Bw, Sw = np.rint(Bd[lo:i]), np.rint(Sd[lo:i])
        fit = PB.gibbs(Bw, Sw, sweeps=sweeps, burn=burn, seed=seed + i)
        if fit is None:
            fits[int(days[i])] = None
            continue
        fits[int(days[i])] = dict(
            a=fit["a"], d=fit["d"], mu=fit["mu"], lb=fit["lb"], ls=fit["ls"],
            pin=fit["pin"], pin_sd=fit["pin_sd"], ci_w=fit["pin_hi"] - fit["pin_lo"],
            ratio=fit["ratio"],
            dispB=float(Bw.var(ddof=1) / max(Bw.mean(), 1e-9)),
            dispS=float(Sw.var(ddof=1) / max(Sw.mean(), 1e-9)))

    # running within-session flow on the chart's own grid
    cb = f.groupby("d").b.cumsum(); cs_ = f.groupby("d").s.cumsum()
    Bt = cb.reindex(D["ix"], method="ffill").to_numpy()
    St = cs_.reindex(D["ix"], method="ffill").to_numpy()
    mod = D["mod"]
    n = len(D["c"])
    out = {c: np.full(n, np.nan) for c in COLS}
    lo_m, hi_m = 570, 960
    for i in range(n):
        p = fits.get(int(D["day"][i]))
        if p is None or not np.isfinite(Bt[i]):
            continue
        fr = min(max((mod[i] - lo_m) / (hi_m - lo_m), 1e-3), 1.0)
        g, bb, nn = PB.posterior_state(Bt[i], St[i], p, fr)
        e = -(g * np.log(max(g, 1e-12)) + bb * np.log(max(bb, 1e-12))
              + nn * np.log(max(nn, 1e-12)))
        out["pin.pin"][i] = p["pin"]; out["pin.alpha"][i] = p["a"]
        out["pin.delta"][i] = p["d"]; out["pin.mu"][i] = p["mu"]
        out["pin.ratio"][i] = p["ratio"]; out["pin.pin_sd"][i] = p["pin_sd"]
        out["pin.ci_w"][i] = p["ci_w"]; out["pin.dispB"][i] = p["dispB"]
        out["pin.dispS"][i] = p["dispS"]
        out["pin.pg"][i] = g; out["pin.pb"][i] = bb; out["pin.pnone"][i] = nn
        out["pin.entropy"][i] = e
        out["pin.imb"][i] = (Bt[i] - St[i]) / max(Bt[i] + St[i], 1e-9)
    return pd.DataFrame(out, index=range(n))
