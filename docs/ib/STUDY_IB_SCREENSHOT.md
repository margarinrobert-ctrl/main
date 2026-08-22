# The TradingView configuration, taken apart

A screenshot of the `NQ IB` Pine strategy's settings panel arrived with a request to run it through
out-of-sample, Monte Carlo and walk-forward testing. The settings in it are **not** the ones the
Pine script ships with, and the differences turn out to matter far more than the strategy does.

| setting | published default | screenshot |
| --- | --- | --- |
| IB window | 09:30–10:30 | 09:30–10:30 |
| flatten time | 15:55 | **11:59** |
| entry retracement | 25% of IB range | 25% |
| stop | 60% of IB range | **80%** |
| target | 50% of IB range beyond the edge | **fixed 1 : 1 against the risk** |
| breakeven move | off | off |
| longs / shorts | both | **longs only** |
| IB range filter | none | none |

Four changes. The rest of this document is about which of the four is doing the work, because the
headline number is much better than the published geometry's and that is exactly the situation in
which a result is most likely to be an artefact.

To test it at all, `initialBalance.ts` needed a `rrMode` / `rrMult` pair: the published target is a
percentage of the IB range measured beyond the broken edge, which floats with the range, whereas the
screenshot's is a fixed multiple of the actual distance from entry to stop. Those are different
orders and cannot be expressed as one another.

## 1. What the configuration does

Session window 09:30–11:59, realistic fill model, full futures costs, one contract, 1-minute bars.

| period | n | win | E | PF | Newey-West t | 95% CI on E | P&L | max DD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| research (first 70%) | 111 | — | 0.163R | — | 2.28 | [0.019, 0.310] | — | — |
| holdout (last 30%) | 57 | — | 0.118R | — | 1.51 | [−0.027, 0.260] | — | — |
| **full** | **168** | **62.5%** | **0.146R** | **1.52** | **2.77** | **[0.044, 0.249]** | **$24,206** | **4.6%** |

On 5-minute bars the same configuration gives n = 167, 59.9% wins, E = 0.169R, PF 1.61, t = 3.29,
$29,702 — close enough to the 1-minute result that the answer is not a resolution artefact. That is
worth stating plainly because most of the failures in this repo did not survive a timeframe change.

Yearly P&L is $356 / $9,608 / $7,720 / $6,522 for 2022 / 23 / 24 / 25. No single year carries it,
which is the first thing that separates this from the earlier IB variants that were entirely 2025.

## 2. Decomposition — the part that matters

Each row below adds exactly one change to the published geometry, then combinations.

| configuration | n | win | E | PF | t | research | holdout |
| --- | --- | --- | --- | --- | --- | --- | --- |
| published (15:55, stop 60, target 50%, both sides) | 529 | 38% | 0.036 | 1.02 | 0.61 | 0.004 | 0.107 |
| + flatten 11:59 only | 349 | 47% | 0.070 | 1.11 | 1.25 | 0.060 | 0.089 |
| + stop 80% only | 529 | 49% | 0.074 | 1.12 | 1.64 | 0.088 | 0.044 |
| + fixed 1 : 1 target only | 529 | 53% | 0.037 | 1.01 | 0.80 | 0.031 | 0.049 |
| **+ longs only** | 261 | 42% | 0.082 | 1.10 | 0.96 | **−0.006** | **+0.255** |
| flatten + stop 80% | 349 | 54% | 0.081 | 1.23 | 1.99 | 0.098 | 0.050 |
| **flatten + stop 80% + fixed 1 : 1** | **349** | **56%** | **0.096** | **1.32** | **2.46** | **0.086** | **0.115** |
| screenshot (all four) | 168 | 63% | 0.146 | 1.52 | 2.77 | 0.163 | 0.118 |
| screenshot but both sides | 349 | 56% | 0.096 | 1.32 | 2.46 | 0.086 | 0.115 |
| screenshot but shorts only | 181 | 51% | 0.050 | 1.19 | 0.99 | 0.020 | 0.113 |

Read the last two columns, not the first six.

**The three structural changes are consistent.** Flatten 11:59, stop 80%, fixed 1 : 1 — each is
positive in isolation, and together they give E = 0.096R at t = 2.46 with **0.086 in the research
half and 0.115 in the holdout half**. Same sign, same magnitude, on both sides of a split they were
not chosen on. Each also has a mechanism that existed before the number did:

- *Flatten 11:59* stops the strategy holding a morning-auction position through the afternoon, when
  the reference level it was trading against is six hours stale. It cuts sample size by a third and
  raises expectancy — the discarded trades were worse than the kept ones.
- *Stop 80%* moves the stop outside the noise band of the retracement it is entering on. A 60% stop
  sits inside the range the entry is a pullback into; the trade is stopped by the same oscillation
  that filled it. This is visible as the win rate jumping 38% → 49% on that change alone.
- *Fixed 1 : 1* decouples the target from the IB range. The published target scales with the range
  while the risk does too, so on wide-range days the geometry demands a much larger absolute move
  for the same R. Fixing the ratio removes that.

**The direction filter is not.** Longs-only in isolation scores **−0.006 in the research half and
+0.255 in the holdout half.** That is not an edge that strengthened; that is a filter that is
capturing NQ's own drift and whose entire measured value sits in the recent, rising half of the
sample. This repo has now produced that exact signature four separate times — the earlier IB study
flagged longs-only at research t = −0.61 / holdout t = +1.96 and rejected it on the same grounds,
and every parameter search handed `sideMode` as a free choice picked longs.

The screenshot's edge over the structural trio is +0.050R per trade. All of it comes from the one
component that fails the consistency test.

**Shorts are not the problem, either.** With shorts re-enabled the short side runs E = 0.050R at
t = 0.99 on n = 181 — weak, but positive and positive in both halves (0.020 / 0.113). Turning them
off does not remove a losing book. It removes a mildly profitable one and halves the sample.

## 3. Period stability — every quarter, both configurations

Same trade stream, bucketed by calendar quarter of entry. Nothing is re-fitted.

| quarter | screenshot (longs only) | | | structural trio (both sides) | | |
| --- | --- | --- | --- | --- | --- | --- |
| | n | E | P&L | n | E | P&L |
| 2022Q4 | 1 | 0.352 | $356 | 1 | 0.352 | $356 |
| 2023Q1 | 8 | 0.382 | $4,226 | 25 | 0.124 | $3,950 |
| 2023Q2 | 11 | 0.611 | $5,129 | 28 | 0.160 | $2,978 |
| 2023Q3 | 7 | 0.030 | $487 | 21 | 0.176 | $4,819 |
| 2023Q4 | 19 | 0.013 | −$234 | 37 | −0.066 | −$2,311 |
| 2024Q1 | 13 | 0.064 | −$760 | 26 | 0.045 | $699 |
| 2024Q2 | 13 | 0.123 | $2,593 | 25 | 0.134 | $4,370 |
| 2024Q3 | 14 | 0.049 | $1,262 | 33 | −0.020 | −$395 |
| 2024Q4 | 15 | 0.146 | $4,625 | 25 | 0.186 | $6,978 |
| 2025Q1 | 20 | 0.137 | $2,360 | 35 | 0.144 | $6,683 |
| 2025Q2 | 18 | 0.014 | −$1,907 | 33 | −0.048 | −$2,092 |
| 2025Q3 | 18 | 0.198 | $3,506 | 32 | 0.258 | $10,062 |
| 2025Q4 | 11 | 0.191 | $2,564 | 28 | 0.148 | $1,313 |
| **total** | **168** | **0.146** | **$24,206** | **349** | **0.096** | **$37,410** |

Both are positive in 10 of 13 quarters. They lose in the same quarters (2023Q4, 2025Q2), which is
what you would expect if they are the same trade with a different filter rather than two edges.

The trio has the lower per-trade expectancy and **55% more money**, because it takes twice the
trades. Per-trade expectancy is the wrong thing to maximise when the constraint is one contract and
a market that only offers a setup a few dozen times a quarter.

## 4. Monte Carlo

20,000 paths, $50,000 starting equity, one contract, on the screenshot configuration's 168 trades.

| method | median DD | 95th pct DD | P(losing) | P(25% DD) | median P&L | 5th pct P&L |
| --- | --- | --- | --- | --- | --- | --- |
| order reshuffle | 10.8% | 17.7% | 0.0% | — | — | — |
| resample with replacement | 10.9% | 22.2% | 1.9% | 2.7% | $24,453 | $4,821 |

The gap between the realised 4.6% drawdown and the 10.8% median across reshuffles is the honest
number: the actual sequence of wins and losses was a lucky one, and a re-ordering of the *same
trades* would more than double the worst stretch. Anyone sizing off the backtest's drawdown would
be sizing off the single most flattering ordering of 168 results.

The resample tail is what to plan against: 22.2% drawdown at the 95th percentile, and a 5th
percentile outcome of $4,821 over four years. Positive, but not a business.

## 5. Walk-forward — and the result nobody asks for

Two different questions get called "walk-forward" and they have opposite answers here.

**The screenshot's geometry is pre-specified.** Its user is not re-optimising anything; they set ten
numbers once and leave them. For that person the relevant test is section 3 — sequential periods,
nothing re-fitted — and it passes at 10/13 quarters.

**But the numbers came from somewhere.** If the honest counterfactual is "somebody tunes this
strategy on the data available to them and trades what they find", then the test has to include the
cost of choosing. Each fold below re-searches the full ten-dimensional geometry (3,000 configurations
per fold) on its training window and trades the next, unseen window with whatever won.

### Rolling, 250 training days / 60 test days — 8 folds, 24,000 trials

| fold | IS Sharpe | OOS Sharpe | n | P&L | parameters chosen |
| --- | --- | --- | --- | --- | --- |
| 0 | 4.004 | 0.987 | 8 | $1,121 | ib 60, retr 50, stop 100, rr 1.5, longs, rng 0–80 |
| 1 | 3.464 | −2.769 | 5 | −$1,325 | ib 60, retr 50, stop 80, rr 2, longs, buf 4 |
| 2 | 2.721 | 1.103 | 3 | $963 | ib 60, retr 50, stop 100, rr 1, longs, buf 4 |
| 3 | 2.669 | 2.484 | 18 | $7,423 | ib 30, retr 10, stop 60, rr 1.5, **shorts**, rng 20–80 |
| 4 | 2.929 | −1.533 | 12 | −$2,018 | ib 45, retr 50, stop 100, tgt 50%, both |
| 5 | 2.582 | 1.507 | 22 | $4,945 | ib 30, retr 50, stop 100, rr 1, both |
| 6 | 2.765 | 1.839 | 27 | $3,955 | ib 30, retr 40, stop 80, rr 1.5, both |
| 7 | 3.079 | −0.387 | 10 | −$483 | ib 60, retr 50, stop 80, rr 1, both, buf 4 |

Stitched out-of-sample: **n = 105, 55.2% wins, E = 0.108R, t = 1.19, 95% CI [−0.042, 0.274],
$14,580**, max DD 10.3%, PF 1.353. Walk-forward efficiency **0.376** — median OOS Sharpe is barely a
third of median IS Sharpe, which is the standard threshold for "the fit does not transfer". Fold hit
rate 63%.

Now the comparison that makes the point. Over **exactly the same stitched out-of-sample bars**, with
no optimisation at all:

| | n | win | E | t | 95% CI | P&L |
| --- | --- | --- | --- | --- | --- | --- |
| re-optimised walk-forward | 105 | 55.2% | 0.108R | 1.19 | [−0.042, 0.274] | $14,580 |
| fixed screenshot config | 118 | 62.7% | 0.099R | 1.62 | [−0.014, 0.215] | $10,383 |
| **fixed structural trio** | **225** | **58.2%** | **0.100R** | **2.14** | **[0.016, 0.181]** | **$27,253** |

**Re-optimising every 60 days destroys value.** The fixed trio earns nearly twice the money of the
re-optimised system over the same period, and it is the only one of the three whose confidence
interval excludes zero. The search is not finding better parameters; it is finding the previous 250
days' noise and paying for it 60 days at a time.

Two details in the fold table are worth more than the summary:

- **`sideMode` stability is 50%.** The optimiser picks longs in folds 0–2, *shorts* in fold 3, and
  both sides in folds 4–7. A parameter that flips sign between adjacent training windows is not a
  parameter, it is a coin. This is the fifth independent demonstration in this repo that direction
  cannot be fitted on 2022–25 NQ.
- **`rrMode` stability is 88%.** The optimiser almost always independently chooses the fixed
  reward-to-risk target over the published range-scaled one. That is the screenshot's most defensible
  change, confirmed by a search that had no knowledge of it.

Also note fold 0: in-sample Sharpe 4.004 → out-of-sample 0.987. Every fold's in-sample Sharpe sits
between 2.6 and 4.0 and means nothing at all.

### Rolling, 400 training days / 90 test days — 3 folds, 9,000 trials

Longer training windows, fewer folds, so this is a weaker test — but it points the same way.

| | n | win | E | t | 95% CI | P&L |
| --- | --- | --- | --- | --- | --- | --- |
| re-optimised walk-forward | 62 | 53.2% | 0.127R | 1.50 | [−0.037, 0.289] | $9,437 |
| fixed screenshot config | 70 | 60.0% | 0.079R | 1.18 | [−0.052, 0.211] | $5,263 |
| fixed structural trio | 131 | 55.0% | 0.073R | 1.33 | [−0.038, 0.177] | $12,786 |

Efficiency 0.533, fold hit rate 100%, max DD 6.5%. The re-optimised system wins on per-trade
expectancy and loses on money, for the same reason as before: it trades half as often. `retrPct`
stability is 100% here — every fold picks a 50% retracement, deeper than the screenshot's 25%, which
is the one place a search consistently disagrees with the configuration under test.

### Anchored, 250 training days / 60 test days — 8 folds, 24,000 trials

Anchored means the training window never drops old data; every fold trains on everything from the
start of the sample. This is the configuration most people actually run, and it fails the hardest.

| | n | win | E | t | 95% CI | P&L |
| --- | --- | --- | --- | --- | --- | --- |
| re-optimised, anchored | 53 | 58.5% | 0.161R | 1.82 | [0.013, 0.317] | **$1,423** |
| fixed screenshot config | 118 | 62.7% | 0.099R | 1.62 | [−0.014, 0.215] | $10,383 |
| fixed structural trio | 225 | 58.2% | 0.100R | 2.14 | [0.016, 0.181] | $27,253 |

Efficiency 0.359, fold hit rate 63%, PF 1.077, max DD 12.7%. Per-trade expectancy is the highest of
the three and the total P&L is **$1,423 across two and a half years** — 5% of what the same geometry
earns fixed. The filters the search keeps adding are so restrictive that 53 trades survive, and one
bad fold (fold 5, −$6,572) wipes out most of the rest.

The parameter-stability line is the clearest result in this document: **`sideMode` stability is
100%. Every single fold picks longs only.** Anchored training always contains the early, strongly
rising part of the sample, so the optimiser reaches the same conclusion every time — and it is the
conclusion the decomposition in section 2 already showed to be drift-fitting. Anchored walk-forward
does not protect against a drift-fitted parameter; it guarantees it.

`retrPct` is 88% stable at 50%, its third independent appearance across the three walk-forward
configurations, and `ibMinutes` is 100% stable at 60. Those two are the folds' real signal.

Fold 6 is worth a look for anyone inclined to trust in-sample numbers: it has the *worst* in-sample
Sharpe of the eight (1.919) and the best out-of-sample one (4.129). The rank correlation between the
two columns is, for practical purposes, absent.

## 6. Following the walk-forward's one consistent disagreement

The folds agreed on almost nothing except this: **every stable fold picked a 50% retracement, not
25%** — 100% parameter stability in the 400/90 configuration, 75% in the 250/60 one. That is a
search, with no knowledge of the screenshot, repeatedly disagreeing with one specific setting. Worth
testing directly.

Retracement depth, both sides, everything else held at the structural trio:

| retracement | n | win | E | PF | t | 95% CI | P&L | max DD | research | holdout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10% | 508 | 52.6% | 0.046 | 1.21 | 1.66 | [−0.006, 0.094] | $40,573 | 17.0% | 0.056 | 0.023 |
| 25% (screenshot) | 349 | 56.4% | 0.096 | 1.32 | 2.46 | [0.028, 0.166] | $37,409 | 14.4% | 0.086 | 0.115 |
| 40% | 222 | 56.8% | 0.100 | 1.12 | 1.78 | [−0.005, 0.201] | $8,930 | 18.8% | 0.147 | −0.002 |
| **50%** | **167** | **60.5%** | **0.246** | **1.57** | **3.37** | **[0.108, 0.383]** | **$22,502** | **10.8%** | **0.303** | **0.112** |

A deeper retracement more than doubles per-trade expectancy, raises the win rate, and *halves* the
drawdown. It is positive in both halves and the confidence interval clears zero comfortably. It is
also the highest t-statistic produced anywhere in this study — **without a direction filter.**

The mechanism is the same one that made the 80% stop work. A 25% pullback is barely inside the
range; the entry is close to the broken edge and the stop is a long way below it. A 50% pullback
buys the same directional resolution at the middle of the auction, which is both a better price and
a shorter distance to the stop. The trade risks less for the same target.

Two honest caveats. First, research 0.303 versus holdout 0.112 — the effect is real in both halves
but **the holdout is a third of the research half**, which is the standard overfitting signature and
means 0.246R is an optimistic point estimate. Second, this came out of a small search (4 × 4 × 4 × 4
= 256 geometries) that the holdout was used to check, so the holdout is no longer fully clean.

Holding retracement at 50% and sweeping the other three:

| IB length | n | E | t | research | holdout | | R:R | n | E | t | research | holdout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 30m | 365 | 0.037 | 0.70 | 0.034 | 0.043 | | 1 : 1 | 167 | 0.246 | 3.37 | 0.303 | 0.112 |
| 45m | 238 | 0.135 | 1.85 | 0.176 | 0.024 | | 1 : 1.5 | 167 | 0.297 | 3.73 | 0.370 | 0.128 |
| **60m** | 167 | 0.246 | 3.37 | 0.303 | 0.112 | | **1 : 2** | 167 | **0.325** | **3.84** | 0.414 | 0.116 |
| 90m | 68 | 0.317 | 2.22 | 0.387 | 0.169 | | 1 : 3 | 167 | 0.266 | 2.87 | 0.368 | 0.029 |

The screenshot's 60-minute IB is the right choice and needs no defending — it is the standard
definition and it wins anyway. The R:R sweep is more interesting: pushing the target to 1 : 2 raises
expectancy to 0.325R at t = 3.84 while *lowering* drawdown to 8.8%, and holds 0.116 in the holdout.
The win rate falls to 55.7%, which is the trade-off, but the 1 : 1 constraint is not doing any work.

Stop depth confirms 80% is the right pick and not a lucky one: 60% gives t = 1.49 with holdout 0.057,
100% gives t = 2.59 with holdout 0.025, and 80% is better than both on every measure. (A 40% stop at
a 50% retracement produces zero trades — the stop would sit on the wrong side of the entry, which is
the geometry telling you the configuration is incoherent rather than a bug.)

### Monte Carlo on the 50%-retracement version

20,000 paths, $50,000, one contract, 167 trades, both sides.

| method | median DD | 95th pct DD | P(losing) | P(25% DD) | median P&L | 5th pct P&L |
| --- | --- | --- | --- | --- | --- | --- |
| order reshuffle | 8.3% | 13.5% | 0.0% | — | — | — |
| resample | 8.4% | 16.5% | 0.8% | 0.4% | $22,677 | $6,742 |

Better than the screenshot configuration on every risk measure — 16.5% versus 22.2% at the 95th
percentile, 0.4% versus 2.7% chance of a 25% drawdown, and a 5th-percentile outcome of $6,742
against $4,821 — while using no direction filter at all.

Quarterly: 11 of 13 positive, but with a **−$8,076 in 2025Q4** that the screenshot configuration
does not have. Deeper retracements mean fewer, larger trades, and the concentration shows up as a
worse worst quarter. That is a real cost and not one the summary statistics make obvious.

## 7. Bottom line

The screenshot configuration is genuinely better than the published Pine defaults, and three of its
four changes are the reason. **Flatten at 11:59, an 80% stop, and a fixed reward-to-risk target are
each defensible before the fact and consistent across both halves of the sample.** Together they
turn a t = 0.61 non-result into a t = 2.46 result with 0.086 research / 0.115 holdout.

**The longs-only filter should be turned off.** It is the largest single contributor to the headline
number and the only component that fails the consistency test (−0.006 research / +0.255 holdout).
Turning it off costs 0.050R per trade and earns $37,410 instead of $24,206, because it doubles the
sample. The shorts being excluded are mildly profitable, not losers.

**The retracement should be 50%, not 25%**, on the evidence of a walk-forward that had no knowledge
of the setting and picked it in every stable fold, and a direct test that shows double the
expectancy, a higher win rate and a smaller drawdown. Consider 1 : 2 rather than 1 : 1 on top of it.

**Do not re-optimise this strategy on a rolling window, and especially not an anchored one.** That
is the clearest finding here. Over identical out-of-sample bars:

| | P&L | t | 95% CI |
| --- | --- | --- | --- |
| re-optimised, rolling 250/60 | $14,580 | 1.19 | [−0.042, 0.274] |
| re-optimised, anchored 250/60 | $1,423 | 1.82 | [0.013, 0.317] |
| **fixed structural trio, no optimisation** | **$27,253** | **2.14** | **[0.016, 0.181]** |

Walk-forward efficiency was 0.376 and 0.359. The parameters are not the alpha; searching for them is
a cost, and anchored search is the worse of the two because it locks in the sample's drift.

What none of this changes: this is 168–349 trades over four years on one instrument, the holdout has
now been looked at, and every expectancy quoted above is an optimistic point estimate. The
strategy has a mechanism and survives a battery it could have failed. It is not a demonstrated edge
and the section-3 quarterly table — not the equity curve — is the thing to watch forward.
