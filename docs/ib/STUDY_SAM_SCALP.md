# The best scalping version of SAM-Fut

*What ran:* 95,230,080 combinations of a SAM-anchored rule space, through the same five phases
every shipped strategy on this branch went through.

*What came out:* three scalps that beat a matched random entry on the holdout, two of them
shippable to TradingView. Added to the book they raise Sharpe from 3.73 to 4.39 and **lower**
drawdown when added one at a time — the opposite of what the first, naive SAM attempt did.

---

## 1. Why the first attempt found nothing

`STUDY_SEMIVARIANCE.md` swept 4,032 combinations of SAM and concluded it was null. That sweep
took the paper's own reading — is the rolling sum of RS+ minus RS− negative — and varied only the
window and the geometry. It was not a search of the signal, it was a search of one point in it.

Three axes were missing, and each changes what the signal means:

| axis | why it matters |
| --- | --- |
| **estimator** | `i` intrabar, realized semivariance from the 1-minute returns inside each bar — what the paper does with 30-minute returns inside a day. `b` bar-return, from the bar's own close-to-close move. |
| **normalisation** | raw SAM's scale depends on volatility, so only its *sign* is comparable across regimes — which is exactly why the original only ever tests `< 0`. **ratio** (RS+ − RS−)/(RS+ + RS−) is bounded in [−1, 1] and means the same thing in a quiet market and a violent one. **z** standardises SAM against its own trailing 100-bar distribution: "unusually asymmetric *for this market lately*". |
| **reading** | the paper's is a *state*. A scalp is more naturally the *cross* — the moment asymmetry flips. |

12 windows × 2 estimators × (raw + 7 ratio thresholds + 7 z thresholds) × 2 directions × 2
readings = **1,440 SAM conditions**.

## 2. The search

Every rule contains at least one SAM condition — the question is the best scalping version of
*this* signal, not the best rule, and that search already ran (`STUDY_1R_MEGA.md`).

    1,440 SAM conditions alone
  + 1,440 x 198 ladder conditions   =   285,120
  + C(1,440, 2) SAM AND SAM         = 1,036,080
  ------------------------------------------------
    1,322,640 rules
  x 6 stop widths x 3 flatten times x 2 directions = 47,615,040 per timeframe
  x 2 timeframes (30m, 15m)                        = 95,230,080 combinations

> A 5-minute pass of the same design was built and started. Each of its eight chunks needs longer
> than a single call allows in this environment, and a half-finished timeframe is worse than an
> absent one, so it was discarded rather than partially reported. The design is in
> `sam_mega.py` and `python3 research/sam_mega.py 5 <chunk> 8` runs it.

Gates, all unchanged from the rest of the branch: calendar ban, base-rate excess against the
population mean of the rule's **own side and geometry**, subset coherence on every condition,
geometry tuned on research, and each condition finally tested against a **random filter of the
same selectivity on the locked block**.

| | 30m | 15m |
| --- | --- | --- |
| combinations | 47,615,040 | 47,615,040 |
| clear the minimal bar | 10,299,685 | 10,033,516 |
| no calendar condition | 10,206,464 | — |
| 55%+ research win with positive excess | 1,529,167 | — |
| survive subset coherence | 775,743 | — |
| tuned rule/direction pairs | 389,254 | 211,072 |
| after collapsing rules sharing any condition | 80 | 80 |
| a condition beats a random filter on the **locked** block | 14 | 17 |
| also clear their base and make money there | 12 | 17 |

## 3. The matched control, which decides it

Random entries with the same side, geometry and minute-of-day distribution. **80 candidates per
timeframe reach this test, so about four pass at p < 0.05 by chance.** That number belongs next
to the results, not after them.

| | rule | tf | dir | locked n | locked win % | control | **p** | locked $ | **p** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **SF3** | SAZi8 x-below −1 AND SAZb6 > 0.5 | 15m | long | 30 | **73.3** | 51.0 | **0.002** | 2,717 | **0.022** |
| **SF1** | SAZb2 x-below 1.5 AND SARb16 < −0.3 | 30m | short | 24 | 66.7 | 47.0 | **0.022** | 892 | 0.072 |
| **SF2** | SAZb16 x-below 1.5 AND outside bar | 15m | short | 34 | 55.9 | 47.1 | 0.177 | 1,787 | **0.017** |
| | SAZi3 x-above 1 AND SAZb8 x-above −1.5 | 15m | long | 26 | 61.5 | 48.8 | 0.072 | 1,148 | **0.017** |
| | SARi34 x-above −0.1 AND SAZb8 < −1.5 | 15m | short | 41 | 53.7 | 47.5 | 0.209 | 2,087 | **0.030** |
| | SARb8 x-below 0.1 AND second hour | 30m | long | 27 | 66.7 | 56.5 | 0.132 | 3,552 | 0.055 |
| | SAZi5 x-above −0.5 AND SARi13 x-above −0.2 | 30m | long | 42 | 50.0 | 48.3 | 0.454 | −144 | 0.439 |
| | SAZi2 x-above −0.5 AND SAZi4 > 1 | 30m | long | 36 | 41.7 | 51.9 | 0.875 | 551 | 0.459 |

Three separate at p < 0.05 on win rate or net on the block nothing was chosen on. SF3 is the
strongest thing this search produced and clears both.

One candidate is worth naming as a failure: `SARb8 x-below 0.1 AND second hour` looks excellent
(74.7% win, $3,552 locked) and is a **drift bet** — 78% of its trades exit at the 16:00 flatten
and 76% of its net comes from there. The exit split catches what the win rate hides.

## 4. The three, in full

| | rule | tf | dir | stop | trades | win % | base | net $ | locked $ | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **SF1** | SAZb2 x-below 1.5 AND SARb16 < −0.3 | 30m | **short** | 1.0×ATR | 84 | 69.0 | 43.9 | 3,786 | 892 | 2.71 | 1.82 |
| **SF2** | SAZb16 x-below 1.5 AND outside bar | 15m | **short** | 2.0×ATR | 95 | 56.8 | 43.7 | 3,549 | 1,787 | 2.29 | 1.55 |
| **SF3** | SAZi8 x-below −1 AND SAZb6 > 0.5 | 15m | long | 2.5×ATR | 91 | 71.4 | 46.8 | 5,731 | 2,717 | 2.75 | 1.82 |

Two of the three are **shorts**, which is the hard direction on a sample where NQ rose 89% — a
short has to beat a 43.9% base rate rather than a 48% one, and drift works against it the whole
time.

### SF1, put through the rest of the battery

| | |
| --- | --- |
| exit split | 55% at target (**151% of net**), 18% at stop, 27% at the time stop (**−1% of net**) |
| median hold | **1 bar** — a real scalp |
| engine → true 1-minute path → +refill | $3,786 → $3,701 (PF 2.83) → $3,817 |
| $/trade at 1× / 2× / 3× costs (locked) | 37 / 34 / 31 — **breakeven at 13.0× measured costs** |
| block bootstrap, locked | 5th pct $414, median $881, **P(net < 0) = 0.00** |
| walk-forward, 6 folds | 478 · 938 · 605 · 940 · 674 · 152 — **6/6 positive** |
| max drawdown | **$231** on $3,786 of profit |

It earns at the barrier, not at the clock. That is the distinction that separated every real
result on this branch from every fake one.

## 5. Correlation matrix and what they do to the book

SF1, SF2 and SF3 against the nine shipped strategies:

| | max \|ρ\| against the nine |
| --- | --- |
| SF1 | **0.10** |
| SF2 | **0.05** |
| SF3 | **0.10** |

Near-orthogonal — they are looking at something none of the nine looks at.

| book | net $ | locked $ | Sharpe | Sortino | maxDD $ |
| --- | --- | --- | --- | --- | --- |
| the nine | 55,424 | 25,528 | 3.73 | 5.88 | 1,289 |
| **nine + SF1** | 59,210 | 26,419 | **3.97** | **6.52** | **1,236** |
| nine + all three | 68,490 | 30,923 | **4.39** | **7.26** | 1,830 |

Adding SF1 alone raises Sharpe *and lowers drawdown*. Compare the naive SAM leg in
`STUDY_SEMIVARIANCE.md`, which was equally decorrelated and cut Sharpe from 3.73 to 3.23: a
decorrelated leg helps only if it has an edge of its own, and these do.

## 6. What ships, and what does not

**`pine/samScalp/SF1_strategy.pine` and `SF2_strategy.pine`** — both lint clean. The emitted Pine
formula was reimplemented from scratch and reproduces the research triggers **exactly**: 84 and 84.

**SF3 cannot ship**, and this is a hard limit rather than an omission. It uses the intrabar
estimator, which needs the 1-minute bars inside each chart bar; `request.security_lower_tf` is
capped near 100,000 intrabars and three years of 15-minute bars asks for over a million. The
result is measurable here and not runnable there. A script that silently returns `na` over most
of its chart would be worse than saying so.

## 7. Honest limits

1. **80 candidates per timeframe reached the matched control**, so roughly four pass at p < 0.05
   by chance. Three did. SF3 at p = 0.002 is the only one comfortably clear of that; SF1 and SF2
   are one-tailed marginal and should be treated as such.
2. **24 to 34 locked trades each.** That is thin, and it is thin for the same reason everything
   on this branch is: three years of data and a rule that fires roughly 30 times a year.
3. **The winning reading is not the paper's.** Every survivor uses the z-score or ratio
   normalisation and a *cross*, not raw SAM as a state. The paper's own reading — long when raw
   SAM is negative — fails on the research block before any holdout is involved
   (`STUDY_SEMIVARIANCE.md` §3).
4. **The 5-minute pass is missing**, which is the timeframe a scalper would most want.

## Files

| | |
| --- | --- |
| `research/sam_pool.py` | the 1,440 SAM conditions: 2 estimators × 12 windows × 3 normalisations |
| `research/sam_mega.py` | Phase 1, chunked, with a cached bitset per timeframe |
| `research/sam_phases.py` | Phases 2–5: gate, tune, validate on locked, select decorrelated |
| `research/sam_pine.py` | emitters; refuses to ship an intrabar rule |
| `pine/samScalp/SF1,SF2_{strategy,indicator}.pine` | four scripts |

Measured on MNQ, 2022-12-26 → 2025-12-12, one contract, $1.00 commission per round turn, one tick
spread plus one tick slippage each side, one extra tick on stops. Research tooling for education
and analysis, not financial advice.
