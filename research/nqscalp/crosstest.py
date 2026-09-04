"""Stage 1: does the signal exist on a SECOND instrument?

US30 is independent evidence and costs nothing from the NAS holdout budget, which
has been spent three times. If the EMA-pullback + StochRSI entry carries real
information it should show up here too. If it does not, no amount of further
tuning on NAS is going to mean anything.

Gate applied throughout this round, declared before running:
  G1 net expectancy > 0 after costs, on research
  G2 excess over the matched control at p < 0.05, on research
  G3 still above the round turn with 2020 and 2022 removed
  G4 walk-forward inside research passes
  G5 replicates on the second instrument
Only something passing all five earns the last NAS holdout look.
"""
import numpy as np, pandas as pd, sys, json, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, nqcontrol as NC, data as D

OUT = "/home/user/main/docs/nqscalp/"
TM, ORD = "barclose", "adverse"
# YM (full-size Dow) is $5/point, 1-point tick. MYM is $0.50/point.
SPEC = {"NAS":  dict(point_value=20.0, tick=0.25, commission=1.24, qty=1),
        "US30": dict(point_value=5.0,  tick=1.00, commission=1.24, qty=1)}
CFG_ASWRITTEN = dict(sess_start_h=6, sess_start_m=0, sess_end_h=11, sess_end_m=30)
CFG_FIXED = dict(dist_units="atr", pullback_atr=1.15, trail_arm_atr=1.0,
                 trail_offset_atr=0.5, sess_start_h=6, sess_start_m=0,
                 sess_end_h=11, sess_end_m=30)
CFG_RTH = dict(dist_units="atr", pullback_atr=1.15, trail_arm_atr=1.0,
               trail_offset_atr=0.5, sess_start_h=8, sess_start_m=30,
               sess_end_h=10, sess_end_m=0)

_C = {}
def bars(sym):
    if sym not in _C:
        df = D.load(sym); r, h = D.blocks(df)
        _C[sym] = (df, r, h)
    return _C[sym]


def evaluate(sym, label, cfg, n_draws=300):
    df, R, H = bars(sym)
    kw = {**SPEC[sym], **cfg}
    I, p = nqs.indicators(df, **kw)
    (lo, sh), _ = nqs.conditions(df, I, p)
    tr = nqs.simulate(df, I, p, lo & R, sh & R, order=ORD, trail_mode=TM)
    if len(tr) < 40:
        print(f"  {sym:<6}{label:<34} only {len(tr)} trades"); return None
    gross = nqs.simulate(df, I, p, lo & R, sh & R, order=ORD, trail_mode=TM,
                         cost_mult=0.0).net_pts.mean()
    g = NC.score(df, I, p, tr, n_draws=n_draws, mask=R, order=ORD, trail_mode=TM)
    rt = 2 * p["slippage_ticks"] * p["tick"] + 2 * p["commission"] / p["point_value"]
    yy = pd.DatetimeIndex(tr.ts).year
    ex = tr[(yy != 2020) & (yy != 2022)]
    exv = float(ex.net_pts.mean()) if len(ex) > 20 else np.nan
    atr_med = float(np.nanmedian(I["atr"][R]))
    out = dict(sym=sym, label=label, n=int(len(tr)), gross=float(gross),
               gross_atr=float(gross / atr_med), net=float(g["exp"]),
               ctrl=float(g["ctrl"]), excess=float(g["excess"]), p=float(g["p"]),
               rt=float(rt), ex_crisis=exv, atr=atr_med,
               usd=float(tr.net_pts.sum() * p["point_value"]))
    print(f"  {sym:<6}{label:<34} n={out['n']:>5} gross{out['gross']:>+7.2f}pts "
          f"({out['gross_atr']:>+5.3f} ATR) net{out['net']:>+7.2f} ctrl{out['ctrl']:>+7.2f} "
          f"excess{out['excess']:>+7.2f} p={out['p']:.4f} RT={rt:.2f} "
          f"ex-crisis{exv:>+7.2f}")
    return out


print("=" * 138)
print("31. CROSS-INSTRUMENT TEST - the same entry rule on US30 (YM), research block, barclose/adverse")
print("    Independent evidence. Spends none of the NAS holdout.")
print("=" * 138)
rows = []
for sym in ("NAS", "US30"):
    df, R, H = bars(sym)
    print(f"\n  --- {sym}: {len(df):,} bars, {df.ts.min().date()} -> {df.ts.max().date()}, "
          f"research {int(df.sess[R].nunique()):,} sessions, median ATR {np.nanmedian(nqs.indicators(df, **SPEC[sym])[0]['atr'][R]):.1f} pts")
    for lbl, cfg in (("as written (full window)", CFG_ASWRITTEN),
                     ("ATR-relative distances", CFG_FIXED),
                     ("ATR-relative + RTH 09:31-11:00", CFG_RTH)):
        r = evaluate(sym, lbl, cfg)
        if r: rows.append(r)
T = pd.DataFrame(rows); T.to_csv(OUT + "crosstest.csv", index=False)

print("\n" + "=" * 138)
print("  THE COMPARISON THAT MATTERS - gross edge in ATR units, which is instrument-independent")
print("=" * 138)
for lbl in T.label.unique():
    g = T[T.label == lbl].set_index("sym")
    n_ = g.loc["NAS"] if "NAS" in g.index else None
    u_ = g.loc["US30"] if "US30" in g.index else None
    if n_ is None or u_ is None: continue
    agree = "AGREE" if np.sign(n_.excess) == np.sign(u_.excess) else "DISAGREE"
    print(f"  {lbl:<34} NAS gross {n_.gross_atr:+.3f} ATR, excess {n_.excess:+.2f} (p {n_.p:.3f})   "
          f"US30 gross {u_.gross_atr:+.3f} ATR, excess {u_.excess:+.2f} (p {u_.p:.3f})   -> {agree}")
json.dump(T.to_dict("records"), open(OUT + "crosstest.json", "w"), indent=2)
print("\n  written: crosstest.csv / .json")
