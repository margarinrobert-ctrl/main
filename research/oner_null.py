"""The null that a 1R win-rate claim actually has to beat.

The generic matched null asks whether a strategy's NET P&L beats random entries. For a 1R
strategy selected on win rate that is the wrong question -- it returned p = 0.0123 for all ten
finalists, which is 1/81, which is "no random draw beat it", which tells you the selection worked
and nothing else.

The question is whether the WIN RATE beats what the same geometry produces on random bars in the
same clock window. That null already sits at 42-54% depending on side and stop width, so it is a
much harder thing to clear than 50%.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from test_suite import build


def win_null(s, draws=400, seed=31):
    rng = np.random.default_rng(seed)
    mod = s.bars["mod"]; n = len(s.bars["c"])
    used = mod[np.maximum(s.ent_bar - 1, 0)]
    lo, hi = used.min(), used.max()
    pool = np.flatnonzero((mod >= lo) & (mod <= hi))
    pool = pool[(pool > 300) & (pool < n - 2)]
    if len(pool) < len(s.pnl) * 3:
        pool = np.arange(300, n - 2)
    obs = 100 * (s.pnl > 0).mean()
    wins, nets = [], []
    for _ in range(draws):
        t = np.sort(rng.choice(pool, size=len(s.pnl), replace=False))
        r = s.sim(trig=t)
        if len(r.pnl) < 10:
            continue
        wins.append(100 * (r.pnl > 0).mean()); nets.append(r.pnl.sum())
    wins = np.array(wins)
    return dict(obs=obs, null_mean=float(wins.mean()), null_p95=float(np.percentile(wins, 95)),
                p=float(((wins >= obs).sum() + 1) / (len(wins) + 1)),
                excess=float(obs - wins.mean()), draws=len(wins),
                net_obs=float(s.pnl.sum()), net_null=float(np.mean(nets)))


if __name__ == "__main__":
    import numpy as _np
    rows = list(_np.load("results/oner/oner_final.npy", allow_pickle=True))[:10]
    print(f"  {'rule':<44}{'tf':>4}{'dir':>6}{'n':>5}{'win%':>7}{'null mean':>11}"
          f"{'null p95':>10}{'excess':>8}{'p':>8}")
    out = []
    for r in rows:
        s = build(r["rule"], side=r["side"], atr_mult=r["am"], tp_r=1.0,
                  flat_min=r["flat"], tf=r["tf"])
        if len(s.pnl) < 40:
            continue
        w = win_null(s)
        out.append((r, w))
        print(f"  {' AND '.join(r['rule'])[:42]:<44}{r['tf']:>4}"
              f"{'long' if r['side']==1 else 'short':>6}{len(s.pnl):>5}{w['obs']:>7.1f}"
              f"{w['null_mean']:>11.1f}{w['null_p95']:>10.1f}{w['excess']:>+8.1f}{w['p']:>8.4f}")
    ok = [x for x in out if x[1]["p"] < 0.05]
    print(f"\n  {len(ok)} of {len(out)} clear p < 0.05 on WIN RATE against random entries in the "
          f"same clock window and geometry")
    print(f"  Bonferroni over the {len(out)} finalists needs p < {0.05/max(len(out),1):.4f}: "
          f"{sum(1 for x in out if x[1]['p'] < 0.05/max(len(out),1))} clear it")
