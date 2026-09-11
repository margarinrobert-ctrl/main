#!/usr/bin/env python3
"""Breakout ML pipeline, self-contained. Runs anywhere with numpy/pandas/scikit-learn/xgboost.

WHAT THIS IS. The same experiment that produced STUDY_V28_ML_CAPACITY, rewritten with NO dependency
on the research/ tree so it runs on your own machine against your own files. Same label, same purged
cross-validation, same shuffled-label null, same selectivity gate.

WHAT IT ANSWERS. Not "what is the best model" -- "does model capacity buy anything on this data".
It runs a ladder from a constant through logistic regression, trees and gradient boosting to a deep
network, on identical folds, and prints each one beside a twin trained on RANDOMLY SHUFFLED labels.
The shuffled score is the floor the pipeline produces from nothing: leakage, class imbalance, fold
luck and the optimisation itself. A result has to clear its own shuffled twin, not 0.5.

USAGE
    python breakout_ml.py --csv PATH [options]
    python breakout_ml.py --csv NQ.csv --tf 30 --stage all

Run `python breakout_ml.py --help` for every option. Start with `--stage inspect` to check the
loader understood your file before spending time on the models.
"""
from __future__ import annotations

import argparse
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ----------------------------------------------------------------------------------- data loading
DATE_CANDS = ["datetime", "date", "time", "timestamp", "date_time", "local time", "gmt time"]
OHLC = {"open": ["open", "o"], "high": ["high", "h"], "low": ["low", "l"],
        "close": ["close", "c", "last"], "volume": ["volume", "vol", "v", "tickvolume"]}


def load_bars(path, tz_shift_hours=0.0):
    """Read almost any bar export. Seven formats have been seen on this project; the differences
    that actually bite are the DELIMITER, the ROW ORDER and the TIMESTAMP FORMAT, so all three are
    detected rather than assumed."""
    with open(path, "r", errors="replace") as f:
        head = f.read(8192)
    delim = max([",", "\t", ";", "|"], key=head.count)
    df = pd.read_csv(path, sep=delim, engine="python")
    df.columns = [str(c).strip() for c in df.columns]
    low = {c.lower().replace(" ", "").replace("_", ""): c for c in df.columns}

    dcol = None
    for cand in DATE_CANDS:
        k = cand.replace(" ", "").replace("_", "")
        if k in low:
            dcol = low[k]
            break
    if dcol is None:                     # unnamed index column, or split date + time
        if len(df.columns) and df.columns[0].lower().startswith("unnamed"):
            dcol = df.columns[0]
        else:
            dcol = df.columns[0]
    ts = pd.to_datetime(df[dcol], errors="coerce", format="mixed", dayfirst=False)
    if ts.isna().mean() > 0.5:
        ts = pd.to_datetime(df[dcol], errors="coerce", dayfirst=True)
    if ts.isna().mean() > 0.5:
        raise SystemExit(f"could not parse timestamps from column '{dcol}'. "
                         f"First values: {list(df[dcol].head(3))}")

    out = {"ts": ts}
    for want, cands in OHLC.items():
        col = next((low[c] for c in cands if c in low), None)
        if col is None and want != "volume":
            raise SystemExit(f"no '{want}' column found. Columns are: {list(df.columns)}")
        out[want] = pd.to_numeric(df[col], errors="coerce") if col else 0.0
    b = pd.DataFrame(out).dropna(subset=["ts", "open", "high", "low", "close"])
    if len(b) > 1 and b.ts.iloc[0] > b.ts.iloc[-1]:
        b = b.iloc[::-1]                                   # delivered newest-first
    b = b.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    if tz_shift_hours:
        b["ts"] = b.ts + pd.Timedelta(hours=tz_shift_hours)
    b["sess"] = b.ts.dt.year * 10000 + b.ts.dt.month * 100 + b.ts.dt.day
    b["mod"] = b.ts.dt.hour * 60 + b.ts.dt.minute
    return b


def resample(b, minutes):
    """Aggregate to a coarser bar. Uses the bar's own spacing, so it works whatever you feed it."""
    if minutes <= 0:
        return b
    step = int(pd.Series(b.ts.diff().dt.total_seconds() / 60).median() or minutes)
    k = max(1, round(minutes / step))
    if k == 1:
        return b
    g = b.groupby(np.arange(len(b)) // k)
    out = pd.DataFrame({
        "ts": g.ts.first(), "open": g.open.first(), "high": g.high.max(),
        "low": g.low.min(), "close": g.close.last(), "volume": g.volume.sum(),
        "sess": g.sess.first(), "mod": g["mod"].first()}).reset_index(drop=True)
    return out


# ------------------------------------------------------------------------------------- indicators
def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False, min_periods=n).mean().to_numpy()


def sma(x, n):
    return pd.Series(x).rolling(n, min_periods=n).mean().to_numpy()


def shift(x, k=1):
    o = np.full(len(x), np.nan)
    if k < len(x):
        o[k:] = np.asarray(x, float)[:-k]
    return o


def true_range(h, l, c):
    pc = shift(c)
    return np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)


def rsi(c, n=14):
    d = np.diff(np.asarray(c, float), prepend=np.nan)
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    return 100 - 100 / (1 + up / np.maximum(dn, 1e-12))


def adx(h, l, c, n=14):
    up, dn = np.diff(h, prepend=np.nan), -np.diff(l, prepend=np.nan)
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.Series(true_range(h, l, c)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    pdi = 100 * pd.Series(pdm).ewm(alpha=1 / n, adjust=False).mean().to_numpy() / np.maximum(tr, 1e-12)
    ndi = 100 * pd.Series(ndm).ewm(alpha=1 / n, adjust=False).mean().to_numpy() / np.maximum(tr, 1e-12)
    dx = 100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-12)
    return pd.Series(dx).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def chop(h, l, c, n=14):
    """Choppiness index. LOW means trending. The one filter that has cleared its control here."""
    s = pd.Series(true_range(h, l, c)).rolling(n, min_periods=n).sum().to_numpy()
    rng = (pd.Series(h).rolling(n, min_periods=n).max().to_numpy()
           - pd.Series(l).rolling(n, min_periods=n).min().to_numpy())
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100 * np.log10(s / np.maximum(rng, 1e-12)) / np.log10(n)


# ------------------------------------------------------------------- the strategy, and the label
def simulate(b, entry_n=30, exit_n=20, atr_len=14, stop_mult=2.0, side=1,
             cost_points=0.72, slip_ticks=2.0, tick=0.25):
    """Donchian breakout with an ATR stop and a channel exit. Returns one row per SIGNAL BAR.

    The exit is the NEARER of the ATR stop and the opposite channel, capped at the previous close
    because a sell stop cannot rest above the market. Entry is a market order at the next bar's
    open. The label is the R-multiple -- P&L over the trade's own stop distance -- which is what
    makes results comparable across instruments and price levels.
    """
    o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(c)
    atr = ema(true_range(h, l, c), atr_len)
    ent_hi = shift(pd.Series(h).rolling(entry_n, min_periods=entry_n).max().to_numpy(), 1)
    ent_lo = shift(pd.Series(l).rolling(entry_n, min_periods=entry_n).min().to_numpy(), 1)
    ex_lo = shift(pd.Series(l).rolling(exit_n, min_periods=exit_n).min().to_numpy(), 1)
    ex_hi = shift(pd.Series(h).rolling(exit_n, min_periods=exit_n).max().to_numpy(), 1)

    if side > 0:
        trig = np.isfinite(ent_hi) & (h > ent_hi)
    else:
        trig = np.isfinite(ent_lo) & (l < ent_lo)
    trig &= np.isfinite(atr) & (atr > 0)
    trig[-3:] = False
    sig = np.flatnonzero(trig)

    cost = cost_points + 2.0 * slip_ticks * tick
    xb = np.full(len(sig), -1, np.int64)
    R = np.full(len(sig), np.nan)
    why = np.zeros(len(sig), np.int64)          # 0 stop, 1 channel
    mae = np.full(len(sig), np.nan)
    mfe = np.full(len(sig), np.nan)
    for k, i in enumerate(sig):
        eb = i + 1
        if eb >= n:
            continue
        px, a = o[eb], atr[i]
        stop = px - side * stop_mult * a
        lo = hi = px
        for j in range(eb, n):
            lo, hi = min(lo, l[j]), max(hi, h[j])
            lvl, w = stop, 0
            ch = ex_lo[j] if side > 0 else ex_hi[j]
            if np.isfinite(ch) and (ch > lvl if side > 0 else ch < lvl):
                lvl, w = ch, 1
            lvl = min(lvl, c[j - 1]) if side > 0 else max(lvl, c[j - 1])
            hit = (l[j] <= lvl) if side > 0 else (h[j] >= lvl)
            if hit:
                xb[k], why[k] = j, w
                R[k] = (side * (lvl - px) - cost) / (stop_mult * a)
                break
        if xb[k] >= 0:
            mae[k] = (px - lo) / a if side > 0 else (hi - px) / a
            mfe[k] = (hi - px) / a if side > 0 else (px - lo) / a
    return dict(sig=sig, xb=xb, R=R, why=why, mae=mae, mfe=mfe, atr=atr,
                ent_hi=ent_hi, ex_lo=ex_lo)


def position_lock(sig, xb, keep):
    """One trade at a time, in order. A signal on or before the previous exit bar is skipped --
    without this a backtest silently holds a dozen overlapping positions."""
    out, last = [], -1
    for k in range(len(sig)):
        if not keep[k] or xb[k] < 0 or sig[k] <= last:
            continue
        out.append(k)
        last = xb[k]
    return np.array(out, np.int64)


def stats(R, idx):
    if len(idx) < 5:
        return None
    r = np.asarray(R)[idx]
    r = r[np.isfinite(r)]
    if len(r) < 5 or not (r < 0).any():
        return None
    eq = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    return dict(n=len(r), R=float(r.mean()), pf=float(r[r > 0].sum() / abs(r[r < 0].sum())),
                win=float((r > 0).mean()), dd=dd, retdd=float(r.sum() / dd) if dd > 0 else np.nan,
                p90=float(np.quantile(r, 0.9)))


# ------------------------------------------------------------------------------------- features
def features(b, S):
    """Causal columns at the SIGNAL bar. Nothing here reads a bar later than the one it labels.

    Volatility state dominates the set deliberately: it is the axis that has produced the only
    non-flat results on this data. `pct` columns are a value's rank inside its own trailing window,
    which is scale-free and comparable across instruments.
    """
    o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    atr = S["atr"]
    lr = np.r_[np.nan, np.diff(np.log(np.maximum(c, 1e-12)))]
    f = {}
    for n in (5, 10, 20, 60, 120):
        cc = np.sqrt(pd.Series(lr ** 2).rolling(n, min_periods=n).mean().to_numpy())
        hl = np.log(np.maximum(h, 1e-12) / np.maximum(l, 1e-12))
        park = np.sqrt(pd.Series(hl ** 2).rolling(n, min_periods=n).mean().to_numpy()
                       / (4 * np.log(2)))
        f[f"cc{n}"] = cc
        f[f"park{n}"] = park
        f[f"park_cc{n}"] = park / np.maximum(cc, 1e-12)      # >1 means oscillating inside bars
        f[f"ret{n}"] = c / np.maximum(shift(c, n), 1e-12) - 1
        f[f"tsmom{n}"] = f[f"ret{n}"] / np.maximum(
            pd.Series(lr).rolling(n, min_periods=n).std().to_numpy() * np.sqrt(n), 1e-12)
        for w in (250, 500):
            f[f"cc{n}_pct{w}"] = pd.Series(cc).rolling(w, min_periods=w).rank(pct=True).to_numpy()
    for a, bq in ((5, 20), (10, 60), (20, 120)):
        f[f"ts_{a}_{bq}"] = (pd.Series(lr ** 2).rolling(a, min_periods=a).mean().to_numpy()
                             / np.maximum(pd.Series(lr ** 2).rolling(bq, min_periods=bq)
                                          .mean().to_numpy(), 1e-18))
    for n in (14, 28):
        f[f"chop{n}"] = chop(h, l, c, n)
        f[f"rsi{n}"] = rsi(c, n)
    f["adx14"] = adx(h, l, c, 14)
    for n in (20, 50, 200):
        f[f"ema_dist{n}"] = (c - ema(c, n)) / np.maximum(atr, 1e-12)
    f["atr_pct500"] = pd.Series(atr).rolling(500, min_periods=500).rank(pct=True).to_numpy()
    f["atr_price"] = atr / np.maximum(c, 1e-12)
    f["bar_pos"] = (c - l) / np.maximum(h - l, 1e-12)
    f["ext_entry"] = (h - S["ent_hi"]) / np.maximum(atr, 1e-12)
    f["chan_w"] = (S["ent_hi"] - S["ex_lo"]) / np.maximum(atr, 1e-12)
    f["mod"] = b["mod"].to_numpy(float)
    f["dow"] = b.ts.dt.dayofweek.to_numpy().astype(float)
    X = pd.DataFrame({k: v[S["sig"]] for k, v in f.items()})
    ok = np.isfinite(X.to_numpy()).all(axis=1) & (S["xb"] >= 0) & np.isfinite(S["R"])
    return X[ok].reset_index(drop=True), ok


def purged_folds(sig, xb, n_folds=6, embargo=50):
    """Contiguous test folds. Any training trade whose [signal, exit] window overlaps a test
    interval -- or sits within `embargo` bars of one -- is DROPPED. Without this the model trains
    on the same price path it is later tested on, and every score is inflated."""
    n = len(sig)
    edges = np.linspace(0, n, n_folds + 1).astype(int)
    for i in range(n_folds):
        te = np.zeros(n, bool)
        te[edges[i]:edges[i + 1]] = True
        t0, t1 = sig[te].min(), xb[te].max()
        overlap = (xb >= t0 - embargo) & (sig <= t1 + embargo)
        tr = (~te) & (~overlap)
        if tr.sum() > 200 and te.sum() > 50:
            yield np.flatnonzero(tr), np.flatnonzero(te)


# ------------------------------------------------------------------------------------ the models
def build_models(deep=True):
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier
    m = [("constant (no model)", None),
         ("logistic regression", LogisticRegression(max_iter=2000, C=0.1)),
         ("random forest 300", RandomForestClassifier(n_estimators=300, min_samples_leaf=20,
                                                      n_jobs=-1, random_state=0))]
    try:
        import xgboost as xgb
        for name, d, ne in (("XGBoost 300 d3 (shallow)", 3, 300), ("XGBoost 600 d6", 6, 600),
                            ("XGBoost 1200 d10 (deep)", 10, 1200)):
            m.append((name, xgb.XGBClassifier(n_estimators=ne, max_depth=d, learning_rate=0.05,
                                              subsample=0.8, colsample_bytree=0.6,
                                              min_child_weight=20, reg_lambda=1.0, random_state=0,
                                              n_jobs=-1, tree_method="hist",
                                              eval_metric="logloss")))
    except ImportError:
        print("   (xgboost not installed -- skipping those rows; pip install xgboost)")
    try:
        import lightgbm as lgb
        m.insert(3, ("LightGBM 400", lgb.LGBMClassifier(n_estimators=400, learning_rate=0.03,
                                                        num_leaves=15, min_child_samples=40,
                                                        subsample=0.8, colsample_bytree=0.6,
                                                        random_state=0, verbose=-1)))
    except ImportError:
        pass
    if deep:
        try:
            from sklearn.neural_network import MLPClassifier
            for name, hl in (("MLP 2x64 (shallow)", (64, 64)),
                             ("MLP 4x128 (deep)", (128,) * 4),
                             ("MLP 6x256 (deeper)", (256,) * 6)):
                m.append((name, MLPClassifier(hidden_layer_sizes=hl, alpha=1e-3, max_iter=300,
                                              early_stopping=True, random_state=0)))
        except ImportError:
            pass
    return m


def fit_predict(model, Xtr, ytr, Xte):
    from sklearn.base import clone
    if model is None:
        return np.full(len(Xte), 0.5)
    m = clone(model)
    m.fit(Xtr, ytr)
    return m.predict_proba(Xte)[:, 1]


def ladder(X, R, sig, xb, folds=6, shuffle=False, seed=0, deep=True):
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score
    from scipy.stats import spearmanr
    Xv = X.to_numpy(float)
    y = (R > 0).astype(int)
    if shuffle:
        y = np.random.default_rng(seed).permutation(y)
    rows = []
    for name, model in build_models(deep):
        P, T, RR = [], [], []
        for tr, te in purged_folds(sig, xb, folds):
            sc = StandardScaler().fit(Xv[tr])
            P.append(fit_predict(model, sc.transform(Xv[tr]), y[tr], sc.transform(Xv[te])))
            T.append(y[te])
            RR.append(R[te])
        if not P:
            continue
        p, t, r = np.concatenate(P), np.concatenate(T), np.concatenate(RR)
        rows.append(dict(model=name,
                         auc=roc_auc_score(t, p) if len(np.unique(t)) > 1 else np.nan,
                         ic=spearmanr(p, r).statistic if len(np.unique(p)) > 1 else 0.0,
                         r_all=r.mean(), r_top50=r[p >= np.median(p)].mean(),
                         r_top10=r[p >= np.quantile(p, 0.9)].mean(), n=len(r)))
    return pd.DataFrame(rows)


def locked_gate(X, R, sig, xb, frac=0.65, draws=400, seed=41, deep=True):
    """Train on the first `frac` of trades, read the rest ONCE, and gate on a random half."""
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score
    Xv = X.to_numpy(float)
    y = (R > 0).astype(int)
    cut = int(len(R) * frac)
    tr = np.arange(len(R)) < cut
    lk = ~tr
    rl = R[lk]
    rng = np.random.default_rng(seed)
    k = int(lk.sum()) // 2
    ctrl = np.array([rl[rng.choice(len(rl), k, replace=False)].mean() for _ in range(draws)])
    rows = []
    for name, model in build_models(deep):
        if model is None:
            continue
        sc = StandardScaler().fit(Xv[tr])
        p = fit_predict(model, sc.transform(Xv[tr]), y[tr], sc.transform(Xv[lk]))
        sel = p >= np.median(p)
        r = float(rl[sel].mean())
        rows.append(dict(model=name, n_all=int(lk.sum()), r_all=float(rl.mean()),
                         n_sel=int(sel.sum()), r_sel=r, delta=r - float(rl.mean()),
                         ctrl=float(ctrl.mean()), excess=r - float(ctrl.mean()),
                         p=float((ctrl >= r).mean()),
                         auc=roc_auc_score(y[lk], p) if len(np.unique(y[lk])) > 1 else np.nan,
                         win_all=float(y[lk].mean()), win_sel=float(y[lk][sel].mean()),
                         p90_all=float(np.quantile(rl, .9)), p90_sel=float(np.quantile(rl[sel], .9))))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------- CLI
def hdr(t):
    print("\n" + "=" * 104 + f"\n{t}\n" + "=" * 104)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True, help="bar file: OHLC(V) with a timestamp column")
    ap.add_argument("--tf", type=int, default=30, help="resample to this many minutes (0 = as-is)")
    ap.add_argument("--tz-shift", type=float, default=0.0,
                    help="hours to add to timestamps to reach your session clock")
    ap.add_argument("--stage", default="all",
                    choices=["inspect", "baseline", "ladder", "locked", "all"])
    ap.add_argument("--side", type=int, default=1, choices=[1, -1])
    ap.add_argument("--entry", type=int, default=30)
    ap.add_argument("--exit", type=int, default=20)
    ap.add_argument("--stop", type=float, default=2.0, help="ATR multiple")
    ap.add_argument("--chop-max", type=float, default=0.0,
                    help="gate on CHOP(14) <= this (0 = off; 40 is the shipped value)")
    ap.add_argument("--cost-points", type=float, default=0.72,
                    help="round-turn fees in POINTS of the instrument (MNQ discount = 0.72)")
    ap.add_argument("--slip-ticks", type=float, default=2.0)
    ap.add_argument("--tick", type=float, default=0.25)
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--no-deep", action="store_true", help="skip the neural nets (much faster)")
    ap.add_argument("--out", default="", help="write per-trade rows to this CSV")
    a = ap.parse_args()

    b = load_bars(a.csv, a.tz_shift)
    b = resample(b, a.tf)
    step = float(pd.Series(b.ts.diff().dt.total_seconds() / 60).median())
    hdr("DATA")
    print(f"   {len(b):,} bars   {b.ts.iloc[0]}  ->  {b.ts.iloc[-1]}   median spacing {step:.0f} min")
    print(f"   close range {b.close.min():,.2f} to {b.close.max():,.2f}"
          f"   sessions {b.sess.nunique():,}")
    if a.stage == "inspect":
        print("\n   First three rows as parsed:")
        print(b.head(3).to_string(index=False))
        print("\n   If the timestamps, order or prices look wrong, fix them before going further:")
        print("   --tz-shift moves the clock; the loader auto-detects delimiter and row order.")
        return

    S = simulate(b, a.entry, a.exit, 14, a.stop, a.side, a.cost_points, a.slip_ticks, a.tick)
    X, ok = features(b, S)
    sig, xb, R = S["sig"][ok], S["xb"][ok], S["R"][ok]
    keep = np.ones(len(sig), bool)
    if a.chop_max > 0:
        keep = chop(b.high.to_numpy(), b.low.to_numpy(), b.close.to_numpy(), 14)[sig] <= a.chop_max
    X, sig, xb, R = X[keep].reset_index(drop=True), sig[keep], xb[keep], R[keep]
    if a.out:
        pd.DataFrame({"ts": b.ts.to_numpy()[sig], "R": R, "exit_bar": xb}).assign(
            **{c: X[c].to_numpy() for c in X.columns}).to_csv(a.out, index=False)
        print(f"   wrote {len(R):,} trade rows to {a.out}")

    hdr("BASELINE -- taking every breakout the rule gives")
    idx = position_lock(sig, xb, np.ones(len(sig), bool))
    st = stats(R, idx)
    print(f"   signals {len(R):,}   after the position lock {len(idx):,}"
          f"   CHOP gate {'off' if a.chop_max <= 0 else f'<= {a.chop_max:g}'}")
    if st:
        print(f"   R/trade {st['R']:+.4f}   PF {st['pf']:.3f}   win {st['win']:.1%}"
              f"   maxDD {st['dd']:.1f} R   ret/DD {st['retdd']:.2f}   p90 R {st['p90']:+.3f}")
    print(f"   cost charged: {a.cost_points:.2f} pts fees + {2*a.slip_ticks:.0f} ticks slippage"
          f" = {a.cost_points + 2*a.slip_ticks*a.tick:.2f} points per round turn")
    if a.stage == "baseline":
        return

    if a.stage in ("ladder", "all"):
        hdr("THE CAPACITY LADDER -- purged folds, and every model beside its SHUFFLED-LABEL twin")
        print("   A model is only worth its complexity if it beats taking every signal AND beats")
        print("   its own shuffled twin. The twin is the floor this pipeline produces from noise.\n")
        real = ladder(X, R, sig, xb, a.folds, False, deep=not a.no_deep)
        shuf = ladder(X, R, sig, xb, a.folds, True, 11, deep=not a.no_deep)
        m = real.merge(shuf[["model", "auc", "r_top10"]], on="model", suffixes=("", "_shuf"))
        print(f"   {'model':<26}{'AUC':>8}{'IC':>8}{'R top50':>10}{'R top10':>10}"
              f"{'|':>3}{'AUC shuf':>10}{'R top10 shuf':>14}")
        for _, r in m.iterrows():
            print(f"   {r.model:<26}{r.auc:>8.4f}{r.ic:>+8.4f}{r.r_top50:>+10.4f}"
                  f"{r.r_top10:>+10.4f}{'|':>3}{r.auc_shuf:>10.4f}{r.r_top10_shuf:>+14.4f}")
        print(f"\n   Taking every signal earns {real.r_all.iloc[0]:+.4f} R.")
        d = m[m.model != "constant (no model)"]
        print(f"   AUC spread across the ladder: {d.auc.max()-d.auc.min():.4f}"
              f"   best {d.loc[d.auc.idxmax(),'model']} at {d.auc.max():.4f}")

    if a.stage in ("locked", "all"):
        hdr("THE LOCKED READ AND THE SELECTIVITY GATE -- trained on the first 65%, read once")
        print("   `p` is the share of 400 RANDOM halves of the same size that did better. A model")
        print("   keeping half the signals is a restrictive filter, and restrictiveness alone")
        print("   moves mean R -- so beating a random half is the only honest bar.\n")
        L = locked_gate(X, R, sig, xb, deep=not a.no_deep)
        print(f"   {'model':<26}{'n all':>7}{'R all':>9}{'R sel':>9}{'delta':>9}"
              f"{'excess':>9}{'p':>7}{'AUC':>8}")
        for _, r in L.iterrows():
            print(f"   {r.model:<26}{int(r.n_all):>7}{r.r_all:>+9.4f}{r.r_sel:>+9.4f}"
                  f"{r.delta:>+9.4f}{r.excess:>+9.4f}{r.p:>7.3f}{r.auc:>8.4f}")
        hdr("   THE TAIL -- why a better win-rate classifier can still lose money")
        print(f"   {'model':<26}{'win% all':>10}{'win% sel':>10}{'p90 R all':>12}{'p90 R sel':>12}")
        for _, r in L.iterrows():
            print(f"   {r.model:<26}{r.win_all:>10.1%}{r.win_sel:>10.1%}"
                  f"{r.p90_all:>+12.3f}{r.p90_sel:>+12.3f}")
        print("\n   If win% rises while p90 R falls, the model bought its win rate by discarding")
        print("   the big winners -- and a breakout system earns in the tail.")


if __name__ == "__main__":
    main()
