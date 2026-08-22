"""Can a model trade break-of-structure and smart-money concepts intraday?

Design, and why each piece is there:

  LABELS      triple-barrier (Lopez de Prado). For each bar, place a target and a stop at +/- k*ATR
              and a time limit. The label is which barrier is hit first. This is the right label for
              a scalp because it is the trade — a raw forward return would reward moves the stop
              would never have survived.
  FEATURES    the SMC set from smc.py, all causal.
  VALIDATION  purged + embargoed K-fold, because triple-barrier labels OVERLAP: a bar's outcome is
              determined over the following minutes, which are also other bars' features. Plain CV
              leaks badly here.
  HOLDOUT     the last 20% of bars, evaluated once at the end.
  CONTROLS    three, all necessary:
                1. a SHUFFLED-LABEL model — must score ~0.5, or the pipeline itself leaks
                2. the take-everything baseline — a filter that cannot beat it has added nothing
                3. costs charged on every trade, and results reported in DOLLARS

Usage: python3 research/smc_ml.py
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd
from numba import njit
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

sys.path.insert(0, "research")
import smc
from nqdata import load_bars, minute_of_day, minutes_since_open, session_index, session_slice
from purged_cv import PurgedKFold

POINT_VALUE = 20.0          # NQ
ROUND_TURN_PTS = 0.95       # 1 tick spread + 1 tick slippage per side + $4 commission
RTH_START, RTH_END = 570, 960


@njit(cache=True)
def triple_barrier(h, l, c, sess, atr, mult, max_bars):
    """First-touch labelling. Returns (label, R outcome, exit bar) for a LONG at each bar's close.

    A bar that would run past the session end is closed at the last bar of its session, which is
    what a scalper actually does — nothing is carried overnight.
    """
    n = c.shape[0]
    lab = np.zeros(n, np.int8)
    rr = np.full(n, np.nan)
    xb = np.full(n, -1, np.int64)
    for i in range(n):
        a = atr[i]
        if not (a > 0):
            continue
        entry = c[i]
        up = entry + mult * a
        dn = entry - mult * a
        risk = mult * a
        end = min(i + max_bars, n - 1)
        j = i + 1
        done = False
        while j <= end and sess[j] == sess[i]:
            if l[j] <= dn:
                lab[i] = -1; rr[i] = -1.0; xb[i] = j; done = True; break
            if h[j] >= up:
                lab[i] = 1; rr[i] = 1.0; xb[i] = j; done = True; break
            j += 1
        if not done:
            k = j - 1
            if k > i:
                lab[i] = 1 if c[k] > entry else -1
                rr[i] = (c[k] - entry) / risk
                xb[i] = k
    return lab, rr, xb


def build(mult=1.0, max_bars=60, pivot_k=3, atr_len=30):
    seg = session_slice(load_bars("data/NQ_1m.csv"), RTH_START, RTH_END)
    o = seg["open"].to_numpy(float); h = seg["high"].to_numpy(float)
    l = seg["low"].to_numpy(float);  c = seg["close"].to_numpy(float)
    v = seg["volume"].to_numpy(float)
    sess = session_index(seg.index, RTH_START)
    mso = minutes_since_open(minute_of_day(seg.index), RTH_START).astype(np.int64)

    atr = smc.atr_series(h, l, c, atr_len)
    ph, pl, phi, pli = smc.swing_pivots(h, l, pivot_k)
    bos, choch, bias, sbos, schoch = smc.structure(c, ph, pl)
    dup, sup, ddn, sdn = smc.fair_value_gaps(h, l, atr)
    sweep, ssweep = smc.liquidity_sweeps(h, l, c, ph, pl)
    pos = smc.dealing_range(c, ph, pl)
    obd = smc.order_block_distance(o, c, h, l, bos, atr)

    lab, rr, xb = triple_barrier(h, l, c, sess, atr, mult, max_bars)

    X = pd.DataFrame({
        "bias": bias,
        "bos": bos,
        "choch": choch,
        "since_bos": np.minimum(sbos, 500),
        "since_choch": np.minimum(schoch, 500),
        "sweep": sweep,
        "since_sweep": np.minimum(ssweep, 500),
        "range_pos": np.where(np.isfinite(pos), pos, 0.5),
        # "no live gap" is information, not missing data. Encoding it as NaN and dropping the row
        # silently filtered 98% of the sample on the first attempt — bars only survived when an
        # unfilled gap existed on BOTH sides at once. Presence flag plus a far-away sentinel keeps
        # every bar and lets the model use the absence.
        "fvg_up_live": np.isfinite(dup).astype(float),
        "fvg_dn_live": np.isfinite(ddn).astype(float),
        "fvg_dist_up": np.where(np.isfinite(dup), dup, 99.0),
        "fvg_size_up": np.where(np.isfinite(sup), sup, 0.0),
        "fvg_dist_dn": np.where(np.isfinite(ddn), ddn, 99.0),
        "fvg_size_dn": np.where(np.isfinite(sdn), sdn, 0.0),
        "ob_live": np.isfinite(obd).astype(float),
        "ob_dist": np.where(np.isfinite(obd), obd, 99.0),
        "range_pos_live": np.isfinite(pos).astype(float),
        "atr_rel": atr / c,
        "mso": mso,
        "ret5": np.concatenate([np.full(5, np.nan), (c[5:] - c[:-5]) / atr[5:]]),
        "vol_rel": v / pd.Series(v).rolling(60, min_periods=20).mean().to_numpy(),
    })
    ok = np.isfinite(X.to_numpy()).all(axis=1) & (xb > 0) & np.isfinite(rr)
    return X[ok].reset_index(drop=True), lab[ok], rr[ok], np.arange(len(seg))[ok], xb[ok], atr[ok], seg


def dollars(rr, atr, mult, taken):
    """Convert R outcomes to dollars, charging a full round turn on every trade taken."""
    risk_pts = mult * atr[taken]
    return (rr[taken] * risk_pts - ROUND_TURN_PTS) * POINT_VALUE


def main() -> None:
    MULT, MAXB = 1.0, 60
    X, lab, rr, idx, xb, atr, seg = build(MULT, MAXB)
    n_bars = len(seg)
    lock = int(n_bars * 0.80)
    tr = idx < lock
    ho = idx >= lock
    y = (lab > 0).astype(int)

    print(f"  {len(X):,} labelled bars from {n_bars:,} ({X.shape[1]} SMC features)")
    print(f"  triple barrier: +/-{MULT}xATR(30), {MAXB}-bar limit, session-capped")
    print(f"  train {tr.sum():,}  |  LOCKED holdout {ho.sum():,}")
    print(f"  base rate (up barrier first): {y[tr].mean():.4f}")
    base_pnl = dollars(rr, atr, MULT, np.where(tr)[0])
    print(f"  take-EVERY-bar-long baseline on train: ${base_pnl.sum():,.0f} over {tr.sum():,} trades "
          f"(${base_pnl.mean():.2f}/trade)\n")

    Xtr = X[tr].to_numpy(); ytr = y[tr]
    t0 = idx[tr]; t1 = xb[tr]

    def fit(Xa, ya):
        return GradientBoostingClassifier(n_estimators=120, max_depth=3, learning_rate=0.05,
                                          subsample=0.5, random_state=7).fit(Xa, ya)

    # ---- purged CV, and the same thing on shuffled labels as a leak detector ----
    for tag, yy in (("REAL labels", ytr), ("SHUFFLED labels (control)", np.random.default_rng(0).permutation(ytr))):
        cv = PurgedKFold(n_splits=5, embargo_pct=0.01)
        aucs, edges = [], []
        for a, b in cv.split(t0, t1):
            m = fit(Xtr[a], yy[a])
            p = m.predict_proba(Xtr[b])[:, 1]
            if len(np.unique(yy[b])) > 1:
                aucs.append(roc_auc_score(yy[b], p))
            take = np.where(tr)[0][b][p >= 0.55]
            if len(take) >= 20:
                edges.append(dollars(rr, atr, MULT, take).mean())
        print(f"  {tag:<28} purged-CV AUC {np.nanmean(aucs):.4f}   "
              f"$/trade at p>=0.55: {np.nanmean(edges) if edges else float('nan'):+.2f}")

    # ---- the locked holdout, once ----
    model = fit(Xtr, ytr)
    ph_ = model.predict_proba(X[ho].to_numpy())[:, 1]
    hidx = np.where(ho)[0]
    print(f"\n  LOCKED HOLDOUT ({ho.sum():,} bars), evaluated once")
    print(f"    AUC {roc_auc_score(y[ho], ph_):.4f}")
    print(f"    {'threshold':>10}{'trades':>9}{'$/trade':>11}{'total $':>13}{'win%':>8}")
    allp = dollars(rr, atr, MULT, hidx)
    print(f"    {'take all':>10}{len(hidx):>9}{allp.mean():>11.2f}{allp.sum():>13,.0f}{100*(rr[hidx]>0).mean():>7.1f}%")
    for thr in (0.50, 0.55, 0.60, 0.65):
        k = hidx[ph_ >= thr]
        if len(k) >= 20:
            d = dollars(rr, atr, MULT, k)
            print(f"    {thr:>10.2f}{len(k):>9}{d.mean():>11.2f}{d.sum():>13,.0f}{100*(rr[k]>0).mean():>7.1f}%")
    imp = pd.Series(model.feature_importances_, index=X.columns).sort_values(ascending=False)
    print("\n    top features: " + "  ".join(f"{k} {v:.3f}" for k, v in imp.head(6).items()))
    print(f"\n    NOTE: costs are ${ROUND_TURN_PTS * POINT_VALUE:.2f} per round turn against a median risk of "
          f"${np.median(MULT * atr[hidx]) * POINT_VALUE:,.0f}, i.e. {100 * ROUND_TURN_PTS / np.median(MULT * atr[hidx]):.1f}% of risk per trade.")


if __name__ == "__main__":
    main()
