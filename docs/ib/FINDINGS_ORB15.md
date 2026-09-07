# 9:30–9:45 opening range on NQ — what the search found

Full report: [`STUDY_ORB15.md`](STUDY_ORB15.md). Strategy: `src/lib/quant/strategies/openingRange.ts`.

1-minute NQ, Dec 2022 – Dec 2025, 766 RTH sessions split 537 research / 229 holdout. Entries
modelled conservatively (a bar must *close* beyond the level, then fill at the next open — a real
resting stop order fills mid-bar and better). Costs 1 tick spread + 1 tick slippage per side + $4.

## The answer: no edge, and the reason is specific

### 1. Six pre-specified variants

| variant | research | holdout |
| --- | --- | --- |
| **A** break, stop at opposite edge, target 100% of range | +6.0t, PF 1.05, t=0.56 | +50.6t, PF 1.31, t=1.60 |
| B break, stop at opposite edge, hold to close | +9.8t, PF 1.06, t=0.67 | +61.1t, PF 1.29, t=1.12 |
| C break, stop 50%, target 100% | +0.9t, t=0.11 | +12.4t, t=0.57 |
| D break, stop 50%, target 200% | +2.0t, t=0.20 | +3.4t, t=0.13 |
| **E retracement 25% (the IB rule)** | **−8.4t, PF 0.88** | **−14.3t, PF 0.86** |
| F break, narrow OR only | +2.2t, t=0.21 | +32.6t, t=1.17 |

Nothing reaches significance in either half.

### 2. The long/short split kills it

Variant A, decomposed:

| | research | holdout |
| --- | --- | --- |
| all | n=536, meanR **+0.016**, t=0.49 | n=227, meanR **+0.110**, t=1.90 |
| long | n=273, meanR **−0.011**, t=−0.21 | n=114, meanR **+0.213**, t=**3.03** |
| short | n=263, meanR **+0.044**, t=0.83 | n=113, meanR **+0.007**, t=0.07 |

**The sides flip completely between halves.** Longs lose over the research period and then produce
$51,807 of the holdout's $57,435. Shorts are the (weak) research edge and contribute nothing to the
holdout. The only t-statistic above 2 anywhere in this study is the holdout long side — which is
the NQ uptrend in 2025, not a property of the opening range.

This is also what the parameter search kept rediscovering: every strong configuration it found set
`sideMode=1`. The optimiser was not finding an edge in the setup, it was finding the index.

### 3. Optimising it is actively harmful

| | result |
| --- | --- |
| best of 800 configurations, in-sample | Sharpe 1.32, **+102.6 ticks/trade**, 77 trades |
| parameter surface | **spike** — an isolated peak, no surviving neighbours |
| same procedure, walk-forward | Sharpe −0.12, **−3.6 ticks/trade**, PF 0.967 |
| probability of backtest overfitting | **0.829** |
| deflated Sharpe | 0.013 |

PBO of 0.83 means that four times out of five, the configuration that looked best in-sample landed
in the *bottom half* out of sample. The search is a noise generator on this setup.

**On the holdout, the untuned rule beat the tuned one outright:** published geometry +50.6 ticks
versus the in-sample optimum's +20.6 and the walk-forward modal's +22.4. Tuning cost roughly 30
ticks per trade of out-of-sample performance.

### 4. Monte Carlo (20,000 paths, $50k)

Median max drawdown 28.2%, 95th percentile 41.5%, P(ending below start) 100% on reshuffle,
P(25% drawdown) 70.3%.

### 5. The anomaly that survived FDR and still failed

Twenty-two day-features tested for lift against the rest of the trades:

- **"Opening range expanding vs yesterday" (>1.25×)** — research n=161, lift **+0.265R, t=3.37,
  p=0.0007, q=0.018**. It survives Benjamini-Hochberg across all 22 buckets.
- The same filter on the holdout: n=67, meanR 0.089, against **0.110 for all holdout trades**. The
  lift is *negative* out of sample. It did not replicate.

Meanwhile "medium OR range percentile", which did **not** survive FDR in research (q=0.442), came in
at meanR 0.195, t=1.97 on the holdout — better than the survivor.

FDR control across 22 tests was not enough protection. The only thing that would have caught this
was doing what was done here: holding back data and checking.

## Two results worth keeping

**The retracement entry does not work on a 15-minute range.** Variant E loses in *both* halves
(−8.4t and −14.3t), the only consistent result in the study. A consistent negative is worth more
than an inconsistent positive. On the hour-long initial balance the retracement is the published
rule and roughly breaks even; on a 15-minute range the break runs and does not come back. **Do not
port the edgeful IB geometry onto a 15-minute window** — it is a different mechanism.

**Direction should not be a free parameter.** Any optimiser handed `sideMode` on 2022–2025 NQ data
will return "longs only" and will be fitting the index, not the setup. If a directional restriction
is ever justified it has to come from a mechanism, not from a backtest.

## Where an edge could still be, honestly

Nothing in this study is close. The productive directions are not more parameter tuning:

1. **Order flow at the break** — volume, delta, or book imbalance in the breaking minute separates a
   genuine repricing from a stop run. This study only has OHLCV, and OHLCV-only rules compete with
   everyone who has the same OHLCV.
2. **A cheaper cost regime** — resting the entry rather than taking it. The `passive` fill model
   exists for exactly this test.
3. **A different instrument or a later sample.** Given the long/short flip, the single most
   informative next test is running the same pre-specified variants on ES or CL, where a 2023–25
   equity uptrend cannot manufacture the result.
