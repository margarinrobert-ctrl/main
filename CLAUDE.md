# Working notes for this repository

Quantitative futures research on NQ/MNQ. One instrument, OHLCV 1-minute bars,
2022-12-26 → 2025-12-12. Read `docs/RESEARCH_PROTOCOL.md` before proposing or judging a strategy.

## The rules that keep getting re-learned the hard way

**Select on research, read the locked block once.** The split is the first 65% of sessions.
Any criterion that touches the locked block — profitability, excess, correlation — puts the
holdout inside the selection. This has happened twice here and both times the result looked
better than it was.

**A win rate means nothing without its base rate.** The driftless bound is 1/(1+R), but the *real*
base rate is not that: costs push it down, a wider barrier pushes it back up, and drift lifts longs
and sinks shorts. On 60-minute bars a long 2.5×ATR 1R strategy wins **54.2%** by default. Score
every rule against its own geometry's base, computed from the population.

**Direction is not free on this sample.** NQ rose 89%. Any search allowed to pick a side picks
long. See §4c.

**Ban calendar conditions from rule search.** Weekday and month conditions partition the sample
five or twelve ways and hand the search a free lottery. Removing them was worth $8,771 on the
holdout; requiring subset coherence was worth another $6,030. Ranking by a *minimum* over a
neighbourhood, the obvious over-correction, cost $18,970. See `docs/ib/STUDY_1R_PROCEDURE.md`.

**Test a condition against a random filter of the same selectivity**, not against total dollars
(which fails every restrictive condition) and not against per-trade edge (which passes every one).
`research/dropone.py`. The research p-value is decoration; read the locked one.

**COMM = 1.00 was broker commission only.** No CME exchange fee, no NFA line, so every result in
`docs/ib/` was measured ~44% light on fees — real MNQ is $1.44/round turn. And a flat slippage tick
is charged in the calm bars where it is not paid and understated in the fast ones where it is,
which is precisely where a stop system exits. `research/costs.py` / `src/lib/quant/costs.ts` itemise
fees per side and scale slippage by bar speed, exit role and session. Cost realism punishes
TURNOVER, not edge: the nine shipped legs give back 3% and none flip, while two high-frequency TS
strategies cross to unprofitable — one of them the time-of-day control. Note the direction is not
uniform on the Python side (calm-bar friction FELL from 2t to 1.5t per side while fees rose), so
read the decomposition, not the total. See `docs/ib/STUDY_COSTS.md`.

**Sizing creates no edge.** Fixed one contract per leg, AVA across legs. See §9.

**A win rate that exists at only one threshold is not a mechanism.** Parameterise every shipped
rule and sweep its own neighbourhood on research; a real edge decays smoothly. V1's 70.9% falls to
its base rate two rungs away, while V3 *gained* holdout significance when loosened (matched-control
p 0.384 → 0.040) because it finally had enough trades. Corollary, learned the hard way: over a
monotone threshold grid a union **is its loosest member**, so gate on the SIZE of the excess, never
its sign. See `docs/ib/STUDY_1R_MORE.md`.

**`ent_bar` is the FILL bar, not the signal bar.** Read any condition, feature, regime label or
ATR at `ent_bar` and you are reading a bar that closes after the order is sent — for a rule whose
median hold is 0 bars, the bar the trade resolves on. Use `test_suite.sig_bar`. This produced a
holdout result at p 0.0005 that replicated across 9 of 9 independently-found strategies, and was
pure leakage; it also faked V2's "edge lives below the 200 EMA". A conditional split of realised
trades is not a filter test — filter the TRIGGERS and re-simulate. See `docs/ib/STUDY_AUCTION.md`.

**Volume profile adds nothing here.** 47 auction conditions (POC, value area, VAH/VAL as levels,
opening classification, naked edges, LVN/HVN) x 9 strategies: 7 of 172 tests passed on research
(fewer than chance), 0 survived the holdout. Low-volume nodes are revisited at exactly the rate of
a distance-matched random level, 42.8% against 42.8%. The 80% rule measures **50.6%**, worse than a
time-matched control's 59.9%. Do not re-run this.

**A decorrelated leg still has to have an edge.** Adding a coin-flip signal at |rho| 0.25 raised
the book's net profit, cut its Sharpe 3.73 -> 3.23 and more than doubled its drawdown. A
correlation matrix alone will talk you into that trade. See `docs/ib/STUDY_SEMIVARIANCE.md`.

**Normalise a signal before deciding it is dead.** SAM looked null over 4,032 combinations
because only the paper's reading was tried. Adding a scale-free ratio, a trailing z-score and the
CROSS as well as the state -- 1,440 conditions, 142.8M combinations -- produced four scalps that
beat a matched control on the holdout and lift book Sharpe 3.73 -> 4.57. On 5-minute bars the edge
is specifically in the INTRABAR estimator: the best bar-return-only 5m rule fails the matched
control at p 0.354, and TradingView cannot supply intrabar data at that scale. See
`docs/ib/STUDY_SAM_SCALP.md`.

**Features do not predict here; the harness is the asset.** 134 causal features (86 base + intrabar
microstructure, semivariance, auction position) x 4 horizons x 2 timeframes = 1,072 IC tests. ONE
survives FDR -- `close position in bar` at h=1 -- and its research-block edge is 0.28 ticks against
a 6.0-tick round turn, with the opposite sign on 30m. 134 features are 28 principal components.
Rank feature importance on RESEARCH ONLY: ranking over both blocks produced a family that failed
research (p 0.08) and "passed" locked (p 0.02). See `docs/ib/STUDY_FEATURES.md`.

**Passing on the holdout while FAILING on research is the wrong shape.** A rule chosen on research
should look better there; the holdout is where an edge decays, not where it appears. Seen twice
now: a feature family (ranked over both blocks by mistake) and the whole daily-trend pullback
family. Treat it as a defect, not a result.

**The daily trend can dictate DIRECTION so the optimiser never picks it.** Worth keeping as a
protocol even though the pullback family failed: `research/daily_trend.py` keys the daily state on
a known-at timestamp so an intraday bar sees the last RTH close and nothing after. Note 81% of bars
are in a daily uptrend and 7% in a downtrend, so the short side is close to untestable here.

**If trading 07:00-11:00 New York, trade 09:30-11:00.** Same rule, 4x the per-trade result on
research on 44% fewer trades, and the cost model does not widen the pre-RTH spread so the gap is
larger than measured. See `docs/ib/STUDY_TREND_PULLBACK.md`.

**The trend-pullback structure is exhausted on this data. Do not re-run it.** Two passes: 161,280
then 5,723,136 combinations, 15 EMA periods, 13 crossover pairs, Supertrend/Ichimoku/PSAR/KAMA/
Hull/Vortex/Aroon/MACD/ADX, in 07:00-11:00 New York with direction dictated by the daily trend.
Second pass: 127 rules beat a time-matched control ON RESEARCH, 0 survived the holdout, 6.4
expected by chance. The window baseline itself is negative (-$22 to -$5/trade). See
`docs/ib/STUDY_TREND_PULLBACK_2.md`. What would move it: more history (this sample is one regime,
81% daily uptrend), cross-asset files, a second instrument.

**Run the matched control as a RESEARCH gate, not a final check.** Running it only at the end let
four rules reach a holdout they then "passed" while failing research. In front, it is the cheapest
way to stop a family that is really just "be in the market at these times".

**The ENTRY MECHANIC was the biggest lever found on this branch, and it cuts both ways.** A resting
limit 0.75 x ATR(5) in your favour, versus a market order at the next open, on EVERY bar with no
rule at all: market entry loses $0.6-$16.8/trade, the limit makes $4.3-$37.7, on both blocks, both
SIDES (so it is not drift), all timeframes and windows, robust to requiring price to trade through
by 4 ticks, and NOT explained by barrier placement -- a market entry given the same absolute
barriers earns nothing. But applied to the nine validated strategies it takes the book from
$55,424 to $13,415, because a good signal's edge is in the IMMEDIACY of the move and waiting for a
0.75 ATR adverse excursion discards exactly those trades. The mechanic SUBSTITUTES for a signal; it
does not complement one. What works is short-horizon mean reversion at the execution layer -- worth
little as a signal (0.28 ticks vs a 6-tick round turn) and a lot as a better fill on a trade you
were making anyway. See `docs/ib/STUDY_LIMIT_ENTRY.md`.

**Tune with `research/tune.py`, not by editing a module.** A trade's outcome depends only on its
signal bar and the geometry, so the price walk is cached per bar and every exit knob — stop,
target, flatten time, max hold, entry mechanic, cost model — becomes an array index: 0.4 us per
geometry against `sim_core`'s 1.3 ms, and a 2,000-draw matched control in 6 ms, which is what
finally makes the control affordable as a GATE. Verified trade-for-trade against `sim_core` on
4.6M trades. It will not show you the locked block from a sweep — `reveal(df, k)` is the only way,
it states the multiplicity first, and it flags anything better on locked than on research as the
wrong shape. It is also a page in the app at `/quant/tune`, engine ported to TypeScript and
asserted trade-for-trade against `runBacktest`; note the app sizes stops in WILDER's ATR (what
`runBacktest` uses) while the research layer uses `ema(tr, n)`, so compare the two on shape, not to
the dollar. See `docs/ib/STUDY_TUNER.md`.

**A high 1R win rate can be a day filter wearing a barrier costume.** M4 wins 73.9% and none of
its machinery earns it: widening the stop to INFINITY is worth more than the shipped 4xATR
($9,030 vs $9,005, zero barriers touched), and on the same days a RANDOM first-hour entry does as
well (p 0.187 win, 0.556 net). It selects sessions that drift up -- its days travel +$96.3 against
+$14.6 for all days -- and it does beat a minute-matched control doing that (research p 0.001).
Before believing any barrier strategy, widen the stop until the barriers stop binding and re-enter
at a random bar on the same days; whatever survives both is what you actually own. Its `body<30%`
is a real monotone mechanism (small bodies +$86..111/trade, large bodies NEGATIVE); its
`ATR>1.8x mean` is a threshold sitting just above a dead [1.6,1.8) band. See
`docs/ib/STUDY_M4_ANATOMY.md`.

**The Initial Balance adds nothing here either.** 14 causal IB features x 8 pre-declared
candidates, matched control as the gate, BH at FDR 0.10: 3 passed research, 2 LOST money on the
holdout and the third decayed to barely above the do-nothing baseline. The two that looked best on
locked both failed research -- the wrong shape. M4's own condition restated at day scale fails its
research control at p 0.305. `research/ib_features.py`. Do not re-run it.
**A two-sided filter is an answer key, not a signal.** The HP filter (Harris & Yilmaz momentum,
QuantConnect 2018) solves for its trend JOINTLY over the whole series, so x_t depends on y_{t+1}...
Run once over a price history it leaks: daily MNQ goes $8,893 -> $83,789 and Sharpe 0.43 -> 3.95,
and on 30m it goes from LOSING $7,480 at Sharpe -0.18 to +$519,532 at Sharpe 12.96 with the max
drawdown collapsing 93% to $1,031. Applied causally the published null replicates -- it loses to
buy-and-hold ($8,893 vs $24,796), fails a flip-matched control at p 0.238, and 19 of 30 cells of
its own parameter grid are negative. THE DIAGNOSTIC IS THE SURFACE: causal 11/30 cells positive,
leaky 30/30. A real edge is a ridge on a noisy surface; a leak is a plateau. Same trap in
`filtfilt`, `rolling(center=True)`, Savitzky-Golay, symmetric wavelets, STL. A filter is a signal
only if bar t's value is unchanged had the series ended at bar t. See `docs/ib/STUDY_HP_FILTER.md`.

**MA TYPE is not a degree of freedom; MA LAG is.** Zakamulin's claim replicates exactly here.
SMA(11), LMA(16) and EMA(11) all carry average lag 5 (closed forms verified to 1e-13), their
values correlate 0.9999+, their trigger sets overlap 89.5-97.3% and their win rates sit inside one
point (52.5-53.5%). Net dollars vary up to 54%, but that is noise on the 5-10% of trades that
differ, not a property of the weighting. Do not expect a rule that fails with SMA to work with
EMA. Three things the article does not say, measured: SMA and EMA have IDENTICAL lag at every
window by construction; DEMA and TEMA have exactly ZERO ramp lag at every window and Hull near
zero, so they are extrapolators, not lagging averages, and cannot be lag-matched to the first
group (they ARE a real separate axis); and KAMA's lag is 1.25 regardless of window, so its period
is INERT on a trending series. `research/ma_lag.py`. See `docs/ib/STUDY_MA_LAG.md`.

**Eight conditions in the pool are literally duplicates, and three pairs are a theorem.**
Zakamulin Part 4: every MA timing rule is a weighted average of price CHANGES, so rules whose
change-weighting coincides are one rule with two names. Verified EXACT here, 0 disagreements in
35,471 bars at every window: SMA change of direction == Momentum(n); LMA(n-1) change == Price-SMA(n)
(the n-1 is the article's convention -- at LMA(n) it is 97-99.7%, an off-by-one masquerading as
"approximately true"); EMA change == Price-EMA(n), because both are positive multiples of
(P_t - EMA_{t-1}). Auditing our own pools found that third identity sitting there as six separate
conditions: `close>EMA20 == EMA20 rising`, and the same for 50 and 200, plus Stoch K<20 ==
Williams%R<-80 and Donchian/ROC naming duplicates. factory 115 -> 107 effective, ladder 198 -> 184;
a 3-condition search overstates its configuration count ~24%. The direction is CONSERVATIVE (a
Bonferroni threshold only gets stricter) so nothing published needs revising, and none of the nine
shipped rules contains a duplicate pair -- but a drop-one test on a rule that did would report a
condition contributing nothing when it was never a second condition. `ma_lag.pool_duplicates()`.
See `docs/ib/STUDY_RULE_ANATOMY.md`.

**There is a second instrument now, and two legs survive it.** `research/us100.py` loads a
US100 15-minute file, 2016-11 to 2025-10, NINE years against NQ's three. Its clock is New York + 7
and that offset is STABLE across DST (the RTH volume jump sits at 16:30 file time in both Dec-Feb
and Jun-Aug), so a fixed -7h shift is right year round. US100 before 2022-12-26 is 71,074 30m bars
nothing here has ever seen -- 2018, COVID, the 2022 bear. Running the shipped legs there unchanged:
V1 +9.2 excess over base (p 0.0001) and V2L +8.5 (p 0.0050) both PASS at FDR 0.10, and their excess
is essentially UNCHANGED from the overlap (+8.4, +7.8). RW, M4 and M1 fail, M4 falling +16.7 -> +4.3
and M1 +8.2 -> +1.2. The two that survive are the MEAN-REVERSION and COUNTER-TREND legs, which is
the same story trend-following has told all along here.

**THE ENTRY MECHANIC IS WORTH TEN TIMES THE ENTRY SIGNAL, and it is MEAN REVERSION.** 293,760
ATME evaluations, four markets. Isolating the mechanic by re-running the same configuration as a
market order: a resting limit 1.0xATR below is worth **+0.24 to +0.43 R/trade**, against a
best-ever SIGNAL on this branch of +0.043 R. Every market is negative as a market order. And the
response is a monotone MIRROR IMAGE on all four markets: buying dips improves as the limit gets
deeper (-0.074 -> -0.051 NQ, -0.130 -> -0.062 US100), while buying strength via a STOP entry
degrades as it gets further (-0.111 -> -0.204 NQ, -0.137 -> -0.279 US100). **Chasing a breakout is
the single most reliably destructive choice in the whole search.** `research/atme/`.

**THE COST OF THE LIMIT MECHANIC IS THE FILL RATE: about two thirds of signals never trade** (35%
fill at 1.0xATR). That is why it cannot be bolted onto a signal whose edge is immediacy -- the
`STUDY_LIMIT_ENTRY.md` finding, now confirmed from the other direction: it is ADDITIVE on a null
signal and SUBSTITUTIVE on a good one.

**STILL 0 OF 64,800 CONFIGURATIONS ARE PROFITABLE ON ALL FOUR MARKETS** (279 reach three). The
three indices hold out of sample at PF 1.68-2.03 with P(edge<=0) 0.0% over 6,585 trades; XAUUSD
fails at P(edge<=0) 99.9%. And two of the three die at 2x the assumed spread, which is inside the
error bar of an assumption -- bid/ask is unavailable in all four feeds.

**CHECK CONCURRENCY BEFORE CALLING AN EVERY-BAR CONFIGURATION A STRATEGY.** An entry on every bar
can silently be a portfolio of dozens of overlapping positions. Measured here: median 1 concurrent
position, max 3, because a 35% fill rate and short holds keep it there. It was checked, not assumed.

**FIVE TREND-FOLLOWING BRIEFS HAVE NOW RESOLVED INTO MEAN REVERSION.** Build the next hypothesis on
that rather than against it.

**A HYPOTHESIS COUNT IS NOT A DIVERSIFICATION COUNT.** Eight breakout hypotheses on US30: H1
Donchian, H6 MTF-aligned and H7 participation-confirmed correlate **0.87-0.96** in daily strategy
returns -- adding an MTF or volume filter to a breakout does not make a new strategy, it makes the
same one with fewer trades. Only the squeeze (0.14-0.39) and prior-session-high (0.17-0.37) are
distinct. Third time this branch has caught its own pool duplicating (`STUDY_RULE_ANATOMY.md`,
and ADX/efficiency-ratio at 0.642). Combining the eight took US30 Sharpe from 0.30 to **0.11**.

**THE DIVERSIFICATION IS ACROSS MARKETS, NOT ACROSS INDICATORS -- and it is still small.** Daily
strategy returns across markets correlate **~0.00** (US30/US100 0.29) even though PRICES correlate
0.68-0.87, because the trades fire at different moments. But combining the three indices moved
Sharpe only 0.37 -> **0.38**: return and volatility rose together. Adding gold destroyed it
(0.38 -> 0.01).

**COMPRESSION SETUPS SELECT THE BARS WHERE COSTS ARE WORST.** The squeeze breakout -- require a
tight range, then trade its resolution -- was the most promising untested "avoid chop structurally"
idea and it ranked LAST of eight: **1.2% parameter plateau**, OOS -0.135, PF 0.64. Diagnosis: on
5-minute bars compression selects LOW-ATR bars, and a low-ATR bar is exactly where a fixed round
turn is largest relative to the stop. A chop-avoidance setup can be anti-selective on cost.

**THE INTRADAY SCALPING CONSTRAINT IS WHAT FAILS, replicated four times now.** Every positive cell
across the US100 edge lab, the US30/US100/NQ scalp study, the XAUUSD study and the eight-hypothesis
programme sits at WIDE stops (3-4xATR) with hour-plus holds. The best surviving candidate -- H5
break-and-retest, robustness 74/100, +0.0435 R over 845 OOS trades on three indices, P(edge<=0)
4.2% -- has a 4xATR stop and a four-hour hold. It is not a scalp. Stop asking for one.

**EVERY CANDIDATE ON THIS BRANCH DIES AT 1.5x THE ASSUMED SPREAD.** H5 +0.0207 -> +0.0032, H6
+0.0221 -> +0.0022, all negative at 2x. Bid/ask is unavailable in ALL FOUR feeds, so the spread is
assumed, not measured -- which means no result here is distinguishable from zero on execution
grounds. Getting bid/ask data is worth more than any further parameter search.

**XAUUSD IS THE FOURTH INSTRUMENT AND THE ONLY UNCORRELATED ONE.** 5-minute, 2004-2026, 1.44M
bars, `data/XAUUSD_5m.csv` -- a DIFFERENT export format (semicolon, `Date;OHLC;Volume`, ascending,
no TickVolume column). Contemporaneous 5m correlation with the indices is only **0.057-0.070**, so
gold genuinely cannot be voted on by NQ/US100/US30. Its clock was derived from its OWN anchor
(gold does not key on 09:30 equities): the summer peak in mean |5m return| lands at raw 15:30 =
**08:30 New York to the minute**, and corr(US30, XAU) spikes to +0.057 at a 7h shift against ~0 at
5/6/8. Also NY+7. **Pre-2010 is EXCLUDED: 10.06% zero-range bars and a median 5-minute volume of
14 ticks.** `research/scalp/inventory.py` prints the whole inventory with a transparent quality score.

**GOLD'S COST FLOOR IS ~3x THE INDICES', and it decides the answer.** XAUUSD 5m ATR is ~1.5 USD
against an assumed 0.30 spread, so break-even at 1:1 needs **100.8% at a 0.35xATR stop**, 73.7% at
0.75x, 55.9% at 3.0x -- against actuals of 30.7/46.0/38.7%. No stop distance closes it. Bid/ask is
unavailable in EVERY feed here, so every cost number is an assumption; on gold the difference
between 0.30 and 0.13 USD/oz is the difference between -0.08 and break-even.

**BUT THE GOLD BREAKOUT IS NEGATIVE *GROSS*, so it is not a cost problem.** At ZERO cost every
trend-following entry is negative at a scalping stop (-0.061 to -0.020), the mirrored SHORT side is
negative too (-0.047), and only `breakout + not-chop p95` turns positive (+0.067 at 1.5xATR). Always
run the zero-cost variant before blaming execution.

**THE XAUUSD FROZEN RULE DECAYED MONOTONICALLY ACROSS FOUR ORDERED BLOCKS** -- gross +0.0669
research, +0.0421 validation, -0.0163 test, **-0.0199 untouched**, with control excess following
+0.149 -> -0.035. An untouched final block is worth more than any amount of walk-forward: it is
the only test that cannot be contaminated by having looked. Reserve one.

**THERE IS A THIRD INSTRUMENT NOW, AND IT IS THE FIRST INDEPENDENT ONE.** US30 (Dow), 2.88M
1-minute bars 2016-10 to 2025-07, `research/edgelab/feeds.py`. 15m return correlation US30/US100
**0.758** and US30/NQ **0.679** against NQ/US100's **0.874** -- materially more independent than
the pair this branch already had, with NO lead-lag at any offset (every cross-correlation peaks at
k=0). Its clock was DERIVED, not inherited from US100: `derive_offset` locates the 09:30 step
separately in winter and summer and refuses a constant shift if they disagree. Also NY+7.

**TRADE-WEIGHTED AND DAY-WEIGHTED EXPECTANCY DISAGREE IN SIGN ON AN INTRADAY TREND SYSTEM.**
`day_R` (mean of per-day means) is the right unit of INFERENCE because triggers cluster, but it
weights a 1-trade day like a 12-trade day -- and a trend follower's profitable days are precisely
the high-activity ones. The gated breakout scores **positive trade-weighted and strongly negative
day-weighted**; scoring on `day_R` alone rejects the whole family for the wrong reason. Use
`fast.score_block_bootstrap`: resample whole DAYS WITH THEIR TRADES ATTACHED, then take the
trade-weighted mean. Report both.

**CHOP FILTERING GENUINELY RESCUES A BREAKOUT -- and it is worth about +0.05 R, which is not
enough.** Gating a 20-bar breakout on trend quality lifts US30 5m from **-0.111 to +0.002** in
07:00-12:00 and -0.008 to +0.038 in 09:30-12:00, MONOTONE in gate strength and on a broad
robustness plateau (18 of 20 geometry cells positive). It still fails out of sample on US30 and NQ;
US100 survives at P(edge<=0) 25.8%. The filter closes the cost gap, it does not open one.
`research/scalp/regime.py` -- eleven causal measures, all oriented higher = trending.

**ADX AND THE EFFICIENCY RATIO ARE THE SAME FILTER (corr 0.642).** Stacking them cut US30 5m from
+0.0165/+0.0196 alone to +0.0102 together -- sample halved, no information added. A directional
+DI>-DI filter contributed nothing. One chop filter is the whole effect.

**07:00-09:00 IS THE WORST PART OF THE DAY ON ALL THREE INSTRUMENTS** (-0.18 to -0.43 R/trade),
and 10:00-11:00 is the only positive hour. Third independent confirmation on this branch. 09:00-09:30
also carries a 6-10% intrabar-ambiguity spike from the pre-open.

**THE OVERNIGHT MASK NEEDS BOTH ENDS.** Masking overnight aggregates to NaN before 07:00 is only
half the condition: FROM 18:00 THE NEXT OVERNIGHT HAS BEGUN, so an evening bar reads its own
still-forming group's running high/low/last-close -- future data. The truncation audit caught it on
US30 at bars stamped 18:30-23:15. Correct window is 07:00-18:00. No published result changed (all
prior work sits inside 07:00-11:00), but the audit earned its keep again.

**THE RIGHT NULL FOR A BREAKOUT SYSTEM IS THE SAME TRADE MANAGEMENT WITH A RANDOM ENTRY.** Turtle
(20/55-bar channel, 2xATR stop, 0.5N pyramid to 4 units) earns +0.595 R/trade on US100 240m; the
identical exits, stop, ladder and costs with a COIN-FLIP entry earn **+0.601**. Excess -0.005,
p 0.475, and no block on either instrument reaches p<0.05. Across 120 UNSELECTED grid points per
timeframe the median excess is +0.02 to +0.07, and daily bars are NEGATIVE on both instruments --
while the top of the same ~100k sweep is all daily. `turtle/core.run_random`. Ranking on research
expectancy bought 30-trade configurations, again.

**A TRAILING-STOP SYSTEM IS A DRIFT HARVESTER, so score it against the drift it is harvesting.**
The random-entry control earns **+0.586 R/trade where the index rose 247.6%** and **-0.005 where it
rose 49.6%**. That single fact explains why excess over the control GREW out of sample here: the
control weakened, not the rule. Before reading a trend system's excess, print what the control
earned per block next to the index move.

**BREAKOUTS PAY EARLY IN A TREND AND FAIL LATE, and ADX has the conventional sign backwards.**
Separating winning from losing Turtle trades at the SIGNAL bar: winners sit closer to the 50-bar
low (d -0.50), less extended above EMA100 (d -0.38), with LOWER slope and **LOWER ADX (21.3 vs
23.6)**. Gating on ADX<22 and re-simulating lifts US100 at 60/120/240m out of sample -- and makes
NQ worse at all three. Coherent, consistent on one instrument, non-transferring. Candle shape
separates nothing (`body_atr` d 0.014).

**COSTS SET A FLOOR ON THE WIN RATE, and at a scalping stop the floor is above 100%-ish.** On
US100 15m the round trip is a FIXED number of points, so the tighter the stop the larger it looms:
break-even at 1:1 needs **95.1% at a 0.25xATR stop, 71.5% at 0.5x, 61.9% at 1.0x, 54.8% at 2.5x**,
against base rates of 27-51%. Before searching for a win-rate target, compute the break-even the
geometry implies -- an 80%-at-1:1 brief is arithmetically dead at a 4-point stop and merely hard at
a 28-point one. `research/edgelab/analysis.stop_sweep` prints cost-in-R next to every row.

**A 15-MINUTE BAR CANNOT RESOLVE A TIGHT BARRIER PAIR.** When low<=stop and high>=target in the
same bar, OHLC cannot say which came first. Resolve it as a STOP always, and REPORT THE AMBIGUOUS
SHARE: it is **47.4% at a 0.25xATR stop**, 16.7% at 0.5x, 4.0% at 1.5x. Any sub-0.5xATR result on
this file is set by the tie-break, not by the market, whichever way it points.

**TRADES INSIDE ONE SESSION ARE NOT INDEPENDENT, and a bar-resampled control does not know that.**
Rules here fire 2-3 times a day on the same move, so 260 trades are ~101 days. Scoring bar-wise
made **17,121 of 27,786 tests "pass" BH at q=0.10** -- a symptom, not a discovery. `fast.score_days`
makes the DAY the unit and resamples days. And collapse near-duplicates by trade-set Jaccard: the
top 25 was one rule wearing 25 hats.

**A WALK-FORWARD IS CONTAMINATED IF THE THRESHOLDS WERE CHOSEN ON THE WHOLE TRAINING SPAN.** Rolling
folds inside the discovery block showed 5/6 positive at +0.33R; only the two folds that POSTDATE
threshold selection were meaningful, and they were the two weakest. Fold the search into the fold,
or read only the post-selection folds.

**PERMUTING TRADES CANNOT CHANGE THE ENDPOINT.** A Monte Carlo that reorders the realised sequence
answers a DRAWDOWN question only; reporting an endpoint distribution from it is meaningless (an
earlier version here printed a 5th-95th spread of 0.6R on +27R). Bootstrap WITH REPLACEMENT for
edge uncertainty, permute for path risk. `validate.monte_carlo` does both.

**THE TRUNCATION TEST IS THE ONLY HONEST LEAKAGE AUDIT.** Recompute every feature on history that
ENDS at bar i and require the value to match. It caught two real leaks here that inspection missed
-- overnight aggregates reading their own group's LAST close, and prev-day stats dropping out of a
groupby index. `research/edgelab/audit.py`.

**A second instrument on the SAME INDEX over the SAME CALENDAR is not a second test.** US100
2023-2025 gave the long-only trend rule +10.9 excess at p 0.0011 and it meant nothing: **68% of
NQ's triggers fire on the EXACT SAME 15-minute bar on US100** (79% within +-2 bars). It is the
same trades on a second data feed. Only US100 BEFORE 2022-12-26 is an independent test of anything
selected on NQ. `trend_long_xmkt.overlap()` measures this; run it before believing a cross-
instrument confirmation. See `docs/ib/STUDY_TREND_LONG.md`.

**A minute-of-day matched control is not VOLATILITY-matched, and an ADX filter exploits that.**
Swept on US100's unseen years the rule's excess climbed monotonically with ADX -- +2.2, +4.6,
+8.3, +10.6, +10.6 at 22/25/28/30/35, dollar excess to +$19.67 -- because the filter concentrates
trades in high-ATR bars while the control draws average-ATR bars at the same minutes, and a fixed
round turn is a smaller fraction of a wider barrier. Against the harder null -- **the REGIME
BASELINE, entering every eligible bar the regime admits** -- the same gradient adds +$15.50/trade
on US100's unseen years and **subtracts $29.65 on NQ's holdout**. It inverts hardest where it
looked best. Score a regime filter against the regime, not against the clock.

**NQ does not lead US100.** corr(NQ at t-k, US100 at t) is a clean spike at k=0 (0.8815) with
-0.022/+0.044/-0.015/+0.010 either side. At 15m the transfer is complete inside the bar.

**OUR NQ PRICE LEVELS ARE SYNTHETIC.** The stored series reads 13,915.8 on 2023-01-10 where the
real Nasdaq-100 was near 11,100 and US100 reads 11,184.6; the raw CSV carries it, so it is in the
source. The ratio decays smoothly 1.253 -> 1.036 (median 2 pts/day, ONE jump over 50 pts in three
years) so it is not roll back-adjustment. RETURNS are usable, LEVELS are not: percent-of-price
stops and ATR/price ratios are affected, and dollar magnitudes are inflated EARLY in the sample --
which is the research block, so correcting it makes the grew-on-locked flag larger, not smaller.
Win rates, R-multiples and ATR-unit measurements are unaffected. See `docs/ib/STUDY_US100.md`.

**Score against a matched control, not a population mean.** Random entries with the same side,
geometry and minute-of-day distribution price in drift, costs, barrier width and session timing at
once. `research/oner_anom.py`. And split net P&L by exit reason first: a 1R rule earning at the
TIME stop is a direction bet, not a barrier edge.

**A 5-minute engine cannot score a limit-entry strategy.** Re-running the selected NQ ATME
configuration against the TRUE 1-minute path left the fills identical (35.7% both ways) and cut the
result fivefold — research +0.331 R → **−0.003**, validation +0.340 → **+0.070** — purely from exit
ORDERING, which bar-level code resolves by rule and the minute path resolves by sequence. The
mechanic still beats a market entry on the same bars by +0.07/+0.16 R on both blocks, so the
finding holds; the LEVEL does not. Any barrier system whose stop and target sit inside one bar's
range has to be walked at a finer resolution before its number means anything. And note what the
perturbation Monte Carlo can and cannot say: P(mean ≤ 0) = 0 prices execution noise on the trades
you selected, never the selection. See `docs/ib/STUDY_ATME_LIVE.md`.

**THERE IS A FIFTH INSTRUMENT, AND IT IS THE FIRST ONE THAT CANNOT BE ACCUSED OF OVERLAP.** EURUSD
30-minute, 230,400 bars, **2003-07-21 to 2022-02-22** — it ends before NQ's sample begins, so not
one shared bar exists and the `STUDY_TREND_LONG.md` objection (68% of NQ's triggers firing on the
identical US100 bar) cannot be raised against it. Its clock was derived from FX's OWN anchors, all
three agreeing on NY+7 and all DST-stable: the weekly open (Sunday 17:00 NY) lands at file 00:00 in
964 of 984 weeks; tick volume bottoms at file hour 0 = the 17:00 rollover; and |30m return| peaks
at file 16 = 09:00 NY with the London/NY overlap at 14-17. A FIFTH export format — comma-separated
with an unnamed index column. `research/edgelab/fx.py`.

**THE SPREAD IS FLAT AND ATR IS WHAT MOVES — the cost model gets the right answer by the wrong
mechanism.** EURUSD is the first feed here carrying a MEASURED spread, and it falsifies the session
step: `Costs.spread_at` charges RTH/pre/off at ratios up to **3x**, and the real spread is **1.46 to
1.62 pips across all 24 hours**, a 10% range. But `spread/ATR` runs **0.073 at 10:00 NY to 0.139 at
22:00**, nearly 2x — entirely from the DENOMINATOR. Model a fixed spread over a varying ATR, not a
stepped spread. Two things survive: spread does NOT widen with bar speed (Q1 1.28, Q3 1.66, Q5 1.40
pips — an inverted U), so scaling slippage but not spread is right; and the assumed magnitudes were
about correct in ATR terms — measured break-even at 1:1 is **92.3% / 71.2% / 60.6% / 54.2%** at
0.25/0.5/1.0/2.5xATR against US100's assumed 95.1/71.5/61.9/54.8. That is the first empirical
support the scalping rejections have had. **Use `fx.usable_span()`, never the raw column** — a
quoted zero is a missing value and 2017/2020/2021/2022 run 25-88% zeros. See
`docs/ib/STUDY_SPREAD_TRUTH.md`.

**`research/datasets.py` IS THE DURABLE MEMORY OF THE DATA.** `data/*.csv` is git-ignored and does
not survive a container recycle; seven files, 382 MB, five distinct export formats, all arriving by
upload. The registry commits everything EXCEPT the bars — format, delimiter, column meanings, exact
row count and span, derived clock and its evidence, measured defects, owning loader, provenance and
a sha256 prefix. `python research/datasets.py` inventories and verifies, distinguishing MISSING from
SIZE MISMATCH from CONTENT MISMATCH so a re-uploaded file can be PROVED identical to the copy the
studies ran on. Run it first in any session that touches data.

**V1 IS THE ONLY RULE ON THIS BRANCH WITH THREE INDEPENDENT CONFIRMATIONS.** Run unchanged on
EURUSD 30m -- a DIFFERENT ASSET CLASS over a period sharing NOT ONE BAR with the NQ file -- it
scores **+0.0716 R excess over a minute-of-day matched control at p 0.000** on 1,501 trades, and
tripling the stop slippage moves it to +0.0736. Of the six 30-minute legs testable there, it is the
ONLY one to pass BH at 0.10. That is three footings: NQ (where it decays across the split, the right
shape), US100's nine unseen years (+9.2, p 0.0001) and now FX. **V2L does NOT transfer (p 0.367)
despite passing on US100** -- which retrospectively suggests its US100 pass owed something to being
the same index. M4 collapses to 98 trades at -0.103 R, as `STUDY_M4_ANATOMY.md` predicts of a day
filter. The qualification: V1's excess is positive in ALL FOUR EURUSD sub-periods but significant
only in the last two, and its P&L splits 57/43 between the barrier pair and the time exit. See
`docs/ib/STUDY_EURUSD_LEGS.md`.

## Tooling

| module | what it does |
| --- | --- |
| `research/test_suite.py` | 57-test battery on one strategy |
| `research/quant_brain.py` | features, regimes, metrics, improvement engine, portfolio |
| `research/alpha_factory2.py` | 16.2M strategy generator, 115 conditions |
| `research/vol_sizing.py` | the eight named volatility-sizing methods |
| `research/intrabar.py` | true 1-minute path execution modelling |
| `research/pine_export.py` | Pine strategy + indicator emitters |
| `research/pine_lint.py` | **run before shipping any Pine** — there is no compiler here |
| `research/alpha_ladder.py` | the 198-condition pool (83 threshold rungs), Pine attached |
| `research/oner_union.py` | threshold neighbourhoods and the trade-count / win-rate frontier |
| `research/oner_anom.py` | exit split, matched control, corner table, FDR slices |
| `research/volprofile.py` | session + developing volume profile, nodes, naked POCs |
| `research/auction.py` | 47 auction-theory conditions, all leakage-checked |
| `research/newsignals.py` | semivariance asymmetry and efficiency-flip signal families |
| `research/sam_pool.py` | 1,440 SAM conditions (2 estimators x 12 windows x 3 normalisations) |
| `research/sam_mega.py` | the 142,845,120-combination SAM-anchored sweep (5m/15m/30m) |
| `research/sam_phases.py` | its five phases, same gates as everything else |
| `research/features2.py` | microstructure, semivariance, auction feature families |
| `research/feature_eval.py` | IC with Newey-West + BH, redundancy clustering, trade separation |
| `research/features3.py` | spread/variance/order-flow-proxy/structure/session/anomaly families |
| `research/daily_trend.py` | causal daily trend states, keyed on the daily close timestamp |
| `research/pullback.py`, `pullback_search.py` | trend-following pullback family, direction dictated |
| `research/trendind.py` | Supertrend, Ichimoku, PSAR, Hull, KAMA, DEMA/TEMA, Vortex, Aroon, Heikin |
| `research/trendpool.py`, `trendpool_search.py` | the 5.7M-combination trend-pullback search |
| `research/limit_entry.py` | limit-order entries, bar-level and true 1-minute, with pessimism knobs |
| `research/allstrats.py` | the nine shipped strategies in one registry |
| `research/m4_anatomy.py` | why M4 is profitable: exit split, barrier sweep, day-vs-bar, bands |
| `research/ib_features.py` | causal Initial Balance day features, control-gated, FDR |
| `research/hpfilter.py` | HP trend, causal vs full-sample, and the leak between them |
| `research/ma_lag.py` | moving-average lag/smoothness, matched-lag equivalence, turn delay |
| `research/eurusd_legs.py`, `run_eurusd_legs.py` | the shipped 30m legs on EURUSD, matched control, BH |
| `research/datasets.py` | **the dataset registry** — every feed's format, clock, defects and checksum; `verify()` |
| `research/edgelab/fx.py` | EURUSD 30m: the fifth instrument, an independent era, and the measured spread |
| `research/edgelab/spread_truth.py` | what a real spread does against the three things the cost model assumes |
| `research/us100.py` | the second instrument: audit, NY timezone, NQ alignment, unseen split |
| `research/trend_long.py`, `trend_long_xmkt.py` | the long-only regime battery, and it on NQ + US100 with the overlap measured |
| `research/edgelab/` | the US100 morning-session lab: 101 causal features, triple-barrier labels, day-clustered control, purged walk-forward, `run_all.py` |
| `research/turtle/` | Turtle long-only, verified against a literal transliteration; random-entry control, ~100k sweep, entry gating |
| `research/scalp/` | intraday trend-following scalp on US30/US100/NQ: chop regime measures, cross-market, frozen rule |
| `research/hypo/` | the eight-hypothesis programme: library with rationales, full metric suite, robustness score, portfolio correlation |
| `research/atme/` | adaptive trade management: entry mechanics, trailing/breakeven stops, partials, mechanic isolation |
| `research/atme/livesim.py` | true 1-minute path re-simulation of a 5-minute config, plus perturbation Monte Carlo |
| `research/tune.py` | **the tuning loop** — `tune.py -i`, or one command; indicators/time/entry/TP/SL |
| `research/tuner.py` | its engine: cached exit tensor, rule language, `run` / `sweep` / `reveal` |
| `research/indpool.py` | 42 indicators with the PERIOD as an argument, memoised |
| `research/fastbars.py` | disk-cached bars; 4.5s -> 0.1s cold start |
| `research/costs.py` | itemised fees, broker presets, bar-dependent slippage; `real_costs.py` reports the damage |
| `src/lib/quant/tuner/` | the same tuner in TypeScript, running in the browser at `/quant/tune` |

## Pine

Three definitional traps, all of which have shipped broken once: ATR is `ta.ema(ta.tr(true), 14)`
not `ta.atr`; bare `hour`/`minute` are **exchange** time (Chicago for CME) not New York; CCI is on
`hlc3`. Entries require `barstate.isconfirmed` so the Strategy Tester's "Script execution"
checkboxes cannot change the result — without it, tick evaluation fires 5.1× as many signals with
80% on bars that never satisfied the rule.
