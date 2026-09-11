"""Does the diversification claim hold as legs are added, and what does the FULL book do?"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm_book as P  # noqa: E402

pd.set_option("display.width", 220)


def sharpe_se(sr, n_yr):
    """Lo (2002): se(SR) ~ sqrt((1 + SR^2/2)/T), T in the SAME units as SR."""
    T = n_yr * P.TDY
    return float(np.sqrt((1 + 0.5 * (sr / np.sqrt(P.TDY)) ** 2) / T) * np.sqrt(P.TDY))


def main():
    L = P.load()
    R, A, av = P.panel(L)

    print("=" * 104)
    print("P2  THE DIVERSIFICATION CLAIM, MEASURED -- and the era when the whole book is live")
    print("=" * 104)

    r_all, _, n_ok = P.book(R, A, scheme="equal")
    st = P.stats(r_all)
    se = sharpe_se(st["sharpe"], st["yrs"])
    print(f"\nFULL-CALENDAR BOOK  Sharpe {st['sharpe']:+.3f} +- {se:.3f} "
          f"(95% CI [{st['sharpe']-1.96*se:+.2f}, {st['sharpe']+1.96*se:+.2f}]) over {st['yrs']:.2f} yr")
    print("  A Sharpe standard error is the number that decides whether a book is worth trading,")
    print("  and it falls only with TIME -- not with more searching.")

    # ---- 1. Sharpe against the number of legs actually live -------------------------------
    print("\n" + "=" * 104)
    print("1. SHARPE AGAINST LEGS LIVE  (sqrt(N) is the claim; this is the measurement)")
    print("=" * 104)
    rows = []
    for lo, hi in [(2, 9), (10, 11), (12, 21), (22, 23)]:
        m = (n_ok >= lo) & (n_ok <= hi)
        seg = r_all[m.reindex(r_all.index).fillna(False)]
        if len(seg) < 40:
            continue
        s = P.stats(seg)
        rows.append(dict(legs=f"{lo}-{hi}", days=len(seg), med_legs=int(n_ok[m].median()),
                         ann_ret=s["ann_ret"], ann_vol=s["ann_vol"], sharpe=s["sharpe"]))
    print(pd.DataFrame(rows).to_string(index=False, formatters={
        "ann_ret": "{:+.2f}".format, "ann_vol": "{:.2f}".format, "sharpe": "{:+.3f}".format}))
    print("\n  Read the VOL column: adding legs should cut it. If vol falls while return holds,")
    print("  the diversification is real; if both fall together, it is just smaller positions.")

    # ---- 2. the era in which the whole book exists ----------------------------------------
    print("\n" + "=" * 104)
    print("2. THE FULL-BOOK ERA  -- dates on which >= 20 of 23 legs are live")
    print("=" * 104)
    m20 = (n_ok >= 20).reindex(r_all.index).fillna(False)
    r20 = r_all[m20]
    if len(r20) > 60:
        s20 = P.stats(r20)
        b20 = P.block_boot(r20)
        p20 = P.perm_dd(r20)
        se20 = sharpe_se(s20["sharpe"], s20["yrs"])
        print(f"  {r20.index[0].date()} -> {r20.index[-1].date()}   {len(r20)} days "
              f"({s20['yrs']:.2f} yr)")
        print(f"  {s20['ann_ret']:+.2f}%/yr at {s20['ann_vol']:.2f}% vol   "
              f"Sharpe {s20['sharpe']:+.3f} +- {se20:.3f}   maxDD {s20['maxdd']:.2f}%   "
              f"ret/DD {s20['ret_dd']:+.2f}")
        print(f"  bootstrap P(mean<=0) {np.mean(b20 <= 0):.4f}   "
              f"MC p99 DD {np.percentile(p20,99):.2f}%  ({np.percentile(p20,99)/s20['maxdd']:.2f}x)")
        print("\n  This is the closest thing here to a forward read of the assembled book -- and it is")
        print("  SHORT, so its Sharpe error bar is wide. Read the CI, not the point estimate.")

    # ---- 3. drop-one over legs ------------------------------------------------------------
    print("\n" + "=" * 104)
    print("3. DROP-ONE: which legs carry the book, and which subtract")
    print("=" * 104)
    base = P.stats(r_all)["sharpe"]
    out = []
    for c in R.columns:
        A2 = A.copy(); A2[c] = False
        r2, _, _ = P.book(R, A2, scheme="equal")
        r2 = r2.reindex(r_all.index).dropna()
        if len(r2) < 100:
            continue
        out.append(dict(dropped=c, sharpe=P.stats(r2)["sharpe"],
                        delta=P.stats(r2)["sharpe"] - base))
    D = pd.DataFrame(out).sort_values("delta")
    print(f"  base Sharpe {base:+.3f}   (a POSITIVE delta means the book is better WITHOUT that leg)")
    print(D.to_string(index=False, formatters={"sharpe": "{:+.3f}".format,
                                               "delta": "{:+.4f}".format}))
    print(f"\n  legs whose removal HELPS: {int((D.delta > 0).sum())} of {len(D)}")

    # ---- 4. what a target Sharpe would take ----------------------------------------------
    print("\n" + "=" * 104)
    print("4. WHAT WOULD RAISE IT  -- the arithmetic, not a search")
    print("=" * 104)
    lc = R.loc[:, :].corr().values
    iu = np.triu_indices_from(lc, 1)
    rho = float(np.nanmean(lc[iu]))
    n = R.shape[1]
    print(f"  mean pairwise leg correlation: {rho:+.4f} over {len(iu[0])} pairs")
    print("  For N legs of equal Sharpe s and average correlation rho,")
    print("      book Sharpe  =  s * sqrt(N) / sqrt(1 + (N-1)*rho)")
    # A leg's Sharpe MUST be measured zero-filled over the same calendar the book uses.
    # Measured on its own ACTIVE days only, a leg that trades twenty times a year prints a
    # large ratio while contributing almost nothing over 252 -- CLAUDE.md's standing rule,
    # and my first pass here made exactly that error (mean solo Sharpe +1.132 active-only
    # against +0.383 zero-filled, which predicted a book Sharpe of 3.99 against a measured
    # 1.61).
    solo_active, solo_zf = [], []
    for c in R.columns:
        live = R[c][A[c]]                      # zero-filled over the leg's live calendar
        act = live[live != 0]                  # its trading days only
        if len(act) > 60 and live.std() > 0:
            solo_zf.append(live.mean() / live.std() * np.sqrt(P.TDY))
            solo_active.append(act.mean() / act.std() * np.sqrt(P.TDY))
    s_bar = float(np.mean(solo_zf))
    print(f"\n  mean solo leg Sharpe, ZERO-FILLED over its live calendar: {s_bar:+.3f}")
    print(f"  (the same legs measured on ACTIVE DAYS ONLY read {np.mean(solo_active):+.3f} -- "
          f"{np.mean(solo_active)/max(s_bar,1e-9):.2f}x,")
    print("   which is the number that must NOT be used here)")
    print(f"  {'N legs':>7} {'predicted book Sharpe':>23}")
    for N in (11, 23, 40, 60, 100, 200):
        pred = s_bar * np.sqrt(N) / np.sqrt(1 + (N - 1) * max(rho, 1e-6))
        print(f"  {N:>7} {pred:>23.3f}")
    ceiling = s_bar / np.sqrt(max(rho, 1e-6))
    print(f"\n  CEILING as N -> infinity: {ceiling:.2f}   (set by rho, not by leg count)")
    print("  That is the whole lever, and it is why adding a 24th correlated leg buys almost")
    print("  nothing while a genuinely independent asset class buys a lot.")


if __name__ == "__main__":
    main()
