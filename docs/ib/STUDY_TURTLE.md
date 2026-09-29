# Turtle Trading, long only: the breakout entry contributes nothing

*The supplied indicator spec — System 1 (20-bar high, 10-bar low exit, skipped once after a
winner), System 2 (55-bar high, 20-bar low exit), a 2×ATR(20) stop, pyramiding 0.5N up to 4 units,
every fill at the next bar's open — implemented faithfully, then run on NQ and US100 across six
timeframes, swept over ~100,000 configurations, controlled, walked forward and stress-tested.*

**Result: the channel breakout is not where the money comes from.** Entering at *random* and
managing the trade with the identical stop, channel exit and pyramid ladder earns the same or more.
On US100 240-minute bars with the spec's own defaults, the breakout returns **+0.595 R/trade** on
the research block and the random-entry control returns **+0.601** — an excess of **−0.005,
p 0.475**.

`research/turtle/`.

---

## 1. The implementation is verified, not assumed

`core.run` is a numba state machine; `reference.py` is a literal line-by-line transliteration of
the supplied JS, including its quirks — the skip flag cleared on use rather than on the next
winner, and the pyramid branch sitting in the same `else if` chain as the exits so a bar can never
both exit and add. The two agree **trade for trade across 8 configurations** (pnl, risk, units,
system, exit reason, entry bar, exit bar).

Two things the spec leaves open, resolved conservatively because they move the result more than
any parameter does:

* **Exit price.** The indicator only *marks* exits. A stop fills at `min(open, stop)` and a channel
  exit at `min(open, channel)`, so a gap through the level is paid in full and a level touched
  intrabar fills exactly at the level, never better.
* **"20-day" means 20 bars.** The spec indexes bars, so on a 15-minute chart its "20-day high" is
  five hours. Timeframe is therefore treated as a *parameter*, not as a fixed reading.

Costs are in index points and are assumptions: MNQ $1.44 round turn at $2/point = 0.72 pt; US100
CFD ~1.0 pt quoted spread; 0.25 pt slippage per fill.

## 2. The spec exactly as supplied

| inst | tf | research n / E[R] | out-of-sample n / E[R] |
| --- | ---: | ---: | ---: |
| NQ | 15m | 1125 / +0.015 | 556 / **+0.352** |
| NQ | 60m | 319 / +0.179 | 163 / **−0.365** |
| NQ | 240m | 58 / +1.329 | 47 / **−0.620** |
| US100 | 60m | 720 / +0.274 | 543 / +0.153 |
| US100 | 240m | 189 / **+0.595** | 130 / **+0.398** |
| US100 | 1440m | 31 / +1.742 | 23 / +1.039 |

Win rates run 17–48%, which is correct for trend following — it is a low-win-rate, high-payoff
system, and the brief-style "80% win rate" framing does not apply to it.

**NQ turns negative out of sample at every timeframe of 60 minutes or more. US100 stays positive
at every timeframe.** That difference is the first hint of what is really going on.

## 3. The control: is the breakout doing anything?

The right null for a breakout system is not a random *bar* — it is **the same trade management with
a random entry trigger**. `core.run_random` holds the ATR stop, the channel exit, the pyramid
ladder, the fill convention and the costs identical, and replaces only the decision of *when* to
enter with a coin flip at the same rate.

**The spec's own defaults, unbiased because nothing was selected:**

| inst | tf | block | E[R] | control | excess | p |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| US100 | 240m | research | +0.595 | +0.601 | **−0.005** | 0.475 |
| US100 | 240m | oos | +0.398 | −0.011 | +0.409 | 0.125 |
| US100 | 60m | research | +0.274 | +0.336 | −0.062 | 0.655 |
| NQ | 60m | research | +0.179 | +0.192 | −0.012 | 0.480 |
| NQ | 60m | oos | −0.365 | −0.094 | −0.271 | 0.840 |
| NQ | 240m | research | +1.329 | +0.473 | +0.856 | 0.100 |

**Not one block on either instrument reaches p < 0.05.** The best is p 0.100.

**And on a random sample of the grid** — 120 unselected configurations per instrument per
timeframe, which is the honest way to ask whether the breakout contributes:

| | 15m | 30m | 60m | 120m | 240m | 1440m |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ, median excess | +0.050 | +0.031 | +0.065 | +0.279 | +0.159 | **−2.267** |
| US100, median excess | +0.021 | +0.026 | −0.010 | +0.052 | +0.073 | **−0.110** |
| US100, % at p<0.05 | 11% | 13% | 12% | 6% | 4% | 4% |

Median excess is a few hundredths of an R, and the p<0.05 rate sits at or near the 5% expected by
chance. **Daily bars — where the sweep's top-ranked configurations all lived — are NEGATIVE on
both instruments once you stop looking only at the maximum.**

## 4. What the sweep actually found, and why its top row is worthless

~100,000 configurations per instrument (6 timeframes × 20,160 parameter points; 5 entry1 × 4
entry2 × 4 exit1 × 3 exit2 × 6 atr_mult × 7 pyramid settings × 2 skip settings, with the
pyramid-off redundancy collapsed). 115,024 scored on US100, ranked on the research block only.

Ranked by research expectancy, the top ten are **all daily configurations with 30–34 trades**.
That is the failure mode this branch has recorded repeatedly: ranking on a research maximum buys
sample size, not edge. Re-ranked on excess over the control and deduplicated by trade-set overlap,
the survivors go out of sample as:

| inst | research E[R] → oos E[R] |
| --- | --- |
| NQ, 6 distinct candidates | +1.57 … +2.00 → **−0.09 … −0.85** (win rate 20–30% → 7–16%) |
| US100 daily, 6 distinct candidates | +2.08 … +3.95 → +0.72 … +2.22, but on **22–26 trades** |

**Every NQ candidate collapses.** The US100 daily candidates stay positive on 25-odd trades, which
is not a sample you can conclude from — and the unselected daily sample in §3 is negative, so
these are the tail of a distribution centred below zero.

## 5. Why the results track the market rather than the rule

The control's own return, per block, next to what the index did:

| inst | tf | block | random-entry control E[R] | index move over the block |
| --- | ---: | --- | ---: | ---: |
| US100 | 240m | research | **+0.586** | **+247.6%** |
| US100 | 240m | oos | −0.005 | +49.6% |
| NQ | 60m | research | +0.157 | +60.1% |
| NQ | 60m | oos | −0.129 | +17.0% |

**Entering at random and trailing a stop pays +0.586 R/trade in a market that rises 248%, and
nothing in a market that rises 50%.** The Turtle machinery is a drift-harvesting device: the ATR
stop and channel exit cut losers short and the pyramid ladder compounds the survivors, which is a
real and useful property — but it is a property of *holding a rising market with a trailing stop*,
not of the 20- and 55-bar breakout.

This also explains an otherwise alarming pattern in §6: excess over the control grows out of
sample. It grows because the *control* weakens when drift weakens, not because the rule improves.

## 6. Feature engineering: what separates a winning Turtle trade from a losing one

Cohen's d at the **signal** bar, US100 240m research block, 189 trades. Every leading feature says
the same thing:

| feature | d | winners | losers |
| --- | ---: | ---: | ---: |
| `dist_low50_atr` | **−0.50** | 5.46 | 6.80 |
| `macd_hist_atr` | +0.45 | 0.214 | 0.139 |
| `ema50_slope_atr` | −0.41 | 0.035 | 0.055 |
| `ema100_slope_atr` | −0.41 | 0.027 | 0.047 |
| `dist_ema100_atr` | −0.38 | 2.30 | 3.17 |
| `vol_expansion` | +0.36 | 1.041 | 0.955 |
| `adx` | **−0.32** | **21.3** | **23.6** |

**Winners are breakouts taken EARLY in a trend; losers are breakouts taken LATE.** Winning entries
sit closer to the 50-bar low, less extended above the 100- and 200-EMA, with *lower* slope and
*lower* ADX — and with momentum accelerating (MACD histogram) into expanding volatility. Nothing
about the candle itself separates them: `body_atr` d = 0.014, `upwick_atr` d = 0.003.

The low-ADX result is worth stating plainly because it inverts the folklore: **the conventional
"only take breakouts when ADX > 25" is backwards here**, and it matches this branch's repeated
finding that ADX contributes negatively.

## 7. Testing that as a real filter — gate the triggers and re-simulate

A conditional split of realised trades is not a filter test, so the gate is applied to the entry
decision and the whole state machine re-run. Thresholds set on the research block only.

| gate | research E[R] / exc / p | out-of-sample E[R] / exc / p |
| --- | ---: | ---: |
| none (spec) | +0.595 / −0.005 / 0.475 | +0.398 / +0.409 / 0.125 |
| `dist_ema100 < p65` | +0.962 / +0.388 / 0.170 | +0.707 / +0.750 / 0.045 |
| `ADX < 25` | +0.881 / +0.273 / 0.255 | +0.797 / +0.806 / 0.030 |
| **`ADX < 22`** | +0.784 / +0.236 / 0.275 | **+1.055 / +1.094 / 0.020** |
| `ADX < 22 AND dist_ema100 < p65` | +1.307 / +0.778 / 0.070 | **+1.486 / +1.582 / 0.010** |
| `ADX < 18` | **−0.155 / −0.658 / 0.870** | +2.168 / +2.157 / 0.000 |

The gate raises raw expectancy on both blocks — the right shape. But **every ADX variant is
stronger out of sample than in sample**, and `ADX < 18` outright *fails* research while scoring
p 0.000 out of sample. Per CLAUDE.md that is a defect flag, not a result. §5 explains most of it
(the control is drift-dependent), but the family is also incoherent: the tighter the threshold the
bigger the out-of-sample excess and the *worse* the research excess, which is not what a real
mechanism looks like over a monotone grid.

**And it does not transfer.** The same `ADX < 22` gate on NQ:

| inst | tf | research E[R] | oos E[R] |
| --- | ---: | ---: | ---: |
| NQ | 60m | +0.297 | **−0.558** (worse than ungated −0.365) |
| NQ | 120m | +1.082 | −0.294 |
| NQ | 240m | +1.594 | −0.312 |
| US100 | 60m | +0.445 | +0.312 |
| US100 | 120m | +0.449 | +0.694 |
| US100 | 240m | +0.784 | +1.055 |

**Consistent on US100 at all three timeframes, negative on NQ at all three.** One instrument is
not a replication.

## 8. Walk-forward and Monte Carlo

Six equal folds, thresholds fixed, so every fold is honest. Excess over control:

| fold | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ 60m | −0.415 | +0.016 | +0.109 | +0.223 | −0.375 | −0.251 |
| US100 240m | −0.320 | −0.015 | +0.044 | +0.522 | +0.319 | +0.594 |

NQ: three of six negative, mean −0.116. US100: improving through time, mean +0.19.

**Monte Carlo**, spec on US100 240m out-of-sample (130 trades; permutation for path risk,
bootstrap with replacement for edge uncertainty):

| median DD | 95th DD | worst DD | mean R p05 | p50 | p95 | **P(edge ≤ 0)** |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 27.8 R | 44.8 R | 73.6 R | −0.136 | +0.393 | +0.969 | **11.7%** |

A median drawdown of **27.8 R** is the number to plan around, not the expectancy. At the Turtles'
own 1%-per-unit risk that is a ~28% equity drawdown in the median case and 45% at the 95th
percentile.

## 9. The four best versions

Ranked on **out-of-sample expectancy**, subject to a non-negative research excess and at least 60
out-of-sample trades, deduplicated by timeframe. All four are US100 — no NQ configuration meets
the bar, at any timeframe or gate.

| | timeframe | gate | research n / E[R] / exc | **out-of-sample n / E[R] / PF / exc / p** | max DD | P(edge≤0) |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| **T1** | 240m | ADX<22 and `dist_ema100 < 3.964` ATR | 90 / +1.307 / +0.77 | **64 / +1.486 / 2.79 / +1.55 / 0.008** | 8.6R | 0.2% |
| **T2** | 240m | ADX<22 | 122 / +0.784 / +0.22 | **79 / +1.055 / 2.09 / +1.11 / 0.016** | 10.0R | 0.8% |
| **T3** | 120m | ADX<22 | 228 / +0.449 / +0.07 | **144 / +0.694 / 1.64 / +0.60 / 0.056** | 31.2R | 3.2% |
| **T4** | 60m | ADX<22 and `dist_ema100 < 3.193` ATR | 313 / +0.523 / +0.19 | **225 / +0.397 / 1.39 / +0.40 / 0.088** | 36.1R | 9.0% |

*All use the spec's geometry: 20/55-bar entries, 10/20-bar exits, 2.0×ATR(20) stop, 0.5N pyramid
to 4 units, skip-after-winner on. Only the regime gate and the timeframe differ.*

T1 is the only one positive **and** control-beating on all three blocks separately — research
+0.77 (p 0.064), validation +1.19 (p 0.048), production +1.96 (p 0.008). It is also the smallest
sample. **T4 is the opposite trade**: 225 out-of-sample trades and the most reliable statistics,
at a third of T1's per-trade edge and a 36R drawdown.

Read the ladder as sample size against effect size, and read all four against §3: every one of
them carries the same caveat that a coin-flip entry with these exits performs comparably, and
against §7 that the ADX family grows out of sample and fails on NQ.

**Exit ordering.** The spec checks the ATR stop *before* the channel low, so when one bar pierces
both it books the worse of the two. A single stop order at `max(ATR stop, channel low)` — which is
what the Pine script places, and what price actually reaches first on the way down — is worth
**+0.05 to +0.13 R/trade** on all four. **The figures above are the conservative ones.**

## 10. The entry session, measured — and left unlocked

US100 240m, spec geometry, entries restricted to a window while **exits run unrestricted** (a
Turtle position is held for days; forcing it flat at a session boundary would be a different
strategy):

| entry window | research E[R] | out-of-sample E[R] |
| --- | ---: | ---: |
| all hours | +0.595 | +0.398 |
| **08:00–20:00** | +0.595 | **+0.462** |
| 09:00–20:00 | +0.618 | +0.524 |
| 04:00–12:00 | +0.713 | +0.322 |
| 18:00–04:00 | +0.321 | +0.347 |
| **09:00–16:00 (RTH only)** | +0.701 | **−0.017** |

**Restricting to the cash session destroys the system.** It is a multi-day trend follower and the
breakouts it needs occur across the extended hours; RTH-only takes research expectancy *up* and
out-of-sample expectancy to zero, which is the shape of a window fitted to the wrong half of the
sample.

Because the answer is broker- and instrument-dependent rather than a constant, `pine/turtle/`
**locks every structural parameter to its measured value and leaves the session start and stop as
free inputs** — the one deliberate exception to the configuration lock this branch adopted after
`STUDY_PINE_CONFIG.md`. The script's on-chart panel marks any non-default session so a changed
window can never be invisible in a screenshot, and the timeframe lock still refuses to run a
preset off its design timeframe.

## 9. Verdict

| claim | status |
| --- | --- |
| The 20/55-bar breakout adds edge over random entry | **REJECTED** — excess −0.005 on the spec's best block, no block at p<0.05, unselected grid median +0.02 to +0.07 |
| The Turtle machinery is profitable on US100 | **SUPPORTED** — but so is random entry with the same exits; it is drift capture |
| Turtle works on NQ | **REJECTED** — negative out of sample at every timeframe ≥60m, gated or not |
| Daily bars are the best timeframe | **REJECTED** — top of the sweep, but the unselected daily sample is negative on both instruments |
| Breakouts work better early in a trend (low ADX, unextended) | **PROMISING** — coherent, consistent across three US100 timeframes, but wrong-shaped and fails on NQ |

**The most profitable defensible modification** is not a modification of the entry at all: keep the
ATR stop, the channel exit and the pyramid ladder, apply them on US100 at 240 minutes, and accept
that what they harvest is drift. Adding `ADX < 22` improves US100 at every timeframe tested and is
the single best candidate found — but it is unproven, since its excess grows out of sample and it
inverts on the second instrument.

**What would settle it**: a third instrument. NQ and US100 are the same underlying index, and
`STUDY_TREND_LONG.md` on this branch already established that over their overlapping period 68% of
signals fire on the identical bar. The disagreement here is between *eras* (US100's 2016–2021 vs
NQ's 2022–2025), not between markets — so what is needed is an uncorrelated market, not more of
this one.

## Files

| | |
| --- | --- |
| `research/turtle/core.py` | the state machine, the random-entry control, entry gating |
| `research/turtle/reference.py` | literal transliteration of the supplied JS + the equality assertion |
| `research/turtle/data.py` | both instruments, their blocks and their cost models |
| `research/turtle/run_sweep.py` | ~100,000 configurations per instrument, research block only |
| `research/turtle/run_validate.py` | control, deduplication, out of sample |
| `research/turtle/run_report.py` | walk-forward, Monte Carlo, feature separation |
| `pine/turtle/TURTLE_LONG_strategy.pine` | the four presets, structurally locked, session left free |

Measured on NQ futures (5-minute source, synthetic price levels — see `research/us100.py`) and
US100 CFD 15-minute, one unit per Turtle unit, costs as stated in §1 and assumed rather than
measured. Research tooling for education and analysis, not financial advice.
