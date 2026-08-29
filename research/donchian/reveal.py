"""THE REVEAL - one pass over the locked block. Run exactly once.

Frozen rule set: A (plain n=20 Donchian baseline), B (A gated on ADX(14) at
07:00 above 30) and D (A requiring the close to exceed the channel by 1.0 x
ATR14). Rule C was dropped before the reveal - see NPRE below.

Rules are FROZEN before this script is executed. Nothing here may be tuned,
re-run with different parameters, or cherry-picked afterwards. The multiplicity
is declared before any locked number is printed.

Reading rules, from CLAUDE.md and the protocol:
  * A rule chosen on research should look BETTER there. The holdout is where an
    edge decays, not where it appears. Passing on locked while FAILING on
    research is the wrong shape and is a defect, not a result.
  * Score against the matched control, never against zero. On this engine
    t-vs-zero carries a 29-33% false-positive rate.
  * The Bonferroni-equivalent threshold for the declared multiplicity is printed
    first, so a p-value can be read against the search that produced it.
"""
import numpy as np, pandas as pd, sys, json
from engine import true_range, atr
import lab

# ------------------------------------------------------------- declared search
MULTIPLICITY = {
    "trend agent (final count)":                          244,
    "my ADX follow-ups (walkforward/fixed/us30/confound)": 58,
    "DSR trial universe":                                 160,
    "baseline lookback sweep":                              8,
    "CSCV grid":                                          140,
    "predictability budget event studies":                170,
    "entry mechanic (paired + geometry)":                  25,
    "ML filter (model configs + thresholds)":              25,
    "vol agent (final count)":                            353,
    "donchian agent (final count)":                       302,
}
K = sum(MULTIPLICITY.values())
NPRE = 6   # pre-registered locked comparisons: 3 frozen rules x 2 instruments
#   Rule C (ADX>30 AND low ATR percentile) was DROPPED before the reveal.
#   Its low-ATR leg was justified by "high volatility hurts these breakouts",
#   but that damage is 74-77% concentrated in five crisis months. Under a
#   criterion fixed before looking - keep C only if it beats B on BOTH
#   instruments after excluding those months - it beat B on US30 (+7.05 vs
#   +4.69) and LOST on NAS (+5.81 vs +6.46). Criterion failed, rule dropped.

def adx(dfx, n_=14):
    hh, ll, cc = dfx.high.values, dfx.low.values, dfx.close.values
    up = np.diff(hh, prepend=hh[0]); dn = -np.diff(ll, prepend=ll[0])
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(hh, ll, cc)
    def wil(x, p):
        out = np.empty_like(x); out[0] = x[0]; a = 1.0/p
        for i in range(1, len(x)): out[i] = a*x[i] + (1-a)*out[i-1]
        return out
    a_ = wil(tr, n_); pdi = 100*wil(plus, n_)/(a_+1e-12); mdi = 100*wil(minus, n_)/(a_+1e-12)
    return wil(100*np.abs(pdi-mdi)/(pdi+mdi+1e-12), n_)

def state(sym):
    df, w, r, h = lab.bars(sym)
    tod, sess = df.tod.values, df.sess.values
    A = adx(df, 14); a14 = atr(df, 14)
    is7 = tod == 420
    mA = dict(zip(sess[is7], A[is7])); mT = dict(zip(sess[is7], a14[is7]))
    at7 = np.array([mA.get(s, np.nan) for s in sess])
    tr7 = np.array([mT.get(s, np.nan) for s in sess])
    su = np.array(sorted(set(sess[is7]))); vals = np.array([mT[s] for s in su])
    pct = np.full(len(su), np.nan)
    for i in range(250, len(su)):
        pct[i] = (vals[i-250:i] < vals[i]).mean()
    mP = dict(zip(su, pct))
    tp7 = np.array([mP.get(s, np.nan) for s in sess])
    return df, w, r, h, tod, at7, tp7

# --------------------------------------------------------------- frozen rules
def rules(sym):
    df, w, r, h, tod, at7, tp7 = state(sym)
    out = {}
    idx, side, _ = lab.signals(df, 20)
    ok = tod[idx] > 420
    out["A baseline n=20"] = (idx[ok], side[ok], 1.5, 2.0)
    m = ok & (at7[idx] > 30)
    out["B ADX@07:00>30"] = (idx[m], side[m], 1.5, 2.0)
    # D: displaced break - the channel must be exceeded by 1.0 x ATR14 at the
    # signal bar. Found independently by the Donchian and volatility agents
    # (70% Jaccard). buffer 0 IS rule A, so the grid carries its own null control.
    idxD, sideD, _ = lab.signals(df, 20, buffer_atr=1.0)
    okD = tod[idxD] > 420
    out["D break > 1.0 ATR buffer"] = (idxD[okD], sideD[okD], 1.5, 2.0)
    return df, w, r, h, out

if __name__ == "__main__":
    if "--yes-really" not in sys.argv:
        print("This script opens the LOCKED block. Rules must be frozen first.")
        print("Re-run with --yes-really once the fleet has reported and the rule")
        print("set is final. It is intended to be run ONCE.")
        print(f"\nDeclared RESEARCH multiplicity K = {K}")
        for k_, v in MULTIPLICITY.items():
            print(f"    {v:>5}  {k_}")
        print(f"\n  Research-block Bonferroni alpha: {0.05/K:.3e}")
        print(f"  Pre-registered LOCKED comparisons: {NPRE}, threshold p < {0.05/NPRE:.4f}")
        sys.exit(0)

    print("="*110)
    print("REVEAL - one pass over the locked block")
    print("="*110)
    print(f"  DECLARED MULTIPLICITY K = {K} configurations evaluated across the study")
    for k_, v in MULTIPLICITY.items():
        print(f"      {v:>5}  {k_}")
    print(f"  Bonferroni-equivalent threshold for the RESEARCH p-values: p < {0.05/K:.3e}")
    print("  That correction applies to the research block, whose numbers were used")
    print("  to SELECT these rules. It does NOT apply to the locked block.")
    print()
    print(f"  The locked test is PRE-REGISTERED: {NPRE} comparisons (3 rules x 2 instruments),")
    print("  frozen in this file before any locked number was read. Its correct")
    print(f"  Bonferroni threshold is therefore p < {0.05/NPRE:.4f}, not {0.05/K:.1e}.")
    print("  Applying the research multiplicity to the holdout would double-count the")
    print("  search; the whole point of freezing rules first is to earn this.")
    print()
    print("  Wrong shape (better on LOCKED than RESEARCH) is a DEFECT, not a result.")

    summary = {}
    for sym in ("NAS", "US30"):
        df, w, r, h, rr = rules(sym)
        print("\n" + "="*110)
        print(f"{sym}")
        print("="*110)
        for name, (idx, side, sm, tm) in rr.items():
            bk = lab.book(sym, idx, side, stop_mult=sm, targ_mult=tm)
            row = {}
            for blk, mask in (("RESEARCH", r), ("LOCKED", h)):
                g = lab.gate(sym, bk, sm, tm, mask=mask, n_draws=800, seed=99, quiet=True)
                row[blk] = g
                print(f"  {name:<26} {blk:<9} n={g['n']:>5,} exp={g['exp']:>+7.2f}"
                      f" ctrl={g['ctrl']:>+7.2f} excess={g['excess']:>+7.2f}"
                      f" z={g['z']:>+6.2f} p={g['p']:.4f} pf={g['pf']:.2f} wr={g['wr']:.1%}")
            a_, b_ = row["RESEARCH"], row["LOCKED"]
            if not np.isnan(a_["excess"]) and not np.isnan(b_["excess"]):
                shape = "WRONG SHAPE (better on locked)" if b_["excess"] > a_["excess"] else "shape OK (decays)"
                sig = ("SURVIVES the pre-registered threshold" if b_["p"] < 0.05/NPRE
                       else "does NOT clear the pre-registered threshold")
                print(f"  {'':<26} -> {shape};  locked {sig}")
            summary[f"{sym}|{name}"] = {k_: {kk: (float(vv) if isinstance(vv,(int,float,np.floating)) else vv)
                                             for kk, vv in v.items()} for k_, v in row.items()}
            print()
    json.dump({"K": K, "multiplicity": MULTIPLICITY, "results": summary},
              open("/home/user/main/docs/donchian/reveal.json", "w"), indent=2, default=str)
    print("written: docs/donchian/reveal.json")
