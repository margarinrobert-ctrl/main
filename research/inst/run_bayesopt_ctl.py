"""Random-entry controls for the Bayesian-optimisation finalists: the same stop, target, channel
exit, hold and position lock, entered at random RTH bars at the rule's own rate. A wide-stop,
long-hold, no-filter breakout in a market that rose 89% is a drift harvester until this says
otherwise (STUDY_TURTLE, STUDY_V46)."""
import os, sys, warnings
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, v64opt as O
warnings.filterwarnings("ignore")
D = O.build(15); n = D["n"]; CUT = D["cut"]; RTH = (D["mod"] >= 570) & (D["mod"] < 930)
rng = np.random.default_rng(21)
FIN = {"cell":     dict(sess=1, ent=55, exN=30, stop=1.5, use_tp=0, tp=0.0, hold=480, adapt=1, use_ma=1, ma_thr=2.0, use_chop=1, chop_thr=40.0, psh=0),
       "TPE total": dict(sess=1, ent=11, exN=47, stop=3.80, use_tp=1, tp=3.2, hold=103, adapt=0, use_ma=0, ma_thr=0, use_chop=0, chop_thr=99, psh=0),
       "GP total":  dict(sess=1, ent=10, exN=80, stop=4.00, use_tp=1, tp=10.0, hold=960, adapt=0, use_ma=0, ma_thr=0, use_chop=0, chop_thr=99, psh=0),
       "TPE pf100": dict(sess=1, ent=56, exN=25, stop=0.61, use_tp=0, tp=0.0, hold=907, adapt=0, use_ma=1, ma_thr=1.35, use_chop=1, chop_thr=43.6, psh=1)}
def walk(p, gate):
    ei = int(p["ent"]) - O.CH_MIN; xi = int(p["exN"]) - O.CH_MIN; stop = float(p["stop"]); tp = float(p["tp"]) if p["use_tp"] else 0.0
    return O._walk(D["o"], D["h"], D["l"], D["c"], D["atr"], D["calm"], D["ent_all"][ei], D["exl_all"][xi], gate, D["d_ma"], D["chop"], D["psh_ok"], int(CUT),
                   stop, stop - 1.0 if p["adapt"] else stop, tp, int(p["hold"]), 1 if p["use_ma"] else 0, float(p["ma_thr"]), 1 if p["use_chop"] else 0, float(p["chop_thr"]),
                   1 if p["psh"] else 0, V.COST, V.SLIP, int(D["last_bar"]))
def at(p, bars):
    xi = int(p["exN"]) - O.CH_MIN; stop = float(p["stop"]); tp = float(p["tp"]) if p["use_tp"] else 0.0
    return O._walk_at(D["o"], D["h"], D["l"], D["c"], D["atr"], D["calm"], D["exl_all"][xi], np.asarray(bars, np.int64), stop, stop - 1.0 if p["adapt"] else stop, tp, int(p["hold"]), V.COST, V.SLIP, int(D["last_bar"]))
def pf(q): return q[q > 0].sum() / max(1e-9, -q[q <= 0].sum())
print(f"  {'finalist':10s} {'block':8s} {'rule n':>6} {'rule PF':>8} {'rule total':>11} | {'random entry PF (median)':>25} {'total':>8} {'p(PF)':>6} {'p(total)':>8}")
for nm, p in FIN.items():
    R, pct, blk, sig = walk(p, RTH)
    for b, bn in ((0, "research"), (1, "locked")):
        q = pct[blk == b]; n_t = len(q)
        elig = np.flatnonzero(RTH & (np.arange(n) >= 1000) & (np.arange(n) < D["last_bar"]) & ((np.arange(n) < CUT) if b == 0 else (np.arange(n) >= CUT)))
        # a random entry per ELIGIBLE bar at the rule's own rate; the lock is inside _walk_at
        rate = n_t / len(elig) * 1.6      # oversample: the lock will reject some; the count is checked below
        cp, ct = [], []
        for _ in range(200):
            bars = np.sort(elig[rng.random(len(elig)) < rate])
            r = at(p, bars); r = r[np.isfinite(r)]
            if len(r) > n_t: r = r[:n_t]
            cp.append(pf(r)); ct.append(r.sum())
        cp, ct = np.array(cp), np.array(ct)
        print(f"  {nm:10s} {bn:8s} {n_t:>6} {pf(q):>8.3f} {q.sum():>+10.2f}% | {np.median(cp):>25.3f} {np.median(ct):>+7.2f}% {np.mean(cp >= pf(q)):>6.3f} {np.mean(ct >= q.sum()):>8.3f}")
