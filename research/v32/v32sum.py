"""Aggregate the V32 tables. The individual rows are 72 cells per market per block; the summary
statistics are what decide the study.

Reads the raw run output rather than re-fitting, so the numbers here and in the tables are the same
numbers by construction.

Usage: python3 research/v32/v32sum.py docs/ib/v32_ml_output.txt
"""
from __future__ import annotations

import re
import sys

import numpy as np
import pandas as pd


def parse(path):
    rows, market, block, task = [], None, None, None
    base = {}
    for ln in open(path):
        m = re.match(r"^(NQ|US30) (\d+)m ", ln)
        if m:
            market = m.group(1)
        if "MODEL trained on R" in ln:
            block, task = "research", "R"
        elif "MODEL trained on WIN" in ln:
            block, task = "research", "win"
        elif "THE LOCKED READ" in ln:
            block, task = "locked", None
        m = re.match(r"\s+BASELINE research \(no model\):\s+n\s+(\d+)\s+win\s+([\d.]+)\s+PF\s+"
                     r"([\d.]+)\s+Sharpe\s+([+-][\d.]+)", ln)
        if m:
            base[(market, "research")] = dict(n=int(m[1]), win=float(m[2]), pf=float(m[3]),
                                              sharpe=float(m[4]))
        m = re.match(r"\s+BASELINE\s+locked\s+n\s+(\d+) win ([\d.]+) PF ([\d.]+) Sharpe "
                     r"([+-][\d.]+) R ([+-][\d.]+) p90 ([+-][\d.]+)", ln)
        if m:
            base[(market, "locked")] = dict(n=int(m[1]), win=float(m[2]), pf=float(m[3]),
                                            sharpe=float(m[4]), p90=float(m[6]))
        # research rows: set model keep n win pf sharpe R p90 dd p(pf) p(win) shufPF
        m = re.match(r"\s+(FLOW\+BASE|FLOW|BASE)\s+(xgb|lgbm)\s+(\d+)%\s+(\d+)\s+([\d.]+)\s+"
                     r"([\d.]+)\s+([+-][\d.]+)\s+([+-][\d.]+)\s+([+-][\d.]+)\s+([\d.]+)\s+"
                     r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$", ln)
        if m and block == "research":
            rows.append(dict(market=market, block="research", task=task, fset=m[1], model=m[2],
                             keep=int(m[3]), n=int(m[4]), win=float(m[5]), pf=float(m[6]),
                             sharpe=float(m[7]), R=float(m[8]), p90=float(m[9]), dd=float(m[10]),
                             p_pf=float(m[11]), p_win=float(m[12]), shuf_pf=float(m[13])))
            continue
        # locked rows: task set model keep n win dwin pf sharpe R p90 dd p(pf) p(win)
        m = re.match(r"\s+(R|win)\s+(FLOW\+BASE|FLOW|BASE)\s+(xgb|lgbm)\s+(\d+)%\s+(\d+)\s+"
                     r"([\d.]+)\s+([+-][\d.]+)\s+([\d.]+)\s+([+-][\d.]+)\s+([+-][\d.]+)\s+"
                     r"([+-][\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$", ln)
        if m and block == "locked":
            rows.append(dict(market=market, block="locked", task=m[1], fset=m[2], model=m[3],
                             keep=int(m[4]), n=int(m[5]), win=float(m[6]), dwin=float(m[7]),
                             pf=float(m[8]), sharpe=float(m[9]), R=float(m[10]), p90=float(m[11]),
                             dd=float(m[12]), p_pf=float(m[13]), p_win=float(m[14]),
                             shuf_pf=np.nan))
    return pd.DataFrame(rows), base


def hdr(t):
    print("\n" + "=" * 118)
    print(t)
    print("=" * 118)


def main(path):
    df, base = parse(path)
    df = df[df.keep < 100]                       # the 100% rung IS the baseline
    hdr("V32 SUMMARY -- what the 4 x 72 cells say once they are counted rather than read")
    print(f"   parsed {len(df)} model cells "
          f"({df.market.nunique()} markets x {df.block.nunique()} blocks x 2 objectives x "
          f"3 feature sets x 2 models x 5 rungs)")

    for (mkt, blk), g in df.groupby(["market", "block"], sort=False):
        b = base[(mkt, blk)]
        print(f"\n   {mkt} {blk.upper():<9} baseline  win {b['win']:.3f}  PF {b['pf']:.3f}  "
              f"Sharpe {b['sharpe']:+.2f}")
        for task, gt in g.groupby("task", sort=False):
            print(f"      trained on {task:<4}  "
                  f"beat baseline PF {int((gt.pf > b['pf']).sum()):>2}/{len(gt):<3}"
                  f"   Sharpe {int((gt.sharpe > b['sharpe']).sum()):>2}/{len(gt):<3}"
                  f"   win {int((gt.win > b['win']).sum()):>2}/{len(gt):<3}"
                  f"   |  clear the control p(PF)<=0.05 {int((gt.p_pf <= 0.05).sum()):>2}"
                  f"   p(win)<=0.05 {int((gt.p_win <= 0.05).sum()):>2}"
                  f"   |  best win {gt.win.max():.3f} (+{gt.win.max() - b['win']:.3f}, "
                  f"{(gt.win.max() / b['win'] - 1):+.0%})")

    hdr("THE SHUFFLED-LABEL TWIN -- the pipeline's noise floor, research block only")
    r = df[(df.block == "research") & df.shuf_pf.notna()]
    for (mkt, task), g in r.groupby(["market", "task"], sort=False):
        print(f"   {mkt:<5} trained on {task:<4}  shuffled PF >= real PF in "
              f"{int((g.shuf_pf >= g.pf).sum()):>2} of {len(g)} cells "
              f"({(g.shuf_pf >= g.pf).mean():.0%})   "
              f"mean real {g.pf.mean():.3f} vs shuffled {g.shuf_pf.mean():.3f}")
    print(f"   POOLED: shuffled beats real in {int((r.shuf_pf >= r.pf).sum())} of {len(r)} "
          f"({(r.shuf_pf >= r.pf).mean():.0%}).  Chance is 50% only if the model has no edge; "
          "above 50% means\n           the noise floor is HIGHER than the signal, which is what a "
          "selection artifact looks like.")

    hdr("THE TAIL -- p90 of R in the selected set.  V28 found this, not AUC, decides the outcome.")
    for (mkt, blk), g in df.groupby(["market", "block"], sort=False):
        b = base.get((mkt, blk), {})
        if "p90" not in b:
            b = dict(p90=np.nan)
        for task, gt in g.groupby("task", sort=False):
            tight = gt[gt.keep <= 25]
            print(f"   {mkt:<5} {blk:<9} trained on {task:<4}  p90 at 75% keep "
                  f"{gt[gt.keep == 75].p90.mean():>+6.3f}  ->  at <=25% keep "
                  f"{tight.p90.mean():>+6.3f}   "
                  f"win rate {gt[gt.keep == 75].win.mean():.3f} -> {tight.win.mean():.3f}")

    hdr("THE WIN-RATE ASK, ANSWERED DIRECTLY:  does a 5-15% relative lift arrive, and what does "
        "it cost?")
    for (mkt, blk), g in df.groupby(["market", "block"], sort=False):
        b = base[(mkt, blk)]
        w = g[g.task == "win"]
        best = w.loc[w.win.idxmax()]
        print(f"   {mkt:<5} {blk:<9} best win-rate cell: {best.fset} {best.model} keep "
              f"{best.keep}%  win {best.win:.3f} vs {b['win']:.3f} "
              f"= {(best.win / b['win'] - 1):+.0%} relative  (control p {best.p_win:.3f})")
        print(f"   {'':<5} {'':<9}   and it costs: PF {best.pf:.3f} vs {b['pf']:.3f}"
              f"   Sharpe {best.sharpe:+.2f} vs {b['sharpe']:+.2f}"
              f"   p90 R {best.p90:+.3f}   control p(PF) {best.p_pf:.3f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/ib/v32_ml_output.txt")
