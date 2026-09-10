"""x4 -- pool what may honestly be pooled, count the replications, and price the MDE.

Three things, in this order.

  1. THE REPLICATION COUNT for the two pre-declared hypotheses, stated in `run_x3.py` before any of
     these markets was read.
  2. THE POOLED READ, twice: over all four fresh markets, and over a DE-DUPLICATED set -- because
     x2 measured US100/NQ at 82-85% identical signal bars (daily leg correlation 0.879) and
     US30/US30I at 89-91% (0.922). Those are single indices on two feeds, and `STUDY_TREND_LONG`
     is explicit that pooling them does not add a test.
  3. THE MDE AT EVERY COUNT, which is the number this workstream exists to move, against what
     PF 1.1 / 1.2 / 1.5 actually require -- computed from the pooled population's OWN win and loss
     magnitudes rather than assumed.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xm_core as X  # noqa: E402

pd.set_option("display.width", 240)
pd.set_option("display.max_columns", 60)
pd.set_option("display.max_rows", 300)

C = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache")
R = pd.read_csv(f"{C}/x3_cells.csv")
T = pd.read_csv(f"{C}/x3_trades.csv", parse_dates=["date"])

print("=" * 100)
print("x4  REPLICATION COUNT, POOLED READ, AND THE MDE AT EVERY COUNT")
print("=" * 100)

NEW = list(X.NEW_MARKETS)
RN = R[R.market.isin(NEW)].copy()

# ---------------------------------------------------------------- 1. replication --------------
print("\n--- 1. THE TWO PRE-DECLARED HYPOTHESES -------------------------------------------")
print("    H1  `+adx<=20` > `base` on per-trade mean.  H2  `+ema align` > `base` and positive.")
print("    Reported per cell (chance 50%) and per market (all cells of that market).\n")

def arm_vs_base(df, arm):
    b = df[df.arm == "base"].set_index(["market", "block", "param"])["mean"]
    a = df[df.arm == arm].set_index(["market", "block", "param"])["mean"]
    j = pd.concat([b.rename("base"), a.rename("arm")], axis=1).dropna()
    j["beats"] = j.arm > j.base
    j["positive"] = j.arm > 0
    return j.reset_index()

for arm, label in (("+adx<=20", "H1 ADX ceiling"), ("+ema align", "H2 EMA alignment"),
                   ("+both", "   (+both)"), ("conventional", "H3 conventional (must lose)")):
    j = arm_vs_base(RN, arm)
    per_mkt = j.groupby("market").agg(cells=("beats", "size"), beats=("beats", "sum"),
                                      pos=("positive", "sum"),
                                      mean_arm=("arm", "mean"), mean_base=("base", "mean"))
    per_mkt["market_pass"] = per_mkt.beats == per_mkt.cells
    print(f"  {label}   cells beating base: {int(j.beats.sum())}/{len(j)} "
          f"({j.beats.mean():.1%})   positive: {int(j.positive.sum())}/{len(j)}   "
          f"markets passing: {int(per_mkt.market_pass.sum())}/{len(per_mkt)}")
    print(per_mkt.round(4).to_string())
    print()

print("    US30 REFERENCE (section 12/13, reproduced exactly by x1):")
j30 = arm_vs_base(R[R.market == "US30"], "+adx<=20")
print(f"      +adx<=20 beats base in {int(j30.beats.sum())}/{len(j30)} US30 cells")
j30e = arm_vs_base(R[R.market == "US30"], "+ema align")
print(f"      +ema align beats base in {int(j30e.beats.sum())}/{len(j30e)} US30 cells")

# ---------------------------------------------------------------- 2. pooled -------------------
print("\n--- 2. POOLED READ ----------------------------------------------------------------")
DEDUP = ["US30I", "US100", "XAU"]     # one Dow feed, one Nasdaq feed, gold
print(f"    all four fresh markets: {NEW}")
print(f"    de-duplicated (x2: US100/NQ 82-85% same bar, US30/US30I 89-91%): {DEDUP}")

def pooled(sub, arm, param, unit="atr_u"):
    t = T[(T.market.isin(sub)) & (T.arm == arm) & (T.param == param)]
    if len(t) < 20:
        return None
    v = t[unit].to_numpy()
    se, n_eff, nd = X.cluster_se(v, t["date"].to_numpy())
    w, l = v[v > 0], v[v < 0]
    return dict(arm=arm, param=param, n=len(v), dates=nd, n_eff=round(n_eff, 0),
                mean=float(v.mean()), sd=float(v.std(ddof=1)), se=se,
                t=float(v.mean() / se), mde80=X.Z80 * se,
                outside=bool(abs(v.mean()) >= X.Z80 * se),
                pf=X.pf(v), win=float((v > 0).mean()),
                mean_win=float(w.mean()) if len(w) else np.nan,
                mean_loss=float(-l.mean()) if len(l) else np.nan)

for label, sub in (("ALL FOUR", NEW), ("DE-DUPLICATED", DEDUP)):
    for param in ("atr", "pts"):
        rows = [pooled(sub, a, param) for a, _ in X.ARMS]
        rows = [r for r in rows if r]
        print(f"\n    {label}  --  {param} parameterisation, ATR units per trade")
        print(pd.DataFrame(rows).round(4).to_string(index=False))

# ---------------------------------------------------------------- 3. MDE ---------------------
print("\n--- 3. THE MDE AT EVERY COUNT -----------------------------------------------------")
print("    MDE = 2.802 x SE_clustered.  US30 alone, section 12: 0.1849 ATR = 5.73 points.")


def pf_required(mean_win, mean_loss, pf_target):
    """The per-trade mean that PF `pf_target` implies, holding the population's OWN win and loss
    MAGNITUDES fixed and moving only the win rate. PF = wW / ((1-w)L)."""
    w = pf_target * mean_loss / (mean_win + pf_target * mean_loss)
    return w * mean_win - (1 - w) * mean_loss, w


rows = []
for arm, _ in X.ARMS:
    for label, sub in (("US100", ["US100"]), ("NQ", ["NQ"]), ("XAU", ["XAU"]),
                       ("US30I", ["US30I"]), ("DEDUP 3", DEDUP), ("ALL 4", NEW)):
        p = pooled(sub, arm, "atr")
        if p is None:
            continue
        need12, w12 = pf_required(p["mean_win"], p["mean_loss"], 1.2)
        need11, w11 = pf_required(p["mean_win"], p["mean_loss"], 1.1)
        need15, _ = pf_required(p["mean_win"], p["mean_loss"], 1.5)
        rows.append(dict(arm=arm, set=label, n=p["n"], n_eff=p["n_eff"], mean=p["mean"],
                         mde80=p["mde80"], ratio=p["mean"] / p["mde80"],
                         need_pf11=need11, need_pf12=need12, need_pf15=need15,
                         n_to_detect=(round((X.Z80 * p["sd"] / abs(p["mean"])) ** 2
                                            * (p["n"] / max(p["n_eff"], 1)))
                                      if p["mean"] != 0 else np.nan)))
M = pd.DataFrame(rows)
print(M.round(4).to_string(index=False))

print("\n    `ratio` is mean / MDE: >= 1.0 is a detectable effect. `n_to_detect` is how many")
print("    trades at the observed dispersion and the observed edge would be needed at 80% power,")
print("    inflated by the clustering factor.")

M.to_csv(f"{C}/x4_mde.csv", index=False)
print(f"\n    wrote {C}/x4_mde.csv")
