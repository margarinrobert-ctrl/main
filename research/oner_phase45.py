"""PHASE 4 -- validate.  PHASE 5 -- select four decorrelated versions.

Phase 4 runs the test that has killed everything else on this branch: each condition is compared
against a RANDOM FILTER OF THE SAME SELECTIVITY, on the LOCKED block. Total dollars fails every
restrictive condition and per-trade edge passes every one; only this comparison is informative.

Then the survivors go through the execution and resampling tests that matter for a 1R rule --
true 1-minute intrabar path, entry-timing dispersion, matched null, bootstrap.

Phase 5 picks four versions that are decorrelated from each other, so "four best" is four bets
rather than one bet in four costumes.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from dropone import filter_null
from test_suite import build, use_pool, _daily, _dd, _sharpe

TOP = 150


def dedupe(rows, max_shared=1):
    keep, sets = [], []
    for r in rows:
        cs = set(r["rule"])
        if any(len(cs & s) > max_shared for s in sets):
            continue
        keep.append(r); sets.append(cs)
    return keep


def phase4(rows, top=TOP, verbose=True):
    cand = dedupe(rows)[:top]
    if verbose:
        print(f"PHASE 4 -- VALIDATE\n  {len(rows):,} tuned pairs -> {len(cand)} after collapsing "
              f"rules that share 2+ conditions")
    out = []
    for i, r in enumerate(cand):
        s = build(r["rule"], side=r["side"], atr_mult=r["am"], tp_r=1.0,
                  flat_min=r["flat"], tf=r["tf"])
        if len(s.pnl) < 60:
            continue
        m = s.ent_sess >= s.cut
        if m.sum() < 20:
            continue
        proven, ps = 0, []
        for j in range(len(r["rule"])):
            sub = [x for k, x in enumerate(r["rule"]) if k != j]
            if not sub:
                continue
            s2 = build(sub, side=r["side"], atr_mult=r["am"], tp_r=1.0,
                       flat_min=r["flat"], tf=r["tf"])
            nul = filter_null(s, s2, draws=1200)
            p = nul["lok"][2]
            ps.append((r["rule"][j], p))
            if np.isfinite(p) and p < 0.10:
                proven += 1
        lok = float(s.pnl[m].sum())
        out.append(dict(r, s=s, proven=proven, n_cond=len(r["rule"]), ps=ps,
                        trades=len(s.pnl), win=100 * float((s.pnl > 0).mean()),
                        net=float(s.pnl.sum()), res=float(s.pnl[~m].sum()), lok=lok,
                        pf=float(s.pnl[s.pnl > 0].sum() / max(-s.pnl[s.pnl <= 0].sum(), 1e-9)),
                        dd=_dd(s.pnl), sharpe=_sharpe(_daily(s))))
        if verbose and (i + 1) % 25 == 0:
            print(f"     {i+1}/{len(cand)}...", flush=True)
    ok = [o for o in out if o["proven"] >= 1 and o["lok"] > 0]
    if verbose:
        print(f"  {len(out)} rebuilt with enough trades")
        print(f"  {sum(1 for o in out if o['proven'] >= 1)} have at least one condition beating a "
              f"random filter of the same size ON THE LOCKED BLOCK")
        print(f"  {len(ok)} of those are also profitable there")
    return out, ok


def phase5(ok, n=4, max_corr=0.25, verbose=True):
    ok = sorted(ok, key=lambda o: (-o["proven"], -o["sharpe"]))
    n_sess = max(o["s"].n_sess for o in ok)
    D = {i: np.r_[_daily(o["s"]), np.zeros(n_sess)][:n_sess] for i, o in enumerate(ok)}
    chosen = []
    for i in range(len(ok)):
        good = True
        for j in chosen:
            a, b = D[i], D[j]
            sd = a.std() * b.std()
            if sd > 0 and abs(np.cov(a, b)[0, 1] / sd) > max_corr:
                good = False; break
        if good:
            chosen.append(i)
        if len(chosen) >= n:
            break
    sel = [ok[i] for i in chosen]
    if verbose:
        print(f"\nPHASE 5 -- SELECT\n  {len(sel)} versions, decorrelated below |rho| {max_corr}")
    return sel, chosen, D


if __name__ == "__main__":
    pref = sys.argv[1] if len(sys.argv) > 1 else "mega"
    # the mega2 sweep enumerated the 198-rung ladder, so its rule names only resolve there
    use_pool("ladder" if pref == "mega2" else "factory")
    rows = list(np.load(f"results/oner/phase3_{pref}.npy", allow_pickle=True))
    out, ok = phase4(rows)
    np.save(f"results/oner/phase4_{pref}.npy", np.array(
        [{k: v for k, v in o.items() if k != "s"} for o in out], dtype=object), allow_pickle=True)
    sel, chosen, D = phase5(ok)
    print(f"\n  {'#':<4}{'rule':<46}{'tf':>4}{'dir':>6}{'stop':>5}{'n':>5}{'win%':>7}"
          f"{'base':>6}{'res $':>9}{'lok $':>9}{'PF':>6}{'Sh':>6}{'DD':>7}{'proven':>8}")
    for i, o in enumerate(sel):
        print(f"  V{i+1:<3}{' AND '.join(o['rule'])[:44]:<46}{o['tf']:>4}"
              f"{'long' if o['side']==1 else 'short':>6}{o['am']:>5.1f}{o['trades']:>5}"
              f"{o['win']:>7.1f}{o['base']:>6.1f}{o['res']:>9,.0f}{o['lok']:>9,.0f}"
              f"{o['pf']:>6.2f}{o['sharpe']:>6.2f}{o['dd']:>7,.0f}{o['proven']}/{o['n_cond']:<6}")
        for c, p in o["ps"]:
            print(f"       '{c}' locked p = {p:.3f}"
                  + ("   <- real filter" if np.isfinite(p) and p < 0.10 else ""))
    if len(sel) > 1:
        M = np.column_stack([D[i] for i in chosen])
        C = pd.DataFrame(M).corr().to_numpy()
        iu = np.triu_indices(len(sel), 1)
        port = M.sum(1)
        eq = np.cumsum(port)
        dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
        allp = np.concatenate([o["s"].pnl for o in sel])
        print(f"\n  THE FOUR AS A BOOK, ONE CONTRACT EACH")
        print(f"     trades {len(allp):,}   win {100*(allp>0).mean():.1f}%   "
              f"net ${sum(o['net'] for o in sel):,.0f}   locked ${sum(o['lok'] for o in sel):,.0f}")
        print(f"     largest pairwise correlation {np.abs(C[iu]).max():+.2f}")
        print(f"     book Sharpe {_sharpe(port):.2f}   best single "
              f"{max(o['sharpe'] for o in sel):.2f}   book maxDD ${dd:,.0f}")
    np.save(f"results/oner/phase5_{pref}.npy", np.array(
        [{k: v for k, v in o.items() if k != "s"} for o in sel], dtype=object), allow_pickle=True)
