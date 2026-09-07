# The cost of search width

> Generated 2026-08-22T14:26:36.834Z · seed `20250822` · data/NQ_5m.csv

Every study in this repository reached the same conclusion from a different direction: the pre-specified rule beat the optimised one, and PBO ranged from 0.23 to 0.97. This measures that directly. **6,771 configurations** of the gap-fade strategy were evaluated on both halves. For each search width *k*, a random subset of *k* configurations is drawn, the best is chosen by IN-SAMPLE score exactly as an optimiser would, and what that choice actually earned OUT OF SAMPLE is recorded — averaged over 600 draws.

Sessions: 764 (research 534, holdout 230). Configurations with fewer than 20 trades in either half are discarded.

| configurations searched | IS E(R) of the pick | OOS E(R) of the pick | **OOS percentile of the pick** | % landing below the OOS median | IS minus OOS |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.014 | 0.132 | 48.8 | 54% | -0.118 |
| 2 | 0.070 | 0.153 | 53.9 | 44% | -0.084 |
| 5 | 0.131 | 0.207 | 62.7 | 30% | -0.077 |
| 10 | 0.177 | 0.233 | 65.7 | 25% | -0.056 |
| 25 | 0.226 | 0.278 | 71.3 | 18% | -0.051 |
| 50 | 0.266 | 0.292 | 72.2 | 16% | -0.025 |
| 100 | 0.305 | 0.343 | 75.7 | 15% | -0.037 |
| 250 | 0.352 | 0.314 | 73.8 | 17% | 0.038 |
| 500 | 0.388 | 0.283 | 74.6 | 15% | 0.105 |
| 1000 | 0.413 | 0.278 | 78.1 | 7% | 0.135 |
| 2500 | 0.437 | 0.329 | 84.6 | 0% | 0.107 |

The column that matters is the **OOS percentile**. 50 means the in-sample winner is, out of sample, an average configuration — the search learned nothing. Above 50 means selection carries information; below 50 means it is actively harmful. The raw OOS score column is shown only to make the confound visible: the holdout period was kinder to nearly every configuration, so raw scores drift upward regardless of whether the search worked.

| reference | IS E(R) | OOS E(R) | n (OOS) |
| --- | --- | --- | --- |
| **pre-specified configuration (no search)** | 0.094 | **0.312** | 61 |
| average of all configurations | 0.014 | 0.131 | — |
| best configuration by OOS score (unknowable in advance) | — | 1.466 | — |

## Reading it

**1. In-sample scores are guaranteed to climb.** Taking the maximum of more draws can only go up, so the IS column rising from 0.014 to 0.437 says nothing about anything. It is arithmetic, not evidence.

**2. Selection here IS informative about ranking.** The out-of-sample percentile of the pick rises from 48.8 at a single configuration to 84.6 at 2500 — well above the 50 that pure noise would produce. Searching does find a better REGION of this parameter space, which was not the expected result and is worth stating plainly.

**3. And it buys almost nothing over not searching.** The pre-specified configuration earns 0.312 out of sample. A search over hundreds or thousands of configurations delivers between 0.278 and 0.343 — the same neighbourhood, for a great deal more work and a great deal more confidence in a number that is not real.

**4. The expectation gap is the real cost.** At the widest search the pick scored 0.437 in sample and 0.329 out of sample. Anyone reporting the in-sample figure as their expected edge is overstating it by roughly 0.107 R per trade.

**5. Reconciling this with PBO 0.968.** The full protocol reported a probability of backtest overfitting of 0.968 for this strategy, which sounds like a flat contradiction of point 2. It is not — the two measure different things. PBO scrambles blocks WITHIN the research period and asks whether an in-sample winner stays a winner across those recombinations; it says you cannot pick a best configuration inside that period. This curve asks whether the winner chosen on the research period lands high in the holdout period; it says the broad parameter region persists forward. Both are true. The region is real; the specific winner inside it is noise.

Runtime 1.0s.
