# STUDY_THE_STRAT — the Strat combo engine EA on US30, US100 and NQ

**Brief.** An MQL5 expert (`TheStrat_ComboEngine.mq5`, v3.10, "Gleidson") was uploaded with
"test this strategy". It types every bar against the previous one (1 inside, 2U, 2D, 3
outside), scores four reversal combos over the last three closed bars — 3-2 (weight 2), 1-3-2
(3), 2-1-2 (1), 3-1-2 (2), with a colour rule on the type-3 bar and a +1 hammer / shooter bonus —
and trades when the net score reaches 2 AND a location score reaches 2 from four filters on the
trigger bar's extreme (swing fractal within 50 pts, weight 2; a PMG cluster of two local extremes
inside an 80-pt zone, 2; a broken-and-reclaimed level within 50 pts, 1; prior day / week high or
low, overnight range or the NY 08:00 open within 50 pts, 1). The order is a stop 20 pts past the
trigger bar's extreme with the stop-loss 20 pts past the other extreme and a 2R target, one
trade at a time, 1% of balance. The pending order is cancelled at the next new bar, so it lives
for one bar. Timeframe is "current"; 15-minute is the primary read here, with 60-minute on all
three and 5-minute on NQ.

**Verdict.** As configured it loses on every market, every block and both sides: **US30 −0.250
R per trade over 1,315 trades (PF 0.71), US100 −0.116 R over 1,459 (PF 0.85), NQ −0.090 R over
489 (PF 0.88)**, win rates 34–36% against a 2R target whose break-even is 33% before costs. At
ZERO cost the three read **0.000, +0.071 and −0.001 R** — the pattern carries no edge, and the
geometry it trades (a stop the size of one 15-minute bar, entered on a stop order, resolved in a
median 4–7 bars) is the scalping geometry this branch has now rejected eight times because a
fixed round turn is a large fraction of a small stop. The combos do beat a random trigger bar
with the same order, buffers, stop and target (control −0.379 / −0.256 / −0.145 R, p 0.000 /
0.000 / 0.18), which is the same shape as `STUDY_SCALP_TREND`: **the pattern closes part of the
cost gap and does not open one.** The location score, the EA's headline feature, does nothing
(no filter at all −0.226 on US30 against −0.250 with it; a stricter score of 4 is worse on all
three). Widening the entry and stop buffers helps monotonically on every market because it widens
the stop relative to the cost, which is the cost-as-a-fraction-of-risk lesson again.

`research/strat/strat_core.py`, `research/strat/run_strat.py`; full output `results/strat/run.txt`.

## 1. Two assumptions the EA forces

**"Points" are broker points.** Every tolerance and buffer is in `SYMBOL_POINT`. These feeds
quote the CFDs to one decimal, so a point is 0.1 and the EA's 20-pt buffer is 2.0 index points,
its 50-pt tolerances 5.0, its 80-pt PMG zone 8.0; NQ ticks at 0.25. A two-decimal broker would
make all of that ten times tighter. The scale is therefore swept (§4).

**The location filters never read the forming bar.** The fractal scan starts at shift k+1 with
neighbours down to shift 1, PMG at shift 2, reclaim at shift 3, the overnight range and session
open at shift 1 — all closed bars. Prior-day and prior-week levels are the broker's day (00:00
server = 17:00 New York on these NY+7 feeds) and Monday week. No leak was found and none was
needed to explain anything.

## 2. As configured, 15-minute bars, whole file

| market | bars | triggers (share of bars) | location ≥ 2 passes | trades | R / trade | PF | win | pts / trade | max DD | median hold |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| US30 2016-10 → 2025-07 | 193,942 | 4,098 (2.1%) | 67.6% | 1,315 | **−0.250** | 0.71 | 33.9% | −4.3 | 333 R | 4 bars |
| US100 2016-11 → 2025-10 | 206,703 | 4,716 (2.3%) | 82.1% | 1,459 | **−0.116** | 0.85 | 35.8% | −0.5 | 171 R | 6 bars |
| NQ 2022-12 → 2025-12 | 70,685 | 1,727 (2.4%) | 92.8% | 489 | **−0.090** | 0.88 | 33.3% | −1.9 | 55 R | 7 bars |

Every block is negative: US30 research −0.320 / validation −0.089 / test −0.214; US100 −0.112 /
−0.079 / −0.162; NQ research −0.109 / locked −0.051. Every calendar year is negative except US30
2022 (+0.007), US100 2018 (+0.007) and 2020 (+0.019). Longs lose less than shorts on all three
(US30 −0.210 vs −0.291, US100 −0.048 vs −0.186, NQ −0.078 vs −0.103), which is the drift.

**The stop loses more than 1 R.** Stopped trades average **−1.30 R on US30, −1.20 on US100,
−1.10 on NQ**: the stop-loss is one bar's range plus 4 index points, so the spread, stop
slippage and the occasional gap through it are 10–30% of the risk. Targets pay +1.79 to +1.92 of
their nominal 2 R. Only 0.6–1.4% of exit bars touch both levels, so OHLC ambiguity is not what
decides this; 5–11% of trades exit on the fill bar.

**Cost is the whole story.**

| market | 0× cost | 1× | 1.5× | 2× |
| --- | ---: | ---: | ---: | ---: |
| US30 | **+0.000** | −0.250 | −0.375 | −0.501 |
| US100 | **+0.071** | −0.116 | −0.209 | −0.302 |
| NQ | **−0.001** | −0.090 | −0.134 | −0.178 |

Gross, the strategy is a coin on two markets and slightly positive on one. The assumed round
turn (US30 2.0-pt spread + 0.5 / 1.5 slippage; US100 1.0 + 0.25 / 0.75; NQ 0.5 + 0.25 / 0.75 +
commission) against a median risk of roughly 40 / 25 / 25 index points is what turns it.

## 3. The control

Random trigger bars with the same one-bar stop order, buffers, stop, 2R target and lock, matched
on trades taken per side, location filter dropped (a random bar has no location):

| market | strategy R | control mean R | P(control ≥ strategy) |
| --- | ---: | ---: | ---: |
| US30 | −0.250 | −0.379 | 0.000 |
| US100 | −0.116 | −0.256 | 0.000 |
| NQ | −0.090 | −0.145 | 0.183 |

So the combo trigger is worth about +0.06 to +0.14 R over a random bar — real, and smaller than
the cost of the geometry. A random stop-entry scalp with this geometry loses 0.15–0.38 R a trade
on these feeds, which is the number to keep: **every bar-range-stop breakout entered on a stop
order starts from there.**

## 4. The knobs

**Location filter.** Removing it entirely: US30 −0.226 (1,946 trades), US100 −0.125 (1,805), NQ
−0.127 (541). Requiring a score of 4 (fractal AND cluster, or everything): −0.363 / −0.149 /
−0.108. The filter passes 68–93% of triggers because a 5-point tolerance against 200 bars of
fractals almost always finds one; it removes a third of the trades on US30 and changes nothing
about their quality. The four flags fire on 65 / 36 / 33 / 21% of US30 triggers (fractal / PMG /
reclaim / HTF) and 91 / 71 / 68 / 50% on NQ.

**Point scale** (every tolerance and buffer multiplied; R / trades / PF):

| market | ×0.5 | ×1 | ×2 | ×5 | ×10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| US30 | −0.400 / 979 | −0.250 / 1,315 | −0.150 / 1,382 | −0.140 / 1,050 | −0.078 / 650 |
| US100 | −0.277 / 1,366 | −0.116 / 1,459 | −0.068 / 1,292 | −0.050 / 703 | −0.106 / 318 |
| NQ | −0.116 / 554 | −0.090 / 489 | −0.145 / 335 | −0.075 / 107 | +0.281 / 37 |

A two-decimal broker (×0.1 of this) is off the left edge. The one positive cell is 37 trades.

**Entry and stop buffer** (0 / 20 / 50 / 100 pts): US30 −0.438 / −0.250 / −0.174 / −0.093;
US100 −0.433 / −0.116 / −0.055 / −0.007; NQ −0.246 / −0.090 / −0.076 / −0.075. Monotone on every
market, and it is the stop widening relative to a fixed cost, not a better entry.

**Take-profit ratio** (R / win rate, break-even in brackets): US30 RR1 −0.275 / 49% (50%), RR2
−0.250 / 34% (33%), RR3 −0.312 / 24% (25%); US100 RR1 −0.163 / 51%, RR2 −0.116 / 36%, RR3 −0.093
/ 27%; NQ RR1 −0.035 / 53%, RR2 −0.090 / 33%, RR3 −0.142 / 24%. The win rate tracks the driftless
break-even at every ratio to within two points: the barriers are being hit by noise.

**Each combo alone** (weight 10, others 0, no hammer bonus): 3-2 −0.239 / −0.114 / −0.043; 1-3-2
−0.240 / −0.219 / −0.106; 2-1-2 −0.444 / −0.261 / −0.140; 3-1-2 −0.284 / −0.137 / −0.206 (US30 /
US100 / NQ). Nothing positive; 2-1-2, the most frequent (10,671 occurrences on US30), is the
worst, which is why the author gave it weight 1. Removing the hammer bonus changes nothing.

**Timeframe.** 60-minute: US30 −0.294 (349 trades, control p 0.64), US100 −0.043 (372, p 0.01),
NQ −0.001 (181, p 0.04). NQ 5-minute: −0.049 (876, p 0.01). Slower bars widen the stop and the
result moves toward zero, never through it.

## 5. What to take from it

* The pattern engine is real in the narrow sense that it beats a random bar; it is not real in
  the sense that matters, because the geometry it is attached to costs more than the pattern
  earns. This is the ninth time this branch has measured a bar-range-stop intraday entry and
  found the cost floor above the edge (`STUDY_US100_EDGELAB`, `STUDY_SCALP_TREND`,
  `STUDY_XAUUSD_SCALP`, `STUDY_ATME_LIVE`, `STUDY_TURTLE_FEATURES`, `STUDY_INTRADAY_SESSION`,
  `STUDY_V13_MA_REGIME`, `STUDY_HYPOTHESIS_PROGRAMME`).
* The location score is decoration at these tolerances. If the author wants it to mean
  something, the tolerances have to be in ATR, not points, and the filter has to be scored
  against a random filter of the same selectivity before it is believed.
* What would move it: a wider stop (the buffer ladder says so, and it says so because of cost),
  a longer hold, or a limit rather than a stop entry — which is the whole branch's finding on
  entry mechanics (`STUDY_ATME`, `STUDY_LIMIT_ENTRY`) and the opposite of what The Strat teaches.
