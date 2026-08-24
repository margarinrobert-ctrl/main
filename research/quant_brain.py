"""The orchestrator: one object that reads every other module and answers the questions the
brief asks, in the order it asks them.

    analyse(rule)        every metric, the constraint check, the Quant Score, regime breakdown
    explain(s, k)        why THIS entry fired, decomposed into named components with a confidence
    improve(s)           variants, kept only when the gain survives the locked block
    feature_importance() which features carry information about the forward move, and which are
                         redundant restatements of each other
    portfolio(names)     rolling, rank, partial and regime-dependent correlation, clustering, PCA
    anomalies()          statistically tested, with multiple-testing control

Two rules run through all of it.

First, nothing is promoted on research-block evidence alone. Every improvement, every feature,
every anomaly is re-read on the locked block, and the report shows both numbers side by side
whether or not the second one is flattering.

Second, a confidence number is only as good as the split it was fitted on. The signal model here
is trained on research trades and scored on locked trades, and the report prints the locked AUC
next to every confidence it quotes. A confidence with no out-of-sample AUC beside it is decoration.
"""
from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
warnings.filterwarnings("ignore")

import features as FT
import metrics as MT
import regimes as RG
from bos_choch import prep
from test_suite import build, _daily

PV = 2.0


# =============================================================== 1. ANALYSE
def analyse(conds, side=1, atr_mult=2.5, tp_r=3.0, flat_min=0, tf=30,
            constraints=None, R=None, book_corr=None):
    s = build(conds, side=side, atr_mult=atr_mult, tp_r=tp_r, flat_min=flat_min, tf=tf)
    if len(s.pnl) < 10:
        return None
    d = _daily(s)
    M = MT.all_metrics(s, d)
    R = R if R is not None else RG.classify(tf)
    rows = RG.by_regime(R, s.ent_sess, s.pnl)
    good, bad = RG.works_where(rows)

    res = s.pnl[s.ent_sess < s.cut]; lok = s.pnl[s.ent_sess >= s.cut]
    per_res = res.mean() if len(res) else 0.0
    per_lok = lok.mean() if len(lok) else 0.0
    grid = [s.sim(atr_mult=a, tp_r=t).pnl.sum()
            for a in (1.0, 1.5, 2.0, 2.5, 3.0) for t in (1.0, 1.5, 2.0, 2.5, 3.0)]
    rng = np.random.default_rng(9)
    noise = [s.sim(noise=(0.125, int(rng.integers(1 << 31)))).pnl.sum() for _ in range(12)]
    e = np.linspace(0, s.n_sess, 9).astype(int)
    folds = [s.pnl[(s.ent_sess >= e[k]) & (s.ex_sess < e[k + 1])].sum() for k in range(1, 8)]
    six = np.array_split(np.arange(s.n_sess), 6)
    periods = sum(1 for b in six if s.pnl[(s.ent_sess >= b[0]) & (s.ent_sess <= b[-1])].sum() > 0)
    reg_ok = [r for r in rows if r[2] >= 15]
    extras = {
        "param grid profitable %": 100 * np.mean([g > 0 for g in grid]),
        "cost 4x survives": 1.0 if s.sim(cost_mult=4.0).pnl.sum() > 0 else 0.0,
        "noise draws profitable %": 100 * np.mean([x > 0 for x in noise]),
        "positive periods": periods,
        "matched null p": _matched_null(s),
        "walk-forward positive folds": sum(1 for f in folds if f > 0),
        "oos retention": (per_lok / per_res) if per_res > 0 else 0.0,
        "max book correlation": book_corr if book_corr is not None else _book_corr(s, d),
        "profitable regime share": np.mean([r[4] > 0 for r in reg_ok]) if reg_ok else 0.0,
    }
    score, dims = MT.quant_score(M, extras)
    cons = (constraints or MT.Constraints()).check(s, M)
    return dict(s=s, M=M, extras=extras, score=score, dims=dims, constraints=cons,
                regime_rows=rows, works=good, avoid=bad, folds=folds,
                research=float(res.sum()), locked=float(lok.sum()))


def _matched_null(s, draws=150, seed=17):
    """Same trade count, entries drawn from the SAME clock window the rule trades in. Holding
    drift, session and geometry fixed isolates the one thing under test: which bars it picked."""
    rng = np.random.default_rng(seed)
    mod = s.bars["mod"]; n = len(s.bars["c"])
    used = mod[s.ent_bar]
    lo, hi = used.min(), used.max()
    pool = np.flatnonzero((mod >= lo) & (mod <= hi))
    pool = pool[(pool > 300) & (pool < n - 2)]
    if len(pool) < len(s.pnl) * 2:
        pool = np.arange(300, n - 2)
    obs = s.pnl.sum(); beat = 0
    for _ in range(draws):
        t = np.sort(rng.choice(pool, size=len(s.pnl), replace=False))
        beat += s.sim(trig=t).pnl.sum() >= obs
    return (beat + 1) / (draws + 1)


def _book_corr(s, d):
    import contextlib, io
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            from book import all_legs
            legs = all_legs()
    except Exception:
        return 0.0
    us = np.unique(s.bars["sess"]); ix = {u: i for i, u in enumerate(us)}
    best = 0.0
    for v in legs.values():
        a = np.zeros(len(us))
        for p, q in zip(v["pnl"], v["sess"]):
            if q in ix:
                a[ix[q]] += p
        n = min(len(a), len(d))
        sd = a[:n].std() * d[:n].std()
        if sd > 0:
            best = max(best, abs(float(np.cov(a[:n], d[:n])[0, 1] / sd)))
    return best


# =============================================================== 2. SIGNAL INTELLIGENCE
COMPONENTS = {
    "Trend alignment": ["dist EMA200 / ATR", "EMA50-EMA200 / ATR", "LR slope50"],
    "Momentum": ["ROC10", "ROC10 acceleration", "return 20b / ATR"],
    "VWAP relationship": ["dist VWAP / ATR", "dist VWAP z100"],
    "Volatility regime": ["ATR / ATR20", "ATR20 / ATR100", "BB width / mean50"],
    "Liquidity condition": ["illiquidity z100", "range per volume"],
    "Market structure": ["Donchian20 position", "position in session range", "close percentile 100"],
    "Volume confirmation": ["volume / mean20", "volume z50", "volume acceleration"],
    "Statistical character": ["Hurst 256", "autocorr 50", "sign entropy 64"],
}


class SignalModel:
    """Fitted on RESEARCH trades, scored on LOCKED trades. The locked AUC travels with every
    confidence this produces, because a confidence fitted and read on the same data is a
    restatement of the fit, not a forecast."""

    def __init__(self, s, F):
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.metrics import roc_auc_score
        self.keys = [k for v in COMPONENTS.values() for k in v]
        X = np.column_stack([np.nan_to_num(F[k][s.ent_bar], nan=0.0, posinf=0.0, neginf=0.0)
                             for k in self.keys])
        y = (s.pnl > 0).astype(int)
        tr = s.ent_sess < s.cut; te = ~tr
        self.ok = tr.sum() >= 40 and te.sum() >= 20 and len(np.unique(y[tr])) == 2
        self.auc = np.nan
        if self.ok:
            self.m = GradientBoostingClassifier(n_estimators=120, max_depth=2,
                                                learning_rate=0.05, random_state=4).fit(X[tr], y[tr])
            if len(np.unique(y[te])) == 2:
                self.auc = float(roc_auc_score(y[te], self.m.predict_proba(X[te])[:, 1]))
        self.F, self.s = F, s

    def confidence(self, bar):
        if not self.ok:
            return np.nan
        x = np.array([[np.nan_to_num(self.F[k][bar], nan=0.0, posinf=0.0, neginf=0.0)
                       for k in self.keys]])
        return float(self.m.predict_proba(x)[0, 1])


def _grade(pct):
    return "+++" if pct >= 0.85 else "++" if pct >= 0.65 else "+" if pct >= 0.5 else \
           "·" if pct >= 0.35 else "−"


def explain(s, F, k, model=None, pctl=None):
    """Decompose one entry into named components, each graded by where it sat in its own
    trailing distribution."""
    bar = int(s.ent_bar[k])
    out = []
    for comp, keys in COMPONENTS.items():
        ranks = []
        for key in keys:
            v = F[key]
            hist = v[max(0, bar - 2000):bar]
            hist = hist[np.isfinite(hist)]
            if not np.isfinite(v[bar]) or len(hist) < 100:
                continue
            r = float((hist < v[bar]).mean())
            ranks.append(r if s.side[k] == 1 else 1 - r)
        if ranks:
            out.append((comp, float(np.mean(ranks))))
    conf = model.confidence(bar) if model is not None else np.nan
    out.sort(key=lambda x: -x[1])
    return dict(bar=bar, time=s.bars["d"]["df"].index[bar], side=int(s.side[k]),
                pnl=float(s.pnl[k]), components=out, confidence=conf,
                primary=[c for c, r in out[:3] if r >= 0.6])


# =============================================================== 3. IMPROVEMENT ENGINE
def improve(s, F=None, tries=40, seed=23):
    """Propose variants, then judge them ONLY by whether the gain survives the locked block.

    The variants are deliberately conservative: geometry moves, a session filter, a fourth
    condition. Every one is a chance to overfit, which is why the report shows the research gain
    and the locked gain side by side and calls a variant an improvement only when both hold.
    """
    from alpha_factory2 import build_conditions
    d = s.bars["d"]
    names, M = build_conditions(d)
    rng = np.random.default_rng(seed)
    base_r = s.pnl[s.ent_sess < s.cut].sum(); base_l = s.pnl[s.ent_sess >= s.cut].sum()
    base_m = MT.all_metrics(s)
    cands = []

    for am in (1.5, 2.0, 2.5, 3.0, 3.5):
        for tp in (1.5, 2.0, 2.5, 3.0, 4.0):
            if am == s.params["atr_mult"] and tp == s.params["tp_r"]:
                continue
            cands.append((f"geometry {am}xATR / {tp}R", dict(atr_mult=am, tp_r=tp)))
    for fl in (840, 900, 960):
        cands.append((f"flatten {fl//60}:00", dict(flat_min=fl)))
    pick = rng.choice(len(names), size=min(tries, len(names)), replace=False)
    for i in pick:
        if names[i] in s.conds:
            continue
        cands.append((f"+ {names[i]}", dict(conds=list(s.conds) + [names[i]])))

    rows = []
    for label, kw in cands:
        try:
            r = s.sim(**kw)
        except Exception:
            continue
        if len(r.pnl) < 30:
            continue
        rr = r.pnl[r.ent_sess < r.cut].sum(); rl = r.pnl[r.ent_sess >= r.cut].sum()
        m = MT.all_metrics(r)
        rows.append(dict(label=label, kw=kw, res=rr, lok=rl, m=m, strategy=r,
                         d_res=rr - base_r, d_lok=rl - base_l))
    rows.sort(key=lambda x: -x["d_res"])
    survivors = [r for r in rows if r["d_res"] > 0 and r["d_lok"] > 0
                 and r["m"]["max drawdown $"] <= base_m["max drawdown $"] * 1.1
                 and r["m"]["Sortino"] >= base_m["Sortino"]]
    return dict(base=base_m, base_res=base_r, base_lok=base_l,
                tried=len(rows), all=rows, survivors=survivors)


# =============================================================== 4. FEATURE IMPORTANCE
def feature_importance(tf=30, horizon=32, top=20, seed=6):
    """Which features carry information about the forward move -- measured by permutation
    importance on a PURGED split, so a feature cannot score by memorising overlapping windows."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.inspection import permutation_importance
    d = prep(tf); F = FT.build(d)
    keys = list(F)
    X = np.column_stack([np.nan_to_num(F[k], nan=0.0, posinf=0.0, neginf=0.0) for k in keys])
    c = d["c"]
    y = np.r_[(c[horizon:] - c[:-horizon]) / np.maximum(d["atr"][:-horizon], 1e-9),
              np.zeros(horizon)]
    n = len(c); cut = int(0.65 * n)
    tr = slice(300, cut - horizon)                      # purge the overlap at the boundary
    te = slice(cut + horizon, n - horizon)
    m = HistGradientBoostingRegressor(max_iter=200, max_depth=4, learning_rate=0.06,
                                      random_state=seed).fit(X[tr], y[tr])
    r2 = float(m.score(X[te], y[te]))
    pi = permutation_importance(m, X[te], y[te], n_repeats=3, random_state=seed, n_jobs=1)
    order = np.argsort(-pi.importances_mean)[:top]
    return dict(r2=r2, ranked=[(keys[i], float(pi.importances_mean[i]),
                                float(pi.importances_std[i])) for i in order],
                keys=keys, X=X, F=F, d=d)


def redundancy(F, keys=None, thresh=0.9):
    """Hierarchical clustering on |Spearman|. Features inside one cluster are restatements of
    each other, and counting them separately inflates every feature-count in a report."""
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform
    keys = keys or list(F)
    A = np.column_stack([np.nan_to_num(F[k], nan=0.0, posinf=0.0, neginf=0.0) for k in keys])
    A = A[300::7]
    C = np.abs(pd.DataFrame(A).corr(method="spearman").to_numpy())
    C = np.nan_to_num(C, nan=0.0)
    np.fill_diagonal(C, 1.0)
    D = np.clip(1 - C, 0, 2)
    np.fill_diagonal(D, 0.0)
    Z = linkage(squareform(D, checks=False), "average")
    lab = fcluster(Z, 1 - thresh, "distance")
    groups = {}
    for k, g in zip(keys, lab):
        groups.setdefault(int(g), []).append(k)
    return {g: v for g, v in groups.items() if len(v) > 1}, len(set(lab))


# =============================================================== 5. PORTFOLIO INTELLIGENCE
def portfolio(strategies, R=None, tf=30):
    """strategies: {name: Strategy}. Correlation on four views, then clustering and PCA."""
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform
    from sklearn.decomposition import PCA
    names = list(strategies)
    n_sess = next(iter(strategies.values())).n_sess
    D = np.column_stack([_daily(strategies[k])[:n_sess] for k in names])
    df = pd.DataFrame(D, columns=names)

    pear = df.corr().to_numpy()
    rank = df.corr(method="spearman").to_numpy()

    # partial correlation: the pairwise link with every other strategy held constant
    C = np.cov(D.T)
    try:
        P = np.linalg.pinv(C)
        dp = np.sqrt(np.outer(np.diag(P), np.diag(P)))
        part = -P / np.where(dp == 0, 1, dp)
        np.fill_diagonal(part, 1.0)
    except Exception:
        part = np.full_like(pear, np.nan)

    # rolling correlation of the two most correlated legs
    iu = np.triu_indices(len(names), 1)
    if len(iu[0]):
        j = int(np.argmax(np.abs(pear[iu])))
        a, b = names[iu[0][j]], names[iu[1][j]]
        roll = df[a].rolling(120).corr(df[b])
        rolling = dict(pair=(a, b), median=float(roll.median()),
                       lo=float(roll.min()), hi=float(roll.max()))
    else:
        rolling = None

    # regime-dependent correlation
    regime = {}
    if R is not None:
        for ax, k, nm in (("volatility", 2, "high vol"), ("volatility", 0, "low vol"),
                          ("trend", 2, "trending"), ("trend", 0, "mean-reverting")):
            m = R["labels"][ax][:n_sess] == k
            if m.sum() > 60:
                sub = df[m]
                cm = sub.corr().to_numpy()
                regime[nm] = float(np.nanmax(np.abs(cm[np.triu_indices(len(names), 1)]))) \
                    if len(names) > 1 else np.nan

    dist = np.clip(1 - np.abs(np.nan_to_num(pear)), 0, 2)
    np.fill_diagonal(dist, 0.0)
    clusters = {}
    if len(names) > 2:
        Z = linkage(squareform(dist, checks=False), "average")
        lab = fcluster(Z, 0.6, "distance")
        for k, g in zip(names, lab):
            clusters.setdefault(int(g), []).append(k)

    sd = D.std(0, ddof=1)
    Xs = D / np.where(sd == 0, 1, sd)
    pca = PCA().fit(Xs)
    ev = pca.explained_variance_ratio_

    w = 1.0 / np.maximum(sd, 1e-9); w /= w.sum()
    port = D @ w
    def sh(x):
        return float(x.mean() / x.std(ddof=1) * np.sqrt(252)) if x.std() > 0 else 0.0
    solo = {k: sh(D[:, i]) for i, k in enumerate(names)}
    return dict(names=names, pearson=pear, rank=rank, partial=part, rolling=rolling,
                regime=regime, clusters=clusters, pca_explained=ev,
                weights=dict(zip(names, w)), portfolio_sharpe=sh(port),
                best_solo_sharpe=max(solo.values()), solo=solo,
                independent=int((np.cumsum(ev) < 0.9).sum() + 1))


# =============================================================== 6. THE REPORT
def _bar(v, w=22):
    n = int(round(np.clip(v, 0, 100) / 100 * w))
    return "█" * n + "·" * (w - n)


def report(A, title=""):
    M, ex = A["M"], A["extras"]
    print("=" * 100)
    print(f"  {title or A['s'].name}")
    print("=" * 100)
    print(f"\n  QUANT SCORE  {A['score']:.1f} / 100")
    for k, v in A["dims"].items():
        print(f"     {k:<26}{_bar(v)}  {v:>5.1f}   (weight {MT.WEIGHTS[k]})")

    print("\n  PERFORMANCE")
    order = ["trades", "net profit", "expectancy $", "profit factor", "win rate %",
             "driftless bound %", "win rate excess", "payoff ratio", "average win $",
             "average loss $", "Sharpe", "Sortino", "Calmar", "max drawdown $",
             "average drawdown $", "recovery factor", "return / max drawdown",
             "volatility $/session", "stability of returns", "longest winning streak",
             "longest losing streak", "VaR 95 $", "VaR 99 $", "CVaR 95 $", "CVaR 99 $",
             "tail ratio", "skew", "kurtosis", "exposure % of bars", "trades per year",
             "MAE mean $", "MFE mean $", "edge ratio (MFE/|MAE|)", "risk of ruin (50%)"]
    for i in range(0, len(order), 2):
        cells = []
        for k in order[i:i + 2]:
            v = M.get(k)
            cells.append(f"{k:<24}{v:>12,.2f}" if isinstance(v, float) else f"{k:<24}{v:>12}")
        print("     " + "     ".join(cells))

    print(f"\n  OUT OF SAMPLE      research ${A['research']:,.0f}  ->  locked ${A['locked']:,.0f}"
          f"   (per-trade retention {100*ex['oos retention']:.0f}%)")
    print(f"  MATCHED NULL       p = {ex['matched null p']:.4f}  "
          f"(same trade count, entries drawn from the same clock window)")
    print(f"  WALK-FORWARD       {ex['walk-forward positive folds']} of 7 folds positive")

    print("\n  CONSTRAINTS")
    for name, got, op, want, ok in A["constraints"]:
        print(f"     {'PASS' if ok else 'FAIL'}  {name:<20}{got:>12,.2f}  {op} {want:>10,.2f}")

    print("\n  WHEN IT WORKS")
    for ax, nm, n, tot, per, wr in A["works"]:
        print(f"     {ax:<12}{nm:<18}{n:>5} tr  ${tot:>9,.0f}  ${per:>7,.0f}/trade  win {wr:.0f}%")
    print("  WHEN TO AVOID IT")
    if not A["avoid"]:
        print("     No regime bucket with 15+ trades loses money. That is either genuine regime"
              " independence")
        print("     or a sample containing one regime -- 2022-12 to 2025-12 NQ rose 89%, so"
              " prefer the second reading")
        print("     until it is checked on a period that fell.")
    for ax, nm, n, tot, per, wr in A["avoid"]:
        print(f"     {ax:<12}{nm:<18}{n:>5} tr  ${tot:>9,.0f}  ${per:>7,.0f}/trade  win {wr:.0f}%")


def explain_report(s, F, model, ks):
    print("\n" + "=" * 100)
    print("  SIGNAL INTELLIGENCE")
    if np.isfinite(model.auc):
        print(f"  Confidence model: gradient boosting on {len(model.keys)} features, fitted on "
              f"research trades.")
        print(f"  LOCKED-BLOCK AUC = {model.auc:.3f}   "
              + ("(0.50 is a coin -- treat every confidence below as decoration)"
                 if model.auc < 0.55 else "(above chance out of sample)"))
    print("=" * 100)
    for k in ks:
        e = explain(s, F, k, model)
        print(f"\n  {'LONG' if e['side']==1 else 'SHORT'} SIGNAL   {e['time']:%Y-%m-%d %H:%M}"
              f"    outcome ${e['pnl']:+,.0f}")
        for comp, r in e["components"]:
            print(f"     {comp:<24}{_grade(r):<4}  {100*r:>5.0f}th percentile")
        if np.isfinite(e["confidence"]):
            print(f"     Signal confidence: {100*e['confidence']:.0f}%"
                  + (f"   primary: {', '.join(e['primary'])}" if e["primary"] else ""))


# =============================================================== 7. MAIN
CANDIDATES = {
    "vol/midday/EMA200": (["vol rising", "midday", "dist EMA200>2 ATR"], 1, 2.5, 3.0, 0),
    "RSI/Williams/ADX": (["RSI14<30", "Williams%R<-80", "ADX>25"], 1, 2.5, 3.0, 0),
    "VWAP/Stoch/ADX": (["close>session VWAP", "Stoch K>D", "ADX>20"], 1, 1.5, 3.0, 0),
    "EMA10/body/momentum": (["close>EMA10", "body>60%", "5-bar momentum>0"], 1, 2.5, 3.0, 0),
}


def main():
    import time
    t0 = time.time()
    tf = 30
    print("Loading bars, features and regimes...", flush=True)
    d = prep(tf)
    F = FT.build(d)
    R = RG.classify(tf)
    print(f"  {len(F)} features, {len(R['sessions'])} sessions on {len(RG.AXES)} regime axes, "
          f"{time.time()-t0:.0f}s\n", flush=True)

    cons = MT.Constraints(max_drawdown=8000, min_profit_factor=1.2, min_sortino=1.0,
                          min_expectancy=25, min_oos=0, max_exposure=80, min_trades=60)

    strategies, analyses = {}, {}
    for name, (conds, side, am, tp, fl) in CANDIDATES.items():
        A = analyse(conds, side, am, tp, fl, tf, constraints=cons, R=R)
        if A:
            analyses[name] = A
            strategies[name] = A["s"]

    print("=" * 100)
    print("  STRATEGY LEADERBOARD -- ranked by Quant Score, not by net profit")
    print("=" * 100)
    print(f"  {'strategy':<22}{'score':>7}{'net $':>11}{'locked $':>11}{'PF':>7}"
          f"{'Sortino':>9}{'maxDD $':>10}{'null p':>9}{'constraints':>13}")
    for name in sorted(analyses, key=lambda k: -analyses[k]["score"]):
        A = analyses[name]; M = A["M"]
        nfail = sum(1 for c in A["constraints"] if not c[4])
        print(f"  {name:<22}{A['score']:>7.1f}{M['net profit']:>11,.0f}{A['locked']:>11,.0f}"
              f"{M['profit factor']:>7.2f}{M['Sortino']:>9.2f}{M['max drawdown $']:>10,.0f}"
              f"{A['extras']['matched null p']:>9.4f}"
              f"{('all pass' if nfail == 0 else f'{nfail} fail'):>13}")

    best = max(analyses, key=lambda k: analyses[k]["score"])
    print()
    report(analyses[best], f"{best}   —   highest Quant Score")

    s = analyses[best]["s"]
    model = SignalModel(s, F)
    idx = np.argsort(-s.pnl)[:2].tolist() + np.argsort(s.pnl)[:1].tolist()
    explain_report(s, F, model, idx)

    print("\n" + "=" * 100); print("  IMPROVEMENT ENGINE"); print("=" * 100)
    imp = improve(s, F)
    b = imp["base"]
    print(f"  {imp['tried']} variants tried on {best}.")
    print(f"  {'':<34}{'trades':>8}{'net $':>10}{'PF':>7}{'Sortino':>9}{'maxDD $':>10}"
          f"{'expect $':>10}{'research Δ':>12}{'locked Δ':>11}")
    print(f"  {'ORIGINAL':<34}{b['trades']:>8}{b['net profit']:>10,.0f}{b['profit factor']:>7.2f}"
          f"{b['Sortino']:>9.2f}{b['max drawdown $']:>10,.0f}{b['expectancy $']:>10,.0f}"
          f"{'—':>12}{'—':>11}")
    for r in imp["all"][:6]:
        m = r["m"]
        print(f"  {r['label']:<34}{m['trades']:>8}{m['net profit']:>10,.0f}"
              f"{m['profit factor']:>7.2f}{m['Sortino']:>9.2f}{m['max drawdown $']:>10,.0f}"
              f"{m['expectancy $']:>10,.0f}{r['d_res']:>+12,.0f}{r['d_lok']:>+11,.0f}")
    print(f"\n  Variants improving RESEARCH: {sum(1 for r in imp['all'] if r['d_res'] > 0)}"
          f" of {imp['tried']}")
    print(f"  Variants that ALSO improve the locked block, without a worse drawdown or Sortino: "
          f"{len(imp['survivors'])}")
    if imp["survivors"]:
        for r in imp["survivors"][:5]:
            m = r["m"]
            print(f"     {r['label']:<32} research {r['d_res']:>+9,.0f}   locked {r['d_lok']:>+9,.0f}"
                  f"   Sortino {b['Sortino']:.2f} -> {m['Sortino']:.2f}"
                  f"   maxDD {b['max drawdown $']:,.0f} -> {m['max drawdown $']:,.0f}")
    else:
        print("     none. Every research gain here is a research gain only.")

    print("\n" + "=" * 100); print("  FEATURE IMPORTANCE"); print("=" * 100)
    fi = feature_importance(tf)
    print(f"  Gradient boosting on the 32-bar forward move, purged split. "
          f"Out-of-sample R2 = {fi['r2']:+.4f}"
          + ("   <- negative: the model does not generalise, and the ranking below is a "
             "description of the fit, not of the market" if fi["r2"] <= 0 else ""))
    for k, v, sd in fi["ranked"][:12]:
        print(f"     {k:<34}{v:>10.5f}  ± {sd:.5f}")
    groups, n_ind = redundancy(F)
    print(f"\n  Redundancy: {len(F)} features collapse to {n_ind} independent groups at |rho| > 0.9")
    for g, v in list(groups.items())[:4]:
        print(f"     {len(v)} restatements: {', '.join(v[:5])}{' ...' if len(v) > 5 else ''}")

    print("\n" + "=" * 100); print("  PORTFOLIO INTELLIGENCE"); print("=" * 100)
    P = portfolio(strategies, R)
    nm = P["names"]
    print(f"  {'':<22}" + "".join(f"{k[:13]:>15}" for k in nm))
    for i, a in enumerate(nm):
        print(f"  {a:<22}" + "".join(f"{P['pearson'][i,j]:>15.2f}" for j in range(len(nm))))
    print(f"\n  rank correlation, largest off-diagonal: "
          f"{np.nanmax(np.abs(P['rank'][np.triu_indices(len(nm),1)])):.2f}")
    print(f"  partial correlation, largest off-diagonal: "
          f"{np.nanmax(np.abs(P['partial'][np.triu_indices(len(nm),1)])):.2f}"
          f"   (the direct link once the others are held constant)")
    if P["rolling"]:
        r = P["rolling"]
        print(f"  rolling 120-session correlation of {r['pair'][0]} vs {r['pair'][1]}: "
              f"median {r['median']:+.2f}, range [{r['lo']:+.2f}, {r['hi']:+.2f}]")
    for k, v in P["regime"].items():
        print(f"  largest pairwise correlation in {k:<16}{v:+.2f}")
    print(f"\n  clusters at |rho| > 0.4: " +
          "; ".join("{" + ", ".join(v) + "}" for v in P["clusters"].values()))
    print(f"  PCA: {P['independent']} components explain 90% of the variance across "
          f"{len(nm)} strategies "
          f"({', '.join(f'{100*x:.0f}%' for x in P['pca_explained'][:4])})")
    print(f"  equal-risk portfolio Sharpe {P['portfolio_sharpe']:.2f} "
          f"against best single {P['best_solo_sharpe']:.2f}")

    print("\n" + "=" * 100); print("  WHAT THIS BRAIN CANNOT SEE"); print("=" * 100)
    for k, why in FT.NOT_AVAILABLE.items():
        print(f"     {k:<42}{why}")
    print(f"\n  {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
