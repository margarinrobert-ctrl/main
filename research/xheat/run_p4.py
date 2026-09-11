"""P4 -- VERIFY THE WHY, then read the locked block ONCE.

Three mechanisms were proposed and each is checked on its own terms BEFORE its P&L is read,
because a p-value on a policy tells you nothing about whether the reason you gave is the reason
it works:

  W1  THE CLOCK SCALING. If heat grows with the time the trade has left, |MAE| should scale as
      sqrt(minutes remaining) -- the random-walk prediction, not a fitted exponent. Tested by
      regressing |MAE| on (mins_left)^p and reading the exponent the data actually wants.
  W2  THE VOLATILITY SCALING. Already replicated in P3.3 on both feeds and both blocks. Verified
      further here: does the ADAPTIVE stop actually equalise the stop-out rate across volatility
      quartiles? That is the mechanism's own prediction, and it is a stronger test than expectancy.
  W3  THE TRAIL. The claim is that a trail is cheap in THIS window specifically, because the 11:00
      flatten forfeits the tail anyway. The counterfactual settles it: for every trade the trail
      closed, what did that trade go on to do by 11:00?

Then the policies, declared in advance, scored PAIRED against the no-policy baseline on the same
trades, research first and ONE locked read with the trial count stated.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/xheat")
import numpy as np, pandas as pd
from scipy import stats
import xdata as X, xsig as S, xpath as P, xpol as PL

R = "results/xheat/"
os.makedirs(R, exist_ok=True)
print(__doc__)
t0 = time.time()
RNG = np.random.default_rng(11)
FEEDS = {"ISO": X.assemble(X.load_iso()), "MT": X.assemble(X.load_mt())}


def paths(D, idx, side):
    k = len(idx)
    a = [np.full(k, np.nan) for _ in range(6)]
    hold = np.zeros(k, np.int64); amb = np.zeros(k, np.int64)
    ent = np.full(k, np.nan); atr0 = np.full(k, np.nan)
    P.walk_paths(D["o"], D["h"], D["l"], D["c"], D["atr"], idx.astype(np.int64), side,
                 D["last_win"], X.COST_RT, X.SLIP,
                 a[0], a[1], a[2], a[3], a[4], hold, amb, atr0, ent, a[5])
    t = pd.DataFrame(dict(sig=idx, mae=a[0], mfe=a[1], t_mfe=a[3], end=a[4],
                          giveback=a[5], hold=hold))
    t["blk"] = D["blk"][idx]
    return t[t.hold > 0].reset_index(drop=True)


SIG = {}
for nm, D in FEEDS.items():
    SIG[nm] = S.events(D, "break", 20, 1)

# ================================================================= W1 the clock exponent
print("=" * 108)
print("W1  DOES HEAT SCALE AS THE SQUARE ROOT OF THE TIME REMAINING?")
print("=" * 108)
print("  A random walk travels as sqrt(t). If the clock term is real, |MAE| regressed on")
print("  (minutes left)^p should want p near 0.5 -- and that number is a PREDICTION made before")
print("  the fit, not an exponent chosen to make the curve look good.")
rows = []
for nm, D in FEEDS.items():
    F, _ = S.build_features(D, with_volume=np.isfinite(D["v"]).any())
    t = paths(D, SIG[nm], 1)
    ml = F["sess.mins_left"][t.sig.to_numpy()]
    for b, lab in ((0, "research"), (1, "LOCKED")):
        m = (t.blk == b).to_numpy() & np.isfinite(ml) & (ml > 0)
        y = -t.mae.to_numpy()[m]; x = ml[m]
        if m.sum() < 200:
            continue
        # the exponent the data wants, from a log-log fit
        sl = stats.linregress(np.log(x), np.log(np.maximum(y, 1e-6)))
        # and the fit quality at the PREDICTED 0.5 against alternatives
        r2 = {}
        for p in (0.25, 0.5, 0.75, 1.0):
            r2[p] = stats.linregress(x ** p, y).rvalue ** 2
        rows.append(dict(feed=nm, block=lab, n=int(m.sum()), fitted_exponent=sl.slope,
                         **{f"r2_p{p}": v for p, v in r2.items()}))
        print(f"  {nm:4s} {lab:9s} n {m.sum():5d}   fitted exponent {sl.slope:+.3f}   "
              f"R^2 at p=0.5 {r2[0.5]:.3f}   best of the five: p="
              f"{max(r2, key=r2.get)} at {max(r2.values()):.3f}")
W1 = pd.DataFrame(rows); W1.to_csv(R + "p4_w1_clock.csv", index=False)

# the same thing as a table, which is what a reader can check
print("\n  |MAE| in ATR by minutes remaining at entry (research block):")
for nm, D in FEEDS.items():
    F, _ = S.build_features(D, with_volume=np.isfinite(D["v"]).any())
    t = paths(D, SIG[nm], 1)
    ml = F["sess.mins_left"][t.sig.to_numpy()]
    m = (t.blk == 0).to_numpy() & np.isfinite(ml)
    g = pd.DataFrame({"ml": ml[m], "mae": -t.mae.to_numpy()[m], "gb": t.giveback.to_numpy()[m]})
    g["bucket"] = pd.cut(g.ml, [0, 60, 120, 180, 240], labels=["<1h", "1-2h", "2-3h", "3-4h"])
    print(f"    {nm}: " + "   ".join(
        f"{b} {r.mae:.2f} ATR (gb {r.gb:.2f}, n {int(r.n)})"
        for b, r in g.groupby("bucket", observed=True).agg(mae=("mae", "mean"),
                                                           gb=("gb", "mean"), n=("mae", "size")).iterrows()))

# ================================================================= W2 does the adaptive stop equalise
print("\n" + "=" * 108)
print("W2  DOES THE ADAPTIVE STOP DO WHAT ITS MECHANISM PREDICTS -- equalise the stop-out rate?")
print("=" * 108)
print("  A fixed ATR stop is hit far more often in the low-volatility quartile, because that is")
print("  where the heat measured in ATR is largest. If the scaling is right, the adaptive stop's")
print("  stop-out rate should be FLAT across the quartiles. Expectancy is a separate question.")
rows = []
for nm, D in FEEDS.items():
    F, _ = S.build_features(D, with_volume=np.isfinite(D["v"]).any())
    idx = SIG[nm]; t = paths(D, idx, 1)
    vp = F["vol.atr_pct500"][t.sig.to_numpy()]
    ml = F["sess.mins_left"][t.sig.to_numpy()]
    wl = D["win_end"] - D["win_start"]
    for kind in ("fixed 2.0N", "vol-adaptive", "vol + clock"):
        if kind == "fixed 2.0N":
            sm = np.full(len(t), 2.0)
        elif kind == "vol-adaptive":
            sm = PL.stop_multiple(2.0, vp, np.full(len(t), wl), wl)
        else:
            sm = PL.stop_multiple(2.0, vp, ml, wl)
        stopped = (t.mae.to_numpy() <= -sm)
        m = (t.blk == 0).to_numpy() & np.isfinite(vp)
        q = pd.qcut(vp[m], 4, labels=False, duplicates="drop")
        r = [float(stopped[m][q == k].mean()) for k in range(4)]
        rows.append(dict(feed=nm, policy=kind, q1=r[0], q2=r[1], q3=r[2], q4=r[3],
                         spread=max(r) - min(r), mean_mult=float(sm[m].mean())))
        print(f"  {nm:4s} {kind:14s} stop-out by vol quartile: "
              + "  ".join(f"{x:.1%}" for x in r) + f"   spread {max(r)-min(r):.1%}"
              + f"   mean stop {sm[m].mean():.2f} ATR")
W2 = pd.DataFrame(rows); W2.to_csv(R + "p4_w2_equalise.csv", index=False)

# ================================================================= W3 the trail counterfactual
print("\n" + "=" * 108)
print("W3  THE TRAIL COUNTERFACTUAL -- what did the trades it closed go on to do?")
print("=" * 108)
print("  A trail is destructive on every open-ended system this branch has measured, because it")
print("  cuts off the tail. Here the clock cuts the tail off anyway. For every trade the trail")
print("  closed early, the honest question is what the FLATTEN would have paid instead.")
rows = []
for nm, D in FEEDS.items():
    idx = SIG[nm]
    base = paths(D, idx, 1)
    k = len(idx)
    Rr = np.full(k, np.nan); why = np.zeros(k, np.int64)
    hold = np.zeros(k, np.int64); mfe = np.full(k, np.nan)
    P.walk_policy(D["o"], D["h"], D["l"], D["c"], D["atr"], idx.astype(np.int64), 1,
                  D["last_win"], X.COST_RT, X.SLIP,
                  0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, Rr, why, hold, mfe)
    tr = pd.DataFrame(dict(sig=idx, R=Rr, why=why, hold=hold))
    tr["blk"] = D["blk"][idx]
    j = base.merge(tr, on="sig", suffixes=("", "_tr"))
    for b, lab in ((0, "research"), (1, "LOCKED")):
        s = j[j.blk == b]
        cut = s[s.why == 1]                       # the trail actually fired
        if len(cut) < 30:
            continue
        rows.append(dict(feed=nm, block=lab, n=len(s), n_cut=len(cut),
                         share_cut=len(cut) / len(s),
                         trail_paid=cut.R.mean(), flatten_would_pay=cut.end.mean(),
                         edge=cut.R.mean() - cut.end.mean(),
                         cut_that_would_have_won=(cut.end > cut.R).mean()))
        print(f"  {nm:4s} {lab:9s} the trail closed {len(cut)/len(s):5.1%} of trades and paid "
              f"{cut.R.mean():+.4f} ATR on them; the 11:00 flatten would have paid "
              f"{cut.end.mean():+.4f}   -> edge {cut.R.mean()-cut.end.mean():+.4f} ATR")
        print(f"       of those, {float((cut.end>cut.R).mean()):.1%} would have finished BETTER "
              f"had the trail not fired -- that is the price, and it is paid on every one of them")
W3 = pd.DataFrame(rows); W3.to_csv(R + "p4_w3_trail.csv", index=False)
print(f"\ntotal {time.time()-t0:.0f}s")
