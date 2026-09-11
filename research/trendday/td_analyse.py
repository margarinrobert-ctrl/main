"""Read the 127,008-cell sweep: grid shares first, then a research-only selection under the ask's
own gates, then ONE read of the reserved blocks with the multiplicity stated."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import td_sweep as S  # noqa: E402

OUT = "results/trendday"
LONG = ["NQ", "US100", "US30"]          # the feeds selection is allowed to see
ALL = LONG + ["US30_ISO"]
SHIPPED = dict(ema=20, bucket=15, trend_pct=75.0, max_touch=0, min_gap=0.0, target_frac=1.0,
               stop_gap=0.0, max_hold=0, flat_frac=1.0)
KEY = list(SHIPPED)
TARGET_MULT = 5.0
TARGET_PF = 2.0


def load():
    g = {m: pd.read_csv(f"{OUT}/sweep_{m}.csv") for m in ALL}
    for m in g:
        g[m]["cell"] = list(map(tuple, g[m][KEY].to_numpy()))
    return g


def shipped_row(df):
    m = np.ones(len(df), bool)
    for k, v in SHIPPED.items():
        m &= np.isclose(df[k], v) if isinstance(v, float) else (df[k] == v)
    return df[m].iloc[0]


def main():
    g = load()
    blocks = {m: [c[:-2] for c in g[m].columns if c.endswith("_n")] for m in ALL}
    print("=" * 104)
    print("A 127,008-CELL SWEEP OF THE TREND-DAY FAMILY -- can it be loosened 5x and still pay?")
    print("=" * 104)
    print("  Axes: EMA period (7) x bucket length (2) x trend ratio (7) x MAX TOUCHED BUCKETS (6)")
    print("        x minimum entry gap (4) x target fraction (3) x stop (3) x max hold (3) x flatten (2).")
    print("  'max touched buckets' generalises the EA's untouched flag: 0 is the rule, 99 is off.\n")

    print("-" * 104 + "\n1. THE SHIPPED CELL IN THIS GRID, and what 5x means\n" + "-" * 104)
    need = {}
    for m in ALL:
        r = shipped_row(g[m])
        b0 = blocks[m][0]
        need[m] = TARGET_MULT * r[f"{b0}_n"]
        print(f"  {m:<9} {b0:<11} n {int(r[f'{b0}_n']):>4}  PF {r[f'{b0}_pf']:5.2f}  "
              f"mean {r[f'{b0}_mean']:+7.1f}   ->  5x needs n >= {need[m]:.0f}")

    print("\n" + "-" * 104 + "\n2. THE SHARE OF THE GRID, before any single row\n" + "-" * 104)
    for m in ALL:
        b0 = blocks[m][0]
        ok = g[m][f"{b0}_n"] >= 20
        d = g[m][ok]
        print(f"  {m:<9} {int(ok.sum()):>6,} cells with >= 20 {b0} trades | profitable "
              f"{(d[f'{b0}_net'] > 0).mean():.0%} | median PF {d[f'{b0}_pf'].median():.2f} | "
              f"PF >= 2.0 {(d[f'{b0}_pf'] >= 2).mean():.1%} | n >= 5x {(d[f'{b0}_n'] >= need[m]).mean():.1%}"
              f" | BOTH {((d[f'{b0}_pf'] >= 2) & (d[f'{b0}_n'] >= need[m])).mean():.2%}")

    print("\n" + "-" * 104 + "\n3. THE ASK, ON RESEARCH ONLY, ON ALL THREE LONG FEEDS AT ONCE\n" + "-" * 104)
    base = g["NQ"][KEY].copy()
    base["cell"] = g["NQ"]["cell"]
    j = base.set_index("cell")
    for m in ALL:
        b0 = blocks[m][0]
        s = g[m].set_index("cell")
        j[f"{m}_n"] = s[f"{b0}_n"]
        j[f"{m}_pf"] = s[f"{b0}_pf"]
        j[f"{m}_mean"] = s[f"{b0}_mean"]
    j = j.dropna(subset=[f"{m}_pf" for m in LONG])
    gate_n = np.ones(len(j), bool)
    gate_pf = np.ones(len(j), bool)
    for m in LONG:
        gate_n &= j[f"{m}_n"] >= need[m]
        gate_pf &= j[f"{m}_pf"] >= TARGET_PF
    print(f"  cells scored on all three long feeds:            {len(j):,}")
    print(f"  ... reaching 5x entries on all three:            {int(gate_n.sum()):,}")
    print(f"  ... reaching PF 2.0 on all three:                {int(gate_pf.sum()):,}")
    print(f"  ... reaching BOTH on all three:                  {int((gate_n & gate_pf).sum()):,}")
    for pf_t in (1.9, 1.75, 1.5, 1.3, 1.2, 1.1, 1.0):
        gp = np.ones(len(j), bool)
        for m in LONG:
            gp &= j[f"{m}_pf"] >= pf_t
        print(f"      5x entries and PF >= {pf_t:<4} on all three:      {int((gate_n & gp).sum()):,}")
    for mult in (4.0, 3.0, 2.0):
        gn = np.ones(len(j), bool)
        for m in LONG:
            gn &= j[f"{m}_n"] >= mult / TARGET_MULT * need[m]
        gp = np.ones(len(j), bool)
        for m in LONG:
            gp &= j[f"{m}_pf"] >= TARGET_PF
        print(f"      {mult:.0f}x entries and PF >= 2.0 on all three:      {int((gn & gp).sum()):,}")

    print("\n" + "-" * 104 + "\n4. THE FRONTIER -- the best PF available at each entry multiple\n"
          + "-" * 104)
    print("  Scored by the WORST of the three long feeds, so a cell must work everywhere.")
    j["min_pf"] = j[[f"{m}_pf" for m in LONG]].min(axis=1)
    j["min_mult"] = np.min([j[f"{m}_n"] / (need[m] / TARGET_MULT) for m in LONG], axis=0)
    print(f"  {'entries >=':>11}{'cells':>9}{'best min PF':>13}{'the cell that achieves it':>46}")
    for mult in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0):
        sub = j[j["min_mult"] >= mult]
        if len(sub) == 0:
            print(f"  {mult:>10.1f}x{0:>9}")
            continue
        b = sub.iloc[int(sub["min_pf"].to_numpy().argmax())]
        cell = "  ".join(f"{k}={b[k]:g}" for k in KEY if k not in ("bucket", "flat_frac"))
        print(f"  {mult:>10.1f}x{len(sub):>9,}{b['min_pf']:>13.2f}   {cell}")
    print("\n  The same frontier as PER-FEED profit factors, so a single feed cannot hide behind the "
          "minimum:")
    print(f"  {'entries >=':>11}   " + "".join(f"{m:>10}" for m in LONG) + f"{'  n (NQ/US100/US30)':>26}")
    for mult in (1.0, 2.0, 3.0, 5.0):
        sub = j[j["min_mult"] >= mult]
        if len(sub) == 0:
            continue
        b = sub.iloc[int(sub["min_pf"].to_numpy().argmax())]
        print(f"  {mult:>10.1f}x   " + "".join(f"{b[f'{m}_pf']:>10.2f}" for m in LONG)
              + f"   {int(b['NQ_n'])}/{int(b['US100_n'])}/{int(b['US30_n'])}")

    print("\n" + "-" * 104 + "\n5. WHAT THE TOP OF THE RANKING AGREES ON (top 1,000 by the worst feed)\n"
          + "-" * 104)
    top = j.nlargest(1000, "min_pf")
    for k in KEY:
        vc = top[k].value_counts(normalize=True).sort_index()
        pop = j[k].value_counts(normalize=True).sort_index()
        s = "  ".join(f"{v:g}:{100*vc.get(v, 0):.0f}%" for v in pop.index)
        print(f"  {k:<12} {s}")
    print(f"  the top 1,000's median entry multiple is {top['min_mult'].median():.2f}x and its "
          f"median worst-feed PF is {top['min_pf'].median():.2f}")

    print("\n" + "-" * 104 + "\n6. ONE READ OF THE RESERVED BLOCKS\n" + "-" * 104)
    cands = []
    sub5 = j[(j["min_mult"] >= 5.0)]
    if len(sub5):
        cands.append(("best worst-feed PF at 5x entries", sub5.iloc[int(sub5["min_pf"].to_numpy().argmax())]))
    sub3 = j[(j["min_mult"] >= 3.0)]
    if len(sub3):
        cands.append(("best worst-feed PF at 3x entries", sub3.iloc[int(sub3["min_pf"].to_numpy().argmax())]))
    sub2 = j[(j["min_mult"] >= 2.0)]
    if len(sub2):
        cands.append(("best worst-feed PF at 2x entries", sub2.iloc[int(sub2["min_pf"].to_numpy().argmax())]))
    cands.append(("the shipped cell", j.loc[[tuple(SHIPPED[k] for k in KEY)]].iloc[0]))
    n_tested = len(j)
    print(f"  MULTIPLICITY: {n_tested:,} cells were scored on research and the reserved blocks are "
          f"read ONCE, below.\n  A Bonferroni threshold over {n_tested:,} tests is 0.05/{n_tested:,} "
          f"= {0.05/n_tested:.2e}. Nothing here approaches that;\n  the only defensible reading is "
          "whether the RANKING transfers at all.\n")
    for label, row in cands:
        cell = tuple(row[k] for k in KEY)
        print(f"  {label}")
        print("    " + "  ".join(f"{k}={row[k]:g}" for k in KEY))
        for m in ALL:
            s = g[m].set_index("cell")
            if cell not in s.index:
                continue
            r = s.loc[[cell]].iloc[0]
            parts = []
            for b in blocks[m]:
                parts.append(f"{b[:4]} n {int(r[f'{b}_n']):>4} PF {r[f'{b}_pf']:5.2f} "
                             f"mean {r[f'{b}_mean']:+7.1f}")
            print(f"    {m:<9} " + " | ".join(parts))
        print()

    print("-" * 104 + "\n7. DOES THE RANKING TRANSFER AT ALL?\n" + "-" * 104)
    for m in ALL:
        bl = blocks[m]
        if len(bl) < 2:
            continue
        s = g[m]
        ok = s[f"{bl[0]}_n"] >= 20
        d = s[ok]
        for later in bl[1:]:
            x, y = d[f"{bl[0]}_mean"], d[f"{later}_mean"]
            print(f"  {m:<9} {bl[0]} -> {later:<11} Spearman {x.corr(y, method='spearman'):+.3f}  "
                  f"Pearson {x.corr(y):+.3f}   (n {len(d):,} cells)")
    print("\n  top-decile transfer, by the first block's mean:")
    for m in ALL:
        bl = blocks[m]
        if len(bl) < 2:
            continue
        s = g[m]
        d = s[s[f"{bl[0]}_n"] >= 20]
        top = d.nlargest(max(10, len(d) // 10), f"{bl[0]}_mean")
        line = f"  {m:<9}"
        for b in bl:
            line += (f" | {b[:4]} top-decile mean {top[f'{b}_mean'].mean():+7.1f} vs population "
                     f"{d[f'{b}_mean'].mean():+7.1f}")
        print(line)




def coherent():
    """Cells whose IMMEDIATE NEIGHBOURS on every axis also work, on research, on all three feeds.

    `STUDY_V16_MOMENTUM` rejected its best cell pre-holdout for having no neighbourhood, and the
    branch's rule is that a plateau is necessary though not sufficient. A cell picked from 127,008
    that sits on a spike is the maximum of 127,008 draws and nothing else."""
    g = load()
    j = None
    for m in ALL:
        s = g[m].set_index("cell")
        b0 = [c[:-2] for c in g[m].columns if c.endswith("_n")][0]
        if j is None:
            j = g["NQ"][KEY].copy()
            j["cell"] = g["NQ"]["cell"]
            j = j.set_index("cell")
        j[f"{m}_n"] = s[f"{b0}_n"]
        j[f"{m}_pf"] = s[f"{b0}_pf"]
    j = j.dropna(subset=[f"{m}_pf" for m in LONG])
    need = {}
    for m in ALL:
        need[m] = shipped_row(g[m])[[c for c in g[m].columns if c.endswith("_n")][0]]
    j["min_pf"] = j[[f"{m}_pf" for m in LONG]].min(axis=1)
    j["min_mult"] = np.min([j[f"{m}_n"] / need[m] for m in LONG], axis=0)

    lut = {c: (pf, mm) for c, pf, mm in zip(j.index, j["min_pf"], j["min_mult"])}
    order = {k: list(S.GRID[k]) for k in KEY}
    print("\n" + "=" * 104)
    print("8. COHERENCE -- cells whose IMMEDIATE NEIGHBOURS on EVERY axis also hold")
    print("=" * 104)
    print("  For each cell, every axis is moved one rung up and one rung down (where a rung exists)")
    print("  and the WORST-FEED research profit factor of every neighbour must also clear the floor.\n")
    for mult, floor in ((2.0, 1.30), (2.0, 1.40), (2.0, 1.50), (3.0, 1.20), (3.0, 1.30),
                        (5.0, 1.10), (5.0, 1.20)):
        cands = []
        for c, (pf, mm) in lut.items():
            if mm < mult or pf < floor:
                continue
            ok = True
            worst = pf
            for ai, k in enumerate(KEY):
                vals = order[k]
                i = vals.index(c[ai]) if c[ai] in vals else -1
                if i < 0:
                    continue
                for d in (-1, 1):
                    jx = i + d
                    if jx < 0 or jx >= len(vals):
                        continue
                    nb = list(c)
                    nb[ai] = vals[jx]
                    v = lut.get(tuple(nb))
                    if v is None or v[0] < floor:
                        ok = False
                        break
                    worst = min(worst, v[0])
                if not ok:
                    break
            if ok:
                cands.append((worst, pf, mm, c))
        cands.sort(reverse=True)
        print(f"  >= {mult:.0f}x entries, every neighbour's worst-feed PF >= {floor:.2f}: "
              f"{len(cands):,} cells")
        for worst, pf, mm, c in cands[:3]:
            print("      " + "  ".join(f"{k}={v:g}" for k, v in zip(KEY, c))
                  + f"   -> own min PF {pf:.2f}, WORST neighbour {worst:.2f}, {mm:.1f}x entries")
    return lut, j


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "coherent":
    coherent()
