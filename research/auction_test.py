"""Every auction condition against every shipped strategy, with the multiplicity paid for.

29 conditions x 9 strategies = 261 tests. At a 5% threshold, 13 of those pass by chance alone, so
a table of "conditions that improved the win rate" is worthless without saying that number out
loud first. The protocol, fixed before running:

  1. RESEARCH BLOCK. A condition must keep at least 25 research trades and beat a RANDOM FILTER
     OF THE SAME SELECTIVITY drawn from that strategy's own trades, at p < 0.05, on BOTH per-trade
     dollars and win rate. Random-filter is the right null: a filter that keeps a third of the
     trades will fail a total-dollars test whatever it does, and pass a per-trade-edge test
     whatever it does (CLAUDE.md).
  2. Count how many pass, and compare that with 261 x 0.05 = 13 expected by chance.
  3. LOCKED BLOCK, once, for the survivors only, same test, then Benjamini-Hochberg across them.

A condition that reaches step 3 and holds is worth adding to a rule. Nothing else is.

Usage: python3 research/auction_test.py
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from allstrats import all_strategies
from anomalies import bh
from auction import conditions, signal_bars
from oner_union import _cut, _sim

MIN_RES, MIN_LOK, DRAWS = 25, 12, 2000
ALPHA = 0.05


def null(sub_p, full_p, draws=DRAWS, seed=17):
    """Where the filtered subset falls among random subsets of the same size. (p_dollars, p_win)"""
    if len(sub_p) < 12 or len(full_p) <= len(sub_p):
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    obs_d, obs_w = sub_p.mean(), (sub_p > 0).mean()
    dd = np.empty(draws); ww = np.empty(draws)
    for i in range(draws):
        q = rng.choice(full_p, size=len(sub_p), replace=False)
        dd[i] = q.mean(); ww[i] = (q > 0).mean()
    return (float(((dd >= obs_d).sum() + 1) / (draws + 1)),
            float(((ww >= obs_w).sum() + 1) / (draws + 1)))


def run(verbose=True):
    A = all_strategies()
    C = {}
    rows = []
    for k, S in A.items():
        d = S["d"]
        tf = S["tf"]
        if tf not in C:
            C[tf] = conditions(d)
        pnl, eb, _x, why, _g = _sim(d, S["trig"], S["side"], S["am"], S["flat"])
        si, cut, _ = _cut(d)
        lok = si[eb] >= cut
        for name, mask in C[tf].items():
            keep = mask[signal_bars(eb)]
            if keep.sum() < MIN_RES + MIN_LOK or keep.all():
                continue
            r_sub, r_all = pnl[keep & ~lok], pnl[~lok]
            l_sub, l_all = pnl[keep & lok], pnl[lok]
            if len(r_sub) < MIN_RES:
                continue
            pd_, pw_ = null(r_sub, r_all)
            rows.append(dict(strat=k, cond=name, n_res=len(r_sub), n_all_res=len(r_all),
                             n_lok=len(l_sub), share=float(keep.mean()),
                             win_res=100 * float((r_sub > 0).mean()),
                             win_res_all=100 * float((r_all > 0).mean()),
                             d_res=float(r_sub.mean()), d_res_all=float(r_all.mean()),
                             p_d=pd_, p_w=pw_,
                             l_sub=l_sub, l_all=l_all))
    if verbose:
        print(f"STEP 1 -- RESEARCH BLOCK\n  {len(rows)} of {len(A)*len(next(iter(C.values())))} "
              f"strategy x condition pairs keep {MIN_RES}+ research trades")
    ok = [r for r in rows if np.isfinite(r["p_d"]) and r["p_d"] < ALPHA
          and np.isfinite(r["p_w"]) and r["p_w"] < ALPHA]
    exp = len(rows) * ALPHA * ALPHA          # both tests, treated as independent -- a lower bound
    if verbose:
        print(f"\nSTEP 2 -- HOW MANY WOULD PASS BY CHANCE")
        print(f"  {len(ok)} pairs beat a random filter of the same size on BOTH dollars and win "
              f"rate at p < {ALPHA}")
        print(f"  {len(rows)} tests x {ALPHA} = {len(rows)*ALPHA:.0f} expected on either test "
              f"alone; requiring both puts the\n  chance expectation between "
              f"{exp:.1f} and {len(rows)*ALPHA:.0f}, since the two statistics are far from "
              f"independent")
        if ok:
            print(f"\n  {'':<5}{'condition':<30}{'keeps':>7}{'n res':>7}{'win%':>7}"
                  f"{'vs all':>8}{'$/tr':>8}{'vs all':>8}{'p$':>7}{'pW':>7}")
            for r in sorted(ok, key=lambda x: x["p_d"]):
                print(f"  {r['strat']:<5}{r['cond'][:28]:<30}{100*r['share']:>6.0f}%"
                      f"{r['n_res']:>7}{r['win_res']:>7.1f}{r['win_res_all']:>8.1f}"
                      f"{r['d_res']:>8,.0f}{r['d_res_all']:>8,.0f}{r['p_d']:>7.3f}"
                      f"{r['p_w']:>7.3f}")

    if verbose:
        print(f"\nSTEP 3 -- THE LOCKED BLOCK, ONCE, FOR THOSE {len(ok)} ONLY")
    if not ok:
        print("  nothing to read"); return rows, ok, []
    for r in ok:
        r["lp_d"], r["lp_w"] = null(r["l_sub"], r["l_all"], seed=29)
    fin = [r for r in ok if np.isfinite(r["lp_d"])]
    if fin:
        q = bh(np.array([max(r["lp_d"], r["lp_w"]) for r in fin]))
        for r, x in zip(fin, q):
            r["q"] = float(x)
    if verbose:
        print(f"  {'':<5}{'condition':<30}{'n lok':>7}{'win%':>7}{'vs all':>8}{'$/tr':>8}"
              f"{'vs all':>8}{'p$':>7}{'pW':>7}{'q':>7}")
        for r in sorted(fin, key=lambda x: x.get("q", 1)):
            ls, la = r["l_sub"], r["l_all"]
            print(f"  {r['strat']:<5}{r['cond'][:28]:<30}{len(ls):>7}"
                  f"{100*(ls>0).mean():>7.1f}{100*(la>0).mean():>8.1f}{ls.mean():>8,.0f}"
                  f"{la.mean():>8,.0f}{r['lp_d']:>7.3f}{r['lp_w']:>7.3f}{r.get('q',np.nan):>7.3f}"
                  + ("  <- holds" if r.get("q", 1) < 0.10 else ""))
        surv = [r for r in fin if r.get("q", 1) < 0.10]
        print(f"\n  {len(surv)} of {len(fin)} survive Benjamini-Hochberg at q < 0.10 on the block "
              f"they were not selected on")
    return rows, ok, fin


if __name__ == "__main__":
    run()
