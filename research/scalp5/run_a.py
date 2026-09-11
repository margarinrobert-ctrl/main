"""A -- the five designs as specified, on 3m and 5m, research block only.

Nothing is tuned here. Each design is run at the geometry the arithmetic admits (a 1.5xATR stop
is where the round turn falls to 7.6% of risk on 5-minute NQ) and the question is only whether it
has a pulse and whether the five are actually different from each other.

Scored the way the ask names: EV per trade AND Sharpe over EVERY trading day in the block,
zero-filled on days that did not trade -- over traded days only, a selective rule is PAID for
trading less.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5")
import numpy as np, pandas as pd
import s5data as S, s5sig as SG, s5walk as W

R = "results/scalp5/"
os.makedirs(R, exist_ok=True)
print(__doc__)
t0 = time.time()
base = S.load_1m()


def run_one(D, lg, sh, stop_n=1.5, tgt_n=1.0, be_at=0.0, be_off=0.0, tr_arm=0.0, tr_dist=0.0):
    sig = lg | sh
    side = np.where(lg, 1, np.where(sh, -1, 0)).astype(np.int64)
    cap = int(sig.sum()) + 4
    oi = np.zeros(cap, np.int64); ox = np.zeros(cap, np.int64)
    oR = np.full(cap, np.nan); op = np.full(cap, np.nan)
    ow = np.zeros(cap, np.int64); oa = np.full(cap, np.nan)
    of = np.full(cap, np.nan); ob = np.zeros(cap, np.int64)
    k = W.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], sig, side, D["last_win"],
               S.RT_POINTS, S.SLIP_POINTS, stop_n, tgt_n, be_at, be_off, tr_arm, tr_dist,
               oi, ox, oR, op, ow, oa, of, ob)
    t = pd.DataFrame(dict(sig=oi[:k], exit=ox[:k], R=oR[:k], pts=op[:k], why=ow[:k],
                          mae=oa[:k], mfe=of[:k], amb=ob[:k]))
    t["side"] = side[t.sig.to_numpy()]
    t["blk"] = D["blk"][t.sig.to_numpy()]
    t["day"] = D["day"][t.sig.to_numpy()]
    t["mod"] = D["mod"][t.sig.to_numpy()]
    return t


rows, store = [], {}
for tf in (3, 5):
    f = S.resample(base, tf)
    D = S.assemble(f, tf)
    F = SG.build(D, base)
    for nm, (fn, p) in SG.DESIGNS.items():
        lg, sh = fn(D, F, p)
        t = run_one(D, lg, sh)
        store[(tf, nm)] = (D, F, lg, sh, t)
        for b, lab in ((0, "research"), (1, "LOCKED")):
            s = t[t.blk == b]
            days = D["all_days"][(D["all_days"] >= D["cut_day"]) if b else (D["all_days"] < D["cut_day"])]
            if len(s) < 25:
                rows.append(dict(tf=tf, design=nm, block=lab, n=len(s)))
                continue
            r = s.R.to_numpy(); pts = s.pts.to_numpy()
            sh_, _ = S.day_sharpe(s.day.to_numpy(), pts, days)
            neg = r[r < 0]; pos = r[r > 0]
            rows.append(dict(tf=tf, design=nm, block=lab, n=len(s),
                             per_yr=len(s) / max(len(days) / 252, 1e-9),
                             R=r.mean(), pts=pts.mean(),
                             pf=pos.sum() / max(-neg.sum(), 1e-9),
                             win=(r > 0).mean(), sharpe=sh_,
                             hold_min=(s.exit - s.sig).mean() * tf,
                             p_stop=(s.why == 1).mean(), p_tgt=(s.why == 2).mean(),
                             p_flat=(s.why == 3).mean(), amb=(s.amb > 0).mean()))
A = pd.DataFrame(rows)
A.to_csv(R + "a_designs.csv", index=False)
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
print("=" * 112)
print("A.1  THE FIVE AS SPECIFIED -- 1.5xATR stop, 1:1 target, flat at 11:00, one position at a time")
print("=" * 112)
print(A[A.block == "research"].round(4).to_string(index=False))

print("\n" + "=" * 112)
print("A.2  ARE THEY ACTUALLY DIFFERENT? daily P&L correlation, research block, 5m")
print("=" * 112)
day_pnl = {}
for nm in SG.DESIGNS:
    D, F, lg, sh, t = store[(5, nm)]
    s = t[t.blk == 0]
    day_pnl[nm] = pd.Series(s.pts.to_numpy()).groupby(pd.Series(s.day.to_numpy())).sum()
P = pd.DataFrame(day_pnl).reindex(D["all_days"][D["all_days"] < D["cut_day"]]).fillna(0.0)
C = P.corr()
C.to_csv(R + "a_corr.csv")
print(C.round(3).to_string())
off = C.to_numpy()[np.triu_indices(len(C), 1)]
print(f"\n  mean |pairwise correlation| {np.abs(off).mean():.3f}   max {np.abs(off).max():.3f}")
print("  (this branch's eight-breakout programme scored 0.87-0.96 here -- one strategy, eight names)")
print(f"\ntotal {time.time()-t0:.0f}s")
