"""Parameter stability, Monte Carlo on every cell, cluster analysis and walk-forward for the
Zeta FX IBS session EA -- on the two long CFD feeds (US100, US30 2016-2025), NQ futures
(2022-2025) and the US30 ISO feed whose 2026 tail nothing has seen.

    python research/ibs/ibs_run.py stability | montecarlo | cluster | walkforward | judge | all

Selection happens on the RESEARCH blocks of US100 and US30 (before 2022). Validation (2022-23)
is read for the rank-stability test; the TEST block (2024+), NQ locked and US30_ISO 2026 are
read ONCE, in `judge`, for a handful of pre-declared cells with the multiplicity stated.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from ibs import ibs_core as C  # noqa: E402

OUT = "results/ibs"
os.makedirs(OUT, exist_ok=True)
AXES = ("entry", "exit", "hold", "mult")
LONG = ("US100", "US30")
MIN_N = 30

_FEEDS = {}


def feed(mk, cost_mult=1.0):
    key = (mk, cost_mult)
    if key not in _FEEDS:
        f, tf = C.load(mk)
        s = C.sessions(f, tf)
        B = C.build(f, tf, s, mk, cost_mult=cost_mult)
        _FEEDS[key] = dict(f=f, tf=tf, s=s, B=B, masks=C.block_masks(mk, s["date"]))
    return _FEEDS[key]


def sweep_block(mk, block, cost_mult=1.0):
    path = f"{OUT}/sweep_{mk}_{block}_c{cost_mult:g}.csv"
    if os.path.exists(path):
        return pd.read_csv(path)
    F = feed(mk, cost_mult)
    t0 = time.time()
    sw = C.sweep(F["B"], F["masks"][block])
    sw.to_csv(path, index=False)
    print(f"  swept {mk} {block} ({len(sw)} cells) in {time.time() - t0:.1f}s")
    return sw


def cell_key(df):
    return list(zip(df["entry"], df["exit"], df["hold"], df["mult"]))


def keyed(df):
    return df.set_index(pd.Index(cell_key(df)))


def index_grid(sw):
    """Map every cell to integer coordinates on the 4-D grid."""
    coords = {}
    for a in AXES:
        lv = list(C.GRID[a])
        coords[a] = sw[a].map(lambda v: lv.index(v)).to_numpy()
    return coords


def neighbour_mean(sw, col="R"):
    """Mean of `col` over the +-1 neighbours of each cell (excluding itself) -- the plateau
    score. A cell with no neighbourhood is the first thing a grid maximum hides."""
    co = index_grid(sw)
    shape = tuple(len(C.GRID[a]) for a in AXES)
    arr = np.full(shape, np.nan)
    arr[co["entry"], co["exit"], co["hold"], co["mult"]] = sw[col].to_numpy()
    out = np.zeros(len(sw))
    for i in range(len(sw)):
        ci = [co[a][i] for a in AXES]
        vals = []
        for d in range(4):
            for step in (-1, 1):
                cj = list(ci)
                cj[d] += step
                if 0 <= cj[d] < shape[d]:
                    v = arr[tuple(cj)]
                    if np.isfinite(v):
                        vals.append(v)
        out[i] = np.mean(vals) if vals else np.nan
    return out


def marginals(sw, col="R"):
    rows = []
    for a in AXES:
        g = sw.groupby(a)[col]
        for lv, grp in g:
            rows.append(dict(axis=a, level=lv, mean=grp.mean(), share_pos=(grp > 0).mean(),
                             n_cells=len(grp)))
    return pd.DataFrame(rows)


def default_row(sw):
    m = np.ones(len(sw), bool)
    for a in AXES:
        m &= sw[a] == C.DEFAULT[a]
    return sw[m].iloc[0]


def ladders(sw, col="R"):
    """One-at-a-time perturbation of the EA's defaults."""
    out = []
    for a in AXES:
        m = np.ones(len(sw), bool)
        for b in AXES:
            if b != a:
                m &= sw[b] == C.DEFAULT[b]
        sub = sw[m].sort_values(a)
        out.append((a, sub[[a, "n", col, "pf", "win", "sharpe", "dd"]]))
    return out


def fmt(df, cols=None, n=None):
    d = df if cols is None else df[cols]
    if n:
        d = d.head(n)
    return d.to_string(index=False, float_format=lambda x: f"{x:.4f}")


# ------------------------------------------------------------------------------------------
# 1. parameter stability
# ------------------------------------------------------------------------------------------
def stability():
    print("=" * 100)
    print("1. PARAMETER STABILITY -- research blocks only (US100, US30 before 2022; NQ first 65%)")
    print("=" * 100)
    R = {mk: sweep_block(mk, "research") for mk in LONG}
    V = {mk: sweep_block(mk, "validation") for mk in LONG}
    Rnq = sweep_block("NQ", "research")
    for mk, sw in list(R.items()) + [("NQ", Rnq)]:
        ok = sw["n"] >= MIN_N
        print(f"\n{mk} research: {len(sw)} cells, {int(ok.sum())} with n>={MIN_N}. "
              f"Share R>0 {float((sw.R > 0).mean()):.1%}, PF>1.2 {float((sw.pf > 1.2).mean()):.1%},"
              f" median R {sw.R.median():+.4f}, median PF {sw.pf.median():.3f}, "
              f"median n {sw.n.median():.0f}")
        d = default_row(sw)
        pct = float((sw.R < d.R).mean())
        print(f"  EA default (20/80/5/1.0): n {d.n:.0f}  R {d.R:+.4f}  pts {d.pts:+.1f}  "
              f"PF {d.pf:.3f}  win {d.win:.1%}  Sharpe {d.sharpe:.2f}  DD {d.dd:.1f}R  "
              f"stop-share {d.stop_share:.1%}  -> percentile {pct:.1%} of the grid")
    print("\nMARGINAL AVERAGE PER AXIS (mean R over all cells at that level, share of cells R>0)")
    M = {mk: marginals(sw) for mk, sw in R.items()}
    for a in AXES:
        print(f"\n  {a:<6}" + "".join(f"{mk:>22}" for mk in LONG) + f"{'NQ':>22}")
        mn = marginals(Rnq)
        for lv in C.GRID[a]:
            line = f"  {lv:<6}"
            for mk in LONG:
                r = M[mk][(M[mk].axis == a) & (M[mk].level == lv)].iloc[0]
                line += f"{r['mean']:+.4f} ({r['share_pos']:.0%})".rjust(22)
            r = mn[(mn.axis == a) & (mn.level == lv)].iloc[0]
            line += f"{r['mean']:+.4f} ({r['share_pos']:.0%})".rjust(22)
            print(line)
    print("\nONE-AT-A-TIME LADDERS AROUND THE EA DEFAULT (research)")
    for mk in LONG:
        print(f"\n  {mk}")
        for a, tab in ladders(R[mk]):
            print(f"    {a}:")
            print("      " + fmt(tab).replace("\n", "\n      "))
    print("\nNEIGHBOURHOOD COHERENCE: corr(cell R, mean R of its +-1 neighbours), and the share of")
    print("cells whose sign agrees with their neighbourhood. A real edge is a ridge, not a spike.")
    for mk in LONG:
        sw = R[mk]
        nb = neighbour_mean(sw)
        sw["plateau"] = nb
        ok = np.isfinite(nb) & (sw.n >= MIN_N)
        c = np.corrcoef(sw.R[ok], nb[ok])[0, 1]
        agree = float((np.sign(sw.R[ok]) == np.sign(nb[ok])).mean())
        print(f"  {mk}: corr {c:.3f}, sign agreement {agree:.1%}")
        top = sw[ok].sort_values("R", ascending=False).head(5)
        print("    top 5 by cell R -> their plateau score:")
        print("      " + fmt(top, list(AXES) + ["n", "R", "pf", "plateau"])
              .replace("\n", "\n      "))
        top = sw[ok].sort_values("plateau", ascending=False).head(5)
        print("    top 5 by plateau:")
        print("      " + fmt(top, list(AXES) + ["n", "R", "pf", "plateau"])
              .replace("\n", "\n      "))
    print("\nRANK STABILITY research -> validation (2022-23), the honest version of a heatmap:")
    print("Spearman over cells with n>=30 on both; share of research top-decile cells positive on")
    print("validation; and what the validation top decile looked like on research.")
    from scipy.stats import spearmanr
    for mk in LONG:
        a = keyed(R[mk])
        b = keyed(V[mk])
        j = a.join(b, lsuffix="_r", rsuffix="_v")
        ok = (j.n_r >= MIN_N) & (j.n_v >= 15)
        rho = spearmanr(j.R_r[ok], j.R_v[ok]).correlation
        q = j[ok].R_r.quantile(0.9)
        top = j[ok & (j.R_r >= q)]
        print(f"  {mk}: Spearman {rho:+.3f} over {int(ok.sum())} cells; research top decile "
              f"({len(top)} cells) mean research R {top.R_r.mean():+.4f} -> validation "
              f"{top.R_v.mean():+.4f}, {float((top.R_v > 0).mean()):.0%} positive; "
              f"all-cell validation mean {j[ok].R_v.mean():+.4f}")
    print("\nTWO-FEED AGREEMENT on research: cells positive on BOTH US100 and US30, and the")
    print("top-100 consensus by the MINIMUM of the two feeds' R (what the top 100 agree on).")
    a = keyed(R["US100"])
    b = keyed(R["US30"])
    j = a.join(b, lsuffix="_q", rsuffix="_d")
    ok = (j.n_q >= MIN_N) & (j.n_d >= MIN_N)
    both = ok & (j.R_q > 0) & (j.R_d > 0)
    print(f"  cells with n>=30 on both: {int(ok.sum())}; positive on both: {int(both.sum())} "
          f"({float(both.sum() / ok.sum()):.1%}); positive on US100 only "
          f"{int((ok & (j.R_q > 0) & (j.R_d <= 0)).sum())}, US30 only "
          f"{int((ok & (j.R_q <= 0) & (j.R_d > 0)).sum())}")
    j["minR"] = np.minimum(j.R_q, j.R_d)
    top = j[ok].sort_values("minR", ascending=False).head(100)
    for ax in AXES:
        vc = top[ax + "_q"].value_counts().sort_index()
        print(f"  {ax:<6}: " + "  ".join(f"{k:g}:{v}" for k, v in vc.items()))
    cons = {ax: top[ax + "_q"].mode().iloc[0] for ax in AXES}
    j.reset_index(drop=True).to_csv(f"{OUT}/two_feed_research.csv", index=False)
    print(f"  consensus cell (mode per axis): {cons}")
    print(f"  top-10 by min R:")
    print("    " + fmt(top.reset_index(drop=True),
                       ["entry_q", "exit_q", "hold_q", "mult_q", "n_q", "R_q", "pf_q", "n_d",
                        "R_d", "pf_d", "minR"], 10).replace("\n", "\n    "))
    return cons


# ------------------------------------------------------------------------------------------
# 2. Monte Carlo on every cell
# ------------------------------------------------------------------------------------------
def mc_cell(r, n_draws=2000, risk=0.01, seed=0):
    """Bootstrap WITH replacement for edge uncertainty; permutation for path (drawdown), both
    fixed-R and compounded at `risk` of equity per trade as the EA sizes."""
    n = len(r)
    if n < 10:
        return dict(p_le0=np.nan, ci5=np.nan, ci95=np.nan, dd_med=np.nan, dd_p95=np.nan,
                    cdd_med=np.nan, cdd_p95=np.nan, p_cdd10=np.nan, p_cdd20=np.nan,
                    eq_med=np.nan, eq_p5=np.nan)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_draws, n))
    means = r[idx].mean(axis=1)
    perm = np.argsort(rng.random((n_draws, n)), axis=1)
    paths = np.cumsum(r[perm], axis=1)
    dd = np.max(np.maximum.accumulate(paths, axis=1) - paths, axis=1)
    lg = np.cumsum(np.log1p(np.clip(risk * r[perm], -0.999, None)), axis=1)
    cdd = np.max(np.maximum.accumulate(lg, axis=1) - lg, axis=1)
    cdd = 1.0 - np.exp(-cdd)
    # the endpoint of a compounded path is a PRODUCT, and permuting trades cannot change a
    # product any more than a sum -- so the equity distribution comes from the bootstrap
    eq = np.exp(np.sum(np.log1p(np.clip(risk * r[idx], -0.999, None)), axis=1))
    return dict(p_le0=float(np.mean(means <= 0)), ci5=float(np.quantile(means, 0.05)),
                ci95=float(np.quantile(means, 0.95)), dd_med=float(np.median(dd)),
                dd_p95=float(np.quantile(dd, 0.95)), cdd_med=float(np.median(cdd)),
                cdd_p95=float(np.quantile(cdd, 0.95)), p_cdd10=float(np.mean(cdd > 0.10)),
                p_cdd20=float(np.mean(cdd > 0.20)), eq_med=float(np.median(eq)),
                eq_p5=float(np.quantile(eq, 0.05)))


def montecarlo(markets=LONG, block="research", n_draws=2000):
    print("=" * 100)
    print("2. MONTE CARLO ON EVERY CELL -- bootstrap (edge) + permutation (path), fixed-R and")
    print("   compounded at 1% of equity per trade as the EA sizes, research blocks")
    print("=" * 100)
    for mk in markets:
        path = f"{OUT}/mc_{mk}_{block}.csv"
        if os.path.exists(path):
            mc = pd.read_csv(path)
        else:
            F = feed(mk)
            sw = sweep_block(mk, block)
            rows = []
            t0 = time.time()
            for i, row in sw.iterrows():
                cell = {a: row[a] for a in AXES}
                t = C.cell_trades(F["B"], F["masks"][block], cell)
                d = dict(cell)
                d["n"] = len(t)
                d["R"] = float(t.r.mean()) if len(t) else np.nan
                d.update(mc_cell(t.r.to_numpy(), n_draws=n_draws, seed=i))
                rows.append(d)
            mc = pd.DataFrame(rows)
            mc.to_csv(path, index=False)
            print(f"  {mk}: {len(mc)} cells x {n_draws} draws x 2 in {time.time() - t0:.0f}s")
        ok = mc.n >= MIN_N
        m = mc[ok]
        print(f"\n{mk} {block}: {int(ok.sum())} cells with n>={MIN_N}")
        print(f"  P(mean R <= 0):  median {m.p_le0.median():.3f}; share < 0.05: "
              f"{float((m.p_le0 < 0.05).mean()):.1%} (chance alone would give ~5% of a null grid);"
              f" share < 0.01: {float((m.p_le0 < 0.01).mean()):.1%}")
        print(f"  fixed-R max drawdown, permutation median: median across cells "
              f"{m.dd_med.median():.1f}R,"
              f" p95 across cells {m.dd_med.quantile(0.95):.1f}R")
        print(f"  1%-risk compounded max DD: median-cell median {m.cdd_med.median():.1%}, "
              f"median-cell p95 {m.cdd_p95.median():.1%}; share of cells with P(DD>10%) > 0.5: "
              f"{float((m.p_cdd10 > 0.5).mean()):.1%}; P(DD>20%) > 0.5: "
              f"{float((m.p_cdd20 > 0.5).mean()):.1%}")
        print(f"  1%-risk final equity multiple over the block (bootstrap): median cell "
              f"{m.eq_med.median():.3f}, 5th percentile of paths at the median cell "
              f"{m.eq_p5.median():.3f}; share of cells whose 5th percentile is below 1.0: "
              f"{float((m.eq_p5 < 1.0).mean()):.1%}")
        d = mc[(mc.entry == 20) & (mc.exit == 80) & (mc.hold == 5) & (mc.mult == 1.0)].iloc[0]
        print(f"  EA default: n {d.n:.0f} R {d.R:+.4f} P(<=0) {d.p_le0:.3f} CI [{d.ci5:+.3f}, "
              f"{d.ci95:+.3f}]  DD median {d.dd_med:.1f}R p95 {d.dd_p95:.1f}R  1%-risk DD median "
              f"{d.cdd_med:.1%} p95 {d.cdd_p95:.1%}  P(DD>10%) {d.p_cdd10:.2f}  equity median "
              f"{d.eq_med:.3f} p5 {d.eq_p5:.3f}")
        best = m.sort_values("p_le0").head(8)
        print("  8 cells with the lowest P(mean<=0):")
        print("    " + fmt(best, list(AXES) + ["n", "R", "p_le0", "ci5", "dd_med", "cdd_p95",
                                                "eq_med"]).replace("\n", "\n    "))
        print(f"  Multiplicity: {len(m)} cells were drawn; the minimum P over them is the minimum"
              f" of {len(m)} draws, not a p-value.")


# ------------------------------------------------------------------------------------------
# 3. cluster analysis
# ------------------------------------------------------------------------------------------
def daily_matrix(mk, block):
    """Sessions x cells matrix of R credited to the exit session, research block."""
    F = feed(mk)
    sw = sweep_block(mk, block)
    S = F["B"]["S"]
    M = np.zeros((S, len(sw)), np.float32)
    for i, row in sw.iterrows():
        cell = {a: row[a] for a in AXES}
        t = C.cell_trades(F["B"], F["masks"][block], cell)
        if len(t):
            np.add.at(M[:, i], t.ex.to_numpy(), t.r.to_numpy())
    return sw, M[F["masks"][block] == 1]


def cluster(markets=LONG, corr_cut=0.7):
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    print("=" * 100)
    print("3. CLUSTER ANALYSIS -- how many distinct strategies does the grid contain?")
    print("   Cells clustered on the CORRELATION of their per-session R (research block), average")
    print(f"   linkage, cut where within-cluster correlation exceeds {corr_cut}.")
    print("=" * 100)
    V = {mk: sweep_block(mk, "validation") for mk in markets}
    for mk in markets:
        sw, M = daily_matrix(mk, "research")
        ok = (sw.n >= MIN_N).to_numpy()
        X = M[:, ok].astype(float)
        sd = X.std(axis=0)
        keep = sd > 0
        X = X[:, keep]
        sub = sw[ok].iloc[np.where(keep)[0]].reset_index(drop=True)
        Cm = np.corrcoef(X.T)
        Cm = np.clip(np.nan_to_num(Cm), -1, 1)
        D = 1.0 - Cm
        np.fill_diagonal(D, 0.0)
        Z = linkage(squareform(D, checks=False), method="average")
        lab = fcluster(Z, t=1.0 - corr_cut, criterion="distance")
        sub["cluster"] = lab
        nclu = len(np.unique(lab))
        sizes = pd.Series(lab).value_counts()
        off = Cm[np.triu_indices_from(Cm, 1)]
        print(f"\n{mk}: {len(sub)} cells -> {nclu} clusters; largest {sizes.iloc[0]} cells; "
              f"median pairwise corr {np.median(off):.3f}, share of pairs > 0.7: "
              f"{float((off > 0.7).mean()):.1%}")
        # effective number of independent strategies, PCA style
        ev = np.linalg.eigvalsh(Cm)[::-1]
        ev = ev[ev > 0]
        print(f"  eigen-share: {int(np.searchsorted(np.cumsum(ev) / ev.sum(), 0.9) + 1)} "
              f"components explain 90% of the variance of {len(sub)} cells")
        q = sub.R.quantile(0.9)
        top = sub[sub.R >= q]
        print(f"  research top decile ({len(top)} cells) falls into "
              f"{top.cluster.nunique()} clusters")
        v = keyed(V[mk])
        sub["R_v"] = [v.R.get(k, np.nan) for k in cell_key(sub)]
        sub["n_v"] = [v.n.get(k, np.nan) for k in cell_key(sub)]
        g = sub.groupby("cluster").agg(
            cells=("R", "size"), R_is=("R", "mean"), R_v=("R_v", "mean"),
            pos_v=("R_v", lambda x: float((x > 0).mean())),
            entry=("entry", "median"), exit=("exit", "median"), hold=("hold", "median"),
            mult=("mult", "median"), n=("n", "median")).sort_values("R_is", ascending=False)
        big = g[g.cells >= 5].head(12)
        print("  clusters with >=5 cells, ranked by research R (validation read for the cluster):")
        print("    " + fmt(big.reset_index()).replace("\n", "\n    "))
        sub.to_csv(f"{OUT}/clusters_{mk}.csv", index=False)
        # k-means on the metric profile: where in parameter space do stable cells sit?
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
        feat = sub[["R", "pf", "win", "stop_share", "dd", "n"]].replace([np.inf, -np.inf],
                                                                         np.nan).fillna(0)
        Xf = StandardScaler().fit_transform(feat)
        km = KMeans(n_clusters=4, n_init=10, random_state=0).fit(Xf)
        sub["kprofile"] = km.labels_
        gk = sub.groupby("kprofile").agg(
            cells=("R", "size"), R_is=("R", "mean"), R_v=("R_v", "mean"), pf=("pf", "median"),
            win=("win", "median"), n=("n", "median"), entry=("entry", "median"),
            exit=("exit", "median"), hold=("hold", "median"),
            mult=("mult", "median")).sort_values("R_is", ascending=False)
        print("  k-means (k=4) on the metric profile [R, PF, win, stop share, DD, n]:")
        print("    " + fmt(gk.reset_index()).replace("\n", "\n    "))
        # Jaccard of the ENTRY sets along the entry-threshold axis at the default geometry
        F = feed(mk)
        sets = {}
        for e in C.GRID["entry"]:
            cell = dict(C.DEFAULT, entry=e)
            t = C.cell_trades(F["B"], F["masks"]["research"], cell)
            sets[e] = set(t.ent.tolist())
        line = "  entry-set Jaccard vs the default (20) along the entry axis: "
        line += "  ".join(f"{e:g}:{len(sets[e] & sets[20.0]) / len(sets[e] | sets[20.0]):.2f}"
                          for e in C.GRID["entry"])
        print(line)


# ------------------------------------------------------------------------------------------
# 4. walk-forward
# ------------------------------------------------------------------------------------------
def walkforward(markets=LONG, train_years=3, anchored=False):
    print("=" * 100)
    mode = 'anchored' if anchored else 'rolling ' + str(train_years) + '-year'
    print(f"4. WALK-FORWARD -- {mode}"
          f" train, one calendar year out of sample, selection re-run inside every fold")
    print("   Three selectors: best cell by R (n>=30), best cell by PLATEAU (neighbour mean), and")
    print("   the EA default held fixed. WFE = out-of-sample R / in-sample R of the chosen cell.")
    print("=" * 100)
    for mk in markets:
        F = feed(mk)
        s = F["s"]
        years = np.array(pd.DatetimeIndex(s["date"]).year)
        yrs = sorted(set(years))
        rows = []
        oos = {"best": [], "plateau": [], "default": []}
        for Y in yrs[train_years:]:
            lo = yrs[0] if anchored else Y - train_years
            tr = ((years >= lo) & (years < Y)).astype(np.int64)
            te = (years == Y).astype(np.int64)
            if te.sum() < 100:
                continue
            sw = C.sweep(F["B"], tr)
            sw["plateau"] = neighbour_mean(sw)
            ok = sw.n >= MIN_N
            picks = {"best": sw[ok].sort_values("R", ascending=False).iloc[0],
                     "plateau": sw[ok].sort_values("plateau", ascending=False).iloc[0],
                     "default": default_row(sw)}
            for name, p in picks.items():
                cell = {a: p[a] for a in AXES}
                t = C.cell_trades(F["B"], te, cell)
                m = C.metrics(t, int(te.sum()))
                oos[name].append(t.assign(year=Y))
                rows.append(dict(market=mk, year=Y, selector=name, **cell, n_is=int(p.n),
                                 R_is=float(p.R), n_oos=m["n"], R_oos=m["R"], pf_oos=m["pf"],
                                 wfe=(m["R"] / p.R) if p.R else np.nan))
        df = pd.DataFrame(rows)
        df.to_csv(f"{OUT}/walkforward_{mk}_{'anch' if anchored else 'roll'}.csv", index=False)
        print(f"\n{mk}")
        for name in ("best", "plateau", "default"):
            d = df[df.selector == name]
            print(f"  {name}:")
            print("    " + fmt(d, ["year"] + list(AXES) + ["n_is", "R_is", "n_oos", "R_oos",
                                                          "pf_oos", "wfe"]).replace("\n", "\n    "))
            allt = pd.concat(oos[name])
            r = allt.r.to_numpy()
            g = r[r > 0].sum()
            l = -r[r <= 0].sum()
            print(f"    concatenated OOS: n {len(r)} R {r.mean():+.4f} PF "
                  f"{g / l if l else np.inf:.3f} win {(r > 0).mean():.1%}; years positive "
                  f"{int((d.R_oos > 0).sum())}/{len(d)}; median WFE {d.wfe.median():.2f}")


# ------------------------------------------------------------------------------------------
# 5. judge: the reserved blocks, read once
# ------------------------------------------------------------------------------------------
def judge(cons=None):
    print("=" * 100)
    print("5. JUDGE -- reserved blocks read ONCE for three pre-declared cells: the EA default, the")
    print("   two-feed top-100 consensus, and the best two-feed PLATEAU cell. Matched control =")
    print("   random sessions with the identical stop, exit rule and hold (1,000 draws).")
    print("=" * 100)
    j = pd.read_csv(f"{OUT}/two_feed_research.csv")
    ok = (j.n_q >= MIN_N) & (j.n_d >= MIN_N)
    j["minR"] = np.minimum(j.R_q, j.R_d)
    if cons is None:
        top = j[ok].sort_values("minR", ascending=False).head(100)
        cons = {a: float(top[a + "_q"].mode().iloc[0]) for a in AXES}
    Rq = sweep_block("US100", "research")
    Rd = sweep_block("US30", "research")
    Rq["plateau"] = neighbour_mean(Rq)
    Rd["plateau"] = neighbour_mean(Rd)
    a = keyed(Rq)
    b = keyed(Rd)
    jj = a.join(b, lsuffix="_q", rsuffix="_d")
    jj["minplat"] = np.minimum(jj.plateau_q, jj.plateau_d)
    okk = (jj.n_q >= MIN_N) & (jj.n_d >= MIN_N)
    pl = jj[okk].sort_values("minplat", ascending=False).iloc[0]
    plateau = {a_: float(pl[a_ + "_q"]) for a_ in AXES}
    plateau["hold"] = int(plateau["hold"])
    cons["hold"] = int(cons["hold"])
    cands = {"EA default": dict(C.DEFAULT), "consensus": cons, "plateau": plateau}
    print("cells:", cands)
    print("Multiplicity: 3 cells read on each reserved block; the consensus and plateau cells were")
    print("chosen from 2,352 on the research blocks, the default was chosen by the author.")
    blocks = [("US100", "research"), ("US100", "validation"), ("US100", "test"),
              ("US30", "research"), ("US30", "validation"), ("US30", "test"),
              ("NQ", "research"), ("NQ", "locked"),
              ("US30_ISO", "iso_pre2026"), ("US30_ISO", "iso_2026")]
    rows = []
    for mk, blk in blocks:
        F = feed(mk)
        mask = F["masks"][blk]
        s = F["s"]
        sel = s[mask == 1]
        drift = float((sel.cl.iloc[-1] - sel.cl.iloc[0]) / sel.rng.median()) if len(sel) else np.nan
        for name, cell in cands.items():
            t = C.cell_trades(F["B"], mask, cell)
            m = C.metrics(t, int(mask.sum()))
            ctl = C.matched_control(F["B"], mask, cell, n_draws=1000, seed=1)
            rows.append(dict(market=mk, block=blk, cell=name, sessions=int(mask.sum()),
                             index_move_in_ranges=drift, **m, **ctl))
    df = pd.DataFrame(rows)
    df.to_csv(f"{OUT}/judge.csv", index=False)
    for name in cands:
        print(f"\n{name}: {cands[name]}")
        d = df[df.cell == name]
        print("  " + fmt(d, ["market", "block", "sessions", "n", "R", "pts", "pf", "win", "sharpe",
                             "dd", "stop_share", "ctrl_mean", "p",
                             "index_move_in_ranges"]).replace("\n", "\n  "))
    print("\nCOST STRESS on the test-type blocks (R per trade at 0x / 1x / 1.5x / 2x the assumed")
    print("spread+slippage; bid/ask is in none of these feeds so the 1x is itself an assumption):")
    for mk, blk in (("US100", "test"), ("US30", "test"), ("NQ", "locked"),
                    ("US30_ISO", "iso_2026")):
        line = f"  {mk:<9} {blk:<12}"
        for name, cell in cands.items():
            vals = []
            for cm in (0.0, 1.0, 1.5, 2.0):
                F = feed(mk, cm)
                t = C.cell_trades(F["B"], F["masks"][blk], cell)
                vals.append(float(t.r.mean()) if len(t) else np.nan)
            line += f" | {name}: " + " ".join(f"{v:+.3f}" for v in vals)
        print(line)
    print("\nEXIT SPLIT on US100 test and US30 test for the EA default (net R by exit reason):")
    for mk in LONG:
        F = feed(mk)
        t = C.cell_trades(F["B"], F["masks"]["test"], C.DEFAULT)
        for st, lab in ((1, "stop"), (0, "rule/clock")):
            sub = t[t.stopped == st]
            print(f"  {mk} {lab:<10} n {len(sub):>4}  sum R {sub.r.sum():+.2f}  mean R "
                  f"{sub.r.mean() if len(sub) else np.nan:+.3f}")


def main(stage="all"):
    t0 = time.time()
    cons = None
    if stage in ("stability", "all"):
        cons = stability()
    if stage in ("montecarlo", "all"):
        montecarlo()
    if stage in ("cluster", "all"):
        cluster()
    if stage in ("walkforward", "all"):
        walkforward(anchored=False)
        walkforward(anchored=True)
    if stage in ("judge", "all"):
        judge(cons)
    print(f"\n[{time.time() - t0:.0f}s]")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
