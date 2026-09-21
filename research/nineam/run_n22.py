"""30-second US30: walk-forward, four Monte Carlos kept apart, and three correlation matrices.

The four Monte Carlos answer four different questions and are never pooled:
  EDGE       a day-block bootstrap of the per-trade result against ZERO
  PATH       a permutation of the realised trade sequence -- was the drawdown a draw?
  EXECUTION  a round turn drawn U(0.5x, 2x) PER TRADE, inside the walk
  DATA       price jitter with the ATR, both EMAs, the 09:00 range and the cross ALL recomputed

Read the last two LAST and do not mistake them for evidence: a 100-point barrier on a 2.29-point
round turn makes the execution band nearly free by arithmetic, so a tight band there says the
implementation is not fragile, never that the edge is real.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import na_core as N    # noqa: E402
import na_opt as O     # noqa: E402
import na_30s as T     # noqa: E402
import na_s30 as S     # noqa: E402
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '.'))
import daykey as DK  # noqa: E402  (pandas 3 made us the default resolution; see the module)

OUT = HERE
pd.set_option("display.width", 220)


def hd(t):
    print("\n" + "=" * 96); print(t); print("=" * 96)


c = S.ctx(tf=0.5, fix=1)
P = dict(S.CFG)
tr = c.trades(P)
sig_g, sd_g = c.sigs(P)
sig_all, sd_all = c.events(P["range_end"], P["side"], P["buf_atr"], P["atr_n"],
                           P["end_m"], P["open_m"])
atrf = c.atr_frame(P["atr_n"])
tdays = np.unique(c.day[sig_g])
print(f"rule: {len(tr)} trades on {len(tdays)} tradeable sessions, "
      f"{DK.from_day(tdays.min()).date()}"
      f"..{DK.from_day(tdays.max()).date()}")

# =============================================================================== 1  walk-forward
hd("1  WALK-FORWARD -- THE CONSTANTS FIXED, BESIDE A RE-CHOSEN ARM AND A RANDOM CELL")
GRID = []
for sp in (60.0, 100.0, 150.0):
    for tp in (60.0, 100.0, 150.0, 0.0):
        for be in (0.0, 43.0, 75.0):
            for xm in ("cross", "off"):
                GRID.append(dict(stop_pts=sp, tgt_pts=tp, be_pts=be, x_mode=xm))
print(f"  {len(GRID)} declared cells; E[max t | pure noise] over that many looks = "
      f"{N.e_max_normal(len(GRID)):.3f} against the 2.802 detection needs")


def cell(q):
    p = dict(P, **q)
    p["tgt_mode"] = "points" if q.get("tgt_pts", 0) > 0 else "none"
    p["be_off"] = 5.0 if q.get("be_pts", 0) > 0 else 0.0
    return p


def run_days(p, days):
    t = c.trades(p)
    return S.sub(t, days) if t is not None else None


K = 6
edges = np.array_split(tdays, K)
rows = []
rng = np.random.default_rng(5)
for k in range(1, K):
    trn = np.concatenate(edges[:k]); tst = edges[k]
    # fixed
    tf_ = run_days(P, tst)
    # re-chosen on the training window by total pct
    best, bsc = None, -np.inf
    for q in GRID:
        t = run_days(cell(q), trn)
        if t is None or len(t) < 8:
            continue
        sc = float(t["pct"].sum())
        if sc > bsc:
            bsc, best = sc, q
    tc_ = run_days(cell(best), tst) if best is not None else None
    # a random cell from the same grid
    tr_ = run_days(cell(GRID[rng.integers(len(GRID))]), tst)
    rows.append(dict(fold=k, test_n=len(tst),
                     fixed=float(tf_["pct"].sum()) if tf_ is not None and len(tf_) else 0.0,
                     fixed_tr=0 if tf_ is None else len(tf_),
                     rechosen=float(tc_["pct"].sum()) if tc_ is not None and len(tc_) else 0.0,
                     random=float(tr_["pct"].sum()) if tr_ is not None and len(tr_) else 0.0,
                     picked=str(best)))
wf = pd.DataFrame(rows)
print(wf.drop(columns=["picked"]).to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
print("\n  cells chosen per fold:")
for _, r in wf.iterrows():
    print(f"    fold {int(r.fold)}: {r.picked}")
print(f"\n  TOTAL over folds   fixed {wf.fixed.sum():+.4f}   re-chosen {wf.rechosen.sum():+.4f}   "
      f"random {wf.random.sum():+.4f}")
print(f"  folds positive     fixed {int((wf.fixed>0).sum())}/{len(wf)}   "
      f"re-chosen {int((wf.rechosen>0).sum())}/{len(wf)}   random {int((wf.random>0).sum())}/{len(wf)}")
wf.to_csv(os.path.join(OUT, "n22_walkforward.csv"), index=False)

# =============================================================================== 2  MC: EDGE
hd("2  MONTE CARLO 1 of 4 -- THE EDGE (day-block bootstrap against zero)")
is_d, oos_d = S.split_days(c, P, 0.5)
mc1 = []
for lab, dd in [("ALL", None), ("IS", is_d), ("OOS", oos_d)]:
    t = tr if dd is None else S.sub(tr, dd)
    b = np.asarray(N.boot_edge(t, n=4000, seed=1, col="pct"))
    mc1.append(dict(block=lab, n=len(t), mean=float(t["pct"].mean()),
                    lo=float(np.percentile(b, 2.5)), hi=float(np.percentile(b, 97.5)),
                    p_le0=float((b <= 0).mean())))
m1 = pd.DataFrame(mc1)
print(m1.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
m1.to_csv(os.path.join(OUT, "n22_mc_edge.csv"), index=False)

# =============================================================================== 3  MC: PATH
hd("3  MONTE CARLO 2 of 4 -- THE PATH (permutation of the realised sequence)")


def maxdd(x):
    e = np.cumsum(x)
    return float(np.max(np.maximum.accumulate(e) - e)) if len(e) else 0.0


r = tr["pct"].to_numpy()
real_dd = maxdd(r)
rp = np.random.default_rng(2)
perm = np.array([maxdd(rp.permutation(r)) for _ in range(6000)])
pct_ = float((perm <= real_dd).mean())
print(f"  realised max drawdown {real_dd:.4f} %  sits at the {100*pct_:.1f}th percentile of "
      f"6,000 reshuffles of its OWN trades")
print(f"  MC median {np.median(perm):.4f}  p95 {np.percentile(perm,95):.4f}  "
      f"p99 {np.percentile(perm,99):.4f}  = {np.percentile(perm,99)/max(real_dd,1e-9):.2f}x realised")
print("  A LOW percentile means the realised path was smoother than a reshuffle -- lucky, and the "
      "p99 is the sizing number, not the backtest's drawdown.")
pd.DataFrame(dict(dd=perm)).to_csv(os.path.join(OUT, "n22_mc_path.csv"), index=False)

# =============================================================================== 4  MC: EXECUTION
hd("4  MONTE CARLO 3 of 4 -- EXECUTION (round turn drawn U(0.5x, 2x) PER TRADE)")
# cost is purely subtractive in `_walk2` (p = s*(ex-e) - cost), so run once at zero and charge
# a drawn cost per trade -- exact, and it varies per TRADE rather than per draw.
p0 = dict(P, cost_mult=0.0)
t0 = c.trades(p0)
assert len(t0) == len(tr), "zero-cost run must produce the same trade set"
ent = t0["ent"].to_numpy(); gross = t0["pts"].to_numpy()
re_ = np.random.default_rng(4)
tot, mean = [], []
for _ in range(2000):
    cm = re_.uniform(0.5, 2.0, len(gross))
    net = 100.0 * (gross - c.cost * cm) / ent
    tot.append(net.sum()); mean.append(net.mean())
tot = np.asarray(tot); mean = np.asarray(mean)
print(f"  gross (zero cost)  {100*(gross/ent).mean():+.4f} %/trade, total {100*(gross/ent).sum():+.4f}")
print(f"  as charged (1.0x)  {tr['pct'].mean():+.4f} %/trade, total {tr['pct'].sum():+.4f}")
print(f"  perturbed  mean/trade p5 {np.percentile(mean,5):+.4f}  median {np.median(mean):+.4f}  "
      f"p95 {np.percentile(mean,95):+.4f}")
print(f"             total      p5 {np.percentile(tot,5):+.4f}  p95 {np.percentile(tot,95):+.4f}   "
      f"P(total<=0) = {(tot<=0).mean():.4f}")
print(f"  the round turn is {100*c.cost/P['stop_pts']:.2f}% of the {P['stop_pts']:.0f}-point stop, "
      f"so this band is nearly free by arithmetic.")
pd.DataFrame(dict(mean=mean, tot=tot)).to_csv(os.path.join(OUT, "n22_mc_exec.csv"), index=False)

# =============================================================================== 5  MC: DATA
hd("5  MONTE CARLO 4 of 4 -- PRICE JITTER, WITH EVERY INDICATOR RECOMPUTED")
TICK = 1.0
f0 = c.f0
O_, H_, L_, C_ = (f0[k].to_numpy().copy() for k in ("open", "high", "low", "close"))


def jitter_ctx(scale, seed):
    g = np.random.default_rng(seed)
    n = len(f0)
    o = O_ + g.uniform(-scale, scale, n) * TICK
    h = H_ + g.uniform(-scale, scale, n) * TICK
    l = L_ + g.uniform(-scale, scale, n) * TICK
    cl = C_ + g.uniform(-scale, scale, n) * TICK
    hi = np.maximum.reduce([o, h, l, cl]); lo = np.minimum.reduce([o, h, l, cl])
    d = pd.DataFrame({"open": o, "high": hi, "low": lo, "close": cl,
                      "volume": f0["volume"].to_numpy()}, index=f0.index)
    pc = np.r_[cl[0], cl[:-1]]
    d["tr"] = np.maximum(hi - lo, np.maximum(np.abs(hi - pc), np.abs(lo - pc)))
    d["atr"] = pd.Series(d["tr"].to_numpy()).ewm(span=14, adjust=False).mean().to_numpy()
    d["mod"] = f0["mod"].to_numpy(); d["day"] = f0["day"].to_numpy()
    return S.Ctx30(name="US30L", tf=0.5, fix=1, frame=d, block_name="ALL")


rows = []
for scale in (0.5, 1.0, 2.0):
    keep, nn, mm = 0, [], []
    for s in range(50):
        cj = jitter_ctx(scale, 1000 + s)
        tj = cj.trades(P)
        if tj is None or len(tj) == 0:
            continue
        nn.append(len(tj)); mm.append(float(tj["pct"].mean()))
        keep += int(tj["pct"].mean() > 0)
    rows.append(dict(jitter_ticks=scale, draws=len(mm), sign_kept=keep / max(len(mm), 1),
                     n_med=float(np.median(nn)), mean_p5=float(np.percentile(mm, 5)),
                     mean_med=float(np.median(mm)), mean_p95=float(np.percentile(mm, 95))))
    print(f"  +-{scale:.1f} tick: sign kept {rows[-1]['sign_kept']:.3f}, "
          f"trades {np.median(nn):.0f} (rule {len(tr)}), "
          f"mean/trade p5 {rows[-1]['mean_p5']:+.4f} med {rows[-1]['mean_med']:+.4f} "
          f"p95 {rows[-1]['mean_p95']:+.4f}")
mj = pd.DataFrame(rows)
mj.to_csv(os.path.join(OUT, "n22_mc_jitter.csv"), index=False)

# =============================================================================== 6  correlations
hd("6  THREE CORRELATION MATRICES -- ARMS, CONDITIONS, RESOLUTIONS")


def dseries(t, days):
    if t is None or len(t) == 0:
        return pd.Series(0.0, index=days)
    g = pd.Series(t["pct"].to_numpy()).groupby(t["eday"].to_numpy()).sum()
    return g.reindex(days).fillna(0.0)


alld = np.unique(c.day[c.mod >= N.OPEN_M])
alld = alld[np.isin(alld, np.unique(c.day[(c.mod >= 540) & (c.mod < 545)]))]
arms = {}
arms["rule"] = dseries(tr, alld)
arms["no gate"] = dseries(c.trades(dict(P, ma_mode="off")), alld)
arms["no breakeven"] = dseries(c.trades(dict(P, be_pts=0.0, be_off=0.0)), alld)
arms["no cross exit"] = dseries(c.trades(dict(P, x_mode="off")), alld)
arms["long only"] = dseries(c.trades(dict(P, side="long")), alld)
arms["short only"] = dseries(c.trades(dict(P, side="short")), alld)
# always-long in the same window with the same geometry
first = []
for d in alld:
    m = np.flatnonzero((c.day == d) & (c.mod >= P["open_m"]) & (c.mod < P["end_m"]))
    if len(m):
        first.append(m[0])
al = c._walk_sig(P, atrf, np.asarray(first, np.int64), np.ones(len(first), np.int64))
arms["always long"] = dseries(al, alld)
A = pd.DataFrame(arms)
print("  (a) between ARMS, on zero-filled daily percent:")
print(A.corr().round(3).to_string())
A.corr().to_csv(os.path.join(OUT, "n22_corr_arms.csv"))

cb = max(1, int(round(P["cross_min"] / 0.5)))
cond = {}
cond["fresh cross"] = np.where(sd_all > 0, (c.age_up <= cb)[sig_all], (c.age_dn <= cb)[sig_all])
cond["13>48 state"] = np.where(sd_all > 0, c.st[sig_all], (~c.st)[sig_all])
ol, osh = c.ma200("any", 0)
cond["vs the 200"] = np.where(sd_all > 0, ol[sig_all], osh[sig_all])
cond["is long"] = sd_all > 0
cond["ATR above median"] = atrf["atr"].to_numpy()[sig_all] > np.median(atrf["atr"].to_numpy()[sig_all])
Cm = pd.DataFrame({k: v.astype(float) for k, v in cond.items()})
print("\n  (b) between CONDITIONS, ON THE SIGNAL BARS (a filter only ever acts there):")
print(Cm.corr().round(4).to_string())
Cm.corr().to_csv(os.path.join(OUT, "n22_corr_cond.csv"))

print("\n  (c) across RESOLUTIONS -- the same rule on 30s / 1m / 5m bars of the SAME file:")
res = {}
for tf in (0.5, 1.0, 5.0):
    cc = S.ctx(tf=tf, fix=1)
    tt = cc.trades(P)
    res[f"{tf:g}m"] = dseries(tt, alld) if tt is not None else pd.Series(0.0, index=alld)
    print(f"    {tf:g}m: {0 if tt is None else len(tt):4d} trades, "
          f"{float(tt['pct'].mean()) if tt is not None else 0:+.4f} %/trade, "
          f"total {float(tt['pct'].sum()) if tt is not None else 0:+.4f}, "
          f"ambiguous {float(tt['amb'].mean()) if tt is not None else 0:.4f}")
R = pd.DataFrame(res)
print(R.corr().round(3).to_string())
R.corr().to_csv(os.path.join(OUT, "n22_corr_res.csv"))
print("\ndone.")
