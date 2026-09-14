"""V46 -- run the 1,036,800-cell Carver sweep on US100, RESEARCH BLOCK ONLY.

The locked block is never touched here. It is read once, in run_v46b.py, on a frozen configuration,
which is the only way a holdout stays a holdout.

Parallel over spans; each worker owns whole (timeframe, span) slices so no state is shared.
"""
from __future__ import annotations

import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v46")
import v46grid as G          # noqa: E402

MARKET = "US100L"
COST, SLIP = 0.72, 0.25
SPLIT = 0.65
MODE_ID = {"state": 0, "cross": 1}


def one_span(args):
    tf, span = args
    P = G.prep(MARKET, tf, COST, SLIP)
    n = P["n"]
    res = np.arange(n) < int(n * SPLIT)
    rows = []
    for sd in G.SMOOTH_DIV:
        fc = P["fc"][(span, sd)]
        sig_cache = {}
        for thr in G.ENTRY_THR:
            for mode in G.ENTRY_MODE:
                for ch in G.CHOP_CEIL:
                    sig_cache[(thr, mode, ch)] = G.signal_bars(P, span, sd, thr, mode, ch, res)
        for ex in G.EXIT_THR:
            use_ex = ex is not None
            exv = 0.0 if ex is None else float(ex)
            for stop in G.STOPS:
                for tp in G.TPS:
                    for hold in G.MAX_HOLD:
                        xb, pnl, amb = G.walk_exits(P["o"], P["h"], P["l"], P["c"], P["atr"],
                                                    fc, exv, use_ex, stop, tp, hold, COST, SLIP)
                        for (thr, mode, ch), sb in sig_cache.items():
                            if len(sb) < 30:
                                continue
                            ntr, net, gw, gl, nw, f_net, f_n = G.lock_and_score(
                                sb, xb, pnl, P["fold"], G.N_FOLDS)
                            if ntr < 30:
                                continue
                            ok = f_n >= G.MIN_TRADES_PER_FOLD
                            if ok.sum() < 4:
                                fmed = np.nan; fpos = -1
                            else:
                                per = f_net[ok] / f_n[ok]
                                fmed = float(np.median(per)); fpos = int((per > 0).sum())
                            rows.append((tf, span, sd, -99.0 if ex is None else exv, stop, tp,
                                         hold, thr, MODE_ID[mode], ch, ntr, net, gw, gl, nw,
                                         fmed, fpos, int(ok.sum())))
    return rows


def main():
    jobs = [(tf, s) for tf in G.TFS for s in G.SPANS]
    t0 = time.time()
    out = []
    with Pool(4) as pool:
        for k, rows in enumerate(pool.imap_unordered(one_span, jobs), 1):
            out.extend(rows)
            print(f"  {k}/{len(jobs)} slices done, {len(out):,} scorable cells, "
                  f"{time.time()-t0:.0f}s", flush=True)
    cols = ["tf", "span", "sd", "exit_thr", "stop", "tp", "hold", "entry_thr", "mode", "chop",
            "n", "net", "gw", "gl", "nw", "fold_med", "folds_pos", "folds_ok"]
    d = pd.DataFrame(out, columns=cols)
    d["pf"] = np.where(d.gl > 0, d.gw / d.gl, np.nan)
    d["pts"] = d.net / d.n
    d["win"] = d.nw / d.n
    for c in ("tf", "span", "sd", "hold", "n", "nw", "folds_pos", "folds_ok", "mode"):
        d[c] = d[c].astype(np.int32)
    for c in ("exit_thr", "stop", "tp", "entry_thr", "chop", "net", "gw", "gl",
              "fold_med", "pf", "pts", "win"):
        d[c] = d[c].astype(np.float32)
    d.to_parquet("results/v46/v46_us100_research.parquet", compression="zstd", index=False)
    print(f"\n  {len(d):,} scorable of {G.N_NOMINAL:,} nominal   elapsed {time.time()-t0:.0f}s")
    return d


if __name__ == "__main__":
    main()
