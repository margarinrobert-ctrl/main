"""Which SELECTION PROCEDURE actually transfers? A head-to-head, all research-only.

The robustness gates added after the Tuesday failure produced a book that was far weaker on the
locked block than the ungated one. That is either the gates throwing away real signal or the
ungated book getting lucky, and the difference matters more than either book does.

Five procedures, each choosing 14 de-duplicated strategies using ONLY the research block, each
then read once on the locked block. Same universe, same trade-count floors, same de-duplication.
"""
from __future__ import annotations

import sys
from itertools import combinations

import numpy as np

sys.path.insert(0, "research")
from oner_pick import load
from oner_robust import CALENDAR, MIN_RES, MIN_LOK, _rowmap


def prep_arrays(tf):
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
    return dict(names=names, combos=combos, ex=ex, nvar=nvar, live=live, v=v, base=base,
                rn=rn, rs=rs, wr_r=wr_r, ln=ln, ls=ls, wr_l=wr_l,
                exc_r=wr_r - base[v], exc_l=wr_l - base[v])


def gates(A, use_cal_ban, use_subset, use_nbr, min_win):
    live, v, nvar = A["live"], A["v"], A["nvar"]
    ok = live & (A["wr_r"] >= min_win) & (A["exc_r"] > 0) & (A["rs"] > 0)
    if use_cal_ban:
        banned = {i for i, n in enumerate(A["names"]) if n in CALENDAR}
        row_ok = np.array([not (banned & {int(x) for x in c if x >= 0}) for c in A["combos"]])
        ok &= np.repeat(row_ok, nvar)
    idx = np.flatnonzero(ok)
    if not (use_subset or use_nbr):
        return idx, None
    rmap = _rowmap(len(A["names"]))
    ex = A["ex"]; stops = sorted({e[0] for e in ex})
    nbr = {}
    for vv in range(nvar):
        hi = vv >= len(ex); am, tp, fl = ex[vv % len(ex)]
        k = stops.index(am); out = []
        for kk in (k - 1, k + 1):
            if 0 <= kk < len(stops):
                out.append(ex.index((stops[kk], tp, fl)) + (len(ex) if hi else 0))
        nbr[vv] = out
    keep, robust = [], {}
    for k in idx:
        r, vv = divmod(int(k), nvar)
        idxs = tuple(sorted(int(x) for x in A["combos"][r] if x >= 0))
        parts = [A["exc_r"][k]]
        if use_subset and len(idxs) > 1:
            subs = [rmap[s] for n_ in range(1, len(idxs))
                    for s in combinations(idxs, n_) if s in rmap]
            sv = [A["exc_r"][si * nvar + vv] for si in subs]
            sv = [x for x in sv if np.isfinite(x)]
            if not sv or min(sv) <= 0:
                continue
            parts += sv
        if use_nbr:
            ng = [A["exc_r"][r * nvar + g] for g in nbr[vv]]
            ng = [x for x in ng if np.isfinite(x)]
            if not ng or min(ng) <= 0:
                continue
            parts += ng
        keep.append(k); robust[int(k)] = min(parts)
    return np.array(keep, np.int64), robust


def pick(A, idx, score, n=14, max_shared=1):
    order = sorted(idx, key=lambda k: -score(int(k)))
    out, sets = [], []
    for k in order:
        r = int(k) // A["nvar"]
        cs = {int(x) for x in A["combos"][r] if x >= 0}
        if any(len(cs & s) > max_shared for s in sets):
            continue
        out.append(int(k)); sets.append(cs)
        if len(out) >= n:
            break
    return out


PROCS = [
    ("A  research win rate, no gates",        dict(cal=0, sub=0, nbr=0, win=58), "wr"),
    ("B  + ban calendar conditions",          dict(cal=1, sub=0, nbr=0, win=58), "wr"),
    ("C  + subset coherence",                 dict(cal=1, sub=1, nbr=0, win=58), "wr"),
    ("D  + geometry neighbours",              dict(cal=1, sub=1, nbr=1, win=58), "wr"),
    ("E  D, ranked by worst-of-neighbourhood", dict(cal=1, sub=1, nbr=1, win=58), "robust"),
    ("F  ungated, ranked by win rate, 60%+",  dict(cal=0, sub=0, nbr=0, win=60), "wr"),
]

if __name__ == "__main__":
    As = {tf: prep_arrays(tf) for tf in (15, 30, 60)}
    print(f"  {'procedure':<40}{'legs':>6}{'res $':>10}{'lok $':>10}{'legs +ve':>10}"
          f"{'res win':>9}{'lok win':>9}{'excess held':>13}")
    for label, g, rank in PROCS:
        rows = []
        for tf, A in As.items():
            idx, robust = gates(A, g["cal"], g["sub"], g["nbr"], g["win"])
            if len(idx) == 0:
                continue
            sc = (lambda k: A["wr_r"][k]) if rank == "wr" else (lambda k: robust[k])
            for k in pick(A, idx, sc, n=14):
                rows.append((tf, k, A))
        rows.sort(key=lambda t: -(t[2]["wr_r"][t[1]] if rank == "wr" else 0))
        rows = rows[:14]
        if not rows:
            print(f"  {label:<40}   none"); continue
        res = sum(A["rs"][k] for _, k, A in rows)
        lok = sum(A["ls"][k] for _, k, A in rows)
        pos = sum(1 for _, k, A in rows if A["ls"][k] > 0)
        wr_r = np.mean([A["wr_r"][k] for _, k, A in rows])
        wr_l = np.mean([A["wr_l"][k] for _, k, A in rows])
        held = sum(1 for _, k, A in rows if A["exc_l"][k] > 0)
        print(f"  {label:<40}{len(rows):>6}{res:>10,.0f}{lok:>10,.0f}{pos:>7}/{len(rows):<2}"
              f"{wr_r:>9.1f}{wr_l:>9.1f}{held:>10}/{len(rows):<2}")
