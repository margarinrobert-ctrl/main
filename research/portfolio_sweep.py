"""Portfolio construction over the 1R book plus the strategy in question, swept and validated.

Same discipline as everything else: every weighting and every subset is chosen on the RESEARCH
block and read once on the LOCKED block. Weights fitted on the whole sample would be a
restatement of the sample.

Six weighting schemes:
    equal lots        one contract each -- what you can actually place
    equal risk        1/volatility, normalised
    inverse variance  1/variance, normalised
    min variance      the minimum-variance portfolio from the research covariance
    max Sharpe        the tangency portfolio from the research block
    risk parity       iterative equal risk contribution
"""
from __future__ import annotations

import itertools
import sys

import numpy as np

sys.path.insert(0, "research")
from oner_book2 import load_all, greedy_book
from test_suite import build, _daily

SCHEMES = ["equal lots", "equal risk", "inverse variance", "min variance",
           "max Sharpe", "risk parity"]
CORR_MAX = [0.15, 0.20, 0.25, 0.30, 0.40, 1.00]
N_LEGS = [4, 6, 8, 10, 12, 14, 18]


def weights(scheme, R, ridge=1e-6):
    n = R.shape[1]
    if scheme == 0:
        return np.ones(n)
    sd = R.std(0, ddof=1)
    if scheme == 1:
        w = 1.0 / np.maximum(sd, 1e-9)
    elif scheme == 2:
        w = 1.0 / np.maximum(sd ** 2, 1e-12)
    elif scheme in (3, 4):
        C = np.cov(R.T) + ridge * np.eye(n)
        Ci = np.linalg.pinv(C)
        w = Ci @ np.ones(n) if scheme == 3 else Ci @ R.mean(0)
        w = np.maximum(w, 0.0)
        if w.sum() <= 0:
            w = np.ones(n)
    else:
        C = np.cov(R.T) + ridge * np.eye(n)
        w = 1.0 / np.maximum(sd, 1e-9)
        for _ in range(60):
            mrc = C @ w
            rc = w * mrc
            w = w * (rc.mean() / np.maximum(rc, 1e-12)) ** 0.15
            w = np.maximum(w, 1e-9)
    return w / max(w.sum(), 1e-12) * n        # normalise to "n contracts of exposure"


def sharpe(x):
    return float(x.mean() / x.std(ddof=1) * np.sqrt(252)) if x.std() > 0 else 0.0


def main():
    cands = load_all()
    extra = build(["RSI14>70", "lower wick>50%"], side=1, atr_mult=2.5, tp_r=1.0,
                  flat_min=0, tf=60)
    pool = [(c[0], c[1]) for c in cands]
    n_sess = max(s.n_sess for _, s in pool)
    have = {" AND ".join(r["rule"]) for r, _ in pool}
    if "RSI14>70 AND lower wick>50%" not in have:
        pool.insert(0, (dict(rule=["RSI14>70", "lower wick>50%"], tf=60, side=1,
                             am=2.5, flat=0, wr_r=62.7), extra))
    D = np.column_stack([np.r_[_daily(s), np.zeros(n_sess)][:n_sess] for _, s in pool])
    cut = pool[0][1].cut
    Rr, Rl = D[:cut], D[cut:]
    print(f"{D.shape[1]} candidate legs, {cut} research sessions, {D.shape[0]-cut} locked\n")

    C = np.corrcoef(Rr.T)
    rows = []
    for cmax, nl, sc in itertools.product(CORR_MAX, N_LEGS, range(len(SCHEMES))):
        keep = []
        for i in np.argsort(-Rr.mean(0) / np.maximum(Rr.std(0), 1e-9)):   # research Sharpe order
            if all(abs(C[i, j]) <= cmax for j in keep):
                keep.append(int(i))
            if len(keep) >= nl:
                break
        if len(keep) < 3:
            continue
        w = weights(sc, Rr[:, keep])
        pr, pl = Rr[:, keep] @ w, Rl[:, keep] @ w
        eq = np.cumsum(pl)
        dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
        rows.append(dict(cmax=cmax, nl=len(keep), sc=sc, keep=keep, w=w,
                         res_sh=sharpe(pr), lok_sh=sharpe(pl),
                         res=float(pr.sum()), lok=float(pl.sum()),
                         lok_dd=dd, lok_mar=float(pl.sum() / dd) if dd > 0 else 0.0))
    print(f"{len(rows)} portfolio configurations (correlation cap x leg count x weighting)\n")

    print(f"  {'weighting':<18}{'n cfgs':>8}{'med res Sharpe':>16}{'med LOK Sharpe':>16}"
          f"{'med locked $':>14}{'% locked +ve':>14}")
    for sc, nm in enumerate(SCHEMES):
        m = [r for r in rows if r["sc"] == sc]
        if not m:
            continue
        print(f"  {nm:<18}{len(m):>8}{np.median([r['res_sh'] for r in m]):>16.2f}"
              f"{np.median([r['lok_sh'] for r in m]):>16.2f}"
              f"{np.median([r['lok'] for r in m]):>14,.0f}"
              f"{100*np.mean([r['lok']>0 for r in m]):>13.0f}%")

    best = max(rows, key=lambda r: r["res_sh"])
    print(f"\n  CHOSEN ON RESEARCH SHARPE, LOCKED READ ONCE")
    print(f"    {SCHEMES[best['sc']]}, {best['nl']} legs, correlation cap {best['cmax']}")
    print(f"    research Sharpe {best['res_sh']:.2f} -> LOCKED Sharpe {best['lok_sh']:.2f}")
    print(f"    locked net ${best['lok']:,.0f}, drawdown ${best['lok_dd']:,.0f}, "
          f"MAR {best['lok_mar']:.2f}")
    solo = [(sharpe(Rl[:, i]), i) for i in range(D.shape[1])]
    print(f"    best single leg on locked: Sharpe {max(solo)[0]:.2f}")
    eqi = [r for r in rows if r["sc"] == 0 and r["nl"] == best["nl"] and r["cmax"] == best["cmax"]]
    if eqi:
        print(f"    the same legs at ONE CONTRACT EACH: locked Sharpe {eqi[0]['lok_sh']:.2f}, "
              f"net ${eqi[0]['lok']:,.0f}, MAR {eqi[0]['lok_mar']:.2f}")
    return rows


if __name__ == "__main__":
    main()
