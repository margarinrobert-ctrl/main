"""R3 said the fast EMA is a drag. Confirm it on the ladder R2 already measured.

R3 decomposed `ema13>34>89` at channel 20 and found the SLOW half carries it: `ema34>ema89`
alone is positive on all three blocks with the best p in the table, while `ema13>ema34` is
negative on BOTH out-of-sample blocks.  One channel is one look, so the claim is re-run on the
six rungs R2 already declared -- same rungs, same blocks, same same-selectivity random veto,
nothing new chosen.

The comparison is head to head: the full three-EMA alignment against its slow half, on
identical bars, so only the fast inequality moves.
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
NDRAW = 400


def masks(f):
    c = f["close"].to_numpy()
    e13, e34, e89 = L.ema(c, 13), L.ema(c, 34), L.ema(c, 89)
    return {"align 13>34>89": (e13 > e34) & (e34 > e89),
            "slow 34>89": e34 > e89,
            "fast 13>34": e13 > e34}


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
    print("R4  DOES DROPPING THE FAST EMA HOLD ACROSS THE LADDER?  3 readings x 6 rungs x 3 blocks")
    print("=" * 110)
    rows = []
    for bname, f in block_frames():
        Mb = L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
        MM = masks(f)
        nsess = f.index.normalize().nunique()
        print(f"\n{'=' * 110}\n{bname}\n{'=' * 110}")
        for ch in R.CHANNELS:
            bs, bd = R.signals_ch(f, ch, [], Mb)
            b = L.stats(R.trades_ch(f, ch, [], Mb), nsess)
            for name, m in MM.items():
                keep = m[bs]
                sig, sd = bs[keep], bd[keep]
                if len(sig) < 5:
                    continue
                a = L.stats(S.walk(f, sig, sd, **L.KW), nsess)
                if not a.get("n"):
                    continue
                null = R.filter_control(f, bs, bd, len(sig), n_draw=NDRAW, seed=13)
                rows.append(dict(block=bname, ch=ch, reading=name, n=a["n"],
                                 keep=float(keep.mean()), base=b["pts"], pts=a["pts"],
                                 delta=a["pts"] - b["pts"], p=R.pval(a["pts"], null),
                                 pf=a["pf"], mde=a["mde"], total=a["total"]))
        s = pd.DataFrame([r for r in rows if r["block"] == bname])
        print(s.pivot(index="ch", columns="reading", values="delta").to_string(
            float_format=lambda x: f"{x:+.3f}"))
        print("\n  p against a same-selectivity random veto:")
        print(s.pivot(index="ch", columns="reading", values="p").to_string(
            float_format=lambda x: f"{x:.3f}"))

    D = pd.DataFrame(rows)
    D.to_csv(os.path.join(HERE, "r4_fastema.csv"), index=False)

    print(f"\n{'=' * 110}\nHEAD TO HEAD across all 18 (rung x block) cells\n{'=' * 110}")
    for name in ["align 13>34>89", "slow 34>89", "fast 13>34"]:
        s = D[D.reading == name]
        print(f"  {name:<16} positive delta {int((s.delta > 0).sum())}/{len(s)}   "
              f"p<=0.05 in {int((s.p <= 0.05).sum())}   median p {s.p.median():.3f}   "
              f"mean delta {s.delta.mean():+.3f}   mean PF {s.pf.mean():.3f}")
        for bn in D.block.unique():
            sb = s[s.block == bn]
            print(f"      {bn:<15} {int((sb.delta > 0).sum())}/{len(sb)} positive   "
                  f"mean delta {sb.delta.mean():+.3f}   total {sb.total.sum():+.0f}")

    a = D[D.reading == "align 13>34>89"].set_index(["block", "ch"])["delta"]
    c = D[D.reading == "slow 34>89"].set_index(["block", "ch"])["delta"]
    # NB bracket access, not attribute: `.align` is a DataFrame METHOD, so `j.align` returns
    # the bound method and the comparison raises. Ninth name-shadow on this branch and the
    # second time `.align` specifically has done it (after `.first`, `agg`, `metrics`, `stack`).
    j = pd.concat([a.rename("alignment"), c.rename("slow")], axis=1).dropna()
    print(f"\n  slow half beats the full alignment in {int((j['slow'] > j['alignment']).sum())} "
          f"of {len(j)} cells   mean advantage "
          f"{(j['slow'] - j['alignment']).mean():+.3f} points/trade")


if __name__ == "__main__":
    main()
