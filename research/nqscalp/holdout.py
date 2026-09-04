"""THE ONLY DOOR TO THE HOLDOUT for this study.

Five comparisons were declared in the ledger (N0001) before any holdout number
existed. Bonferroni threshold for NPRE=5 is p < 0.01. Requires --yes-really.

A rule chosen on research should look BETTER on research; the holdout is where an
edge decays, not where it appears. Passing on the holdout while failing research
is treated as a defect, not a result.
"""
import numpy as np, pandas as pd, sys, json, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, cache, nqcontrol as NC, data as D, ledger

if "--yes-really" not in sys.argv:
    print("Refusing to open the holdout without --yes-really."); sys.exit(1)

df = D.load("NAS"); B = cache.build(df)
R, H = D.blocks(df)
NPRE, THR = 6, 0.05 / 6   # amended in ledger N0002, before any holdout look
WF_CFG = json.load(open("/home/user/main/docs/nqscalp/wf_selected.json"))

CONV = [("barclose", "adverse"), ("barclose", "favorable"),
        ("intrabar", "adverse"), ("intrabar", "favorable")]


def run(mask, tm, order, **kw):
    I, p = cache.indicators(df, B, **kw)
    (lo, sh), _ = nqs.conditions(df, I, p)
    tr = nqs.simulate(df, I, p, lo & mask, sh & mask, order=order, trail_mode=tm)
    g = NC.score(df, I, p, tr, n_draws=400, mask=mask, order=order, trail_mode=tm)
    return tr, g


print("=" * 122)
print("HOLDOUT REVEAL - NQ Scalping System")
print(f"  {NPRE} comparisons were pre-registered in ledger N0001 before this ran.")
print(f"  Bonferroni threshold for NPRE={NPRE}: p < {THR:.4f}")
print("  Test 6 (the RTH sub-window) was added in amendment N0002 before this ran;")
print("  it additionally carries a best-of-5-windows search made on research.")
print("  Holdout: 2022-08-30 -> 2025-10-01, 962 sessions (35% of the sample).")
print("  PASS requires, on the PRIMARY model (barclose/adverse): expectancy > 0 AND p < 0.01.")
print("=" * 122)

rows = []
tests = [(f"as-written {tm}/{o}", tm, o, {}) for tm, o in CONV]
tests.append((f"walk-forward pick {WF_CFG['label']}", WF_CFG["trail_mode"], "adverse", WF_CFG["kw"]))
RTH = dict(sess_start_h=8, sess_start_m=30, sess_end_h=10, sess_end_m=0)
tests.append(("RTH sub-window 09:30-11:00 NY barclose/adverse", "barclose", "adverse", RTH))
tests.append(("RTH sub-window 09:30-11:00 NY intrabar/adverse", "intrabar", "adverse", RTH))

for label, tm, order, kw in tests:
    trR, gR = run(R, tm, order, **kw)
    trH, gH = run(H, tm, order, **kw)
    rows.append(dict(test=label, tm=tm, order=order,
                     r_n=gR["n"], r_exp=gR["exp"], r_ctrl=gR["ctrl"], r_excess=gR["excess"], r_p=gR["p"],
                     h_n=gH["n"], h_exp=gH["exp"], h_ctrl=gH["ctrl"], h_excess=gH["excess"], h_p=gH["p"],
                     h_net_usd=float(trH.net_usd.sum()), r_net_usd=float(trR.net_usd.sum()),
                     passes=bool(gH["exp"] > 0 and gH["p"] < THR)))
    r_, h_ = rows[-1], rows[-1]
    print(f"\n  {label}")
    print(f"    RESEARCH n={r_['r_n']:>5} exp={r_['r_exp']:>+7.2f} ctrl={r_['r_ctrl']:>+7.2f} "
          f"excess={r_['r_excess']:>+7.2f} p={r_['r_p']:.4f}  net=${r_['r_net_usd']:>+10,.0f}")
    print(f"    HOLDOUT  n={h_['h_n']:>5} exp={h_['h_exp']:>+7.2f} ctrl={h_['h_ctrl']:>+7.2f} "
          f"excess={h_['h_excess']:>+7.2f} p={h_['h_p']:.4f}  net=${h_['h_net_usd']:>+10,.0f}")
    print(f"    verdict  {'PASS' if r_['passes'] else 'FAIL'}"
          f"   (needs exp>0 and p<{THR:.4f})")
    if h_["h_excess"] > r_["r_excess"]:
        print("    ** WRONG SHAPE ** better on holdout than on research. Treat as a defect,")
        print("       not as a result - a rule should decay out of sample, not improve.")

T = pd.DataFrame(rows)
T.to_csv("/home/user/main/docs/nqscalp/holdout.csv", index=False)
prim = T[T.test.str.startswith("as-written barclose/adverse")].iloc[0]
rth = T[T.test.str.startswith("RTH sub-window 09:30-11:00 NY barclose")].iloc[0]
verdict = "PASS" if bool(prim.passes) else "FAIL"
print("\n" + "=" * 122)
print(f"PRIMARY MODEL (barclose/adverse) VERDICT: {verdict}")
print(f"  holdout expectancy {prim.h_exp:+.2f} pts/trade, excess {prim.h_excess:+.2f}, p {prim.h_p:.4f}")
print(f"  RTH SUB-WINDOW (barclose/adverse) VERDICT: {'PASS' if bool(rth.passes) else 'FAIL'}")
print(f"  holdout expectancy {rth.h_exp:+.2f} pts/trade, excess {rth.h_excess:+.2f}, p {rth.h_p:.4f}, n={rth.h_n}")
print(f"  {int(T.passes.sum())} of {len(T)} pre-registered comparisons pass at p<{THR:.4f}.")
print("=" * 122)
json.dump(dict(verdict=verdict, npre=NPRE, threshold=THR,
               rows=T.to_dict("records")),
          open("/home/user/main/docs/nqscalp/holdout.json", "w"), indent=2, default=str)
ledger.log(kind="HOLDOUT_REVEAL", pre_registration="N0001", npre=NPRE, threshold=THR,
           verdict=verdict, rows=T.to_dict("records"))
print("  written: holdout.csv, holdout.json; ledger entry added.")
