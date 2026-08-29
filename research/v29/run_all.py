"""One runner. Imports the pieces and calls only what is asked for."""
from __future__ import annotations
import sys, numpy as np, pandas as pd
sys.path.insert(0, "research"); sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v21"); sys.path.insert(0, "research/v24")
sys.path.insert(0, "research/v27"); sys.path.insert(0, "research/v28")
sys.path.insert(0, "research/v29")
import v21regime as RG, v24ma as V, v28data as D, v29chop as Q          # noqa: E402
from v28ml import run_model                                             # noqa: E402
from sklearn.preprocessing import StandardScaler                        # noqa: E402

if __name__ == "__main__":
    V.hdr("A. IS THE US30 ML RESULT JUST CHOP? -- one line against 141 features")
    print("   All four models passed the gate at the same excess regardless of AUC, which is the")
    print("   signature of every model rediscovering ONE thing. CHOP is the candidate: 74 of the")
    print("   141 columns are volatility or regime readings.\n")
    for mkt in ("US30", "NQ"):
        X, yR, yw, meta = D.build(mkt, 30, 1)
        u = np.unique(meta["sess"]); cut = u[int(len(u) * 0.65)]
        res, lk = meta["sess"] < cut, meta["sess"] >= cut
        Xv = X.to_numpy(float); chop = X["reg.chop14"].to_numpy()
        rl, cl = yR[lk], chop[lk]
        rng = np.random.default_rng(41); k = int(lk.sum()) // 2
        ctrl = np.array([rl[rng.choice(len(rl), k, replace=False)].mean() for _ in range(400)])
        chop_sel = cl <= np.median(cl)
        print(f"   {mkt}: {int(lk.sum())} locked signals, baseline {rl.mean():+.4f} R,"
              f" control mean {ctrl.mean():+.4f}")
        print(f"   {'selector':<28}{'n':>6}{'R':>10}{'excess':>9}{'p':>7}{'Jaccard w/ CHOP':>18}")
        r = float(rl[chop_sel].mean())
        print(f"   {'CHOP14 <= median (1 line)':<28}{int(chop_sel.sum()):>6}{r:>+10.4f}"
              f"{r-ctrl.mean():>+9.4f}{float((ctrl>=r).mean()):>7.3f}{1.0:>18.3f}")
        for name, spec in (("XGBoost 300 d3", ("xgb", 300, 3, 0.05)),
                           ("LightGBM 400", "lgbm"), ("random forest 300", "rf")):
            sc = StandardScaler().fit(Xv[res])
            p = run_model(spec, sc.transform(Xv[res]), yw[res], sc.transform(Xv[lk]))
            sel = p >= np.median(p); r = float(rl[sel].mean())
            jac = (sel & chop_sel).sum() / max((sel | chop_sel).sum(), 1)
            print(f"   {name:<28}{int(sel.sum()):>6}{r:>+10.4f}{r-ctrl.mean():>+9.4f}"
                  f"{float((ctrl>=r).mean()):>7.3f}{jac:>18.3f}")
        print()

    V.hdr("B. CAN A MODEL PREDICT FORWARD CHOP BETTER THAN READING CHOP NOW?")
    print("   Label = forward efficiency ratio over the next h bars (1.0 straight, ~0 chop).")
    print("   `naive` is just -CHOP(14) today. XGBoost gets 74 volatility features and ADX too.\n")
    print(f"   {'market':<8}{'h':>4}{'n':>8}{'IC model (res)':>16}{'IC model (LOCKED)':>19}"
          f"{'IC naive (LOCKED)':>19}{'AUC model':>11}{'AUC naive':>11}")
    rows = []
    for mkt in ("NQ", "US30"):
        for h in (12, 24, 48):
            r = Q.part1_predict_chop(mkt, 30, h)
            rows.append(r)
            print(f"   {mkt:<8}{h:>4}{r['n']:>8}{r['ic_model_res']:>+16.4f}{r['ic_model']:>+19.4f}"
                  f"{r['ic_naive']:>+19.4f}{r['auc_model']:>11.4f}{r['auc_naive']:>11.4f}")
    pd.DataFrame(rows).to_csv("results/v29/v29_chop_pred.csv", index=False)
