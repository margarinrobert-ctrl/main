"""Combinatorial purged CV done properly: the configuration is RE-SELECTED on
each split's training groups and scored on its held-out groups, then the blocks
are reassembled into distinct backtest paths. A fixed-parameter CPCV is
degenerate - every path is the whole sample - so the selection has to happen
inside the split for the number to mean anything.
"""
import numpy as np, pandas as pd, sys, itertools, json, importlib.util, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, cache, data as D

SK = "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/quant-strategy-lab/scripts/"
s = importlib.util.spec_from_file_location("sk_splits", SK + "splits.py")
SP = importlib.util.module_from_spec(s); s.loader.exec_module(SP)

df = D.load("NAS"); B = cache.build(df); R, H = D.blocks(df)
sess = np.unique(df.sess.values[R]); n = len(sess)
GRID = list(itertools.product([50, 89, 144], [10, 15, 25], [1.0, 1.5, 2.0],
                              [2.0, 3.5], [10, 15, 25], [4, 8, 12]))
NG, NT = 6, 2

print("=" * 112)
print(f"17. COMBINATORIAL PURGED CV - {len(GRID)} configurations, {NG} groups, "
      f"{NT} test groups = {len(list(itertools.combinations(range(NG), NT)))} splits, "
      f"{SP.n_paths(NG, NT)} reconstructable paths")
print("    The configuration is re-selected inside every split, so the number prices in the choosing.")
print("=" * 112)

for tm in ("barclose", "intrabar"):
    books = {}
    for cfg in GRID:
        te, mp, st, tg, ta, to = cfg
        I, p = cache.indicators(df, B, trend_ema=te, min_pullback=mp, atr_stop=st,
                                atr_target=tg, trail_arm=ta, trail_offset=to)
        (lo, sh), _ = nqs.conditions(df, I, p)
        tr = nqs.simulate(df, I, p, lo & R, sh & R, trail_mode=tm, order="adverse")
        if len(tr) >= 100:
            books[cfg] = (tr.sess.values, tr.net_pts.values)
    groups = np.array_split(np.arange(n), NG)
    gsess = [set(sess[g]) for g in groups]
    split_res = {}
    for split_i, (tr_i, te_i) in enumerate(SP.combinatorial_purged_cv(
            n, n_groups=NG, n_test_groups=NT, label_horizon=5, embargo_pct=0.01)):
        train_s, best, bv = set(sess[tr_i]), None, -np.inf
        for cfg, (bs, net) in books.items():
            m = np.isin(bs, list(train_s))
            if m.sum() < 60: continue
            if net[m].mean() > bv: bv, best = net[m].mean(), cfg
        if best is None: continue
        bs, net = books[best]
        for g in range(NG):
            if not gsess[g] & set(sess[te_i]): continue
            m = np.isin(bs, list(gsess[g]))
            split_res[(split_i, g)] = (net[m], bv, best)
    paths = SP.cpcv_paths(n, NG, NT)
    vals, sharpes = [], []
    for pth in paths:
        chunks = [split_res[(si, g)][0] for si, g in pth if (si, g) in split_res]
        if not chunks: continue
        allp = np.concatenate(chunks)
        vals.append(allp.mean())
        sharpes.append(allp.mean() / allp.std(ddof=1) * np.sqrt(len(allp)) if allp.std(ddof=1) > 0 else 0.0)
    vals, sharpes = np.array(vals), np.array(sharpes)
    is_means = np.array([v[1] for v in split_res.values()])
    print(f"\n  --- {tm}/adverse   {len(books)} eligible configurations")
    print(f"    in-sample expectancy of the SELECTED config, per split : "
          f"median {np.median(is_means):+.2f} pts/trade")
    print(f"    out-of-sample expectancy per reconstructed path        : "
          f"{'  '.join(f'{v:+.2f}' for v in vals)}")
    print(f"    across {len(vals)} paths: median {np.median(vals):+.2f}  "
          f"min {vals.min():+.2f}  max {vals.max():+.2f}  "
          f"{(vals>0).mean():.0%} profitable")
    print(f"    IS -> OOS decay: {np.median(is_means):+.2f} -> {np.median(vals):+.2f} pts/trade "
          f"({np.median(is_means)-np.median(vals):+.2f})")
    cfgs = pd.Series([str(v[2]) for v in split_res.values()]).value_counts()
    print(f"    configuration stability: the modal pick wins {cfgs.iloc[0]/cfgs.sum():.0%} of splits")
    json.dump(dict(paths=[float(v) for v in vals], median_oos=float(np.median(vals)),
                   median_is=float(np.median(is_means)), frac_profitable=float((vals > 0).mean())),
              open(f"/home/user/main/docs/nqscalp/cpcv_{tm}.json", "w"), indent=2)
print("\n  written: cpcv_barclose.json, cpcv_intrabar.json")
