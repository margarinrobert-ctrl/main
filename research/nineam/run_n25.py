"""30-second US30 at the LIVE settings: walk-forward, four Monte Carlos, correlations, deflation.

The four Monte Carlos answer four different questions and are never pooled:
  EDGE       a day-block bootstrap of the per-trade result against ZERO
  PATH       a permutation of the realised trade sequence -- was the drawdown a draw?
  EXECUTION  a round turn drawn U(0.5x, 2x) PER TRADE, inside the walk
  DATA       price jitter with the ATR, both EMAs, the 09:00 range and the cross ALL recomputed

Read the last two LAST. A 100-point target on a 2.29-point round turn makes the execution band
nearly free by arithmetic, so a tight band there says the implementation is not fragile, never
that the edge is real.

Section 6 is the number that governs: 44 trades chosen from a configuration space the user swept
by hand in TradingView. The deflation is not a formality.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import na_core as N    # noqa: E402
import na_s30 as S     # noqa: E402
import na_live as L    # noqa: E402
import daykey as DK    # noqa: E402

OUT = HERE
pd.set_option("display.width", 220)


def hd(t):
    print("\n" + "=" * 96); print(t); print("=" * 96)


c = S.ctx(tf=0.5, fix=1)
P = dict(L.LIVE)
tr = c.trades(P)
r = tr["pct"].to_numpy()
sig_g, sd_g = c.sigs(P)
atrf = c.atr_frame(P["atr_n"])
tdays = np.unique(c.day[sig_g])
print(f"rule: {len(tr)} trades on {len(tdays)} sessions, "
      f"{DK.from_day(tdays.min()).date()}..{DK.from_day(tdays.max()).date()}")

# ============================================================== 1  walk-forward
hd("1  WALK-FORWARD -- THE CONSTANTS FIXED, BESIDE A RE-CHOSEN ARM AND A RANDOM CELL")
GRID = []
for sa in (1.5, 2.25, 3.0):
    for tp in (60.0, 100.0, 150.0):
        for be in (0.0, 43.0, 75.0):
            for xm in ("cross", "off"):
                GRID.append(dict(stop_atr=sa, tgt_pts=tp, be_pts=be, x_mode=xm))
print(f"  {len(GRID)} declared cells; E[max t | pure noise] over that many looks = "
      f"{N.e_max_normal(len(GRID)):.3f} against the 2.802 a detection needs")


def cell(q):
    p = dict(P, **q)
    p["be_off"] = 3.0 if q.get("be_pts", 0) > 0 else 0.0
    return p


def run_days(p, days):
    t = c.trades(p)
    return S.sub(t, days) if t is not None else None


K = 5
edges = np.array_split(tdays, K)
rows = []
rng = np.random.default_rng(5)
for k in range(1, K):
    trn = np.concatenate(edges[:k]); tst = edges[k]
    tf_ = run_days(P, tst)
    best, bsc = None, -np.inf
    for q in GRID:
        t = run_days(cell(q), trn)
        if t is None or len(t) < 5:
            continue
        sc = float(t["pct"].sum())
        if sc > bsc:
            bsc, best = sc, q
    tc_ = run_days(cell(best), tst) if best is not None else None
    tr_ = run_days(cell(GRID[rng.integers(len(GRID))]), tst)
    rows.append(dict(fold=k, test_sessions=len(tst),
                     fixed=float(tf_["pct"].sum()) if tf_ is not None and len(tf_) else 0.0,
                     fixed_n=0 if tf_ is None else len(tf_),
                     rechosen=float(tc_["pct"].sum()) if tc_ is not None and len(tc_) else 0.0,
                     random=float(tr_["pct"].sum()) if tr_ is not None and len(tr_) else 0.0,
                     picked=str(best)))
wf = pd.DataFrame(rows)
print(wf.drop(columns=["picked"]).to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
print("\n  cells chosen on the training window:")
for _, q in wf.iterrows():
    print(f"    fold {int(q.fold)}: {q.picked}")
print(f"\n  TOTAL   fixed {wf.fixed.sum():+.4f}   re-chosen {wf.rechosen.sum():+.4f}   "
      f"random {wf.random.sum():+.4f}")
print(f"  folds positive  fixed {int((wf.fixed>0).sum())}/{len(wf)}   "
      f"re-chosen {int((wf.rechosen>0).sum())}/{len(wf)}   random {int((wf.random>0).sum())}/{len(wf)}")
print("  The random cell is the control that matters: if a cell drawn blind from the same grid")
print("  earns what the chosen one does, the choosing was not what produced the result.")
wf.to_csv(os.path.join(OUT, "n25_walkforward.csv"), index=False)

# ============================================================== 2  MC 1: EDGE
hd("2  MONTE CARLO 1 of 4 -- THE EDGE (day-block bootstrap against zero)")
is_d, oos_d = S.split_days(c, P, 0.5)
m1 = []
for lab, dd in [("ALL", None), ("IS", is_d), ("OOS", oos_d)]:
    t = tr if dd is None else S.sub(tr, dd)
    b = np.asarray(N.boot_edge(t, n=6000, seed=1, col="pct"))
    m1.append(dict(block=lab, n=len(t), mean=float(t["pct"].mean()),
                   lo=float(np.percentile(b, 2.5)), hi=float(np.percentile(b, 97.5)),
                   p_le0=float((b <= 0).mean())))
m1 = pd.DataFrame(m1)
print(m1.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
m1.to_csv(os.path.join(OUT, "n25_mc_edge.csv"), index=False)

# ============================================================== 3  MC 2: PATH
hd("3  MONTE CARLO 2 of 4 -- THE PATH (permutation of the realised sequence)")


def maxdd(x):
    e = np.cumsum(x)
    return float(np.max(np.maximum.accumulate(e) - e)) if len(e) else 0.0


real_dd = maxdd(r)
rp = np.random.default_rng(2)
perm = np.array([maxdd(rp.permutation(r)) for _ in range(8000)])
print(f"  realised max drawdown {real_dd:.4f} % sits at the {100*float((perm<=real_dd).mean()):.1f}"
      f"th percentile of 8,000 reshuffles of its OWN trades")
print(f"  MC median {np.median(perm):.4f}  p95 {np.percentile(perm,95):.4f}  "
      f"p99 {np.percentile(perm,99):.4f} = {np.percentile(perm,99)/max(real_dd,1e-9):.2f}x realised")
print(f"  in dollars at 1 contract: realised ${5.0*real_dd*float(tr['ent'].mean())/100:.0f}, "
      f"p99 ${5.0*np.percentile(perm,99)*float(tr['ent'].mean())/100:.0f}")
print("  The p99 is the sizing number. The backtest's own drawdown is a single draw and is not.")
pd.DataFrame(dict(dd=perm)).to_csv(os.path.join(OUT, "n25_mc_path.csv"), index=False)

# ============================================================== 4  MC 3: EXECUTION
hd("4  MONTE CARLO 3 of 4 -- EXECUTION (round turn drawn U(0.5x, 2x) PER TRADE)")
t0 = c.trades(dict(P, cost_mult=0.0))
assert len(t0) == len(tr), "zero-cost run must produce the same trade set"
ent = t0["ent"].to_numpy(); gross = t0["pts"].to_numpy()
re_ = np.random.default_rng(4)
tot, mean = [], []
for _ in range(3000):
    cm = re_.uniform(0.5, 2.0, len(gross))
    net = 100.0 * (gross - c.cost * cm) / ent
    tot.append(net.sum()); mean.append(net.mean())
tot = np.asarray(tot); mean = np.asarray(mean)
print(f"  gross (zero cost)  {100*(gross/ent).mean():+.4f} %/trade")
print(f"  as charged (1.0x)  {r.mean():+.4f} %/trade")
print(f"  perturbed mean/trade  p5 {np.percentile(mean,5):+.4f}  median {np.median(mean):+.4f}  "
      f"p95 {np.percentile(mean,95):+.4f}   P(mean<=0) = {(mean<=0).mean():.4f}")
med_stop = float(2.25 * atrf['atr'].to_numpy()[sig_g].mean())
print(f"  the round turn is {100*c.cost/med_stop:.2f}% of the mean stop -- this band is nearly")
print("  free by arithmetic and is NOT evidence of an edge.")
pd.DataFrame(dict(mean=mean, tot=tot)).to_csv(os.path.join(OUT, "n25_mc_exec.csv"), index=False)

# a cost LADDER is the honest version of the same question
print("\n  cost ladder (every knob fixed, only the round turn moved):")
lad = []
for m in (0.0, 1.0, 2.0, 4.0, 8.0, 16.0):
    t = c.trades(dict(P, cost_mult=m))
    lad.append(dict(mult=m, rt_pts=c.cost * m, n=len(t), pct=float(t["pct"].mean()),
                    tot=float(t["pct"].sum()), win=float((t["pct"] > 0).mean())))
lad = pd.DataFrame(lad)
print(lad.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
lad.to_csv(os.path.join(OUT, "n25_cost.csv"), index=False)

# ============================================================== 5  MC 4: DATA
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
    for s in range(60):
        tj = jitter_ctx(scale, 1000 + s).trades(P)
        if tj is None or len(tj) == 0:
            continue
        nn.append(len(tj)); mm.append(float(tj["pct"].mean()))
        keep += int(tj["pct"].mean() > 0)
    rows.append(dict(jitter_ticks=scale, draws=len(mm), sign_kept=keep / max(len(mm), 1),
                     n_med=float(np.median(nn)), mean_p5=float(np.percentile(mm, 5)),
                     mean_med=float(np.median(mm)), mean_p95=float(np.percentile(mm, 95))))
    q = rows[-1]
    print(f"  +-{scale:.1f} tick: sign kept {q['sign_kept']:.3f}, trades {q['n_med']:.0f} "
          f"(rule {len(tr)}), mean/trade p5 {q['mean_p5']:+.4f} med {q['mean_med']:+.4f} "
          f"p95 {q['mean_p95']:+.4f}")
pd.DataFrame(rows).to_csv(os.path.join(OUT, "n25_mc_jitter.csv"), index=False)
print("  A jitter that moves the TRADE COUNT is moving the signal set, not just the fills --")
print("  read the count column before the P&L column.")

# ============================================================== 6  drop-one
hd("6  DROP-ONE -- WHAT EACH COMPONENT IS WORTH")
ARMS = {
    "rule (all on)": {},
    "no fresh-cross gate": dict(ma_mode="off"),
    "no breakeven ratchet": dict(be_pts=0.0, be_off=0.0),
    "no opposite-cross exit": dict(x_mode="off"),
    "no 10:00 entry cutoff": dict(end_m=960),
    "no 10:30 flatten": dict(flat_m=960),
    "long only": dict(side="long"),
    "short only": dict(side="short"),
}
rows = []
for lab, q in ARMS.items():
    t = c.trades(dict(P, **q))
    if t is None or len(t) == 0:
        rows.append(dict(arm=lab, n=0)); continue
    x = t["pct"].to_numpy()
    rows.append(dict(arm=lab, n=len(x), pct=float(x.mean()), tot=float(x.sum()),
                     win=float((x > 0).mean()),
                     pts=float(t["pts"].mean()),
                     d_pct=float(x.mean()) - r.mean(), d_tot=float(x.sum()) - r.sum()))
do = pd.DataFrame(rows)
print(do.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
do.to_csv(os.path.join(OUT, "n25_dropone.csv"), index=False)

# ============================================================== 7  correlation matrices
hd("7  CORRELATION MATRICES -- ARMS, AND THE DAILY SERIES AGAINST THE MARKET")
alld = np.intersect1d(np.unique(c.day[(c.mod >= 540) & (c.mod < 545)]),
                      np.unique(c.day[(c.mod >= P["open_m"]) & (c.mod < P["end_m"])]))


def dseries(t, days):
    if t is None or len(t) == 0:
        return pd.Series(0.0, index=days)
    g = pd.Series(t["pct"].to_numpy()).groupby(t["eday"].to_numpy()).sum()
    return g.reindex(days).fillna(0.0)


arms = {lab: dseries(c.trades(dict(P, **q)), alld) for lab, q in ARMS.items()}
# the market itself, over the same window
mkt = []
for d in alld:
    m = np.flatnonzero((c.day == d) & (c.mod >= P["open_m"]) & (c.mod < P["flat_m"]))
    if len(m) < 2:
        mkt.append(0.0); continue
    o = c.f0["open"].to_numpy()[m[0]]; cl = c.f0["close"].to_numpy()[m[-1]]
    mkt.append(100.0 * (cl - o) / o)
arms["market 09:26-10:30"] = pd.Series(mkt, index=alld)
A = pd.DataFrame(arms)
print(A.corr().to_string(float_format=lambda v: f"{v:+.3f}"))
A.corr().to_csv(os.path.join(OUT, "n25_corr_arms.csv"))
print(f"\n  rule vs the market over its own window: {A.corr().loc['rule (all on)', 'market 09:26-10:30']:+.3f}")
print(f"  long-only vs short-only               : {A.corr().loc['long only', 'short only']:+.3f}")
A.to_csv(os.path.join(OUT, "n25_daily.csv"))

# ============================================================== 8  power and deflation
hd("8  POWER AND DEFLATION -- THE NUMBER THAT GOVERNS")
sd = r.std(ddof=1)
sr_t = r.mean() / sd                      # per-trade Sharpe
print(f"  per-trade Sharpe {sr_t:.4f}, t = {sr_t*np.sqrt(len(r)):.3f} on {len(r)} trades")
print(f"  MDE {N.mde(sd, len(r)):.4f} %/trade, delivered {r.mean():.4f} = "
      f"{r.mean()/N.mde(sd, len(r)):.2f}x")
for M in (10, 50, 100, 500, 2000):
    em = N.e_max_normal(M)
    print(f"    if this configuration was the best of {M:5d} looks: E[max t | noise] = {em:.3f}, "
          f"{'SURVIVES' if sr_t*np.sqrt(len(r)) > em else 'FAILS'}")
print("\n  The look count is not a number the backtest can supply. It is how many settings the")
print("  user tried in the Inputs dialog before keeping this one -- range window, entry window,")
print("  flatten time, ATR length, cross reach, stop mode, target, breakeven arm and offset.")
print("  Nine knobs with three plausible values each is 19,683; the observed t clears none of")
print("  that. The honest statement is that this result is significant against a random entry")
print("  and NOT established against its own search.")
print("\ndone.")
