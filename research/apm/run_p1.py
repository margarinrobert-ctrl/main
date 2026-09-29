"""P1 -- is the APM session-VWAP rule profitable out of sample, and does it survive walk-forward?

Both questions have already been measured on this branch (STUDY_APM_VWAP, STUDY_APM_WFO). This
re-reads them in DOLLARS, block by block, so the answer is in the same unit as the other two
strategies, and puts the matched control beside every block rather than over all trades -- the
STUDY_TOP5 correction.

Nothing is selected here. The configuration is the author's constants throughout.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/apm")
import numpy as np, pandas as pd
import apm_core as A

R = "results/apm2/"; os.makedirs(R, exist_ok=True)
print(__doc__); t0 = time.time()
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)

MK = [("NQ", "USIndex"), ("US100", "USIndex"), ("US30", "USIndex")]
rows = []
store = {}
for mkt, prof in MK:
    try:
        D = A.load(mkt, 10)
    except Exception as e:
        print(f"  {mkt}: unavailable ({e})")
        continue
    tr, _cnt = A.run(D, profile=prof)
    B = A.blocks(D)
    store[mkt] = (D, tr, B)
    for bl, m in B.items():
        s = A.metrics(tr, D, m)
        if s["n"] == 0:
            continue
        rows.append(dict(market=mkt, block=bl, n=s["n"], pts=s["mean"], usd_trade=s["usd"] / s["n"],
                         usd=s["usd"], pf=s["pf"], win=s["win"], sharpe=s["sharpe"],
                         dd_usd=s["dd"] * D["pv"], ret_dd=s["ret_dd"], top5=s["top5"]))
    print(f"  ...{mkt} done {time.time()-t0:.0f}s")
T = pd.DataFrame(rows)
T.to_csv(R + "p1_blocks.csv", index=False)

print("\n" + "=" * 126)
print("P1.1  EVERY BLOCK, IN DOLLARS -- one contract, costs in, the author's constants")
print("=" * 126)
print("  NQ splits 65/35 by session. US100 and US30 are nine-year CFD feeds and split")
print("  research (<2022) / validation (2022-23) / test (>=2024) -- so their TEST block is the")
print("  cleanest read available on this family.")
print(T.round(4).to_string(index=False))

print("\n" + "=" * 126)
print("P1.2  THE MATCHED CONTROL, INSIDE EACH BLOCK")
print("=" * 126)
print("  A random fill minute in the SAME entry window on the SAME sessions, same side mix,")
print("  same exits. This is the null that asks whether the ENTRY carries anything.")
rows = []
for mkt, (D, tr, B) in store.items():
    for bl, m in B.items():
        s = A.metrics(tr, D, m)
        if s["n"] < 15:
            continue
        res = A.control(D, tr, {}, m, profile="USIndex", draws=600, seed=5, mode="random")
        if res is None:
            continue
        rows.append(dict(market=mkt, block=bl, n=s["n"], rule=res["rule"],
                         ctl_med=res["ctl_median"], excess=res["rule"] - res["ctl_median"],
                         p=res["p"]))
        print(f"  ...{mkt} {bl} done {time.time()-t0:.0f}s")
C = pd.DataFrame(rows)
C.to_csv(R + "p1_controls.csv", index=False)
print(C.round(4).to_string(index=False))
print(f"\ntotal {time.time()-t0:.0f}s")
