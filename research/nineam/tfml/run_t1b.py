"""T1b  The 30s primary at the reading TradingView ACTUALLY runs. The shipped Pine clamps
`tfMin = max(1, seconds/60)`, so on a 30s chart `crossBars` = 7 BARS = 3.5 minutes, not the 14 bars
(7 minutes) `na_live.TV` models; reconciled against the user's TradingView export that reading
matches 86.0% of entries against 70.4% for the 14-bar one. One extra Gate-1 row, nothing else."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import tfcore as C  # noqa: E402
import numpy as np, pandas as pd  # noqa: E402
import run_t1 as R1  # noqa: E402  (re-runs T1's table on import; cheap)
P2 = dict(C.P, cross_min=3.5)
c = C.ctx(0.5)
R1.P = P2
rows = []
for blk, dd in (("ALL", R1.DAYS), ("research", R1.IS_D), ("holdout", R1.OOS_D)):
    sig, sd = c.sigs(P2); m = np.isin(c.day[sig], dd)
    t = c._walk_sig(P2, c.atr_frame(14), sig[m], sd[m]); r = t["pct"].to_numpy()
    nul = R1.control(c, sig[m], sd[m], 400, seed=77 + len(blk)); v = nul[np.isfinite(nul)]
    bo = C.N.boot_edge(t.assign(_day=t["eday"]), 4000, 7, col="pct")
    mde = C.N.mde(r.std(ddof=1), len(r))
    rows.append(dict(tf=0.5, reading="7-bar (TradingView)", block=blk, n=len(r), pct=r.mean(), pf=C.pf(r),
                     win=(r > 0).mean(), hit=(t["why"] == 2).mean(), null_med=np.median(v),
                     p_entry=float((v >= r.mean()).mean()), mde=mde, per_mde=r.mean() / mde,
                     boot_p=float((bo <= 0).mean())))
G = pd.DataFrame(rows); print(G.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
G.to_csv(os.path.join(HERE, "t1b_gate1_7bar.csv"), index=False)
