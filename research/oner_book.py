"""The finalists as a book, because individually they are too small to matter.

Each 1R survivor earns $500-$6,000 over three years on 85-140 trades. That is not a strategy, it
is a component. The question this answers is whether they are components of the SAME thing --
mostly short, mostly last-hour, mostly reversal -- or genuinely separate bets that add up.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from test_suite import build, _daily, _stats, _dd, _sharpe


def load_finalists(n=14):
    rows = list(np.load("results/oner/oner_final.npy", allow_pickle=True))[:n]
    out = []
    for r in rows:
        s = build(r["rule"], side=r["side"], atr_mult=r["am"], tp_r=1.0,
                  flat_min=r["flat"], tf=r["tf"])
        if len(s.pnl) >= 40:
            out.append((r, s))
    return out


def main():
    F = load_finalists()
    n_sess = max(s.n_sess for _, s in F)
    D, labels = [], []
    for i, (r, s) in enumerate(F):
        d = _daily(s)
        D.append(np.r_[d, np.zeros(n_sess - len(d))][:n_sess])
        labels.append(f"L{i+1}")
    D = np.column_stack(D)
    df = pd.DataFrame(D, columns=labels)
    C = df.corr().to_numpy()

    print("  #   rule                                           tf   dir   n   win%   net $   locked $")
    for i, (r, s) in enumerate(F):
        lok = s.pnl[s.ent_sess >= s.cut].sum()
        print(f"  {labels[i]:<4}{' AND '.join(r['rule'])[:44]:<48}{r['tf']:>3}"
              f"{'short' if r['side']==-1 else 'long':>6}{len(s.pnl):>5}"
              f"{100*(s.pnl>0).mean():>6.1f}{s.pnl.sum():>9,.0f}{lok:>11,.0f}")

    iu = np.triu_indices(len(labels), 1)
    print(f"\n  Correlation of daily P&L: max {C[iu].max():+.2f}, mean {C[iu].mean():+.2f}, "
          f"min {C[iu].min():+.2f}")
    print(f"  Pairs above 0.3: {(C[iu] > 0.3).sum()} of {len(iu[0])}")
    print("\n      " + "".join(f"{l:>6}" for l in labels))
    for i, l in enumerate(labels):
        print(f"  {l:<4}" + "".join(
            f"{C[i,j]:>6.2f}" if i != j else "     ·" for j in range(len(labels))))

    # One contract on each leg -- the book you could actually place. Equal-RISK weights sum to
    # one, so their drawdown is in fractional contracts and is not a dollar figure anyone trades.
    port = D.sum(axis=1)
    eq = np.cumsum(port)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    solo = [_sharpe(D[:, i]) for i in range(D.shape[1])]
    solo_dd = [_dd(F[i][1].pnl) for i in range(len(F))]
    allp = np.concatenate([s.pnl for _, s in F])
    print(f"\n  BOOK OF {len(labels)}, ONE CONTRACT EACH")
    print(f"     combined trades          {sum(len(s.pnl) for _, s in F):,}")
    print(f"     combined win rate        {100*(allp>0).mean():.1f}%  "
          f"(1R, so the driftless bound is 50% and the cost-adjusted base is ~47%)")
    print(f"     summed net               ${sum(s.pnl.sum() for _, s in F):,.0f}")
    print(f"     summed locked            "
          f"${sum(s.pnl[s.ent_sess>=s.cut].sum() for _, s in F):,.0f}")
    print(f"     best single Sharpe       {max(solo):.2f}")
    print(f"     book Sharpe              {_sharpe(port):.2f}")
    print(f"     worst single-leg maxDD   ${max(solo_dd):,.0f}")
    print(f"     book max drawdown        ${dd:,.0f}")
    print(f"     return / drawdown        {port.sum()/max(dd,1):.2f}")
    return F, C, labels


if __name__ == "__main__":
    main()
