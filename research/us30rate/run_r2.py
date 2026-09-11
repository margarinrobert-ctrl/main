"""The null on the ladder: does the sign consistency survive a same-selectivity random gate?

R1 found `+ema align` positive in 18 of 18 (rung x block) cells and `+adx<=20` in 15 of 18,
with all three of its failures on the RESERVED forward feed.  Sign consistency is the
evidence this branch trusts (`STUDY_V17`: a gradient reproducing in both directions), but a
condition that keeps 63% of the signals has to be scored against a RANDOM gate keeping 63%,
not against zero -- restrictiveness alone moves a profit factor (`STUDY_V12`).

Two things are settled here and nothing is selected:
  1.  Every cell against its own same-selectivity random VETO, 400 draws, re-simulated.
  2.  How many INDEPENDENT tests 18 cells actually are, given the rungs share their trades
      (R1 measured Jaccard 0.455-0.880 between them).
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
NDRAW = 400


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
    print("R2  THE NULL ON THE LADDER -- same-selectivity random VETO at every rung")
    print("=" * 100)
    print(f"draws per cell: {NDRAW}   cells: {len(R.CHANNELS) * 2 * 3}")

    rows = []
    for bname, f in block_frames():
        M = L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
        nsess = f.index.normalize().nunique()
        print(f"\n{'=' * 100}\n{bname}\n{'=' * 100}")
        for ch in R.CHANNELS:
            bs, bd = R.signals_ch(f, ch, [], M)
            bt = R.trades_ch(f, ch, [], M)
            b = L.stats(bt, nsess)
            for aname, conds in R.ARMS[1:]:
                sig, sd = R.signals_ch(f, ch, conds, M)
                t = R.trades_ch(f, ch, conds, M)
                a = L.stats(t, nsess)
                if not a.get("n"):
                    continue
                keep_sig = len(sig) / len(bs)
                null = R.filter_control(f, bs, bd, len(sig), n_draw=NDRAW, seed=7)
                p = R.pval(a["pts"], null)
                rows.append(dict(block=bname, ch=ch, arm=aname, n=a["n"],
                                 keep=keep_sig, pts=a["pts"], base=b["pts"],
                                 null_med=float(np.median(null)) if null is not None else np.nan,
                                 p=p, mde=a["mde"], pf=a["pf"]))
        s = pd.DataFrame([r for r in rows if r["block"] == bname])
        print(s[["ch", "arm", "n", "keep", "base", "pts", "null_med", "p", "mde", "pf"]].to_string(
            index=False, formatters={"keep": "{:.3f}".format, "base": "{:+.3f}".format,
                                     "pts": "{:+.3f}".format, "null_med": "{:+.3f}".format,
                                     "p": "{:.3f}".format, "mde": "{:.2f}".format,
                                     "pf": "{:.3f}".format}))

    D = pd.DataFrame(rows)
    D.to_csv(os.path.join(HERE, "r2_control.csv"), index=False)

    print(f"\n{'=' * 100}\nSUMMARY -- cells clearing p<=0.05 against a random gate of the same "
          f"selectivity\n{'=' * 100}")
    for aname, _ in R.ARMS[1:]:
        s = D[D.arm == aname]
        exp = 0.05 * len(s)
        print(f"  {aname:<12} {int((s.p <= 0.05).sum())} of {len(s)}  "
              f"({exp:.1f} expected)   beats its own null median in "
              f"{int((s.pts > s.null_med).sum())} of {len(s)}   best p {s.p.min():.3f}")
        for bn in D.block.unique():
            sb = s[s.block == bn]
            print(f"      {bn:<15} beats null median {int((sb.pts > sb.null_med).sum())}/{len(sb)}"
                  f"   median p {sb.p.median():.3f}")

    # ---- effective independence of the 18 cells --------------------------------------
    print(f"\n{'=' * 100}\nHOW MANY TESTS IS 18 CELLS?  (the rungs share their trades)\n{'=' * 100}")
    _, fa = block_frames()[0]
    Ma = L.build_masks(fa["high"].to_numpy(), fa["low"].to_numpy(), fa["close"].to_numpy())
    for aname, conds in R.ARMS[1:]:
        sg = {ch: R.signals_ch(fa, ch, conds, Ma)[0] for ch in R.CHANNELS}
        js = [R.jaccard(sg[R.CHANNELS[i]], sg[R.CHANNELS[j]])
              for i in range(len(R.CHANNELS)) for j in range(i + 1, len(R.CHANNELS))]
        jbar = float(np.mean(js))
        # Bailey/Lopez de Prado effective-trial form: N_hat = rho + (1 - rho) * M
        neff_ch = jbar + (1 - jbar) * len(R.CHANNELS)
        print(f"  {aname:<12} mean pairwise Jaccard {jbar:.3f}  ->  effective rungs "
              f"{neff_ch:.2f} of {len(R.CHANNELS)}")
        n_eff = neff_ch * 3
        from scipy.stats import binomtest
        s = D[D.arm == aname]
        k = int((s.pts > s.base).sum())
        k_eff = int(round(k / len(s) * n_eff))
        print(f"      sign test: {k}/{len(s)} nominal -> {k_eff}/{round(n_eff)} effective, "
              f"binomial p = {binomtest(k_eff, round(n_eff), 0.5, 'greater').pvalue:.4f}")


if __name__ == "__main__":
    main()
