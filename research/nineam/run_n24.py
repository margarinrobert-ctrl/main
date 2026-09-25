"""30-second US30 at the LIVE settings: geometry, coverage, IS/OOS, exit mix, and the two nulls.

Section 22 measured a 100/100-point configuration. This measures the one the Inputs dialog
actually holds (`na_live.LIVE`), whose stop is 2.25 x ATR(45) against a 100-POINT target -- a
reward-to-risk near 3.9:1, so its driftless break-even win rate is near 0.205 and a 64% win rate
means something completely different here than it did there.

Order is deliberate. Geometry and base rates come before any P&L, coverage before any count, and
the MDE is printed beside the result rather than after it.
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
import na_30s as T     # noqa: E402
import na_s30 as S     # noqa: E402
import na_live as L    # noqa: E402
import daykey as DK  # noqa: E402  (pandas 3 made us the default resolution; see the module)

OUT = HERE
pd.set_option("display.width", 220)


def hd(t):
    print("\n" + "=" * 96); print(t); print("=" * 96)


c = S.ctx(tf=0.5, fix=1)
P = dict(L.LIVE)
f0 = c.f0

# ============================================================== 0  what the feed can carry
hd("0  COVERAGE -- THE 09:00 RANGE EXISTS ON ONLY PART OF THIS FILE")
have = np.unique(c.day[(c.mod >= P["range_start"]) & (c.mod < P["range_end"])])
alld = np.unique(c.day)
win = np.unique(c.day[(c.mod >= P["open_m"]) & (c.mod < P["end_m"])])
print(f"  sessions in the file            {len(alld)}")
print(f"  sessions carrying 09:00-09:05   {len(have)}  "
      f"({DK.from_day(have.min()).date()}..{DK.from_day(have.max()).date()})")
print(f"  sessions carrying 09:26-10:00   {len(win)}")
both = np.intersect1d(have, win)
print(f"  sessions carrying BOTH          {len(both)}  <- the tradeable sample")
print("  The 30-second feed omits bars with no activity, so a bar index is not a clock and a")
print("  session either carries the whole 09:00 range or none of it.")

# ============================================================== 1  the geometry, before any P&L
hd("1  THE GEOMETRY -- WHAT THIS CONFIGURATION IS BEFORE IT IS PROFITABLE")
atrf = c.atr_frame(P["atr_n"])
sig_g, sd_g = c.sigs(P)
sig_all, sd_all = c.events(P["range_end"], P["side"], P["buf_atr"], P["atr_n"],
                           P["end_m"], P["open_m"])
at_sig = atrf["atr"].to_numpy()[sig_g]
ent_sig = f0["close"].to_numpy()[sig_g]
stop_pts = P["stop_atr"] * at_sig
rr = P["tgt_pts"] / stop_pts
be_drift = 1.0 / (1.0 + rr)
print(f"  ATR(45) at the signal bars: median {np.median(at_sig):.2f} points "
      f"(p10 {np.percentile(at_sig,10):.2f}, p90 {np.percentile(at_sig,90):.2f})")
print(f"  stop = 2.25 x ATR         : median {np.median(stop_pts):.2f} points")
print(f"  target                    : {P['tgt_pts']:.0f} points, FIXED")
print(f"  reward:risk               : median {np.median(rr):.2f} : 1  "
      f"(p10 {np.percentile(rr,10):.2f}, p90 {np.percentile(rr,90):.2f})")
print(f"  driftless break-even win  : median {np.median(be_drift):.4f}   <- the base rate to beat")
print(f"  round turn {c.cost:.2f} points is {100*c.cost/np.median(stop_pts):.2f}% of the stop "
      f"and {100*c.cost/P['tgt_pts']:.2f}% of the target")
print(f"  breakeven arms at +{P['be_pts']:.0f} and secures +{P['be_off']:.0f}, i.e. it arms at "
      f"{100*P['be_pts']/P['tgt_pts']:.0f}% of the way to target and books "
      f"{P['be_off']-c.cost:+.2f} net when hit")
geo = pd.DataFrame(dict(atr=at_sig, stop_pts=stop_pts, rr=rr, be=be_drift))
geo.describe().to_csv(os.path.join(OUT, "n24_geometry.csv"))

# ============================================================== 2  availability of the trigger
hd("2  AVAILABILITY -- HOW MUCH THE GATE THROWS AWAY")
print(f"  breaks of the 09:00 range in 09:26-10:00 : {len(sig_all)} on "
      f"{len(np.unique(c.day[sig_all]))} sessions")
print(f"  surviving the fresh 13x48 cross <= 5 min : {len(sig_g)} on "
      f"{len(np.unique(c.day[sig_g]))} sessions  "
      f"({100*len(sig_g)/max(len(sig_all),1):.1f}% kept)")
print(f"  long/short split of the kept triggers    : {int((sd_g>0).sum())} long / "
      f"{int((sd_g<0).sum())} short")
print(f"  sessions that CAN trade but never fire   : "
      f"{len(both) - len(np.unique(c.day[sig_g]))} of {len(both)}")

# ============================================================== 3  the result, with its MDE
hd("3  THE RESULT -- AND THE SMALLEST EFFECT THIS SAMPLE COULD HAVE DETECTED")
tr = c.trades(P)
r = tr["pct"].to_numpy()
mde = N.mde(r.std(ddof=1), len(r))
print(f"  {len(tr)} trades on {len(np.unique(tr['eday']))} sessions")
print(f"  mean {r.mean():+.4f} %/trade = {tr['pts'].mean():+.2f} points "
      f"= ${5.0*tr['pts'].mean():+.2f} at $5/point, 1 contract")
print(f"  total {r.sum():+.4f} % = {tr['pts'].sum():+.1f} points = ${5.0*tr['pts'].sum():+.0f}")
w = r > 0
pf = float(r[w].sum() / -r[~w].sum()) if (~w).any() else np.nan
print(f"  win {w.mean():.4f}   PF {pf:.3f}   sd {r.std(ddof=1):.4f}")
print(f"\n  MDE at n={len(r)}: {mde:.4f} %/trade. Delivered {r.mean():.4f} "
      f"= {r.mean()/mde:.2f}x MDE.")
print("  A ratio below 1 means the sample is too small to have resolved an effect of this size;")
print("  the point estimate is then a draw from a distribution wide enough to contain zero.")
print(f"  Trades needed for the delivered effect to be its OWN MDE: "
      f"{int(np.ceil((2.802*r.std(ddof=1)/r.mean())**2))}")
bo = np.asarray(N.boot_edge(tr, n=6000, seed=3, col="pct"))
print(f"  day-block bootstrap: 95% CI [{np.percentile(bo,2.5):+.4f}, "
      f"{np.percentile(bo,97.5):+.4f}], P(mean<=0) = {(bo<=0).mean():.4f}")

# ============================================================== 4  exit mix and the win rate
hd("4  EXIT MIX -- AND THE WIN RATE AGAINST ITS OWN BREAK-EVEN")
WHY = {1: "stop / ratchet", 2: "target", 3: "flatten 10:30", 6: "opposite cross"}
mx = tr.groupby("why").agg(n=("pts", "size"), pts=("pts", "mean"), tot=("pts", "sum"),
                           tot_pct=("pct", "sum"))
mx.index = [WHY.get(i, str(i)) for i in mx.index]
mx["share"] = mx["n"] / mx["n"].sum()
mx["of_net"] = mx["tot_pct"] / r.sum()
print(mx.to_string(float_format=lambda v: f"{v:.3f}"))
mx.to_csv(os.path.join(OUT, "n24_exitmix.csv"))
aw = tr.loc[tr["pts"] > 0, "pts"].mean(); al = tr.loc[tr["pts"] <= 0, "pts"].mean()
payoff = aw / -al
print(f"\n  avg win {aw:+.2f} pts, avg loss {al:+.2f} pts, payoff {payoff:.3f}")
print(f"  REALISED break-even win rate = 1/(1+payoff) = {1/(1+payoff):.4f}")
print(f"  actual win rate {w.mean():.4f} -> {100*(w.mean()-1/(1+payoff)):+.1f} points of win rate "
      f"above break-even")
sec = float(P["be_off"] - c.cost)
k = int((np.abs(tr["pts"].to_numpy() - sec) < 1e-6).sum())
print(f"  trades booking EXACTLY the secured {sec:+.2f}: {k} of {len(tr)} "
      f"({100*k/len(tr):.1f}%) -- these are LOSING trades relabelled by the ratchet offset")
hold = (tr['xb'].to_numpy() - tr['eb'].to_numpy()) * 0.5
print(f"  median hold {np.median(hold):.1f} min (max {hold.max():.1f}), "
      f"intrabar ambiguity {tr['amb'].mean():.4f}, through-the-market {tr['thru'].mean():.4f}")

# ============================================================== 5  IS / OOS
hd("5  IS / OOS -- A CHRONOLOGICAL SPLIT OVER THE SESSIONS THAT CAN TRADE")
is_d, oos_d = S.split_days(c, P, 0.5)
print(f"  IS  {len(is_d)} sessions {DK.from_day(is_d.min()).date()}..{DK.from_day(is_d.max()).date()}")
print(f"  OOS {len(oos_d)} sessions {DK.from_day(oos_d.min()).date()}..{DK.from_day(oos_d.max()).date()}")
rows = []
for lab, dd in [("ALL", None), ("IS", is_d), ("OOS", oos_d)]:
    t = tr if dd is None else S.sub(tr, dd)
    s = S.summary(t, len(both), 0.38)
    s["block"] = lab
    s["per_mde"] = s["pct"] / s["mde"] if s.get("n", 0) > 1 else np.nan
    rows.append(s)
res = pd.DataFrame(rows)[["block", "n", "pct", "pts", "win", "pf", "tot", "dd", "retdd",
                          "mde", "per_mde"]]
print(res.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
res.to_csv(os.path.join(OUT, "n24_isoos.csv"), index=False)
print("\n  Neither half is an out-of-sample test in the protocol sense -- the configuration was")
print("  chosen with the whole file visible. It is a stability check, and nothing more.")

# ============================================================== 6  the nulls
hd("6  THE NULLS -- A MATCHED RANDOM ENTRY AND A SAME-SELECTIVITY RANDOM GATE")
rhi, rlo, _ = c.ranges(P["range_end"])
ok = (c.mod >= P["open_m"]) & (c.mod < P["end_m"]) & np.isfinite(rhi) & np.isfinite(rlo)
elig = np.flatnonzero(ok)
elig_day = c.day[elig]


def control(n_draw=400, seed=0):
    """Random ENTRY: same side, same geometry, same session, same minute-of-day pool."""
    g = np.random.default_rng(seed)
    pool = {d: elig[elig_day == d] for d in np.unique(c.day[sig_g])}
    out = []
    for _ in range(n_draw):
        bb, ss = [], []
        for i, b in enumerate(sig_g):
            cand = pool.get(c.day[b])
            if cand is None or not len(cand):
                continue
            bb.append(g.choice(cand)); ss.append(sd_g[i])
        o = np.argsort(np.asarray(bb), kind="stable")
        t = c._walk_sig(P, atrf, np.asarray(bb)[o], np.asarray(ss)[o])
        out.append(np.nan if t is None else float(t["pct"].mean()))
    return np.asarray(out, float)


def gate_null(n_draw=400, seed=0):
    """Random GATE of the same selectivity, applied to the TRIGGERS and re-simulated end to end."""
    g = np.random.default_rng(seed)
    frac = len(sig_g) / max(len(sig_all), 1)
    out = []
    for _ in range(n_draw):
        k = g.random(len(sig_all)) < frac
        if k.sum() < 5:
            out.append(np.nan); continue
        t = c._walk_sig(P, atrf, sig_all[k], sd_all[k])
        out.append(np.nan if t is None else float(t["pct"].mean()))
    return np.asarray(out, float)


ce = control(400, 11); ge = gate_null(400, 12)
print(f"  rule                  {r.mean():+.4f} %/trade on {len(r)} trades")
for lab, nul in [("random ENTRY", ce), ("random GATE", ge)]:
    v = nul[np.isfinite(nul)]
    print(f"  {lab:14s} median {np.median(v):+.4f}  p5 {np.percentile(v,5):+.4f}  "
          f"p95 {np.percentile(v,95):+.4f}   p = {float((v>=r.mean()).mean()):.3f}  "
          f"(null sd {v.std(ddof=1):.4f})")
pd.DataFrame(dict(entry=ce, gate=ge)).to_csv(os.path.join(OUT, "n24_nulls.csv"), index=False)
print("\n  The random-ENTRY null prices drift, costs, barrier width and session timing at once.")
print("  The random-GATE null asks whether a filter of this selectivity is worth anything AT ALL")
print("  -- it is the one that says whether the fresh cross is doing work or just thinning.")

# the no-gate arm, for the same question read a different way
ng = c.trades(dict(P, ma_mode="off"))
print(f"\n  ungated (every break taken): {len(ng)} trades, {ng['pct'].mean():+.4f} %/trade, "
      f"win {(ng['pct']>0).mean():.4f}, total {ng['pct'].sum():+.4f}")
print(f"  the gate's contribution     : {r.mean()-float(ng['pct'].mean()):+.4f} %/trade, against a "
      f"random gate's {np.median(ge[np.isfinite(ge)])-float(ng['pct'].mean()):+.4f}")
print("\ndone.")
