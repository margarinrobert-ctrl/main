"""US30 gap fill, fourth step: probability of backtest overfitting, and sizing scored on MAR.

    1. PBO (CSCV, Bailey et al.). The 72-cell family (gap 0.3/0.5/0.75/1.0 ATR x stop 0.75/1.0/
       1.5 x flat 11:00/12:00/13:00 x outside-prior-range filter on/off) on the RESEARCH block:
       daily P&L per cell, 12 contiguous groups, every choice of 6 train groups (924 splits). In
       each split the train-best cell (by Sharpe of daily P&L) is ranked out of sample among all
       72; the logit of that rank is recorded. PBO = share of splits where the winner ranks below
       the median out of sample. Above 0.5 means a better in-sample number is bad news.

    2. SIZING. The gap is the unit of risk and ranges from 25 to 500+ points, so one contract
       risks very different dollars on different days. Dispersion check first (CV of per-trade
       dollar risk); if > 0.30, one pre-registered scheme -- VAPS, lots = 1% of $50,000 / stop
       distance in dollars, in MYM ($0.50/pt) so lots are whole numbers, capped at 20 -- against
       fixed lots, ranked on MAR (net / max drawdown) on research, read once on locked.

    python3 research/us30_gap4.py
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd

import us30_orb as U
import us30_orb2 as M2
import us30_gap2 as G2
import us30_gap3 as G3
from us30_orb import load, sessions, split_days, metrics

PT_MYM = 0.5


def family(d, F):
    cells = {}
    for thr in (0.3, 0.5, 0.75, 1.0):
        for stop in (0.75, 1.0, 1.5):
            for flat in (660, 720, 780):
                b = G2.gap_trades(d, F, thr=thr, stop=stop, flat=flat, entry="E1")
                bc = G3.conditions(d, F, b)
                cells[(thr, stop, flat, "all")] = bc
                cells[(thr, stop, flat, "outside")] = bc[bc.C2_inside_prior_range == False]
    return cells


def pbo(cells, days, S=12):
    # daily P&L matrix: sessions x cells, research only
    idx = {dd: i for i, dd in enumerate(days)}
    M = np.zeros((len(days), len(cells)))
    names = list(cells)
    for j, k in enumerate(names):
        df = cells[k]; df = df[df.day.isin(idx)]
        for dd, v in df.groupby("day").net.sum().items():
            M[idx[dd], j] = v
    groups = np.array_split(np.arange(len(days)), S)
    logits, ranks = [], []
    for train in itertools.combinations(range(S), S // 2):
        tr = np.concatenate([groups[g] for g in train]); te = np.concatenate([groups[g] for g in range(S) if g not in train])
        A, B = M[tr], M[te]
        def sharpe(X):
            m, s = X.mean(0), X.std(0); return np.where(s > 0, m / s, -9)
        best = int(np.argmax(sharpe(A)))
        so = sharpe(B)
        r = (so < so[best]).mean()            # relative rank of the winner out of sample, in (0,1)
        r = min(max(r, 1e-3), 1 - 1e-3)
        logits.append(math.log(r / (1 - r))); ranks.append(r)
    logits = np.array(logits)
    return dict(pbo=float((logits < 0).mean()), n_splits=len(logits), median_oos_rank=float(np.median(ranks)))


def size_vaps(df, risk_usd=500.0, cap=20):
    lots = np.floor(risk_usd / (df.sl.to_numpy(float) * PT_MYM)).clip(0, cap)
    return lots


def book(df, lots, ptv):
    pnl = df.net.to_numpy(float) * lots * ptv
    eq = np.cumsum(pnl); dd = -(eq - np.maximum.accumulate(eq)).min()
    return dict(net=pnl.sum(), maxdd=dd, mar=(pnl.sum() / dd if dd > 0 else np.inf), mean_lots=lots.mean(),
                zero_lots=100 * (lots == 0).mean(), trades=len(df))


def main():
    d = load(); F = M2.session_facts(d)
    cut = split_days(d)
    days = [dd for dd in sessions(d, 540) if dd < cut]
    print("== 1. PROBABILITY OF BACKTEST OVERFITTING, research block, 72 cells, 12 groups ==")
    cells = family(d, F)
    r = pbo(cells, days)
    print(f"  splits {r['n_splits']}  PBO {r['pbo']:.3f}  median OOS rank of the in-sample winner {r['median_oos_rank']:.2f} (0.5 = no information)")
    # also the unfiltered 36-cell family alone, and the filtered 36 alone
    for tag in ("all", "outside"):
        sub = {k: v for k, v in cells.items() if k[3] == tag}
        rr = pbo(sub, days)
        print(f"  {tag:<8} 36 cells: PBO {rr['pbo']:.3f}  median OOS rank {rr['median_oos_rank']:.2f}")

    print("\n== 2. SIZING on the shipped rule (gap 0.5 ATR, stop 0.75, flat 12:00, outside prior range) ==")
    rule = cells[(0.5, 0.75, 720, "outside")]
    res, loc = rule[rule.block == "research"], rule[rule.block == "locked"]
    risk = res.sl.to_numpy(float) * PT_MYM
    print(f"  dispersion check: CV of per-trade dollar risk at 1 MYM = {risk.std() / risk.mean():.2f} (>0.30 means sizing has something to work with); "
          f"stop distance median {np.median(res.sl):.0f} pt, range {res.sl.min():.0f}-{res.sl.max():.0f}")
    schemes = {"fixed 1 MYM": lambda df: np.ones(len(df)), "fixed 5 MYM": lambda df: np.full(len(df), 5.0),
               "VAPS 1% of $50k, cap 20 MYM": lambda df: size_vaps(df)}
    print(f"  {'scheme':<30} {'block':<9} {'trades':>6} {'net $':>9} {'maxDD $':>9} {'MAR':>6} {'mean lots':>10} {'zero-lot %':>10}")
    for nm, fn in schemes.items():
        for blk, df in (("research", res), ("locked", loc)):
            b = book(df, fn(df), PT_MYM)
            print(f"  {nm:<30} {blk:<9} {b['trades']:>6} {b['net']:>9,.0f} {b['maxdd']:>9,.0f} {b['mar']:>6.2f} {b['mean_lots']:>10.1f} {b['zero_lots']:>10.0f}")
    # order-bootstrap of MAR for the two schemes on research (a compounding-free scheme is not path dependent
    # in net, only in drawdown)
    rng = np.random.default_rng(2)
    for nm in ("fixed 1 MYM", "VAPS 1% of $50k, cap 20 MYM"):
        fn = schemes[nm]; mars = []
        for _ in range(2000):
            p = rng.permutation(len(res)); df = res.iloc[p]
            mars.append(book(df, fn(df), PT_MYM)["mar"])
        print(f"  {nm:<30} research MAR over 2,000 trade orderings: median {np.median(mars):.2f}, 5th pct {np.percentile(mars, 5):.2f}")


if __name__ == "__main__":
    main()
