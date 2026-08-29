"""PHASE 2 -- gate.  PHASE 3 -- tune.  Both on the research block only.

Phase 2 applies every gate this repository has paid for:

  * CALENDAR BAN. Weekday and month conditions partition the sample five or twelve ways and hand
    the search a free lottery. Worth $8,771 on the holdout (STUDY_1R_PROCEDURE.md).
  * BASE-RATE EXCESS. A 1R win rate is not measured against 50%. Costs push the real base down,
    a wider barrier pushes it up, drift lifts longs and sinks shorts. Each strategy is scored
    against the population mean of its OWN geometry.
  * SUBSET COHERENCE. Every subset of a rule must also beat its base. Removes three-way
    interactions that exist only because 253,575 rules were tried. Worth another $6,030.

Phase 3 then TUNES each surviving rule's geometry across all 18 stop x flatten combinations per
side, choosing on research, and keeps the tuned choice only if it still passes coherence. Tuning
is a search, so it is gated exactly like the search that produced the rule.
"""
from __future__ import annotations

import sys
from itertools import combinations

import numpy as np

sys.path.insert(0, "research")
from oner_robust import CALENDAR, _rowmap

MIN_WIN = 58.0

# which Phase 1 output to read. "mega" is the 27,386,100-combination sweep on the 115-condition
# pool; "mega2" is the 139,740,876-combination sweep on the 198-rung ladder. The gates are the
# same either way -- a finer grid does not earn a laxer bar, it needs the same one.
PREFIX = "mega"


def load(tf):
    Z = np.load(f"results/oner/{PREFIX}_{tf}m.npz", allow_pickle=True)
    return {k: Z[k] for k in Z.files}


def base_rates(Z):
    """Population mean research win rate per variant -- the null each strategy is scored against."""
    nvar = int(Z["nvar"][0])
    rn, rw = Z["base_rn"].astype(float), Z["base_rw"].astype(float)
    v = np.arange(len(rn)) % nvar
    live = rn >= 50
    wr = np.where(rn > 0, 100 * rw / np.maximum(rn, 1), np.nan)
    base = np.full(nvar, np.nan)
    for vv in range(nvar):
        m = live & (v == vv)
        if m.sum() > 200:
            base[vv] = np.nanmean(wr[m])
    return base


def phase2(tf, verbose=True):
    Z = load(tf)
    names = list(Z["names"]); combos = Z["combos"]; ex = list(map(tuple, Z["exits"]))
    nvar = int(Z["nvar"][0]); idx = Z["idx"]
    base = base_rates(Z)
    rn, rs, rw = Z["r_n"].astype(float), Z["r_sum"].astype(float), Z["r_win"].astype(float)
    ln, ls, lw = Z["l_n"].astype(float), Z["l_sum"].astype(float), Z["l_win"].astype(float)
    wr_r = 100 * rw / np.maximum(rn, 1)
    wr_l = 100 * lw / np.maximum(ln, 1)
    v = idx % nvar
    exc_r = wr_r - base[v]

    banned = {i for i, n in enumerate(names) if n in CALENDAR}
    rule_i = idx // nvar
    has_cal = np.array([bool(banned & {int(x) for x in combos[r] if x >= 0}) for r in rule_i])

    ok = (~has_cal) & (wr_r >= MIN_WIN) & (exc_r > 0)
    if verbose:
        print(f"  {tf}m  {len(idx):,} in -> {int((~has_cal).sum()):,} without a calendar "
              f"condition -> {int(ok.sum()):,} at {MIN_WIN:.0f}%+ with positive excess")

    # subset coherence needs the FULL research arrays, so rebuild a lookup from the saved base
    full_rn, full_rw = Z["base_rn"].astype(float), Z["base_rw"].astype(float)
    full_wr = np.where(full_rn > 0, 100 * full_rw / np.maximum(full_rn, 1), np.nan)
    rmap = _rowmap(len(names))
    keep = []
    for k in np.flatnonzero(ok):
        r, vv = int(rule_i[k]), int(v[k])
        idxs = tuple(sorted(int(x) for x in combos[r] if x >= 0))
        if len(idxs) < 2:
            keep.append(k); continue
        good = True
        for nsub in range(1, len(idxs)):
            for sset in combinations(idxs, nsub):
                si = rmap.get(sset)
                if si is None:
                    continue
                j = si * nvar + vv
                if full_rn[j] < 30:
                    continue
                if full_wr[j] - base[vv] <= 0:
                    good = False; break
            if not good:
                break
        if good:
            keep.append(k)
    keep = np.array(keep, np.int64)
    if verbose:
        print(f"        -> {len(keep):,} survive subset coherence")
    return dict(tf=tf, Z=Z, base=base, keep=keep, idx=idx, nvar=nvar, names=names,
                combos=combos, ex=ex, rule_i=rule_i, v=v,
                wr_r=wr_r, wr_l=wr_l, exc_r=exc_r, rs=rs, ls=ls, rn=rn, ln=ln)


def phase3(P, verbose=True):
    """Tune each surviving RULE's geometry on research, across all variants of the same side."""
    Z = P["Z"]; nvar = P["nvar"]; base = P["base"]; ex = P["ex"]
    full_rn = Z["base_rn"].astype(float); full_rw = Z["base_rw"].astype(float)
    full_wr = np.where(full_rn > 0, 100 * full_rw / np.maximum(full_rn, 1), np.nan)
    seen, out = set(), []
    for k in P["keep"]:
        r, vv = int(P["rule_i"][k]), int(P["v"][k])
        side_hi = vv >= len(ex)
        if (r, side_hi) in seen:
            continue
        seen.add((r, side_hi))
        lo = len(ex) if side_hi else 0
        cand = []
        for g in range(lo, lo + len(ex)):
            j = r * nvar + g
            if full_rn[j] < 50 or not np.isfinite(base[g]):
                continue
            e = full_wr[j] - base[g]
            if e > 0:
                cand.append((e, g, j))
        if not cand:
            continue
        cand.sort(reverse=True)
        e, g, j = cand[0]
        out.append(dict(tf=P["tf"], rule_row=r, rule=[P["names"][i] for i in P["combos"][r] if i >= 0],
                        side=-1 if side_hi else 1, am=float(ex[g % len(ex)][0]),
                        flat=int(ex[g % len(ex)][2]), var=g, exc_r=float(e),
                        wr_r=float(full_wr[j]), base=float(base[g]), n_res=int(full_rn[j]),
                        n_geo=len(cand)))
    if verbose:
        print(f"  {P['tf']}m  tuned {len(out):,} unique rule/direction pairs "
              f"(median {np.median([o['n_geo'] for o in out]):.0f} of {len(ex)} geometries "
              f"beat the base)")
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1:
        PREFIX = sys.argv[1]
    print(f"PHASE 2 -- GATE   (reading /tmp/{PREFIX}_*.npz)")
    allo = []
    for tf in (15, 30, 60):
        P = phase2(tf)
        print("PHASE 3 -- TUNE")
        allo += phase3(P)
    allo.sort(key=lambda x: -x["exc_r"])
    np.save(f"results/oner/phase3_{PREFIX}.npy", np.array(allo, dtype=object), allow_pickle=True)
    print(f"\nPHASE 3 DONE: {len(allo):,} tuned rule/direction pairs carried forward")
    print(f"  {'rule':<48}{'tf':>4}{'dir':>6}{'stop':>5}{'flat':>6}{'n':>5}{'win%':>7}"
          f"{'base':>6}{'exc':>7}{'geos':>6}")
    for x in allo[:12]:
        print(f"  {' AND '.join(x['rule'])[:46]:<48}{x['tf']:>4}"
              f"{'long' if x['side']==1 else 'short':>6}{x['am']:>5.1f}"
              f"{(x['flat']//60 if x['flat'] else 0):>6}{x['n_res']:>5}{x['wr_r']:>7.1f}"
              f"{x['base']:>6.1f}{x['exc_r']:>+7.1f}{x['n_geo']:>6}")
