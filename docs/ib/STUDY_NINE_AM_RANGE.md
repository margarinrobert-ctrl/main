# The 09:00–09:30 range, a 09:30 breakout and an EMA 13/48 momentum gate — US30

**Verdict: null on US30 at every setting of every parameter, and the one genuinely new thing in the
study is a base rate rather than a strategy.**

Asked for: *mark the 9am high and low, wait for a breakout at the 9:30am open, use the EMA cross
for momentum, make the strategy and test it with all parameters* — then, mid-run, *do it for us30*.

---

## 0. Phase 0, written before any code ran

The half hour before the cash open is where overnight inventory is repositioned ahead of the
opening auction, so its extremes are levels at which a lot of resting orders sit. That names a
population of orders. It does not name a counterparty who **must** trade at a bad time: no
redemption, no index roll, no margin call. Under the mechanism-first architecture this is a
**fitted pattern wearing a story** and it carries the full deflation burden rather than escaping
it.

What the branch already knew, none of it re-discovered here:

* `STUDY_V35_BALANCE` swept 11 window starts × 4 lengths against 150 random same-length
  same-session controls each: **0 of 38 cells cleared p ≤ 0.05 where 1.9 are expected**, and the
  conclusion was *do not re-run the Initial Balance in any form*. The 09:00 × 30-minute cell is
  almost certainly inside that sweep.
* `STUDY_V41_EMA_DONCHIAN`: `EMA13 > EMA48` holds on **82.6%** of Donchian breakout bars. The state
  form is very nearly the trigger restated; only the recency form binds.
* The 13×48 cross has now failed a held-back read three times (`V51`, `V52`, `V55`).

What was **not** inside any of that is the conjunction asked for here — the range breakout *with*
the EMA cross *with* a support/resistance channel gate. That is the only reason the family was
re-opened, and it is stated here so the re-opening is on the record.

## 1. Data, and the file the user re-uploaded

`us30_2_year_data.rtf` was unwrapped and checked against the copy already on disk before anything
was run with it. It is **not a new market and not a new test**: 48,937 rows over
2024-08-19 01:45 → 2026-08-26 17:30 New York, and all four OHLC series agree with
`data/US30_ISO_15m.csv` at **max |diff| 0.0000 on 100.00% of 48,937 shared stamps**. Its clock
re-derives independently — mean bar range peaks at minute-of-day 570 = **09:30 New York**. Every
p-value already spent on that block stays spent. `research/datasets.py` now records the
verification.

It also **overlaps `US30_LONG_15m`** from 2024-08 to 2025-07, so only bars from **2025-07-16** are
genuinely unseen by a US30_LONG search. That is the reservation `mr30core` already uses and it is
kept.

| block | feed | span | role |
|---|---|---|---|
| A research | `US30_LONG_15m` | 2016 → 2022-12 | the only block allowed to choose |
| B holdout | `US30_LONG_15m` | 2023-01 → 2025-07 | one read |
| C forward | `US30_ISO_15m` | 2025-07-16 → 2026-08 | different provider, one read |

`US100_LONG_15m` and `NQ_1m` are read only to ask whether anything found is a US30 fact or a market
fact. Unlike `STUDY_IB25_RETRACEMENT`, this question **is** answerable cross-market: on a
15-minute feed the window is exactly the 09:00 and 09:15 bars and 09:30 is a clean bar boundary.

## 2. The arithmetic, before any rule

| feed | median ATR | median 09:00–09:30 range | round turn | cost / 1.5N stop | break-even @1R |
|---|---|---|---|---|---|
| US30_LONG | 42.53 | 47.00 = **1.13 ATR** | 2.29 | 3.6% | 51.79% |
| US30_ISO | 63.83 | 74.70 = 1.16 ATR | 2.29 | 2.4% | 51.20% |
| US100 | 22.93 | 23.50 = 1.05 ATR | 1.215 | 3.5% | 51.77% |
| NQ | 30.90 | 32.75 = 1.05 ATR | 1.72 | 3.7% | 51.86% |

**Cost is not the objection here**, which is unusual on this branch: at a 1.5×ATR stop the round
turn is 2.4–3.7% of risk. The family does not fail on execution.

## 3. The finding that is worth keeping: the EMA cross actually binds on this trigger

![base rates](../../research/nineam/fig2_baserates.png)

Measured on the trigger's own bars, before any P&L:

| reading | US30_LONG | US30_ISO | US100 | NQ | lift vs all bars |
|---|---|---|---|---|---|
| `ema13>48` state | 0.5604 | 0.5929 | 0.5785 | 0.5772 | **1.03 – 1.14** |
| `sma13>48` state | 0.5334 | 0.5616 | 0.5365 | 0.5326 | 0.99 – 1.07 |
| `wma` / `hull` / `vwma` | 0.545 – 0.555 | 0.56 – 0.60 | — | — | 1.01 – 1.14 |
| fresh cross ≤ 5 bars | 0.1156 | 0.1232 | 0.1155 | 0.1261 | 1.20 – 1.45 |

**On a Donchian-20 breakout the same state condition passes 82.6% at lift 2.24.** On a range
breakout it passes 53–59% at lift 1.03–1.14. The mechanism is plain: a channel break *is* an
N-bar high, so a fast average is necessarily above a slow one; a 09:00-range break clears a
two-bar window from thirty minutes ago, which says nothing about a 48-bar average.

So this is the **first confirmation family measured on this branch that is not the trigger
restated** — against RSI ≥ 55 at 94.7%, Aroon osc ≥ 0 at 100.0%, MACD > 0 at 99.8–100.0%,
MFI ≥ 50 at 91.7%, `+DI > −DI` at 97.8%, `close > EMA50` at 93.7%, `EMA13>48` at 82.6%, and
VWAP-vs-stochastic at ρ +0.831. It binds. **It is also worth nothing**, which is the point: the
base-rate check screens out conditions that *cannot* help, and passing it is necessary rather than
sufficient.

The five MA types span 0.533 – 0.560 on the same signal bars, reproducing `STUDY_MA_LAG` on a new
base: **change the length, not the letter.**

## 4. Gate 1 — the bare primary

63 declared cells (4 feeds × 3 sides × 3 geometries × every block), each against a matched random
entry in the same session with the same side, geometry, exits and cost, drawn bars sorted.

**0 of 63 clear p ≤ 0.05 where 3.2 are expected by chance, and 0 of 63 deliver an effect larger
than its own minimum detectable effect.** `E[max t | pure noise]` over 63 looks is 2.364 against
the 2.802 detection needs. US30 research long reads +0.0085 %/trade at PF 1.059, p 0.705; the
holdout −0.0314 short / +0.0102 long; the forward block negative on every row.

## 5. The rule exactly as asked, plus every component removed one at a time

84 declared arms. Two nulls, because they answer different questions: a random **entry** asks
whether the *level* is worth anything; a random **gate** of the same selectivity, re-simulated end
to end, asks whether the *confirmation* is. A filter is a veto, never a subset — refusing a signal
releases the position lock and admits a later break the unfiltered run never saw.

| US30_LONG, 1.5N, no target, flat 16:00 | research | p(gate) | holdout | p(gate) |
|---|---|---|---|---|
| bare breakout, long | +0.0085 PF 1.059 | — | +0.0102 PF 1.059 | — |
| + `ema13>48` state | +0.0094 PF 1.071 | 0.477 | **−0.0201 PF 0.867** | **0.998** |
| + fresh cross ≤ 5 | +0.0160 PF 1.121 | 0.432 | +0.0336 PF 1.177 | 0.237 |
| + fresh cross ≤ 20 | +0.0021 PF 1.043 | 0.675 | +0.0393 PF 1.236 | 0.058 |

On the US30_ISO forward block the three EMA readings score −0.0015 / +0.0034 / −0.0272, p 0.38 /
0.35 / 0.76. **Nothing on US30 clears both blocks.** 8 of 63 gate tests clear p ≤ 0.05 against 3.2
expected — and five of the eight are NQ *holdout* cells that fail research and pass locked, the
wrong shape for the fifteenth time on this branch (NQ both, cross ≤ 5: research +0.0823 p 0.105 →
locked +0.2773 p 0.000).

**1 of 84 cells delivers an effect larger than its own MDE.**

## 6. The support/resistance channel as a third gate

LonesomeTheBlue's channels ported with the confirmation lag applied rather than assumed away — a
pivot at bar *j* needs bars *j−prd … j+prd*, so it is usable only from *j+prd*. The broken level
sits on a channel on 25.1% (US30_LONG) / 27.6% (US30_ISO) of signal bars.

| | US30_LONG research | US30_LONG holdout | US30_ISO forward |
|---|---|---|---|
| level **on** a channel | +0.0116 PF 1.059, p 0.247 | **−0.0500 PF 0.698, p 0.998** | **+0.0426 PF 1.316, p 0.048** |
| level **not** on a channel | +0.0060, p 0.152 | −0.0011, p 0.540 | −0.0191, p 0.738 |

Opposite signs on two blocks of the same market, with the only pass on the block read last. Not a
finding; ships default OFF.

## 7. All 16,200 parameters, read the only way this grid can be read

![marginals](../../research/nineam/fig1_marginals.png)

3 range windows × 3 buffers × 3 sides × 5 EMA readings × 6 stops × 5 targets × 4 flattens =
**16,200 declared cells a feed**. `E[max t | pure noise]` over 16,200 looks is **3.977** against the
2.802 detection needs — *the maximum of this grid could not be believed even if the whole space
were noise* — so the marginal average is the only reading taken.

![population](../../research/nineam/fig3_population.png)

| feed | research profitable | holdout profitable | corr(res, lock) | research top 1% → holdout | whole population, holdout |
|---|---|---|---|---|---|
| **US30_LONG** | 34.2% | **5.6%** | +0.46 / **+0.06** Sp | +0.0556 → **−0.0550** | −0.0380 |
| US30_ISO (forward) | **12.5%** | — | — | — | — |
| US100 | 26.7% | 47.3% | +0.70 / +0.26 | +0.1255 → +0.0812 | −0.0029 |
| NQ | 45.9% | 53.4% | +0.59 / +0.44 | +0.1793 → +0.2394 | +0.0133 |

**On US30 every setting of every axis is negative on both blocks US30 did not choose**, and only
one setting of one axis is positive on the block it did (`ema = fresh cross ≤ 20`, +0.09 bp). That
is the cleanest possible statement that the family has nothing here at any parameter.

One caveat on the US100 column: `tgt = none` reads +24.76 bp and `flat = never` +19.35 bp on its
research block, and both are dominated by a handful of multi-day holds. Those are the *no-flatten*
arms, not intraday cells, and the branch's standing finding that removing a flatten produces an
overnight strategy applies rather than being contradicted.

## 8. The marginal-consensus cell, read once, with the battery

![consensus](../../research/nineam/fig4_consensus.png)

Chosen by marginal average on the US30 **research block alone** — 09:00–09:15 range, no buffer,
both sides, fresh cross ≤ 20 bars, 1.0N stop, 3R target, flat at 16:00 — then read once on each
other block.

| block | n | %/trade | PF | win | p(entry) | p(gate) | P(mean ≤ 0) | 95% CI | MDE |
|---|---|---|---|---|---|---|---|---|---|
| US30 research | 649 | +0.0044 | 1.064 | 0.263 | 0.738 | 0.637 | 0.383 | [−0.0245, +0.0346] | 0.0419 |
| US30 holdout | 319 | −0.0252 | 0.792 | 0.241 | 0.995 | 0.735 | 0.921 | [−0.0604, +0.0108] | 0.0482 |
| US30 forward | 138 | +0.0054 | 1.044 | 0.290 | 0.578 | 0.207 | 0.424 | [−0.0377, +0.0501] | 0.0632 |

Four Monte Carlos, kept apart:

* **Day-block bootstrap (the edge)** — no block excludes zero; the holdout excludes zero on the
  *negative* side at P(mean ≤ 0) 0.921.
* **Permutation (the path)** — realised drawdown at the 0.59 / 0.61 / 0.27 percentile of reshuffles
  of its own trades; **MC p99 drawdown 1.35× – 2.12× realised**, which is the sizing number.
* **Execution** — round turn drawn U(0.5×, 2×) inside the walk: P(total ≤ 0) 0.395 / 1.000 / 0.000.
* **Price jitter** — OHLC jittered with the ATR, the range and both MAs recomputed: sign kept
  1.000 everywhere.

The last two are nearly free whenever the stop is wide against the round turn, and here it is. They
say the *implementation* is not fragile; they say nothing about edge, and a tight band there must
not be read as evidence.

**Counted looks: 64,947.** `E[max t | pure noise]` = **4.296**. No deflated Sharpe is quoted
because there is no surviving candidate to deflate.

## 9. The script

`pine/nineam/NINE_AM_RANGE_BREAKOUT_strategy.pine`, lint-clean, all three components as inputs with
the EMA gate defaulting to Off and the S/R gate to Off, every measured number in the header, no
edge claimed.

Mechanics that were corrected rather than hoped:

* Every setting that is a **reach in time** is declared in MINUTES and converted with
  `timeframe.in_seconds()`, so the same numbers mean the same thing on any chart (`STUDY_V57`).
* The bracket is placed **with** the entry and priced fill-relative in ticks, so the fill bar is
  protected — `strategy.exit` on a later bar leaves the entry bar naked, and a bracket reading
  `strategy.position_avg_price` cannot be armed on the fill bar at all (`STUDY_SCALP89`).
* A break refused by a gate still consumes the session, in both the script and the research event
  stream, so the two take the first break or none.
* Every block writing `var` state is guarded by `barstate.isconfirmed`.

Parity, `research/nineam/na_parity.py`, six cells on the two US30 feeds:

| | trade count | same exit bar | per-trade correlation | gap |
|---|---|---|---|---|
| US30_LONG, three configs | **1.000** | 0.973 – 0.991 | 0.996 – 0.998 | +0.18 / −0.22 / +0.24 pts |
| US30_ISO, three configs | **1.000** | 0.986 – 1.000 | 0.989 – 1.000 | −1.04 / −2.21 / +0.00 pts |

The gap is quoted **per trade, not as a share of the total**, because this family's total is near
zero and a ratio with a collapsing denominator is the artifact `STUDY_SWEEP_110K` recorded.

## 10. What would change the verdict

Not more parameters — the grid's own noise floor already exceeds the detection threshold by 1.4×,
so a wider search makes the bar higher, not the answer better. What would move it is **more
events**: US30 supplies ~1,760 breakouts across nine years at this window, and the MDE at that
count is 0.036 %/trade against a delivered 0.004. A second decade of US30, or 1-minute US30 bars
that would let the window be resolved exactly and the intrabar convention be settled, are the only
two levers that change the arithmetic.

---

### Files
`research/nineam/na_core.py` · `run_n1.py` (arithmetic, base rates, Gate 1) · `run_n2.py` (the
16,200-cell grid by marginal average) · `run_n3.py` (the rule as asked, both nulls, drop-one, the
S/R gate) · `run_n4.py` (the consensus cell, four Monte Carlos, deflation) · `na_parity.py` ·
`plot_na.py` · `pine/nineam/NINE_AM_RANGE_BREAKOUT_strategy.pine`
