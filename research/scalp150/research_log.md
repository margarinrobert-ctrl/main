# PF 1.50, 07:00–11:00 scalp — research log

## Question
Can a simple 07:00–11:00 New York scalp hold profit factor 1.50?

## What was run (NQ 15m resampled from `data/NQ_1m.csv`, split 2025-03-17, cost 1.72 pts round turn)

| # | configuration | research PF | holdout PF | note |
|---|---|---|---|---|
| 1 | Donchian 10/10, 3.19 ATR stop, 2.3 ATR target, 230-min cap | 0.969 | 0.900 | reconstruction of `STUDY_BAYESOPT_SCALP`'s cell — see caveat |
| 2–401 | 5×4×4×5 grid: entry {5,10,20,40,80} × exit {5,10,20,40} × stop {1.5,2.5,3.19,5.0} × target {0,1.5,2.3,4.0,8.0} | 0.63–1.16 | 0.42–1.05 | 400 scorable cells |
| — | random entry in the same window, same geometry, 50 seeds | PF 0.929 | PF 0.992 | rule fails on the holdout at p 0.640 |

## Results

- **PF 1.50 requires a 68.6% win rate** at the tested geometry (R = 0.721, measured cost/risk 0.0200),
  against a driftless break-even of 59.3% — a **+9.3 point** lift. The rule's actual win rate is 56.5%.
- **0 of 400 cells reach PF 1.50 on the research block**, the block permitted to be optimistic.
  Best research PF anywhere in the grid: **1.159**, and that cell reads **0.631** on the holdout.
- `corr(research PF, holdout PF) = **−0.267**` — selecting on the research block is worse than not
  selecting.
- Only **24.2%** of cells are research-profitable; **7 of 400 (1.8%)** clear PF 1.00 on both blocks,
  which is *below* the 2.8% expected if the two blocks were independent coin flips.
- Best cell profitable on both: entry 20 / exit 10 / stop 1.5 ATR / target 8 ATR — **PF 1.036
  research, 1.048 holdout** at 376 trades/yr.
- Marginal averages: no axis has a setting whose research preference survives on the holdout. The
  entry channel runs 80 → research 1.051 / holdout **0.734**, the clearest inversion in the table.

## Caveat that must stay attached

Configuration 1 is **not a reproduction** of `STUDY_BAYESOPT_SCALP`'s published cell. That study
reports 387 research trades at PF 1.13; this build produces **1,019** at PF 0.969 on the same
parameters. A 2.6× trade-count gap means the two are different strategies wearing the same parameter
names — most likely a different channel or position-lock construction in the original evaluator.
Nothing here falsifies that study's number; it measures this build, and the frontier result below
does not depend on configuration 1 at all.

---

## Round 2 — the wide pre-declared search (`run_p2.py`)

Grid declared in `pf150.GRID` before any cell was scored: 3 timeframes (5/15/30m) × 3 sides
(long / short / both) × 3 stops (1.5/2.5/4.0 ATR) × 4 targets (none/1.5/3.0/6.0 ATR) × 9 triggers
(4 Donchian channel pairs + 5 CMMA mean-reversion settings) = **972 cells**. Entries 07:00–11:00
New York, nothing held past 4 hours, fill at the next bar's open, 1.72 pts round turn.

### Population

| | |
|---|---|
| scorable cells | 972 |
| research-profitable (PF > 1.00) | 23.3% |
| **research PF ≥ 1.50** | **0** |
| research PF ≥ 1.50 **and** holdout ≥ 1.50 | 0 |
| PF > 1.00 on both blocks | 124 (12.8%) vs 7.6% by chance |
| corr(research PF, holdout PF) | +0.262 Pearson / +0.238 Spearman |
| **gross** research-profitable | 45.1% — cost is **not** the binding constraint |

### Declared best, one holdout read

30m Donchian 40/20, long only, 2.5 ATR stop, no target:
research PF **1.310** (226 trades, 102/yr) → holdout PF **0.843** (71 trades).
Gross 1.367 → 0.873. Deflated Sharpe **0.3081** at 972 trials (E[max SR | noise] 0.1446 against
an achieved 0.1121) — **FAIL**.

Top-10 research mean PF 1.238 → holdout 0.915, against a whole-population holdout mean of **0.963**.
The research top decile does *worse* out of sample than an average cell.

### Marginals (research PF / holdout PF)

| axis | values |
|---|---|
| timeframe | 5m 0.908/0.924 · 15m 0.935/0.940 · 30m 0.944/1.025 |
| family | CMMA 0.891/0.948 · Donchian 0.977/0.982 |
| **side** | short 0.854/0.892 · both 0.932/0.941 · **long 1.001/1.057** |
| stop | 1.5 0.924/0.958 · 2.5 0.929/0.973 · 4.0 0.934/0.958 |
| target | none 0.965/0.994 · 1.5 0.888/0.907 · 3.0 0.917/0.967 · 6.0 0.946/0.985 |

The only axis with a positive marginal on both blocks is **long-only**, on a sample where NQ rose
88%. That is drift, not a scalping edge. No-target beats every target again (25th time on this
branch).

## Combined verdict across both rounds

**1,372 cells evaluated. Zero reach PF 1.50 on the research block**, which is the block permitted
to be optimistic. The requirement is arithmetic: PF 1.50 needs a +9.3 point win-rate lift over the
driftless break-even at scalp geometry, and the honest lifts measured on this branch are +1 to +5.
