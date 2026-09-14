"""The four versions, re-set for entry count, then read on the locked block once.

ONE selection rule, stated before it is run, applied to each mechanism's own threshold grid:

    maximise RESEARCH trade count
    subject to  research win rate      >= 60%
                research excess over its geometry's matched base >= 60% of the shipped rule's
                research net           >  0
                research trades        >= 40

Everything in that rule is a research-block quantity. The win-rate floor is what the user asked
for; the excess floor is what stops the floor being met by a looser rule that simply trades a
kinder geometry; the trade-count objective is the thing being bought. If no point on the grid
clears all four, the shipped setting stands -- "no improvement" is an allowed answer and two of
the four give it.

Then, and only then: the locked block, the correlation matrix, and the book.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from oner_union import FAMILIES, GEOS, _sim, _cut, bars, score, sweep
from test_suite import _daily, _dd, _sharpe

WIN_FLOOR = 60.0
EXC_FRAC = 0.60
MIN_RES = 40


def select(key, verbose=True):
    F = FAMILIES[key]
    rows, masks, d, si, cut, bases = sweep(key, verbose=False)
    am, flat = F["am"], F["flat"]
    here = [r for r in rows if r["am"] == am and r["flat"] == flat]
    ship = next(r for r in here if r["p"] == F["ship"])
    bar = EXC_FRAC * ship["exc"]
    cand = [r for r in here if r["wr_res"] >= WIN_FLOOR and r["exc"] >= bar
            and r["res"] > 0 and r["n_res"] >= MIN_RES]
    best = max(cand, key=lambda r: r["n_res"]) if cand else ship
    if verbose:
        print(f"  {key}: {len(here)} points at the shipped geometry, {len(cand)} clear "
              f"win>={WIN_FLOOR:.0f}% and excess>={bar:+.1f}  ->  {best['p']}"
              + ("   (unchanged)" if best is ship else
                 f"   ({ship['n_res']} -> {best['n_res']} research trades)"))
    trig = np.flatnonzero(F["fn"](d, *best["p"])).astype(np.int64)
    return dict(key=key, p=best["p"], row=best, ship=ship, changed=best is not ship,
                d=d, si=si, cut=cut, trig=trig[trig >= 300], base=bases[(am, flat)],
                side=F["side"], am=am, flat=flat, tf=F["tf"], human=F["human"])


def daily(S, s):
    """Per-session P&L on a common session axis, so four timeframes can be correlated."""
    us = np.unique(S["d"]["sess"])
    out = np.zeros(len(us))
    for p, b in zip(s["pnl"], s["ent_bar"]):
        out[S["si"][b]] += p
    return out


def main(verbose=True):
    print("SELECTION  (research block only)")
    sel = [select(k) for k in FAMILIES]
    scored = [(S, score(S["d"], S["si"], S["cut"], S["trig"], S["side"], S["am"], S["flat"],
                        S["base"])) for S in sel]

    print(f"\nTHE FOUR, AFTER RE-SETTING FOR ENTRY COUNT")
    print(f"  {'':<5}{'setting':<22}{'tf':>4}{'dir':>6}{'stop':>5}{'trades':>8}{'res':>5}"
          f"{'lok':>5}{'win%':>7}{'base':>7}{'net $':>10}{'res $':>9}{'lok $':>9}{'PF':>6}")
    for S, s in scored:
        print(f"  {S['key']:<5}{str(S['p'])[:20]:<22}{S['tf']:>4}"
              f"{'long' if S['side']==1 else 'short':>6}{S['am']:>5.1f}{s['n']:>8}{s['n_res']:>5}"
              f"{s['n_lok']:>5}{s['win']:>7.1f}{s['base']:>7.1f}{s['net']:>10,.0f}"
              f"{s['res']:>9,.0f}{s['lok']:>9,.0f}{s['pf']:>6.2f}")

    print(f"\n  the locked block on its own, which is the only number that was not selected on:")
    print(f"  {'':<5}{'trades':>8}{'win%':>7}{'base':>7}{'excess':>8}{'net $':>9}"
          f"{'per trade':>11}{'PF lok':>8}")
    for S, s in scored:
        m = S["si"][s["ent_bar"]] >= S["cut"]
        pl = s["pnl"][m]; w = pl > 0
        print(f"  {S['key']:<5}{len(pl):>8}{100*w.mean():>7.1f}{s['base']:>7.1f}"
              f"{100*w.mean()-s['base']:>+8.1f}{pl.sum():>9,.0f}{pl.mean():>11,.0f}"
              f"{pl[w].sum()/max(-pl[~w].sum(),1e-9):>8.2f}")

    # ---- correlation matrices -----------------------------------------------------------------
    n_sess = max(len(np.unique(S["d"]["sess"])) for S, _ in scored)
    D = np.column_stack([np.r_[daily(S, s), np.zeros(n_sess)][:n_sess] for S, s in scored])
    keys = [S["key"] for S, _ in scored]
    P = pd.DataFrame(D, columns=keys)
    print(f"\nMATRIX CORRELATIONS   per-session P&L, {n_sess} sessions")
    for nm, C in (("Pearson", P.corr()), ("Spearman", P.corr(method="spearman"))):
        print(f"\n  {nm}")
        print("     " + "".join(f"{k:>8}" for k in keys))
        for i, k in enumerate(keys):
            print(f"  {k:<5}" + "".join(f"{C.iloc[i, j]:>8.2f}" for j in range(len(keys))))
    iu = np.triu_indices(len(keys), 1)
    print(f"\n  largest |Pearson| off the diagonal: {np.abs(P.corr().to_numpy()[iu]).max():.2f}")

    # same-session overlap: do they fire together, regardless of sign?
    A = (D != 0).astype(float)
    O = np.zeros((len(keys), len(keys)))
    for i in range(len(keys)):
        for j in range(len(keys)):
            both = (A[:, i] > 0) & (A[:, j] > 0)
            O[i, j] = 100 * both.sum() / max((A[:, i] > 0).sum(), 1)
    print(f"\n  co-occurrence: % of {keys} sessions that also have the column's version trading")
    print("     " + "".join(f"{k:>8}" for k in keys))
    for i, k in enumerate(keys):
        print(f"  {k:<5}" + "".join(f"{O[i, j]:>7.0f}%" for j in range(len(keys))))

    # split the correlation by block, because a book is only decorrelated if it stays that way
    cutmax = max(S["cut"] for S, _ in scored)
    for nm, sl in (("research", slice(0, cutmax)), ("locked", slice(cutmax, None))):
        C = pd.DataFrame(D[sl]).corr().to_numpy()
        print(f"  largest |Pearson| on the {nm} block alone: "
              f"{np.abs(C[np.triu_indices(len(keys),1)]).max():.2f}")

    # ---- the book -------------------------------------------------------------------------------
    port = D.sum(1)
    allp = np.concatenate([s["pnl"] for _, s in scored])
    eq = np.cumsum(port)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    neg = port[port < 0]
    sortino = float(port.mean() / neg.std(ddof=1) * np.sqrt(252)) if len(neg) > 1 else np.nan
    print(f"\nTHE BOOK, ONE CONTRACT EACH")
    print(f"  {len(allp):,} trades   win {100*(allp>0).mean():.1f}%   "
          f"net ${port.sum():,.0f}   locked ${port[cutmax:].sum():,.0f}")
    print(f"  Sharpe {_sharpe(port):.2f}   Sortino {sortino:.2f}   maxDD ${dd:,.0f}   "
          f"MAR {port.sum()/max(dd,1):.2f}")
    best = max(_sharpe(np.r_[daily(S, s), np.zeros(n_sess)][:n_sess]) for S, s in scored)
    print(f"  best single-version Sharpe {best:.2f}, so the book buys "
          f"{_sharpe(port)-best:+.2f} of it from decorrelation alone")
    np.save("results/oner/more.npy", np.array(
        [{"key": S["key"], "p": S["p"], "tf": S["tf"], "side": S["side"], "am": S["am"],
          "flat": S["flat"], "changed": S["changed"],
          "stats": {k: v for k, v in s.items() if not isinstance(v, np.ndarray)}}
         for S, s in scored], dtype=object), allow_pickle=True)
    return scored, D


if __name__ == "__main__":
    main()
