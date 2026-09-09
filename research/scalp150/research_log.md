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
