"""Phase 4 -- price the search, then read the locked block exactly once.

Every candidate that was evaluated is a trial, including the ones that were dropped, and the
survivor is the MAXIMUM of that set. This file re-simulates the whole declared grid so the
reality check has the return stream of everything tried rather than only the winner -- which is
the input users throw away and the one the check actually needs.

  * White's Reality Check over all candidates, stationary block bootstrap, so correlation between
    candidates is preserved.
  * Deflated Sharpe against the EXPECTED MAXIMUM of the trial set, with the trial count reduced
    to an EFFECTIVE count because candidates built from overlapping parameters are correlated and
    the raw count over-deflates.
  * PBO by CSCV -- does the selection PROCEDURE carry information, independent of any one cell.

The locked block is read at the very end, once, for one candidate.
"""
from __future__ import annotations
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
SK = "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9"
sys.path.insert(0, f"{SK}/quant-strategy-lab/scripts")
sys.path.insert(0, f"{SK}/mechanism-first-alpha/scripts")
import numpy as np
import bars as B, sim as S
import gates, metrics
from run_grid import TFS, WINDOWS, SIDES, STOPS, TGTS


def streams():
    """Per-session research P&L for every declared cell, aligned on a common session axis."""
    cols = {}; meta = []
    for tf in TFS:
        b = B.bars(tf); a = B.atr(b, 14)
        for (r0, r1, arm, wname) in WINDOWS:
            hu, hd, _, _ = S.triggers(b, r0, r1, arm, 960, a, 0.0, "both", True)
            sess = np.unique(b["si"][np.flatnonzero(hu | hd)])
            if len(sess) < 20:
                continue
            cut, _ = B.split(b, sess)
            rs = sess[sess < cut]
            pos = {int(s): k for k, s in enumerate(rs)}
            for side in SIDES:
                trig = S.triggers(b, r0, r1, arm, 960, a, 0.0, side, True)[:2]
                for sk in STOPS:
                    for (tm, tk) in TGTS:
                        r = S.run(b, a, r0=r0, r1=r1, arm=arm, stop_k=sk, tgt_k=tk,
                                  tgt_mode=tm, side=side, trig=trig)
                        v = np.zeros(len(rs))
                        ss = b["si"][r["eb"]]; m = ss < cut
                        for s, p in zip(ss[m], r["pnl"][m]):
                            j = pos.get(int(s))
                            if j is not None:
                                v[j] += p
                        key = f"{tf}m|{wname}|{side}|s{sk}|{tm}{tk}"
                        cols[key] = v
                        meta.append((key, tf, wname, side, sk, tm, tk, int(m.sum())))
    return cols, meta


def pad(cols):
    """Stack candidates on the longest session axis; a candidate that trades fewer sessions is
    padded with zeros, which is the honest reading (no trade that session = no P&L)."""
    T = max(len(v) for v in cols.values())
    keys = sorted(cols)
    M = np.zeros((T, len(keys)))
    for j, k in enumerate(keys):
        v = cols[k]; M[T - len(v):, j] = v
    return keys, M


def main():
    cols, meta = streams()
    keys, M = pad(cols)
    print(f"candidates {M.shape[1]}, sessions {M.shape[0]}")
    tot = M.sum(0)
    best = int(np.argmax(tot))
    print(f"\nbest research candidate: {keys[best]}   net ${tot[best]:,.0f}")

    print("\n--- WHITE REALITY CHECK over every candidate (not just the winner) ---")
    rc = gates.reality_check(M, block_mean=5, n_boot=2000, seed=0)
    for k, v in rc.items():
        if isinstance(v, float):
            print(f"   {k}: {v:.4f}")
        else:
            print(f"   {k}: {v}")

    print("\n--- DEFLATED SHARPE ---")
    srs = np.array([m / s if s > 0 else 0.0
                    for m, s in zip(M.mean(0), M.std(0, ddof=1))])
    cc = np.corrcoef(M.T)
    iu = np.triu_indices_from(cc, 1)
    rho = float(np.nanmean(cc[iu]))
    neff = gates.effective_trials(M.shape[1], rho)
    sr = float(srs[best]); T = M.shape[0]
    from scipy import stats
    x = M[:, best]
    dsr = gates.deflated_sharpe(sr, T, M.shape[1], float(np.var(srs, ddof=1)),
                                skew=float(stats.skew(x)), kurtosis=float(stats.kurtosis(x, fisher=False)),
                                avg_correlation=rho)
    print(f"   winner per-session Sharpe {sr:.4f} over T={T} sessions")
    print(f"   trials M={M.shape[1]}, mean pairwise corr {rho:.3f} -> effective trials {neff:.1f}")
    print(f"   E[max Sharpe | {M.shape[1]} pure-noise trials] = "
          f"{gates.expected_max_sharpe(float(np.var(srs, ddof=1)), M.shape[1]):.4f}")
    print(f"   DEFLATED SHARPE = {dsr if not isinstance(dsr,dict) else dsr}")

    print("\n--- PBO (CSCV): does picking the research winner carry information? ---")
    pbo = metrics.probability_of_backtest_overfitting(M, n_splits=14)
    for k, v in (pbo.items() if isinstance(pbo, dict) else []):
        print(f"   {k}: {v:.4f}" if isinstance(v, float) else f"   {k}: {v}")
    json.dump(dict(keys=keys, best=keys[best], rho=rho, neff=float(neff), sr=sr,
                   rc={k: (float(v) if isinstance(v, (int, float)) else str(v)) for k, v in rc.items()}),
              open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "deflate.json"), "w"))


if __name__ == "__main__":
    main()
