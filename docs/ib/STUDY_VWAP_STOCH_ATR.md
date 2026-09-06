# VWAP + Stochastic + ATR

**Verdict — the two indicators are one reading, and the trigger does not beat a coin flip.**
`corr(%K, (close − VWAP)/ATR) = +0.831`; the oversold cross sits below the session VWAP on **92.6%**
of its own bars against 44.3% of bars in general, and its short mirror sits above it on **94.4%**.
Against a random entry with the same side, stop, target, hold cap, costs and position lock, the
unfiltered trigger clears **0 of 8** declared geometry cells (best p 0.43). The marginal-consensus
cell fails both nulls on research (0.482 / 0.530) and on locked (0.292 / 0.184), on n=42 and n=9.
Ships `pine/vstoch/VWAP_STOCH_ATR_strategy.pine` with the asked-for design, the numbers in the
header, and **no edge claimed**.

Feeds: `NQ_1m` resampled to 15m (70,685 bars), `US100_LONG_15m`, `US30_LONG_15m`. Research block is
the first 65% of sessions, cut at 2024-11-28. MNQ costs, `COST 0.86 / SLIP 0.25` per side on NQ.

---

## 1. The design, declared before searching

Built around what this branch has already measured about all three components rather than around
what the indicators are usually said to do — the declaration is in the docstring of
`research/vstoch/vstoch.py` and was written before any number below.

| component | what the branch already knew | how it enters here |
| --- | --- | --- |
| VWAP | `STUDY_V63`: the volume is worth **+0.0096 Sharpe** over 69,003 matched pairs, and the VWAP is **not support** — nearest-distance quartile worst (+0.1325 against +0.2636 / +0.2538), Spearman(distance, result) −0.0495 | enters as a **state**, with the location readings carried as declared alternatives and an **unweighted twin** of every anchor |
| Stochastic | `STUDY_RULE_ANATOMY`: `Stoch K < 20` is **exactly** `Williams %R < −80`. `STUDY_DIVERGENCE_CONFIRM`: Stoch divergence is worth +1.04 points against the +11.9 the geometry needs | the oversold **cross** is the trigger; no Williams reading is added, because it would be the same column twice |
| ATR | `STUDY_V63`: floors positive, ceilings negative. `STUDY_V28`: the only survivor of 240 cells was the **bottom fifth** | **both directions run**, because the sign has now moved four times |

Long and short both run, since a mean-reversion trigger is symmetric in a way a breakout is not.

## 2. A plain ATR trailing mean is a clock, not a volatility reading

The first pass used `ATR / sma(ATR, 50)` and every rung of it came back inert on the trigger's own
bars — 98.6% and 98.8% pass rates. The cause is the tape, not the trigger:

```
mean ATR by hour, NQ 15m research:   00h 13.8   09h 23.2   13h 34.6   17h 29.2   23h 15.3
share of bars with ATR >= sma(ATR,50):   all 45.6%    RTH 98.9%    overnight 25.1%
```

**NQ's RTH ATR is 34.8 against 13.1 overnight — 2.7× — so an RTH bar clears its own 50-bar trailing
mean 98.9% of the time.** Any session-restricted strategy gating on `atr / sma(atr, n)` is gating on
the clock. Replaced with a **causal time-of-day baseline** — the mean ATR at this minute-of-day over
prior sessions only, minimum 20 observations — which lands at 51.4% within RTH and 48.4% overnight.
Same repair `STUDY_V32_FLOW_ML` made for volume, and it has to be made for ATR too.

## 3. Base rates on the trigger's own bars, before any P&L

| condition | long trigger | short trigger | all bars | lift (L / S) |
| --- | --- | --- | --- | --- |
| close < VWAP | **92.6%** | 5.6% | 44.3% | 2.09 / 0.13 |
| close > VWAP | 7.4% | **94.4%** | 55.8% | 0.13 / 1.69 |
| above VWAP **and** rising | 0.0% | 74.2% | 32.5% | 0.00 / 2.29 |
| VWAP rising | 0.5% | 74.4% | 37.6% | 0.01 / 1.98 |
| \|dist to VWAP\| ≥ 1.5 ATR | 52.9% | 56.7% | 35.5% | 1.49 / 1.60 |

**13 of 28 condition × side cells are inert** (pass ≥95% or ≤5%). The VWAP state is the trigger
restated: `corr(%K, (close − VWAP)/ATR) = +0.831` on RTH research bars. An oversold stochastic and a
below-VWAP close are two readings of the same displacement, so the VWAP cannot be an independent
confirmation of the stochastic — the sixth time on this branch a proposed confirmation has turned
out to be the trigger, after RSI 94.7%, Aroon 100.0%, MACD 99.8–100.0%, MFI 91.7% and EMA13>48
90.9% on breakout bars. **It is the first one measured as a correlation rather than a pass rate, and
it is the strongest of the six.**

## 4. The trigger against a random entry — 0 of 8

Same side, ATR stop, target, hold cap, costs and one-position lock; only the entry bar is randomised,
drawn from the eligible RTH population at the same rate and re-simulated end to end.

| side | geometry | n | %/trade | PF | random entry | p |
| --- | --- | --- | --- | --- | --- | --- |
| LONG | 2.0N / no TP / 96b | 270 | +0.0553 | 1.183 | **+0.0581** | 0.540 |
| LONG | 2.0N / 2R / 96b | 305 | +0.0001 | 0.974 | +0.0153 | 0.757 |
| LONG | 1.5N / 1.5R / 48b | 327 | +0.0047 | 1.012 | +0.0025 | 0.430 |
| LONG | 3.0N / no TP / 192b | 205 | +0.1518 | 1.406 | **+0.1492** | 0.483 |
| SHORT | 2.0N / no TP / 96b | 367 | −0.0780 | 0.727 | −0.0503 | 0.793 |
| SHORT | 2.0N / 2R / 96b | 424 | −0.0510 | 0.773 | −0.0322 | 0.827 |
| SHORT | 1.5N / 1.5R / 48b | 472 | −0.0199 | 0.880 | −0.0218 | 0.440 |
| SHORT | 3.0N / no TP / 192b | 268 | −0.1292 | 0.690 | −0.1282 | 0.513 |

The two long cells that make money make **exactly what a random bar makes** with the same geometry.
`STUDY_TURTLE`'s finding on a different indicator: the exits are the asset.

## 5. It is not cost, and the win rate is its own break-even

Gross-positive on **4 of 4 long** geometries and gross-**negative** on 4 of 4 short, over a sample in
which the index rose 89% — a drift exposure, not a signal.

| geometry | median risk | round turn | cost as % of risk | break-even win | actual win |
| --- | --- | --- | --- | --- | --- |
| 1.5N / 1.5×ATR | 47.1 pts | 1.36 pts | 2.89% | 51.44% | **51.38%** |
| 2.0N / 2.0×ATR | 62.8 | 1.36 | 2.17% | 51.08% | **50.82%** |
| 3.0N / 3.0×ATR | 94.2 | 1.36 | 1.44% | 50.72% | **54.31%** |

Cost is **1.4–2.9% of the stop** — an order of magnitude below the 24% a 0.75N scalping stop carries
(`STUDY_SCALP_REQUIREMENTS`) — which is rare on this branch and means cost is not the objection. The
win rate tracks its own driftless bound within 0.6 points at two of three rungs: the barriers are
being hit by noise, the same signature `STUDY_THE_STRAT` and `STUDY_IB25_RETRACEMENT` recorded.

## 6. The grid: 31,752 declared cells, 37.1% profitable

3 stochastic parameter sets × 3 level pairs × 2 sides × 7 VWAP readings × 7 ATR readings × 3 stops ×
4 targets × 3 hold caps; 19,579 scorable at ≥40 research trades. **37.1% profitable** — unusually
hostile for this branch, where grids typically run 60–98% and the complaint is normally the opposite.

Marginal average per axis (%/trade, across everything else):

- **side** — LONG +0.0232 (67.6% of cells positive) against SHORT **−0.0429 (9.8%)**.
- **ATR** — `ceil<=1.0` **+0.0062** and `rank<=0.4` +0.0029 are the only positive readings;
  `floor>=1.2` −0.0228, `rank>=0.6` −0.0213, `floor>=1.0` −0.0190. **The sign inverted again**: this
  agrees with `STUDY_V28`'s bottom-fifth survivor and reverses `STUDY_V63`, which measured every
  floor positive and every ceiling negative on a trend base. Fifth time a volatility rule's sign has
  moved here. Run both directions or run neither.
- **VWAP** — `with_trend` +0.0102 beats `with_reversion` −0.0137, so the oversold cross does better
  **above** the VWAP than below it, which is the opposite of the mean-reversion framing. Read that
  against §3: the reading only binds on the 7.4% of long triggers that are above the anchor.
  `anchor_trend` has the best marginal (+0.0472) on **72 cells** and is discarded as a sample-size
  artefact — it passes 0.55% of long triggers.
- **take profit** — no target is the only positive PF marginal (1.0070 against 0.943–0.981).
  **Nineteenth time on this branch.**
- **stoch parameters** — 9/3/3, 14/3/3 and 21/3/3 span 0.007 %/trade, and the level pair spans 0.008.
  Neither is a degree of freedom.
- **hold cap** — 48/96/192 give the *identical* trade set at the consensus geometry, because a 1.5N
  stop with a 1.5×ATR target always resolves first. **An inert axis**, as in `STUDY_V61`.

## 7. The one locked read

Declared in advance: the **marginal-consensus** cell — LONG, stoch 9/3/3, level 30, `with_trend`,
`ceil<=1.0`, 1.5N, 1.5×ATR, hold 48 — not the top row, which is the maximum of ~7,273 positive draws
(top row: +0.2827 %/trade at PF 2.957 on **42 trades**).

| block | n | %/trade | PF | vs random entry | vs random filter |
| --- | --- | --- | --- | --- | --- |
| research | 42 | +0.0022 | 1.044 | p 0.482 | p 0.530 |
| **locked** | **9** | +0.0526 | 1.855 | p 0.292 | p 0.184 |

It fails both nulls on both blocks, and it **grows on locked** — the wrong shape, for the twelfth
time here. n=9 settles it regardless of any p-value. Its neighbourhood is 13 of 14 profitable, which
is exactly the reminder `STUDY_V60` supplied: a perfect plateau is not evidence, and this one is
built on 42 trades.

## 8. Cross-market, frozen

| market | research | locked |
| --- | --- | --- |
| NQ (chose it) | +0.0022, PF 1.044, n 42 | +0.0526, PF 1.855, n 9 |
| US100 | **−0.0160, PF 0.787**, n 44 | +0.0287, PF 1.191, n 20 (p 0.341) |
| US30 | **−0.0171, PF 0.741**, n 79 | +0.0280, PF 1.554, n 40 (p 0.288) |

Negative on **both** research blocks of the two markets that had no part in choosing it, positive on
both locked blocks, and clearing nothing anywhere. A rule that is negative where it is fitted and
positive only in the last block is describing the late-sample regime, not a mechanism.

## 9. Parity

`research/vstoch/vstoch_parity.py` runs the shipped script's own order model — tick-rounded
fill-relative bracket placed **with** the entry, hold cap firing on bar `signal+hold` and filling at
the **next** bar's open, since `strategy.close_all()` cannot sell the close of the bar that triggers
it. Against the engine on identical signals: **51/51 trades, per-trade correlation 1.0000, 98.04%
identical exit bars**, gap +1.7% research / −0.2% locked. The hold cap is inert at this geometry so
the transcription and as-configured runs are the same run.

## 10. What would move it

Not a parameter. The trigger is a coin flip on this data and the VWAP is 83% the same column, so the
family needs a genuinely independent second reading — order flow at price (no feed here carries
bid/ask), or a level the auction has to cross. Do not re-run the stochastic cross with a different
smoothing, a different oversold level, or Williams %R, which is the same rule.
