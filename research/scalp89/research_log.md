# NQ Scalping System — research log

Every configuration evaluated, so the trial count feeds the deflated Sharpe rather than being
guessed afterwards. Research block only unless marked LOCKED READ.

| # | What | Cells | Where |
| --- | --- | ---: | --- |
| 1 | as configured (screenshot values), NQ 5m | 1 | `run_a` §1 |
| 2 | exit machine variants: trail off / ATR trail / 30-15 / 60-30 / no target / stop only | 6 | `run_a` §1 |
| 3 | order-model gaps: protect_fill × path | 4 | `run_a` §2 |
| 4 | entry ablation: drop one of five conditions, plus long-only and short-only | 7 | `run_a` §3 |
| 5 | session: six windows / flatten combinations | 6 | `run_a` §4 |
| 6 | feeds × timeframes × {configured, trail off} — both blocks read | 8 configs, **8 LOCKED READS** | `run_b` |
| 7 | fixed-horizon forward return, 6 horizons × 2 sides | 12 tests | `run_c` §1 |
| 8 | matched random-entry controls, 2 configs | 2 | `run_c` §2 |
| 9 | geometry sweep on the short and long entry: 4 stops × 5 targets × 4 holds × 2 sides | 160 | `run_d` |
| 10 | cross-feed fixed-horizon signal test, 4 feed-tf × 2 blocks × 3 horizons × 2 sides | 48 tests, **24 on locked/unseen** | `run_e` |

Running total: **~200 research-block configurations and ~32 locked-block reads.** The locked reads
in row 6 were spent on the configured script and its trail-off twin before any selection was made
on research; row 10's locked reads are of a pre-declared test (the short side at 15–30 min) on
blocks that had no part in noticing it.

## Decisions so far

- The screenshot's values override the code defaults; the material difference is **"Always use
  Fixed Points for Trail" = ON**, pinning the trail to 15 / 8 points regardless of ATR.
- Bar frequency is unstated. 1m / 5m / 15m all run; 5m is the working base.
- MNQ economics: $2/pt, 0.25 tick, 0.86 pts a side (0.25 spread + 0.25 slip + 0.36 fees).
- The script has no session flatten — positions carry until stop / target / trail. Modelled as
  written; a flatten was tested as a variant (§5) and is neutral.

## Final count

| # | What | Cells | Locked reads |
| --- | --- | ---: | ---: |
| 11 | Monte Carlo on the trail-off variant: execution 1,000 draws, price jitter 3 levels × 150, permutation 5,000, bootstrap 5,000 | perturbations, not selections | both blocks read for the one pre-chosen variant |
| 12 | walk-forward, 729 declared cells × 9 folds × 2 schemes, selection inside each fold | 729 | 9 test quarters, 4 of which postdate the block cut |

**Total: ~1,100 research-block configurations evaluated; 32 locked-block reads of pre-declared
configurations; 0 configurations selected on the locked block.**

## Decisions

- **Ship**: the corrected order model only (trail off, fill bar protected, isconfirmed guard).
  No parameter of the submission was changed on the basis of performance.
- **Do not ship**: any geometry from the 160-cell sweep (0/80 net-positive on the short side; the
  long side's positives are no-target no-hold drift) or any cell from the walk-forward (a random
  cell beats the re-chosen one).
- **Verdict**: no edge. The deflated Sharpe is not computed because the observed Sharpe is negative
  on research under every perturbation — there is nothing to deflate.
