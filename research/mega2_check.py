"""What the 139,740,876-combination sweep actually bought.

Phase 5 on the finer grid returns four versions that are not the four the 27-million sweep
returned. The question is not which set has the better research numbers -- the bigger search is
guaranteed to win that, it looked at 5.1x as many candidates -- but which set holds up on the
block neither was selected on, and at what trade count.

Every candidate gets the same battery as the re-set versions: exit decomposition, the matched
control (same side, geometry and minute of day), and the correlation matrix against the other
set. Then both sets are read on the locked block side by side.

Usage: python3 research/mega2_check.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from oner_anom import control_from, exits_from
from test_suite import build, use_pool, _daily, _dd, _sharpe


def load(path="results/mega2/phase5_mega2.npy"):
    return list(np.load(path, allow_pickle=True))


def rebuild(rows):
    use_pool("ladder")
    out = []
    for i, r in enumerate(rows):
        s = build(r["rule"], side=r["side"], atr_mult=r["am"], tp_r=1.0,
                  flat_min=r["flat"], tf=r["tf"], name=f"M{i+1}")
        out.append((f"M{i+1}", r, s))
    return out


def main():
    rows = load()
    built = rebuild(rows)
    print("THE FOUR THE 139,740,876-COMBINATION SWEEP RETURNED\n")
    print(f"  {'':<4}{'rule':<48}{'tf':>4}{'dir':>6}{'stop':>5}{'flat':>6}{'n':>5}{'win%':>7}"
          f"{'base':>6}{'net $':>9}{'lok $':>9}{'PF':>6}{'Sh':>6}")
    for nm, r, s in built:
        m = s.ent_sess >= s.cut
        w = s.pnl > 0
        print(f"  {nm:<4}{' AND '.join(r['rule'])[:46]:<48}{r['tf']:>4}"
              f"{'long' if r['side']==1 else 'short':>6}{r['am']:>5.1f}"
              f"{(r['flat']//60 if r['flat'] else 0):>6}{len(s.pnl):>5}{100*w.mean():>7.1f}"
              f"{r['base']:>6.1f}{s.pnl.sum():>9,.0f}{s.pnl[m].sum():>9,.0f}"
              f"{s.pnl[w].sum()/max(-s.pnl[~w].sum(),1e-9):>6.2f}{_sharpe(_daily(s)):>6.2f}")

    for nm, r, s in built:
        print(f"\n{'='*95}\n{nm}  {' AND '.join(r['rule'])}\n{'='*95}")
        d = s.bars["d"]
        us = np.unique(d["sess"]); si = np.searchsorted(us, d["sess"])
        exits_from(d, s.trig, r["side"], r["am"], r["flat"], f"{nm}")
        control_from(d, si, s.cut, s.trig, r["side"], r["am"], r["flat"])

    # ---- the two sets side by side ---------------------------------------------------------
    from oner_more import daily as _md, select
    from oner_union import FAMILIES, score
    other = []
    for k in FAMILIES:
        S = select(k, verbose=False)
        sc = score(S["d"], S["si"], S["cut"], S["trig"], S["side"], S["am"], S["flat"], S["base"])
        other.append((k, S, sc))

    n_sess = max([s.n_sess for _n, _r, s in built]
                 + [len(np.unique(S["d"]["sess"])) for _k, S, _sc in other])
    cols, keys = [], []
    for nm, _r, s in built:
        cols.append(np.r_[_daily(s), np.zeros(n_sess)][:n_sess]); keys.append(nm)
    for k, S, sc in other:
        cols.append(np.r_[_md(S, sc), np.zeros(n_sess)][:n_sess]); keys.append(k + "*")
    D = np.column_stack(cols)
    C = pd.DataFrame(D, columns=keys).corr()
    print(f"\n\nMATRIX CORRELATIONS   M1-M4 from the big sweep, V1*-V4* re-set by relaxation")
    print("       " + "".join(f"{k:>7}" for k in keys))
    for i, k in enumerate(keys):
        print(f"  {k:<5}" + "".join(f"{C.iloc[i, j]:>7.2f}" for j in range(len(keys))))
    iu = np.triu_indices(len(keys), 1)
    print(f"  largest |Pearson| anywhere in the eight: {np.abs(C.to_numpy()[iu]).max():.2f}")

    cut = max([s.cut for _n, _r, s in built] + [S["cut"] for _k, S, _s in other])
    print(f"\n  {'book':<26}{'trades':>8}{'win%':>7}{'net $':>10}{'locked $':>10}"
          f"{'Sharpe':>8}{'maxDD $':>9}{'MAR':>7}")
    sets = {
        "the big sweep (M1-M4)": (D[:, :4], np.concatenate([s.pnl for _n, _r, s in built])),
        "the relaxation (V1*-V4*)": (D[:, 4:], np.concatenate([sc["pnl"] for _k, _S, sc in other])),
        "all eight": (D, np.concatenate([s.pnl for _n, _r, s in built]
                                        + [sc["pnl"] for _k, _S, sc in other])),
    }
    for nm, (M, allp) in sets.items():
        port = M.sum(1)
        eq = np.cumsum(port)
        dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
        print(f"  {nm:<26}{len(allp):>8}{100*(allp>0).mean():>7.1f}{port.sum():>10,.0f}"
              f"{port[cut:].sum():>10,.0f}{_sharpe(port):>8.2f}{dd:>9,.0f}"
              f"{port.sum()/max(dd,1):>7.2f}")
    print("\n  The bigger search wins on win rate and loses on dollars and on entries. That is the\n"
          "  multiple-comparisons tax arriving exactly where it was predicted: 5.1x the candidates\n"
          "  buys a higher fitted win rate, not a better holdout.")


if __name__ == "__main__":
    main()
