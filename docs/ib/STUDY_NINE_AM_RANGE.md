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

## 11. Fixed POINT barriers — the option, and what it measures

Requested directly: a TP and an SL selectable as 100 points. Both are now inputs
(`Stop mode = Points`, `Target mode = Points`), and the arithmetic was run before the option was
shipped, because a point distance is the one parameterisation that is **not the same geometry
twice**.

| 100 points is… | US30_LONG | US30_ISO | NQ | US100 |
|---|---|---|---|---|
| × median in-window ATR | **2.35** | 1.57 | 3.24 | **4.36** |
| round turn / risk | 2.29% | 2.29% | 1.72% | 1.22% |
| driftless break-even @1:1 | 51.1% | 51.1% | 50.9% | 50.6% |

On US30 alone the same 100 points was 4.23 ATR in 2016 and 1.10 in 2025 (`STUDY_DL50`), so a points
grid confounds geometry with market *and* with era. The script's panel therefore prints the chosen
distance in both units live.

**The 100 / 100 cell, one read per block:**

| feed | block | side | n | %/trade | PF | win | break-even | p(entry) | P(mean≤0) | MDE |
|---|---|---|---|---|---|---|---|---|---|---|
| US30_LONG | research | long | 1378 | +0.0031 | 1.022 | 0.517 | 0.511 | 0.728 | 0.364 | 0.0247 |
| US30_LONG | holdout | long | 585 | **−0.0164** | 0.872 | 0.475 | 0.511 | **1.000** | 0.933 | 0.0298 |
| US30_ISO | forward | long | 263 | −0.0048 | 0.954 | 0.502 | 0.511 | 0.480 | 0.663 | 0.0351 |
| US100 | research | both | 1710 | +0.0407 | 1.107 | 0.535 | 0.506 | **0.025** | 0.012 | 0.0483 |
| US100 | holdout | both | 635 | −0.0089 | 0.956 | 0.501 | 0.506 | 0.983 | 0.690 | 0.0543 |

**The win rate is its own break-even**, within half a point on every US30 row — the fourth family
here where the barriers are hit by noise. Across 14 cells, **1 clears p ≤ 0.05 where 0.7 are
expected by chance, and 0 of 14 exceed their own MDE**. The one pass (US100 research) is the block
that would choose, and its holdout reads 0.983.

**The 75-cell declared points grid on US30 research** (5 stops × 5 targets × 3 sides): 54.7%
profitable, 3 of 75 outside their own MDE, best |t| **3.635** against an `E[max t | pure noise]` of
**2.428** for a search that size — so the top row of this grid is readable only as a marginal.

| target | none | 200 pt | 150 pt | 100 pt | 50 pt |
|---|---|---|---|---|---|
| marginal, bp/trade | **+0.87** | +0.80 | +0.43 | −0.44 | **−1.07** |

Monotone, with the tightest target the single worst choice in the space — **no take profit wins for
the 26th time here**, and this time the points parameterisation says it independently. The stop
marginal runs the other way (50 pt −0.26 → 200 pt +0.42), reproducing the monotone-toward-wider
result for the ninth family. The intrabar tie-break decides nothing at these widths: the ambiguous
share is 1.33% at a 50-point stop and 0.01% at 200.

Parity on the new modes: **10 of 10 cells at trade count 1.000**, same exit bar 0.962–1.000,
per-trade correlation 0.996–1.000, gap **−0.14 to +0.00 points a trade** — conservative on every
points cell.

**Defaults are unchanged** (ATR stop, no target). The points values are pre-filled at 100 and the
modes have to be switched deliberately, because on this evidence 100/100 is worse than the
researched geometry on every US30 block.

## 12. The range is the 09:00 BAR, and the choice against the half hour is free

Clarified by the user after the first pass: *"it should be 9am high and low"* — the 09:00 candle,
not the 09:00–09:30 window. That is now the default (`Range end = 555`, i.e. 09:00–09:15 declared in
minutes so it is the same reach on any chart), with the breakout still armed only at 09:30.

The research event stream had always kept those two apart, so this is a re-read of a cell the
16,200-grid already contained rather than a new search. Both readings, paired on identical
feed / block / side / geometry:

| | 09:00 bar | half hour |
|---|---|---|
| median range width, ATR | **1.03 – 1.13** | 1.50 – 1.87 |
| paired cells won | **14 of 28** | 14 of 28 |
| mean delta | **+0.0014 %/trade** | — |
| mean MDE | 0.0593 | — |

**Exactly chance, at a delta 42× smaller than the sample can resolve.** The choice is free on
performance. What it does change is the *level*: the one-bar range is about a third narrower, so the
breakout sits nearer and fires slightly more often on the long side (US30 research 1,418 long
signals against 1,378).

On the new default, US30, 1.5×ATR stop, no target, flat 16:00, against a matched random entry:

| block | side | n | %/trade | PF | p |
|---|---|---|---|---|---|
| research | long | 1418 | +0.0145 | 1.087 | 0.338 |
| holdout | long | 600 | +0.0098 | 1.053 | 0.890 |
| forward (US30_ISO) | long | 268 | +0.0087 | 1.043 | 0.177 |
| research | both | 1734 | +0.0067 | 1.047 | 0.367 |
| holdout | both | 733 | +0.0009 | 1.006 | 0.983 |
| forward (US30_ISO) | both | 315 | +0.0080 | 1.037 | 0.325 |

Positive on all three US30 blocks and on both sides — and **not one of them is a detectable
effect**. Over the 56 declared window × geometry × block cells, 3 clear their control at p ≤ 0.05
where 2.8 are expected by chance, **0 of 56 exceed their own MDE**, and `E[max t | pure noise]` over
56 looks is 2.319 against the 2.802 detection needs.

Parity after the change: **7 of 7 cells at trade count 1.000**, same exit bar 0.962–0.991, per-trade
correlation 0.996–0.998, gap −0.20 to +0.24 points a trade.

## 13. The auto breakeven — measured, and it subtracts

Asked for as a 50-point option. The branch had measured this policy once before and it was the only
exit arm that came out below its own baseline (`TEAM_EXIT_PF`: the channel exit a wash, the trail's
profit-factor gain shared with its own coin-flip twin, breakeven-after-1R the lone subtractor), so
it was measured rather than wired up.

The grid was declared before anything was read: `be` ∈ {off, 25, 50, 75, 100, 150} points ×
{long, both} × {1.5N no target, 100pt/100pt} × {US30L research, US30L holdout, US30_ISO forward}.

**72 nominal cells and 60 effective.** At the 100-point target a breakeven armed at 100 or 150
points can never fire — the target resolves first on the same bar — and those twelve rungs reproduce
their own OFF twin *to the cent and to the exit bar* (checked, not asserted: 0 of 12 differ). An
axis that changes nothing is excluded from the count, or the multiplicity corrects for tests never
run. `E[max t | pure noise]` over 60 looks is **2.345**, against the 2.802 detection needs.

Paired against each cell's own OFF twin, marginal average over the whole grid:

| arms at | Δ %/trade | Δ excess over twin | Δ stop share | Δ flatten share | cells won |
|---|---|---|---|---|---|
| 25 pt | **+0.0036** | +0.0006 | +0.222 | −0.141 | 9 / 12 |
| 50 pt (the ask) | **−0.0008** | −0.0013 | +0.145 | −0.095 | 7 / 12 |
| 75 pt | −0.0034 | −0.0028 | +0.093 | −0.069 | 1 / 12 |
| 100 pt | −0.0034 | −0.0028 | +0.048 | −0.048 | 0 / 12 |
| 150 pt | −0.0038 | −0.0031 | +0.027 | −0.028 | 2 / 12 |

**A breakeven beats its own OFF twin in 19 of 60 paired cells — 32%, where chance is 50%** — and the
ladder is monotone against the arming distance once past 25 points. The mechanism is in the exit
mix and is the same in every cell: the stop share rises and the flatten share falls by almost
exactly as much, so the ratchet arms on a favourable excursion and is then taken out on the pullback
before the 16:00 clock would have closed the trade in profit. On US30 research at 1.5N the long cell
goes +0.0145 → +0.0113 %/trade and its stop share 63.3% → 75.7%.

Two qualifications keep this honest. **Every paired delta is inside its own MDE (0 of 60 outside)**,
so this is a direction with a consistent sign across three blocks and two geometries, not a resolved
effect. And **0 of 72 cells clear a matched random entry at p ≤ 0.05** where 3.6 are expected — the
breakeven changes neither the rule's level nor its excess over its own null enough to matter.

### Securing points: the threshold is the round turn, not zero

The user's observation was exact — a true breakeven stop shows up as a *losing* trade, because an
exit at the fill books minus the commission and slippage. The fix is to move the stop slightly
*beyond* the fill, and the distance it has to clear is the round turn: on US30 that is 2.29 points
in the research accounting, so a 5-point secure books **+2.71** and is a win.

That makes `Secure, POINTS` (default **5**) the second breakeven input. Measured at breakeven = 50,
1.5N, across US30 research, the US30 holdout and the different-provider forward block:

| secured | Δ %/trade vs 0 | Δ win rate | Δ trade count | cells won |
|---|---|---|---|---|
| 5 pt | −0.0008 | **+0.410** | +0.8 | 2 / 6 |
| 10 pt | +0.0006 | +0.410 | +1.5 | 4 / 6 |
| 25 pt | +0.0059 | +0.411 | +1.7 | 5 / 6 |

**Read the trade count before the win rate.** It moves by 0 to 5 trades out of 268–1,799, so the
secured level is overwhelmingly *relabelling exits it did not move*. On US30 research long the win
rate goes 0.2207 → 0.5275 and the money goes +0.011307 → +0.009270 %/trade; on the forward block
0.1493 → 0.6493 and +0.0098 → +0.0110. Identical trades, +41 points of win rate.

The ladder does rise with the secured distance, and that is the warning rather than the
recommendation: once the level is far enough from the fill it has stopped being a breakeven and
started being a small take profit, and no take profit has beaten every target tested 26 times on
this branch. **5 is the asked-for setting and the honest one; 25 is a target wearing a stop's name.**

The panel computes the round turn **live** from the run's own closed trades —
`(gross − net) / trades / point value + 2 × tick`, because slippage is charged in ticks on both
sides and never appears in the commission figure — and prints the secured distance beside it with a
CLEARS / BELOW verdict, so the arithmetic is visible on whatever symbol the script is loaded on
rather than assumed from US30.

### How it ships

Four inputs — `Auto breakeven` (**default Off**), the arming distance (50), `Secure, POINTS` (5),
and the stop mode they sit under — with each ladder's own numbers in the tooltips. In the script the
ratchet is re-issued as an absolute stop priced from `strategy.position_avg_price` once the position
exists, which is one bar after the entry order is written and exactly when the research walker arms;
the moved stop then binds from the bar after that, because within one bar OHLC cannot order the
excursion against the pullback.

Parity with the breakeven live, including the shipped 50/+5 default: **12 of 12 cells at trade
count 1.000**, same exit bar 0.979–0.997 on the breakeven configs, per-trade correlation
0.995–1.000, gap −0.39 to +0.07 points a trade. The tick rounding of the moved stop is the only
place the two order models can disagree, and it does not move the trade count anywhere.

## 14. The 08:00 hourly candle as a direction gate — it binds, and it does not pay

Asked for directly: if the 08:00–09:00 New York hourly candle is bearish, take only the bearish
break. Unusually for a direction filter this one is *causal by construction* — the hour completes
at 09:00, before the range starts and ninety minutes before the 09:30 arm — so it can be tested
without an argument about leakage. It was audited anyway: **0 mismatches of 40 probes** on both
feeds, rebuilding the hour from history that ends at the signal bar.

### It is not the trigger restated — the second condition here to pass that check

The failure mode that has killed RSI (94.7%), Aroon (100.0%), MACD (99.8%), MFI (91.7%), +DI
(97.8%), `close>EMA50` (93.7%) and `EMA13>48` on a Donchian break (82.6%) is a confirmation that
the trigger already implies. The 08:00 hour does not:

| reading | admits of long breaks | admits of short breaks |
|---|---|---|
| direction (close vs open) | 0.4990 / 0.5430 | 0.4899 / 0.4530 |
| body ≥ 0.25 ATR | 0.4039 / 0.4242 | 0.4006 / 0.3761 |
| close position in the hour's range | 0.4970 / 0.5143 | 0.4955 / 0.4850 |

(US30_LONG / US30_ISO.) **Every cell sits between 0.376 and 0.543** — the hour is a genuinely
independent reading of direction, which is exactly why it was worth measuring.

### And then it fails every null

36 declared cells: 3 readings × {ALIGNED, COUNTER} × two geometries × three blocks, each scored
against a **random gate of the same selectivity re-simulated end to end** (a filter is a veto, not
a subset — refusing a signal releases the position lock and admits a later break). COUNTER is in
the grid because a proposed condition's sign has inverted seven times on this branch.

| reading | polarity | Δ vs no filter | beats baseline | clears its null |
|---|---|---|---|---|
| direction | **ALIGNED** (the ask) | **−0.0006** | 3/6 | **0/6** |
| direction | COUNTER | −0.0040 | 3/6 | 0/6 |
| body ≥ 0.25N | ALIGNED | −0.0062 | 0/6 | 0/6 |
| body ≥ 0.25N | COUNTER | −0.0017 | 3/6 | 0/6 |
| close pos | ALIGNED | −0.0060 | 0/6 | 0/6 |
| close pos | COUNTER | +0.0016 | 3/6 | 0/6 |

**0 of 36 cells clear p ≤ 0.05 where 1.8 are expected by chance. 0 of 36 exceed their own MDE. The
gate beats the ungated rule in 12 of 36 cells, where chance is 50%.** `E[max t | pure noise]` over
36 looks is 2.148 against the 2.802 detection needs.

By block, ALIGNED is negative on all three (−0.0041 research, −0.0045 holdout, −0.0042 forward) —
consistent, small, and in the wrong direction. COUNTER is positive on research only (+0.0031) and
negative on both blocks it did not choose, which is the shape this file has now recorded fourteen
times. On the 1.5N geometry the research block flatters COUNTER hard (+0.0171 to +0.0242 against a
baseline +0.0067) and then reads −0.0099 to −0.0168 on the holdout; that inversion is the entire
reason the mirror was declared in advance rather than discovered afterwards.

### How it ships

`08:00 hour gates the side` — **Off** / Align with the hour / Counter to the hour — plus the
reading, a body threshold and the hour's start and end **declared in minutes**, so the same numbers
mean the same thing on any chart. The candle is accumulated from the chart's own bars and frozen at
09:00 rather than pulled with `request.security(…, "60")`, because a 60-minute security bar is the
*exchange's* hour and need not begin at 08:00 New York — the same reason an RTH session high has to
be accumulated here rather than requested. The hour is shaded teal or maroon on the chart when the
gate is on, and the panel prints `bearish -> shorts only` so the state is never in doubt.

Parity with the gate live: **15 of 15 configs at trade count 1.000**, same exit bar 0.977–0.996,
per-trade correlation 0.995–0.998, gap −0.84 to +0.40 points a trade.

## 15. The MA 200 — a cross of ANY of the provided EMAs, or of ALL of them

The ask: add the 200 as a third average and require the shorter ones to have crossed it on the
side the break points. This is a third object and not a restatement of two things already
measured here — it is not the 13×48 cross (§3), which compares two fast averages with each
other, and it is not `close > MA200`, which `STUDY_V40` found is priced by its DISTANCE and
`STUDY_V51` found works as a FLOOR and not as support. Both of those are price against the
average; this is the shorter averages against it.

**Declared grid**, nothing outside it read: 4 readings (`any`/`all` × state/fresh-cross) × 2
polarities (ALIGNED, the literal ask / COUNTER, the mirror) × 2 geometries (1.5×ATR no target /
100pt–100pt) × 3 blocks (US30_LONG research, US30_LONG holdout, US30_ISO forward — a different
provider) = **48 cells**. `E[max t | pure noise]` over 48 looks is **2.261** against the 2.802
detection needs, so the ceiling was known before the table was read. COUNTER is declared in front
because this branch has inverted a proposed condition's sign eight times.

### ANY and ALL are the same condition unless a split reading resolves

Read as a single +1/−1/0 direction label the two modes are **identical to four decimals**
(0.5389 / 0.3810 / 0.0801 on US30 for both) — because "at least one above with none below" *is*
"all above". The mode axis only binds if a split reading (13 above the 200, 48 below) is allowed
to confirm *both* sides rather than abstain, which is what `ma200_ok` returns: two masks, not one
label. Under `any` a split day simply vetoes nothing. Without that the grid would have counted
twelve tests that were never run — `run_n7`'s inert-rung accounting, reached from a different
direction.

### The base rate is the finding: lift exactly 1.00

| reading | admits (long breaks) | on all bars | lift |
| --- | --- | --- | --- |
| `close > MA200` (reference) | 0.6313 | 0.5798 | **1.089** |
| any STATE | 0.6155 | 0.6190 | **0.994** |
| all STATE | 0.5411 | 0.5389 | **1.004** |
| any CROSS ≤ 5 bars | 0.0515 | 0.0439 | 1.173 |
| all CROSS ≤ 5 bars | 0.0035 | 0.0027 | 1.296 |

Across every state cell on both feeds and both sides the lift is **0.990 to 1.007**. A
200-period average is so slow that a 15-minute range break carries *no information whatever*
about where the 13 and the 48 sit relative to it — so the gate is a coin flip applied to the
signal set. Price itself does lean (1.089–1.152), which is the contrast that makes the point: the
information is in where price is, not in where the slow averages are.

This is the opposite failure from the eight confirmation families that died on this check by
passing 82–100% of the trigger's own bars. Those were the trigger restated. This one is
independent to the point of carrying nothing.

### Nothing clears, and the direction asked for is the negative one

Scored as a VETO against a random gate of the same selectivity, re-simulated end to end:

| reading × polarity | %/trade | Δ vs no filter | beats base | clears p≤0.05 |
| --- | --- | --- | --- | --- |
| any STATE **ALIGNED** | −0.0189 | **−0.0164** | **0/6** | 0/6 |
| all STATE **ALIGNED** | −0.0199 | **−0.0173** | **0/6** | 0/6 |
| any CROSS ALIGNED | −0.0007 | +0.0018 | 3/6 | 0/6 |
| any STATE COUNTER | +0.0085 | +0.0110 | 4/6 | 2/6 |
| all STATE COUNTER | +0.0113 | +0.0139 | 5/6 | 1/6 |
| any CROSS COUNTER | −0.0181 | −0.0156 | 3/6 | 0/6 |

- **3 of 36 scorable cells clear p≤0.05 where 1.8 are expected by chance**, and all three are
  COUNTER.
- **0 of 36 exceed their own minimum detectable effect.**
- The gate beats the ungated rule in **15 of 36** cells where chance is 50%.
- **12 of 48 declared cells are unscorable** (under 25 trades): the `all CROSS` reading admits
  0.0–1.1% of breaks. That is a fact about the condition, not a reason to loosen it afterwards.
- By block, COUNTER reads +0.0063 research / +0.0107 holdout / **−0.0077 on the reserved forward
  feed** — so the one polarity that scores is the one that dies on the block nobody chose.

Ships as four options on the existing MA-confirmation input, **default OFF**, with the base-rate
table and the 0/6 ALIGNED record in the tooltip. Parity: **20 of 20 configurations at trade count
1.000**, same exit bar 0.974–1.000, correlation 0.993–1.000.

---

## 16. Trend lines through two confirmed pivots, as a breakout

The ask: draw the trend lines and break them. Three ways that can enter the rule, all declared —
**GATE** (keep the range break, additionally require price to have cleared the line on the side it
is breaking), **LEVEL** (the line *is* the breakout level, the range unused), **EITHER** (the level
is whichever of the two is nearer, so the session fires on the first break of either).

Construction: the resistance line runs through the last **two confirmed** pivot highs and is
extended to the current bar; the support line through the last two pivot lows. A pivot at bar *j*
needs bars *j−prd..j+prd*, so it is knowable at *j+prd* and never at *j* — a line anchored at the
pivot itself back-tests beautifully and cannot be traded, which is exactly the leak
`STUDY_DIVERGENCE_CONFIRM` caught reading +37 full against +999 truncated. At three points a third,
earlier pivot must lie within 0.25 ATR of the same line — a pivot the line was *not* fitted to,
which is the only reading of "three points" that is not automatically true.

**Declared grid**: 4 modes × 2/3 points × 2 geometries (1.5 ATR no target / 100pt–100pt) × 3 blocks
(US30_LONG research, US30_LONG holdout, US30_ISO forward — a different provider) = **48 cells**.
`E[max t | pure noise]` over 48 looks is **2.261** against the 2.802 detection needs. The pivot
period is fixed at 10 and never swept.

### Audit clean, and the base-rate check passes

Levels rebuilt from history ending at the signal bar: **0 mismatches of 48 probes on both feeds**.

| points | admits (long breaks) | on all bars | lift | line exists | median distance |
| --- | --- | --- | --- | --- | --- |
| 2 | 0.3756 | 0.2854 | **1.316** | 1.000 | 2.39 ATR |
| 3 | 0.0793 | 0.0376 | **2.109** | 0.233 | 2.13 ATR |

0 of 8 cells admit over 95%, and the lift runs 1.30–2.71 — so the trend line is the **third**
condition in this study to be a genuinely separate reading rather than the trigger restated, after
the EMA 13/48 cross (53–59%) and the 08:00 hourly candle (37.6–54.3%). The MA200 cross failed the
same check from the other end, at lift exactly 1.00.

### And it clears nothing

Each GATE reading against a random gate of the same selectivity; each LEVEL/EITHER reading against
a **matched random entry**, because those two change which bars the rule fires on and a selectivity
control is the wrong null for them. Both re-simulated end to end.

| mode | points | %/trade | Δ vs no filter | beats base | clears p≤0.05 |
| --- | --- | --- | --- | --- | --- |
| gate ALIGNED | 2 | +0.0008 | **+0.0034** | 4/6 | 1/6 |
| gate ALIGNED | 3 | +0.0094 | **+0.0120** | 4/6 | 0/6 |
| gate COUNTER | 2 | −0.0080 | −0.0055 | 3/6 | 1/6 |
| level | 2 | −0.0032 | −0.0006 | 4/6 | 0/6 |
| level | 3 | +0.0125 | +0.0151 | 3/6 | 0/6 |
| either | 2 | −0.0020 | +0.0005 | 3/6 | 0/6 |

- **2 of 48 cells clear their own null at p≤0.05 where 2.4 are expected by chance.**
- **1 of 48 exceeds its own minimum detectable effect.**
- A reading beats the ungated rule in **27 of 48** cells where chance is 50%.
- **LEVEL is the worst of the four**: on US30 research it takes *more* trades than the range
  (1,863 against 1,734) and loses to a random entry with the same geometry at **p 1.000**. Using
  the line as the level is worse than entering at an arbitrary bar in the same session.
- GATE has the best marginal and **inverts by block** — +0.0186 research, **−0.0171 holdout**,
  +0.0216 forward.
- Three points reads the largest number in the table and is the least resolvable: it cuts the
  sample to ~120 trades a block against an MDE of 0.12–0.14.

Ships as a fourth gate, **default OFF**, with the base-rate table and the 1-of-48 record in the
tooltip. The lines plot when the mode is on. Parity: **25 of 25 configurations at trade count
1.000**, same exit bar 0.974–1.000, correlation 0.995–1.000.

---

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
`run_n5.py` (the fixed-points parameterisation: the ATR conversion table first, a 75-cell
declared grid by marginal average, then the 100/100 cell read once per block against a matched
random entry) · `run_n6.py` (the 09:00 bar against the half hour, paired) · `run_n7.py` (the auto
breakeven ladder: the inert-axis accounting and the noise floor before the table, and the paired
comparison against each cell's own OFF twin) · `run_n8.py` (the secured-points rung, with the trade
count printed beside the win rate so a relabelling cannot be read as an improvement) · `run_n9.py`
(the 08:00 hourly candle as a direction gate: truncation audit, then the base rate on the trigger's
own bars, then both polarities against a same-selectivity random gate re-simulated) · `run_n10.py`
(the MA 200 as a third average: the ANY-equals-ALL degeneracy proved before the grid, the audit,
the lift-1.00 base rate, then both polarities against a same-selectivity random gate) ·
`run_n11.py` (trend lines through two confirmed pivots: the audit, the base rate on the
trigger's own bars, then GATE against a same-selectivity random gate and LEVEL/EITHER against a
matched random entry, because the last two change the event stream) ·
`run_n12.py` (the opposite-cross exit: the binding rate and the trade count in both arms printed
before any verdict, each reading paired against its own OFF twin on identical entry bars) ·
`run_n13.py` (its placebo -- the same number of early exits at RANDOM bars, 100 seeds a cell,
which is what separates closing AT THE CROSS from closing early at that RATE) ·
`run_n14.py` (the ATR period as a ladder paired against its own ATR(14) twin, and the ATR target
against no target -- with the ATR-target/R-target identity asserted on exit bars before either) · `plot_na.py` ·
`pine/nineam/NINE_AM_RANGE_BREAKOUT_strategy.pine`

## 17. Close the position on an opposite EMA cross

Asked for as an exit rule. Measured rather than wired up, because this branch has now measured
three exit policies on this family and none of them earned a place: `TEAM_EXIT_PF` found the 1.0
ATR trail raising its own coin flip's profit factor by as much as its own, the channel exit a wash
and breakeven-after-1R the one arm below its baseline; `run_n7` found the auto breakeven beating
its own OFF twin in 19 of 60 scorable cells; `STUDY_V63` found removing a chandelier trail worth
3.6x the per-trade result. The prior on closing a position early is poor and the correct null is
not zero.

**The declared grid.** off / fresh cross / opposite state x pair 13/48 and 21/55 x long and both
x two geometries (1.5xATR stop no target, 100pt stop 100pt target) x three blocks (US30_LONG
research and holdout, US30_ISO forward, a different provider) = **72 NOMINAL cells and 48
SCORABLE**. The OFF arm never reads the pair, so its two pair rows are one cell and not two;
counting them twice would correct the multiplicity for 24 tests never run. `E[max t | pure noise]`
over 48 looks is **2.261** against the 2.802 detection needs.

**The binding rate first, because an exit that never fires is an inert switch.** The two readings
are different rules and were kept apart for exactly this reason:

| reading | binds | median hold | mechanism |
| --- | --- | --- | --- |
| fresh opposite cross | **4.5-7.5%** of trades | 10.1 bars (off: 10.9) | a 13/48 flip inside a 2.5-hour hold is rare |
| opposite state | **35%** | **6.5 bars** | fires on the first bar the state is against the fill |

**The result.** The policy beats its own OFF twin in **15 of 48 cells -- 31%, where chance is
50%** -- and **0 of 48 paired deltas exceed their own minimum detectable effect**. Both marginal
averages are negative (fresh cross -0.0010 %/trade, opposite state -0.0044) and both pairs agree in
sign (13/48 -0.0033, 21/55 -0.0022), so it is a consistent direction rather than a spike. By block:
research -0.0034, holdout -0.0055, forward +0.0006.

**The mechanism is the win-rate-for-money trade, and it is visible in one row.** The opposite-state
reading takes US30 research long from **+0.0145 %/trade at a 32.6% win rate to +0.0076 at 38.9%**,
and the holdout from **+0.0098 PF 1.053 to -0.0101 PF 0.907 at a 34.7% win rate**. It converts a
payoff book into a hit-rate book and pays for the conversion. The stop share rises from 0.633 to
0.424 and the flatten share falls 0.364 to 0.207 -- the cross closes, at a worse price, trades the
clock would have closed in profit.

**AND THE PLACEBO IS THE FINDING.** A before/after cannot separate "closing at the cross helps"
from "closing early at that RATE helps", and the second needs no forecasting at all -- a coin flip
closing as often would also cut the hold, also raise the win rate and also change the trade count
by freeing the position lock. So every cell was re-run against an exit array carrying the **same
number of exit bars with the same signed mix, placed at random bars**, 100 seeds a cell
(`run_n13.py`). The real delta sits at a mean percentile of **0.38** (cross) and **0.57** (state)
of its own null; **the placebo does BETTER in 12 of 24 cells**; and 3 of 24 clear the 95th
percentile where 1.2 are expected by chance. The moving average is not doing the work. This is the
random-delay placebo of the execution-overlay literature applied to an exit rather than an entry.

One row is worth reading carefully because it is the trap: on research long at 1.5N the state
reading beats its placebo at percentile **1.00** -- and its delta is still **-0.0069**. It beats a
null that loses more. `STUDY_IB_US30_OPTUNA`'s sentence from the other side: a rule that beats a
losing null is still a losing rule.

**Causality.** The cross is read at a bar's CLOSE and the exit FILLS AT THE NEXT BAR'S OPEN,
because `strategy.close()` cannot sell the close of the bar that triggers it -- `STUDY_V16`'s
`flat_open` lesson, where the engine was changed to match the script rather than the other way
round. The stop and the target are intrabar and resolve first within the same bar.

Ships as an input on the existing MA pair, **DEFAULT OFF**, with the binding rate and the placebo
record in the tooltip. Parity: **30 of 30 configs at trade count 1.000**, same exit bar
0.986-1.000, correlation 0.989-1.000, and the gap is negative on every cross-exit config
(-1.06 to -2.19 points a trade) -- the script reads worse than the engine, which is the
conservative direction.

## 18. Three gates removed, the ATR period made selectable, and an ATR take profit

Asked to delete the 08:00 hourly-candle direction gate, the LonesomeTheBlue support/resistance
channels and the trend lines, and to add one ATR period governing every ATR setting plus an ATR
take profit.

**The removals cost nothing, because all three had already been measured to nothing** -- the 08:00
hour cleared 0 of 36 cells (section 14), the S/R channel read opposite signs on two blocks of one
market (section 2), and the trend lines managed 1 of 48 outside its own MDE with the literal
LEVEL reading losing to a random entry at p 1.000 (section 16). The measurements stay in this
document and in `run_n9.py` / `run_n11.py`; what goes is three switches on a chart, which is three
fewer ways to fit it.

### The ATR target is not a new axis under an ATR stop, and that is asserted rather than reasoned

`target = k x ATR` and `target = r x stop` are the same level when `k = r x stopAtr`. Checked on
2,295-2,580 trades at 1.5N and 2.5N across three R multiples: **identical trade counts, identical
exit bars, max |dpts| 0.000e+00** (one cell at 3.6e-12, float noise). It separates only under a
POINTS or range stop, where the risk is not an ATR multiple -- there the two agree on **66-73%** of
exit bars and the trade counts differ. So the axis is real, and only outside the default geometry.

### The ATR period ladder: 21 of 60 rungs beat ATR(14), where chance is 50%

Every figure in this study was measured at `ema(tr, 14)`, so the period is a genuinely new axis.
Declared rungs 7 / 10 / 14 / 21 / 30 / 50 x long and both x two geometries x three blocks = 72
cells, 60 of them paired against their own ATR(14) twin. `E[max t | pure noise]` over 60 looks is
**2.345** against the 2.802 detection needs.

| ATR period | paired Δ %/trade | Δ trades | beats ATR(14) |
| --- | --- | --- | --- |
| 7 | −0.0027 | −15.1 | 25% |
| 10 | −0.0019 | −6.4 | 25% |
| 21 | **+0.0004** | +4.4 | 58% |
| 30 | −0.0002 | +9.2 | 42% |
| 50 | −0.0021 | +12.9 | 25% |

**0 of 60 paired deltas exceed their own MDE**, and the two rungs either side of 14 are the only
non-negative ones -- a smooth hump centred on the incumbent, which is what an axis with no
information in it looks like when the default happens to sit in the middle. 14 stays the default.

**What moves with it is the TRADE COUNT, and not for the obvious reason.** The count rises
monotonically with the period (−15 at 7, +13 at 50) even though the break level is unchanged at the
default zero buffer -- so the events are identical and the difference is downstream: a wider stop
holds positions longer and the one-position lock then refuses later breaks. `STUDY_V56`'s mechanism
again, reached from the stop rather than the exit.

### The ATR take profit loses monotonically -- the 27th confirmation

Paired against NO TARGET at the shipped 1.5N stop, over three blocks and both sides:

| target | R equivalent | paired Δ %/trade | target-hit rate | beats no target |
| --- | --- | --- | --- | --- |
| 1.5 ATR | 1R | **−0.0167** | 48.2% | 0 of 6 |
| 2.25 ATR | 1.5R | −0.0115 | 38.2% | 0 of 6 |
| 3.0 ATR | 2R | −0.0070 | 29.5% | 2 of 6 |
| 4.5 ATR | 3R | −0.0042 | 16.5% | 1 of 6 |
| 6.0 ATR | 4R | +0.0020 | **9.4%** | 5 of 6 |

Monotone, with the tightest target the worst choice in the space. **A target beats no target in 8
of 30 cells where chance is 50%**, and 0 of 30 paired deltas exceed their own MDE. The one
non-negative rung reaches its target on 9.4% of trades, so it is barely a target at all -- setting
6 ATR and setting NONE are nearly the same strategy, which is `STUDY_INTRADAY_HEAT`'s finding on a
different base. Ships with `tgtMode` default **None**.

Parity after all of it: **28 of 28 configs at trade count 1.000**, same exit bar 0.972-1.000,
correlation 0.989-1.000, with the six new ATR-period and ATR-target configs reading 1.000 on the
count and −0.33 to +0.02 points a trade on the gap.
