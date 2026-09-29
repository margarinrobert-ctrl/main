"""G1 -- Phase 0 sanity, then Gate 1 on the PIN posterior as an intraday entry.

Nothing is modelled and no feature is written until the raw event stream is scored with costs in.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/pin")
import numpy as np, pandas as pd
import s5data as S, s5walk as W
import pin_core as P

R = "results/pin/"; os.makedirs(R, exist_ok=True)
print(__doc__); t0 = time.time()
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)

TF = 10
D = P.load(TF)
B, Sc = P.bs_counts(D)
F = P.session_frame(D, B, Sc)
DAYS = {0: D["all_days"][D["all_days"] < D["cut_day"]],
        1: D["all_days"][D["all_days"] >= D["cut_day"]]}
print(f"  NQ {TF}m: {D['n']:,} decision bars, {len(F)} sessions, research to {D['cut_date']}")

print("\n" + "=" * 116)
print("G1.0  PHASE 0 -- IS THE MECHANISM EVEN PRESENT ON AN INDEX FUTURE?")
print("=" * 116)
rows = []
for k in (0.75, 1.0, 1.5, 2.0):
    ps = [P.fit_causal(F, i, window=120, k=k) for i in range(len(F))]
    ok = [p for p in ps if p]
    if not ok:
        continue
    rows.append(dict(k=k, fitted=len(ok), alpha=np.mean([p["a"] for p in ok]),
                     delta=np.mean([p["d"] for p in ok]), eps_b=np.mean([p["eb"] for p in ok]),
                     eps_s=np.mean([p["es"] for p in ok]), mu=np.mean([p["mu"] for p in ok]),
                     PIN=np.mean([p["pin"] for p in ok]),
                     mu_over_eps=np.mean([p["mu"] / (p["eb"] + p["es"]) for p in ok])))
Q = pd.DataFrame(rows)
Q.to_csv(R + "g1_params.csv", index=False)
print(Q.round(4).to_string(index=False))
print("\n  PIN in the equity literature runs 0.10-0.20 (EKOP's own 90 stocks average ~0.19).")
print("  MEASURED HERE IT IS ~0.005 -- a factor of THIRTY smaller. Two reasons, and both were")
print("  predictable before any backtest:")
print("   1. PIN IS A SINGLE-NAME MEASURE. It prices FIRM-SPECIFIC private information. There is")
print("      no insider on the Nasdaq-100 index; an index future is the most liquid, least")
print("      information-asymmetric instrument there is, and the literature's own finding is that")
print("      PIN FALLS with size and liquidity. The mechanism is weakest exactly here.")
print("   2. THE B/S PROXY IS COARSE. Lee-Ready needs quotes; counting up- and down-minutes")
print("      recovers direction but throws away the size and aggressor information that separates")
print("      informed from uninformed flow.")
print("  mu / (eps_b + eps_s) is the informed-to-uninformed arrival ratio and it is the number to")
print("  read: an informed arrival rate that is 2% of the uninformed one cannot move a posterior far.")

print("\n" + "=" * 116)
print("G1.1  THE POSTERIOR AS AN EVENT STREAM -- how often does it even fire?")
print("=" * 116)
# per-bar posterior, parameters frozen from the sessions BEFORE each session
day_of = {int(d): j for j, d in enumerate(F.day.to_numpy())}
params = {}
for j in range(len(F)):
    params[int(F.day.iloc[j])] = P.fit_causal(F, j, window=120, k=1.0)
pg = np.full(D["n"], np.nan); pb = np.full(D["n"], np.nan)
win_len = D["win_close"] - D["win_open"]
for i in np.flatnonzero(D["inw"]):
    p = params.get(int(D["day"][i]))
    if p is None or not np.isfinite(B[i]):
        continue
    frac = min(max((D["mod"][i] + TF - D["win_open"]) / win_len, 1e-3), 1.0)
    g, b, _ = P.posterior(B[i], Sc[i], p, frac)
    pg[i] = g; pb[i] = b
fin = np.isfinite(pg)
print(f"  posterior computed on {int(fin.sum()):,} of {int(D['inw'].sum()):,} in-window bars")
print(f"  P(good): median {np.nanmedian(pg):.4f}  p90 {np.nanpercentile(pg,90):.4f}  "
      f"p99 {np.nanpercentile(pg,99):.4f}  max {np.nanmax(pg):.4f}")
print(f"  P(bad) : median {np.nanmedian(pb):.4f}  p90 {np.nanpercentile(pb,90):.4f}  "
      f"p99 {np.nanpercentile(pb,99):.4f}  max {np.nanmax(pb):.4f}")
for th in (0.30, 0.50, 0.70, 0.90):
    print(f"    bars with P(good) >= {th:.2f}: {int(np.nansum(pg >= th)):>6,}   "
          f"P(bad) >= {th:.2f}: {int(np.nansum(pb >= th)):>6,}")

print("\n" + "=" * 116)
print("G1.2  GATE 1 -- the raw event stream, costs in, before any feature exists")
print("=" * 116)
GEOM = dict(stop=2.5, tgt=0.0, be=0.0, be_off=0.0, arm=1.0, tr=1.0)

def walk(lg, sh, g=GEOM):
    sig = lg | sh
    side = np.where(lg, 1, -1).astype(np.int64)
    n = int(sig.sum())
    if n == 0:
        return pd.DataFrame(columns=["sig", "exit", "R", "pts", "why", "blk", "day"])
    z = lambda t: np.zeros(n, t)
    oi, ox, oR, op, ow = z(np.int64), z(np.int64), z(float), z(float), z(np.int64)
    oa, of, ob = z(float), z(float), z(np.int64)
    m = W.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], sig, side, D["last_win"],
               S.RT_POINTS, S.SLIP_POINTS, g["stop"], g["tgt"], g["be"], g["be_off"],
               g["arm"], g["tr"], oi, ox, oR, op, ow, oa, of, ob)
    t = pd.DataFrame(dict(sig=oi[:m], exit=ox[:m], R=oR[:m], pts=op[:m], why=ow[:m]))
    t["blk"] = D["blk"][t.sig.to_numpy()]; t["day"] = D["day"][t.sig.to_numpy()]
    return t

rows = []
for th in (0.20, 0.30, 0.40, 0.50, 0.60, 0.70):
    lg = np.nan_to_num(pg, nan=0.0) >= th
    sh = np.nan_to_num(pb, nan=0.0) >= th
    lg &= D["inw"] & ~D["last_win"]; sh &= D["inw"] & ~D["last_win"] & ~lg
    t = walk(lg, sh)
    for b, bl in ((0, "research"), (1, "LOCKED")):
        s = t[t.blk == b]
        if len(s) < 20:
            continue
        r = s.pts.to_numpy()
        shp, _ = S.day_sharpe(s.day.to_numpy(), r, DAYS[b])
        rows.append(dict(thresh=th, block=bl, n=len(s),
                         per_yr=len(s) / (len(DAYS[b]) / 252), pts=r.mean(),
                         usd=r.mean() * P.PV, PF=r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9),
                         win=(r > 0).mean(), sharpe=shp, total=r.sum() * P.PV))
G = pd.DataFrame(rows)
G.to_csv(R + "g1_gate1.csv", index=False)
print(G.round(4).to_string(index=False))

print("\n" + "=" * 116)
print("G1.3  WHAT PROFIT FACTOR 2 WOULD REQUIRE, AT THIS GEOMETRY")
print("=" * 116)
lg = np.nan_to_num(pg, nan=0.0) >= 0.40
sh = np.nan_to_num(pb, nan=0.0) >= 0.40
lg &= D["inw"] & ~D["last_win"]; sh &= D["inw"] & ~D["last_win"] & ~lg
t = walk(lg, sh)
r = t[t.blk == 0].pts.to_numpy()
if len(r) > 20:
    gp, gl = r[r > 0].mean(), -r[r < 0].mean()
    w = (r > 0).mean()
    print(f"  measured on research: mean win {gp:+.2f} pts, mean loss {-gl:+.2f}, win rate {w:.3f}"
          f"  ->  PF {w*gp/((1-w)*gl):.3f}")
    for target in (1.5, 2.0, 3.0):
        need = target * gl / (target * gl + gp)
        print(f"    PF {target:.1f} needs a win rate of {need:.3f} -- a lift of "
              f"{need-w:+.3f} over what this delivers")
print(f"\ntotal {time.time()-t0:.0f}s")
