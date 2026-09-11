"""V60 part three: is the leading configuration a PLATEAU or a spike, and does it hold in time?

`CLAUDE.md`: "A plateau is necessary and not sufficient." V16's best cell was rejected pre-holdout
for having no neighbourhood; the rule carried forward instead HAD a clean five-rung plateau and
still failed. So this module is a REJECTION test, not a confirmation one -- a spike is fatal, a
plateau is merely not fatal.

Three reads:

  1. THE LADDER. Hold the leader fixed and sweep ONE axis at a time. A real parameter is a smooth
     decay away from its peak; an artifact is a spike with negative neighbours.
  2. THE BOX. Every cell within one rung of the leader on EVERY axis at once, scored on both
     blocks. What is reported is the SHARE of the box that stays profitable -- reading the box's
     best cell would just repeat the selection.
  3. WALK-FORWARD IN TIME on the research block, five contiguous folds. `CLAUDE.md`: a
     walk-forward inside the discovery block is CONTAMINATED, because the thresholds were chosen
     on the whole span. It is printed to show whether the result is carried by one fold, which is
     a different question from whether it generalises -- `STUDY_V13`'s short side was one bear
     market and the fold table is what showed it.

A NOTE ON THE LOCKED COLUMN. `v60verdict.py` already read the locked block once, for the top
twelve. The ladder and the box read it for their neighbourhoods too, and the number of cells that
adds is printed. Those cells were never candidates -- nothing is selected here -- but the read is
declared rather than hidden.

Usage: python3 research/v60/v60robust.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "v38"))
sys.path.insert(0, os.path.join(HERE, "..", "v39"))

import v60core as V             # noqa: E402
import v38grid as G             # noqa: E402
import v39mc as MC              # noqa: E402
from run_v60 import MARKETS      # noqa: E402
from v60judge import load, MIN_N  # noqa: E402

# The leader, as ranked on RESEARCH by the worse of three markets' Sharpe in `v60verdict.py`.
LEAD = dict(mode="cross", ema_f=21, ema_s=62, win=40, don_e=10, gate="adx>=20",
            aroon_n=0, aroon="off")
LEAD_GEO = dict(don_x=10, stop=3.0, tp=0.0)

AXES = [("mode", V.EMA_MODE), ("ema_f", V.EMA_F), ("ema_s", V.EMA_S), ("win", V.WIN),
        ("don_e", V.DON_E), ("gate", V.GATE), ("aroon", V.AROON), ("aroon_n", V.AROON_N)]
GEO_AXES = [("don_x", V.DON_X), ("stop", V.STOP), ("tp", V.TP)]


def canon(d):
    """The key tuple exactly as `signal_keys` canonicalises it -- inert axes zeroed, so a lookup
    of a cell whose axis does nothing lands on the ONE cell that represents it."""
    md = d["mode"]
    ka = 0 if md == "off" else d["ema_f"]
    kb = 0 if md == "off" else d["ema_s"]
    kw = 0 if md != "cross" else d["win"]
    kan = 0 if d["aroon"] == "off" else (d["aroon_n"] or V.AROON_N[0])
    return (md, ka, kb, kw, d["don_e"], d["gate"], kan, d["aroon"])


def index(keys, geoms):
    ki = {k: i for i, k in enumerate(keys)}
    gj = {g: j for j, g in enumerate(geoms)}
    return ki, gj


def cell(D, d, g):
    """($/trade, PF, n) on both blocks for one configuration, per market. NaN where unscorable."""
    out = {}
    for mk in MARKETS:
        M, keys, geoms, _nr, _nl = D[mk]
        ki, gj = index(keys, geoms)
        k = canon(d)
        gk = (g["don_x"], g["stop"], g["tp"])
        if k not in ki or gk not in gj:
            out[mk] = None
            continue
        s, j = ki[k], gj[gk]
        out[mk] = tuple(
            (float(M["usd"][s, j, b]), float(M["pf"][s, j, b]), int(M["n"][s, j, b]))
            for b in (0, 1))
    return out


def ladder(D):
    print("=" * 108)
    print("7. THE LADDER -- one axis swept, everything else held at the leader")
    print("=" * 108)
    print(f"  leader: {LEAD}  {LEAD_GEO}")
    hdr = f"{'axis':<9} {'setting':<9}"
    for mk in MARKETS:
        hdr += f"{mk[:5] + ' res':>13}{mk[:5] + ' lock':>13}"
    print(hdr)
    read = 0
    for axis, vals in AXES + GEO_AXES:
        is_geo = axis in ("don_x", "stop", "tp")
        for v in vals:
            d = dict(LEAD)
            g = dict(LEAD_GEO)
            (g if is_geo else d)[axis] = v
            if not is_geo and axis == "aroon_n" and d["aroon"] == "off":
                continue                      # inert: aroon off ignores its period
            c = cell(D, d, g)
            row = f"{axis:<9} {str(v):<9}"
            for mk in MARKETS:
                if c[mk] is None:
                    row += f"{'--':>13}{'--':>13}"
                    continue
                (ur, pr, nr), (ul, pl, nl) = c[mk]
                row += (f"{ur:>+9.2f}/{nr:<3d}" if nr >= MIN_N else f"{'n<30':>13}")
                row += (f"{ul:>+9.2f}/{nl:<3d}" if nl >= MIN_N else f"{'n<30':>13}")
                read += 1
            mark = "  <-- leader" if str(v) == str((g if is_geo else d)[axis]) and (
                (is_geo and v == LEAD_GEO[axis]) or (not is_geo and v == LEAD[axis])) else ""
            print(row + mark)
        print("   " + "-" * 100)
    print(f"  locked cells read by the ladder: {read}")


def box(D):
    """Every combination within one rung of the leader on every axis at once."""
    print("\n" + "=" * 108)
    print("8. THE BOX -- every cell within ONE RUNG of the leader on EVERY axis simultaneously")
    print("=" * 108)

    def nb(vals, v):
        vals = list(vals)
        if v not in vals:
            return [v]
        i = vals.index(v)
        return [vals[j] for j in (i - 1, i, i + 1) if 0 <= j < len(vals)]

    from itertools import product
    grid = list(product(nb(V.EMA_F, LEAD["ema_f"]), nb(V.EMA_S, LEAD["ema_s"]),
                        nb(V.WIN, LEAD["win"]), nb(V.DON_E, LEAD["don_e"]),
                        nb(V.DON_X, LEAD_GEO["don_x"]), nb(V.STOP, LEAD_GEO["stop"]),
                        nb(V.TP, LEAD_GEO["tp"])))
    print(f"  {len(grid)} cells (ema_f x ema_s x win x don_e x don_x x stop x tp, mode/gate/aroon"
          f" held)")
    stat = {mk: [[], []] for mk in MARKETS}
    for ef, es, wn, de, dx, sn, tp in grid:
        d = dict(LEAD, ema_f=ef, ema_s=es, win=wn, don_e=de)
        g = dict(don_x=dx, stop=sn, tp=tp)
        c = cell(D, d, g)
        for mk in MARKETS:
            if c[mk] is None:
                continue
            for b in (0, 1):
                u, p, n = c[mk][b]
                if n >= MIN_N and np.isfinite(u):
                    stat[mk][b].append(u)
    print(f"  {'market':<8}{'block':<10}{'scorable':>10}{'profitable':>12}{'median $/tr':>14}"
          f"{'p25':>9}{'p75':>9}")
    for mk in MARKETS:
        for b, bn in ((0, "research"), (1, "locked")):
            a = np.array(stat[mk][b])
            if not len(a):
                print(f"  {mk:<8}{bn:<10}{'--':>10}")
                continue
            print(f"  {mk:<8}{bn:<10}{len(a):>10d}{(a > 0).mean() * 100:>11.1f}%"
                  f"{np.median(a):>+14.2f}{np.percentile(a, 25):>+9.2f}"
                  f"{np.percentile(a, 75):>+9.2f}")
    print(f"  locked cells read by the box: {sum(len(stat[mk][1]) for mk in MARKETS)}")


def walk_forward(folds=5):
    print("\n" + "=" * 108)
    print(f"9. WALK-FORWARD IN TIME, {folds} contiguous folds of the RESEARCH block")
    print("   (contaminated by construction -- the question is whether ONE fold carries it)")
    print("=" * 108)
    d, g = dict(LEAD), dict(LEAD_GEO)
    key = canon(d)
    print(f"  {'market':<8}" + "".join(f"{'fold ' + str(i + 1):>15}" for i in range(folds))
          + f"{'locked':>15}")
    for mk in MARKETS:
        P = V.prep(60, mk)
        cut = int(P["n"] * V.SPLIT)
        xb, pnl, _ = G.tensor_stop(P, g["don_x"], g["stop"], g["tp"], 0)
        m = V.signal_mask(P, key)
        row = f"  {mk:<8}"
        edges = np.linspace(0, cut, folds + 1).astype(int)
        pos = 0
        for i in range(folds):
            sig = np.flatnonzero(m[edges[i]:edges[i + 1]]).astype(np.int64) + edges[i]
            p_, _s = MC.gather(P, xb, pnl, sig)
            row += (f"{p_.mean():>+11.2f}/{len(p_):<3d}" if len(p_) >= 10
                    else f"{'n<10':>15}")
            pos += 1 if len(p_) >= 10 and p_.mean() > 0 else 0
        sig = np.flatnonzero(m[cut:]).astype(np.int64) + cut
        p_, _s = MC.gather(P, xb, pnl, sig)
        row += f"{p_.mean():>+11.2f}/{len(p_):<3d}"
        print(row + f"   {pos}/{folds} folds positive")


def main():
    D = {mk: load(mk) for mk in MARKETS}
    ladder(D)
    box(D)
    walk_forward()


if __name__ == "__main__":
    main()
