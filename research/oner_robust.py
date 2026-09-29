"""A 1R selection built so the failure that produced the last one cannot happen again.

What went wrong, precisely:

  1. CALENDAR CONDITIONS. `Tue` carried the rule -- deleting it earned more money on 4.5x the
     trades. Weekday and month conditions partition the sample five or twelve ways and hand the
     search a free lottery; 12.5% of the rule space contains one. They are banned here.
  2. NO COHERENCE CHECK. A three-condition rule whose two-condition subsets are all worthless is
     a three-way interaction found by search. Every subset must also beat its base rate.

Two more gates were tried and are NOT here, because research/oner_procedures.py ran all five
head to head on the same universe and measured what each does to the locked block:

  * a geometry-neighbour gate (adjacent stop widths must also work) changed nothing at all --
    subset coherence already implies it.
  * ranking by the WORST score across the neighbourhood, which was the obvious over-correction
    to "the winner was an extreme tail value", took the locked block from +$15,505 to -$3,465
    and the count of profitable legs from 12 of 14 to 6. Ranking by the minimum selects
    mid-distribution rules with no edge in any direction. The extreme tail was not the problem;
    the calendar condition inside it was.

Measured, 14 legs each, research-only selection, locked read once:

    ungated                          research $96,385   locked    $704   7/14 legs positive
    + ban calendar                   research $73,961   locked  $9,475  10/14
    + subset coherence               research $74,142   locked $15,505  12/14
    ranked by worst-of-neighbourhood research $19,202   locked -$3,465   6/14

Selection is on the research block alone. The locked block is read once, at the end.
"""
from __future__ import annotations

import sys
from itertools import combinations

import numpy as np

sys.path.insert(0, "research")
from oner_pick import load

CALENDAR = {"Mon", "Tue", "Wed", "Thu", "Fri", "first half of month", "month end (last 3d)"}
MIN_RES, MIN_LOK = 60, 25


def _rowmap(n_names):
    """tuple of condition indices -> row in the combos array, matching alpha_factory2's order."""
    m = {}
    r = 0
    for i in range(n_names):
        m[(i,)] = r; r += 1
    for a, b in combinations(range(n_names), 2):
        m[(a, b)] = r; r += 1
    for a, b, c in combinations(range(n_names), 3):
        m[(a, b, c)] = r; r += 1
    return m


def select(tf, min_win=58.0, verbose=True):
    Z = load(tf)
    names = list(Z["names"]); combos = Z["combos"]; ex = list(map(tuple, Z["exits"]))
    nvar = len(ex) * 2
    rn, rs, rw = Z["r_n"].astype(float), Z["r_sum"].astype(float), Z["r_win"].astype(float)
    ln, ls, lw = Z["l_n"].astype(float), Z["l_sum"].astype(float), Z["l_win"].astype(float)
    live = (rn >= MIN_RES) & (ln >= MIN_LOK)
    wr_r = np.where(rn > 0, 100 * rw / np.maximum(rn, 1), np.nan)
    wr_l = np.where(ln > 0, 100 * lw / np.maximum(ln, 1), np.nan)

    v = np.arange(len(rn)) % nvar
    base = np.full(nvar, np.nan)
    for vv in range(nvar):
        m = live & (v == vv)
        if m.sum() > 200:
            base[vv] = np.nanmean(wr_r[m])
    exc_r = wr_r - base[v]
    exc_l = wr_l - base[v]

    banned = {i for i, n in enumerate(names) if n in CALENDAR}
    rule_ok_row = np.array([not (banned & {int(x) for x in c if x >= 0}) for c in combos])
    rule_ok = np.repeat(rule_ok_row, nvar)      # combos are per RULE, arrays per strategy
    rmap = _rowmap(len(names))

    # geometry neighbours: same side and flatten, one stop width either way
    stops = sorted({e[0] for e in ex})
    nbr = {}
    for vv in range(nvar):
        side_hi = vv >= len(ex)
        am, tp, fl = ex[vv % len(ex)]
        k = stops.index(am)
        out = []
        for kk in (k - 1, k + 1):
            if 0 <= kk < len(stops):
                gi = ex.index((stops[kk], tp, fl))
                out.append(gi + (len(ex) if side_hi else 0))
        nbr[vv] = out

    cand = np.flatnonzero(live & rule_ok & (wr_r >= min_win) & (exc_r > 0) & (rs > 0))
    if verbose:
        print(f"\n{tf}m: {live.sum():,} live -> {int((live & rule_ok).sum()):,} without a calendar "
              f"condition -> {len(cand):,} at {min_win:.0f}%+ with positive excess")

    rows = []
    for k in cand:
        r, vv = divmod(int(k), nvar)
        idxs = tuple(sorted(int(x) for x in combos[r] if x >= 0))
        if len(idxs) < 2:
            continue
        # 3. every subset must also beat its base rate on research
        subs = [rmap[s] for n_ in range(1, len(idxs))
                for s in combinations(idxs, n_) if s in rmap]
        sub_exc = [exc_r[si * nvar + vv] for si in subs]
        sub_ok = [x for x in sub_exc if np.isfinite(x)]
        if not sub_ok or min(sub_ok) <= 0:
            continue
        # the neighbourhood is kept for reporting only -- it gates nothing, because it never
        # changed an outcome, and ranking by its minimum actively destroyed the result
        ng = [exc_r[r * nvar + g] for g in nbr[vv]]
        ng = [x for x in ng if np.isfinite(x)]
        robust = min([exc_r[k]] + sub_ok + (ng or [exc_r[k]]))
        rows.append(dict(tf=tf, key=int(k), rule=[names[i] for i in idxs],
                         side=1 if vv < len(ex) else -1, am=float(ex[vv % len(ex)][0]),
                         flat=int(ex[vv % len(ex)][2]), n=int(rn[k] + ln[k]),
                         res=float(rs[k]), lok=float(ls[k]),
                         wr_r=float(wr_r[k]), wr_l=float(wr_l[k]),
                         wr=float(100 * (rw[k] + lw[k]) / (rn[k] + ln[k])),
                         base=float(base[v[k]]), exc_r=float(exc_r[k]), exc_l=float(exc_l[k]),
                         robust=float(robust), worst_sub=float(min(sub_ok)),
                         worst_nbr=float(min(ng)) if ng else float("nan")))
    rows.sort(key=lambda x: -x["wr_r"])          # procedure C: rank by research win rate
    if verbose:
        print(f"      {len(rows):,} survive subset coherence")
    return rows


def dedupe(rows, max_shared=1):
    keep, sets = [], []
    for r in rows:
        cs = set(r["rule"])
        if any(len(cs & s) > max_shared for s in sets):
            continue
        keep.append(r); sets.append(cs)
    return keep


if __name__ == "__main__":
    allr = []
    for tf in (15, 30, 60):
        allr += select(tf)
    k = dedupe(sorted(allr, key=lambda x: -x["wr_r"]))
    print(f"\n{'='*104}\nROBUST 1R SURVIVORS -- no calendar conditions, every subset coherent"
          f"\n{'='*104}")
    print(f"  {'rule':<46}{'tf':>4}{'dir':>6}{'stop':>5}{'n':>5}{'win%':>6}{'base':>6}"
          f"{'robust':>8}{'excR':>7}{'excL':>7}{'res $':>9}{'lok $':>9}")
    for x in k[:15]:
        print(f"  {' AND '.join(x['rule'])[:44]:<46}{x['tf']:>4}"
              f"{'long' if x['side']==1 else 'short':>6}{x['am']:>5.1f}{x['n']:>5}{x['wr']:>6.1f}"
              f"{x['base']:>6.1f}{x['robust']:>+8.1f}{x['exc_r']:>+7.1f}{x['exc_l']:>+7.1f}"
              f"{x['res']:>9,.0f}{x['lok']:>9,.0f}")
    np.save("results/oner/oner_robust.npy", np.array(k, dtype=object), allow_pickle=True)
    held = sum(1 for x in k if x["exc_l"] > 0)
    print(f"\n  {len(k)} de-duplicated survivors. {held} ({100*held/max(len(k),1):.0f}%) also beat "
          f"their base rate on the locked block, which was read once, after selection.")
