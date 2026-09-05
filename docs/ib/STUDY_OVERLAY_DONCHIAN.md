# Donchian trend follower + a 1-minute mean-reversion execution overlay

`research/overlay/`, `results/overlay/gates.txt`, `results/overlay/battery.txt`.

## Verdict

**Do not believe the overlay.** It reads as a +436.8 point improvement on a +107,608
point baseline -- **+0.41%**, +0.104 points a trade, Sharpe 1.021 -> 1.030 -- and every
one of the skill's own disbelief conditions fires. The gain sits **inside the placebo
band** (observed +436.8 against a random-delay 5-95% of [-2,106.5, +914.9], percentile
87.5, one-sided p 0.125), it is **62.4% dropped trades and only 37.6% entry price**
while being sold as fill quality, the paired block bootstrap cannot separate the two
arms (mean daily difference +0.47, p **0.706**; Sharpe difference +0.009, p **0.357**),
and it dies at a fill haircut of **0.0210 bps a side against half the Roll implied
effective spread of 0.1871** -- a ratio of **0.11**, i.e. it is claiming roughly nine
times more price improvement than the spread it would be trying to earn.

The four "dropped trades" that supply most of the gain are four observations, all
losers (mean -68.77 against the kept trades' +21.40). That is a filter result on n=4,
not an execution result, and it would need its own trial count to mean anything.

What would change it: a fast signal that clears the bounce floor (a per-trade edge
above ~0.19 bps rather than 0.03), or a slow strategy whose entries are actually
chased -- and `STUDY_V50_SELECTION` already measured the adverse open gap on these
continuous futures at **+0.0000 ATR**, because the next open IS the prior close. There
is no chasing cost here for an overlay to recover.

## Setup

| | |
| --- | --- |
| Instrument | NQ (the only feed on this branch with 1-minute bars, so no cross-market read) |
| Slow bars | 30-minute |
| Fast bars | 1-minute |
| Sample | 2022-12-26 -> 2025-12-12, 923 trading days |
| Baseline (frozen) | Donchian 20 long breakout, stop `signal_close - 2.5 x ATR(14)`, no target, 480-bar (240h) clock, 1 unit, both sides of the round turn charged (0.86 pts) |
| Fast signal | `z = (close - EMA20) / ATR20` on 1-minute bars |
| Gate rule | after a long breakout, wait while `z[j-1] > 0` (price still extended above its own fast mean), then buy the next open |
| Urgency window K | 30 minutes, swept 5/10/15/30/60/120 |
| Fill model | taker both arms -- the same round turn is charged on the same side, so no free price improvement is booked |

The stop **level**, the exit **clock** and the **size** are computed from the signal bar
in both arms and are byte-identical. Only the entry timestamp and the entry price differ.
If the stop level is breached while the overlay is waiting, the overlay skips the trade
(status 1) rather than entering behind the market.

**Concurrency caveat, stated up front.** There is no position lock: all 5,045 signals are
taken independently, ~6.7 a day on 30-minute bars. That is deliberate -- the question is
about entry timestamps, not about a book -- but it means the baseline is not a tradeable
strategy and the Sharpe figures are per-signal, not per-account. The branch's own rule
(`research/atme/`: check concurrency before calling an every-bar configuration a strategy)
applies to the baseline, not to the comparison.

## The four screening gates

| Gate | Result |
| --- | --- |
| 1. Horizon separation | **PASS on ratio, FAIL on magnitude.** Fast AR(1) rho 0.8934 -> half-life 6.1 min against a 926-min median hold = **151x**, far past the 10x the skill asks. But the fast drift at the signal bars is **-0.0422 bps** against a slow accrual of **+1.4880 bps/min** -- **0.03x**. The skill requires the fast drift be "comparable in magnitude to (or larger than)" the slow accrual. It is not: waiting is almost pure cost against the thesis. |
| 2. Sign opposition | **Setup right, forecast absent.** The breakout does fire into extension -- z = +0.4356 ATR at signal bars against +0.0484 on all bars, 63.5% extended -- which is exactly the configuration the overlay wants. But the next-minute return by z quintile is **non-monotone** (+0.0304, -0.0053, -0.0058, +0.0138, -0.0031 bps) with a Q1-Q5 spread of **+0.0335 bps**. There is no reversion gradient to schedule against. |
| 3. Slow strategy net-profitable | **PASS.** 5,045 trades, +21.330 points/trade, +0.1378% of entry price, win 15.0%, total +107,608 points, net of both sides. |
| 4. Bounce floor (Roll) | **FAIL.** Traded directly (long the bottom z quintile, hold one minute) the fast signal earns **+0.0304 bps** gross against half the Roll implied effective spread of **0.1871 bps** -- ratio **0.16**. The "mean reversion" is substantially bid-ask bounce in the print series. Against the 0.850 bps round turn the signal is informational and not monetizable, which is the overlay premise -- but a gate-4 failure means every later number needs the placebo to be believed at all. |

Two of four gates fail. The overlay was built and run anyway, because a gate-4 failure is
explicitly the case the skill says to test with the placebo rather than discard.

## Baseline vs overlay

| Metric | Baseline | Overlay | Δ |
| --- | ---: | ---: | ---: |
| Trades | 5,045 | 5,041 | -4 |
| Points / trade | +21.330 | +21.433 | +0.104 |
| % of entry price / trade | +0.1378 | +0.1378 | +0.0000 |
| Win rate | 14.99% | 15.02% | +0.03 pp |
| Total points | +107,608 | +108,044 | **+436.8 (+0.41%)** |
| Median hold (min) | 926 | 915 | -11 |
| Sharpe (daily, annualised) | 1.021 | 1.030 | +0.009 |
| Max drawdown (pts) | -55,045 | -54,829 | +217 |
| Worst day (pts) | -3,261 | -3,220 | +41 |
| CVaR 5% (pts) | -1,820 | -1,803 | +17 |

The tails do not worsen, which is the one thing the overlay has going for it -- and it is
what a four-trade difference on 5,045 trades should look like either way.

**The urgency sweep is shapeless**, which is the skill's own disqualifier: total Δ runs
+862, +91, +367, +437, +700, +878 points at K = 5, 10, 15, 30, 60, 120 minutes. It does not
rise or fall with the timeout, the median delay is **2 bars at every K**, and the spread
across K (+91 to +878) is twice the headline result. "If the result only works at one value
of K, it isn't a result" -- here it works at no particular value of K, which is the same
statement with more noise.

## Attribution of the PnL difference

| Component | Points | % of Δ |
| --- | ---: | ---: |
| Entry price improvement (5,041 matched) | +161.8 | +37.6% |
| Exit price improvement | 0.0 | 0.0% |
| **Dropped trades (n = 4)** | **+268.2** | **+62.4%** |
| Added trades | 0.0 | 0.0% |
| Residual | 0.0 | 0.0% |

Exit improvement is exactly zero by construction -- the exit clock and stop level are
identical in both arms, so there is no free-option exit here and no fattened left tail.
That removes one of the four ways a naive delay backtest lies, and leaves the other three.

The majority of the gain is **population change**, not fill quality: four signals whose
stop level was breached while the overlay waited, all four losers. Sold as a filter this
is a claim about four observations; sold as execution it is mislabelled.

## Falsification

- **Roll implied spread vs per-trade edge.** Half-spread 0.1871 bps, direct fast edge +0.0304 bps, **ratio 0.16**.
- **Random-delay placebo**, 200 seeds drawing from the observed delay distribution: real Δ **+436.8**, placebo mean **-643.8**, placebo 5-95% **[-2,106.5, +914.9]**, percentile **87.5**, one-sided **p 0.125**. The tool's own verdict: *improvement is within the placebo distribution -- the fast signal is not the source of the gain.* Note the placebo mean is negative, so the placebo does not reproduce the gain in the usual sense -- mechanical delay on this strategy is on average harmful. What it does is put the observed number comfortably inside the null's spread, which is the same conclusion by a different route: a delay rule with no information in it lands here about one time in eight.
- **Paired block bootstrap** (5,000 draws, block 10, 923 daily observations): mean daily difference **+0.4733**, 95% CI **[-1.9228, +2.9794]**, **p 0.7062**; Sharpe difference **+0.0094**, CI **[-0.0110, +0.0300]**, **p 0.3574**.
- **Cost sweep.** The improvement is positive at all ten commission x slippage cells -- and it **grows with slippage**, +430 at 0 bps to +450 at 1.5 bps. That is not robustness, it is the population-change tell: the overlay takes four fewer trades, so its advantage mechanically scales with the per-trade cost rather than with any price it captures.
- **Slippage breakeven.** The advantage vanishes at a fill haircut of **0.0210 bps/side**, **0.11x** half the implied spread.
- **Skipped signals.** 4 (0.08% of baseline trades) at K <= 30, 5 at K >= 60. Counterfactual baseline PnL **-275 points**, mean **-68.77** against the kept trades' +21.40. Not foregone winners -- but four observations.

## What this adds to the branch

Nothing to ship, and one thing to keep: **`STUDY_V50_SELECTION`'s chasing result is now
confirmed from the execution-overlay side.** V50 measured the adverse open gap on continuous
futures at +0.0000 ATR and concluded no market-entry backtest here is quietly paying a
chasing cost. This study asked the complementary question -- if there is no chasing cost,
is there anything for a scheduler to save? -- and the answer is 0.41% of PnL, inside the
placebo band, 62% of it from four trades. An execution overlay recovers implementation
shortfall, and on this instrument at this bar size there is essentially none to recover.

Also worth keeping as method: the skill's **attribution decomposition is what makes the
verdict legible**. A +0.41% headline with a non-significant paired test would normally be
filed as "too small to matter". Splitting it into entry price and dropped trades turns it
into a specific, falsifiable claim -- and that claim (four losing trades) is small enough
to state exactly.

---

# Addendum: the position lock, and what it corrects

The concurrency caveat above was the one real defect in the study, and repairing it changes
which objection is the binding one. **It does not change the verdict.**

`ov_core.walk` now takes `lock=1`: a signal is refused while a previous trade is still open,
each arm locking on its own exit bars. `research/overlay/run_ov3.py`, `run_ov4.py`;
`results/overlay/locked.txt`, `blocks.txt`, `concentration.txt`.

## What the lock does to the baseline

| | Unlocked | Locked |
| --- | ---: | ---: |
| Trades | 5,045 | **227** (4,873 blocked) |
| Points / trade | +21.330 | **+62.043** |
| % of entry price | +0.1378 | +0.3399 |
| Total points | +107,608 | +14,084 |
| Sharpe | 1.021 | **1.249** |
| Max drawdown | -55,045 | -2,766 |

The unlocked figure counted the same move up to twenty times. The locked book is the one an
account can carry, and it is the correct baseline for the comparison.

## The lock reverses four of the five falsification tests

| Test | Unlocked | Locked |
| --- | --- | --- |
| Total Δ | +436.8 (+0.41%) | **+508.5 (+3.61%)** |
| Attribution | 62.4% dropped trades, 37.6% entry price | **100.0% entry price**, 0 dropped, 0 added, 0 stopped while waiting |
| Placebo (whole sample) | pctile 87.5, p 0.125 | **pctile 100.0, p 0.0000** |
| Paired bootstrap | mean p 0.706, Sharpe p 0.357 | mean p **0.083**, Sharpe p **0.099** |
| Haircut breakeven vs half-spread | 0.0210 bps, ratio **0.11** | 0.558 bps, ratio **2.98** |
| Urgency sweep | shapeless (+862/+91/+367/+437/+700/+878) | **rises then plateaus** (+118/+150/+406/+508/+506/+518 at K = 5/10/15/30/60/120) |

**This corrects the attribution finding in the main study.** "62.4% dropped trades, n=4" is a
property of the unlocked baseline, not of the strategy: with the lock the overlay drops nothing
at all and the entire difference is entry price. The cost stress confirms it -- Δ is exactly
+508 points at 1x, 2x, 4x and 8x the round turn, because the trade counts are identical and cost
cancels. There is no population change left to hide behind.

## And then the block split kills it anyway

The overlay had never been read against the branch's own split. Splitting the 227 trades by the
block their entry bar sits in:

| Block | n | Baseline pts | Overlay pts | Δ / trade | Total Δ | Δ % | Placebo p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| research | 151 | +56.161 | +56.747 | **+0.586** | +88 | +1.04% | **0.1250** |
| locked | 76 | +73.728 | +79.255 | **+5.526** | +420 | +7.50% | 0.0000 |

**Absent on research, appearing on locked.** 83% of the whole-sample gain lives in the block that
should show decay, and the research block -- the only one the K of 30 could have been chosen on --
fails its own placebo at p 0.125. The research-block **median** per-trade difference is exactly
**+0.000 points**. This is the wrong shape, for the eighth time on this branch.

## The concentration, which settles it

| Share of trades | Share of the +508 point gain |
| --- | ---: |
| Top 1% (2 trades) | **32.0%** |
| Top 3% (7 trades) | 76.7% |
| Top 5% (11 trades) | **101.1%** |
| Top 10% (23 trades) | 147.7% |

Eleven trades supply the entire gain; the other 216 lose in aggregate. The single largest is
+107 points = 21.1% of the total, and it is in the research block. Per trade: **50.2% better,
33.0% unchanged, 16.7% worse**, median +0.250 points against a mean of +2.240.

## What it actually is, and why that matters

The mean entry improvement is **+2.240 points = +1.162 bps**, against half the Roll implied
effective spread of **0.1871 bps** -- **6.2x**. No amount of waiting captures six half-spreads.
This is not a better fill at the same level; it is a **better level**, reached by waiting a
median 3 minutes for a pullback. That is the branch's entry-mechanic finding
(`STUDY_LIMIT_ENTRY`, `research/atme/`, `STUDY_V58_ANATOMY` -- the sixth route to it) arriving
in execution costume.

The distinction is not pedantic: an execution improvement is judged against half the spread and
carries no selection burden, while a pullback entry is a **signal change** and carries the trial
count of one. Judged as what it is -- a new entry rule read on 227 trades, failing on the
research block, carried by eleven trades out of 227 -- it is not a result.

**The verdict is unchanged: do not trade the overlay.** The reason changes. Under the unlocked
baseline it was a four-trade filter mislabelled as fill quality; under the correct locked
baseline it is a pullback entry that does not exist on the research block.
