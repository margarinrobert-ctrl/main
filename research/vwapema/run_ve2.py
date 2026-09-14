"""TEST 2 -- drop-one, the parameter neighbourhood, then ONE read of the locked block.

Drop-one answers which of the six conditions earns its place; the neighbourhood answers whether
the spec's ten free numbers sit on a plateau or a spike. Both are research-only. The locked block
is read once, at the end, with the trial count stated first.
"""
import os, sys, json
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

RNG = np.random.default_rng(77)
pd.set_option("display.width", 210)
print(__doc__)
D = V.build()
r = D["blk"] == 0
TRIALS = {"conditions_dropone": 12, "params_swept": 0, "arms": 14, "sides": 2}


def build_sig(D, side, drop=None, p=None, use_vol=True):
    sig, P = V.triggers(D, side=side, use_vwap_vol=use_vol, p=p)
    if drop is None:
        return sig
    keys = ["C1", "C2", "C3", "C4", "C5", "C6", "ambig"]
    m = np.ones(D["n"], bool)
    for k in keys:
        if k != drop:
            m &= np.nan_to_num(P[k], nan=False).astype(bool)
    return m & D["rth"]


def ctl_p(D, n_target, side, obs, blk=0, draws=400, **kw):
    idx = np.flatnonzero((D["blk"] == blk) & D["rth"])
    rate = min(1.0, n_target / max(len(idx), 1))
    out = []
    for _ in range(draws):
        g = np.zeros(D["n"], bool); g[idx[RNG.random(len(idx)) < rate]] = True
        t = V.run(D, g, side=side, **kw); t = t[t.blk == blk]
        if len(t) >= 20:
            out.append(t.R.mean())
    out = np.array(out)
    return float((out >= obs).mean()), float(np.median(out))


print("=" * 112)
print("DROP-ONE -- does each of the six conditions earn its place? (research block)")
print("=" * 112)
rows = []
for side, nm in ((1, "LONG"), (-1, "SHORT")):
    full = build_sig(D, side)
    tf = V.run(D, full, side=side); tf = tf[tf.blk == 0]; sf = V.stats(tf)
    rows.append(dict(side=nm, dropped="-- none (full rule) --", n=sf["n"], R=sf["R"], pf=sf["pf"],
                     win=sf["win"], totR=sf["totR"], dR=0.0))
    for k in ("C1", "C2", "C3", "C4", "C5", "C6", "ambig"):
        s = build_sig(D, side, drop=k)
        t = V.run(D, s, side=side); t = t[t.blk == 0]; st = V.stats(t)
        rows.append(dict(side=nm, dropped=k, n=st["n"], R=st["R"], pf=st["pf"], win=st["win"],
                         totR=st["totR"], dR=st["R"] - sf["R"]))
DO = pd.DataFrame(rows)
for nm in ("LONG", "SHORT"):
    print(f"  --- {nm} ---")
    print(DO[DO.side == nm].drop(columns="side").to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
    print()
print("  dR > 0 means REMOVING the condition IMPROVES the rule -- it was subtracting.")

print("\n" + "=" * 112)
print("PARAMETER NEIGHBOURHOOD -- plateau or spike? (research block, long side)")
print("=" * 112)
LAD = dict(ema_slow=[100, 150, 200, 250, 300], ema_pull=[20, 34, 50, 70, 100],
           atr_stop=[0.25, 0.5, 0.75, 1.0, 1.5], vol_mult=[1.0, 1.1, 1.3, 1.5],
           range_mult=[0.5, 0.8, 1.0, 1.3], wick_body=[1.0, 1.5, 2.0, 3.0])
rows = []
for k, vals in LAD.items():
    for x in vals:
        s = build_sig(D, 1, p={k: x})
        t = V.run(D, s, side=1, p={k: x}); t = t[t.blk == 0]; st = V.stats(t)
        rows.append(dict(param=k, value=x, n=st["n"], R=st["R"], pf=st["pf"], spec=(x == V.PARAMS[k])))
        TRIALS["params_swept"] += 1
for tR in (1.5, 2.0, 3.0, 4.0, 5.0):
    s = build_sig(D, 1)
    t = V.run(D, s, side=1, tgt_R=tR); t = t[t.blk == 0]; st = V.stats(t)
    rows.append(dict(param="target_R", value=tR, n=st["n"], R=st["R"], pf=st["pf"], spec=(tR == 3.0)))
    TRIALS["params_swept"] += 1
N = pd.DataFrame(rows)
print(N.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
pos = N[N.R > 0]
print(f"\n  cells with a positive R on research: {len(pos)} of {len(N)}; the spec's own settings are "
      f"{'positive' if float(N[(N.param=='ema_slow')&(N.spec)].R.iloc[0])>0 else 'NEGATIVE'} on the long side.")

# ---------------------------------------------------------------- the one locked read
n_trials = sum(TRIALS.values())
print("\n" + "=" * 112)
print("THE ONE LOCKED READ")
print("=" * 112)
print(f"  MULTIPLICITY FIRST: {TRIALS} = {n_trials} looks taken on research before this read.")
print(f"  Declared in advance: the rule EXACTLY AS SPECIFIED, both sides, against the same matched")
print(f"  control, plus the zero-cost arm. No parameter is changed from the spec's own values.\n")
rows = []
for side, nm in ((1, "LONG"), (-1, "SHORT")):
    sig = build_sig(D, side)
    for blk, bn in ((0, "research"), (1, "LOCKED")):
        t = V.run(D, sig, side=side); t = t[t.blk == blk]
        st = V.stats(t)
        p, med = ctl_p(D, st["n"], side, st["R"], blk=blk)
        tz = V.run(D, sig, side=side, cost_rt=0.0, slip=0.0); tz = tz[tz.blk == blk]
        rows.append(dict(side=nm, block=bn, n=st["n"], R=st["R"], pct=st["pct"], pf=st["pf"],
                         win=st["win"], totR=st["totR"], ret_dd=st["ret_dd"],
                         ctl_R=med, p_ctl=p, gross_R=V.stats(tz)["R"]))
L = pd.DataFrame(rows)
print(L.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
for nm in ("LONG", "SHORT"):
    a = L[L.side == nm]
    rr, ll = a[a.block == "research"].iloc[0], a[a.block == "LOCKED"].iloc[0]
    shape = "decays (right shape)" if ll.R < rr.R else "GROWS on locked -- the WRONG SHAPE"
    print(f"  {nm}: research {rr.R:+.4f} -> locked {ll.R:+.4f}  ({shape})")

# ---------------------------------------------------------------- the paper's own sample
print("\n" + "=" * 112)
print("THE PAPER'S OWN SAMPLE -- Jan-Dec 2024, a labelled slice inside the locked block")
print("=" * 112)
yr = pd.DatetimeIndex(D["ix"]).year
rows = []
for side, nm in ((1, "LONG"), (-1, "SHORT")):
    sig = build_sig(D, side)
    t = V.run(D, sig, side=side)
    ty = t[pd.DatetimeIndex(t.ts).year == 2024]
    st = V.stats(ty)
    rows.append(dict(side=nm, **st))
P24 = pd.DataFrame(rows)
print(P24.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
print("  the paper claims +0.414 R/trade, 45.3% win, PF 1.76, 3.99 Sharpe on this calendar year.")

print("\n  --- by calendar year, long side, as specified ---")
sig = build_sig(D, 1); t = V.run(D, sig, side=1)
t["year"] = pd.DatetimeIndex(t.ts).year
Y = t.groupby("year").agg(n=("R", "size"), R=("R", "mean"), totR=("R", "sum"),
                          win=("R", lambda x: 100 * (x > 0).mean()))
print(Y.to_string(float_format=lambda v: f"{v:9.4f}"))
print(f"  years positive: {int((Y.R>0).sum())} of {len(Y)}")

os.makedirs("results/vwapema", exist_ok=True)
DO.to_csv("results/vwapema/dropone.csv", index=False)
N.to_csv("results/vwapema/neighbourhood.csv", index=False)
L.to_csv("results/vwapema/locked.csv", index=False)
Y.to_csv("results/vwapema/byyear.csv")
json.dump(dict(trials=TRIALS, total=n_trials), open("results/vwapema/trials.json", "w"), indent=1)
