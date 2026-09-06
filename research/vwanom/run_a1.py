"""A1 -- Phase 0 stated, GATE 1 measured and frozen, then the feature screen. No model yet.

The order is the architecture's, not a preference: the primary is scored ALONE and the number is
written down BEFORE any feature exists, because it is the only honest baseline a meta layer can
later be compared against.
"""
import os, sys, time, pickle
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vwapema"))
sys.path.insert(0, "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
import anomfeat as AF, vecore as V, ve_markets as M, two_sided as T
import gates

RNG = np.random.default_rng(5)
pd.set_option("display.width", 225)
os.makedirs("results/vwanom", exist_ok=True)
CACHE = "results/vwanom/feat_cache.pkl"
L = lambda s: print("\n" + "=" * 114 + f"\n{s}\n" + "=" * 114)
print(__doc__)

CFGS = {("US100", "SHORT"): T.SHORT_CFG, ("US30", "LONG"): T.LONG_CFG,
        ("US30_ISO", "LONG"): T.LONG_CFG, ("US30_ISO", "SHORT"): T.SHORT_CFG,
        ("US100", "LONG"): T.LONG_CFG, ("US30", "SHORT"): T.SHORT_CFG}

L("A1.0  PHASE 0 -- the mechanism, stated before anything is measured")
print("""  COUNTERPARTY: none named. Bhatti's rule is a pullback to an EMA inside a VWAP-filtered
  session with a volume spike and a candle shape. The paper offers no constrained flow and no risk
  transfer, so there is nobody whose hand is forced and nothing that says why the other side keeps
  taking it. FAMILY: neither. FREE PARAMETERS: ten, all tuned.
  CONSEQUENCE: this is a fitted pattern, not a mechanism-derived primary, and it carries the full
  deflation burden. The meta layer below cannot fix that -- it is measured to find out what it
  does, not to rescue anything.""")

L("A1.1  GATE 1 -- the raw primary alone, every event, no filter, no sizing, costs in")
rows = []
for (mk, sd), cfg in CFGS.items():
    D = M.build(mk, sess=cfg["sess"])
    sig, _ = V.triggers(D, side=cfg["side"], p=cfg["p"])
    t = M.run(D, sig, side=cfg["side"], tgt_R=cfg["tgt_R"], flatten=cfg["flatten"], p=cfg["p"])
    blocks = (("whole", None),) if mk == "US30_ISO" else (("research", 0), ("LOCKED", 1))
    for bn, b in blocks:
        tb = t if b is None else t[t.blk == b]
        if len(tb) < 30:
            continue
        r = tb.pct.to_numpy() / 100.0           # percent of entry price, as a return per event
        g = gates.primary_gate(r)
        rows.append(dict(feed=mk, cell=sd, block=bn, n=len(tb), R=round(tb.R.mean(), 4),
                         pct=round(tb.pct.mean(), 4), pf=round(V.stats(tb)["pf"], 3),
                         boot_p=round(float(g.get("bootstrap_p_one_sided", np.nan)), 3),
                         ci_lo=round(1e2 * float(g["net_mean_ci95"][0]), 4),
                         ci_hi=round(1e2 * float(g["net_mean_ci95"][1]), 4),
                         sharpe=round(float(g["sharpe_per_event"]), 4),
                         verdict=str(g.get("verdict", ""))[:24]))
G1 = pd.DataFrame(rows)
print(G1.to_string(index=False))
G1.to_csv("results/vwanom/a1_gate1.csv", index=False)
print("""
  GATE 1 VERDICT, in one line: the primary clears on the blocks it was CHOSEN on and on none of the
  others. That is a FAIL by the architecture's own rule, and the skill says plainly that a meta
  layer cannot create direction skill on a primary that fails here. The study continues in order to
  measure that claim on this family, and to answer the separate anomaly question, which does not
  require the primary to have an edge.""")

L("A1.2  THE FEATURE TABLE -- 51 causal columns in nine declared families")
t0 = time.time()
if os.path.exists(CACHE):
    BUNDLE = pickle.load(open(CACHE, "rb"))
    print(f"  loaded cache ({len(BUNDLE)} bundles)")
else:
    BUNDLE = {}
    for (mk, sd), cfg in CFGS.items():
        D, meta, feat, info = AF.build(mk, cfg)
        BUNDLE[(mk, sd)] = dict(meta=meta, feat=feat, info=info)
        print(f"  {mk:9s} {sd:5s}  events {len(meta):5d}  cols {feat.shape[1]}  "
              f"ffd d={info['ffd_d']}  hmm means {np.round(info['hmm_mu'], 6).tolist()}  "
              f"({time.time()-t0:.0f}s)")
    pickle.dump(BUNDLE, open(CACHE, "wb"))
FCOLS = list(BUNDLE[("US30", "LONG")]["feat"].columns)
print(f"  {len(FCOLS)} features: " + ", ".join(sorted({c.split('.')[0] for c in FCOLS})))

L("A1.3  TRUNCATION AUDIT -- recompute on history that ENDS at the event bar")
bad, ntest = AF.truncation_audit("US30", T.LONG_CFG, probes=10)
print(f"  {len(bad)} mismatches / {ntest} probes")
for b in bad[:5]:
    print("   ", b)
print("""  The fitted models (autoencoder, isolation forest, Mahalanobis, HMM, the FFD order) are
  excluded from this probe on purpose: refitting them on a truncated block changes the MODEL, not
  the causality. Their causality is enforced structurally instead -- each is fitted on the research
  block and only APPLIED forward.""")

L("A1.4  BASE RATES AND REDUNDANCY, measured ON THE EVENT BARS")
b = BUNDLE[("US30", "LONG")]
X = b["feat"]
print("  a feature that is near-constant on the trigger's own bars cannot filter it:")
near = [(c, float(X[c].std() / max(abs(X[c].mean()), 1e-9))) for c in FCOLS if X[c].notna().sum() > 50]
near = sorted(near, key=lambda z: z[1])[:6]
for c, v in near:
    print(f"    {c:18s} coefficient of variation {v:.4f}")
corr = X[FCOLS].corr(method="spearman").abs()
np.fill_diagonal(corr.values, 0.0)
pairs = (corr.stack().sort_values(ascending=False).head(10))
print("\n  the ten most redundant pairs (Spearman |rho| ON THE SIGNAL BARS):")
for (a, bb), v in pairs.items():
    if a < bb:
        print(f"    {a:18s} {bb:18s} {v:.4f}")
print(f"\n  exact duplicates (|rho| > 0.999): "
      f"{int(sum(1 for (a, bb), v in corr.stack().items() if a < bb and v > 0.999))}")

L("A1.5  IC SCREEN against a SHUFFLED TWIN -- research block only")
rows = []
for (mk, sd), bun in BUNDLE.items():
    if mk == "US30_ISO":
        continue
    m, X = bun["meta"], bun["feat"]
    tr = m.blk == 0
    if tr.sum() < 100:
        continue
    y = m.loc[tr, "pct"].to_numpy()
    ysh = RNG.permutation(y)
    for c in FCOLS:
        x = X.loc[tr, c].to_numpy()
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() < 80 or np.nanstd(x[ok]) == 0:
            continue
        ic = float(pd.Series(x[ok]).corr(pd.Series(y[ok]), method="spearman"))
        icsh = float(pd.Series(x[ok]).corr(pd.Series(ysh[ok]), method="spearman"))
        rows.append(dict(feed=mk, cell=sd, feat=c, fam=c.split(".")[0], n=int(ok.sum()),
                         ic=round(ic, 4), ic_shuffled=round(icsh, 4)))
S = pd.DataFrame(rows)
S.to_csv("results/vwanom/a1_ic.csv", index=False)
print(S.groupby("fam").agg(cols=("feat", "nunique"), mean_abs_ic=("ic", lambda s: np.abs(s).mean()),
                           mean_abs_shuffled=("ic_shuffled", lambda s: np.abs(s).mean()),
                           best=("ic", lambda s: s.abs().max())).round(4).to_string())
print("\n  top 12 by |IC| (research only), with the shuffled twin beside each:")
print(S.reindex(S.ic.abs().sort_values(ascending=False).index).head(12).to_string(index=False))
print("""
  READ THE SHUFFLED COLUMN, not the IC. On this branch the shuffled twin has outscored the real
  model in 83 of 120 research cells before now (`STUDY_V32_FLOW_ML`); a family whose mean |IC| sits
  at its own noise floor has nothing in it.""")
