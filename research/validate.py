"""What the speed is actually for.

vectorbt's headline feature is searching millions of parameter combinations quickly. This project
has already measured that as HARMFUL: STUDY_SEARCH_CURVE.md found a pre-specified configuration
earning 0.312R against a searched one's 0.278-0.343, and the IB study found PBO 0.968 and
walk-forward re-optimisation turning $27,253 into $14,580.

So the 100x speedup is spent on VALIDATION, not on search:
  1. CSCV / PBO with 16 blocks — 12,870 train/test splits, which was not affordable before.
  2. A stationary block bootstrap at 10,000 resamples, preserving serial dependence.
  3. The search-width curve at real resolution.

Usage: python3 research/validate.py
"""
from __future__ import annotations

import sys
import time
from itertools import combinations

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from grid import CONST, block_matrix, build_grid, run_all
from ib_sim import simulate
from nqdata import load_bars, minute_of_day, minutes_since_open, session_index, session_slice
from pf import stats

rng = np.random.default_rng(7)
seg = session_slice(load_bars("data/NQ_1m.csv"), 570, 719)
mod = minute_of_day(seg.index)
bars = (
    seg["open"].to_numpy(np.float64), seg["high"].to_numpy(np.float64),
    seg["low"].to_numpy(np.float64), seg["close"].to_numpy(np.float64),
    session_index(seg.index, 570), minutes_since_open(mod, 570).astype(np.int64),
    np.zeros(len(seg)),
)
n_bars = len(seg)

grid = build_grid()
t0 = time.perf_counter()
results = run_all(bars, grid)
elapsed = time.perf_counter() - t0
print(f"{len(grid):,} configurations in {elapsed:.1f}s ({len(grid)/elapsed:,.0f}/sec) over {n_bars:,} bars\n")

n_trades = np.array([len(r[1]) for r in results])
mean_r = np.array([r[1].mean() if len(r[1]) >= 30 else np.nan for r in results])
ok = n_trades >= 30
print(f"  {ok.sum():,} configurations with >= 30 trades; mean expectancy across them "
      f"{np.nanmean(mean_r[ok]):+.4f}R, best {np.nanmax(mean_r[ok]):+.4f}R")

# ---------------------------------------------------------------------------------------------
# 1. CSCV / PBO. Split into S blocks, train on every half, test on the complement, and ask how
#    often the in-sample winner lands in the BOTTOM half out of sample. Above 0.5 means the
#    selection procedure is picking noise.
# ---------------------------------------------------------------------------------------------
for metric in ("r", "dollars"):
  for S in (10, 12, 16):
      M = block_matrix(results, n_bars, S, metric)
      keep = ~np.isnan(M).any(axis=0) & ok
      Mk = M[:, keep]
      combos = list(combinations(range(S), S // 2))
      below = 0
      for tr in combos:
          te = [b for b in range(S) if b not in tr]
          is_score = Mk[list(tr)].mean(axis=0)
          oos_score = Mk[te].mean(axis=0)
          best = int(np.argmax(is_score))
          rank = (oos_score < oos_score[best]).mean()   # share of configs the winner beat OOS
          if rank < 0.5:
              below += 1
      print(f"  PBO on {metric:>7} at S={S:>2} ({len(combos):,} splits, {Mk.shape[1]:,} configs): {below/len(combos):.3f}")

# ---------------------------------------------------------------------------------------------
# 2. Stationary block bootstrap on the validated configuration. Resampling BLOCKS rather than
#    individual trades keeps the serial dependence that an i.i.d. bootstrap destroys.
# ---------------------------------------------------------------------------------------------
res = simulate(*bars, 60, 50.0, 80.0, 2.0, 0, 0, 0, 1.5, 40.0, *CONST)
r = res[6]
print(f"\n  validated config (ib60 / retr50 / stop80 / 1:2 / both): n={len(r)}, mean {r.mean():+.4f}R")

def block_bootstrap_mean(x, n_paths=10_000, mean_block=5):
    out = np.empty(n_paths)
    n = len(x)
    for p in range(n_paths):
        acc, tot = 0.0, 0
        while tot < n:
            start = rng.integers(0, n)
            ln = min(rng.geometric(1.0 / mean_block), n - tot)
            idx = (start + np.arange(ln)) % n
            acc += x[idx].sum()
            tot += ln
        out[p] = acc / tot
    return out

bs = block_bootstrap_mean(r)
print(f"    block bootstrap (10,000 paths, mean block 5): "
      f"95% CI [{np.percentile(bs, 2.5):+.4f}, {np.percentile(bs, 97.5):+.4f}], "
      f"P(mean <= 0) = {(bs <= 0).mean():.4f}")

# ---------------------------------------------------------------------------------------------
# 3. The search-width curve, on TWO objectives.
#
#    This is the part the speed bought, and it changed the answer. Draw W configurations, pick the
#    best on the first 70% of bars, and record where it ranks on the last 30%. Repeated 700 times
#    per width, at widths up to a third of the grid — enough resolution to see the turning point.
#
#    Run it on mean R and it rises forever. Run it on DOLLARS and it collapses. The difference is
#    the finding: R divides by the stop distance, so a configuration with a tiny stop reports large
#    multiples on very few trades, and a search maximising mean R converges on exactly those.
# ---------------------------------------------------------------------------------------------
cut = int(n_bars * 0.7)
res_r = np.full(len(results), np.nan); hold_r = np.full(len(results), np.nan)
res_d = np.full(len(results), np.nan); hold_d = np.full(len(results), np.nan)
rr3 = (grid.rr_mult >= 3).to_numpy()
for j, (exit_idx, rr_, pnl) in enumerate(results):
    m = exit_idx < cut
    if m.sum() >= 30:
        res_r[j] = rr_[m].mean(); res_d[j] = pnl[m].sum()
    if (~m).sum() >= 30:
        hold_r[j] = rr_[~m].mean(); hold_d[j] = pnl[~m].sum()

for label, res_o, hold_o, fmt in (("mean R", res_r, hold_r, "{:>16.4f}"), ("DOLLARS", res_d, hold_d, "{:>16,.0f}")):
    valid = np.where(~np.isnan(res_o) & ~np.isnan(hold_o))[0]
    print(f"\n  search-width curve, selecting on {label} ({len(valid):,} configs, 700 draws per width)")
    print(f"    {'width':>7}{'holdout pctile':>17}{'median holdout':>16}{'% picked rr>=3':>16}")
    for W in (1, 4, 16, 64, 128, 256, 512):
        if W > len(valid):
            break
        pcts, outs, hi = [], [], 0
        for _ in range(700):
            pick = rng.choice(valid, size=W, replace=False)
            best = pick[np.argmax(res_o[pick])]
            pcts.append((hold_o[valid] < hold_o[best]).mean() * 100)
            outs.append(hold_o[best])
            hi += int(rr3[best])
        print(f"    {W:>7}{np.median(pcts):>17.1f}" + fmt.format(np.median(outs)) + f"{100*hi/700:>15.0f}%")

# The same, with direction removed from the search — the collapse arrives earlier because the grid
# is smaller, so a given width is a larger share of it.
both = (grid.side_mode == 0).to_numpy()
valid = np.where(~np.isnan(res_d) & ~np.isnan(hold_d) & both)[0]
print(f"\n  DOLLARS, both-sides configurations only ({len(valid):,} configs)")
print(f"    {'width':>7}{'holdout pctile':>17}{'median holdout $':>18}")
for W in (1, 4, 16, 64, 128, 256):
    if W > len(valid):
        break
    pcts, outs = [], []
    for _ in range(700):
        pick = rng.choice(valid, size=W, replace=False)
        best = pick[np.argmax(res_d[pick])]
        pcts.append((hold_d[valid] < hold_d[best]).mean() * 100)
        outs.append(hold_d[best])
    print(f"    {W:>7}{np.median(pcts):>17.1f}{np.median(outs):>18,.0f}")
