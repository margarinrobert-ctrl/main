"""M1 -- GATE 1 on the three equity-index feeds. The rule as published, nothing fitted.

Order is deliberate and is the branch's: the feed and its clock first, then the base rates of the
six conditions ON THE TRIGGER'S OWN BARS, then the arithmetic (cost as a fraction of risk and the
win rate the geometry needs), and only then any P&L -- with the matched control run as a GATE
rather than as a final check.
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vecore as V, ve_markets as M

RNG = np.random.default_rng(11)
MK = ["US100", "US30", "US30_ISO"]
os.makedirs("results/vwapema", exist_ok=True)
pd.set_option("display.width", 220)
L = lambda s: print("\n" + "=" * 108 + f"\n{s}\n" + "=" * 108)

D = {k: M.build(k) for k in MK}

L("M1.1  THE FEEDS -- clock RE-DERIVED, volume column CHECKED, block split stated")
rows = []
for k in MK:
    f = M.raw(k)
    mo, pk, mn = M.clock_evidence(f)
    cv, mv, zv = M.volume_check(f)
    rows.append(dict(feed=k, bars=len(f), first=str(f.index[0].date()), last=str(f.index[-1].date()),
                     peak_mod=mo, peak_rng=round(pk, 2), mean_rng=round(mn, 2),
                     corr_v_range=round(cv, 3), med_vol=mv, zero_vol=round(100 * zv, 2),
                     cut=D[k]["cut_date"]))
print(pd.DataFrame(rows).to_string(index=False))
print("\nminute-of-day 570 = 09:30 New York. All three peak there, so the registry clocks hold.")
print("corr(volume, bar range) 0.71-0.77 = a real activity column (XAUUSD15_MT's fake one is +0.005).")
print("US30_ISO is NOT split for selection -- it is the reserved forward block; its `cut` is shown")
print("only so the table is readable, and nothing below searches it.")

L("M1.2  COST AS A FRACTION OF RISK, and the win rate each geometry needs")
rows = []
for k in MK:
    sig, _ = V.triggers(D[k], 1)
    t = M.run(D[k], sig, side=1)
    med = float(t.risk.median())
    rt = D[k]["cost_rt"] + 2 * D[k]["slip"]
    px = float(D[k]["c"][D[k]["rth"]].mean())
    for tg in (1.0, 2.0, 3.0, 5.0):
        c = rt / med
        rows.append(dict(feed=k, med_risk_pts=round(med, 2), med_risk_pct=round(100 * med / px, 3),
                         round_turn=round(rt, 2), cost_in_R=round(c, 4), target_R=tg,
                         breakeven_win=round(100 * (1 + c) / (tg + 1), 2)))
B = pd.DataFrame(rows)
print(B.to_string(index=False))
print("\nGold's floor for comparison: round turn 0.40 USD/oz on a 2.35 median risk = 0.17 R.")
B.to_csv("results/vwapema/m1_cost.csv", index=False)

L("M1.3  BASE RATES ON THE TRIGGER'S OWN BARS -- before any P&L")
rows = []
for k in MK:
    d = D[k]
    for side, nm in ((1, "LONG"), (-1, "SHORT")):
        sig, P = V.triggers(d, side)
        rth = d["rth"]
        keys = ["C1", "C2", "C3", "C4", "C5", "C6", "ambig"]
        base = {q: np.nan_to_num(P[q], nan=False).astype(bool) for q in keys}
        for q in keys:
            others = rth.copy()
            for r2 in keys:
                if r2 != q:
                    others &= base[r2]
            rows.append(dict(feed=k, side=nm, cond=q,
                             pass_all_rth=round(100 * base[q][rth].mean(), 2),
                             pass_given_others=round(100 * base[q][others].mean(), 2),
                             n_others=int(others.sum()), n_sig=int(sig.sum())))
R = pd.DataFrame(rows)
print(R.pivot_table(index=["feed", "cond"], columns="side",
                    values=["pass_all_rth", "pass_given_others"]).round(2).to_string())
R.to_csv("results/vwapema/m1_baserates.csv", index=False)
print("\n`pass_given_others` is the one that matters: a condition passing ~100% of the bars the")
print("other five already admit is the trigger restated and cannot add anything (the branch has")
print("now measured that for RSI, Aroon, MACD, MFI, EMA13>48 and the stochastic).")

L("M1.4  THE PUBLISHED RULE, both sides, both blocks, per feed")
rows = []
for k in MK:
    for side, nm in ((1, "LONG"), (-1, "SHORT")):
        sig, _ = V.triggers(D[k], side)
        t = M.run(D[k], sig, side=side)
        for b, bn in ((0, "research"), (1, "LOCKED")):
            st = V.stats(t[t.blk == b])
            st.update(feed=k, side=nm, block=bn)
            rows.append(st)
T = pd.DataFrame(rows)[["feed", "side", "block", "n", "R", "pct", "pf", "win", "totR", "dd", "ret_dd"]]
print(T.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
T.to_csv("results/vwapema/m1_published.csv", index=False)
print("\nR and percent-of-price disagree in sign on several rows. R divides by a risk that varies")
print("with ATR; percent of price does not. Both are reported and percent is the safe one.")

L("M1.5  THE MATCHED CONTROL, run as a gate -- random New York bars, identical geometry")
rows = []
for k in MK:
    d = D[k]
    for side, nm in ((1, "LONG"), (-1, "SHORT")):
        sig, _ = V.triggers(d, side)
        t = M.run(d, sig, side=side)
        idx = np.flatnonzero(d["rth"])
        for b, bn in ((0, "research"), (1, "LOCKED")):
            obs = V.stats(t[t.blk == b])
            if obs["n"] < 20:
                continue
            rate = min(1.0, obs["n"] / max(int((d["rth"] & (d["blk"] == b)).sum()), 1))
            out = []
            for _ in range(300):
                g = np.zeros(d["n"], bool)
                g[idx[RNG.random(len(idx)) < rate]] = True
                c = M.run(d, g, side=side)
                c = c[c.blk == b]
                if len(c) >= 20:
                    out.append((c.R.mean(), c.pct.mean()))
            a = np.array(out)
            rows.append(dict(feed=k, side=nm, block=bn, n=obs["n"], R=obs["R"], pct=obs["pct"],
                             ctl_R=float(np.median(a[:, 0])), p_R=float((a[:, 0] >= obs["R"]).mean()),
                             ctl_pct=float(np.median(a[:, 1])),
                             p_pct=float((a[:, 1] >= obs["pct"]).mean())))
C = pd.DataFrame(rows)
print(C.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
C.to_csv("results/vwapema/m1_control.csv", index=False)
print("\nA control that itself LOSES money makes 'clears its control' a weak statement -- read the")
print("ctl_ column's level, not only the p-value (STUDY_IB_US30_OPTUNA).")

L("M1.6  ARMS -- is it cost, is it the exit machine, is it drift?")
rows = []
for k in MK:
    for side, nm in ((1, "LONG"), (-1, "SHORT")):
        sig, _ = V.triggers(D[k], side)
        sigu, _ = V.triggers(D[k], side, use_vwap_vol=False)
        for arm, s2, kw in (("as specified", sig, {}),
                            ("ZERO COST", sig, dict(cost_rt=0.0, slip=0.0)),
                            ("no 3R target", sig, dict(tgt_R=99.0)),
                            ("no EMA20 tightening", sig, dict(tighten=False)),
                            ("flatten at close", sig, dict(flatten=True)),
                            ("volume-free VWAP", sigu, {})):
            t = M.run(D[k], s2, side=side, **kw)
            for b, bn in ((0, "research"), (1, "LOCKED")):
                st = V.stats(t[t.blk == b])
                rows.append(dict(feed=k, side=nm, arm=arm, block=bn, n=st["n"],
                                 R=round(st["R"], 4), pct=round(st["pct"], 4), pf=round(st["pf"], 3)))
A = pd.DataFrame(rows)
print(A.pivot_table(index=["feed", "side", "arm"], columns="block", values=["R", "pf", "n"],
                    sort=False).round(4).to_string())
A.to_csv("results/vwapema/m1_arms.csv", index=False)
print("\nRun the ZERO-COST variant before concluding anything about execution (CLAUDE.md).")
