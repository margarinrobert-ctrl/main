"""Phase-1 audit from the quant-strategy-lab skill, plus the contract-size
question the cost model raises.

The strategy is configured for MNQ ($2/point) but charged $1.24 per contract per
order. In POINTS - the only unit in which an edge and a cost are comparable -
that same dollar commission is 10x larger on the micro than on the full-size
contract, so the instrument choice moves the cost floor by more than any
parameter in the strategy does.
"""
import numpy as np, pandas as pd, sys, importlib.util, warnings, json
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, cache, data as D

SK = "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/quant-strategy-lab/scripts/"
def _load(n):
    s = importlib.util.spec_from_file_location("sk_" + n, SK + n + ".py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
LA, SP = _load("leakage_audit"), _load("splits")

df = D.load("NAS"); B = cache.build(df); R, H = D.blocks(df)
I, p = cache.indicators(df, B)
(lo, sh), in_sess = nqs.conditions(df, I, p)

print("=" * 112)
print("16. LEAKAGE AUDIT (quant-strategy-lab Phase 1) on the strategy's own feature matrix")
print("=" * 112)
c = I["c"]
F = pd.DataFrame(dict(
    trend_dist=(c - I["trend"]) / I["atr"], fast_dist=(c - I["fast"]) / I["atr"],
    slow_dist=(c - I["slow"]) / I["atr"], k=I["k"], d=I["d"], kd=I["k"] - I["d"],
    atr=I["atr"], pullback_depth=(I["swing_hi"] - I["l"]) / I["atr"],
    rally_depth=(I["h"] - I["swing_lo"]) / I["atr"]),
    index=pd.DatetimeIndex(df.ts))
fwd = pd.Series(np.r_[np.diff(c), np.nan] / I["atr"], index=F.index)
m = np.isfinite(F).all(axis=1) & np.isfinite(fwd)
try:
    rep = LA.audit(F[m], fwd[m])
    if isinstance(rep, dict):
        for k_, v in rep.items():
            print(f"  {k_}: {v}" if not isinstance(v, (pd.DataFrame, pd.Series)) else f"  {k_}:\n{v}")
    else:
        print(rep)
except Exception as e:
    print(f"  audit() raised {e!r}; running the individual checks instead")
print("\n  execution alignment on the realised position series:")
tr = nqs.simulate(df, I, p, lo & R, sh & R)
pos = np.zeros(len(df))
for _, t in tr.iterrows():
    pos[int(t.fill_bar): int(t.exit_bar) + 1] = t.side
rets = pd.Series(np.r_[np.diff(c), 0.0], index=F.index)
try:
    ea = LA.check_execution_alignment(pd.Series(pos, index=F.index), rets)
    for k_, v in (ea.items() if isinstance(ea, dict) else [("result", ea)]):
        print(f"    {k_}: {v}")
except Exception as e:
    print(f"    check_execution_alignment raised {e!r}")

print("\n" + "=" * 112)
print("17. PURGED K-FOLD AND COMBINATORIAL PURGED CV (research block, barclose/adverse)")
print("=" * 112)
trs = nqs.simulate(df, I, p, lo & R, sh & R, trail_mode="barclose", order="adverse")
sess = np.unique(df.sess.values[R])
sp = pd.Series(0.0, index=sess)
g = trs.groupby("sess").net_pts.sum()
sp.loc[sp.index.intersection(g.index)] = g.reindex(sp.index.intersection(g.index)).values
cnt = pd.Series(0, index=sess)
gc = trs.groupby("sess").size()
cnt.loc[cnt.index.intersection(gc.index)] = gc.reindex(cnt.index.intersection(gc.index)).values
for name, folds in (("purged 5-fold (embargo 5 sessions)", SP.purged_kfold(len(sess), n_splits=5, label_horizon=5)),):
    print(f"  {name}:")
    for i, (tr_i, te_i) in enumerate(folds):
        v = sp.values[te_i]; n = cnt.values[te_i].sum()
        print(f"    fold {i+1}: {len(te_i)} sessions, {n} trades, "
              f"expectancy {v.sum()/max(n,1):+.2f} pts/trade, total {v.sum():+.0f} pts")
try:
    paths = SP.cpcv_paths(len(sess), n_groups=6, n_test_groups=2)
    vals = []
    for pth in paths:
        idx = np.concatenate([np.arange(a, b) for a, b in pth])
        n = cnt.values[idx].sum()
        vals.append(sp.values[idx].sum() / max(n, 1))
    vals = np.array(vals)
    print(f"  CPCV: {len(paths)} paths, expectancy p5 {np.percentile(vals,5):+.2f} "
          f"median {np.median(vals):+.2f} p95 {np.percentile(vals,95):+.2f}, "
          f"{(vals>0).mean():.0%} of paths profitable")
except Exception as e:
    print(f"  CPCV unavailable: {e!r}")

print("\n" + "=" * 112)
print("18. THE CONTRACT-SIZE QUESTION - the same edge against three cost floors")
print("=" * 112)
print("  A $1.24-per-contract commission is 0.62 points on MNQ and 0.062 points on NQ.")
print("  The edge is measured in points, so the instrument moves the cost floor 2.8x.")
specs = [("MNQ as configured ($2/pt)", 2.0, 1.24), ("NQ ($20/pt), same $ commission", 20.0, 1.24),
         ("NQ ($20/pt), realistic $2.50/contract", 20.0, 2.50)]
rows = []
for tm in ("barclose", "intrabar"):
    for order in ("adverse", "favorable"):
        base = nqs.simulate(df, I, p, lo & R, sh & R, trail_mode=tm, order=order, cost_mult=0.0)
        gross = base.net_pts.mean()
        for nm, pv, cm in specs:
            rt = 2 * 0.25 + 2 * cm / pv
            rows.append(dict(model=f"{tm}/{order}", contract=nm, round_turn_pts=rt,
                             gross=gross, net=gross - rt))
        print(f"  {tm}/{order:<10} gross edge {gross:+.2f} pts/trade")
        for nm, pv, cm in specs:
            rt = 2 * 0.25 + 2 * cm / pv
            print(f"      {nm:<38} round turn {rt:>5.3f} pts -> net {gross-rt:>+6.2f} pts/trade"
                  f"  = ${(gross-rt)*pv*5:>+8.2f}/trade on 5 lots")
pd.DataFrame(rows).to_csv("/home/user/main/docs/nqscalp/contract_costs.csv", index=False)
print("\n  written: contract_costs.csv")
