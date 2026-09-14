"""Decompose the condition section 14 promoted: is `ema13>34>89` doing three things or one?

Section 14 found the EMA ALIGNMENT is the more robust of the two arms -- 18 of 18 against a
same-selectivity random veto across six channel rungs and three blocks, against `adx<=20`'s
15/18 and 3/6 on the reserved feed.  That promotion makes the next question worth asking
before anything is built on it: is the three-EMA stack a mechanism, or is it a simpler
condition wearing two extra inequalities?

Two of this branch's own findings say to check.  `STUDY_V40`/`STUDY_V51`: a moving average is
priced by its DISTANCE, not by the crossing -- `close > MA200` is the base condition and worth
nothing alone, while `(close - MA200)/ATR` in the top half clears at p 0.017 and the MA200
FLOOR at >=1.5 ATR clears three blocks at p 0.001.  And `STUDY_V41`/`STUDY_V16`: the state form
of an EMA condition passes 82-91% of breakout bars, so it removes a sixth of the signals and is
nearly free of information.

Seven declared readings, no sweep, every one reported:

  A  ema13>34>89                the arm as section 14 tested it
  B  ema13>ema34                its fast half alone
  C  ema34>ema89                its slow half alone
  D  close>ema89                the plain state, no stack
  E  (close-ema89)/ATR >= 0     the same thing said as a distance -- must equal D
  F  (close-ema89)/ATR >= its research median      the DISTANCE reading
  G  (close-ema89)/ATR >= 1.5   V51's floor, frozen at the value that market chose

Cells: 7 readings x 3 blocks = 21, E[max t | pure noise] = 1.90 against a 2.802 threshold.
Every threshold in F is fitted on the RESEARCH block only and carried to the other two.
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

pd.set_option("display.width", 220)
CH = 20          # the channel section 12/13 declared; NOT re-chosen here
NDRAW = 400


def readings(f, dist_med=None):
    c = f["close"].to_numpy()
    at = f["atr"].to_numpy()
    e13, e34, e89 = L.ema(c, 13), L.ema(c, 34), L.ema(c, 89)
    with np.errstate(invalid="ignore", divide="ignore"):
        d = (c - e89) / at
    d = np.nan_to_num(d, nan=-999.0)
    out = {
        "A ema13>34>89": (e13 > e34) & (e34 > e89),
        "B ema13>ema34": e13 > e34,
        "C ema34>ema89": e34 > e89,
        "D close>ema89": c > e89,
        "E dist>=0": d >= 0.0,
        "G dist>=1.5": d >= 1.5,
    }
    if dist_med is not None:
        out["F dist>=med"] = d >= dist_med
    return out, d


def block_frames():
    us30 = S.load("US30L")
    bk = S.blocks(us30, "US30L")
    iso = S.load("US30I")
    bi = S.blocks(iso, "US30I")
    return [("A research", us30.loc[bk["A_research"]]),
            ("B holdout", us30.loc[bk["B_holdout"]]),
            ("C forward ISO", iso.loc[bi["C_forward"]])]


def main():
    print("=" * 110)
    print(f"R3  IS THE EMA ALIGNMENT ONE CONDITION OR THREE?   channel {CH}, 7 declared readings")
    print("=" * 110)
    print(f"cells: 21   E[max t | pure noise] = {R.e_max_normal(21):.3f}   "
          f"threshold = {R.Z80:.3f}")

    frames = block_frames()

    # --- the ONE fitted number, taken on the research block only -----------------------
    _, fa = frames[0]
    sig_a, _ = R.signals_ch(fa, CH, [])
    _, da = readings(fa)
    dist_med = float(np.median(da[sig_a]))
    print(f"\nthe single fitted threshold: median (close-ema89)/ATR over the RESEARCH block's "
          f"own {len(sig_a)} signal bars = {dist_med:.4f}")
    print("  (carried unchanged to the holdout and the forward feed)")

    rows = []
    for bname, f in frames:
        R89, d = readings(f, dist_med)
        Mbase = L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
        nsess = f.index.normalize().nunique()
        bs, bd = R.signals_ch(f, CH, [], Mbase)
        bt = R.trades_ch(f, CH, [], Mbase)
        b = L.stats(bt, nsess)
        print(f"\n{'=' * 110}\n{bname}   base: n={b['n']} pts={b['pts']:+.3f} pf={b['pf']:.3f}"
              f"\n{'=' * 110}")
        for name in sorted(R89):
            m = R89[name]
            keep = m[bs]
            sig, sd = bs[keep], bd[keep]
            if len(sig) < 5:
                continue
            t = S.walk(f, sig, sd, **L.KW)
            a = L.stats(t, nsess)
            if not a.get("n"):
                continue
            null = R.filter_control(f, bs, bd, len(sig), n_draw=NDRAW, seed=11)
            p = R.pval(a["pts"], null)
            rows.append(dict(block=bname, reading=name, n=a["n"], lift=float(keep.mean()),
                             base=b["pts"], pts=a["pts"], delta=a["pts"] - b["pts"],
                             null_med=float(np.median(null)) if null is not None else np.nan,
                             p=p, mde=a["mde"], pf=a["pf"], total=a["total"],
                             sharpe=a["sharpe"]))
        s = pd.DataFrame([r for r in rows if r["block"] == bname])
        print(s[["reading", "n", "lift", "pts", "delta", "null_med", "p", "mde", "pf", "total",
                 "sharpe"]].to_string(
            index=False, formatters={"lift": "{:.3f}".format, "pts": "{:+.3f}".format,
                                     "delta": "{:+.3f}".format, "null_med": "{:+.3f}".format,
                                     "p": "{:.3f}".format, "mde": "{:.2f}".format,
                                     "pf": "{:.3f}".format, "total": "{:+.0f}".format,
                                     "sharpe": "{:+.2f}".format}))

    D = pd.DataFrame(rows)
    D.to_csv(os.path.join(HERE, "r3_decompose.csv"), index=False)

    print(f"\n{'=' * 110}\nSUMMARY -- every reading across the three blocks\n{'=' * 110}")
    piv = D.pivot(index="reading", columns="block", values="delta")
    piv["pos"] = (piv > 0).sum(axis=1)
    piv["beats null"] = [int((D[(D.reading == r)].pts > D[(D.reading == r)].null_med).sum())
                         for r in piv.index]
    piv["min p"] = [D[D.reading == r].p.min() for r in piv.index]
    print(piv.to_string(float_format=lambda x: f"{x:+.3f}"))

    print(f"\n{'=' * 110}\nBASE RATE: what share of the trigger's own bars does each reading pass?"
          f"\n{'=' * 110}")
    print("  (a reading passing >95% is the trigger restated -- this branch has caught eight)")
    for bname, f in frames:
        R89, _ = readings(f, dist_med)
        Mb = L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
        bs, _ = R.signals_ch(f, CH, [], Mb)
        allbars = np.ones(len(f), bool)
        line = []
        for name in sorted(R89):
            on_sig = R89[name][bs].mean()
            on_all = R89[name][allbars].mean()
            line.append(f"{name}: {on_sig:.3f} (lift {on_sig / on_all:.2f}x)")
        print(f"  {bname:<15} " + "   ".join(line))


if __name__ == "__main__":
    main()
