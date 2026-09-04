# NQ Scalping System — evaluation

> Research tooling for education and analysis. Nothing here is financial advice.

## Verdict

**The strategy is not profitable on this data. Its entire backtested profit comes from
assuming a price path inside the 15-minute bar that the data does not contain.**

With the trailing stop allowed to arm and fire within the bar that opened the trade — which is
what a bar-level backtester does by default — the strategy earns
+2.75 to +4.10 points per trade on the research block.
Refuse to make any claim about the order of prices inside a bar, and let the trail update only from
bars that have closed, and the same signals on the same data earn
-1.31 to -0.55 points per trade. Turn the trailing stop off entirely and
it is -1.86 to -1.16.

The signal itself is not worthless: entries beat random entries with identical geometry, session
and side mix by about +0.5 to +1.6 points per trade, consistently, under every convention. But the
gross edge under the honest model is +0.45 points per trade against a 1.74-point round turn on the
configured micro contract. **Costs are roughly four times the edge.**

On the holdout, **0 of 7 pre-registered comparisons pass**, and the decisive number is this: out of
sample, random entries pushed through the same trailing stop earn +4.50 points per trade while the
strategy earns +4.70. The signal's advantage over random, +1.60 points on the research block,
becomes +0.20 on the holdout. The exit mechanic is doing the work, and the mechanic is a modelling
assumption.

**And it does not replicate on a second instrument.** Run unchanged on US30, the strategy's excess
over the matched control is negative in every configuration tested, at p 0.79 to 0.95. The one
configuration that looked promising on NAS — the 09:31–11:00 window — is +0.323 ATR gross there and
**−0.210 ATR** on the Dow. A real intraday effect should not be present on the Nasdaq and inverted on
its near-twin. See §19.

What would change my mind: 1-minute or tick data, so the trailing stop can be resolved on a real
path instead of bracketed, *and* a version of the entry that survives on both instruments. Neither
exists yet.

## Setup

Nasdaq 15-minute bars · 206,703 bars · 2016-11-14 → 2025-10-01 · 2,747 sessions ·
research block first 65% of sessions (1,785, to 2022-08-29), holdout last 35% (962) ·
5 contracts, $2/point (MNQ), $1.24/contract/order, 1 tick slippage — the settings in the
screenshots · session 06:00–11:30 Chicago with a 1-minute warmup, which is 07:01–12:30 New York ·
configurations evaluated: 729 in the walk-forward grid, 486 in CPCV, 40 in the sensitivity sweep.

## 1. The result depends entirely on one modelling choice

The strategy's median hold is **one bar**. Its trailing stop arms after 15 points of favourable
movement and then follows the extreme by 8 points. On a 15-minute NQ bar whose typical range is
larger than both of those numbers, whether that trail arms and fires *within the entry bar itself*
is not a fact in the data — it is an assumption. So the simulator brackets it three ways rather
than picking one:

| convention | what it assumes |
| --- | --- |
| `intrabar / favorable` | price runs first, arming and tightening the trail, which is then hit on the way back |
| `intrabar / adverse` | the initial stop gets first refusal each bar, then the trail arms |
| `barclose` | the trail may only arm or tighten from **closed** bars; no claim about intra-bar order |

`barclose` is the primary model because it is the only one a 15-minute OHLC file can support.

| exit model | trades | pts/trade | $/trade | win rate | PF | net P&L | max DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **barclose / adverse** (primary) | 1,228.0 | -1.31 | $-13.09 | 51.2% | 0.89 | $-16,073 | $29,146 |
| barclose / favorable | 1,228.0 | -0.55 | $-5.52 | 52.0% | 0.95 | $-6,783 | $23,964 |
| intrabar / adverse | 1,232.0 | +2.75 | $+27.50 | 58.7% | 1.27 | $+33,875 | $5,252 |
| intrabar / favorable | 1,240.0 | +4.10 | $+41.00 | 62.7% | 1.47 | $+50,839 | $6,540 |
| no trailing stop / adverse | 1,186.0 | -1.86 | $-18.57 | 36.3% | 0.91 | $-22,020 | $41,653 |
| no trailing stop / favorable | 1,186.0 | -1.16 | $-11.61 | 37.6% | 0.94 | $-13,773 | $36,824 |

Reading the adverse column, which holds the bar-path assumption constant and varies only the trail:
**$+33,875 → $-16,073 → $-22,020**. The intrabar path assumption is worth
**$+49,948**, which is 147% of the headline profit. The trailing stop as a
mechanic that only reads closed bars is worth **$+5,948**. The signal is worth the rest, and the
rest is negative.

## 2. Matched control — the signal is real, the profit is not

Random entries drawn from the same session pool, with the same side mix and the same
minute-of-day histogram, pushed through the *identical* exit machinery. Scoring a barrier strategy
against zero is invalid — the geometry alone has non-zero expectation under a time limit — so
everything is scored against this control.

| exit model | strategy | random control | excess | z | p |
| --- | ---: | ---: | ---: | ---: | ---: |
| barclose / adverse | -1.31 | -1.86 | +0.55 | +0.73 | 0.2500 |
| barclose / favorable | -0.55 | -1.04 | +0.49 | +0.62 | 0.2833 |
| intrabar / adverse | +2.75 | +1.14 | +1.61 | +2.17 | 0.0133 |
| intrabar / favorable | +4.10 | +2.46 | +1.64 | +2.35 | 0.0100 |

**Random entries with this trailing stop earn +1.14 to +2.46 points per trade under the
intrabar convention.** That is where the money in a bar-level backtest of this system comes from —
not from the EMA89 trend filter, the pullback rule or the StochRSI cross, but from an exit that
harvests intra-bar noise the data cannot confirm was tradable.

The signal's own contribution, the excess over the control, is stable at
+0.55 to +1.64 points per trade in every convention. It is real, small, and
under the honest model it is not significant (p 0.25 and 0.28).

## 3. Verification — the engine is clean, so the problem is not a bug

Four checks gate every number above. Truncation: every indicator recomputed on `data[:i+1]`
matches the full-sample value at bar *i* to 0.0e+00 relative deviation, at 40 randomly chosen bars —
no centred window, no backfill, no global normalisation. Execution alignment: 0 fills at or before
their signal bar, 0 exits before their fill, 0 overlapping positions, and the signal-to-fill gap is
exactly 1 bar for every trade. Indicators: Wilder ATR and RSI match a literal textbook transcription
to 2.3e-13 and 5.7e-14. Future-bar probe: feeding the engine tomorrow's prices moves expectancy by
+0.16 points, not by a jump — an engine already reading its own fill bar would leap.

The skill's leakage audit on a 9-feature matrix over 206,614 rows returns **no critical findings and
no warnings**; the largest |IC| against the next bar's ATR-normalised return is 0.022. Its execution
alignment check reports **no same-bar execution signature**.

So the profit is not produced by a coding error. It is produced by an assumption that a correct
bar-level backtester — TradingView's included — makes silently.

## 4. Where the money comes from

Split by exit reason on the research block, adverse ordering:

| exit reason | intrabar share | intrabar total | barclose share | barclose total |
| --- | ---: | ---: | ---: | ---: |
| initial stop | 41.3% | $-126,415 | 41.3% | $-125,817 |
| fixed target | 12.3% | $+39,560 | 12.3% | $+39,560 |
| trailing stop | 46.4% | $+120,730 | 46.4% | $+70,184 |
| **exits on the entry bar itself** | **31.1%** | **$+23,892** | **13.8%** | **$-31,444** |

The stop and target legs are nearly identical between the two models — as they must be, since
neither depends on the trail. The whole difference is the trailing leg, and specifically the trades
that open and close inside one 15-minute bar: under the intrabar model those 31% of trades
contribute +$23,892, under the path-free model the same rule contributes **-$31,444**. That single
row is the study.

## 5. Parameter sensitivity — and a diagnostic that gives the artifact away

A real edge decays smoothly across a parameter. Here is the whole 40-cell sweep:

| parameter | values | barclose/adverse (pts/trade) | intrabar/adverse (pts/trade) |
| --- | --- | --- | --- |
| `trend_ema` | 34.0 · 50.0 · 89.0 · 144.0 · 200.0 | +0.11 · -0.38 · -1.31 · -1.33 · -0.86 | +5.15 · +4.26 · +2.75 · +2.58 · +2.95 |
| `min_pullback` | 5.0 · 10.0 · 15.0 · 20.0 · 30.0 | -1.34 · -1.36 · -1.31 · -1.04 · -0.83 | +2.00 · +2.25 · +2.75 · +3.54 · +4.81 |
| `atr_stop` | 1.0 · 1.25 · 1.5 · 2.0 · 2.5 | -1.33 · -1.49 · -1.31 · -1.20 · -1.44 | +1.89 · +2.26 · +2.75 · +3.64 · +3.70 |
| `atr_target` | 1.5 · 2.0 · 2.5 · 3.5 · 5.0 | -1.56 · -1.27 · -1.31 · -1.06 · -0.89 | +1.68 · +2.38 · +2.75 · +3.13 · +3.41 |
| `trail_arm` | 8.0 · 12.0 · 15.0 · 20.0 · 30.0 | -1.40 · -1.24 · -1.31 · -1.13 · -0.92 | +3.02 · +2.95 · +2.75 · +2.34 · +1.73 |
| `trail_offset` | 4.0 · 6.0 · 8.0 · 12.0 · 16.0 | -1.15 · -1.16 · -1.31 · -1.22 · -1.41 | +3.98 · +3.38 · +2.75 · +2.00 · +1.15 |
| `reset_lookback` | 4.0 · 6.0 · 8.0 · 12.0 · 16.0 | -1.83 · -1.66 · -1.31 · -1.46 · -1.46 | +2.37 · +2.36 · +2.75 · +2.52 · +2.48 |
| `pullback_lookback` | 5.0 · 8.0 · 10.0 · 15.0 · 20.0 | -1.17 · -1.25 · -1.31 · -1.34 · -1.35 | +3.30 · +2.91 · +2.75 · +2.60 · +2.54 |

**Every one of the 40 cells is negative under the honest model, and every one is positive under the
intrabar model.** No parameter choice rescues it and none is needed to break it.

The `trail_offset` row is the diagnostic. Under the intrabar model expectancy rises monotonically as
the trail is tightened — +3.98 → +3.38 → +2.75 → +2.00 → +1.15 as the offset goes
4 → 6 → 8 → 12 → 16 points. A tighter trailing stop capturing *more* profit,
monotonically, is not a property of any market; it is the signature of a model harvesting more
intra-bar noise as you let it read the bar more finely. Under the path-free model the same row is
flat and negative (-1.15 → -1.16 → -1.31 → -1.22 → -1.41), which is what a
parameter with no edge behind it should look like.

## 6. Correlation matrices

Session-P&L correlations across 16 parameter variants (`corr_variants.csv`): mean
off-diagonal **0.829**, median 0.850, first eigenvalue explaining
84.7% of the variance. The Li & Ji effective number of independent tests among those
16 variants is **M_eff = 5.5** — tuning this strategy's parameters is worth about
5 genuinely independent bets, not 16, because variants sharing a lookback share nearly all
their trades.

The one variant that decorrelates is `notrail` (0.45–0.63 against everything else). Removing the
trailing stop does not adjust the strategy, it replaces it.

Across exit conventions (`corr_conventions.csv`) the two `barclose` orderings correlate 0.98 with
each other and 0.79–0.91 with the `intrabar` pair, so the conventions agree about *which sessions*
make money and disagree about *how much* — again pointing at the exit, not the entry.

## 7. Walk-forward — and why it cannot save you here

729 configurations, the best selected on each training window by mean net per trade and
traded on the next block. Pass requires stitched OOS expectancy > 0 with a bootstrap 95% CI
excluding zero, ≥ 60% of folds profitable, and a positive median fold.

| exit model | train/test | folds | profitable | median IS | median OOS | stitched OOS [95% CI] | worst fold | modal cfg | verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| barclose | 400/150 | 9 | 22% | +0.55 | -1.64 | -0.78 [-3.06, +1.47] | -5.11 | 11% | FAIL |
| barclose | 600/200 | 5 | 0% | +0.27 | -2.46 | -2.88 [-5.54, -0.49] | -4.52 | 20% | FAIL |
| intrabar | 400/150 | 9 | 89% | +5.44 | +4.17 | +7.98 [+5.57, +10.33] | -5.00 | 33% | **PASS** |
| intrabar | 600/200 | 5 | 100% | +4.07 | +5.50 | +6.58 [+3.76, +9.41] | +1.09 | 60% | **PASS** |

**Walk-forward validation confirms this strategy under the optimistic bar-path assumption and
rejects it under the honest one.** That is the single most useful thing in this report. Walk-forward
tests whether parameters are stable out of sample; it has nothing to say about whether the fills
were achievable, and it will happily certify an execution artifact as robust. Anyone who
walk-forwards a fast trailing stop on bar data and reads a PASS has tested the wrong thing.

## 8. Purged CV and combinatorial purged CV

Purged 5-fold with a 5-session embargo, honest model: fold expectancies -2.63, -0.69,
-3.99, -3.50, +3.47 points per trade — four of five negative, and the positive one is the 2022 block.

CPCV re-selecting the configuration inside each split (486 configurations, 6 groups, 2 test groups,
15 splits, 5 reconstructable paths):

| exit model | median IS | median OOS | decay | paths profitable | path range |
| --- | ---: | ---: | ---: | ---: | --- |
| barclose | +1.75 | -0.54 | +2.30 | 20% | -0.60 to +0.04 |
| intrabar | +10.02 | +8.06 | +1.96 | 100% | +7.76 to +8.23 |


## 9. Monte Carlo — 10,000 simulations per test

| test | barclose / adverse | intrabar / adverse |
| --- | ---: | ---: |
| expectancy per trade | $-13.09 | $+27.50 |
| block-bootstrap Sharpe p5 / p50 / p95 | -1.60 / -0.77 / +0.06 | +0.53 / +1.48 / +2.44 |
| P(Sharpe ≤ 0) | 93.8% | 0.4% |
| P(loss over the next 250 trades) | 78.1% | 11.4% |
| P(account halved in 250 trades) | 0.00% | 0.00% |
| permutation max drawdown, p95 | -29.8% | -7.0% |
| random-strategy null p-value | 0.2510 | 0.3860 |

Permuting trade order leaves total return unchanged by construction — only the path moves — so that
row is a drawdown test, not a significance test: reshuffling the honest model's own trades produces
a 29.8% drawdown at the 95th percentile.

The block bootstrap is the significance test, and it says the honest model has a **93.8%** chance of a
non-positive Sharpe. Forward-simulating the next 250 trades from its own distribution gives a
**78.1%** chance of losing money.

The random-strategy null in the last row is the skill's coarse version — it compares bar-level
Sharpes over a series the strategy is flat in 96% of, so it has very little power and returns
p 0.25 and 0.39 for models that differ by $50,000. The matched control in §2, which shares the side
mix, minute-of-day histogram and exit geometry, is the sharper instrument and is what the verdict
rests on.

## 10. Deflation and probability of backtest overfitting

| | barclose / adverse | intrabar / adverse |
| --- | ---: | ---: |
| annualised Sharpe (daily) | -0.59 | +1.19 |
| annualised return on $50k | -4.72% | +9.68% |
| max drawdown | -44.9% | -9.9% |
| deflated Sharpe (729 trials) | 0.000 | 0.539 |
| min track record for SR>0 | n/a — Sharpe is negative | 455 days (1.8 yrs) |
| PBO (CSCV, 16 splits) | 21.5% | 0.0% |

**The deflated Sharpe kills the optimistic version too.** Selecting the best of 729 configurations,
the highest annualised Sharpe you should expect from pure noise is +1.16. The intrabar model's
observed Sharpe is +1.19, so its deflated Sharpe is 0.539 — it does not clear the bar its own
search sets. Note also that 67% of its P&L comes from the top 1% of days, and it is underwater
90% of the time.

PBO points the same way in reverse: 21.5% for the honest model against 0.0% for the intrabar one.
A PBO of zero does not mean the strategy is sound; it means every configuration in the grid is
carried by the same artifact, so selecting among them cannot go wrong.

## 11. The contract-size question — the one finding that is actionable

The strategy is configured for MNQ at $2 per point but charged $1.24 per contract per order.
An edge and a cost are only comparable in the same unit, and in **points** that same dollar
commission is ten times larger on the micro than on the full-size contract. The round turn is
1.74 points on MNQ and 0.62 points on NQ.

| exit model | gross edge | MNQ (1.74 pt RT) | NQ, $1.24/ct (0.62 pt RT) | NQ, $2.50/ct (0.75 pt RT) |
| --- | ---: | ---: | ---: | ---: |
| barclose/adverse | +0.45 | -1.29 | -0.18 | -0.30 |
| barclose/favorable | +1.22 | -0.52 | +0.59 | +0.47 |
| intrabar/adverse | +4.53 | +2.79 | +3.90 | +3.78 |
| intrabar/favorable | +5.87 | +4.13 | +5.25 | +5.12 |

Under the honest model the full-size contract moves the strategy from -1.29 to -0.18 points per
trade at the adverse ordering and from -0.52 to **+0.59** at the favourable one. The honest bracket
on NQ therefore straddles zero: somewhere between -0.18 and +0.59 points per trade, which is another
way of saying *indistinguishable from zero with this data*. It is not a green light. It is the only
change in the whole study that moves the number by more than the noise, and it costs nothing to
make.

## 12. Live account simulation — $50,000, 5 MNQ, every cost charged

| | barclose / adverse (honest) | intrabar / adverse (optimistic) |
| --- | ---: | ---: |
| final equity | $33,927 | $83,875 |
| net profit over 7.1 years | $-16,073 | $+33,875 |
| CAGR | -5.33% | +7.58% |
| max drawdown | $29,146 (58.3%) | $5,252 (10.4%) |
| trades | 1,228 | 1,232 |
| win rate | 51.2% | 58.7% |
| longest losing run | 18 trades | 18 trades |
| total costs paid | $21,367 | $21,437 |

Costs paid over the research block, $21,367, are **1.3x the size of the honest
model's entire loss**. This strategy's problem is not that it is wrong about direction; it is that
it trades a small edge too often through an expensive contract.

## 13. The session window in the screenshots is not 07:00-11:00 New York

The inputs are set to 06:00-11:30 **Chicago** with a 1-minute warmup. Chicago is New York
minus one hour, so the strategy trades **07:01-12:30 New York**. Five windows were searched on the
research block; treat what follows as best-of-five, not as a result.

| window | trades | gross (barclose) | net (barclose) | net $ | net (intrabar) |
| --- | ---: | ---: | ---: | ---: | ---: |
| as configured: 06:00-11:30 Chicago = 07:01-12:30 NY | 1,228 | +0.45 | **-1.31** | $-16,073 | +2.75 |
| 07:00-11:00 NEW YORK = 06:00-10:00 Chicago | 954 | -0.03 | **-1.76** | $-16,798 | +2.24 |
| 09:30-11:00 NEW YORK = 08:30-10:00 Chicago (RTH only) | 299 | +3.20 | **+1.25** | $+3,738 | +7.69 |
| 08:30-11:30 Chicago (US cash open onward) | 574 | +2.66 | **+0.75** | $+4,326 | +6.14 |
| full RTH 08:30-15:00 Chicago | 1,339 | +1.79 | **-0.02** | $-269 | +4.58 |

**Cutting the pre-open out is the only change in this study that flips the honest model positive.**
Restricted to 09:30-11:00 New York the gross edge rises from +0.45 to +3.20 points per trade, which
clears the 1.74-point round turn, and the excess over the matched control is +3.19 points
(p 0.0275 on research, but ~0.14 once the five-window search is priced in).

That is the same effect this repository has recorded before on unrelated strategies: the 07:00-09:30
New York pre-open contributes the losses, and the cost model does not even widen the spread there, so
the real gap is larger than measured. It was carried into the holdout as a pre-registered test.

## 14. Holdout — the single look, six pre-registered comparisons

Every rule below was frozen in code, and the pass criterion written into the ledger, before
any holdout number existed (entries N0001 and N0002). Bonferroni threshold for NPRE=6 is
p < 0.0083. Holdout: 2022-08-30 → 2025-10-01, 962 sessions.

| test | research exp | research excess | research p | holdout exp | holdout ctrl | holdout excess | holdout p | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| as-written barclose/adverse | -1.31 | +0.60 | 0.2225 | **-0.63** | -1.77 | +1.13 | 0.1775 | FAIL |
| as-written barclose/favorable | -0.55 | +0.53 | 0.2650 | **+0.73** | -0.52 | +1.25 | 0.1725 | FAIL |
| as-written intrabar/adverse | +2.75 | +1.60 | 0.0175 | **+4.70** | +4.50 | +0.20 | 0.4375 | FAIL |
| as-written intrabar/favorable | +4.10 | +1.64 | 0.0075 | **+7.36** | +7.05 | +0.31 | 0.4050 | FAIL |
| walk-forward pick trend50/pull25/stop2.0/targ3.5/arm15/off12 | +0.52 | +2.44 | 0.0050 | **-1.26** | -1.76 | +0.50 | 0.3750 | FAIL |
| RTH sub-window 09:30-11:00 NY barclose/adverse | +1.25 | +3.19 | 0.0275 | **+0.24** | -2.05 | +2.29 | 0.2225 | FAIL |
| RTH sub-window 09:30-11:00 NY intrabar/adverse | +7.69 | +4.97 | 0.0000 | **+7.83** | +7.60 | +0.23 | 0.4750 | FAIL |

**0 of 7 comparisons pass.**

The most informative row is the intrabar one, and it is worth reading twice. On the holdout the
strategy earns +4.70 points per trade — *better* than its research number. But the matched control,
random entries through the same trailing stop, earns +4.50. The excess collapses from
+1.60 on research to +0.20 on the holdout (p 0.4375); at the favourable ordering it is
+1.64 → +0.31. **Out of sample the signal contributes essentially nothing and the exit
mechanic contributes everything.** A backtest that only reported the strategy's own P&L would have
called the holdout a success.

The RTH sub-window did not collapse — research excess +3.19 → holdout +2.29 — but its holdout
expectancy is +0.24 points per trade on 177 trades, which is zero with a wide error bar, and
p 0.2225 is nowhere near the threshold. It is the one thread worth pulling, and it is not evidence
of an edge today.

Two of the `barclose` rows are flagged wrong-shape (better on holdout than research). Both are
negative or ~zero on both blocks, so this is small-sample noise rather than the leakage signature
that flag exists to catch.

## 15. A defect in the Pine, independent of everything above

`inSession` gates entries only. There is no session exit anywhere in the script, so a position
opened at 11:29 Chicago holds until a barrier is hit. On this data the longest hold ran 85 bars —
just under a day — and 0.8% of trades survive past their own session. It changes the P&L by about
1% here, so it is not what is wrong with the strategy, but it is not what the description says the
strategy does. The fix is two lines:

```pine
mustFlat = not inSession and strategy.position_size != 0
if mustFlat and barstate.isconfirmed
    strategy.close_all(comment = "Session Flat")
```

## 16. Weaknesses of this evaluation

**The intrabar question is unresolved, not settled.** The honest model is a lower bound on the
trailing stop's value and the intrabar model an upper bound; the truth is between. Resolving it needs
1-minute or tick data for this instrument, which is not in this container. Everything else in the
report is downstream of that one missing input.

**The parameters were not chosen by me.** If they were tuned on a TradingView chart covering this
sample, then the research block is not clean for them either and the whole study is optimistic.

**One long bull regime.** 2016-2025 on the Nasdaq is one macro environment. The honest model loses in
every year except 2022, which is the one bear year — consistent with the short side carrying what
little edge there is (shorts +0.06 vs longs -2.43 points per trade), and that is a small sample.

**The holdout is not pristine.** This NAS holdout was read twice for an unrelated Donchian study in
this repository. It was not read for this strategy family, and these six comparisons were
pre-registered, but a holdout is a depleting resource and this one is not new.

**The matched control is one design.** It matches side, minute-of-day and geometry. It does not match
volatility regime at entry, so a strategy that systematically enters in unusual volatility could beat
it for reasons that are not edge.

## 17. What I would do next, in order

1. **Get 1-minute data for NQ and re-run the trailing stop on real paths.** This is the only test
   that matters. Everything else is bracketing around a missing input. If the true fill sits near the
   `barclose` end, the strategy is dead as configured; near the `intrabar` end, it is worth developing.
2. **Trade the full-size contract, not the micro.** A $1.24 commission is 0.62 points on MNQ and 0.062
   on NQ, and the honest gross edge is +0.45 points. The contract choice is worth more than any
   parameter in the strategy.
3. **Cut the pre-open.** 09:30-11:00 New York is the only window where the honest model is positive
   after costs. It is best-of-five and it did not clear the holdout bar, but it costs nothing and it
   points the same way this repository's earlier work did.
4. **Add the session flatten.** Not for P&L — it is worth about 1% — but because the code does not
   currently do what its description says.
5. **Do not add filters to fix this.** The signal beats random entries by about a point per trade and
   loses that to costs. Filters cut trade count, which raises the variance faster than the edge.

## 18. Optimisation round — what was fixed, what could not be

Asked to optimise the signal until it passes. Every number here is the path-free
`barclose` model on the **research block only**; the holdout is not opened again, because
nothing in this round earned the look. Search size: 5 session windows + 165 moving-average
structures + 240 filter/geometry cells.

### 18a. A real defect: every distance is in fixed points over a 5× price range

`minPullbackPoints = 15`, `trailArmPoints = 15` and `trailOffsetPoints = 8` are absolute
NQ points. NQ opens this sample near 4,800 and ends near 24,600, so those thresholds mean
something different at each end and nothing in the strategy adapts.

| year | median close | median ATR(14) | trail arm in ATR | trail offset in ATR | bars passing the 15-pt pullback |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2016 | 4,873 | 4.6 | 3.27 | 1.75 | 34% |
| 2017 | 5,796 | 4.5 | 3.31 | 1.76 | 31% |
| 2018 | 6,965 | 10.4 | 1.44 | 0.77 | 68% |
| 2019 | 7,671 | 9.9 | 1.51 | 0.81 | 65% |
| 2020 | 10,498 | 21.6 | 0.69 | 0.37 | 89% |
| 2021 | 14,551 | 21.3 | 0.71 | 0.38 | 90% |
| 2022 | 13,316 | 37.5 | 0.40 | 0.21 | 99% |

The trailing stop is a **3.27 ATR** rule in 2016 and a **0.40 ATR** rule in 2022. By the end
of the sample it is tight enough to sit inside a single bar's noise, which is precisely the
regime where the intrabar artifact from §1 is largest — the two defects compound. The pullback
filter degrades the same way: it screens out 66% of in-session bars in 2016 and 1% in 2022.

Making every distance ATR-relative is a fix worth making on its own terms, whatever the P&L
does, because it is the difference between a rule and an accident.

### 18b. The ladder — what each change is actually worth

| step | trades | net pts/trade | control | excess | p | step |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| as written, MNQ, full window | 1,228 | -1.31 | -1.86 | +0.55 | 0.2500 |  |
| + full-size NQ instead of MNQ | 1,228 | -0.19 | -0.75 | +0.55 | 0.2500 | +1.12 |
| + ATR-relative distances | 1,507 | -0.12 | -0.84 | +0.72 | 0.1667 | +0.07 |
| + RTH window 09:31–11:00 NY | 329 | +3.18 | -0.85 | +4.03 | 0.0200 | **+3.31** |
| + best MA of 165 searched | 267 | +5.65 | -1.03 | +6.68 | 0.0000 | +2.46 |

Two of these are legitimate and two are not. The contract change and the ATR normalisation are
**mechanical**: they have a reason that is not "it backtested better", and together they take the
strategy from −1.31 to −0.12 points per trade. That is still a loss, but it is no longer a
scale-broken loss. The window and the MA are **selections**, and the rest of this section is about
why they do not survive.

### 18c. The moving average is not the lever

165 MA structures — EMA, SMA and Hull, trend periods 34 to 200, every fast/slow pair — each
front-gated by the matched control. **165 of 165 are net positive** and 145 clear p&lt;0.05
against the control, where chance would give about 8.

A search in which *everything* wins has not found a good configuration; it has found something
common to all of them. The marginals say so directly:

| MA type | mean net | mean excess | | trend period | mean net |
| --- | ---: | ---: | --- | --- | ---: |
| ema | +3.82 | +4.67 | | 34 | +4.87 |
| hma | +3.94 | +4.81 | | 50 | +4.61 |
| sma | +3.76 | +4.60 | | 89 | +4.40 |
|  | |  | | 144 | +2.79 |
|  | |  | | 200 | +2.52 |

Every MA type lands within 0.18 points of every other. Swapping your EMA89 for a Hull 34 or an
SMA 200 changes the result by less than the measurement error. **The entry MA is interchangeable
here** — which means tuning it is not where the answer is, and the +2.46 points the search added on
top of the window is selection over 165 cells, not information.

The entry rule is not *worthless*, though. A placebo — random triggers at the same rate inside the
same trend-plus-pullback context and the same window — earns a median +0.32 points against the
real rule's +5.65 (p 0.0000), and taking *every* context bar earns -0.46. The StochRSI cross
does discriminate on research. It just does not discriminate enough, or durably.

### 18d. What the search actually found: two years

| year | trades | net pts/trade |
| --- | ---: | ---: |
| 2016 | 5 | +1.03 |
| 2017 | 45 | +0.07 |
| 2018 | 44 | +1.22 |
| 2019 | 41 | -0.78 |
| 2020 | 52 | **+12.40** |
| 2021 | 46 | +1.10 |
| 2022 | 34 | **+23.01** |

| drop this year | trades | net pts/trade |
| --- | ---: | ---: |
| 2016 | 262 | +5.74 |
| 2017 | 222 | +6.78 |
| 2018 | 223 | +6.52 |
| 2019 | 226 | +6.81 |
| 2020 | 215 | +4.01 |
| 2021 | 221 | +6.59 |
| 2022 | 233 | +3.11 |
| **2020 and 2022 together** | 181 | **+0.45** |

The round turn on full-size NQ is 0.62 points, so **+0.45 is a loss**. 2020 and 2022 are 95% of the
P&L across 7 years, the top 5% of trades are 78% of it, and shorts earn +9.71 against longs' +1.91.
The optimised strategy is a short-volatility-spike bet expressed through about thirteen trades.

The filter sweep says the same thing across all 240 cells: 230 are positive on the full block,
but only **69 of 240** stay above the round turn once 2020 and 2022 are removed, and the median
share of P&L coming from the top 5% of trades is **106%** — for the median configuration the
best 5% of trades produce more than the total, so the other 95% lose money together.

| filter | mean net, full block | mean net, 2020 and 2022 removed |
| --- | ---: | ---: |
| cap retrace at 3 ATR | +5.10 | +1.41 |
| close back through fast MA | +5.35 | +0.56 |
| none | +4.73 | -0.07 |
| ATR pct 0.2-0.8 | +1.73 | -0.34 |
| ATR pct < 0.8 | +1.60 | -0.37 |
| align + close back | +4.66 | -0.61 |
| trend MA rising 4 bars | +3.21 | -1.09 |
| EMA align | +4.15 | -1.64 |

The two filters that look strongest on the full block — requiring EMA alignment, and requiring the
trend MA to be rising — are the two that turn *most* negative without the crisis years. They are
not making the signal more accurate; they are concentrating it into the trending crashes.

### 18e. Walk-forward on the optimised family — still FAIL

| train/test | folds | profitable | median IS | median OOS | stitched [95% CI] | worst | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 400/150 | 9 | 56% | +3.41 | +1.09 | +3.27 [-1.72, +8.42] | -2.92 | FAIL |
| 600/200 | 5 | 40% | +1.84 | -0.66 | +0.78 [-4.12, +5.88] | -1.84 | FAIL |

Both bootstrap intervals include zero. The fold sequence at 400/150 is +1.09, +4.15, −2.92, −0.14,
−2.26, **+16.92**, −0.75, +1.12, **+19.26** — seven of nine folds sit between −2.9 and +4.2 and two
carry the entire result. That is the same concentration, seen through a different instrument.

### 18f. Verdict on the optimisation

**The optimisation did not produce a strategy that passes, so the holdout was not opened.**
Spending the last look on a configuration already known to fail its research gate would waste it.

Two changes are worth keeping regardless of the verdict, because both are corrections rather than
selections:

1. **Make every distance ATR-relative.** Worth +0.07 points per trade, and worth much more than
   that as insurance: the current code silently becomes a different strategy as price levels change.
2. **Trade the full-size contract.** Worth +1.12 points per trade, free, and not a backtest result —
   it is arithmetic on the commission.

Together they take the as-written strategy from −1.31 to −0.12 points per trade. That is still
negative, and the remaining gap is not closable by tuning the moving average, because the moving
average is demonstrably interchangeable here.

The one prior finding that survives as a *lead* rather than a result is the same one as before: the
09:31–11:00 New York window. It is worth +3.31 points per trade on research, it was already carried
into the holdout in the previous round with the original parameters, and there it returned +0.24
points per trade at p 0.2225. It did not replicate. The optimisation round explains why: 95% of its
research-block edge is 2020 and 2022.



## 19. Cross-instrument test, component correlations, and what to delete

The NAS holdout has been read three times, so this round buys its out-of-sample evidence a
different way: **a second instrument**. US30 costs nothing from the NAS budget, and if an
EMA-pullback plus StochRSI entry carries real information about intraday index futures, it should
carry it on the Dow as well as the Nasdaq. Two 0.85-correlated indices trading the same session
with the same participants is about as favourable a replication test as exists.

### 19a. The signal does not replicate on US30 — it inverts

| configuration | instrument | trades | gross (ATR units) | net | control | excess | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| as written (full window) | NAS | 1,228 | +0.038 | -0.19 | -0.75 | +0.55 | 0.2500 |
| ATR-relative distances | NAS | 1,507 | +0.036 | -0.12 | -0.84 | +0.72 | 0.1667 |
| ATR-relative + RTH 09:31-11:00 | NAS | 329 | +0.323 | +3.18 | -0.85 | +4.03 | 0.0200 |
| as written (full window) | US30 | 1,553 | -0.035 | -3.48 | -2.51 | -0.97 | 0.7900 |
| ATR-relative distances | US30 | 1,511 | -0.092 | -4.67 | -2.27 | -2.41 | 0.9100 |
| ATR-relative + RTH 09:31-11:00 | US30 | 364 | -0.210 | -7.66 | -1.73 | -5.94 | 0.9467 |

Gross edge is quoted in ATR units because that is the only scale on which two instruments are
comparable. **All three configurations disagree in sign**, and US30's excess over the matched
control is negative in every one, at p 0.79 to 0.95 — the strategy is consistently *worse* than
random entries there.

The reversal is sharpest on the one configuration that looked promising. The 09:31–11:00 window
is +0.323 ATR gross on NAS with excess +4.03 at p 0.020; on US30 it is **-0.210 ATR** with excess
**-5.94** at p 0.947. The single best finding of the previous round does not weaken on a second
instrument, it points the other way.

That is the cleanest evidence in the whole study. A real intraday effect in the US cash open should
not be present on the Nasdaq and inverted on the Dow.

### 19b. Matrix correlations over the strategy's own conditions

Each entry rule as a boolean series over research bars, long side (US30's matrix is the same to
two decimals, which is itself worth knowing — the *structure* replicates even though the edge does
not):

| | trend gate (close vs E | pullback depth >= 1.15 | touch of fast/slow EMA | StochRSI reset (20/80) | StochRSI %K/%D cross | session window |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| trend gate (close vs EMA89) | 1.00 | -0.18 | -0.32 | -0.08 | 0.00 | -0.01 |
| pullback depth >= 1.15 ATR | -0.18 | 1.00 | 0.53 | 0.26 | 0.03 | 0.16 |
| touch of fast/slow EMA | -0.32 | 0.53 | 1.00 | 0.29 | 0.04 | 0.00 |
| StochRSI reset (20/80) | -0.08 | 0.26 | 0.29 | 1.00 | 0.03 | 0.02 |
| StochRSI %K/%D cross | 0.00 | 0.03 | 0.04 | 0.03 | 1.00 | 0.00 |
| session window | -0.01 | 0.16 | 0.00 | 0.02 | 0.00 | 1.00 |

Two things stand out.

**The pullback depth and the EMA touch are 0.53 correlated and fire on 71% and 75% of bars.** They
are close to the same rule, and neither is selective: a "filter" that passes three bars in four is
not filtering. The trend gate is *negatively* correlated with the touch (−0.32), which is just the
observation that price touches a fast MA more often when it is below the slow one.

**The %K/%D cross is the only independent, selective condition in the strategy.** It correlates
0.00–0.04 with everything else and fires on 12.2% of bars. Whatever selection this strategy does,
that line does it.

### 19c. Drop-one — what each condition is actually worth

Each condition removed from the **triggers** and the book re-simulated, which is the only valid
way to test a filter; splitting realised trades is not. A condition earns its place only if removing
it *hurts* on both instruments.

| condition | worth on NAS | worth on US30 | trades without it (NAS) | verdict |
| --- | ---: | ---: | ---: | :---: |
| StochRSI %K/%D cross | +0.78 | -1.41 | 4,523 | mixed |
| StochRSI reset (20/80) | +0.52 | -2.24 | 2,404 | mixed |
| pullback depth >= 1.15 ATR | -0.08 | -0.10 | 1,525 | **DELETE** |
| session window | +0.30 | -2.03 | 5,616 | mixed |
| touch of fast/slow EMA | -0.29 | -0.41 | 1,592 | **DELETE** |
| trend gate (close vs EMA89) | +0.44 | -1.46 | 4,024 | mixed |

**Nothing is worth keeping on both instruments.** Two conditions are actively harmful on both, and
they are the two that define the pullback: the **depth requirement** (-0.08 on NAS,
-0.10 on US30) and the **MA touch** (-0.29, -0.41). Removing either makes the
strategy better on both instruments, and they are 0.53 correlated with each other anyway.

So the answer to "what should be deleted" is uncomfortable but specific: **the moving-average
pullback mechanism is the part that does not earn its place.** That is the part the strategy is
named after. The conditions with positive worth on NAS — trend gate, StochRSI reset, the cross, the
session — all have negative worth on US30, which is the same non-replication as §19a seen through a
different instrument.

### 19d. The features your script has but never switched on

Four early exits, quick-scalp mode, and the volume and MACD filters were all `false` in the
supplied settings and had never been measured. Round turn is 0.62 points on NAS (full-size NQ) and
2.50 on US30 (YM).

| feature | NAS net | NAS ex-crisis | US30 net | US30 ex-crisis |
| --- | ---: | ---: | ---: | ---: |
| baseline (all off, as tested) | -0.12 | -0.70 | -4.67 | -2.16 |
| early exit: StochRSI fade | -0.39 | -1.28 | -4.18 | -1.92 |
| early exit: slow-EMA break | -0.97 | -1.30 | -3.80 | -1.77 |
| early exit: trend-EMA break | -0.55 | -0.77 | -3.21 | -1.67 |
| early exit: fade + EMA break | -0.63 | -1.34 | -3.91 | -1.96 |
| quick scalp 8 pts / 6 bars | -2.02 | -1.78 | -5.57 | -4.87 |
| quick scalp 0.5 ATR / 6 bars | -2.30 | -1.86 | -5.15 | -4.44 |
| quick scalp 1.0 ATR / 12 bars | -1.48 | -1.31 | -4.89 | -3.03 |
| volume thrust filter 1.2x | -0.06 | -0.24 | -5.19 | +0.73 |
| volume thrust filter 1.5x | +1.55 | +1.03 | -5.56 | -0.18 |
| MACD momentum confirm | +1.13 | +0.82 | +1.70 | -0.61 |
| volume + MACD | +0.25 | +1.64 | +1.93 | +2.07 |

**Every early exit makes it worse on NAS**, and quick-scalp mode is the worst thing in the table
(−1.48 to −2.30). Cutting a trade short at a fixed 8 points when the ATR-based target is 2.5 ATR is
the same mistake as the fixed-point trail: a distance that does not scale.

The volume and MACD filters are the only features that help, and only on NAS.

### 19e. The StochRSI trigger parameters

486 configurations per instrument — RSI length, stoch length, %K and %D smoothing,
oversold/overbought levels, reset lookback. This is the actual trigger and it had never been swept.

| | NAS | US30 |
| --- | ---: | ---: |
| cells with ≥60 trades | 243 | 243 |
| median net | -0.70 | -2.20 |
| best net | +1.17 | +1.27 |
| cells above the round turn | 6 / 243 | 0 / 243 |
| …and still above it without 2020+2022 | **0** | **0** |

No parameterisation of the trigger clears its own cost floor durably on either instrument. Every
marginal is negative on both. The default 14/14/3/3 with 20/80 is not a bad choice — there is no
good one.

### 19f. The finalists, through the whole gate

Three cells survived the cheap screen. The gate, declared before running: **G1** net above the
round turn; **G2** excess over the matched control at p&lt;0.05; **G3** still above the round turn with
2020 and 2022 removed; **G4** stable across 250-session blocks; **G5** the same on both instruments.

| candidate | instrument | trades | net | excess | p | ex-crisis | blocks positive | G1 | G2 | G3 | G4 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | :-: | :-: | :-: | :-: |
| MACD momentum confirm | NAS | 249 | +1.13 | +1.83 | 0.1800 | +0.82 | 86% | ✓ | ✗ | ✓ | ✓ |
| volume 1.5x thrust | NAS | 627 | +1.55 | +2.54 | 0.0280 | +1.03 | 86% | ✓ | ✓ | ✓ | ✓ |
| volume 1.2x + MACD | NAS | 199 | +0.25 | +0.93 | 0.3360 | +1.64 | 57% | ✗ | ✗ | ✓ | ✗ |
| MACD momentum confirm | US30 | 271 | +1.70 | +3.90 | 0.1680 | -0.61 | 57% | ✗ | ✗ | ✗ | ✗ |
| volume 1.5x thrust | US30 | 462 | -5.56 | -3.08 | 0.8680 | -0.18 | 29% | ✗ | ✗ | ✗ | ✗ |
| volume 1.2x + MACD | US30 | 202 | +1.93 | +4.54 | 0.1640 | +2.07 | 57% | ✗ | ✗ | ✗ | ✗ |

**Zero candidates pass on both instruments.**

The volume-thrust filter is the best single thing found anywhere in this study: on NAS it is
**4 of 4**, at +1.55 points per trade against a 0.62 round turn, excess +2.54 over the matched control
at p 0.0280, still +1.03 with the crisis years removed, and positive in 86% of 250-session blocks.
On US30 it is **0 of 4**, at -5.56 points per trade with excess -3.08 at p 0.868.

A filter that is the strongest result on one index and the weakest on its near-twin is a property
of the sample, not of the market. The NAS holdout was not opened for it.

### 19g. What to delete

On the evidence above, in order of confidence:

1. **Quick-scalp mode.** Worst feature measured, on both instruments. It re-introduces the
   fixed-point scale bug that §18a is about.
2. **All four early exits.** Every one is negative on NAS; the least-bad is the trend break.
3. **The pullback depth and MA-touch conditions.** Negative worth on both instruments, 0.53
   correlated with each other, and each passes ~3 bars in 4. This is the strategy's namesake
   mechanism and it is the part that does not work.
4. **The MA period and type inputs** — not deleted, but stop tuning them. 165 structures, all
   within 0.2 points of each other (§18c).
5. **The fixed-point distance inputs** — already replaced by ATR-relative ones in §18a.

What survives as *worth keeping in the code*: the ATR-relative distances, the session flatten, the
New York clock, and the volume-thrust filter as an option with its NAS-only caveat attached. That
is a cleaner script. It is not a profitable one.


## Files

| file | role |
| --- | --- |
| `research/nqscalp/nqs.py` | the Pine replication: Pine TA definitions, next-open fills, three exit conventions |
| `research/nqscalp/verify.py` | truncation, execution alignment, Wilder cross-checks, future-bar probe |
| `research/nqscalp/nqcontrol.py` | the matched control |
| `research/nqscalp/cache.py` | memoised indicators for the sweeps |
| `research/nqscalp/battery1.py` | conventions, control, exit split, regimes, costs, sensitivity, correlations |
| `research/nqscalp/battery2.py` | walk-forward, Monte Carlo, deflation, PBO, live account |
| `research/nqscalp/cpcv.py` | combinatorial purged CV with per-split re-selection |
| `research/nqscalp/audit.py` | the skill's leakage audit, purged k-fold, contract-cost comparison |
| `research/nqscalp/session_test.py`, `rth_check.py` | the session-window search and its control |
| `research/nqscalp/holdout.py` | the single door to the holdout |
| `docs/nqscalp/ledger.jsonl` | pre-registration, amendment, and result |
| `docs/nqscalp/*.json`, `*.csv` | every number in this document |