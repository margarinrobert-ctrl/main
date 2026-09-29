"""The power ladder: does a higher trade rate close the detectability gap?

Six declared channel rungs x three declared arms x three blocks.  Nothing is selected.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "us30scalp"))
import r_lib as R  # noqa: E402
import s10lib as L  # noqa: E402
import s30core as S  # noqa: E402

pd.set_option("display.width", 200)
np.set_printoptions(suppress=True)


def block_frames():
    us30 = S.load("US30L")
    bk = S.blocks(us30, "US30L")
    iso = S.load("US30I")
    bi = S.blocks(iso, "US30I")
    return [("A research", us30.loc[bk["A_research"]]),
            ("B holdout", us30.loc[bk["B_holdout"]]),
            ("C forward ISO", iso.loc[bi["C_forward"]])]


def main():
    print("=" * 100)
    print("R1  TRADE RATE AS THE POWER AXIS -- six declared channel rungs, three declared arms")
    print("=" * 100)
    print(f"channels declared: {R.CHANNELS}")
    print(f"arms declared:     {[a for a, _ in R.ARMS]}")
    n_cells = len(R.CHANNELS) * len(R.ARMS)
    print(f"cells on the research block: {n_cells}   "
          f"E[max t | pure noise] = {R.e_max_normal(n_cells):.3f}   "
          f"detection threshold = {R.Z80:.3f}")
    print("  (a ladder is readable where a grid is not: section 10's 1,176 cells gave 3.301)")

    frames = block_frames()
    out = []
    for bname, f in frames:
        M = L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
        nsess = f.index.normalize().nunique()
        yrs = R.years(f)
        print(f"\n{'=' * 100}\n{bname}   {f.index[0].date()} -> {f.index[-1].date()}   "
              f"{yrs:.2f} yr   {len(f):,} bars\n{'=' * 100}")
        for ch in R.CHANNELS:
            for aname, conds in R.ARMS:
                t = R.trades_ch(f, ch, conds, M)
                d = R.row(t, nsess, yrs)
                d.update(block=bname, ch=ch, arm=aname)
                out.append(d)
        sub = pd.DataFrame([o for o in out if o["block"] == bname])
        cols = ["ch", "arm", "n", "per_yr", "pts", "sd", "t", "mde", "ratio", "pf", "win",
                "total", "sharpe"]
        print(sub[cols].to_string(index=False,
                                  formatters={"per_yr": "{:.1f}".format, "pts": "{:+.3f}".format,
                                              "sd": "{:.1f}".format, "t": "{:+.3f}".format,
                                              "mde": "{:.2f}".format, "ratio": "{:+.3f}".format,
                                              "pf": "{:.3f}".format, "win": "{:.3f}".format,
                                              "total": "{:+.0f}".format,
                                              "sharpe": "{:+.2f}".format}))

    df = pd.DataFrame(out)
    df.to_csv(os.path.join(HERE, "r1_ladder.csv"), index=False)

    # ---- Q1: does t improve with the rate? --------------------------------------------
    print(f"\n{'=' * 100}\nQ1  POWER: is a shorter channel a better bet on the STATISTIC?\n{'=' * 100}")
    print("If sd and per-trade edge were flat in the channel, t would rise as sqrt(n).")
    for bname, _ in frames:
        s = df[(df.block == bname) & (df.n > 0)]
        print(f"\n{bname}")
        for aname, _ in R.ARMS:
            r = s[s.arm == aname].sort_values("ch")
            if not len(r):
                continue
            sp_n = r[["per_yr", "t"]].corr(method="spearman").iloc[0, 1]
            sp_e = r[["per_yr", "pts"]].corr(method="spearman").iloc[0, 1]
            sp_s = r[["per_yr", "sd"]].corr(method="spearman").iloc[0, 1]
            print(f"  {aname:<12} spearman(rate, t) {sp_n:+.3f}   "
                  f"spearman(rate, pts) {sp_e:+.3f}   spearman(rate, sd) {sp_s:+.3f}")

    # ---- Q2: replication of adx<=20 across every rung ---------------------------------
    print(f"\n{'=' * 100}\nQ2  REPLICATION: does `adx<=20` hold at every rung, or only at 20?\n{'=' * 100}")
    piv = []
    for bname, _ in frames:
        for ch in R.CHANNELS:
            b = df[(df.block == bname) & (df.ch == ch) & (df.arm == "base")]
            for aname, _ in R.ARMS[1:]:
                a = df[(df.block == bname) & (df.ch == ch) & (df.arm == aname)]
                if not len(b) or not len(a) or not b.iloc[0]["n"] or not a.iloc[0]["n"]:
                    continue
                piv.append(dict(block=bname, ch=ch, arm=aname,
                                base=b.iloc[0]["pts"], armv=a.iloc[0]["pts"],
                                delta=a.iloc[0]["pts"] - b.iloc[0]["pts"],
                                n=a.iloc[0]["n"], mde=a.iloc[0]["mde"]))
    P = pd.DataFrame(piv)
    P.to_csv(os.path.join(HERE, "r1_replication.csv"), index=False)
    for aname, _ in R.ARMS[1:]:
        s = P[P.arm == aname]
        print(f"\n  {aname}   positive delta in {int((s.delta > 0).sum())} of {len(s)} cells")
        print(s.pivot(index="ch", columns="block", values="delta").to_string(
            float_format=lambda x: f"{x:+.3f}"))

    # ---- Q3: do the rungs overlap? ----------------------------------------------------
    print(f"\n{'=' * 100}\nQ3  Do the rungs share their trades?  (pooling them would not multiply n)\n{'=' * 100}")
    _, fa = frames[0]
    Ma = L.build_masks(fa["high"].to_numpy(), fa["low"].to_numpy(), fa["close"].to_numpy())
    sigs = {ch: R.signals_ch(fa, ch, [], Ma)[0] for ch in R.CHANNELS}
    J = pd.DataFrame(index=R.CHANNELS, columns=R.CHANNELS, dtype=float)
    for i in R.CHANNELS:
        for j in R.CHANNELS:
            J.loc[i, j] = R.jaccard(sigs[i], sigs[j])
    print("  Jaccard of the SIGNAL BAR sets, research block:")
    print(J.to_string(float_format=lambda x: f"{x:.3f}"))
    print(f"\n  signal counts: {{{', '.join(f'{c}: {len(sigs[c])}' for c in R.CHANNELS)}}}")

    # ---- Q4: what would it take -------------------------------------------------------
    print(f"\n{'=' * 100}\nQ4  WHAT WOULD IT TAKE, per rung (research block, delivered effect)\n{'=' * 100}")
    s = df[(df.block == "A research") & (df.n > 0) & (df.pts > 0)]
    print(s[["ch", "arm", "n", "per_yr", "pts", "mde", "n_need", "yrs_need"]].to_string(
        index=False, formatters={"per_yr": "{:.1f}".format, "pts": "{:+.3f}".format,
                                 "mde": "{:.2f}".format, "n_need": "{:,.0f}".format,
                                 "yrs_need": "{:.1f}".format}))
    print("\n  (`n_need` is trades for the DELIVERED effect to reach 80% power; it is itself a "
          "noisy estimate\n   because it divides by an effect measured on this sample.)")


if __name__ == "__main__":
    main()
