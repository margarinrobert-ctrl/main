"""Stage 1: the coarse grid on TRAIN, robustness for the top, then one read of VALID.

Saves every trial so later stages can resume and so the trial COUNT is available to the
deflated-Sharpe calculation. OOS is not opened here.
"""
from __future__ import annotations

import sys
import time

import pandas as pd

sys.path.insert(0, "research/v33")
import v33core as V           # noqa: E402
import v33opt as O            # noqa: E402

OUT = "research/v33/trials"


def hdr(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124, flush=True)


if __name__ == "__main__":
    import os
    os.makedirs(OUT, exist_ok=True)
    sp = O.grid_space()
    hdr("STAGE 1  COARSE GRID -- declared before it is run")
    for k, v in sp.items():
        print(f"   {k:<12} {v}")
    print(f"   -> {O.n_configs():,} configurations per side per market, "
          f"{O.n_configs() * 4:,} in total")

    keep = []
    for market in ("US30", "NQ"):
        for side in (1, -1):
            t0 = time.perf_counter()
            print(f"\n   grid {market} side {side:+d} ...", flush=True)
            df = O.coarse(market, side, progress=True)
            df.to_csv(f"{OUT}/grid_{market}_{side}.csv", index=False)
            print(f"   {market} side {side:+d}: {len(df):,} scorable of {O.n_configs():,} "
                  f"in {time.perf_counter() - t0:.0f}s")
            print(f"      share of grid profitable on TRAIN (PF>1): "
                  f"{float((df.pf > 1).mean()):.3f}   Sharpe>0: {float((df.sharpe > 0).mean()):.3f}"
                  f"   median PF {df.pf.median():.3f}   best PF {df.pf.max():.3f}")
            d = O.add_robustness(market, df, side, top=400)
            d.to_csv(f"{OUT}/robust_{market}_{side}.csv", index=False)
            v = O.read_valid(market, d, side, top=60)
            v.drop(columns=["params"]).to_csv(f"{OUT}/valid_{market}_{side}.csv", index=False)
            keep.append((market, side, df, d, v))

    hdr("STAGE 1 RESULT  top of TRAIN by the objective, read once on VALID")
    for market, side, df, d, v in keep:
        print(f"\n   {market} side {side:+d}   "
              f"(grid {len(df):,} scorable; robustness computed for the top 400; "
              f"VALID read for the top 60)")
        print(f"      {'#':>3}{'tf':>4}{'ent':>5}{'exit':>5}{'stop':>6}{'tp':>5}{'chop':>6}"
              f"{'adx':>5}{'sess':>12}{'vol':>10}{'rob':>6}{'score':>7}"
              f"{'  |':>3}{'tr n':>6}{'tr PF':>7}{'tr Sh':>7}{'  |':>3}{'va n':>6}{'va PF':>7}"
              f"{'va Sh':>7}")
        for i, r in v.head(12).iterrows():
            p = r["params"]
            print(f"      {i:>3}{p.tf:>4}{p.entry_n:>5}{p.exit_n:>5}{p.stop:>6.1f}{p.tp_r:>5.1f}"
                  f"{str(p.chop_max):>6}{str(p.adx_min):>5}{str(p.session):>12}"
                  f"{str(p.vol_policy):>10}{r.robust:>6.2f}{r.score:>7.3f}{'  |':>3}"
                  f"{r.tr_n:>6.0f}{r.tr_pf:>7.3f}{r.tr_sharpe:>+7.2f}{'  |':>3}"
                  f"{r.va_n:>6.0f}{r.va_pf:>7.3f}{r.va_sharpe:>+7.2f}")
        ok = v.dropna(subset=["va_sharpe"])
        if len(ok) > 3:
            print(f"      TRANSFER train -> valid over the top {len(ok)}:  "
                  f"Sharpe rank corr {ok.tr_sharpe.corr(ok.va_sharpe, method='spearman'):+.3f}"
                  f"   PF rank corr {ok.tr_pf.corr(ok.va_pf, method='spearman'):+.3f}"
                  f"   share still Sharpe>0 {float((ok.va_sharpe > 0).mean()):.3f}")
