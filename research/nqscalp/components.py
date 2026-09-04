"""Matrix correlations over the strategy's own parts, and a drop-one test to find
what is not earning its place.

Two matrices:
  A. CONDITION correlations - each rule in the entry as a boolean series. Two rules
     that fire on the same bars are one rule with extra typing.
  B. VARIANT P&L correlations - session P&L across parameter variants, with the
     Li & Ji effective number of independent tests.

Then DROP-ONE: remove each condition, re-simulate from the TRIGGERS (conditionally
splitting realised trades is not a filter test), and measure what its presence is
worth. Run on both instruments, because §31 showed NAS-only results reverse on US30.
"""
import numpy as np, pandas as pd, sys, json, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, nqcontrol as NC, data as D

OUT = "/home/user/main/docs/nqscalp/"
TM, ORD = "barclose", "adverse"
SPEC = {"NAS":  dict(point_value=20.0, tick=0.25, commission=1.24, qty=1),
        "US30": dict(point_value=5.0,  tick=1.00, commission=1.24, qty=1)}
BASE = dict(dist_units="atr", pullback_atr=1.15, trail_arm_atr=1.0,
            trail_offset_atr=0.5, sess_start_h=6, sess_start_m=0,
            sess_end_h=11, sess_end_m=30)


def parts(sym):
    """Every condition in the entry, as its own boolean series."""
    df = D.load(sym); R, Hm = D.blocks(df)
    I, p = nqs.indicators(df, **{**SPEC[sym], **BASE})
    c, h, l = I["c"], I["h"], I["l"]
    k, d = I["k"], I["d"]
    kp = np.concatenate([[np.nan], k[:-1]]); dp = np.concatenate([[np.nan], d[:-1]])
    chi = (df.tod.values - nqs.NY_MINUS_CHICAGO) % 1440
    thr = p["pullback_atr"] * I["atr"]
    P = {
        "trend gate (close vs EMA89)": (c > I["trend"], c < I["trend"]),
        "pullback depth >= 1.15 ATR": ((I["swing_hi"] - l) >= thr, (h - I["swing_lo"]) >= thr),
        "touch of fast/slow EMA": ((l <= I["fast"]) | (l <= I["slow"]),
                                   (h >= I["fast"]) | (h >= I["slow"])),
        "StochRSI reset (20/80)": (nqs.ll(k, p["reset_lookback"]) <= p["oversold"],
                                   nqs.hh(k, p["reset_lookback"]) >= p["overbought"]),
        "StochRSI %K/%D cross": ((k > d) & (kp <= dp), (k < d) & (kp >= dp)),
        "session window": ((chi >= 361) & (chi < 690), (chi >= 361) & (chi < 690)),
    }
    return df, R, I, p, P


def condition_matrix(sym):
    df, R, I, p, P = parts(sym)
    # a condition's "long-side firing" series, restricted to the research block
    M = pd.DataFrame({k: v[0][R].astype(float) for k, v in P.items()})
    C = M.corr()
    print(f"\n  --- {sym}: correlation between the entry conditions (long side, research bars)")
    print("      " + "".join(f"{n[:11]:>13}" for n in C.columns))
    for i, n in enumerate(C.index):
        print(f"  {n[:26]:<26}" + "".join(f"{C.iloc[i,j]:>13.2f}" for j in range(len(C.columns))))
    print(f"      firing rate: " + "  ".join(f"{n[:14]}={M[n].mean():.1%}" for n in C.columns))
    C.to_csv(OUT + f"corr_conditions_{sym}.csv")
    return C, M


def dropone(sym):
    df, R, I, p, P = parts(sym)
    RT = 2 * 1.0 * SPEC[sym]["tick"] + 2 * SPEC[sym]["commission"] / SPEC[sym]["point_value"]
    keys = list(P.keys())

    def build(drop=None):
        lo = np.ones(len(df), bool); sh = np.ones(len(df), bool)
        for kk in keys:
            if kk == drop: continue
            lo &= P[kk][0]; sh &= P[kk][1]
        fin = np.isfinite(I["atr"]) & np.isfinite(I["trend"]) & np.isfinite(I["d"]) & np.isfinite(I["swing_hi"])
        return lo & fin & R, sh & fin & R

    full_l, full_s = build()
    full = nqs.simulate(df, I, p, full_l, full_s, order=ORD, trail_mode=TM)
    print(f"\n  --- {sym}: DROP-ONE (round turn {RT:.2f} pts).  full rule: "
          f"n={len(full)} net {full.net_pts.mean():+.2f}")
    rows = []
    for kk in keys:
        lo, sh = build(drop=kk)
        tr = nqs.simulate(df, I, p, lo, sh, order=ORD, trail_mode=TM)
        if len(tr) < 40: continue
        g = NC.score(df, I, p, tr, n_draws=200, mask=R, order=ORD, trail_mode=TM)
        # what the condition is WORTH = full minus without-it, and whether removing it
        # changes the excess over a control matched to the NEW selectivity
        rows.append(dict(sym=sym, dropped=kk, n=len(tr), net=float(tr.net_pts.mean()),
                         excess=float(g["excess"]), p=float(g["p"]),
                         worth=float(full.net_pts.mean() - tr.net_pts.mean())))
        print(f"      without {kk:<28} n={len(tr):>6} net {tr.net_pts.mean():>+7.2f} "
              f"excess {g['excess']:>+6.2f} p={g['p']:.3f}   condition is worth "
              f"{full.net_pts.mean()-tr.net_pts.mean():>+6.2f} pts/trade")
    return pd.DataFrame(rows), full


print("=" * 132)
print("34. MATRIX CORRELATIONS OVER THE STRATEGY'S OWN CONDITIONS")
print("    Two rules that fire on the same bars are one rule.")
print("=" * 132)
mats = {}
for sym in ("NAS", "US30"):
    mats[sym] = condition_matrix(sym)

print("\n" + "=" * 132)
print("35. DROP-ONE - what is each condition actually worth?")
print("    Filters are removed from the TRIGGERS and re-simulated, not split out of realised trades.")
print("=" * 132)
allrows = []
for sym in ("NAS", "US30"):
    d, full = dropone(sym)
    allrows.append(d)
DO = pd.concat(allrows); DO.to_csv(OUT + "dropone.csv", index=False)

print("\n" + "=" * 132)
print("  WHAT TO DELETE - a condition earns its place only if removing it HURTS on BOTH instruments")
print("=" * 132)
piv = DO.pivot(index="dropped", columns="sym", values="worth")
pn = DO.pivot(index="dropped", columns="sym", values="n")
print(f"  {'condition':<30}{'worth on NAS':>16}{'worth on US30':>16}{'trades w/o it NAS':>20}{'verdict':>12}")
for k in piv.index:
    nas, us = piv.loc[k, "NAS"], piv.loc[k, "US30"]
    v = "KEEP" if (nas > 0 and us > 0) else ("DELETE" if (nas <= 0 and us <= 0) else "mixed")
    print(f"  {k:<30}{nas:>+16.2f}{us:>+16.2f}{int(pn.loc[k,'NAS']):>20,}{v:>12}")
json.dump(dict(worth_nas=piv["NAS"].to_dict(), worth_us30=piv["US30"].to_dict()),
          open(OUT + "dropone.json", "w"), indent=2)
print("\n  written: corr_conditions_*.csv, dropone.csv / .json")
