"""D5 -- is the PIN family's small contribution just more volatility?

D4 left one clean question. PIN survives the 8-seed ablation with t -2.60 -- small but consistent
-- while being NEGATIVELY informed on its own (IC -0.0087, t -84). A feature set that only helps in
combination is either capturing an interaction or duplicating a neighbour, and `STUDY_PIN_BAYES`
already established what PIN measures: the DISPERSION of the buy and sell series. Dispersion is a
volatility concept, and volatility is the one family that carries this model (t -17.77).

So: does PIN still add anything once volatility is present, and does it add anything volatility
does not already supply? Two nested comparisons and a correlation, all on the SIGNAL BARS.
"""
import pickle, sys, time
import numpy as np, pandas as pd, runpy
sys.path.insert(0, "research/v66")
import torch; torch.set_num_threads(1)

t0 = time.time()
pd.set_option("display.width", 200)
print(__doc__)
_m = runpy.run_path("research/v66/_mlmod.py")
oof, ic = _m["oof"], _m["ic"]
FE = pd.read_parquet("results/v66/events_features.parquet")
with open("results/v66/frozen.pkl", "rb") as f:
    Z = pickle.load(f)
COLS = Z["cols"]
R = FE[FE.blk == 0].reset_index(drop=True)
y = R.R.to_numpy(float)
PIN = [c for c in COLS if c.startswith("pin.")]
VOL = [c for c in COLS if c.startswith("vol.")]
OTH = [c for c in COLS if not c.startswith("pin.") and not c.startswith("vol.")]
SEEDS = range(8)

def score(cols, label):
    v = np.array([ic(oof(R, cols, "rf", seed=s), y) for s in SEEDS])
    print(f"{label:>28} {len(cols):>4} {v.mean():>9.4f} {v.std(ddof=1):>8.4f}", flush=True)
    return v

print("=" * 110)
print("D5.1  NESTED SETS -- 8 seeds each, regularised random forest, OOF IC on the return")
print("=" * 110)
print(f"{'feature set':>28} {'k':>4} {'mean IC':>9} {'sd':>8}")
v_vol = score(VOL, "vol only")
v_volpin = score(VOL + PIN, "vol + pin")
v_all = score(COLS, "everything (65)")
v_nopin = score([c for c in COLS if not c.startswith("pin.")], "everything minus pin")
v_novol = score([c for c in COLS if not c.startswith("vol.")], "everything minus vol")
v_pin = score(PIN, "pin only")

def tt(a, b):
    d = a - b
    return d.mean(), d.mean() / max(d.std(ddof=1) / np.sqrt(len(d)), 1e-12)

print("\n  the two nested comparisons:")
m, t = tt(v_volpin, v_vol)
print(f"    adding PIN to volatility alone      {m:+.4f}  t {t:+6.2f}  "
      f"({'helps' if t > 2 else 'does not help'})")
m, t = tt(v_all, v_nopin)
print(f"    adding PIN to everything else       {m:+.4f}  t {t:+6.2f}  "
      f"({'helps' if t > 2 else 'does not help'})")
m, t = tt(v_vol, v_all)
print(f"    volatility ALONE vs all 65 features {m:+.4f}  t {t:+6.2f}")

print("\n" + "=" * 110)
print("D5.2  WHAT PIN OVERLAPS WITH -- correlation on the SIGNAL BARS, which is where it acts")
print("=" * 110)
Zm = R[COLS].to_numpy(float)
idx = {c: i for i, c in enumerate(COLS)}
C = np.corrcoef(Zm.T)
rows = []
for p in PIN:
    best = max(((c, abs(C[idx[p], idx[c]])) for c in COLS if not c.startswith("pin.")),
               key=lambda z: z[1])
    rows.append(dict(pin=p, nearest=best[0], rho=C[idx[p], idx[best[0]]],
                     max_vol=max((abs(C[idx[p], idx[c]]) for c in VOL), default=np.nan)))
P = pd.DataFrame(rows).sort_values("rho", key=abs, ascending=False)
print(P.round(4).to_string(index=False))
print(f"\n  mean |rho| of a pin.* feature to its nearest VOLATILITY feature: "
      f"{P.max_vol.mean():.4f}   max {P.max_vol.max():.4f}")

print("\n" + "=" * 110)
print("D5.3  THE SIMPLEST THING THAT WORKS -- how far does one volatility feature get?")
print("=" * 110)
print(f"{'feature set':>28} {'k':>4} {'mean IC':>9} {'sd':>8}")
sing = []
for c in VOL:
    v = np.array([ic(oof(R, [c], "rf", seed=s), y) for s in SEEDS])
    sing.append((c, v.mean(), v.std(ddof=1)))
sing.sort(key=lambda z: -z[1])
for c, m, s in sing:
    print(f"{c:>28} {1:>4} {m:>9.4f} {s:>8.4f}")
print(f"\n  best single volatility feature {sing[0][0]} at IC {sing[0][1]:.4f} against all 65 "
      f"features at {v_all.mean():.4f}")
pd.DataFrame(dict(set=["vol", "vol+pin", "all", "all-pin", "all-vol", "pin"],
                  ic=[v_vol.mean(), v_volpin.mean(), v_all.mean(), v_nopin.mean(),
                      v_novol.mean(), v_pin.mean()])).to_csv("results/v66/d5_nested.csv",
                                                            index=False)
print(f"\n[{time.time()-t0:.0f}s]")
