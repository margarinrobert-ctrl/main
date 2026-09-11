"""M3 -- THE ONE LOCKED READ on US100 and US30, then the RESERVED FORWARD READ on US30_ISO.

Everything before this file was research-only. Multiplicity is stated before any number. Each
finalist faces the same matched control it faced on research, a day-block BOOTSTRAP for the edge
and a PERMUTATION for the path, and then -- once, last -- US30_ISO, whose 48,937 bars post-date
both LONG feeds and which no search here has touched.

CROSS-MARKET FREEZE is run in both directions: a cell chosen on US100 read on the WHOLE of US30 and
vice versa. A market that chose nothing is worth more than a second block of the market that did
(STUDY_V12, STUDY_V38, STUDY_VP_TPO_NEXT).
"""
import os, sys, json
import numpy as np, pandas as pd
from scipy.stats import skew, kurtosis

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
import vecore as V, ve_markets as M
import gates

RNG = np.random.default_rng(4242)
pd.set_option("display.width", 235)
print(__doc__)
MK = ("US100", "US30")
DS = {(k, sm): M.build(k, sess=sm) for k in ("US100", "US30", "US30_ISO") for sm in ("ny", "utc")}
T = pd.read_parquet("results/vwapema/m2_trials.parquet")
FN = pd.read_csv("results/vwapema/m2_finalists.csv")
N_LOOKS = len(T) + 40           # + the ~40 research looks in M1
L = lambda s: print("\n" + "=" * 116 + f"\n{s}\n" + "=" * 116)

PKEYS = list(V.PARAMS)


def cfg_of(row):
    p = {k: (int(row[k]) if isinstance(V.PARAMS[k], int) else float(row[k])) for k in PKEYS}
    tg = row.get("tgt_R", 0.0)
    if not row.get("use_tgt", True) or not np.isfinite(float(tg)):
        tg = 0.0
    return dict(p=p, side=int(row["side"]), sess=str(row["sess"]),
                tgt_R=float(tg), flatten=bool(row["flatten"]))


CFG = {}
for _, r in FN.iterrows():
    CFG[(r.feed, f"Optuna {r.study}")] = cfg_of(r)
PUB = dict(p=dict(V.PARAMS), side=1, sess="ny", tgt_R=3.0, flatten=False)
PUBS = dict(p=dict(V.PARAMS), side=-1, sess="ny", tgt_R=3.0, flatten=False)
for k in MK:
    CFG[(k, "As published L")] = PUB
    CFG[(k, "As published S")] = PUBS


def trades(mk, cfg, blk=None):
    D = DS[(mk, cfg["sess"])]
    sig, _ = V.triggers(D, side=cfg["side"], p=cfg["p"])
    t = M.run(D, sig, side=cfg["side"], tgt_R=cfg["tgt_R"], flatten=cfg["flatten"], p=cfg["p"])
    t["date"] = pd.DatetimeIndex(t.ts).normalize()
    return t if blk is None else t[t.blk == blk].reset_index(drop=True)


def control(mk, cfg, n_target, blk, draws=300):
    D = DS[(mk, cfg["sess"])]
    sel = D["rth"] if blk is None else (D["rth"] & (D["blk"] == blk))
    idx = np.flatnonzero(sel)
    rate = min(1.0, n_target / max(len(idx), 1))
    out = []
    for _ in range(draws):
        g = np.zeros(D["n"], bool); g[idx[RNG.random(len(idx)) < rate]] = True
        t = M.run(D, g, side=cfg["side"], tgt_R=cfg["tgt_R"], flatten=cfg["flatten"], p=cfg["p"])
        if blk is not None:
            t = t[t.blk == blk]
        if len(t) >= 20:
            out.append((t.R.mean(), t.pct.mean()))
    return np.array(out) if out else np.zeros((0, 2))


def dayboot(t, col="pct", n=2000):
    if len(t) < 30:
        return np.nan
    d = t.groupby("date")[col].apply(list)
    arr = list(d.values)
    m = np.array([np.mean(np.concatenate([arr[i] for i in RNG.integers(0, len(arr), len(arr))]))
                  for _ in range(n)])
    return float((m <= 0).mean())


def permdd(t, n=2000):
    if len(t) < 30:
        return np.nan, np.nan, np.nan
    r = t.R.to_numpy()
    cum = np.cumsum(r); real = float(np.max(np.maximum.accumulate(cum) - cum))
    dd = []
    for _ in range(n):
        c = np.cumsum(RNG.permutation(r))
        dd.append(np.max(np.maximum.accumulate(c) - c))
    dd = np.array(dd)
    return real, float((dd <= real).mean()), float(np.percentile(dd, 99))


L(f"M3.1  THE ONE LOCKED READ.  MULTIPLICITY: {len(T):,} Optuna trials + ~40 M1 looks = {N_LOOKS:,}")
rows = []
for (mk, nm), cfg in CFG.items():
    for blk, bn in ((0, "research"), (1, "LOCKED")):
        t = trades(mk, cfg, blk); st = V.stats(t)
        if st["n"] < 20:
            continue
        c = control(mk, cfg, st["n"], blk)
        rows.append(dict(feed=mk, cell=nm, block=bn, n=st["n"], R=st["R"], pct=st["pct"],
                         pf=st["pf"], win=st["win"], totR=st["totR"], ret_dd=st["ret_dd"],
                         ctl_R=float(np.median(c[:, 0])) if len(c) else np.nan,
                         p_ctl=float((c[:, 0] >= st["R"]).mean()) if len(c) else np.nan,
                         boot_p=dayboot(t)))
A = pd.DataFrame(rows)
print(A.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
A.to_csv("results/vwapema/m3_locked.csv", index=False)
print("\n`p_ctl` is against a random New York bar with the identical geometry; `boot_p` is")
print("P(mean percent-of-price <= 0) from a day-block bootstrap. They are different questions and")
print("a rule can clear one and fail the other (STUDY_V15_BOOK).")

L("M3.2  PATH RISK -- permutation of the realised sequence")
rows = []
for (mk, nm), cfg in CFG.items():
    for blk, bn in ((0, "research"), (1, "LOCKED")):
        t = trades(mk, cfg, blk)
        real, pct, p99 = permdd(t)
        if np.isnan(pct):
            continue
        rows.append(dict(feed=mk, cell=nm, block=bn, n=len(t), realised_dd=round(real, 2),
                         percentile=round(pct, 3), mc_p99=round(p99, 2),
                         ratio=round(p99 / max(real, 1e-9), 2)))
P = pd.DataFrame(rows)
print(P.to_string(index=False))
P.to_csv("results/vwapema/m3_path.csv", index=False)
print("\nSize for the p99, not for the backtest. A low percentile means the realised path was")
print("LUCKIER than a reshuffle of its own trades.")

L("M3.3  DEFLATED SHARPE at the counted trial number")
rows = []
# var_trials must be the variance of the TRIAL SHARPES, per-observation and un-annualised.
sr_pool = T.loc[T.n_res >= 100, "sharpe_res"].to_numpy(float)
sr_pool = sr_pool[np.isfinite(sr_pool)]
vt = float(np.var(sr_pool))
print(f"  var_trials measured over {len(sr_pool):,} trial per-trade Sharpes = {vt:.6f} "
      f"(sd {np.sqrt(vt):.4f}); E[max SR | null] over {N_LOOKS:,} looks = "
      f"{gates.expected_max_sharpe(vt, N_LOOKS):.4f}")
for (mk, nm), cfg in CFG.items():
    t = trades(mk, cfg)
    if len(t) < 60:
        continue
    r = t.pct.to_numpy()
    sr = float(r.mean() / max(r.std(ddof=1), 1e-12))
    d = gates.deflated_sharpe(sr, len(r), N_LOOKS, vt, float(skew(r)), float(kurtosis(r, fisher=False)))
    e = gates.expected_max_sharpe(vt, N_LOOKS)
    rows.append(dict(feed=mk, cell=nm, n=len(r), sharpe_per_trade=round(sr, 4),
                     dsr=round(float(d if np.isscalar(d) else d.get("dsr", np.nan)), 4),
                     E_max_null=round(float(e), 4) if np.isfinite(e) else np.nan))
Dd = pd.DataFrame(rows)
print(Dd.to_string(index=False))
Dd.to_csv("results/vwapema/m3_dsr.csv", index=False)

L("M3.4  CORRELATION MATRICES")
print("(a) parameter -> research performance, over the scorable trial population, per feed")
ok = T[T.n_res >= 100]
for mk in MK:
    s = ok[ok.feed == mk]
    cols = PKEYS + ["tgt_R"]
    c = s[cols + ["R_res", "totR_res", "pf_res"]].corr(method="spearman")[["R_res", "totR_res", "pf_res"]]
    print(f"\n  --- {mk} (n={len(s)})")
    print(c.loc[cols].round(3).to_string())

print("\n(b) the cells' DAILY R against each other, whole sample")
dailies = {}
for (mk, nm), cfg in CFG.items():
    t = trades(mk, cfg)
    if len(t) < 60:
        continue
    dailies[f"{mk}|{nm}"] = t.groupby("date").R.sum()
Dm = pd.DataFrame(dailies).fillna(0.0)
print(Dm.corr().round(3).to_string())
Dm.corr().to_csv("results/vwapema/m3_corr_cells.csv")

print("\n(c) YEAR BY YEAR, R per trade")
rows = []
for (mk, nm), cfg in CFG.items():
    t = trades(mk, cfg)
    if len(t) < 60:
        continue
    g = t.groupby(pd.DatetimeIndex(t.ts).year).R.agg(["size", "mean"])
    for y, r in g.iterrows():
        rows.append(dict(feed=mk, cell=nm, year=int(y), n=int(r["size"]), R=round(float(r["mean"]), 3)))
Y = pd.DataFrame(rows)
print(Y.pivot_table(index="year", columns=["feed", "cell"], values="R").round(3).to_string())
Y.to_csv("results/vwapema/m3_years.csv", index=False)

L("M3.5  CROSS-MARKET FREEZE -- each cell on the market that had no part in choosing it")
rows = []
for (mk, nm), cfg in CFG.items():
    if nm.startswith("As published"):
        continue
    for other in ("US100", "US30"):
        if other == mk:
            continue
        t = trades(other, cfg); st = V.stats(t)
        c = control(other, cfg, st["n"], None)
        rows.append(dict(chosen_on=mk, cell=nm, read_on=other, n=st["n"], R=round(st["R"], 4),
                         pct=round(st["pct"], 4), pf=round(st["pf"], 3),
                         ctl_R=round(float(np.median(c[:, 0])), 4) if len(c) else np.nan,
                         p_ctl=round(float((c[:, 0] >= st["R"]).mean()), 3) if len(c) else np.nan))
X = pd.DataFrame(rows)
print(X.to_string(index=False))
X.to_csv("results/vwapema/m3_crossmarket.csv", index=False)

L("M3.6  THE RESERVED FORWARD BLOCK -- US30_ISO, read ONCE, never searched")
rows = []
for (mk, nm), cfg in CFG.items():
    t = trades("US30_ISO", cfg); st = V.stats(t)
    if st["n"] < 15:
        rows.append(dict(chosen_on=mk, cell=nm, n=st["n"], R=np.nan, pct=np.nan, pf=np.nan,
                         ctl_R=np.nan, p_ctl=np.nan, boot_p=np.nan)); continue
    c = control("US30_ISO", cfg, st["n"], None)
    rows.append(dict(chosen_on=mk, cell=nm, n=st["n"], R=round(st["R"], 4), pct=round(st["pct"], 4),
                     pf=round(st["pf"], 3),
                     ctl_R=round(float(np.median(c[:, 0])), 4) if len(c) else np.nan,
                     p_ctl=round(float((c[:, 0] >= st["R"]).mean()), 3) if len(c) else np.nan,
                     boot_p=round(dayboot(t), 3) if len(t) >= 30 else np.nan))
Z = pd.DataFrame(rows).drop_duplicates(subset=["cell", "chosen_on"])
print(Z.to_string(index=False))
Z.to_csv("results/vwapema/m3_forward.csv", index=False)
print("\nUS30_ISO is a DIFFERENT PROVIDER from US30_LONG (registry: median level gap 11.1 points on")
print("the US100 pair), it overlaps US30_LONG by eleven months at most, and 27,436 of its bars")
print("post-date every other file on this branch. It is the only genuinely forward read available.")
