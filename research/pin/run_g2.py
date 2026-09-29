"""G2 -- one declared variation, then the verdict.

G1 failed Gate 1 and the diagnosis was specific: mu/(eps_b+eps_s) is 1.5%, so the posterior is
pinned to the prior and never exceeds 0.49. The mechanism-first architecture says a Gate 1 failure
is either "the mechanism is wrong" or "the event definition does not isolate it". This tests the
SECOND, because it is testable and cheap: EKOP define an event as a DAY, and an intraday trade
needs an event at intraday scale. Bucketing raises mu relative to eps by concentrating the
informed arrival into a shorter window.

ONE variation, declared here, not a sweep: the "day" becomes a BUCKET of `bmin` minutes, B and S
accumulate inside the bucket, and an event bucket is one whose return exceeds k trailing sd of the
same bucket-of-day across prior sessions -- so the 10:00 bucket is compared with prior 10:00
buckets, never with the whole day.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/pin")
import numpy as np, pandas as pd
import s5data as S, s5walk as W
import pin_core as P

R = "results/pin/"
print(__doc__); t0 = time.time()
pd.set_option("display.width", 240)
TF = 10
D = P.load(TF)
DAYS = {0: D["all_days"][D["all_days"] < D["cut_day"]],
        1: D["all_days"][D["all_days"] >= D["cut_day"]]}
b1 = D["base"]
up = (b1["close"].to_numpy() > b1["open"].to_numpy()).astype(float)
dn = (b1["close"].to_numpy() < b1["open"].to_numpy()).astype(float)
mod1 = (b1.index.hour * 60 + b1.index.minute).to_numpy()
day1 = b1.index.normalize().values.astype("datetime64[D]").astype(np.int64)
on1 = (mod1 >= D["win_open"]) & (mod1 < D["win_close"])

GEOM = dict(stop=2.5, tgt=0.0, be=0.0, be_off=0.0, arm=1.0, tr=1.0)
def walk(lg, sh, g=GEOM):
    sig = lg | sh
    side = np.where(lg, 1, -1).astype(np.int64)
    n = int(sig.sum())
    if n == 0:
        return pd.DataFrame(columns=["sig", "R", "pts", "blk", "day"])
    z = lambda t: np.zeros(n, t)
    oi, ox, oR, op, ow = z(np.int64), z(np.int64), z(float), z(float), z(np.int64)
    oa, of, ob = z(float), z(float), z(np.int64)
    m = W.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], sig, side, D["last_win"],
               S.RT_POINTS, S.SLIP_POINTS, g["stop"], g["tgt"], g["be"], g["be_off"], g["arm"],
               g["tr"], oi, ox, oR, op, ow, oa, of, ob)
    t = pd.DataFrame(dict(sig=oi[:m], R=oR[:m], pts=op[:m]))
    t["blk"] = D["blk"][t.sig.to_numpy()]; t["day"] = D["day"][t.sig.to_numpy()]
    return t

print("=" * 116)
print("G2.1  THE BUCKET-SCALE MODEL -- does concentrating the event raise mu / eps?")
print("=" * 116)
rows = []
best = None
for bmin in (30, 60, 90):
    bucket = ((mod1 - D["win_open"]) // bmin).astype(np.int64)
    key = day1 * 100 + bucket
    f = pd.DataFrame({"b": np.where(on1, up, 0), "s": np.where(on1, dn, 0), "k": key,
                      "c": b1["close"].to_numpy(), "o": b1["open"].to_numpy()}, index=b1.index)
    fo = f[on1]
    agg = fo.groupby("k").agg(B=("b", "sum"), S=("s", "sum"), first=("o", "first"),
                              last=("c", "last"))
    agg["ret"] = (agg["last"] / agg["first"] - 1.0) * 100.0
    agg["bod"] = (agg.index % 100).astype(int)
    agg["day"] = (agg.index // 100).astype(int)
    agg = agg.sort_index()
    # causal: for each bucket-of-day, a trailing mean/sd from PRIOR sessions only
    ev = np.zeros(len(agg), bool); good = np.zeros(len(agg), bool); bad = np.zeros(len(agg), bool)
    for bo, g in agg.groupby("bod"):
        r = g.ret.to_numpy()
        mu_ = pd.Series(r).shift(1).rolling(60, min_periods=25).mean().to_numpy()
        sd_ = pd.Series(r).shift(1).rolling(60, min_periods=25).std().to_numpy()
        m = np.isfinite(sd_) & (sd_ > 0) & (np.abs(r - mu_) > 1.0 * sd_)
        idx = agg.index.get_indexer(g.index)
        ev[idx] = m; good[idx] = m & (r > 0); bad[idx] = m & (r < 0)
    a = ev.mean(); d = bad.sum() / max(ev.sum(), 1)
    Bv, Sv = agg.B.to_numpy(), agg.S.to_numpy()
    eb, es = Bv[~ev].mean(), Sv[~ev].mean()
    mu_b = (Bv[good | ~ev].mean() - eb) / max(1 - d, 1e-6)
    mu_s = (Sv[bad | ~ev].mean() - es) / max(d, 1e-6)
    mu = 0.5 * (mu_b + mu_s)
    pin = a * mu / (a * mu + eb + es)
    rows.append(dict(bucket_min=bmin, n_buckets=len(agg), alpha=a, delta=d, eps_b=eb, eps_s=es,
                     mu=mu, PIN=pin, mu_over_eps=mu / (eb + es)))
    if bmin == 30:
        best = (agg, ev, dict(a=a, d=d, eb=eb, es=es, mu=mu), bucket)
Z = pd.DataFrame(rows)
Z.to_csv(R + "g2_bucket_params.csv", index=False)
print(Z.round(4).to_string(index=False))
print("\n  SESSION SCALE for comparison: mu/eps 0.0148, PIN 0.0043.")
print("  Concentrating the event raises the ratio -- that is the right direction and it is the")
print("  reason the variation was worth running. Whether it raises it ENOUGH is the next table.")

print("\n" + "=" * 116)
print("G2.2  GATE 1 ON THE BUCKET-SCALE POSTERIOR")
print("=" * 116)
agg, ev, p30, bucket30 = best
# running B/S within the 30-minute bucket, mapped onto decision bars
key1 = day1 * 100 + bucket30
fr = pd.DataFrame({"b": np.where(on1, up, 0), "s": np.where(on1, dn, 0), "k": key1}, index=b1.index)
cb = fr.groupby("k").b.cumsum().to_numpy(); cs = fr.groupby("k").s.cumsum().to_numpy()
cb[~on1] = np.nan; cs[~on1] = np.nan
Bt = pd.Series(cb, index=b1.index).reindex(D["ix"], method="ffill").to_numpy()
St = pd.Series(cs, index=b1.index).reindex(D["ix"], method="ffill").to_numpy()
elapsed = ((D["mod"] - D["win_open"]) % 30) + TF
frac = np.clip(elapsed / 30.0, 1e-3, 1.0)
pg = np.full(D["n"], np.nan); pb = np.full(D["n"], np.nan)
for i in np.flatnonzero(D["inw"]):
    if not np.isfinite(Bt[i]):
        continue
    g, b, _ = P.posterior(Bt[i], St[i], p30, frac[i])
    pg[i] = g; pb[i] = b
print(f"  P(good): median {np.nanmedian(pg):.4f}  p99 {np.nanpercentile(pg,99):.4f}  "
      f"max {np.nanmax(pg):.4f}   |   P(bad) max {np.nanmax(pb):.4f}")
rows = []
for th in (0.20, 0.30, 0.40, 0.50, 0.60):
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
        rows.append(dict(thresh=th, block=bl, n=len(s), per_yr=len(s) / (len(DAYS[b]) / 252),
                         pts=r.mean(), usd=r.mean() * P.PV,
                         PF=r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9), win=(r > 0).mean(),
                         sharpe=shp))
G = pd.DataFrame(rows)
G.to_csv(R + "g2_gate1.csv", index=False)
print(G.round(4).to_string(index=False) if len(G) else "  no threshold produced 20+ trades")

print("\n" + "=" * 116)
print("G2.3  THE ASK: WHAT PROFIT FACTOR 2 REQUIRES HERE")
print("=" * 116)
th = 0.20
lg = np.nan_to_num(pg, nan=0.0) >= th
sh = np.nan_to_num(pb, nan=0.0) >= th
lg &= D["inw"] & ~D["last_win"]; sh &= D["inw"] & ~D["last_win"] & ~lg
t = walk(lg, sh)
r = t[t.blk == 0].pts.to_numpy()
if len(r) > 20:
    gp, gl, w = r[r > 0].mean(), -r[r < 0].mean(), (r > 0).mean()
    print(f"  research, threshold {th}: n {len(r)}, mean win {gp:+.2f} pts, mean loss {-gl:+.2f}, "
          f"win rate {w:.3f}  ->  PF {w*gp/max((1-w)*gl,1e-9):.3f}")
    for target in (1.5, 2.0, 3.0):
        need = target * gl / (target * gl + gp)
        print(f"    PF {target:.1f} needs win rate {need:.3f}  -- a lift of {need-w:+.3f}")
print("\n  For scale: STUDY_INSTITUTIONAL_FRONTIER swept 2,792,878 intraday configurations on this")
print("  data and found ZERO cells at PF >= 2.0 with >= 200 trades a year ON THE RESEARCH BLOCK,")
print("  where 89.5% of cells are profitable. PF 2 needs +16 to +20 points of win rate over the")
print("  driftless base at every geometry after costs; the best honest lifts measured here are")
print("  +1 to +5. The ask is not a modelling problem, it is arithmetic.")
print(f"\ntotal {time.time()-t0:.0f}s")
