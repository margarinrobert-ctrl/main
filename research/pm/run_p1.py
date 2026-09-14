"""The book a desk would actually have run: every leg admitted the day its own research ends."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm_book as P  # noqa: E402

pd.set_option("display.width", 220)


def main():
    L = P.load()
    R, A, av = P.panel(L)
    print("=" * 104)
    print("P1  PER-LEG AVAILABILITY -- the construction defect, and what removing it is worth")
    print("=" * 104)
    print(f"legs: {R.shape[1]}   calendar: {R.index[0].date()} -> {R.index[-1].date()}   "
          f"{len(R)} dates")

    print("\n--- when each leg becomes available (day after its OWN research block ends) ---")
    print(av.sort_values().to_frame("available_from").assign(
        date=lambda d: d.available_from.dt.date)[["date"]].to_string())

    print("\n--- the old GLOBAL cut, for comparison ---")
    gcut = pd.Timestamp("2021-12-17")
    old = [c for c in R.columns if (R[c] != 0).idxmax() <= gcut]
    print(f"  STUDY_ALLOCATION's cut {gcut.date()} admits {len(old)} of {R.shape[1]} legs")
    print(f"  excluded: {sorted(set(R.columns) - set(old))}")

    n_ok = A.sum(axis=1)
    print(f"\n--- legs live over time ---")
    for y, g in n_ok.groupby(n_ok.index.year):
        print(f"  {y}: median {int(g.median()):2d} live   max {int(g.max()):2d}")

    print("\n" + "=" * 104)
    print("THE BOOK, equal weight over whatever is live, unlevered (1 unit per leg per trade)")
    print("=" * 104)
    rows = []
    for scheme in ("equal", "invvol"):
        r, w, _ = P.book(R, A, scheme=scheme)
        s = P.stats(r); s.update(arm=f"all 23, {scheme}")
        rows.append(s)
    # the 11-leg book on the SAME dates, so the comparison is like for like
    A11 = A.copy()
    for c in A11.columns:
        if c not in old:
            A11[c] = False
    r11, _, _ = P.book(R, A11, scheme="equal")
    s = P.stats(r11); s.update(arm="11 legs (old cut), equal"); rows.append(s)

    D = pd.DataFrame(rows)[["arm", "days", "yrs", "ann_ret", "ann_vol", "sharpe", "total",
                            "maxdd", "ret_dd", "pct_underwater"]]
    print(D.to_string(index=False, formatters={
        "yrs": "{:.2f}".format, "ann_ret": "{:+.3f}".format, "ann_vol": "{:.3f}".format,
        "sharpe": "{:+.3f}".format, "total": "{:+.2f}".format, "maxdd": "{:.2f}".format,
        "ret_dd": "{:+.2f}".format, "pct_underwater": "{:.3f}".format}))
    print("\n  (units are PERCENT OF ENTRY PRICE at one unit a trade -- a leverage-free number.)")

    r, _, _ = P.book(R, A, scheme="equal")
    r.to_frame("ret").to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "p1_book_daily.csv"))

    print("\n" + "=" * 104)
    print("IS THE EDGE THERE?  day-block bootstrap, and the permutation for the path")
    print("=" * 104)
    for name, x in (("all 23", r), ("11 legs", r11)):
        b = P.block_boot(x)
        pm = P.perm_dd(x)
        st = P.stats(x)
        print(f"  {name:<9} mean/day {x.mean():+.5f}   P(mean<=0) {np.mean(b <= 0):.4f}   "
              f"95% CI [{np.percentile(b,2.5):+.5f}, {np.percentile(b,97.5):+.5f}]")
        print(f"            realised DD {st['maxdd']:.2f}   MC p99 {np.percentile(pm,99):.2f}   "
              f"p99/realised {np.percentile(pm,99)/st['maxdd']:.2f}x   "
              f"percentile of realised {np.mean(pm < st['maxdd']):.3f}")

    print("\n" + "=" * 104)
    print("THE LEVERAGE QUESTION -- return is a sizing decision, not a strategy decision")
    print("=" * 104)
    st = P.stats(r)
    pm = P.perm_dd(r)
    p99_1x = float(np.percentile(pm, 99))
    # `pct` is ALREADY in percent of entry price, so these are percentages, not fractions.
    print(f"  unlevered: {st['ann_ret']:+.2f}%/yr at {st['ann_vol']:.2f}% vol, "
          f"Sharpe {st['sharpe']:+.2f}, realised maxDD {st['maxdd']:.2f}%, MC p99 DD {p99_1x:.2f}%")
    print(f"\n  {'target %/yr':>12} {'leverage':>9} {'ann vol':>8} {'realised DD':>12} {'MC p99 DD':>10}")
    for tgt in (5.0, 10.0, 15.0, 20.0, 30.0):
        lev = tgt / st["ann_ret"] if st["ann_ret"] > 0 else np.nan
        print(f"  {tgt:>11.0f}% {lev:>9.2f} {st['ann_vol']*lev:>7.2f}% "
              f"{st['maxdd']*lev:>11.2f}% {p99_1x*lev:>9.2f}%")
    print("\n  A drawdown tolerance PICKS the row, and the MC p99 column is the one that binds.")
    print("\n  Size against the MC p99, not the realised drawdown -- this branch has measured that")
    print("  ratio at 1.2x to 3.5x across every study that has run the permutation.")


if __name__ == "__main__":
    main()
