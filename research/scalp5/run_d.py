"""D -- the book variants, the walk-forward, and what it would actually take.

C left three facts to resolve. Two of the five LOSE on the research block (S2 -1.25 Sharpe, S5
-0.57), so an all-five book is carrying dead weight. The book reads Sharpe -0.46 on research and
+1.16 on locked, which is the WRONG SHAPE -- a rule chosen on research should look better there,
and this branch has recorded that defect thirteen times. And no leg clears its matched control.

Three declared book variants, and the selection rule for each is stated BEFORE it is scored:
  ALL FIVE          no selection at all
  RESEARCH-POSITIVE the legs with positive research Sharpe, chosen on research only
  BEST LEG          S3 alone, for the comparison a book has to beat to be worth building

Then a walk-forward with the leg selection RE-RUN inside every training window and a RANDOM leg
subset beside it, because without one "the book won" is unfalsifiable. And finally the arithmetic:
the win rate each design would need to reach a given profit factor, against what it delivers.
"""
import sys, os, time, itertools
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5")
import numpy as np, pandas as pd
import s5data as S, s5sig as SG, s5walk as W

R = "results/scalp5/"
os.makedirs(R, exist_ok=True)
print(__doc__)
t0 = time.time()
RNG = np.random.default_rng(29)
GEOM = dict(stop=3.0, tgt=0.0, be=1.0, be_off=0.25, arm=1.0, tr=1.0)
base = S.load_1m()
TF = 5
D = S.assemble(S.resample(base, TF), TF)
F = SG.build(D, base)
DAYS = {0: D["all_days"][D["all_days"] < D["cut_day"]], 1: D["all_days"][D["all_days"] >= D["cut_day"]]}


def walk(lg, sh, g=GEOM):
    sig = lg | sh
    side = np.where(lg, 1, np.where(sh, -1, 0)).astype(np.int64)
    cap = int(sig.sum()) + 4
    a = [np.zeros(cap, np.int64), np.zeros(cap, np.int64)]
    b = [np.full(cap, np.nan) for _ in range(4)]
    w = np.zeros(cap, np.int64); am = np.zeros(cap, np.int64)
    k = W.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], sig, side, D["last_win"],
               S.RT_POINTS, S.SLIP_POINTS, g["stop"], g["tgt"], g["be"], g["be_off"],
               g["arm"], g["tr"], a[0], a[1], b[0], b[1], w, b[2], b[3], am)
    t = pd.DataFrame(dict(sig=a[0][:k], R=b[0][:k], pts=b[1][:k], why=w[:k]))
    t["day"] = D["day"][t.sig.to_numpy()]
    return t


LEGS = {}
for nm, (fn, p) in SG.DESIGNS.items():
    lg, sh = fn(D, F, p)
    LEGS[nm] = walk(lg, sh)


def daily(nm, days):
    t = LEGS[nm]
    s = t[np.isin(t.day.to_numpy(), days)]
    ser = pd.Series(s.pts.to_numpy()).groupby(pd.Series(s.day.to_numpy())).sum()
    full = pd.Series(0.0, index=pd.Index(days)); full.loc[ser.index] = ser.to_numpy()
    return full


def book_stats(names, days):
    P = pd.DataFrame({n: daily(n, days) for n in names})
    tot = P.sum(axis=1)
    eq = tot.cumsum().to_numpy()
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    sd = tot.std(ddof=1)
    ntr = sum(int(np.isin(LEGS[n].day.to_numpy(), days).sum()) for n in names)
    return dict(legs=len(names), trades=ntr, per_yr=ntr / (len(days) / 252),
                pts_per_day=float(tot.mean()),
                sharpe=float(tot.mean() / sd * np.sqrt(252)) if sd > 0 else np.nan,
                pf=float(tot[tot > 0].sum() / max(-tot[tot < 0].sum(), 1e-9)),
                dd=dd, ret_dd=float(tot.sum() / max(dd, 1e-9)),
                total=float(tot.sum()))


res_sh = {n: book_stats([n], DAYS[0])["sharpe"] for n in LEGS}
POS = [n for n in LEGS if res_sh[n] > 0]
BEST = [max(res_sh, key=res_sh.get)]
VARIANTS = {"ALL FIVE": list(LEGS), "RESEARCH-POSITIVE": POS, "BEST LEG ALONE": BEST}
print("=" * 112)
print("D.1  THREE DECLARED BOOKS -- the selection rule for each was written before it was scored")
print("=" * 112)
print(f"  research Sharpe by leg: " + "  ".join(f"{n.split()[0]} {v:+.2f}" for n, v in res_sh.items()))
print(f"  RESEARCH-POSITIVE resolves to {POS}")
rows = []
for lab, names in VARIANTS.items():
    for b, bl in ((0, "research"), (1, "LOCKED")):
        rows.append(dict(book=lab, block=bl, **book_stats(names, DAYS[b])))
BK = pd.DataFrame(rows)
BK.to_csv(R + "d_books.csv", index=False)
pd.set_option("display.width", 220)
print(BK.round(4).to_string(index=False))
print("\n  A book is only worth building if it beats its own BEST LEG. Compare the two rows.")

# ---------------------------------------------------------------- walk-forward
print("\n" + "=" * 112)
print("D.2  WALK-FORWARD with the LEG SELECTION re-run inside every training window")
print("=" * 112)
print("  Expanding train / 3-month test. Arms: re-chosen (positive-Sharpe legs in the training")
print("  window), a RANDOM subset of the same size, all five fixed, and the best research leg fixed.")
ud = np.sort(D["all_days"])
qs = pd.Series(pd.to_datetime(ud, unit="D")).dt.to_period("Q")
folds = sorted(qs.unique())[4:]
rows = []
for q in folds:
    te = ud[(qs == q).to_numpy()]
    tr = ud[(qs < q).to_numpy()]
    if len(te) < 20 or len(tr) < 120:
        continue
    sh_tr = {n: book_stats([n], tr)["sharpe"] for n in LEGS}
    chosen = [n for n in LEGS if sh_tr[n] > 0] or [max(sh_tr, key=sh_tr.get)]
    rnd = list(RNG.choice(list(LEGS), size=len(chosen), replace=False))
    rows.append(dict(fold=str(q), n_test=len(te), n_chosen=len(chosen),
                     re_chosen=book_stats(chosen, te)["pts_per_day"],
                     random_subset=book_stats(rnd, te)["pts_per_day"],
                     all_five=book_stats(list(LEGS), te)["pts_per_day"],
                     best_fixed=book_stats(BEST, te)["pts_per_day"]))
WF = pd.DataFrame(rows)
WF.to_csv(R + "d_wf.csv", index=False)
print(WF.round(3).to_string(index=False))
print("\n  mean points per day across folds:")
for c in ("re_chosen", "random_subset", "all_five", "best_fixed"):
    print(f"    {c:16s} {WF[c].mean():+8.3f}   folds positive {int((WF[c]>0).sum())}/{len(WF)}")

# ---------------------------------------------------------------- what it would take
print("\n" + "=" * 112)
print("D.3  WHAT IT WOULD TAKE -- the win rate each profit factor demands, against what is delivered")
print("=" * 112)
a = float(np.nanmedian(D["atr"][D["inw"]]))
print(f"  median in-window ATR {a:.2f} pts; all-in round turn {S.RT_POINTS:.2f} pts")
rows = []
for stop_n in (1.0, 1.5, 3.0):
    Sd = stop_n * a
    for pf in (1.5, 2.0):
        for rr in (1.0, 2.0):
            # w such that PF = w*rr*S / ((1-w)*S) after cost on both sides
            need = (pf * (Sd + S.RT_POINTS)) / (rr * Sd - S.RT_POINTS + pf * (Sd + S.RT_POINTS))
            rows.append(dict(stop_atr=stop_n, target_R=rr, want_pf=pf, need_win=need,
                             driftless=1 / (1 + rr), lift_needed=need - 1 / (1 + rr)))
NT = pd.DataFrame(rows)
NT.to_csv(R + "d_need.csv", index=False)
print(NT.round(4).to_string(index=False))
print("\n  Measured win rates at the shipped geometry, research block:")
for n in LEGS:
    t = LEGS[n]; s = t[np.isin(t.day.to_numpy(), DAYS[0])]
    if len(s) > 25:
        print(f"    {n:20s} {float((s.R>0).mean()):.1%} on {len(s)} trades")
print(f"\ntotal {time.time()-t0:.0f}s")
