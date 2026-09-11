"""Sweep the two new signal families through this repository's standard 1R procedure.

Nothing here is new procedure. It is the same one every shipped strategy went through:

  * every condition x 18 geometries (6 stop widths x 3 flatten times) x both sides x 2 timeframes
  * scored against the base win rate of ITS OWN side and geometry, computed from the population,
    never against 50% -- costs push the real base down, a wider barrier pushes it up, and drift
    lifts longs and sinks shorts on a sample where NQ rose 89%
  * chosen on the RESEARCH block only; the locked block is read once, at the end
  * the winner then goes through the matched control, the drop-one random-filter test, the true
    1-minute execution path, costs, a stationary block bootstrap and a walk-forward

Usage: python3 research/newsignals_test.py [sam|eff|both]
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from newsignals import eff_masks, sam_masks
from oner_union import GEOS, _cut, _sim, bars, base_rate

MIN_RES, MIN_LOK = 40, 15
TFS = (15, 30)


def sweep(family="sam", verbose=True):
    rows = []
    for tf in TFS:
        d = bars(tf)
        si, cut, _ = _cut(d)
        if family == "sam":
            M = {}
            for mode in ("bar", "intrabar"):
                M.update(sam_masks(d, tf, mode=mode))
        else:
            M = eff_masks(d)
        for k in M:
            M[k] = np.asarray(M[k], bool).copy()
            M[k][:300] = False
        base = {(s, a, f): base_rate(d, s, a, f) for s in (1, -1) for a, f in GEOS}
        for name, mask in M.items():
            trig = np.flatnonzero(mask).astype(np.int64)
            if len(trig) < MIN_RES:
                continue
            for side in (1, -1):
                for am, flat in GEOS:
                    pnl, eb, _x, _w, _g = _sim(d, trig, side, am, flat)
                    r = si[eb] < cut
                    if r.sum() < MIN_RES or (~r).sum() < MIN_LOK:
                        continue
                    b = base[(side, am, flat)]
                    wr = 100.0 * float((pnl[r] > 0).mean())
                    rows.append(dict(family=family, tf=tf, cond=name, side=side, am=am, flat=flat,
                                     n_res=int(r.sum()), n_lok=int((~r).sum()),
                                     res=float(pnl[r].sum()), lok=float(pnl[~r].sum()),
                                     wr_res=wr, base=b, exc=wr - b,
                                     wr_lok=100.0 * float((pnl[~r] > 0).mean()),
                                     n=len(pnl), net=float(pnl.sum()),
                                     pf=float(pnl[pnl > 0].sum() / max(-pnl[pnl <= 0].sum(), 1e-9))))
    if verbose:
        print(f"  {family}: {len(rows):,} condition x side x geometry x timeframe combinations "
              f"with {MIN_RES}+ research and {MIN_LOK}+ locked trades")
    return rows


def pick(rows, verbose=True, top=10):
    """Research block only: positive excess over its own base, research-profitable, most trades."""
    ok = [r for r in rows if r["exc"] > 0 and r["res"] > 0]
    if verbose:
        print(f"     {len(ok):,} beat their own base rate on research and are research-profitable")
    if not ok:
        return []
    best = sorted(ok, key=lambda r: -r["exc"])
    if verbose:
        print(f"\n  {'condition':<30}{'tf':>4}{'dir':>6}{'stop':>5}{'flat':>6}{'n res':>7}"
              f"{'win%':>7}{'base':>7}{'exc':>7}{'res $':>9}")
        for r in best[:top]:
            print(f"  {r['cond'][:28]:<30}{r['tf']:>4}{'long' if r['side']==1 else 'short':>6}"
                  f"{r['am']:>5.1f}{(r['flat']//60 if r['flat'] else 0):>6}{r['n_res']:>7}"
                  f"{r['wr_res']:>7.1f}{r['base']:>7.1f}{r['exc']:>+7.1f}{r['res']:>9,.0f}")
    return best


def read_locked(best, n=5, verbose=True):
    """The locked block, once, for the top n chosen on research."""
    if verbose:
        print(f"\n  THE LOCKED BLOCK, READ ONCE, for the {n} with the largest research excess")
        print(f"  {'condition':<30}{'tf':>4}{'dir':>6}{'trades':>8}{'lok n':>7}{'lok win%':>10}"
              f"{'base':>7}{'excess':>8}{'net $':>9}{'lok $':>9}{'PF':>6}")
        for r in best[:n]:
            print(f"  {r['cond'][:28]:<30}{r['tf']:>4}{'long' if r['side']==1 else 'short':>6}"
                  f"{r['n']:>8}{r['n_lok']:>7}{r['wr_lok']:>10.1f}{r['base']:>7.1f}"
                  f"{r['wr_lok']-r['base']:>+8.1f}{r['net']:>9,.0f}{r['lok']:>9,.0f}"
                  f"{r['pf']:>6.2f}")
        held = sum(1 for r in best[:n] if r["wr_lok"] > r["base"] and r["lok"] > 0)
        print(f"\n  {held} of {n} keep a positive excess AND positive dollars on the block they "
              f"were not chosen on")
    return best[:n]


if __name__ == "__main__":
    want = sys.argv[1] if len(sys.argv) > 1 else "both"
    fams = ["sam", "eff"] if want == "both" else [want]
    out = {}
    for f in fams:
        print(f"\n{'='*100}\n{'SEMIVARIANCE ASYMMETRY (SAM)' if f=='sam' else 'EFFICIENCY FLIP (EFF)'}"
              f"\n{'='*100}")
        rows = sweep(f)
        best = pick(rows)
        out[f] = read_locked(best) if best else []
    np.save("results/newsignals/newsignals.npy", np.array(
        [r for f in out for r in out[f]], dtype=object), allow_pickle=True)
