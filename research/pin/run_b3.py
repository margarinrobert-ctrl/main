"""B3 -- Gate 1 on the Bayesian posterior, and on the paper's own INTRADAY-INTERVAL construction.

Two primaries, both scored before any feature exists, research block only:

  A. SESSION construction (B1's). Parameters fitted on 120 prior SESSIONS of daily B/S; the signal
     is the posterior given the flow accumulated SO FAR TODAY. Identical to the Yan version in
     every respect except the estimator, so the difference IS the estimator.

  B. INTERVAL construction. The paper's own generalisation -- "the type of news is fixed over
     intervals at other frequencies, for example over a 15 minute interval" -- and its claim that
     26 intraday observations suffice. Parameters fitted on the previous 5 sessions' worth of
     10-minute periods; the signal is the posterior for THE CURRENT PERIOD from that period's own
     B and S. This is a genuinely different and much faster signal, and it is the construction the
     paper argues for.

Both are scored against a MATCHED RANDOM ENTRY -- same window, same rate, same side mix, same
exits, sorted so the position lock rejects the same way (STUDY_V59).
"""
import sys, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/pin"); sys.path.insert(0, "research/scalp5")
import numpy as np, pandas as pd
import pin_core as P
import pin_bayes as PB
import s5data as S
import s5walk as W

t0 = time.time()
TF = 10
rng = np.random.default_rng(7)
pd.set_option("display.width", 200)

D = P.load(tf=TF)
b1 = D["base"]
c, o = b1["close"].to_numpy(), b1["open"].to_numpy()
v = b1["volume"].to_numpy().astype(float)
mod1 = (b1.index.hour * 60 + b1.index.minute).to_numpy()
day1 = b1.index.normalize().values.astype("datetime64[D]").astype(np.int64)
on1 = (mod1 >= D["win_open"]) & (mod1 < D["win_close"])
vbar = np.nanmean(v[on1])
w = v / vbar

# ------------------------------------------------------------------ A: session construction
f = pd.DataFrame({"b": np.where(on1 & (c > o), w, 0.0),
                  "s": np.where(on1 & (c < o), w, 0.0), "d": day1}, index=b1.index)
agg = f[on1].groupby("d").agg(B=("b", "sum"), S=("s", "sum")).sort_index()
Bd, Sd = agg.B.to_numpy(), agg.S.to_numpy()
days_all = agg.index.to_numpy()
parA = {}
for i in range(len(days_all)):
    lo = max(0, i - 120)
    parA[int(days_all[i])] = (None if i - lo < 30 else
                              PB.gibbs(np.rint(Bd[lo:i]), np.rint(Sd[lo:i]),
                                       sweeps=900, burn=300, seed=i))
cb = f.groupby("d").b.cumsum().to_numpy(); cs = f.groupby("d").s.cumsum().to_numpy()
cb[~on1] = np.nan; cs[~on1] = np.nan
BtA = pd.Series(cb, index=b1.index).reindex(D["ix"], method="ffill").to_numpy()
StA = pd.Series(cs, index=b1.index).reindex(D["ix"], method="ffill").to_numpy()
wl = D["win_close"] - D["win_open"]
pgA = np.full(D["n"], np.nan); pbA = np.full(D["n"], np.nan)
for i in np.flatnonzero(D["inw"]):
    p = parA.get(int(D["day"][i]))
    if p is None or not np.isfinite(BtA[i]):
        continue
    fr = min(max((D["mod"][i] + TF - D["win_open"]) / wl, 1e-3), 1.0)
    g, bb, _ = PB.posterior_state(BtA[i], StA[i], p, fr)
    pgA[i] = g; pbA[i] = bb
print(f"A built  fits {sum(x is not None for x in parA.values())}   [{time.time()-t0:.0f}s]")

# ------------------------------------------------------------------ B: interval construction
# each 10-minute chart bar is one "trading period"; B and S are that period's own sub-bar flow
per = pd.DataFrame({"b": np.where(on1 & (c > o), w, 0.0),
                    "s": np.where(on1 & (c < o), w, 0.0)}, index=b1.index)
BtB = per.b.resample(f"{TF}min").sum().reindex(D["ix"]).to_numpy()
StB = per.s.resample(f"{TF}min").sum().reindex(D["ix"]).to_numpy()
inw = D["inw"]
dayx = D["day"]
udays = np.unique(dayx[inw])
parB = {}
for j, dd in enumerate(udays):
    prev = (dayx < dd) & inw                       # every period strictly before today
    idx = np.flatnonzero(prev)[-5 * 40:]           # the previous ~5 sessions of periods
    if len(idx) < 60:
        parB[int(dd)] = None
        continue
    parB[int(dd)] = PB.gibbs(np.rint(np.nan_to_num(BtB[idx])), np.rint(np.nan_to_num(StB[idx])),
                             sweeps=900, burn=300, seed=1000 + j)
pgB = np.full(D["n"], np.nan); pbB = np.full(D["n"], np.nan)
for i in np.flatnonzero(inw):
    p = parB.get(int(dayx[i]))
    if p is None or not np.isfinite(BtB[i]):
        continue
    g, bb, _ = PB.posterior_state(BtB[i], StB[i], p, 1.0)
    pgB[i] = g; pbB[i] = bb
print(f"B built  fits {sum(x is not None for x in parB.values())}   "
      f"mean period B {np.nanmean(BtB[inw]):.1f}   [{time.time()-t0:.0f}s]")

# ------------------------------------------------------------------ the walk
GEOM = dict(stop=2.5, tgt=0.0, be=0.0, be_off=0.0, arm=1.0, tr=1.0)
def walk(lg, sh):
    sig = lg | sh
    n = int(sig.sum())
    if n < 5:
        return pd.DataFrame(columns=["sig", "pts", "blk"])
    side = np.where(lg, 1, -1).astype(np.int64)
    z = lambda t: np.zeros(n, t)
    oi, ox, oR, op, ow = z(np.int64), z(np.int64), z(float), z(float), z(np.int64)
    oa, of, ob = z(float), z(float), z(np.int64)
    m = W.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], sig, side, D["last_win"],
               S.RT_POINTS, S.SLIP_POINTS, GEOM["stop"], GEOM["tgt"], GEOM["be"], GEOM["be_off"],
               GEOM["arm"], GEOM["tr"], oi, ox, oR, op, ow, oa, of, ob)
    t = pd.DataFrame(dict(sig=oi[:m], pts=op[:m]))
    t["blk"] = D["blk"][t.sig.to_numpy()]
    return t

print("\n" + "=" * 112)
print("B3.1  GATE 1 -- RESEARCH BLOCK ONLY, both constructions, against a matched random entry")
print("=" * 112)
print(f"{'build':>10} {'thresh':>7} {'n':>6} {'pts':>8} {'PF':>7} {'win%':>7} "
      f"{'ctl_med':>8} {'excess':>8} {'p':>6}")
rows = []
for name, (pg, pb) in (("session", (pgA, pbA)), ("interval", (pgB, pbB))):
    for th in (0.50, 0.70, 0.85, 0.95):
        lg = np.nan_to_num(pg, nan=0.0) >= th
        sh = np.nan_to_num(pb, nan=0.0) >= th
        lg &= inw & ~D["last_win"]; sh &= inw & ~D["last_win"] & ~lg
        t = walk(lg, sh)
        s = t[t.blk == 0]
        if len(s) < 20:
            print(f"{name:>10} {th:>7} {len(s):>6}  -- too few --")
            continue
        real = s.pts.mean()
        elig = np.flatnonzero(inw & ~D["last_win"] & (D["blk"] == 0)
                              & np.isfinite(D["atr"]) & (D["atr"] > 0))
        p_long = float(lg[s.sig.to_numpy()].mean())
        ctl = []
        for j in range(200):
            pick = np.sort(rng.choice(elig, min(len(s), len(elig)), replace=False))
            L = np.zeros(D["n"], bool); Sh = np.zeros(D["n"], bool)
            isl = rng.random(len(pick)) < p_long
            L[pick[isl]] = True; Sh[pick[~isl]] = True
            q = walk(L, Sh); q = q[q.blk == 0]
            if len(q):
                ctl.append(q.pts.mean())
        ctl = np.array(ctl)
        r = s.pts.to_numpy()
        pf = r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9)
        pv = float((ctl >= real).mean())
        rows.append(dict(build=name, thresh=th, n=len(s), pts=real, PF=pf,
                         ctl=np.median(ctl), p=pv))
        print(f"{name:>10} {th:>7} {len(s):>6} {real:>8.2f} {pf:>7.3f} "
              f"{(r > 0).mean()*100:>6.1f}% {np.median(ctl):>8.2f} "
              f"{real-np.median(ctl):>8.2f} {pv:>6.3f}")
R = pd.DataFrame(rows)
R.to_csv("research/pin/b3_gate1.csv", index=False)
if len(R):
    print(f"\n  research cells clearing at p<=0.05: {int((R.p<=0.05).sum())} of {len(R)}")
    print(f"  best research p {R.p.min():.3f}   best research PF {R.PF.max():.3f}")
print(f"[{time.time()-t0:.0f}s]")
