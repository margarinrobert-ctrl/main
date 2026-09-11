"""Does a rule that survives on one timeframe survive on the others?

Each timeframe is a separate 16.2-million-strategy sweep over the SAME 115 conditions and the
SAME 32 exit geometries, so a rule has a directly comparable result on each. That makes a
question available that a single-timeframe search cannot ask: is this rule a property of the
market, or of the bar size it happened to be measured on?
"""
from __future__ import annotations

import glob
import re
import sys

import numpy as np

sys.path.insert(0, "research")
from alpha_factory2 import EXITS

NV = 2 * len(EXITS)
W = 100


def load(tf):
    Z = np.load(f"results/alpha/af2_{tf}m.npz", allow_pickle=True)
    return dict(rn=Z["res_net"], rN=Z["res_n"], ln=Z["lok_net"], lN=Z["lok_n"],
                combos=Z["combos"], names=[str(x) for x in Z["names"]])


def main():
    tfs = sorted(int(re.search(r"af2_(\d+)m", p).group(1))
                 for p in glob.glob("results/alpha/af2_*m.npz"))
    print(f"timeframes available: {', '.join(str(t)+'m' for t in tfs)}\n")
    Ds = {t: load(t) for t in tfs}
    ref = Ds[tfs[0]]
    names, combos = ref["names"], ref["combos"]
    nrule = len(combos)

    print("=" * W)
    print("1. PER TIMEFRAME — the same search, run four times")
    print("=" * W)
    print(f"   {'bars':<8}{'scored':>12}{'median locked':>16}{'best research':>16}"
          f"{'-> LOCKED':>13}{'top-1000 long':>16}")
    best = {}
    for t in tfs:
        D = Ds[t]
        ok = (D["rN"] >= 30) & (D["lN"] >= 15) & ((D["rN"] + D["lN"]) >= 60)
        idx = np.where(ok)[0]
        o_ = idx[np.argsort(-D["rn"][idx])]
        side = np.where((np.arange(len(D["rn"])) % NV) < len(EXITS), 1, -1)
        best[t] = o_[0]
        print(f"   {str(t)+'m':<8}{ok.sum():>12,}{np.median(D['ln'][idx]):>16,.0f}"
              f"{D['rn'][o_[0]]:>16,.0f}{D['ln'][o_[0]]:>13,.0f}"
              f"{100*(side[o_[:1000]] == 1).mean():>15.0f}%")

    print()
    print("=" * W)
    print("2. DOES A RULE TRANSFER ACROSS BAR SIZES?")
    print("=" * W)
    print("   For each rule and geometry, its research P&L is known on every timeframe. If the")
    print("   edge is a property of the market, the ranks should agree. If it is a property of")
    print("   the bar size, they should not.\n")
    print(f"   {'pair':<16}{'rank correlation of research P&L':>36}")
    for i in range(len(tfs)):
        for j in range(i + 1, len(tfs)):
            a, b = Ds[tfs[i]], Ds[tfs[j]]
            ok = ((a["rN"] >= 30) & (a["lN"] >= 15) & (b["rN"] >= 30) & (b["lN"] >= 15))
            ii = np.where(ok)[0]
            if len(ii) < 1000:
                continue
            s = np.random.default_rng(0).choice(ii, size=min(300000, len(ii)), replace=False)
            r1 = np.argsort(np.argsort(a["rn"][s])); r2 = np.argsort(np.argsort(b["rn"][s]))
            rc = np.corrcoef(r1, r2)[0, 1]
            print(f"   {f'{tfs[i]}m vs {tfs[j]}m':<16}{rc:>+36.3f}")

    print()
    print("=" * W)
    print("3. THE CROSS-TIMEFRAME FILTER — profitable on RESEARCH on every timeframe, both ways")
    print("=" * W)
    L = (np.arange(nrule)[:, None] * NV + np.arange(len(EXITS))[None, :]).ravel()
    S = L + len(EXITS)
    keep = np.ones(len(L), bool)
    for t in tfs:
        D = Ds[t]
        ok = (D["rN"] >= 20) & (D["lN"] >= 10)
        keep &= ok[L] & ok[S] & (D["rn"][L] > 0) & (D["rn"][S] > 0)
    print(f"   {int(keep.sum()):,} rule/geometry pairs are profitable in BOTH directions on the")
    print(f"   research block of ALL {len(tfs)} timeframes, out of {len(L):,} pairs.\n")
    if keep.sum():
        ki = np.where(keep)[0]
        sc = np.minimum.reduce([Ds[t]["rn"][L[ki]] + Ds[t]["rn"][S[ki]] for t in tfs])
        order = ki[np.argsort(-sc)]
        print("   READ ONCE on the locked block of every timeframe:")
        hdr = f"   {'rule':<62}" + "".join(f"{str(t)+'m':>11}" for t in tfs)
        print(hdr)
        shown = 0
        seen = set()
        for k in order:
            r = tuple(x for x in combos[L[k] // NV] if x >= 0)
            if r in seen:
                continue
            seen.add(r)
            txt = " AND ".join(names[i] for i in r)
            am, tp, fl = EXITS[L[k] % len(EXITS)]
            vals = "".join(f"{Ds[t]['ln'][L[k]] + Ds[t]['ln'][S[k]]:>11,.0f}" for t in tfs)
            print(f"   {txt[:60]:<62}{vals}")
            print(f"      stop {am}xATR, target {tp}R"
                  + (f", flat {fl//60}:00" if fl else ", no time stop"))
            shown += 1
            if shown >= 10:
                break
        pos = np.array([[Ds[t]["ln"][L[k]] + Ds[t]["ln"][S[k]] > 0 for t in tfs] for k in ki])
        print(f"\n   of the {len(ki):,} that pass on all timeframes' research blocks,")
        print(f"   {int(pos.all(axis=1).sum()):,} ({100*pos.all(axis=1).mean():.1f}%) are still "
              f"positive on all {len(tfs)} locked blocks.")
        print(f"   chance if the {len(tfs)} timeframes were independent: "
              f"{100*np.prod(pos.mean(axis=0)):.1f}%")


if __name__ == "__main__":
    main()
