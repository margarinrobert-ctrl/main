"""Build a decorrelated book from the robust survivors, and tag each by trading style.

Selection of the survivors happened in oner_robust.py on the research block. This adds two things
the earlier attempt did not have:

  * a GREEDY DECORRELATION pass -- a candidate joins only if its daily P&L correlates below a
    threshold with everything already in. Ranking by score alone gave a book whose top eight
    correlated at 0.88.
  * STYLE TAGS derived from what the strategy actually does, not from what it is called: median
    holding time in minutes, whether it crosses a session boundary, trade frequency, win rate,
    and whether its conditions are reversion or breakout shaped.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from test_suite import build, _daily, _dd, _sharpe

REVERSION = ("RSI14<30", "RSI14>70", "RSI7<25", "RSI7>75", "close<BB lower", "close>BB upper",
             "close<Keltner lower", "close>Keltner upper", "CCI<-100", "CCI>100",
             "Williams%R<-80", "Williams%R>-20", "MFI<20", "MFI>80", "Stoch K<20", "Stoch K>80")
BREAKOUT = ("close>5-bar high", "close<5-bar low", "close>10-bar high", "close<10-bar low",
            "close>20-bar high", "close<20-bar low", "close>50-bar high", "close<50-bar low",
            "close>Donchian20 high", "close<Donchian20 low", "range>1.5xATR", "vol>2x mean",
            "gap up", "gap down", "outside bar")
CLOCK = ("first hour", "second hour", "midday", "last hour", "overnight")


def styles(r, s):
    hold_bars = float(np.median(s.ex_bar - s.ent_bar))
    hold_min = hold_bars * r["tf"]
    crosses = float(np.mean(s.ex_sess > s.ent_sess))
    yrs = s.n_sess / 252.0
    per_year = len(s.pnl) / yrs
    win = 100 * float((s.pnl > 0).mean())
    t = []
    if hold_min <= 60:
        t.append("scalping")
    elif crosses < 0.15:
        t.append("intraday")
    else:
        t.append("swing")
    if crosses >= 0.15 and "swing" not in t:
        t.append("overnight")
    t.append("long" if r["side"] == 1 else "short")
    if win >= 60:
        t.append("high win rate")
    if per_year >= 100:
        t.append("high frequency")
    elif per_year < 40:
        t.append("selective")
    rs = set(r["rule"])
    if rs & set(REVERSION):
        t.append("mean reversion")
    if rs & set(BREAKOUT):
        t.append("breakout")
    if rs & set(CLOCK):
        t.append("session timed")
    if r["flat"]:
        t.append("flat by close")
    return t, hold_min, crosses, per_year


def load_all(path="results/oner/oner_robust.npy", cap=200):
    rows = list(np.load(path, allow_pickle=True))[:cap]
    out = []
    for r in rows:
        s = build(r["rule"], side=r["side"], atr_mult=r["am"], tp_r=1.0,
                  flat_min=r["flat"], tf=r["tf"])
        if len(s.pnl) < 50:
            continue
        tags, hm, cr, py = styles(r, s)
        lok = float(s.pnl[s.ent_sess >= s.cut].sum())
        pf = float(s.pnl[s.pnl > 0].sum() / max(-s.pnl[s.pnl <= 0].sum(), 1e-9))
        out.append((dict(r, tags=tags, hold_min=hm, crosses=cr, per_year=py,
                         net=float(s.pnl.sum()), locked=lok,
                         research=float(s.pnl[s.ent_sess < s.cut].sum()),
                         win=100 * float((s.pnl > 0).mean()), pf=pf,
                         dd=_dd(s.pnl), sharpe=_sharpe(_daily(s)), trades=len(s.pnl)), s))
    return out


def greedy_book(cands, max_corr=0.25, n=14, n_sess=None):
    n_sess = n_sess or max(s.n_sess for _, s in cands)
    D = {i: np.r_[_daily(s), np.zeros(n_sess)][:n_sess] for i, (_, s) in enumerate(cands)}
    order = sorted(range(len(cands)), key=lambda i: -cands[i][0]["wr_r"])
    chosen = []
    for i in order:
        ok = True
        for j in chosen:
            a, b = D[i], D[j]
            sd = a.std() * b.std()
            if sd > 0 and abs(np.cov(a, b)[0, 1] / sd) > max_corr:
                ok = False; break
        if ok:
            chosen.append(i)
        if len(chosen) >= n:
            break
    return chosen, D, n_sess


def main():
    cands = load_all()
    print(f"{len(cands)} robust survivors rebuilt")
    chosen, D, n_sess = greedy_book(cands)
    M = np.column_stack([D[i] for i in chosen])
    port = M.sum(axis=1)
    eq = np.cumsum(port)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    C = pd.DataFrame(M).corr().to_numpy()
    iu = np.triu_indices(len(chosen), 1)
    allp = np.concatenate([cands[i][1].pnl for i in chosen])

    print(f"\n  {'#':<4}{'rule':<44}{'tf':>4}{'dir':>6}{'n':>5}{'win%':>6}{'net $':>8}"
          f"{'lok $':>8}{'hold':>8}{'styles':>0}")
    for k, i in enumerate(chosen):
        r = cands[i][0]
        hm = r["hold_min"]
        ht = f"{hm:.0f}m" if hm < 600 else f"{hm/1440:.1f}d"
        print(f"  {'B'+str(k+1):<4}{' AND '.join(r['rule'])[:42]:<44}{r['tf']:>4}"
              f"{'long' if r['side']==1 else 'short':>6}{r['trades']:>5}{r['win']:>6.1f}"
              f"{r['net']:>8,.0f}{r['locked']:>8,.0f}{ht:>8}  {', '.join(r['tags'])}")
    print(f"\n  BOOK OF {len(chosen)}, ONE CONTRACT EACH, max pairwise |rho| 0.25")
    print(f"     trades {len(allp):,}   win {100*(allp>0).mean():.1f}%   "
          f"net ${sum(cands[i][0]['net'] for i in chosen):,.0f}   "
          f"locked ${sum(cands[i][0]['locked'] for i in chosen):,.0f}")
    print(f"     largest pairwise correlation {np.abs(C[iu]).max():+.2f}, mean {C[iu].mean():+.2f}")
    print(f"     book Sharpe {_sharpe(port):.2f}   best single "
          f"{max(cands[i][0]['sharpe'] for i in chosen):.2f}")
    print(f"     book maxDD ${dd:,.0f}   worst single leg ${max(cands[i][0]['dd'] for i in chosen):,.0f}")
    pos = sum(1 for i in chosen if cands[i][0]["locked"] > 0)
    print(f"     {pos} of {len(chosen)} legs profitable on the locked block")
    return cands, chosen


if __name__ == "__main__":
    main()
