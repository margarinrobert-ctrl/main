"""V4 -- PART C: does a movement forecast change a DECISION?

An IC table is not a result. Parts A and B established that magnitude, envelope and duration are
forecastable (|IC| 0.29-0.60, clearing a block-permutation null 24 of 24) while direction and
straightness are not (0.060 and 0.041, clearing 0 of 4 and 2 of 4). The only question left is
whether the forecastable half is worth anything, and there is exactly one place `STUDY_V22` says it
should be: an ATR stop is BACKWARD-looking while volatility MEAN-REVERTS, so heat measured in ATR
units is 1.8-2.2x larger when volatility sits LOW in its own distribution.

So: on the P3 primary that clears Gate 1 (Donchian 11/47, RTH, 15m), replace the trailing ATR that
sets the stop with a FORECAST of forward volatility, and compare four arms end to end:

    fixed      stop = 3.8 x ATR(14)              -- as searched
    v22        stop = 2.5N if vol pct <= 0.5 else 1.5N, scaled to the same mean -- the shipped rule
    forecast   stop = 3.8 x (forecast of forward vol, expressed in ATR units)
    shuffled   the same forecast, its VALUES PERMUTED -- the twin that prices the machinery

The forecast is a ridge on the seven-feature volatility set, fitted on the RESEARCH block only, and
the shuffled arm is what separates "the forecast helped" from "changing the stop at all helped".
Every arm is re-simulated end to end; nothing is a subset of another arm's trades.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research/v67"); sys.path.insert(0, "research/v66")
sys.path.insert(0, "research/v61sess"); sys.path.insert(0, "research/v22")
import v67core as V
import v66core as VC
import v66_parity as P
import v22vol as VV
import sess_core as SC
from sklearn.linear_model import Ridge

t0 = time.time(); pd.set_option("display.width", 200)
def say(*a): print(*a, flush=True)
say(__doc__)

D = V.load(15)
mR = D["blk"] == 0
say(f"[{time.time()-t0:6.1f}s] {D['n']:,} bars")

# ---- the forecast: forward realised vol at h=16, in ATR units, from the seven-feature set
H = 16
T = V.build_targets(D, H)
tgt = T["rv"]                                    # forward realised vol, percent
F7 = P.features(D)                               # the seven, exactly as V66 ships them
ok = np.isfinite(F7).all(axis=1) & np.isfinite(tgt)
tr = ok & mR
say(f"[{time.time()-t0:6.1f}s] fitting the forecast on {int(tr.sum()):,} research bars "
    f"(7 features -> forward rv at h={H})")
mdl = Ridge(alpha=5.0).fit(F7[tr], tgt[tr])
pred = np.full(D["n"], np.nan)
pred[ok] = mdl.predict(F7[ok])
say(f"           in-sample IC {V.ic(pred[tr], tgt[tr]):.4f}   "
    f"locked IC {V.ic(pred[ok & ~mR], tgt[ok & ~mR]):.4f}")

# express the forecast as a MULTIPLIER on the trailing ATR, centred on 1 over research
atr = D["atr"]
cur = pd.Series(np.diff(np.log(np.maximum(D['c'],1e-12)), prepend=0.0)).rolling(96)\
        .std(ddof=1).to_numpy() * 100.0
with np.errstate(invalid="ignore", divide="ignore"):
    ratio = pred / np.maximum(cur, 1e-9)
ctr = np.nanmedian(ratio[tr])
mult = np.clip(ratio / ctr, 0.5, 2.0)
say(f"           forecast/current vol ratio: research median {ctr:.4f}, "
    f"multiplier p5-p95 {np.nanquantile(mult[tr],0.05):.3f}-{np.nanquantile(mult[tr],0.95):.3f}")

# ---- the V22 rule and the shuffled twin, on the same grid
vpct = pd.Series(cur).rolling(500).rank(pct=True).to_numpy()
v22 = np.where(np.isfinite(vpct) & (vpct <= 0.5), 2.5, 1.5)
v22 = v22 / np.nanmean(v22[tr]) * 1.0            # same mean stop as fixed, so only SHAPE differs
rng = np.random.default_rng(4)
shuf = mult.copy()
fin = np.flatnonzero(np.isfinite(shuf))
sv = shuf[fin].copy(); rng.shuffle(sv); shuf[fin] = sv

def walk(mults, tag):
    """P3's own walker with a per-bar stop multiplier. Re-simulated, never a subset."""
    o, hi, lo, c = D["o"], D["h"], D["l"], D["c"]
    mod, n = D["mod"], D["n"]
    ei = 11 - 2; xi = 47 - 2
    ent_hi, ex_lo = D["ent_hi"][ei], D["ex_lo"][xi]
    rows = []; i, lock = 200, -1
    last = int(D["last_bar"])
    while i < last:
        if i <= lock or not (570 <= mod[i] < 960):
            i += 1; continue
        a0 = atr[i]; mm = mults[i] if mults is not None else 1.0
        if not np.isfinite(a0) or a0 <= 0 or not np.isfinite(ent_hi[i]) or hi[i] < ent_hi[i] \
                or not np.isfinite(mm):
            i += 1; continue
        j = i + 1
        px = o[j] + SC.SLIP
        risk = 3.8 * a0 * mm
        fixed_lvl = px - risk
        tgt_lvl = px + 3.2 * a0
        e, out, why = j, np.nan, ""
        held = 0
        while e < n - 1:
            lvl = fixed_lvl
            if e > j:
                if np.isfinite(ex_lo[e]) and ex_lo[e] > lvl:
                    lvl = ex_lo[e]
                if np.isfinite(c[e - 1]) and lvl > c[e - 1]:
                    lvl = c[e - 1]
            if lo[e] <= lvl:
                out = (lvl if o[e] > lvl else o[e]) - SC.SLIP; why = "stop"; break
            if hi[e] >= tgt_lvl:
                out = (tgt_lvl if o[e] < tgt_lvl else o[e]) - SC.SLIP; why = "target"; break
            held += 1
            if held >= 96:
                out = o[e + 1] - SC.SLIP; e += 1; why = "hold"; break
            e += 1
        if not why:
            break
        g = out - px - SC.COST
        rows.append(dict(sig=i, pts=g, pct=100.0 * g / px, R=g / risk, why=why,
                         blk=D["blk"][i], risk=risk))
        lock, i = e, e + 1
    return pd.DataFrame(rows)

say(f"\n[{time.time()-t0:6.1f}s] four arms, re-simulated end to end")
say(f"{'arm':>10} {'block':>9} {'n':>5} {'%/ev':>9} {'PF':>7} {'stop%':>7} {'mean risk':>10}")
res = {}
for tag, mm in (("fixed", None), ("v22", v22), ("forecast", mult), ("shuffled", shuf)):
    t = walk(mm, tag)
    res[tag] = t
    for blk, nm in ((0, "research"), (1, "LOCKED")):
        s = t[t.blk == blk]
        if len(s) < 20:
            continue
        x = s.pct.to_numpy()
        pf = x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)
        say(f"{tag:>10} {nm:>9} {len(s):>5} {x.mean():>9.5f} {pf:>7.3f} "
            f"{100*np.mean(s.why=='stop'):>6.1f}% {s.risk.mean():>10.2f}")
    say("")
out = []
for tag in ("fixed", "v22", "forecast", "shuffled"):
    for blk, nm in ((0, "research"), (1, "LOCKED")):
        s = res[tag][res[tag].blk == blk]
        x = s.pct.to_numpy()
        out.append(dict(arm=tag, block=nm, n=len(s), pct=x.mean(),
                        pf=x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9),
                        stop_rate=float(np.mean(s.why == "stop"))))
O = pd.DataFrame(out)
O.to_csv("results/v67/v4_decision.csv", index=False)

say("THE COMPARISON THAT MATTERS -- forecast against its own SHUFFLED twin")
for blk in ("research", "LOCKED"):
    f = O[(O.arm == "forecast") & (O.block == blk)].iloc[0]
    s = O[(O.arm == "shuffled") & (O.block == blk)].iloc[0]
    b = O[(O.arm == "fixed") & (O.block == blk)].iloc[0]
    say(f"  {blk:>8}: fixed PF {b.pf:.3f}   forecast {f.pf:.3f}   shuffled {s.pf:.3f}   "
        f"forecast-minus-shuffled {f.pf - s.pf:+.3f}")
say(f"\n[{time.time()-t0:6.1f}s] done")
