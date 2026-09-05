# V59 — EMA 16/64 with a four-hour ceiling, 243,000 configurations, three markets

**The brief.** A trend-following strategy holding no longer than four hours, on the 16/64 EMA
cross, with ADX and ATR, searched over a hundred thousand combinations for the most robust
version.

**The answer.** 243,000 configurations per market on nine years of US30 and US100, then one read
on NQ, which had no part in the search. **Nothing survives.** The rule as briefed loses on both
search markets in both blocks and is flat on NQ; the best-supported configuration earns +0.057
ATR/trade on NQ where a random entry with the same management earns +0.041.

---

## 1. What was swept

`research/v59/v59core.py`. A trade's outcome depends only on its **signal bar** and its
**geometry**, so the price is walked once per (signal bar, geometry) and every filtered
configuration becomes an array lookup plus a position-lock pass. 243,000 configurations per
market cost one walk of ten seconds.

| axis | settings |
| --- | --- |
| entry mechanic | the cross bar; the first close beyond the cross bar's extreme; the first pullback to EMA 16 |
| side | long, short, both |
| stop | 0.5, 1.0, 1.5, 2.0, 2.5, 3.0 × ATR(14) |
| target | 1.0, 1.5, 2.0, 3.0 R, or **none** |
| maximum hold | 1h, 2h, 3h, **4h** |
| stop management | fixed, breakeven at 1R, ATR trail |
| session | all hours, 09:30–16:00, 09:30–12:00 |
| ADX(14) | off, ≥ 15, ≥ 20, ≥ 25, **≤ 20** |
| ATR(14) vs its own trailing median | off, ≥ 0.8×, ≥ 1.2×, ≤ 1.2×, ≤ 0.8× |

3 × 3 × 6 × 5 × 4 × 3 × 3 × 5 × 5 = **243,000**. Research is the first 65% of bars, locked the
last 35%. Everything is read at the **signal** bar and the entry is the **next bar's open**;
reading a condition at the fill bar is the `ent_bar` leak. The entry bar carries its own stop.
Scoring is in **ATR units at the signal bar**, never in R — the stop is a swept ATR multiple, so
R would pay a configuration for tightening its own denominator (`STUDY_V58_INITIAL_BALANCE.md`).
A **position lock** is enforced: a signal is skipped while the previous trade is still open,
because an every-cross rule can otherwise be a portfolio of overlapping positions.

**Grid shape, before any row of it:** 21.1% of scorable configurations profitable on US30
research and **11.4%** on US100, with the median configuration losing on both.

---

## 2. The control had the wrong variance, and that is worth recording

The first run of the minute-of-day matched control returned **0 of 25** clearing at p ≤ 0.05,
with p pinned near 0.40 for every row — including rows earning +0.18 ATR/trade against a control
median of +0.00. A control whose median is far below the rule and which still cannot reject
anything has the wrong **variance**, not the wrong mean.

The cause: the control samples one random bar per real signal, and those samples come out in the
order of the signals they replace, which is not chronological. The position lock — *skip a signal
while the previous trade is still open* — then rejected an arbitrary and enormous share of them,
so each draw kept a different small fraction of its trades and the spread of the draw means
exploded.

> **A CONTROL THAT INHERITS A POSITION LOCK MUST INHERIT THE ORDER TOO.** Sort the sampled bars
> before walking them. Check a control by its **spread**, not only by its median: if a rule
> beating its control by 0.18 scores p 0.40, the null is broken, not the rule.

Sorted, the same control returns **6 of 25** clearing on both markets — and the locked read then
kills all six anyway.

---

## 3. What the top 1000 agree on

| axis | consensus |
| --- | --- |
| entry mechanic | **cross 77%**, breakout confirm 20%, pullback 3% |
| side | long 55%, both 35%, short 11% |
| ADX | **≤ 20 — 55%**, ≥ 25 15%, off 11% |
| ATR regime | ≥ 1.2× 39%, off 29%, ≥ 0.8× 27% |
| stop | 3.0N 32%, 0.5N 23%, 1.5N 14% |
| target | **none 38%**, 3.0R 29% |
| maximum hold | **4h 47%**, 3h 30% |
| stop management | ATR trail 59% |
| session | 09:30–16:00 66%, all hours 23% |

Two of these are worth keeping and one is a trap.

**The plain cross beats both confirmation mechanics**, on both markets, in the consensus and in
the marginal read. Waiting for a close beyond the cross bar's extreme, or for a pullback to the
fast average, both score *worse* than simply taking the cross. Ninth independent confirmation
that chasing a move is destructive here — and, unusually, the pullback is no better, which
separates this family from the limit-entry mechanic that works on a null signal.

**The stop axis is bimodal** — 3.0N at 32% and 0.5N at 23% with a trough between. Two different
regimes are sitting in the same top 1000, which is a warning that the ranking is not describing
one thing.

**ADX ≤ 20 — the inverted filter — dominated at 55%, and it does not survive the marginal read.**

---

## 4. The marginal effect of each condition over the whole grid

A condition earns its place only by beating `off` in all four market-block columns.

| condition | US30 res | US30 lock | US100 res | US100 lock | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| ADX off | −0.0717 | −0.0553 | −0.1199 | −0.0028 | — |
| ADX ≤ 20 | −0.0603 | **+0.0244** | −0.1203 | **−0.0220** | **splits across markets** |
| ADX ≥ 25 | −0.0529 | −0.0632 | −0.1241 | +0.0101 | splits |
| ATR off | −0.0670 | −0.0334 | −0.1090 | +0.0007 | — |
| **ATR ≥ 1.2×** | **−0.0591** | **−0.0183** | **−0.0792** | **+0.0064** | **better in all four** |
| ATR ≤ 0.8× | −0.0837 | −0.1848 | −0.2555 | −0.0258 | worst everywhere |
| target none | −0.0590 | −0.0176 | −0.1014 | +0.0227 | best or tied, all four |
| target 1.0R | −0.0759 | −0.0719 | −0.1375 | −0.0354 | worst target everywhere |
| session 09:30–16:00 | −0.0589 | −0.0269 | −0.0622 | +0.0008 | better than all hours, all four |
| max hold 1h → 4h | −0.078 → −0.057 | −0.038 → −0.055 | −0.126 → −0.112 | −0.000 → −0.002 | no signal |

> **THE FILTER THAT WON THE RANKING AT 55% SPLITS ACROSS MARKETS ON THE MARGINAL READ.** ADX ≤ 20
> is +0.0244 on US30's locked block and −0.0220 on US100's. This is the second time in two studies
> that the single most-agreed condition of a top-1000 consensus fails the marginal test — V58's
> was an EMA cross at 74%. A consensus over a ranking is a consensus over what the ranking
> selected for; only the marginal read asks what a condition does to the whole grid.

The **ATR floor** is the one condition that earns its place, and its mirror is the worst setting
in every column, which makes it a gradient rather than a threshold. **No take profit** is best or
tied-best in all four — the thirteenth time on this branch. **The four-hour ceiling is neither
here nor there:** 1h to 4h spans 0.02 ATR/trade with no consistent direction, so the brief's
constraint costs nothing and buys nothing.

---

## 5. The single locked read, and it fails

| candidate | US30 res | US30 lock | US100 res | US100 lock |
| --- | ---: | ---: | ---: | ---: |
| **A** consensus (marginal mode of every axis) | +0.1081 | **−0.1437** | +0.2878 | +0.0573 |
| **B** the survivor cluster | +0.1761 | **−0.1562** | +0.1477 | +0.1233 |
| **C** as briefed | −0.0503 | −0.1577 | −0.1031 | −0.0532 |
| **D** C + the conventional ADX ≥ 25 | +0.0124 | −0.0894 | −0.1283 | +0.0682 |

Candidates A and B were research-positive on **both** markets and then went **negative on US30's
locked block** while staying positive on US100's — a split verdict, which is a failure. Candidate
C, the rule as briefed, is a well-powered negative: **PF 0.948 / 0.849** on US30 and **0.898 /
0.947** on US100 over 6,173 trades, control p **0.79 to 0.99**. Adding the conventional ADX floor
does not rescue it.

**And the population diagnostic is the strongest form of the verdict:**

> `corr(research ATR/trade, locked ATR/trade)` over 175,000 scorable configurations is
> **−0.0698 on US30** and **+0.0937 on US100**.

A research ranking on this family carries *no* information about held-back performance. Not a
weak signal — none.

---

## 6. NQ, read once

NQ had no part in the search: a different feed, a different contract, a different span.

| candidate, declared before the file was opened | n | ATR/trade | PF | win | control | control p | P(mean ≤ 0) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ATR floor (the only condition that earned its place) | 236 | +0.0567 | 1.097 | 46.4% | **+0.0413** | **0.449** | 0.265 |
| the research survivor cluster | 86 | −0.1190 | 0.753 | 45.6% | +0.0136 | 0.858 | 0.749 |
| as briefed | 1,084 | +0.0039 | 1.004 | 42.0% | −0.0274 | 0.527 | 0.472 |

**The ATR-floor candidate makes money and does not beat a coin flip.** A random entry running the
same stop, the same trail, the same four-hour ceiling and the same session earns +0.0413 against
its +0.0567. That is the whole result: what looks like a trend edge is the trade management and
the session, available to any entry at all.

The survivor cluster's failure on NQ agrees with its failure on US30's locked block, so that split
was a real defect and not noise.

---

## 7. The vectorbt second opinion

`research/v59/v59_vbt.py` rebuilds the briefed configuration from the bars with no shared code
path — its own EMAs, its own cross, its own stop and target. vectorbt 1.1.0 has no `td_stop`, so
the four-hour ceiling is expressed as an explicit exit sixteen bars after each entry.

| | v59 n | vectorbt n | agreement | v59 gross | vectorbt gross |
| --- | ---: | ---: | ---: | ---: | ---: |
| US30 long | 1,723 | 1,714 | 99.5% | −0.23 | −3.35 pts |
| US30 short | 1,714 | 1,712 | 99.9% | +1.08 | −1.69 pts |
| US100 long | 1,794 | 1,784 | 99.4% | +1.58 | +0.22 pts |
| US100 short | 1,794 | 1,787 | 99.6% | −2.61 | −3.29 pts |

Second consecutive study where vectorbt matches this branch's engine on trade count. The per-trade
points differ by intrabar ordering convention, and the two engines bracket the same conclusion:
**the gross edge, −3.35 to +1.58 points, is smaller than the round turn** (1.72 on US30, 1.215 on
US100). There is nothing for a cost model to preserve.

---

## 8. What ships

`pine/v59/V59_EMA_TREND_4H_strategy.pine` — lint clean, no continuation line indented by a
multiple of four, ATR as `ta.ema(ta.tr(true), 14)`, `ta.dmi`'s **third** element for the ADX,
New York wall-clock, every `var`-writing block guarded by `barstate.isconfirmed`, the exit bracket
placed with the entry, and the maximum hold declared as a **duration** converted through
`timeframe.in_seconds()` rather than a bar count — the unit error that cost V57 two live signals.

Its defaults are the best-*supported* configuration, not the best-scoring one, and the header
states its control p-value of 0.449. **Never backtested on TradingView.**

---

## 9. What is reusable

1. **A control that inherits a position lock must inherit the order.** Sort the sampled bars.
   Diagnose a null by its spread, not only its median.
2. **The most-agreed condition of a top-1000 consensus failed the marginal read for the second
   study running.** Consensus tells you what the ranking selected for; only the marginal read
   tells you what a condition does.
3. **`corr(research, locked)` = −0.07.** Print it before believing any ranking.
4. **The plain cross beats waiting for confirmation and beats waiting for a pullback.**
5. **The four-hour ceiling is free and worthless** — the constraint is not what is wrong with
   this family.
6. **No take profit**, thirteenth time.
7. **A volatility floor is the only condition that transfers**, and it buys about +0.02 ATR/trade
   against a hole of −0.06 to −0.11.
