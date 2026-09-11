"""Phase 2: the best reading chosen on research, read once on locked, then attacked."""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v20")
import v16core as C          # noqa: E402
import v20linreg as L        # noqa: E402
from v20run import control   # noqa: E402

RNG = np.random.default_rng(20260828)
PICK = "C close>value"     # best pooled median add on BOTH timeframes, chosen on research only


def hdr(t):
    print("\n" + "=" * 118)
    print(t)
    print("=" * 118)


if __name__ == "__main__":
    hdr("4. THE READING CHOSEN ON RESEARCH, READ ONCE ON LOCKED, WITH ITS MATCHED CONTROL")
    print(f"   '{PICK}' -- the only reading with a positive pooled median on BOTH timeframes")
    print("   (+0.0049 at 15m, +0.0028 at 30m). Chosen on the research block, nothing else tuned.\n")
    print(f"   {'market':<8}{'tf':>4}{'block':<10}{'n':>7}{'EV(R)':>9}{'PF':>8}{'net R':>9}"
          f"{'maxDD':>8}{'MAR':>7}{'Sharpe':>8}{'Sortino':>9}{'ctl p':>8}")
    for tf in (15, 30):
        for k in L.MARKETS:
            P = L.ctx(k, tf)
            res, lock = L.blocks(P)
            for bn, bb in (("research", res), ("LOCKED", lock)):
                O, i = L.run(P, 1, PICK, block=bb)
                m = L.metrics(P, O, i, bb)
                ctl, p = control(P, bb, O, i, L.SPEC["stop"], draws=800)
                pv = f"{p:.3f}" if np.isfinite(p) else "n/a"
                print(f"   {k:<8}{tf:>3}m{bn:<10}{m['n']:>7}{m['ev']:>+9.4f}{m['pf']:>8.3f}"
                      f"{m['net']:>+9.1f}{m['dd']:>8.1f}{m['mar']:>7.2f}{m['sharpe']:>8.2f}"
                      f"{m['sortino']:>9.2f}{pv:>8}")
            print()

    hdr("5. PERTURBATION ON THE REGRESSION LENGTH -- 50 was given, so check its neighbourhood")
    print(f"   {'length':>8}" + "".join(f"{k:>12}" for k in L.MARKETS) + f"{'pooled EV':>12}")
    for n in (20, 30, 50, 75, 100):
        cells, allr = [], []
        for k in L.MARKETS:
            spec = dict(L.SPEC); spec["lr_len"] = n
            P = L.ctx(k, 30, spec)
            res, _ = L.blocks(P)
            O, i = L.run(P, 1, PICK, block=res, spec=spec)
            m = L.metrics(P, O, i, res)
            cells.append(f"{m['ev']:+.4f}")
            allr.append(O["R"][i])
        pooled = np.concatenate(allr)
        mark = "  <- as briefed" if n == 50 else ""
        print(f"   {n:>8}" + "".join(f"{c:>12}" for c in cells)
              + f"{pooled.mean():>+12.4f}{mark}")

    hdr("6. WHAT THE SAME MEASUREMENTS SAY WOULD ACTUALLY HELP")
    print("   The two geometry knobs in the brief are the ones STUDY_V18 already measured across")
    print("   3,125 cells. Holding the Donchian and the regression fixed and changing only those:\n")
    print(f"   {'market':<8}{'configuration':<30}{'n':>7}{'EV(R)':>9}{'PF':>8}{'MAR':>7}"
          f"{'Sharpe':>8}{'Sortino':>9}")
    for k in L.MARKETS:
        P = L.ctx(k, 30)
        res, lock = L.blocks(P)
        for lab, st, tp in (("as briefed: 2.0N, 2R", 2.0, 2.0),
                            ("no target", 2.0, 0.0),
                            ("3.0N, no target", 3.0, 0.0)):
            O, i = L.run(P, 1, PICK, block=lock, stop=st, tp_r=tp)
            m = L.metrics(P, O, i, lock)
            print(f"   {k + ' LOCKED':<8}{lab:<30}{m['n']:>7}{m['ev']:>+9.4f}{m['pf']:>8.3f}"
                  f"{m['mar']:>7.2f}{m['sharpe']:>8.2f}{m['sortino']:>9.2f}")
        print()

    hdr("7. COST STRESS AND MONTE CARLO on the briefed configuration, 30m, locked")
    print(f"   {'market':<8}{'x1':>10}{'x1.5':>10}{'x2':>10}{'P(mean<=0)':>13}"
          f"{'realDD':>9}{'MC p95':>9}{'MC p99':>9}")
    for k in L.MARKETS:
        P = L.ctx(k, 30)
        res, lock = L.blocks(P)
        row = []
        for cm in (1.0, 1.5, 2.0):
            O, i = L.run(P, 1, PICK, block=lock, cost_mult=cm)
            row.append(f"{L.metrics(P, O, i, lock)['ev']:+.4f}")
        O, i = L.run(P, 1, PICK, block=lock)
        m = L.metrics(P, O, i, lock)
        d = L.daily_R(P, O, i, lock).to_numpy()
        d = d[d != 0]
        if len(d) < 20:
            print(f"   {k:<8}" + "".join(f"{c:>10}" for c in row) + f"{'thin':>13}")
            continue
        bs = np.array([RNG.choice(d, len(d), replace=True).mean() for _ in range(6000)])
        dds = np.array([float((np.maximum.accumulate(RNG.permutation(d).cumsum())
                               - RNG.permutation(d).cumsum()).max()) for _ in range(3000)])
        print(f"   {k:<8}" + "".join(f"{c:>10}" for c in row)
              + f"{float((bs <= 0).mean()):>13.3f}{m['dd']:>9.1f}"
                f"{np.percentile(dds,95):>9.1f}{np.percentile(dds,99):>9.1f}")
