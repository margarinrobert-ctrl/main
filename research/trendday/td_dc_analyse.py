"""Read the 371,520-cell Donchian sweep against section 12's frontier, at 3x / 5x / 8x."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import td_sweep2 as S2  # noqa: E402
import td_analyse as A  # noqa: E402

OUT = "results/trendday"
LONG = ["NQ", "US100", "US30"]
ALL = LONG + ["US30_ISO"]
KEY = list(S2.GRID)
BASE_PF = {3.0: 1.41, 5.0: 1.28, 8.0: 1.20}     # section 12, no Donchian


def join():
    g = {m: pd.read_csv(f"{OUT}/dc_{m}.csv") for m in ALL}
    for m in g:
        g[m]["cell"] = list(map(tuple, g[m][KEY].to_numpy()))
    old = A.load()
    need = {}
    for m in ALL:
        b0 = [c[:-2] for c in old[m].columns if c.endswith("_n")][0]
        need[m] = A.shipped_row(old[m])[f"{b0}_n"]
    j = g["NQ"][KEY].copy()
    j["cell"] = g["NQ"]["cell"]
    j = j.set_index("cell")
    for m in ALL:
        s = g[m].set_index("cell")
        b0 = [c[:-2] for c in g[m].columns if c.endswith("_n")][0]
        j[f"{m}_n"] = s[f"{b0}_n"]
        j[f"{m}_pf"] = s[f"{b0}_pf"]
        j[f"{m}_mean"] = s[f"{b0}_mean"]
    j["stop_share"] = g["US100"].set_index("cell")["stop_share"]
    j = j.dropna(subset=[f"{m}_pf" for m in LONG])
    j["min_pf"] = j[[f"{m}_pf" for m in LONG]].min(axis=1)
    j["min_mult"] = np.min([j[f"{m}_n"] / need[m] for m in LONG], axis=0)
    return g, j, need


def main():
    g, j, need = join()
    print("=" * 108)
    print("A DONCHIAN CHANNEL ON THE TREND-DAY FAMILY -- 371,520 cells, at 3x / 5x / 8x entries")
    print("=" * 108)
    print("  Three uses, all causal, all at session scale: a GATE (the qualifying session closed at")
    print("  the extreme of its own recent channel), a STOP (the fade is cut when price breaks the")
    print("  channel against it), and an alternative TARGET (the channel midpoint).")
    print(f"  {len(j):,} cells scored on the research block of all three long feeds.\n")

    print("-" * 108 + "\n1. THE FRONTIER, WITH THE DONCHIAN, AGAINST SECTION 12's WITHOUT IT\n" + "-" * 108)
    print(f"  {'entries >=':>11}{'cells':>10}{'best min PF':>13}{'was (no DC)':>13}{'change':>9}   "
          "the cell")
    for mult in (1.0, 2.0, 3.0, 5.0, 8.0):
        sub = j[j["min_mult"] >= mult]
        if len(sub) == 0:
            print(f"  {mult:>10.1f}x{0:>10}")
            continue
        b = sub.iloc[int(sub["min_pf"].to_numpy().argmax())]
        was = BASE_PF.get(mult)
        cell = "  ".join(f"{k}={b[k]:g}" for k in
                         ("ema", "trend_pct", "max_touch", "target_frac", "dc_len", "dc_gate",
                          "dc_stop", "tgt_mode") if b[k] != 0 or k in ("dc_len", "dc_stop"))
        wtxt = f"{was:>13.2f}" if was else f"{'-':>13}"
        ctxt = f"{b['min_pf'] - was:>+9.2f}" if was else f"{'-':>9}"
        print(f"  {mult:>10.1f}x{len(sub):>10,}{b['min_pf']:>13.2f}{wtxt}{ctxt}   {cell}")

    print("\n" + "-" * 108 + "\n2. DOES THE DONCHIAN DO ANYTHING? the same grid with it OFF\n" + "-" * 108)
    off = j[j["dc_len"] == 0]
    on = j[j["dc_len"] > 0]
    print(f"  {'entries >=':>11}{'DC off: cells / best min PF':>32}{'DC on: cells / best min PF':>32}"
          f"{'gain':>8}")
    for mult in (1.0, 2.0, 3.0, 5.0, 8.0):
        a = off[off["min_mult"] >= mult]
        b = on[on["min_mult"] >= mult]
        pa = a["min_pf"].max() if len(a) else np.nan
        pb = b["min_pf"].max() if len(b) else np.nan
        print(f"  {mult:>10.1f}x{len(a):>16,} / {pa:>11.2f}{len(b):>16,} / {pb:>11.2f}"
              f"{pb - pa:>+8.2f}")
    print("\n  The Donchian axes multiply the cell count by 129, so the DC-on column is the maximum")
    print("  of 129x as many draws. A gain smaller than that inflation is not a finding.")

    print("\n" + "-" * 108 + "\n3. EACH DONCHIAN USE ON ITS OWN, at the frontier rungs\n" + "-" * 108)
    for mult in (3.0, 5.0, 8.0):
        sub = j[j["min_mult"] >= mult]
        if len(sub) == 0:
            continue
        base = sub[(sub.dc_len == 0)]["min_pf"].max()
        gate = sub[(sub.dc_len > 0) & (sub.dc_gate > 0) & (sub.dc_stop == 0) & (sub.tgt_mode == 0)]
        stop = sub[(sub.dc_len > 0) & (sub.dc_gate == 0) & (sub.dc_stop > 0) & (sub.tgt_mode == 0)]
        tgt = sub[(sub.dc_len > 0) & (sub.dc_gate == 0) & (sub.dc_stop == 0) & (sub.tgt_mode == 1)]
        allthree = sub[(sub.dc_len > 0) & (sub.dc_gate > 0) & (sub.dc_stop > 0)]
        print(f"  {mult:.0f}x entries: no Donchian {base:.2f} | GATE only "
              f"{gate['min_pf'].max() if len(gate) else np.nan:.2f} | STOP only "
              f"{stop['min_pf'].max() if len(stop) else np.nan:.2f} | MID target only "
              f"{tgt['min_pf'].max() if len(tgt) else np.nan:.2f} | gate+stop "
              f"{allthree['min_pf'].max() if len(allthree) else np.nan:.2f}")

    print("\n" + "-" * 108 + "\n4. WHAT THE TOP 1,000 AGREE ON (by the worst feed, all multiples)\n"
          + "-" * 108)
    top = j.nlargest(1000, "min_pf")
    for k in KEY:
        pop = j[k].value_counts(normalize=True).sort_index()
        vc = top[k].value_counts(normalize=True)
        print(f"  {k:<12} " + "  ".join(f"{v:g}:{100*vc.get(v, 0):.0f}%" for v in pop.index))
    print(f"  median entry multiple of the top 1,000: {top['min_mult'].median():.2f}x")

    print("\n" + "-" * 108 + "\n5. COHERENCE -- every immediate neighbour on every axis must hold too\n"
          + "-" * 108)
    lut = {c: (pf, mm) for c, pf, mm in zip(j.index, j["min_pf"], j["min_mult"])}
    order = {k: list(S2.GRID[k]) for k in KEY}

    def worst_nb(c):
        w = lut[c][0]
        for ai, k in enumerate(KEY):
            vals = order[k]
            i = vals.index(c[ai]) if c[ai] in vals else -1
            if i < 0:
                continue
            for d in (-1, 1):
                jx = i + d
                if jx < 0 or jx >= len(vals):
                    continue
                nb = list(c); nb[ai] = vals[jx]
                v = lut.get(tuple(nb))
                w = min(w, v[0] if v is not None else 0.0)
        return w

    print(f"  {'entries >=':>11}{'cells':>10}{'best WORST-neighbour PF':>26}   the cell")
    finals = {}
    for mult in (3.0, 5.0, 8.0):
        sub = [c for c, (pf, mm) in lut.items() if mm >= mult]
        if not sub:
            continue
        best, bw = None, -1.0
        for c in sub:
            w = worst_nb(c)
            if w > bw:
                bw, best = w, c
        finals[mult] = (best, bw)
        print(f"  {mult:>10.1f}x{len(sub):>10,}{bw:>26.2f}   "
              + "  ".join(f"{k}={v:g}" for k, v in zip(KEY, best)
                          if v != 0 or k in ("dc_len", "dc_stop")))
    print("\n  For comparison, section 12's best cells had worst-neighbour PF 1.18 at 3x and 1.07 at 5x.")

    print("\n" + "-" * 108 + "\n6. ONE READ OF THE RESERVED BLOCKS\n" + "-" * 108)
    print(f"  MULTIPLICITY: {len(j):,} cells scored on research, on top of section 12's 127,008.")
    print(f"  Bonferroni over {len(j):,} is {0.05/len(j):.2e}. The reserved read below is a single")
    print("  read and is reported for shape, not for significance.\n")
    cands = []
    for mult in (3.0, 5.0, 8.0):
        sub = j[j["min_mult"] >= mult]
        if len(sub):
            cands.append((f"best worst-feed PF at {mult:.0f}x entries",
                          sub.iloc[int(sub["min_pf"].to_numpy().argmax())].name))
        if mult in finals:
            cands.append((f"most COHERENT cell at {mult:.0f}x entries", finals[mult][0]))
    seen = set()
    for label, cell in cands:
        if cell in seen:
            print(f"  {label}: the same cell as above\n")
            continue
        seen.add(cell)
        print(f"  {label}")
        print("    " + "  ".join(f"{k}={v:g}" for k, v in zip(KEY, cell)))
        for m in ALL:
            s = g[m].set_index("cell")
            if cell not in s.index:
                continue
            r = s.loc[[cell]].iloc[0]
            bl = [c[:-2] for c in g[m].columns if c.endswith("_n")]
            parts = [f"{b[:4]} n {int(r[f'{b}_n']):>4} PF {r[f'{b}_pf']:5.2f} "
                     f"mean {r[f'{b}_mean']:+7.1f}" for b in bl]
            print(f"    {m:<9} " + " | ".join(parts))
        print(f"    stop exits {100*g['US100'].set_index('cell').loc[[cell]].iloc[0]['stop_share']:.0f}%"
              f", clock exits {100*g['US100'].set_index('cell').loc[[cell]].iloc[0]['clock_share']:.0f}% "
              "(US100)\n")


if __name__ == "__main__":
    main()
