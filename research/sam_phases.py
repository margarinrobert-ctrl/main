"""PHASE 2 gate, PHASE 3 tune, PHASE 4 validate, PHASE 5 select -- on the SAM-anchored sweep.

Same gates as every other search on this branch. Nothing is relaxed because the pool is new:

  CALENDAR BAN     weekday and month conditions partition the sample and hand the search a free
                   lottery. Worth $8,771 on the holdout (STUDY_1R_PROCEDURE.md).
  BASE-RATE EXCESS a 1R win rate is not measured against 50%. Each rule is scored against the
                   population mean of its OWN side and geometry.
  SUBSET COHERENCE every condition of a rule must beat its base ALONE. Removes pairs that exist
                   only because 1.3 million rules were tried. Worth another $6,030.
  TUNE ON RESEARCH geometry is chosen across the 18 same-side stop x flatten combinations on the
                   research block, and tuning is gated exactly like the search that produced the
                   rule.
  VALIDATE ON LOCKED each condition against a RANDOM FILTER OF THE SAME SELECTIVITY, read on the
                   block nothing was chosen on.

The ladder singletons are not in the Phase 1 enumeration, so their research statistics are swept
here on demand -- 198 conditions x 36 variants, using the same kernel and the same precomputed
exits. Without them the ladder leg of a SAM x ladder rule could not be coherence-checked.

Usage: python3 research/sam_phases.py [tf ...]
"""
from __future__ import annotations

import sys
from itertools import combinations

import numpy as np

sys.path.insert(0, "research")
from alpha_factory2 import price_one
from alpha_ladder import build_ladder
from bos_choch import prep
from oner_hunt import sweep_wins
from oner_robust import CALENDAR
from sam_pool import conditions as sam_conditions

MIN_WIN = 55.0            # a scalp on 5m bars will not reach the 58% the 30m searches used
STOPS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
FLATS = [0, 900, 960]
EXITS = [(a, 1.0, f) for a in STOPS for f in FLATS]
_C = {}


def load(tf):
    Z = np.load(f"results/sam/sam_{tf}m.npz", allow_pickle=True)
    return {k: Z[k] for k in Z.files}


def base_rates(Z):
    """Population mean research win rate per variant -- the null each rule is scored against."""
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


def ladder_singletons(tf):
    """Research win rate and trade count for each ladder condition alone, per variant."""
    if ("lad", tf) in _C:
        return _C[("lad", tf)]
    d = prep(tf)
    names, M = build_ladder(d)
    nbars = M.shape[1]
    nw = (nbars + 63) // 64
    B = np.zeros((len(names), nw), np.uint64)
    for i in range(len(names)):
        for p in np.flatnonzero(M[i]):
            B[i, p >> 6] |= np.uint64(1) << np.uint64(p & 63)
    combos = np.array([(i, -1, -1) for i in range(len(names))], np.int32)
    variants = [(s, gi) for s in (1, -1) for gi in range(len(EXITS))]
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr_, mod = d["atr"], d["mod"].astype(np.int64)
    us = np.unique(d["sess"]); sidx = np.searchsorted(us, d["sess"]).astype(np.int64)
    cut = np.int64(int(0.65 * len(us)))
    EB = np.zeros((len(variants), nbars), np.int64)
    EP = np.zeros((len(variants), nbars), np.float64)
    OK = np.zeros((len(variants), nbars), np.int64)
    for vi, (s, gi) in enumerate(variants):
        am, tp, fl = EXITS[gi]
        price_one(o, h, l, c, atr_, mod, s, am, tp, fl, EB[vi], EP[vi], OK[vi])
    tot = len(combos) * len(variants)
    z = lambda t: np.zeros(tot, t)
    rn, rw, ln, lw = z(np.int32), z(np.int32), z(np.int32), z(np.int32)
    rs, ls = z(np.float32), z(np.float32)
    sweep_wins(B, combos, nbars, EB, EP, OK, sidx, cut, rn, rs, rw, ln, ls, lw)
    out = dict(names=names, n=rn.astype(float), w=rw.astype(float), nvar=len(variants))
    _C[("lad", tf)] = out
    return out


def phase2(tf, verbose=True):
    Z = load(tf)
    names = list(Z["names"]); combos = Z["combos"]; nvar = int(Z["nvar"][0])
    n_sam = int(Z["n_sam"][0]); idx = Z["idx"]
    base = base_rates(Z)
    rn, rw = Z["r_n"].astype(float), Z["r_win"].astype(float)
    wr_r = 100 * rw / np.maximum(rn, 1)
    v = idx % nvar
    rule_i = idx // nvar
    exc_r = wr_r - base[v]

    banned = {i for i, n in enumerate(names) if n in CALENDAR}
    has_cal = np.array([bool(banned & {int(x) for x in combos[r] if x >= 0}) for r in rule_i])
    ok = (~has_cal) & (wr_r >= MIN_WIN) & (exc_r > 0)
    if verbose:
        print(f"  {tf}m  {len(idx):,} in -> {int((~has_cal).sum()):,} without a calendar "
              f"condition -> {int(ok.sum()):,} at {MIN_WIN:.0f}%+ with positive excess")

    full_rn, full_rw = Z["base_rn"].astype(float), Z["base_rw"].astype(float)
    full_wr = np.where(full_rn > 0, 100 * full_rw / np.maximum(full_rn, 1), np.nan)
    rmap = {}
    for r in range(len(combos)):
        key = tuple(sorted(int(x) for x in combos[r] if x >= 0))
        rmap[key] = r
    LAD = ladder_singletons(tf)
    keep = []
    for k in np.flatnonzero(ok):
        r, vv = int(rule_i[k]), int(v[k])
        idxs = tuple(sorted(int(x) for x in combos[r] if x >= 0))
        if len(idxs) < 2:
            keep.append(k); continue
        good = True
        for one in idxs:
            if one < n_sam:                       # a SAM condition: it is in this sweep
                si = rmap.get((one,))
                if si is None:
                    continue
                j = si * nvar + vv
                if full_rn[j] < 30:
                    continue
                if full_wr[j] - base[vv] <= 0:
                    good = False; break
            else:                                  # a ladder condition: swept separately
                j = (one - n_sam) * LAD["nvar"] + vv
                if LAD["n"][j] < 30:
                    continue
                if 100 * LAD["w"][j] / max(LAD["n"][j], 1) - base[vv] <= 0:
                    good = False; break
        if good:
            keep.append(k)
    keep = np.array(keep, np.int64)
    if verbose:
        print(f"        -> {len(keep):,} survive subset coherence")
    return dict(tf=tf, Z=Z, base=base, keep=keep, idx=idx, nvar=nvar, names=names, n_sam=n_sam,
                combos=combos, rule_i=rule_i, v=v, wr_r=wr_r, exc_r=exc_r, rn=rn)


def phase3(P, verbose=True):
    """Tune each surviving rule's geometry on research, across all variants of the same side."""
    Z = P["Z"]; nvar = P["nvar"]; base = P["base"]
    full_rn = Z["base_rn"].astype(float); full_rw = Z["base_rw"].astype(float)
    full_wr = np.where(full_rn > 0, 100 * full_rw / np.maximum(full_rn, 1), np.nan)
    seen, out = set(), []
    for k in P["keep"]:
        r, vv = int(P["rule_i"][k]), int(P["v"][k])
        side_hi = vv >= len(EXITS)
        if (r, side_hi) in seen:
            continue
        seen.add((r, side_hi))
        lo = len(EXITS) if side_hi else 0
        cand = []
        for g in range(lo, lo + len(EXITS)):
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
        out.append(dict(tf=P["tf"], rule=[P["names"][i] for i in P["combos"][r] if i >= 0],
                        side=-1 if side_hi else 1, am=float(EXITS[g % len(EXITS)][0]),
                        flat=int(EXITS[g % len(EXITS)][2]), exc_r=float(e),
                        wr_r=float(full_wr[j]), base=float(base[g]), n_res=int(full_rn[j]),
                        n_geo=len(cand)))
    if verbose:
        print(f"  {P['tf']}m  tuned {len(out):,} unique rule/direction pairs")
    return out


def rule_trig(tf, rule):
    """Trigger bars for a rule named in SAM and ladder condition names."""
    if ("pool", tf) not in _C:
        d = prep(tf)
        S = sam_conditions(d, tf)
        lnames, LM = build_ladder(d)
        S.update({n: LM[i] for i, n in enumerate(lnames)})
        _C[("pool", tf)] = (d, S)
    d, S = _C[("pool", tf)]
    m = np.ones(len(d["c"]), bool)
    for q in rule:
        m &= S[q]
    m[:300] = False
    return d, np.flatnonzero(m).astype(np.int64)


if __name__ == "__main__":
    tfs = [int(x) for x in sys.argv[1:]] or [30, 15, 5]
    print("PHASE 2 -- GATE")
    allo = []
    for tf in tfs:
        P = phase2(tf)
        print("PHASE 3 -- TUNE")
        allo += phase3(P)
    allo.sort(key=lambda x: -x["exc_r"])
    np.save("results/sam/sam_phase3.npy", np.array(allo, dtype=object), allow_pickle=True)
    print(f"\nPHASE 3 DONE: {len(allo):,} tuned rule/direction pairs carried forward")
    print(f"  {'rule':<52}{'tf':>4}{'dir':>6}{'stop':>5}{'flat':>6}{'n':>6}{'win%':>7}"
          f"{'base':>6}{'exc':>7}")
    for x in allo[:15]:
        print(f"  {' AND '.join(x['rule'])[:50]:<52}{x['tf']:>4}"
              f"{'long' if x['side']==1 else 'short':>6}{x['am']:>5.1f}"
              f"{(x['flat']//60 if x['flat'] else 0):>6}{x['n_res']:>6}{x['wr_r']:>7.1f}"
              f"{x['base']:>6.1f}{x['exc_r']:>+7.1f}")


# ---- PHASE 4 and 5, in the same file so the whole procedure reads top to bottom ---------------
def dedupe(rows, max_shared=0):
    """Collapse rules that share a condition, keeping the best. Two SAM readings one window apart
    are all but the same rule, and the top of an excess-sorted list is full of them."""
    keep, sets = [], []
    for r in rows:
        cs = set(r["rule"])
        if any(len(cs & s) > max_shared for s in sets):
            continue
        keep.append(r); sets.append(cs)
    return keep


def phase4(rows, top=80, draws=1500, verbose=True):
    """Each condition against a random filter of the same selectivity, ON THE LOCKED BLOCK."""
    from dropone import filter_null
    from test_suite import build, _daily, _dd, _sharpe
    cand = dedupe(rows)[:top]
    if verbose:
        print(f"\nPHASE 4 -- VALIDATE\n  {len(rows):,} tuned pairs -> {len(cand)} after collapsing "
              f"rules that share any condition")
    out = []
    for i, r in enumerate(cand):
        d, trig = rule_trig(r["tf"], r["rule"])
        s = build(r["rule"], side=r["side"], atr_mult=r["am"], tp_r=1.0, flat_min=r["flat"],
                  tf=r["tf"], trig=trig, pool=False, name=" AND ".join(r["rule"]))
        m = s.ent_sess >= s.cut
        if len(s.pnl) < 60 or m.sum() < 20:
            continue
        proven, ps = 0, []
        for j in range(len(r["rule"])):
            sub = [x for k, x in enumerate(r["rule"]) if k != j]
            if not sub:
                continue
            d2, t2 = rule_trig(r["tf"], sub)
            s2 = build(sub, side=r["side"], atr_mult=r["am"], tp_r=1.0, flat_min=r["flat"],
                       tf=r["tf"], trig=t2, pool=False)
            p = filter_null(s, s2, draws=draws)["lok"][2]
            ps.append((r["rule"][j], p))
            if np.isfinite(p) and p < 0.10:
                proven += 1
        w = s.pnl > 0
        out.append(dict(r, s=s, proven=proven, n_cond=len(r["rule"]), ps=ps,
                        trades=len(s.pnl), win=100 * float(w.mean()),
                        net=float(s.pnl.sum()), res=float(s.pnl[~m].sum()),
                        lok=float(s.pnl[m].sum()),
                        win_lok=100 * float((s.pnl[m] > 0).mean()),
                        pf=float(s.pnl[w].sum() / max(-s.pnl[~w].sum(), 1e-9)),
                        dd=_dd(s.pnl), sharpe=_sharpe(_daily(s))))
        if verbose and (i + 1) % 20 == 0:
            print(f"     {i+1}/{len(cand)}...", flush=True)
    ok = [o for o in out if o["proven"] >= 1 and o["lok"] > 0 and o["win_lok"] > o["base"]]
    if verbose:
        print(f"  {len(out)} rebuilt with enough trades")
        print(f"  {sum(1 for o in out if o['proven'] >= 1)} have a condition beating a random "
              f"filter of the same size ON THE LOCKED BLOCK")
        print(f"  {len(ok)} of those also clear their base rate AND make money there")
    return out, ok


def phase5(ok, n=4, max_corr=0.30, verbose=True):
    from test_suite import _daily, _sharpe
    ok = sorted(ok, key=lambda o: (-o["proven"], -o["sharpe"]))
    n_sess = max(o["s"].n_sess for o in ok)
    D = {i: np.r_[_daily(o["s"]), np.zeros(n_sess)][:n_sess] for i, o in enumerate(ok)}
    chosen = []
    for i in range(len(ok)):
        if all(not (D[i].std() * D[j].std() > 0
                    and abs(np.cov(D[i], D[j])[0, 1] / (D[i].std() * D[j].std())) > max_corr)
               for j in chosen):
            chosen.append(i)
        if len(chosen) >= n:
            break
    sel = [ok[i] for i in chosen]
    if verbose:
        print(f"\nPHASE 5 -- SELECT\n  {len(sel)} versions, decorrelated below |rho| {max_corr}")
        print(f"\n  {'#':<4}{'rule':<50}{'tf':>4}{'dir':>6}{'stop':>5}{'n':>6}{'win%':>7}"
              f"{'base':>6}{'lok n':>7}{'lok win%':>10}{'res $':>9}{'lok $':>9}{'PF':>6}"
              f"{'Sh':>6}{'proven':>8}")
        for i, o in enumerate(sel):
            lm = o["s"].ent_sess >= o["s"].cut
            print(f"  S{i+1:<3}{' AND '.join(o['rule'])[:48]:<50}{o['tf']:>4}"
                  f"{'long' if o['side']==1 else 'short':>6}{o['am']:>5.1f}{o['trades']:>6}"
                  f"{o['win']:>7.1f}{o['base']:>6.1f}{int(lm.sum()):>7}{o['win_lok']:>10.1f}"
                  f"{o['res']:>9,.0f}{o['lok']:>9,.0f}{o['pf']:>6.2f}{o['sharpe']:>6.2f}"
                  f"{o['proven']}/{o['n_cond']:<6}")
            for cnd, p in o["ps"]:
                print(f"       '{cnd}' locked p = {p:.3f}"
                      + ("   <- real filter" if np.isfinite(p) and p < 0.10 else ""))
    return sel, chosen, D
