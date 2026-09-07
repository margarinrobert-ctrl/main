# Can any of this pass a prop firm evaluation?

The question "which combination is best for a prop firm" is not the question a backtest answers, and
the gap between them is where most funded accounts die. A backtest **sums** P&L. An evaluation is a
**race** between a profit target and a threshold that ratchets up behind every equity high, run under
a minimum-day rule and a consistency rule. The same set of trades in a different order gives a
different answer, so this has to be simulated over paths rather than computed from a total.

Everything below comes from `scripts/quant-prop-firm.ts` and `src/lib/quant/propFirm.ts` (14 tests).

## 0. What the simulator does that a drawdown number does not

Three modelling choices change the answer materially:

- **The threshold is tested against the intraday path, not the closed balance.** Most firms trail the
  peak of *unrealised* equity. A trade that runs 40 points your way and gives it all back has already
  moved the threshold up behind you while booking nothing. Closed-P&L drawdown cannot see this.
- **The threshold locks when the threshold — not the peak — reaches the lock point.** Getting this
  backwards caps the threshold as soon as the account is $100 up and makes every account look far
  safer than it is. This was a real bug, caught by a test before it reached any of the numbers here.
- **Cost is charged at entry**, so the path never shows profit the account has not earned.

Bar excursions use the adverse extreme and the favourable extreme of every bar the position is open,
so one bar can both raise the peak and test the threshold. Within a single bar that is doubly
pessimistic; on 1-minute bars it is small, and erring towards killing the account is the right
direction for a question about surviving one.

## 1. The instrument matters more than the strategy

`MNQ` had to be added to the instrument table to answer this, and its cost structure is the first
finding:

| | round turn | round turn (points) | E on the screenshot config |
| --- | --- | --- | --- |
| NQ | $19.00 | 0.95 | 0.146R |
| MNQ | $2.84 | 1.42 | 0.137R |

The micro has the same tick size and the same one-tick spread, a tenth of the tick value, and a
commission that only falls by a factor of three. So it costs **50% more in points** — 1.42 against
0.95 — and gives up 0.009R of expectancy. That is the price of the position sizing granularity, and
it is worth paying, for reasons that the next table makes obvious.

## 2. Size is the whole game, and one NQ contract is far too big

60 trading-day budget, 8,000 resampled paths, pass% / blow%:

| config | firm | 1x NQ | 2x NQ | 3x NQ |
| --- | --- | --- | --- | --- |
| screenshot | Apex-style | 34.9 / 65.0 | 17.9 / 82.1 | 10.7 / 89.3 |
| screenshot | TopStep-style | 35.2 / 64.8 | 26.4 / 73.6 | 22.0 / 78.0 |
| trio | Apex-style | 25.9 / 74.1 | 13.1 / 86.9 | 8.3 / 91.7 |
| trio | TopStep-style | 27.4 / 72.6 | 17.1 / 83.0 | 14.5 / 85.5 |

**One NQ contract on a $50k account blows it about two thirds of the time.** The reason is arithmetic:
the strategy's own Monte Carlo median drawdown is 10.8% of $50k ≈ $5,400, and the trailing threshold
is $2,500. The account is roughly half the size the strategy's natural variation requires. Adding
contracts makes it monotonically worse — there is no size at which NQ becomes sensible here.

On MNQ the same sweep has an interior optimum:

| config | 1x | 2x | 3x | 4x | 5x | 6x | 8x | 10x |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| screenshot | 0.1 / 0.0 | 20.9 / 2.7 | 49.4 / 16.6 | **59.0 / 31.7** | 56.5 / 41.6 | 49.7 / 49.9 | 41.6 / 58.2 | 33.7 / 66.3 |
| trio | 0.1 / 0.0 | 16.9 / 9.5 | 38.4 / 31.5 | **43.6 / 48.4** | 40.3 / 58.0 | 35.6 / 63.8 | 29.8 / 70.1 | 24.8 / 75.1 |

Note that 10x MNQ ≈ 1x NQ and the numbers agree, which is a useful internal consistency check.

## 3. Patience substitutes for size, and it is a good trade

Two failure modes pull in opposite directions: too big and the threshold kills you, too small and you
never reach the target inside the budget. Sweeping both (screenshot config, Apex-style rules,
pass% / blow% / median trading days to pass):

| budget | 2x | 3x | 4x | 5x | 6x | 8x |
| --- | --- | --- | --- | --- | --- | --- |
| 40d | 5.4 / 1.2 / 35 | 27.1 / 10.8 / 30 | 44.1 / 26.8 / 25 | 49.8 / 39.7 / 21 | 47.7 / 49.0 / 18 | 41.2 / 58.1 / 15 |
| 60d | 20.9 / 2.7 / 48 | 49.4 / 16.6 / 39 | 59.0 / 31.7 / 30 | 56.5 / 41.6 / 23 | 49.7 / 49.9 / 19 | 41.6 / 58.2 / 15 |
| 90d | 46.1 / 4.7 / 63 | 67.6 / 20.2 / 45 | 65.6 / 33.0 / 32 | 58.2 / 41.6 / 23 | 51.1 / 48.9 / 18 | 43.3 / 56.7 / 15 |
| 120d | 64.4 / 6.4 / 74 | 74.2 / 22.2 / 49 | 65.3 / 34.5 / 33 | 56.9 / 43.1 / 24 | 49.3 / 50.7 / 19 | 41.2 / 58.8 / 15 |
| 180d | **82.9 / 8.5 / 85** | 76.8 / 22.9 / 50 | 65.6 / 34.4 / 33 | 57.3 / 42.8 / 23 | 50.3 / 49.7 / 19 | 42.0 / 58.0 / 15 |

The best cell in the entire study is **2x MNQ with a 180-trading-day budget: 82.9% pass against 8.5%
blow.** Every column improves with patience and every row worsens with size. The dominant strategy is
unambiguous: **trade the smallest size that can still reach the target, and give it as long as
possible.** Traders do the opposite, because the fee is charged monthly.

Which is exactly where this falls apart.

## 4. The bill comes in calendar time

Every number above counts *trading* days — days the strategy produced a signal. It signals on 22% of
sessions (screenshot) or 46% (trio). So the 180-day budget that yields 82.9% is **about 39 calendar
months.**

Passing is also not the goal. A payout is, and the funded account runs the same trailing threshold,
so the survival problem repeats with real money. Chaining the two (90-day budget, Apex-style, MNQ):

| config | size | eval pass | funded → payout | joint | evaluations per payout |
| --- | --- | --- | --- | --- | --- |
| screenshot | 2x | 46.1% | 71.1% | 32.7% | 3.1 |
| screenshot | **3x** | **67.6%** | **79.3%** | **53.6%** | **1.9** |
| screenshot | 4x | 65.6% | 71.2% | 46.7% | 2.1 |
| screenshot | 5x | 58.2% | 61.9% | 36.0% | 2.8 |
| trio | 3x | 52.5% | 62.3% | 32.7% | 3.1 |
| trio | 4x | 48.5% | 54.0% | 26.2% | 3.8 |

The best joint probability in the study is **53.6%** — screenshot geometry, 3x MNQ, 90 trading-day
budget. Slightly better than a coin flip to convert one evaluation fee into one first payout.

Translated into the unit the fee is charged in — calendar months, assuming $50/month:

| config | size | eval pass | median months to pass | attempts per payout | expected months | expected fees |
| --- | --- | --- | --- | --- | --- | --- |
| screenshot | 2x | 46.1% | 13.7 | 3.1 | 62 | $3,078 |
| screenshot | 3x | 67.6% | 9.8 | 1.9 | 31 | $1,552 |
| screenshot | 4x | 65.6% | 6.9 | 2.1 | 29 | $1,457 |
| screenshot | 5x | 58.2% | 5.0 | 2.8 | 35 | $1,743 |
| trio | 2x | 35.2% | 6.3 | 4.9 | 45 | $2,265 |
| **trio** | **3x** | **52.5%** | **4.6** | **3.1** | **25** | **$1,229** |
| trio | 4x | 48.5% | 3.2 | 3.8 | 27 | $1,354 |
| trio | 5x | 42.2% | 2.4 | 5.3 | 36 | $1,812 |

The best configuration in the study expects to spend **25 months and $1,229 in fees to reach one
first payout of about $2,000.** Net, before tax, that is roughly $770 over two years for a strategy
that requires watching the open every session. The screenshot's own settings are worse — 31 months
and $1,552 — because the longs-only filter halves the trade count and the calendar clock does not
care that the surviving trades are better.

Note what the ranking rewards: the both-sides trio wins on this metric while *losing* on per-trade
expectancy. Frequency beats edge quality here, because the fee accrues in calendar time.

## 5. What actually binds

It is not the edge, the geometry, the firm, or the drawdown rule. It is **trade frequency.**

The trio signals 115 times a year. A $3,000 target at roughly $10 per trade per MNQ contract needs
about 300 contract-trades, so at 3x that is 100 signals — most of a year — and the trailing threshold
gets a full year of chances to end the run first. Every path in Part B that improves the pass rate
does it by buying more time, and time is exactly what the monthly fee is priced against.

That points at the only fix that changes the answer by an order of magnitude, and it is not a better
IB configuration: **more uncorrelated setups.** Four rules of this quality firing on different
sessions would reach the target in a quarter of the calendar time with the same threshold exposure,
and would smooth the day-to-day path that the consistency rule punishes. This repo has tested nine
strategy families and found one that survives; the productive next move is finding a second and a
third, not tuning this one further.

## 6. How much of this is the edge, and how much is luck?

Every number above assumes the measured expectancy is real and persists. It rests on t = 2.46 over
349 trades, which is not certain. Charging extra cost per round turn models worse fills, a decayed
edge, or both (90-day budget, Apex-style, pass% / blow%):

| extra cost | screenshot E | 3x | 4x | 5x | | trio E | 3x | 4x | 5x |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +$0 | 0.137R | 67.5 / 20.3 | 65.5 / 33.1 | 58.2 / 41.6 | | 0.088R | 52.1 / 38.0 | 48.2 / 50.4 | 41.8 / 58.0 |
| +$1 | 0.128R | 63.9 / 22.3 | 62.9 / 35.7 | 56.1 / 43.7 | | 0.078R | 49.4 / 40.4 | 45.6 / 53.1 | 39.5 / 60.2 |
| +$2 | 0.119R | 60.5 / 24.7 | 60.1 / 38.4 | 53.9 / 45.9 | | 0.069R | 46.2 / 43.0 | 43.0 / 55.5 | 37.7 / 62.0 |
| +$4 | 0.101R | 53.5 / 29.6 | 54.3 / 43.5 | 49.4 / 50.3 | | 0.051R | 39.8 / 48.7 | 38.4 / 60.1 | 33.6 / 66.0 |
| +$7 | 0.074R | 43.1 / 38.2 | 45.8 / 51.6 | 42.3 / 57.4 | | 0.023R | 30.7 / 57.2 | 31.1 / 67.1 | 27.9 / 71.6 |

Degradation is graceful rather than cliff-edged, which is mildly reassuring. But the last row is the
finding that matters most in this whole document:

**At +$7 per round turn the trio's expectancy is 0.023R — effectively nothing — and it still passes
31% of the time.** A strategy with no edge at all passes an Apex-style evaluation roughly a third of
the time, because a $3,000 target against a $2,500 threshold over 90 days is a nearly fair coin.

So the entire measured edge is worth **21 percentage points** of pass rate: 52% against a 31% floor
that random trading achieves. Two consequences follow, and both are uncomfortable:

1. **Passing an evaluation is weak evidence that a strategy works.** Roughly a third of people who
   pass with no edge whatsoever will conclude, reasonably and wrongly, that their method is sound.
   The funded account then tests it against the same threshold, indefinitely.
2. **The firm's economics do not require its traders to lose.** With a ~31% baseline pass rate and
   fees charged monthly against a slow clock, the fee stream stands on its own.

## 7. Bottom line

**The best combination in this study:** structural trio (both sides — flatten 11:59, 80% stop, fixed
1:1 target, no direction filter), **3x MNQ**, Apex-style $50k, sized small and given as much time as
the rules allow. 52.5% evaluation pass, 32.7% joint probability of converting a fee into a first
payout, expected 25 months and $1,229 in fees per ~$2,000 payout.

**And it is not a good proposition.** Roughly $770 net over two years, for a strategy that requires
watching the open every session, where 31 of the 52 percentage points of pass probability would be
there with no edge at all. That is the honest answer to the question, and the arithmetic behind it is
in `scripts/quant-prop-firm.ts` so it can be re-run against a different fee, firm, or target.

Three things would change it, in descending order of impact:

1. **More uncorrelated setups.** The binding constraint is 115 signals a year against a fee charged
   in calendar months. This is the only fix worth an order of magnitude.
2. **A larger account for the same size.** Every table here is dominated by the ratio of position
   size to the trailing threshold. A $100k or $150k account traded at 3x MNQ moves every row up.
3. **A firm whose threshold does not trail intraday.** The TopStep-style end-of-day rule was
   consistently kinder in Part A at small size, because it ignores unrealised spikes that ratchet the
   Apex-style threshold up behind you.

What would *not* change it: more parameter tuning on this strategy. The walk-forward in
`STUDY_IB_SCREENSHOT.md` already showed that re-optimising the geometry destroys value relative to
leaving it fixed.

## Caveats

- Rule sets are modelled on publicly described $50k evaluations and were **not verified against
  current terms**. Firms change targets, thresholds, consistency rules and payout schedules
  frequently; re-check before relying on any row here.
- Funded-phase payout requirements are simplified to "reach $2,000 profit across at least 8 trading
  days without touching the threshold". Real schedules add safety-net balances, withdrawal caps and
  winning-day definitions that this does not model.
- Sessions are resampled with replacement, which assumes they are exchangeable. They are not
  perfectly — volatility clusters — so real paths have somewhat fatter tails than these.
- All of it inherits the parent limitation: one instrument, four years, a single market regime.

## 8. Correction — the geometry above was not the best one

Sections 1–7 test the *screenshot* geometry (25% retracement, fixed 1:1) because that is what the
question arrived attached to. It is not the best-performing configuration in this repo. Re-running
the same simulation against the validated v3 geometry — **50% retracement, 80% stop, fixed 1:2** —
changes the answer substantially (Apex-style, 90-day budget, 6,000 paths):

| geometry | n | E | signals | size | eval pass | blown | funded → payout | joint | months / fees |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| retr 25, 1:1 | 349 | 0.088R | 45.6% | 3x | 52.1% | 38.0% | 62.2% | 32.4% | 25 mo / $1,240 |
| retr 50, 1:1 | 167 | 0.229R | 21.8% | 3x | 66.0% | 7.6% | 80.7% | 53.3% | 36 mo / $1,789 |
| retr 50, 1:1 | 167 | 0.229R | 21.8% | 4x | 73.3% | 18.4% | 80.3% | 58.8% | 28 mo / $1,376 |
| **retr 50, 1:2** | **167** | **0.308R** | **21.8%** | **3x** | **76.4%** | **10.6%** | **84.3%** | **64.4%** | **27 mo / $1,370** |
| retr 50, 1:2 | 167 | 0.308R | 21.8% | 4x | 74.7% | 22.4% | 77.4% | 57.8% | 26 mo / $1,286 |

**The v3 geometry roughly doubles the joint probability — 64.4% against 32.4% — at the same calendar
cost**, and cuts the blow-up rate from 38% to 10.6%. Section 5's claim that frequency beats edge
quality holds only *within* a fixed geometry; across geometries, an edge large enough (0.308R against
0.088R) more than compensates for signalling half as often.

3x is the recommendation over 4x: near-identical cost and joint probability, at less than half the
blow-up rate.

The luck-floor finding in section 6 is unaffected and still the most important line in this document.
A no-edge strategy passes about 31% of the time, so even at 76.4% roughly two fifths of the pass
probability is coming from the coin rather than the method.
