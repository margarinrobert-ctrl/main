"""Out-of-sample test of the best versions — including the part that was never tested.

V1's research/holdout split is documented. V2 and V3 have NO clean out-of-sample evidence: the
30-minute timeframe was chosen from 8 and the 1-ATR range filter from 5 values, both while looking
at the whole sample. This file does three things about that:

  A. RE-SPLIT and report each version on a locked final third. For V2 this is CONTAMINATED -- the
     parameters were picked with that data visible -- so it is an upper bound, not a test.
  B. HONEST SIMULATION: choose the timeframe and filter on the research portion ONLY, then apply
     that choice to the locked portion once. This is what a person following the method would
     actually have experienced.
  C. The book, both ways.

Usage: python3 research/best_oos.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from best_versions import HDR, _naive_days, daily_from_trades, line, perf
from bos_choch import prep, run
from bos_report import sc

SPLIT = 0.65          # research / locked holdout, on session boundaries


def split_masks(days: pd.DatetimeIndex):
    cut = days[int(len(days) * SPLIT)]
    return days < cut, days >= cut, cut


def bos_daily(tf, md, cal):
    d = prep(tf)
    side, ti, to, pnl, gross, r, why, delay = run(
        minutes=tf, session="rth_0930_1600", min_ema_dist=md)
    return daily_from_trades(pnl, ti, d["df"].index, cal), len(pnl)


def main() -> None:
    ibd = pd.read_parquet("research/portfolio_daily.parquet")
    cal = _naive_days(pd.to_datetime(ibd.pop("ts")))
    ib = pd.Series(ibd["IB_retr"].to_numpy(float), index=cal)
    res_m, hold_m, cut = split_masks(cal)
    print("=" * 118)
    print("OUT-OF-SAMPLE TEST OF THE BEST VERSIONS")
    print("=" * 118)
    print(f"\n  research: {res_m.sum()} sessions to {cut.date()}   |   "
          f"LOCKED holdout: {hold_m.sum()} sessions after\n")

    v2, n2 = bos_daily(30, 1.0, cal)
    book = ib + v2

    print("A. EACH VERSION ON THE LOCKED THIRD")
    print("   (V1 clean; V2/V3 CONTAMINATED — their parameters were chosen with this data visible)\n")
    print(HDR)
    for nm, ser in (("V1 IB retracement", ib), ("V2 BOS/CHoCH 30m+filter", v2),
                    ("V3 book (equal $)", book)):
        print(line(perf(ser[res_m].to_numpy(), label=f"{nm} — research")))
        print(line(perf(ser[hold_m].to_numpy(), label=f"{nm} — LOCKED")))
        print()

    print("=" * 118)
    print("B. THE HONEST SIMULATION — choose timeframe AND filter on research only, then open once")
    print("=" * 118 + "\n")
    grid = [(tf, md) for tf in (5, 15, 30, 60) for md in (0.0, 0.5, 1.0, 1.5, 2.0)]
    rows = []
    for tf, md in grid:
        ser, n = bos_daily(tf, md, cal)
        r = ser[res_m].to_numpy(); h = ser[hold_m].to_numpy()
        rows.append(dict(tf=tf, md=md, n=n,
                         res=r.sum(), res_sh=(r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan),
                         hold=h.sum(), hold_sh=(h.mean() / h.std() * np.sqrt(252) if h.std() > 0 else np.nan)))
    df = pd.DataFrame(rows)
    print(f"  {'tf':>5}{'filter':>8}{'trades':>8}{'research $':>13}{'res Sharpe':>12}"
          f"{'LOCKED $':>12}{'lock Sharpe':>13}")
    for _, r in df.iterrows():
        mark = ""
        print(f"  {int(r.tf):>3}m{r.md:>8.1f}{int(r.n):>8}{r.res:>13,.0f}{r.res_sh:>12.2f}"
              f"{r.hold:>12,.0f}{r.hold_sh:>13.2f}{mark}")

    best = df.loc[df.res.idxmax()]
    print(f"\n  Chosen on RESEARCH ONLY: {int(best.tf)}m, filter {best.md:.1f} ATR "
          f"(research ${best.res:,.0f}, Sharpe {best.res_sh:.2f})")
    print(f"  Its LOCKED result:       ${best.hold:,.0f}, Sharpe {best.hold_sh:.2f}")
    spec = df[(df.tf == 30) & (df.md == 1.0)].iloc[0]
    print(f"  V2 as shipped (30m/1.0): ${spec.hold:,.0f}, Sharpe {spec.hold_sh:.2f} on the same block")
    rho = df[["res", "hold"]].corr(method="spearman").iloc[0, 1]
    print(f"\n  Spearman rank correlation research -> holdout across the {len(df)} cells: {rho:+.3f}")
    print(f"  Cells profitable on research: {(df.res > 0).sum()} of {len(df)};  "
          f"on the holdout: {(df.hold > 0).sum()} of {len(df)}")
    both = df[(df.res > 0) & (df.hold > 0)]
    print(f"  Profitable on BOTH: {len(both)} of {len(df)}")

    print("\n" + "=" * 118)
    print("C. THE BOOK, BUILT THE HONEST WAY")
    print("=" * 118 + "\n")
    ser_best, _ = bos_daily(int(best.tf), float(best.md), cal)
    print(HDR)
    print(line(perf((ib + ser_best)[res_m].to_numpy(), label="book (research-chosen V2) — research")))
    print(line(perf((ib + ser_best)[hold_m].to_numpy(), label="book (research-chosen V2) — LOCKED")))
    print(line(perf(ib[hold_m].to_numpy(), label="V1 alone on the same LOCKED block")))
    print(f"\n  correlation on the LOCKED block: "
          f"{np.corrcoef(ib[hold_m].to_numpy(), ser_best[hold_m].to_numpy())[0,1]:+.3f}")


if __name__ == "__main__":
    main()
