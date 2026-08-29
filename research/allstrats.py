"""Every shipped strategy in one place, so a new test runs on all of them and not on a favourite.

Nine legs:
  V1..V4  the four 1R versions after the threshold relaxation (docs/ib/STUDY_1R_MORE.md)
  V2L     V2's mechanism mirrored onto the long side (docs/ib/STUDY_V2_LONG.md)
  M1..M4  what the 139,740,876-combination ladder sweep returned

Each entry yields (conds, side, atr_mult, flat_min, tf, trigger bars). The trigger bars are the
authority: two of the nine use thresholds the shared condition pool has no rung for, so their
condition names are labels rather than lookups.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")

_C = {}


def _relaxed():
    from oner_anom import _parts
    from oner_more import select
    from oner_union import FAMILIES
    out = {}
    for k in FAMILIES:
        S = select(k, verbose=False)
        names, masks = _parts(FAMILIES[k], S["d"], S["p"])
        m = np.ones(len(S["d"]["c"]), bool)
        for x in masks:
            m &= x
        m[:300] = False
        out[k] = dict(conds=names, side=S["side"], am=S["am"], flat=S["flat"], tf=S["tf"],
                      trig=np.flatnonzero(m).astype(np.int64), d=S["d"], src="relaxation")
    return out


def _mirror():
    from v2_long import B_CONDS, B_GEO, TF, b_masks
    from oner_union import bars
    d = bars(TF)
    m = np.ones(len(d["c"]), bool)
    for x in b_masks(d):
        m &= x
    m[:300] = False
    return {"V2L": dict(conds=list(B_CONDS), side=1, am=B_GEO["am"], flat=B_GEO["flat"], tf=TF,
                        trig=np.flatnonzero(m).astype(np.int64), d=d, src="mirror")}


def _mega2(path="results/allstrats/phase5_mega2.npy"):
    import os
    if not os.path.exists(path):
        return {}
    from test_suite import build, use_pool
    use_pool("ladder")
    out = {}
    for i, r in enumerate(np.load(path, allow_pickle=True)):
        s = build(list(r["rule"]), side=r["side"], atr_mult=r["am"], tp_r=1.0,
                  flat_min=r["flat"], tf=r["tf"])
        out[f"M{i+1}"] = dict(conds=list(r["rule"]), side=int(r["side"]), am=float(r["am"]),
                              flat=int(r["flat"]), tf=int(r["tf"]), trig=s.trig,
                              d=s.bars["d"], src="ladder sweep")
    return out


def all_strategies():
    if "all" not in _C:
        out = {}
        out.update(_relaxed())
        out.update(_mirror())
        out.update(_mega2())
        _C["all"] = out
    return _C["all"]


if __name__ == "__main__":
    from oner_union import _cut, _sim, base_rate
    A = all_strategies()
    print(f"{len(A)} strategies\n")
    print(f"  {'':<5}{'source':<12}{'tf':>4}{'dir':>6}{'stop':>5}{'flat':>6}{'trig':>7}"
          f"{'trades':>8}{'win%':>7}{'base':>7}{'net $':>10}{'rule'}")
    for k, S in A.items():
        d = S["d"]; si, cut, _ = _cut(d)
        pnl, eb, _x, _w, _g = _sim(d, S["trig"], S["side"], S["am"], S["flat"])
        b = base_rate(d, S["side"], S["am"], S["flat"])
        print(f"  {k:<5}{S['src']:<12}{S['tf']:>4}{'long' if S['side']==1 else 'short':>6}"
              f"{S['am']:>5.1f}{(S['flat']//60 if S['flat'] else 0):>6}{len(S['trig']):>7}"
              f"{len(pnl):>8}{100*(pnl>0).mean():>7.1f}{b:>7.1f}{pnl.sum():>10,.0f}   "
              + " AND ".join(S["conds"])[:52])
