# The 5-minute ORB paper, tested on NQ

Zarattini, Barbon & Aziz, *A Profitable Day Trading Strategy For The U.S. Equity Market* (2024):
1,600% net over 2016–2023, Sharpe 2.81, annualized alpha 36%, against 198% for passive S&P 500.

Reproduce with `npx tsx scripts/quant-orb-paper.ts`.

## 0. What their strategy actually is

| element | specification |
| --- | --- |
| opening range | the first **5 minutes** |
| direction | **the opening candle's own body** — a bearish opening range permits only shorts and *refuses the upside break outright*. The authors call this the crucial parameter. |
| entry | stop order at the opening-range edge |
| stop | **10% of the trailing 14-day ATR** from entry — an absolute distance, not a fraction of the range |
| target | **none.** Exit at the end of the day. |
| universe | each day's 20 highest relative-volume US stocks — **"Stocks in Play"** |

Both defining choices are now real parameters in `openingRange.ts` (`dirMode`, `stopMode 2` +
`atrFrac`), with four tests. The ATR is built from completed prior sessions only, and the strategy
refuses to trade before it has history rather than inventing a stop.

## 1. The part that cannot be reproduced is the part that earns the money

Their alpha is overwhelmingly cross-sectional. "Stocks in Play" is a **selector**: pick, from ~7,000
names, the 20 with abnormal volume that day, usually because of company news. The paper's own
framing is that limiting day trading to those names is the significant benefit.

**NQ is one instrument.** There is no cross-section to select from, no relative-volume ranking, and
no company news. So what follows tests the mechanical geometry with the engine that generates the
edge removed. That is a real limitation, not a technicality, and it should be read as *"does the ORB
shape survive on a liquid index future"* rather than *"does the paper replicate"*.

## 2. Their specification on NQ, with a locked holdout

| period | n | win% | E | PF | t | P&L |
| --- | --- | --- | --- | --- | --- | --- |
| full sample | 540 | 23.0% | +0.176R | 1.19 | 1.64 | $57,480 |
| research 60% | 326 | 22.1% | +0.202R | 1.26 | 1.41 | +$41,516 |
| validate 20% | 105 | 26.7% | +0.432R | 1.47 | 1.56 | +$35,480 |
| **LOCKED 20%** | 105 | 22.9% | **−0.128R** | **0.71** | −0.75 | **−$18,755** |

Profitable in research and validate, **losing on data selection never touched.** The full-sample
t-statistic is 1.64 and its confidence interval spans zero.

The 23% win rate is not a defect — it is the design. A tight stop with no target produces many small
losses and a long right tail. It also means the implied reward multiple is enormous, which matters
in section 4.

Their two signature choices, isolated:

| variant | n | win% | E | P&L |
| --- | --- | --- | --- | --- |
| paper spec | 540 | 23.0% | +0.176R | $57,480 |
| without the body rule (any break) | 759 | 21.3% | +0.073R | $30,804 |
| **without the ATR stop (opposite edge)** | 544 | **32.4%** | +0.129R | **$100,469** |
| with a 1:2 target instead of end-of-day | 540 | 33.0% | +0.128R | $45,063 |

- **The body rule carries weight.** Removing it more than halves expectancy, 0.176R to 0.073R. That
  is the one component of the paper that transfers to this instrument.
- **The ATR stop costs money here.** Replacing it with the opposite-edge stop nearly doubles total
  P&L, $57,480 to $100,469, at a much higher win rate. A stop sized at 10% of daily ATR is calibrated
  to single stocks; on NQ it sits inside the noise.

## 3. Every combination: 2,400 configurations, selected on research, opened on locked data

| | value |
| --- | --- |
| configurations with enough trades in both ends | 2,400 |
| locked-holdout P&L, mean | **−$3,643** |
| locked-holdout P&L, median | **−$2,968** |
| share profitable on locked data | **36%** |

| rank on research | research $ | validate $ | **LOCKED $** | locked percentile | configuration |
| --- | --- | --- | --- | --- | --- |
| #1 | 68,579 | 75,903 | **−7,925** | 31.7 | or30, any-break, opposite-edge stop, no target |
| #2 | 68,579 | 75,903 | **−7,925** | 31.7 | or30, stop 100% of range, no target |
| #3 | 65,412 | 30,896 | **−33,515** | **1.3** | or30, stop 75%, 1:2 target |
| #5 | 62,876 | 30,084 | **−5,612** | 38.3 | or60, ATR 33% stop, 1:3 target, longs |
| #10 | 58,959 | 70,853 | **−14,825** | 15.8 | or30, stop 100%, 1:3 target |
| **the paper's spec** | 40,195 | 33,972 | **−16,687** | 11.8 | pre-specified, not searched |

**Not one of them makes money on the locked holdout.** The best-on-research lands at the 31.7th
percentile; the third-best at the **1.3rd**. This is the same shape as `STUDY_MEGA_SEARCH.md` found
across 225,792 IB configurations, now reproduced on a completely different strategy family.

Note also that research and validate agree with each other and both disagree with locked. Two
consecutive periods of agreement bought nothing.

## 4. The winner, priced against the search — and the paper's spec against its own variance

| | n | cumulative R | implied b | z | threshold | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| best-on-research, as a single test | 757 | 65.3R | 1.06 | 2.30 | 46.7R | passes |
| best-on-research, priced as best-of-2,400 | 757 | 65.3R | 1.06 | 2.30 | **146.0R** | **fails** |
| paper spec, as a single test | 540 | 95.3R | **4.21** | 2.00 | 78.4R | passes |
| **paper spec, corrected for its own variance** | 540 | 95.3R | 4.21 | 2.00 | **~100.2R** | **fails** |

That last row is the interesting one, and it comes straight out of `STUDY_RMULTIPLE.md`.

The R-multiple framework assumes a clean +b / −1 payoff. The paper's spec has **implied b = 4.21** —
naturally, because it has no profit target and lets winners run — but its **observed variance is
6.85 against the model's 4.21, a ratio of 1.63.** Since the threshold scales with √Var, the correct
bar is about **28% higher**: roughly 100.2R rather than 78.4R. The realised 95.3R clears the naive
threshold and **misses the corrected one**.

And the framework predicted this in advance. Viaggi's result is that null variance equals the reward
multiple, so `N = z²·b/e²`: **a strategy with b = 4.21 needs four times the record of a 1:1 system to
prove the same edge.** A no-target ORB is, structurally, the hardest kind of strategy to validate —
and that is a property of its geometry, not of NQ. The paper's own 5-minute ORB on 7,000 stocks
generates tens of thousands of trades, which is exactly why it can support the claim and a
540-trade single-instrument version cannot.

## 5. Walk-forward

Re-optimising the geometry on a rolling window and trading the next block with whatever won:

| | folds | stitched n | E | P&L | efficiency | fold hit rate |
| --- | --- | --- | --- | --- | --- | --- |
| rolling 250d / 60d | 8 | 152 | +0.086R | +$21,020 | **0.412** | 63% |

Efficiency 0.412 is below the ~0.5 threshold at which a fit is considered to transfer: the median
out-of-sample objective is under half the median in-sample one. The stitched P&L is positive, which
is worth noting honestly — unlike the IB study, where re-optimisation destroyed value outright — but
it comes with only 152 trades and a fit that demonstrably decays between folds.

## 6. Bottom line

- **The paper is not wrong, and this is not a replication failure.** It is a cross-sectional
  strategy whose selector cannot exist on a single future. Removing "Stocks in Play" removes the
  edge, which is what the authors themselves report.
- **The mechanical geometry does not survive on NQ.** Their spec loses $18,755 on locked data, and
  its full-sample t is 1.64.
- **The body rule is the transferable idea.** It doubles expectancy on this instrument and is the
  one component worth carrying into anything else.
- **The ATR stop does not transfer.** 10% of daily ATR is a single-stock calibration; the
  opposite-edge stop nearly doubles P&L on NQ.
- **Searching 2,400 ORB variants made things worse, again.** Mean locked P&L −$3,643, 36%
  profitable, and every top-ranked configuration negative. Third independent strategy family, same
  result.
- **A no-target strategy is the hardest thing to validate.** Its large reward multiple inflates the
  null variance one-for-one. This is why "let winners run" systems need thousands of trades before
  their record means anything.

## Caveats

- One instrument, three years, one regime.
- Our engine requires a bar to CLOSE beyond the level and fills at the next open; a real stop order
  fills at the level, mid-bar. This understates the strategy slightly and never overstates it.
- The ATR here is computed on session-filtered bars, so it is an ATR of the traded window rather
  than of the 24-hour day. That is the right reference for a stop sized inside that window, but it
  is not identical to the paper's daily ATR.
- The internet was not reachable from this session (all outbound requests return 403 from the
  environment's proxy), so no external sources beyond the supplied PDF were consulted.
