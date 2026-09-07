# Validating the ATR phase momentum + session VWAP strategy

A 31-test battery -- leakage and execution, out-of-sample, multiple testing, costs and capacity, robustness -- run on the strategy in `APM-VWAP.pine`, whose header states that **no matched control has ever been run on this family**. That control is test 5.6 and it is the one to read first.

Reproduce with `python3 research/apm/run_all.py`.

## What was actually tested, and what could not be

The strategy is defined on a **10-minute** decision bar built from 1-minute NQ data. `data/NQ_1m.csv` is git-ignored and absent from this checkout, and a 10-minute bar cannot be reconstructed from 15-minute data, so the header's own measured figures (100,511 decision bars, 104 trades) are **not reproduced here**. What is tested instead is the same rule on a **15-minute** decision bar, on two instruments and nine years:

| dataset | bars | span | note |
| --- | --- | --- | --- |
| NASDAQ_15m | 206,703 | 2016-11-15 -> 2025-10-01 | 2,283 sessions |
| US30_15m | 193,942 | 2016-10-26 -> 2025-07-15 | 2,250 sessions |

Every session boundary the strategy uses (09:30, 11:00, 16:00, 18:00) is divisible by 15, so the source's own alignment validation passes -- but this is a **timeframe and instrument transplant**, not a reproduction. It is also a stronger test than the original in three ways: nine years instead of three, a second instrument, and a period that contains 2018, 2020 and 2022 rather than a single 81%-uptrend regime.

The feeds are broker index CFDs, so `Volume` is identically zero and the strategy's volume-weighted VWAP is a **tick-weighted** VWAP here. The broker clock was not assumed: it was pinned to EET/EEST two independent ways (0.9955 return correlation against a separately supplied New York-stamped file, and the busiest 15-minute slot of the day landing exactly on the 09:30 cash open). See `research/apm/apm_data.py`.

## Verdict

| dataset | section | verdict | why |
| --- | --- | --- | --- |
| NASDAQ_15m | 1 leakage/execution | **PASS** | no look-ahead found; the backtest measures what it claims |
| NASDAQ_15m | 2 out-of-sample | **PASS** | locked $4,148, walk-forward $7,083, 0.0% of CPCV paths negative |
| NASDAQ_15m | 3 multiple testing | **FAIL** | failed: deflated Sharpe 0.425 against a 0.94 noise benchmark; Harvey-Liu t 2.83 < 3.0 |
| NASDAQ_15m | 4 costs/capacity | **PASS** | breakeven round turn is 16.3x the applied $2.44 |
| NASDAQ_15m | 5 robustness | **PASS** | matched control p 0.003, bootstrap Sharpe CI [0.15, 1.67] |
| US30_15m | 1 leakage/execution | **PASS** | no look-ahead found; the backtest measures what it claims |
| US30_15m | 2 out-of-sample | **FAIL** | failed: locked block $-300; walk-forward $-683; 39.3% of CPCV paths negative |
| US30_15m | 3 multiple testing | **FAIL** | failed: deflated Sharpe 0.095 against a 0.68 noise benchmark; SPA p 0.778; PBO 0.67; Harvey-Liu t 0.67 < 3.0 |
| US30_15m | 4 costs/capacity | **PASS** | breakeven round turn is 2.9x the applied $2.44 |
| US30_15m | 5 robustness | **FAIL** | failed: matched control p 0.154; bootstrap Sharpe CI includes zero (lower -0.47); synthetic paths p 0.091 |

## What the battery found

**1. The matched control, run for the first time on this family.** Random entries with the same side mix, the same entry-minute distribution and the same hold-to-the-cash-close exit price in drift, costs, session timing and hold length at once, so what is left over is the rule.

| dataset | observed | control | percentile | p | verdict |
| --- | --- | --- | --- | --- | --- |
| NASDAQ_15m | $37.26/trade | $-1.71/trade | 100 | 0.003 | beats its control |
| US30_15m | $4.54/trade | $-1.97/trade | 85 | 0.154 | INDISTINGUISHABLE |


**2. It is a direction bet held to the close, not a barrier edge.** 92.5% of exits on NASDAQ_15m are the 16:00 cash close, and there are 0 reversals in nine years -- the same signature the Pine header reports (101 of 104 cash-close exits, zero reversals). Mean hold is 5.8 hours. The oscillator chooses a SIDE and a DAY; it never chooses an exit. That is why the matched control above is the whole test: it holds the same side for the same hours on the same minutes.


**3. The VWAP admission band, the strategy's distinguishing feature, is close to free.** Its own one-step ladder, with the band widened to the point of being absent:

| dataset | band | sharpe | net | trades | ship |
| --- | --- | --- | --- | --- | --- |
| NASDAQ_15m | 1.5 x ATR | 0.51 | $5,978 | 150 |  |
| NASDAQ_15m | 2.0 x ATR | 0.62 | $8,302 | 259 |  |
| NASDAQ_15m | 2.5 x ATR | 0.86 | $11,998 | 322 | <-- ship |
| NASDAQ_15m | 3.0 x ATR | 0.89 | $13,087 | 362 |  |
| NASDAQ_15m | no filter | 0.73 | $11,180 | 390 |  |
| US30_15m | 1.5 x ATR | 0.30 | $1,060 | 140 |  |
| US30_15m | 2.0 x ATR | -0.03 | $-127 | 213 |  |
| US30_15m | 2.5 x ATR | 0.25 | $1,226 | 270 | <-- ship |
| US30_15m | 3.0 x ATR | 0.16 | $809 | 300 |  |
| US30_15m | no filter | 0.09 | $443 | 315 |  |


On NASDAQ_15m the filter is worth $818 of $11,998 (6.8% of the result), and the band it ships at is not the best one on the ladder -- widening it to 3.0 x ATR is worth $13,087. A filter that is not at an optimum and that costs little to remove is not carrying the strategy.


**4. The binding constraint is the trial count, and it has two honest readings.**

| dataset | sharpe | psr_a_priori | noise_benchmark | dsr_180 | dsr_1800 |
| --- | --- | --- | --- | --- | --- |
| NASDAQ_15m | 0.86 | 0.982 | 0.94 | 0.425 | 0.223 |
| US30_15m | 0.25 | 0.773 | 0.68 | 0.095 | 0.034 |


The ship constants (EMA 21, ATR 14, EMA 3, denominator 3.0, thresholds +/-100, band 2.5) are a FIXED a-priori setting in the source, not something selected on this grid. So the Probabilistic Sharpe column is the reading if those constants were specified once and never tuned, and the Deflated Sharpe columns are the reading if they are the survivor of a search the size of this grid. Which is true is not knowable from the source, and the answer differs across the two: a Sharpe of 0.86 is comfortably above zero and comfortably BELOW what a 180-configuration search extracts from noise alone.


**5. It does not replicate on the second instrument.** The same rule, the same clock, the same nine years:

| dataset | net | per_trade | sharpe | nw_t | locked | matched_control_p | pbo |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NASDAQ_15m | $11,998 | $37.26 | 0.86 | 2.83 | $4,148 | 0.003 | 0.15 |
| US30_15m | $1,226 | $4.54 | 0.25 | 0.67 | $-300 | 0.154 | 0.67 |


US30_15m fails the locked block, the matched control and PBO together. Two instruments is a small sample of instruments, so this does not prove the NASDAQ_15m result is noise -- but a mechanism that is real in index futures should not care which index, and this one does.


**6. What would move this.** The 10-minute bar the strategy is actually defined on, from 1-minute data, which would make the header's own 104 trades reproducible and testable rather than transplanted. Failing that, a third and fourth index on the same clock: the single most informative number here is the cross-instrument disagreement, and it is currently computed from n=2.


## NASDAQ_15m

206,703 decision bars over 2,283 sessions, priced as MNQ ($2.00/point, 0.25 tick, $0.72/side, 1 tick slippage, $2.44 round turn).

**Headline.** 322 trades, $11,998 net, $37.26/trade, 59.9% win rate, Sharpe 0.86 (daily, annualised), Newey-West t 2.83, max drawdown $2,542, 35.5 trades/year.

Exits are overwhelmingly the 16:00 cash close, as in the source: 298 cash-close, 8 opposite-cross, 4 session-end. 322 intents admitted and 87 rejected by the VWAP band; 0 reversals; 95 of 2283 sessions blocked.


### 1. Leakage and execution audit

| test | result | verdict |
| --- | --- | --- |
| point-in-time / look-ahead | 25 signal bars re-simulated on truncated data, 0 mismatches | PASS |
| execution alignment | next-open $37.26/trade vs same-bar $37.51/trade ($0.25, 1%) | PASS |
| survivorship / universe | causal blocking $37.26/tr vs source pre-scan $37.55/tr ($0.29) | PASS |
| information coefficient | max |IC| 0.047 over 16 feature x horizon tests, threshold 0.15 | PASS |
| normalisation scope | prefix re-run reproduces 154 of 154 trades exactly | PASS |
| index hygiene | 0 duplicate, 0 NaN, 0 OHLC violations, 0.986 contiguous | PASS |


Information coefficients, Spearman against forward returns on the bars the strategy actually decides on (BH-adjusted):

| feature | horizon | n | ic | p | q | leak_flag |
| --- | --- | --- | --- | --- | --- | --- |
| osc | 1 | 13641 | 0.0091 | 0.2872 | 0.3063 | False |
| vwap_dist | 1 | 11366 | -0.0039 | 0.6782 | 0.6782 | False |
| osc_chg | 1 | 13641 | 0.0225 | 0.0086 | 0.0154 | False |
| close_less_ema | 1 | 13641 | 0.0155 | 0.0701 | 0.0863 | False |
| osc | 4 | 13641 | 0.0171 | 0.0454 | 0.0605 | False |
| vwap_dist | 4 | 11366 | -0.0209 | 0.0259 | 0.0414 | False |
| osc_chg | 4 | 13641 | 0.0391 | 0.0000 | 0.0000 | False |
| close_less_ema | 4 | 13641 | 0.0270 | 0.0016 | 0.0033 | False |
| osc | 16 | 13641 | 0.0390 | 0.0000 | 0.0000 | False |
| vwap_dist | 16 | 11366 | -0.0153 | 0.1029 | 0.1175 | False |
| osc_chg | 16 | 13641 | 0.0414 | 0.0000 | 0.0000 | False |
| close_less_ema | 16 | 13641 | 0.0466 | 0.0000 | 0.0000 | False |
| osc | 26 | 13641 | 0.0406 | 0.0000 | 0.0000 | False |
| vwap_dist | 26 | 11366 | -0.0197 | 0.0354 | 0.0515 | False |
| osc_chg | 26 | 13641 | 0.0313 | 0.0003 | 0.0006 | False |
| close_less_ema | 26 | 13641 | 0.0451 | 0.0000 | 0.0000 | False |


### 2. Out-of-sample validation


**Walk-forward, rolling.** 6 folds, 5 profitable. Selected-config OOS $7,083, ship-config OOS $11,010, in-sample to out-of-sample Sharpe decay 1.52.

| fold | train | test | picked | is_sharpe | oos_sharpe | oos_net | ship_oos_sharpe | ship_oos_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 326 | 326 | 77 | 2.199 | 0.777 | 775.760 | 0.777 | 775.760 |
| 2 | 326 | 326 | 13 | 1.786 | 0.414 | 594.960 | 0.127 | 164.320 |
| 3 | 326 | 326 | 132 | 1.828 | -0.486 | -1,088.880 | 1.658 | 2,646.560 |
| 4 | 326 | 326 | 107 | 2.710 | 0.613 | 852.080 | 1.021 | 2,657.920 |
| 5 | 326 | 326 | 64 | 2.189 | 0.946 | 2,539.240 | 1.341 | 2,228.840 |
| 6 | 326 | 327 | 138 | 1.988 | 1.333 | 3,409.560 | 0.705 | 2,536.520 |


**Walk-forward, anchored.** 6 folds, 5 profitable. Selected-config OOS $11,035, ship-config OOS $11,010, in-sample to out-of-sample Sharpe decay 0.52.

| fold | train | test | picked | is_sharpe | oos_sharpe | oos_net | ship_oos_sharpe | ship_oos_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 326 | 326 | 77 | 2.199 | 0.777 | 775.760 | 0.777 | 775.760 |
| 2 | 652 | 326 | 14 | 1.650 | 0.073 | 109.360 | 0.127 | 164.320 |
| 3 | 978 | 326 | 72 | 1.222 | -0.486 | -1,232.920 | 1.658 | 2,646.560 |
| 4 | 1304 | 326 | 12 | 1.334 | 1.072 | 2,842.880 | 1.021 | 2,657.920 |
| 5 | 1630 | 326 | 12 | 1.179 | 1.621 | 2,669.000 | 1.341 | 2,228.840 |
| 6 | 1956 | 327 | 12 | 1.252 | 2.685 | 5,871.200 | 0.705 | 2,536.520 |


**Purged k-fold.** selected mean OOS Sharpe 1.51, ship mean OOS Sharpe 1.02, embargo 0 sessions.

| fold | train | test | picked | oos_sharpe | oos_net | ship_oos_sharpe | ship_oos_net |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 1901 | 381 | 12 | 1.053 | 631.520 | 1.558 | 999.080 |
| 1 | 1900 | 381 | 12 | 1.182 | 1,360.080 | 0.386 | 427.520 |
| 2 | 1900 | 381 | 12 | 1.502 | 2,934.120 | 1.017 | 1,619.680 |
| 3 | 1901 | 380 | 12 | 1.541 | 4,635.040 | 1.310 | 3,762.560 |
| 4 | 1901 | 380 | 12 | 1.172 | 2,502.120 | 1.148 | 2,562.840 |
| 5 | 1902 | 380 | 12 | 2.623 | 6,267.080 | 0.677 | 2,625.840 |


**Purged + embargoed.** selected mean OOS Sharpe 1.51, ship mean OOS Sharpe 1.02, embargo 22 sessions.

| fold | train | test | picked | oos_sharpe | oos_net | ship_oos_sharpe | ship_oos_net |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 1879 | 381 | 12 | 1.053 | 631.520 | 1.558 | 999.080 |
| 1 | 1878 | 381 | 12 | 1.182 | 1,360.080 | 0.386 | 427.520 |
| 2 | 1878 | 381 | 12 | 1.502 | 2,934.120 | 1.017 | 1,619.680 |
| 3 | 1879 | 380 | 12 | 1.541 | 4,635.040 | 1.310 | 3,762.560 |
| 4 | 1879 | 380 | 12 | 1.172 | 2,502.120 | 1.148 | 2,562.840 |
| 5 | 1902 | 380 | 12 | 2.623 | 6,267.080 | 0.677 | 2,625.840 |


**Combinatorial purged CV.** 28 backtest paths. Selected-config Sharpe 5/50/95th percentile 0.43 / 1.19 / 1.96; ship-config 0.37 / 1.11 / 1.60. 0.0% of paths put the ship config underwater.


**Locked holdout** (last 30% of sessions, cut at 20230208, read once). Ship config: research $7,850 (Sharpe 1.04) -> locked $4,148 (Sharpe 0.71). Config selected on research: locked $7,924 (Sharpe 1.95).



### 3. Multiple testing and data snooping

The grid is 180 configurations (EMA length x ATR denominator x threshold x VWAP band). Trial Sharpes: mean 0.033, sd 0.022, best 0.095; the ship config ranks 29 of 180.

| test | value | reads |
| --- | --- | --- |
| Probabilistic Sharpe (vs 0) | 0.982 | P(true Sharpe > 0); want > 0.95 |
| Deflated Sharpe (N=180) | 0.425 | benchmark Sharpe from noise alone 0.94 annualised |
| Deflated Sharpe (N=1800) | 0.223 | if the real search was 10x this grid |
| Probability of Backtest Overfitting | 0.153 | CSCV over 924 splits; want < 0.5 |
| Minimum Track Record Length | 5.6 yr | have 9.1 yr |
| White's Reality Check | 0.016 | best of 180 rules vs benchmark |
| Hansen SPA | 0.001 | studentised, drops hopeless models from the recentring |
| Harvey-Liu hurdle | 2.83 | Newey-West t; needs ~3.0, not 2.0 (fails) |


### 4. Costs and capacity

Breakeven round turn $39.70 (16.5 bps of the $24,046 notional) against an applied $2.44 (1.0 bps): **16.3x cushion**. Friction is 6.1% of gross P&L.


Cost sensitivity:

| mult | rt | rt_bps | net | per_trade | sharpe |
| --- | --- | --- | --- | --- | --- |
| 0.00 | 0.00 | 0.00 | 12,783.20 | 39.70 | 0.91 |
| 0.50 | 1.22 | 0.51 | 12,390.36 | 38.48 | 0.89 |
| 1.00 | 2.44 | 1.01 | 11,997.52 | 37.26 | 0.86 |
| 1.50 | 3.66 | 1.52 | 11,604.68 | 36.04 | 0.83 |
| 2.00 | 4.88 | 2.03 | 11,211.84 | 34.82 | 0.80 |
| 3.00 | 7.32 | 3.04 | 10,426.16 | 32.38 | 0.75 |
| 4.00 | 9.76 | 4.06 | 9,640.48 | 29.94 | 0.69 |
| 6.00 | 14.64 | 6.09 | 8,069.12 | 25.06 | 0.58 |
| 8.00 | 19.52 | 8.12 | 6,497.76 | 20.18 | 0.47 |
| 12.00 | 29.28 | 12.18 | 3,355.04 | 10.42 | 0.24 |


Turnover: 35.5 round turns/year, mean hold 5.8 hours (23.0 bars), $1,709,291 notional traded per contract per year.


Capacity under a square-root impact law. volume is broker TICK count, not contracts: capacity is ordinal, not a size.

| contracts | participation | impact_bps | impact_dollars_per_trade | net_per_trade |
| --- | --- | --- | --- | --- |
| 1 | 0.000 | 0.094 | 0.451 | 36.809 |
| 5 | 0.000 | 0.210 | 1.008 | 36.251 |
| 10 | 0.000 | 0.296 | 1.426 | 35.834 |
| 25 | 0.000 | 0.469 | 2.254 | 35.005 |
| 50 | 0.000 | 0.663 | 3.188 | 34.071 |
| 100 | 0.001 | 0.938 | 4.509 | 32.751 |
| 250 | 0.001 | 1.482 | 7.129 | 30.131 |
| 500 | 0.003 | 2.096 | 10.082 | 27.178 |
| 1000 | 0.006 | 2.965 | 14.257 | 23.002 |


### 5. Robustness

| test | value | reads |
| --- | --- | --- |
| Block bootstrap (stationary), Sharpe | 0.86 [0.15, 1.67] | 95% CI, mean block 5 sessions; P(<=0) = 0.008 |
| Block bootstrap (circular), Sharpe | 0.86 [0.15, 1.70] | fixed 5-session blocks |
| Block bootstrap, net P&L | $11,998 [$2,586, $20,415] | 95% CI |
| Trade-sequence permutation (drawdown) | $2,542 vs median $3,056, 95th pct $4,322 | 4th percentile of orderings: the realised drawdown was LUCKY -- plan for the median, not the backtest |
| Random-direction null | p = 0.005 | same trades, coin-flip side |
| MATCHED CONTROL (same side, minute, hold) | p = 0.003 | observed $37.26/trade vs control $-1.71/trade (sd 13.15); 100th percentile |
| Synthetic price paths | p = 0.008 | 120 bootstrapped histories; 48.3% profitable, median $-72.05 |
| Execution noise | median $11,491 | execution noise (2.0 tick sd, 5% dropped); 100.0% profitable |


**Parameter surface.** The ship config sits at the 78th percentile of the 180-point grid; 85.6% of the grid is profitable and 36.7% is within 25% of the ship Sharpe. A broad plateau supports a mechanism; an isolated peak does not.


One-step neighbourhood of the ship setting:

| knob | value | sharpe | net | trades | is_ship |
| --- | --- | --- | --- | --- | --- |
| upper | 75.00 | 0.62 | 10,139.20 | 585 | False |
| upper | 100.00 | 0.86 | 11,997.52 | 322 | True |
| upper | 125.00 | 0.47 | 4,080.76 | 146 | False |
| upper | 150.00 | 0.04 | 158.36 | 46 | False |
| vwap_mult | 1.50 | 0.51 | 5,978.20 | 150 | False |
| vwap_mult | 2.00 | 0.62 | 8,302.04 | 259 | False |
| vwap_mult | 2.50 | 0.86 | 11,997.52 | 322 | True |
| vwap_mult | 3.00 | 0.89 | 13,086.52 | 362 | False |
| vwap_mult | 1,000,000,000.00 | 0.73 | 11,179.60 | 390 | False |
| ema_len | 13.00 | 0.67 | 6,283.60 | 185 | False |
| ema_len | 21.00 | 0.86 | 11,997.52 | 322 | True |
| ema_len | 34.00 | 0.88 | 11,338.36 | 391 | False |
| atr_den | 2.00 | 0.50 | 9,139.12 | 692 | False |
| atr_den | 3.00 | 0.86 | 11,997.52 | 322 | True |
| atr_den | 4.00 | 0.77 | 4,885.40 | 100 | False |


**Risk of ruin**, resampling the observed trade distribution with a 3-trade stationary block (so clustered losses are not resampled away):

| account | p_ruin | median_final | p5_final | median_worst |
| --- | --- | --- | --- | --- |
| 5k/1k drawdown | 0.2199 | $16,936 | $9,519 | $4,680 |
| 10k/2k | 0.0874 | $21,936 | $14,519 | $9,680 |
| 25k/2.5k | 0.0527 | $36,936 | $29,519 | $24,680 |


**Regime breakdown** (Newey-West t, BH-adjusted across all slices):

| dim | bucket | n | total | per_trade | win | nw_t | q |
| --- | --- | --- | --- | --- | --- | --- | --- |
| year | 2016 | 8 | 303.880 | 37.985 | 0.875 | 4.554 | 0.000 |
| year | 2017 | 41 | 569.560 | 13.892 | 0.537 | 1.340 | 0.300 |
| year | 2018 | 36 | 931.760 | 25.882 | 0.472 | 1.109 | 0.401 |
| year | 2019 | 32 | -338.080 | -10.565 | 0.500 | -0.772 | 0.600 |
| year | 2020 | 23 | 429.080 | 18.656 | 0.522 | 0.530 | 0.650 |
| year | 2021 | 41 | 2,147.960 | 52.389 | 0.732 | 1.499 | 0.251 |
| year | 2022 | 37 | 4,286.520 | 115.852 | 0.676 | 2.395 | 0.062 |
| year | 2023 | 34 | 875.840 | 25.760 | 0.588 | 0.515 | 0.650 |
| year | 2024 | 38 | 3,530.680 | 92.913 | 0.684 | 2.415 | 0.062 |
| year | 2025 | 32 | -739.680 | -23.115 | 0.562 | -0.302 | 0.762 |
| vol | high vol | 98 | 6,394.880 | 65.254 | 0.633 | 1.726 | 0.211 |
| vol | low vol | 112 | 1,353.520 | 12.085 | 0.554 | 1.635 | 0.218 |
| vol | mid vol | 112 | 4,249.120 | 37.939 | 0.616 | 2.260 | 0.071 |
| side | -1 | 141 | 10,259.160 | 72.760 | 0.603 | 3.229 | 0.009 |
| side | 1 | 181 | 1,738.360 | 9.604 | 0.597 | 0.573 | 0.650 |


## US30_15m

193,942 decision bars over 2,250 sessions, priced as MYM ($0.50/point, 1.0 tick, $0.72/side, 1 tick slippage, $2.44 round turn).

**Headline.** 270 trades, $1,226 net, $4.54/trade, 50.7% win rate, Sharpe 0.25 (daily, annualised), Newey-West t 0.67, max drawdown $1,344, 30.2 trades/year.

Exits are overwhelmingly the 16:00 cash close, as in the source: 264 cash-close, 1 opposite-cross, 5 session-end. 270 intents admitted and 69 rejected by the VWAP band; 0 reversals; 5 of 2250 sessions blocked.


### 1. Leakage and execution audit

| test | result | verdict |
| --- | --- | --- |
| point-in-time / look-ahead | 25 signal bars re-simulated on truncated data, 0 mismatches | PASS |
| execution alignment | next-open $4.54/trade vs same-bar $-0.30/trade ($-4.83, -106%) | REVIEW |
| survivorship / universe | causal blocking $4.54/tr vs source pre-scan $4.44/tr ($-0.09) | PASS |
| information coefficient | max |IC| 0.024 over 16 feature x horizon tests, threshold 0.15 | PASS |
| normalisation scope | prefix re-run reproduces 117 of 117 trades exactly | PASS |
| index hygiene | 0 duplicate, 0 NaN, 0 OHLC violations, 0.988 contiguous | PASS |


Information coefficients, Spearman against forward returns on the bars the strategy actually decides on (BH-adjusted):

| feature | horizon | n | ic | p | q | leak_flag |
| --- | --- | --- | --- | --- | --- | --- |
| osc | 1 | 13460 | 0.0104 | 0.2274 | 0.4027 | False |
| vwap_dist | 1 | 11215 | 0.0029 | 0.7566 | 0.8070 | False |
| osc_chg | 1 | 13460 | -0.0020 | 0.8143 | 0.8143 | False |
| close_less_ema | 1 | 13460 | 0.0092 | 0.2834 | 0.4027 | False |
| osc | 4 | 13460 | 0.0103 | 0.2313 | 0.4027 | False |
| vwap_dist | 4 | 11215 | -0.0097 | 0.3020 | 0.4027 | False |
| osc_chg | 4 | 13460 | 0.0144 | 0.0958 | 0.3064 | False |
| close_less_ema | 4 | 13460 | 0.0126 | 0.1438 | 0.3286 | False |
| osc | 16 | 13456 | 0.0033 | 0.6982 | 0.7980 | False |
| vwap_dist | 16 | 11211 | -0.0238 | 0.0116 | 0.0931 | False |
| osc_chg | 16 | 13456 | 0.0150 | 0.0820 | 0.3064 | False |
| close_less_ema | 16 | 13456 | 0.0069 | 0.4228 | 0.5204 | False |
| osc | 26 | 13454 | 0.0127 | 0.1416 | 0.3286 | False |
| vwap_dist | 26 | 11210 | -0.0105 | 0.2680 | 0.4027 | False |
| osc_chg | 26 | 13454 | 0.0243 | 0.0048 | 0.0766 | False |
| close_less_ema | 26 | 13454 | 0.0179 | 0.0374 | 0.1994 | False |


### 2. Out-of-sample validation


**Walk-forward, rolling.** 6 folds, 3 profitable. Selected-config OOS $-683, ship-config OOS $1,553, in-sample to out-of-sample Sharpe decay 1.62.

| fold | train | test | picked | is_sharpe | oos_sharpe | oos_net | ship_oos_sharpe | ship_oos_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 321 | 321 | 126 | 1.178 | -1.067 | -1,067.820 | 0.021 | 13.680 |
| 2 | 321 | 322 | 176 | 1.213 | 0.885 | 31.060 | 1.439 | 968.980 |
| 3 | 322 | 321 | 141 | 1.757 | -0.030 | -30.160 | -0.890 | -631.360 |
| 4 | 321 | 322 | 155 | 1.858 | 0.046 | 21.420 | 1.566 | 1,579.220 |
| 5 | 322 | 321 | 168 | 1.988 | -0.338 | -141.360 | -1.322 | -827.450 |
| 6 | 321 | 322 | 0 | 1.619 | 0.412 | 503.450 | 0.545 | 449.850 |


**Walk-forward, anchored.** 6 folds, 3 profitable. Selected-config OOS $-1,694, ship-config OOS $1,553, in-sample to out-of-sample Sharpe decay 0.99.

| fold | train | test | picked | is_sharpe | oos_sharpe | oos_net | ship_oos_sharpe | ship_oos_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 321 | 321 | 126 | 1.178 | -1.067 | -1,067.820 | 0.021 | 13.680 |
| 2 | 642 | 322 | 176 | 0.849 | 0.885 | 31.060 | 1.439 | 968.980 |
| 3 | 964 | 321 | 140 | 0.949 | -0.668 | -570.100 | -0.890 | -631.360 |
| 4 | 1285 | 322 | 176 | 0.674 | 0.696 | 198.620 | 1.566 | 1,579.220 |
| 5 | 1607 | 321 | 75 | 0.612 | -1.516 | -739.750 | -1.322 | -827.450 |
| 6 | 1928 | 322 | 137 | 0.467 | 0.448 | 453.710 | 0.545 | 449.850 |


**Purged k-fold.** selected mean OOS Sharpe -0.03, ship mean OOS Sharpe 0.16, embargo 0 sessions.

| fold | train | test | picked | oos_sharpe | oos_net | ship_oos_sharpe | ship_oos_net |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 1874 | 375 | 137 | 0.304 | 130.040 | -1.174 | -465.980 |
| 1 | 1873 | 375 | 137 | 0.113 | 111.060 | 0.508 | 393.160 |
| 2 | 1873 | 375 | 137 | 0.430 | 500.400 | 0.894 | 678.160 |
| 3 | 1873 | 375 | 0 | -1.112 | -1,497.240 | -0.047 | -51.120 |
| 4 | 1873 | 375 | 75 | -0.397 | -248.560 | 0.439 | 383.860 |
| 5 | 1874 | 375 | 137 | 0.462 | 525.660 | 0.316 | 287.620 |


**Purged + embargoed.** selected mean OOS Sharpe -0.08, ship mean OOS Sharpe 0.16, embargo 22 sessions.

| fold | train | test | picked | oos_sharpe | oos_net | ship_oos_sharpe | ship_oos_net |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 1852 | 375 | 137 | 0.304 | 130.040 | -1.174 | -465.980 |
| 1 | 1851 | 375 | 167 | -0.145 | -113.940 | 0.508 | 393.160 |
| 2 | 1851 | 375 | 137 | 0.430 | 500.400 | 0.894 | 678.160 |
| 3 | 1851 | 375 | 0 | -1.112 | -1,497.240 | -0.047 | -51.120 |
| 4 | 1851 | 375 | 75 | -0.397 | -248.560 | 0.439 | 383.860 |
| 5 | 1874 | 375 | 137 | 0.462 | 525.660 | 0.316 | 287.620 |


**Combinatorial purged CV.** 28 backtest paths. Selected-config Sharpe 5/50/95th percentile -1.29 / -0.14 / 0.75; ship-config -1.17 / 0.18 / 1.39. 39.3% of paths put the ship config underwater.


**Locked holdout** (last 30% of sessions, cut at 20221202, read once). Ship config: research $1,526 (Sharpe 0.44) -> locked $-300 (Sharpe -0.20). Config selected on research: locked $-471 (Sharpe -0.44).



### 3. Multiple testing and data snooping

The grid is 180 configurations (EMA length x ATR denominator x threshold x VWAP band). Trial Sharpes: mean -0.001, sd 0.016, best 0.029; the ship config ranks 21 of 180.

| test | value | reads |
| --- | --- | --- |
| Probabilistic Sharpe (vs 0) | 0.773 | P(true Sharpe > 0); want > 0.95 |
| Deflated Sharpe (N=180) | 0.095 | benchmark Sharpe from noise alone 0.68 annualised |
| Deflated Sharpe (N=1800) | 0.034 | if the real search was 10x this grid |
| Probability of Backtest Overfitting | 0.669 | CSCV over 924 splits; want < 0.5 |
| Minimum Track Record Length | 43.2 yr | have 8.9 yr |
| White's Reality Check | 0.622 | best of 180 rules vs benchmark |
| Hansen SPA | 0.778 | studentised, drops hopeless models from the recentring |
| Harvey-Liu hurdle | 0.67 | Newey-West t; needs ~3.0, not 2.0 (fails) |


### 4. Costs and capacity

Breakeven round turn $6.98 (4.5 bps of the $15,512 notional) against an applied $2.44 (1.6 bps): **2.9x cushion**. Friction is 35.0% of gross P&L.


Cost sensitivity:

| mult | rt | rt_bps | net | per_trade | sharpe |
| --- | --- | --- | --- | --- | --- |
| 0.00 | 0.00 | 0.00 | 1,884.50 | 6.98 | 0.38 |
| 0.50 | 1.22 | 0.79 | 1,555.10 | 5.76 | 0.31 |
| 1.00 | 2.44 | 1.57 | 1,225.70 | 4.54 | 0.25 |
| 1.50 | 3.66 | 2.36 | 896.30 | 3.32 | 0.18 |
| 2.00 | 4.88 | 3.15 | 566.90 | 2.10 | 0.11 |
| 3.00 | 7.32 | 4.72 | -91.90 | -0.34 | -0.02 |
| 4.00 | 9.76 | 6.29 | -750.70 | -2.78 | -0.15 |
| 6.00 | 14.64 | 9.44 | -2,068.30 | -7.66 | -0.42 |
| 8.00 | 19.52 | 12.58 | -3,385.90 | -12.54 | -0.68 |
| 12.00 | 29.28 | 18.88 | -6,021.10 | -22.30 | -1.19 |


Turnover: 30.2 round turns/year, mean hold 5.8 hours (23.1 bars), $938,136 notional traded per contract per year.


Capacity under a square-root impact law. volume is broker TICK count, not contracts: capacity is ordinal, not a size.

| contracts | participation | impact_bps | impact_dollars_per_trade | net_per_trade |
| --- | --- | --- | --- | --- |
| 1 | 0.000 | 0.090 | 0.278 | 4.261 |
| 5 | 0.000 | 0.201 | 0.622 | 3.918 |
| 10 | 0.000 | 0.284 | 0.880 | 3.660 |
| 25 | 0.000 | 0.448 | 1.391 | 3.149 |
| 50 | 0.000 | 0.634 | 1.967 | 2.572 |
| 100 | 0.001 | 0.897 | 2.782 | 1.757 |
| 250 | 0.002 | 1.418 | 4.399 | 0.141 |
| 500 | 0.004 | 2.005 | 6.221 | -1.681 |
| 1000 | 0.008 | 2.836 | 8.798 | -4.258 |


### 5. Robustness

| test | value | reads |
| --- | --- | --- |
| Block bootstrap (stationary), Sharpe | 0.25 [-0.47, 0.90] | 95% CI, mean block 5 sessions; P(<=0) = 0.239 |
| Block bootstrap (circular), Sharpe | 0.25 [-0.47, 0.86] | fixed 5-session blocks |
| Block bootstrap, net P&L | $1,226 [$-2,250, $4,726] | 95% CI |
| Trade-sequence permutation (drawdown) | $1,344 vs median $1,325, 95th pct $2,057 | 52th percentile of orderings: the realised drawdown was typical |
| Random-direction null | p = 0.234 | same trades, coin-flip side |
| MATCHED CONTROL (same side, minute, hold) | p = 0.154 | observed $4.54/trade vs control $-1.97/trade (sd 6.52); 85th percentile |
| Synthetic price paths | p = 0.091 | 120 bootstrapped histories; 47.5% profitable, median $-41.85 |
| Execution noise | median $1,242 | execution noise (2.0 tick sd, 5% dropped); 99.2% profitable |


**Parameter surface.** The ship config sits at the 77th percentile of the 180-point grid; 45.6% of the grid is profitable and 19.4% is within 25% of the ship Sharpe. A broad plateau supports a mechanism; an isolated peak does not.


One-step neighbourhood of the ship setting:

| knob | value | sharpe | net | trades | is_ship |
| --- | --- | --- | --- | --- | --- |
| upper | 75.00 | 0.14 | 992.89 | 524 | False |
| upper | 100.00 | 0.25 | 1,225.70 | 270 | True |
| upper | 125.00 | 0.18 | 579.61 | 96 | False |
| upper | 150.00 | -0.38 | -891.54 | 36 | False |
| vwap_mult | 1.50 | 0.30 | 1,059.85 | 140 | False |
| vwap_mult | 2.00 | -0.03 | -126.97 | 213 | False |
| vwap_mult | 2.50 | 0.25 | 1,225.70 | 270 | True |
| vwap_mult | 3.00 | 0.16 | 808.60 | 300 | False |
| vwap_mult | 1,000,000,000.00 | 0.09 | 442.75 | 315 | False |
| ema_len | 13.00 | 0.32 | 1,094.49 | 114 | False |
| ema_len | 21.00 | 0.25 | 1,225.70 | 270 | True |
| ema_len | 34.00 | 0.46 | 2,714.54 | 364 | False |
| atr_den | 2.00 | -0.15 | -1,226.34 | 636 | False |
| atr_den | 3.00 | 0.25 | 1,225.70 | 270 | True |
| atr_den | 4.00 | 0.21 | 558.99 | 59 | False |


**Risk of ruin**, resampling the observed trade distribution with a 3-trade stationary block (so clustered losses are not resampled away):

| account | p_ruin | median_final | p5_final | median_worst |
| --- | --- | --- | --- | --- |
| 5k/1k drawdown | 0.3206 | $6,212 | $3,315 | $4,369 |
| 10k/2k | 0.0866 | $11,212 | $8,315 | $9,369 |
| 25k/2.5k | 0.0414 | $26,212 | $23,315 | $24,369 |


**Regime breakdown** (Newey-West t, BH-adjusted across all slices):

| dim | bucket | n | total | per_trade | win | nw_t | q |
| --- | --- | --- | --- | --- | --- | --- | --- |
| year | 2016 | 7 | 24.920 | 3.560 | 0.286 | 0.283 | 0.832 |
| year | 2017 | 28 | -329.320 | -11.761 | 0.321 | -2.400 | 0.246 |
| year | 2018 | 25 | 60.000 | 2.400 | 0.480 | 0.085 | 0.932 |
| year | 2019 | 30 | 550.800 | 18.360 | 0.567 | 1.501 | 0.487 |
| year | 2020 | 18 | 164.080 | 9.116 | 0.667 | 0.421 | 0.832 |
| year | 2021 | 38 | -291.220 | -7.664 | 0.579 | -0.675 | 0.832 |
| year | 2022 | 33 | 1,452.980 | 44.030 | 0.606 | 1.297 | 0.487 |
| year | 2023 | 36 | -610.340 | -16.954 | 0.417 | -1.558 | 0.487 |
| year | 2024 | 37 | -330.330 | -8.928 | 0.432 | -0.510 | 0.832 |
| year | 2025 | 18 | 534.130 | 29.674 | 0.667 | 1.659 | 0.487 |
| vol | high vol | 94 | 1,576.290 | 16.769 | 0.574 | 1.038 | 0.641 |
| vol | low vol | 80 | -558.750 | -6.984 | 0.388 | -1.375 | 0.487 |
| vol | mid vol | 96 | 208.160 | 2.168 | 0.542 | 0.338 | 0.832 |
| side | -1 | 116 | 502.760 | 4.334 | 0.466 | 0.334 | 0.832 |
| side | 1 | 154 | 722.940 | 4.694 | 0.539 | 0.686 | 0.832 |

