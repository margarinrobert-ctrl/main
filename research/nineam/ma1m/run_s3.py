"""THE ONE HOLDOUT READ of the four declared picks, each against its nulls, with deflation."""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import m_core as M
import na_core as N

B = M.Base()
z = np.load(os.path.join(HERE, "s1_sweep.npz")); meta = z["meta"]
picks = json.load(open(os.path.join(HERE, "s2_picks.json")))
ob = json.load(open(os.path.join(HERE, "o1_best.json")))["best"]

def from_row(r):
    pid, rem = r // 48, r % 48
    kf, ks, nf, ns = meta[pid]
    return M.TYPES[kf], int(nf), M.TYPES[ks], int(ns), rem // 3, rem % 3

cells = []
for k, r in picks.items():
    kf, nf, ks, ns, g, x = from_row(r)
    cells.append((k, kf, nf, ks, ns, M.cfg_dict(g, x)))
q = dict(M.P0, ma_mode="state" if ob["gate_mode"] == "state" else "xcross", x_mode=ob["exit"])
if ob["gate_mode"] != "state": q["cross_min"] = ob["cross_min"]
cells.append(("D Optuna best (research t)", ob["fast_type"], ob["fast_len"], ob["slow_type"], ob["slow_len"], q))

hold_days = np.setdiff1d(B.sessions, B.res_days)
rng = np.random.default_rng(11)
c0 = B.c
rhi, rlo, _ = c0.ranges(M.P0["range_end"])
elig = np.flatnonzero((c0.mod >= M.P0["open_m"]) & (c0.mod < M.P0["end_m"]) & np.isfinite(rhi) & np.isfinite(rlo))
eday = c0.day[elig]
allb = np.isin(c0.day[B.sig], hold_days)

def pf(r):
    w = r > 0
    return r[w].sum() / -r[~w].sum() if (~w).any() and r[~w].sum() < 0 else np.inf

rows = []
for name, kf, nf, ks, ns, cfg in cells:
    c = M.ctx_for(B, kf, nf, ks, ns)
    tr = c.trades(cfg)
    atrf = c.atr_frame(14)
    res = {}
    for blk, days in [("research", B.res_days), ("holdout", hold_days)]:
        t = tr[np.isin(tr.eday.to_numpy(), days)]
        r = t.pct.to_numpy()
        res[blk] = dict(n=len(r), m=r.mean() if len(r) else np.nan, pf=pf(r) if len(r) else np.nan,
                        win=(r > 0).mean() if len(r) else np.nan)
    th = tr[np.isin(tr.eday.to_numpy(), hold_days)]
    rh = th.pct.to_numpy()
    # null 1: a random ENTRY bar in the same session window, same side, same exits (sorted draws)
    sigh, sdh = c.sigs(cfg); keep = np.isin(c.day[sigh], hold_days); sigh, sdh = sigh[keep], sdh[keep]
    pool = {d: elig[eday == d] for d in np.unique(c.day[sigh])}
    ent_null = []
    for _ in range(400):
        bb = [rng.choice(pool[c.day[b]]) for b in sigh if len(pool.get(c.day[b], []))]
        ss = [s for b, s in zip(sigh, sdh) if len(pool.get(c.day[b], []))]
        o = np.argsort(bb, kind="stable")
        t = c._walk_sig(cfg, atrf, np.asarray(bb)[o], np.asarray(ss)[o])
        ent_null.append(np.nan if t is None else t.pct.mean())
    ent_null = np.asarray(ent_null)
    # null 2: a RANDOM GATE of the same selectivity on the holdout breaks, re-simulated end to end
    sa, sda = B.sig[allb], B.side[allb]
    frac = len(sigh) / max(len(sa), 1)
    gate_null = []
    for _ in range(400):
        k = rng.random(len(sa)) < frac
        t = c._walk_sig(cfg, atrf, sa[k], sda[k]) if k.sum() >= 2 else None
        gate_null.append(np.nan if t is None or len(t) == 0 else t.pct.mean())
    gate_null = np.asarray(gate_null)
    bo = np.asarray(N.boot_edge(th.assign(_day=th.eday), n=4000, seed=3, col="pct")) if len(th) > 1 else np.array([np.nan])
    mde = N.mde(rh.std(ddof=1), len(rh)) if len(rh) > 1 else np.nan
    rows.append(dict(pick=name, cfg=f"{kf}{nf}/{ks}{ns} {cfg['ma_mode']}{'' if cfg['ma_mode']=='state' else cfg.get('cross_min')} exit={cfg['x_mode']}",
                     nR=res["research"]["n"], pfR=res["research"]["pf"], mR=res["research"]["m"],
                     nH=res["holdout"]["n"], pfH=res["holdout"]["pf"], mH=res["holdout"]["m"], winH=res["holdout"]["win"],
                     p_entry=float(np.nanmean(ent_null >= rh.mean())) if len(rh) else np.nan,
                     p_gate=float(np.nanmean(gate_null >= rh.mean())) if len(rh) else np.nan,
                     boot_le0=float(np.mean(bo <= 0)), mde=mde, ratio=rh.mean() / mde if mde == mde else np.nan))
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print("=" * 120); print("THE ONE HOLDOUT READ -- second half of the 92 sessions, never used for any selection"); print("=" * 120)
for _, r in df.iterrows():
    print(f"\n  {r.pick}\n    {r.cfg}")
    print(f"    research n {r.nR:3d}  PF {r.pfR:6.2f}  %/tr {r.mR:+.4f}   ->   HOLDOUT n {r.nH:3d}  PF {r.pfH:6.2f}  "
          f"%/tr {r.mH:+.4f}  win {r.winH:.2f}")
    print(f"    holdout vs random ENTRY p {r.p_entry:.3f} | vs random GATE p {r.p_gate:.3f} | "
          f"bootstrap P(mean<=0) {r.boot_le0:.3f} | delivered/MDE {r.ratio:.2f}")
df.to_csv(os.path.join(HERE, "s3_holdout.csv"), index=False)
looks = 1150128 + 3000
print(f"\n  looks taken: {looks:,}  -> E[max t | pure noise] {N.e_max_normal(looks):.3f}; detection needs 2.802")
