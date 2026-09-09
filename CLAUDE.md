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

**A BACKTEST'S FILL MODEL CAN TAKE ORDERS A SCRIPT CANNOT PLACE.** `eem.run`'s limit entry scans
forward from each signal in turn and fills at THAT signal's level, so a limit priced eight bars ago
outranks a nearer one priced since — eight simultaneous resting orders with the far one filling
first. A script has ONE live order. Re-measured with the implementable model the four V15 legs keep
**24–47%** of their R, while every trade the two models share is IDENTICAL (exit bar 100%,
correlation 1.0000) — so the bug is invisible in P&L-per-trade and shows only in the TRADE COUNT.
Of the three one-order policies, holding the order untouched beats re-pricing on every fresh signal
by 2x: "keep the order current" chases the market. This corrects every limit-entry figure in
`docs/ib/STUDY_V10_LIMIT.md` and `docs/ib/STUDY_V14_WINDOW_GRID.md`. Market orders are unaffected.
See `docs/ib/STUDY_V15_BOOK.md`.

**Clearing a matched control and clearing zero are different questions.** V15's shipped book beats
its minute-of-day-matched control on the judged block at p 0.010 — the control's MEDIAN outcome is
−10.9R, so random entries with that geometry lose — while a bootstrap of the same 81 days puts
P(mean daily R ≤ 0) at 0.073. Both are true. Report both; a short holdout can answer the first and
not the second.

**Prop targets are a distribution problem, not a strategy problem.** The V15 book's best risk level
by edge (0.25%: 25.5% pass, 12.8% bust) is also the one where **61.7% of 60-day runs end neither
passed nor busted**. Sized to survive, it grinds. Print P(neither) beside P(pass) or the table lies.

**A SESSION PREFERENCE DOES NOT TRANSFER BETWEEN STRATEGIES.** 09:30-11:00 New York, which
`STUDY_TREND_PULLBACK` preferred on a different instrument and family, is the WORST of seven windows
on V16 (+0.0705 research -> +0.0119 locked, control p 0.487). The only window better than all hours
on BOTH blocks is 08:00-12:00 (+0.1521 / +0.1872, locked control p 0.024) — and seven windows tested
corrects that to 0.168, so it ships OFF as a candidate. 13:00-16:00 has the best RESEARCH profit
factor in the table (1.423) and dies out of sample, which is the whole reason the table is read on
both blocks.

**A FIXED-TIME FLATTEN COSTS ABOUT HALF THE PER-TRADE EDGE** when there is no entry window
(+0.1033 -> +0.0481 locked on V16): it truncates exactly the trades a channel exit exists to hold.
It is roughly free inside a morning window, where the trade would have closed anyway. And it fills
at the NEXT BAR'S OPEN — `strategy.close_all()` cannot sell the close of the bar that triggers it —
so the engine was changed to match the script (`flat_open`), not the other way round.

**CHOP EARNS ITS PLACE, ADX DOES NOT, AND STACKING THEM MAKES THE HOLDOUT WORSE.** 110-cell
ADX x CHOP grid on the V20 base, five markets pooled in R. Against a random filter of the SAME
selectivity: every ADX floor fails both blocks (p 0.248 / 0.372 at 25, 0.736 / 0.269 at 40), while
CHOP clears all four rungs on research and **CHOP <= 45 clears both blocks (p 0.005 / 0.015)**.
ADX>=25 + CHOP<=35 scores p 0.215 on locked against CHOP<=35 alone at 0.083 — the stack is worse.
Mechanically: on breakout bars ADX >= 25 passes 55.6% against 50.0% of bars in general, a lift of
**1.11x**, while CHOP <= 40 passes 41.1% against 21.3%, a lift of **1.93x** — and 68.3% of the bars
CHOP keeps already pass ADX. The research-PF-to-locked-PF correlation across the 110 cells is
**+0.035**, so the top-20 ranking transferred only because CHOP did. See
`docs/ib/STUDY_V21_ADX_CHOP.md`.

**EVERY ENTRY WINDOW THAT STARTS AT 09:30 IS POOLED-POSITIVE AND EVERY ONE THAT STARTS EARLIER IS
NOT.** Seven windows x five markets on V20's locked block: all hours -0.0179, 07:00-11:00 -0.0078,
08:00-12:00 -0.0010, then 09:30-11:00 **+0.0345**, 09:30-12:00 +0.0187, 09:30-16:00 +0.0075,
13:00-16:00 +0.0161. The SHAPE is consistent and is the finding; the best single window is not — it
helps three markets and hurts two badly, and it is the best of seven. Consistent with the pre-open
block being subtractive on all three indices (`STUDY_TREND_PULLBACK`, `STUDY_INTRADAY_SESSION`).

**A LINEAR REGRESSION CANNOT CONFIRM A BREAKOUT, AND ITS MOST LITERAL READING IS BACKWARDS.** On a
breakout bar the 50-period regression's one-bar-ahead FORECAST is BELOW the current price **88% of
the time** (12.1% of breakout bars pass, against 50.5% of bars in general — lift **0.24x**), because
a breakout has just jumped above the range the line is fitted to. The reading that scores best,
`close > value`, passes **89.1%** of breakout bars and adds +0.005 R. Four declared readings x 5
markets x 2 timeframes = 40 cells; bootstrap p 0.41-0.97, every market negative at 1.5x spread.
Same mechanism as `STUDY_V16_MOMENTUM.md`. See `docs/ib/STUDY_V20_LINREG.md`.

**V17'S SESSION-HIGH FILTER DOES NOT GENERALISE, AND ITS US100 "CONFIRMATION" WAS THE SAME TRADES.**
Frozen and run on four markets that had no part in finding it: positive on ONE, and that one is the
Nasdaq. 59.9% of NQ's signal bars are also US100 signal bars at the IDENTICAL timestamp (83.6%
within two bars), and splitting US100 at the end of NQ's data collapses it +0.2952 -> +0.0334 R.
At 60 minutes drop-one shows the filter earns nothing and REMOVING it improves the rule
(+0.2511 -> +0.2554, control p 0.005 -> 0.001). See `docs/ib/STUDY_V19_DESTROY.md`.

**RUN THE ZERO-COST VARIANT BEFORE CONCLUDING THERE IS NO EDGE — AND THEN CHANGE THE BAR SIZE.** The
same rule is gross-POSITIVE on all four markets while the round turn is 8-11% of the stop on the
three that fail net against 3.1% on the one that does not. Cost-in-R and gross-edge-in-R both scale
with bar size, so the arithmetic is neutral and anything that moves NET is real: 15m -> 30m -> 60m
takes US30 from -0.0218 to +0.0663 to **+0.2511** and gold from -0.0117 to +0.1154, while INVERTING
on US100 — the market that duplicates the NQ trades the 15m result came from.

**SCORE A REGIME-CONDITIONAL RULE AGAINST A CONTROL DRAWN FROM THE SAME REGIME BARS.** A
minute-of-day control on 60-minute bars has about SEVEN minutes to match on, so it prices the clock
and not the direction — and three things said the 60m result was drift (the short mirror loses what
the long side wins, -0.165 against +0.251; the edge lives entirely above the 200-day, +0.2689 against
+0.0210; 3 of 9 walk-forward years negative). Restricted to the up state and scored against random
entries from THE SAME up-trend bars it still clears: US30 8.5yr p **0.004** (+0.192 R excess), gold
22yr p 0.032 (+0.095). Against the blunter baseline of EVERY eligible up-state bar with identical
geometry the breakout adds **+0.12 to +0.22 R per trade**. That is a drift harvester that beats its
own drift — worth trading, not an all-weather alpha, and it will not trade in a bear market.

**AND IT STILL DOES NOT CLEAR ITS OWN MULTIPLICITY.** The 60-minute timeframe was chosen AFTER
comparing three; roughly sixty looks were taken; Bonferroni needs ~0.0008 against a best p of 0.004.
Realised drawdown was LUCKY — MC median 22.4R against a realised 15.5, p99 **60.8R**. Size for p99.

**A 1.5xATR STOP AND A 2R TARGET ARE BOTH ON THE WRONG SIDE OF THEIR OWN MARGINAL CURVES.** 625
cells x 5 instruments: the stop axis is MONOTONE toward wider on every single market (pooled EV
-0.228 at 1.0N to -0.053 at 3.0N) and NO TAKE PROFIT beats every target for the sixth independent
time, taking 60-79% of the MAR top decile on four of five markets against a 20% population share.
The specified geometry is second-worst on the stop axis. Share of grid profitable FIRST: US30 0%,
US30L 2%, XAU 1%, NQ 45%, US100 66%. See `docs/ib/STUDY_V18_COINT_EWMAC.md`.

**CORRELATION NEAR 1 WITH NO COINTEGRATION MEANS THE LEVELS ARE WRONG, NOT THE MARKET.** US100 and
NQ are the same index — daily return correlation **0.9995** — and the pair does not cointegrate
(t -1.64). That is the smoothly drifting level ratio `STUDY_US100.md` already documents in our NQ
file. The positive control that proves the test works is US30 vs US30L: same instrument, two
providers, beta 0.994, half-life SIX bars. Always include a pair you know the answer to.

**READ A RESIDUAL COINTEGRATION TEST AGAINST MACKINNON'S EG VALUES (-3.90/-3.34/-3.04), NOT ADF's
(-3.43/-2.86/-2.57).** Testing a residual you ESTIMATED costs degrees of freedom. Run both
directions and believe only a pair that rejects both ways; on daily closes here NOTHING cointegrates,
so the 15-minute rejections were microstructure and sample size. And note the sign convention for a
trend follower: a cointegrated pair is BAD news — the spread reverts, so two cointegrated legs are
one bet wearing two names. Gold is the only independent series (rho 0.06-0.10, rolling correlation
below 0.5 in 97-99% of windows), and US30/US100 15m correlation itself ranges 0.019 to 0.971.

**A DAILY EWMAC(16,64) GATE ON AN INTRADAY BREAKOUT IS A COIN FLIP** — helps four of ten
instrument-block cells, hurts six, and hurts on both blocks of the 8.5-year US30 history.

**THE ONE ENGINEERED FEATURE THAT SURVIVED: a breakout must also be above the LAST COMPLETED RTH
SESSION'S HIGH.** On the V11 base (Donchian 55, ADX >= 25, 2.5N, 15m) it takes locked profit factor
1.308 -> **1.780**, Sharpe 1.05 -> **1.55** and drawdown 14.3R -> 9.0R, and it is what makes the
strategy clear a minute-of-day matched control it otherwise FAILS out of sample (base locked
p 0.213, filtered p 0.014). It is a LEVEL, not a trend: the prior session's CLOSE does nothing
(p 0.150) and every daily trend state tested does nothing (p 0.23 to 1.00). Bootstrap on locked
P(mean daily R <= 0) = 0.023. See `docs/ib/STUDY_V17_FEATURES.md`.

**Its pool was null, and it was carried on GRADIENT, not rank.** 285 conditions, 16 beat their
control at p <= 0.05 against 14.2 expected; on net R only 7 against 14.2. The condition shipped was
not the best cell — it was the only feature whose whole ladder was sign-consistent in BOTH
directions, and that gradient reproduced on the locked block. Bonferroni over 285 kills the
p-value; the replication of the gradient is the evidence, and it is one replication, not a result.

**COMPUTE SHARPE OVER EVERY TRADING DAY IN THE BLOCK, zero-filled on days that did not trade.** Over
traded days only, a filter is PAID for trading less: keep twelve days a year and the ratio explodes
while the account earns nothing. This is the choice that makes a selectivity search honest.

**`request.security` on a daily bar is NOT the session high.** It returns the 24-hour futures high.
A script that needs an RTH session level must accumulate it on its own bars and freeze it at the
session end — verified here identical to the tick against the 1-minute research construction.

**A MOMENTUM FILTER CANNOT IMPROVE A BREAKOUT, BECAUSE A BREAKOUT IS A MOMENTUM EVENT.** 2,167
conditions (58 scores x 366 rungs x 3 timeframes x 2 sides): 99 beat a same-selectivity control on
research against 37 expected by chance, and on the holdout only **28%** still beat the UNFILTERED
rule where chance is 50%; research-edge to locked-edge correlation **+0.107**. The mechanism is
measurable — **94.7% of breakout bars already pass an RSI(14) >= 55 filter** against 41.0% of bars
in general (lift 1.9-3.2x across every family), so the filter removes a twentieth of the sample and
adds nothing. Do not re-run momentum-on-breakout. See `docs/ib/STUDY_V16_MOMENTUM.md`.

**Volatility-scaling a past return is a CROSS-SECTIONAL fix and does nothing on one instrument.**
The commodity-futures literature is right that raw returns let the most volatile assets monopolise
the extreme buckets — but that is a ranking problem. Matched on trade count, `tsmom40` and `roc40`
are the same rule (PF 1.193 vs 1.188, Sharpe 1.01 vs 0.99).

**A plateau is necessary and not sufficient.** V16's best cell was rejected pre-holdout for having
no neighbourhood (rungs below it scored -1.2, +6.1, -1.1, -4.4). The rule carried forward instead
HAD a clean five-rung plateau (+12.8 to +52.6) and still failed the holdout. Coherence filters out
the obvious artefacts; it does not certify anything.

**On NQ 30m the plain Donchian 30/20 long breakout is the most block-stable thing measured here**
— +0.1126 R/trade on research against +0.1033 on locked, PF 1.19 both — **and it does not beat its
own minute-of-day matched control (p 0.16 on both blocks).** Consistency across blocks is not
evidence of edge; it can just as easily be a consistent exposure to drift. Always run the control.

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

**A moving-average entry tap is priced by its DISTANCE, not by the average.** KAMA 9 (and EMA 9/21,
SMA 20, Hull 9) as a pullback location on a Donchian breakout: score every tap against a BLIND LIMIT
resting the same number of ATRs from the signal close. Not one tap beat that on either block
(research p 0.162-0.985, locked p 0.047-0.686). The obvious control -- a random WAIT -- is rigged in
the tap's favour, because it fills at an OPEN while the tap fills at a LEVEL. And the tap loses to
just taking the trade: locked baseline +0.1387 R on all 275 breakouts against -0.0223 R on the 31%
that pull back to KAMA 9, even though the fill is 1.44 ATR cheaper. Same lesson as
`STUDY_LIMIT_ENTRY.md` from the other side. As a TRIGGER, KAMA 9 x EMA 50 is the best of twelve
crossovers on research (p 0.005, PF 1.48) and decays to p 0.258 / PF 1.07 with 87% of net P&L in the
top 1% of trades; over a 6x7 length grid the surface rises monotonically with the KAMA period, so
the 9 is not the mechanism. `docs/ib/STUDY_KAMA_ENTRY.md`.

**A COST IS A FRACTION OF RISK, NOT A NUMBER OF POINTS — and the 15m Turtle gate transfers.** On 15m
NQ the Turtle's ADX ceiling and EMA100 not-extended ceiling are both INVERTED: as floors (ADX>=20,
EMA distance >=3.0 ATR) plus a new ATR-expansion gate (>=1.10) and 3 units instead of 4, PF goes
0.94 -> 1.58 research and **1.56 holdout**. The three gates are near-independent (|rho| <= 0.23) and
counting them gives a monotone chop score (3/3 PF 1.58, 0/3 0.63). Frozen and applied to US30 and
XAUUSD -- markets that had no part in finding it -- both flip from negative to positive: pooled in
ATR-normalised units, baseline -0.0655 against improved **+0.1469** per trade over 17,073 vs 2,889
trades. **But the first cross-market run charged NQ's 1.72-point round turn in GOLD's points, which
is 54.2% of gold's 2N stop against 3.7% of NQ's**, and reported PF 0.35 as a decisive failure. Always
express cost as a fraction of the stop before comparing markets. Caveats that stay attached: NQ
holdout n=88 with a bootstrap of [-23.9, +140.7]; the EMA-distance ridge runs off the grid so 3.0 was
taken from the interior; the holdout's 2-of-3 bucket earned more than 3-of-3 and was left unacted;
gold is improved but straddles break-even; ES has never been supplied.
`docs/ib/STUDY_TURTLE_15M.md`, `research/turtle15/`.

**A published indicator stack can be a random entry, and the grid hides it.** Donchian 20 + EMA 50
+ ADX>20 + CHOP<40 with a 3xATR trail, on the 1-hour chart it is published for: **0 of 384 scorable
combinations** of its own 432-parameter grid beat a matched control at p<0.05, against 19 expected
by chance, and the median combination earns LESS than its control. Against selectivity-matched
random filters none of the three filters earns its keep and the full stack scores BELOW the raw
unfiltered breakout. What does carry is on FASTER charts (5m p 0.006, 30m p 0.026 on research) --
the opposite of the source's choice. But all five timeframes scored better on LOCKED than on
research, including two that failed research outright, so read that as a regime in the later block,
not a rule: 2024 supplies 78% of the 30m points with 2023 negative, and the top 1% of 5m trades
supply 171% of net P&L. **Every session-constrained variant fails out of sample** -- winners run a
median 2.1h against losers' 0.8h and overnight trades supply 338% of net P&L, so a 3xATR trail is
paid in the tail and a daily flatten cuts the tail off. `research/donchian/`,
`docs/ib/STUDY_DONCHIAN_ADX_CHOP.md`. Pine trap found here: `ta.dmi` returns `[+DI, -DI, ADX]`, so
destructuring the first element substitutes +DI for ADX silently.

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

**A Pine port cannot be asserted by reading it — diff it against the engine's order model.**
`TURTLE_4_FINALISTS` was transcribed line by line, read back twice, shipped lint-clean, and did not
compile: an `options` array continued at 16 spaces, and Pine reads any continuation indented by a
MULTIPLE OF 4 as a block body (`pine_lint` only checks a statement's first continuation line).
Three rules were also wrong, and `research/turtle15/pine_parity.py` — the shipped script's order
model in Python, run against the engine on the same bars — found all three: no exit order was live
during the ENTRY bar, which is 4.4-13.0% of trades averaging -33 to -118 points; the ladder placed
one rung per bar when the rung levels are deterministic and can all rest at once; and a signal could
fire on the bar a trade closed. Run the harness TWICE — with position scaling off, which is the
transcription check and must come back at correlation 0.99+, and as configured, which measures the
order-model gap. Here that gap is 1.5-2x the engine's points per trade with NO rule differing,
because the engine re-anchors the stop to each new fill WITHIN a bar and Pine cannot see a fill
until the bar closes. A better Strategy Tester number than the research is that gap, not an edge.
See `docs/ib/STUDY_PINE_PARITY.md`.

**A partial exit must not re-open the ladder — count units OPENED, not units live.** `eem.run`
gated its ladder on `size < max_units`; a partial reduces `size`, so the ladder re-opened a unit it
had just closed and trades finished at 1.5 units on a max_units=1 config. It inflated EVERY result
using a partial: config D 1.38/1.29 -> 1.10/0.95, the partial block's 1.14-1.19 "plateau" -> 0.82-1.02
(the bug applied uniformly, which is exactly why a flat improvement looked robust), and a prop
config from 1.87/1.62 to 1.12/0.98. Found by the parity harness, not by reading: target trades paid
+270.53 in the engine against the +133.48 the arithmetic demands. Corollary: **partial exits are
worth nothing here**, and a suspiciously FLAT improvement across a whole parameter block is a bug
signature, not a plateau. See `docs/ib/STUDY_V8_EXIT_OPT.md`.

**One unit is the prop answer; the ladder is what generates the drawdown.** Same rules, US30 15m:
three units run a max drawdown of 4,428 all-hours and 6,685 in a 07:00-10:00 window; one unit runs
1,488-1,573 for the same profit factor. Replicates `STUDY_TURTLE_15M`. And what binds a funded
evaluation is the RULE SET, not the strategy: under 30 days / 6% / 4% TRAILING nothing tested
passes, while 90 days with a STATIC 4% gives 39% pass against 12% bust at the same sizing.

**A limit-entry backtest on bar data measures intrabar ordering, not edge.** Three separate
artifacts, each worth a lot: filling at a bar's low and paying the target at the same bar's high;
the Donchian channel exit sitting ABOVE a limit fill so `max(ATR stop, channel)` fired instantly AT
A PROFIT (3,170 trades averaging +1.14, median hold ONE bar); and a sell stop resting above the
market, which is not a stop. Together they showed **Sharpe 11 on a rule-free every-bar test**.
Removing them gave ~6; the true 1-minute path (`limit_entry.run_1m`) gave ~2. ALWAYS settle a
limit-entry question on `run_1m`, never on the bars that decide the exits. Corollaries: a working
stop level must be capped at the close of the bar the order is placed on, and `through_ticks=4` --
the pessimism the module itself flags as mattering most -- turns out to cost only ~0.02 PF.
Note `limit_entry.py` still ships the OLD bare costs (COMM=1.00, broker-only); pass `cost_mult=1.44`
for the real MNQ stack. Its `trig` argument is a list of bar INDICES, not a boolean mask.
See `docs/ib/STUDY_V10_LIMIT.md`.

**The entry MECHANIC beat the entry SIGNAL again, on V9.** Same Donchian breakout, same ADX gate,
same ATR stop, market order swapped for a resting limit 0.75xATR(5) below the close: locked Sharpe
1.23 -> 1.57, $/trade +12.34 -> +24.44, research Sharpe 0.66 -> 3.81. And removing the Donchian
entirely scored BETTER on both blocks (locked 1.26/2.10 against 1.19/1.30) -- the trigger fails its
matched control at p 0.12-0.43. It is retained in the shipped script by user instruction, which
costs ~0.05 PF and ~0.4 Sharpe on locked and halves the trade count; recorded so the decision can be
revisited on evidence.

**A breakout finally beat its own random-entry control -- ADX>=25 and NO take profit did it.**
Donchian 55 + ADX>=25 + 2.5N stop + 20-bar channel exit + ONE unit + no target, market order at the
next open: matched control p 0.007 (+12.19 vs +2.32 for a random bar with identical geometry) and
selectivity control p 0.016. At ADX>=15 the SAME system fails at p 0.12-0.43, so the floor is the
mechanism, not decoration. Locked PF 1.29 / Sharpe 1.36 / +11.61 pts against V9's 1.17 / 1.23 /
+6.17. Perturbation moves PF by <=0.05 on every axis at +/-20%; bootstrap P(mean<=0) 0.0075; 5/6
walk-forward folds positive. Read a grid by its MARGINAL average per axis, not its top cell -- the
top cell is the max of 459 draws. Two cautions: drawdown TRIPLES out of sample (703 -> 2,044,
ret/DD 5.88 -> 1.01), and MC says the realised sequence was UNLUCKY (median 1,284, p95 2,033), so
size for the p99. NO TAKE PROFIT beat every target tested -- the third independent time on this
branch. See `docs/ib/STUDY_V11_MARKET.md`.

**Donchian 30/20 + ADX>=25 works on US100 and FAILS on the US30 it was fitted to.** 900 cells on
US30 train; read once on three held-back sets. US30 2026 PF 0.92 / Sharpe -0.53; US100 held back
1.42 / 2.01 with 6/6 walk-forward folds and bootstrap P(mean<=0) 0.0095; XAU flat (0.98 -> 1.19).
US100 chose nothing, so its block is a genuine pre-registered test -- and the instrument that DID
choose is the one that failed. The ADX filter is both the only thing that survived selection AND
the thing that inverts out of sample (US30 2026: ungated 1.04, ADX>=20 0.94, ADX>=25 0.92).
BOTH CONTROLS FAIL EVERYWHERE (breakout vs random bar p 0.06-0.29; ADX vs same-selectivity filter
p 0.14-0.58, and on US100 held-back a random filter earned MORE). The edge is the EXIT GEOMETRY --
2.0N stop, 20-bar channel exit, one unit, no target -- not the trigger. Compare STUDY_V11_MARKET:
the same family with Donchian **55** on NQ passes both gates at p 0.007/0.016, so channel length
decides whether the trigger carries information. Also: the ATR-expansion filter looks strong
(PF 1.42 -> 1.77) and is indistinguishable from a random filter of the same selectivity
(p 0.117-0.454) -- restrictiveness alone raises PF. XAU 5m arrives as semicolon CSV from 2004,
NY+7; 494,235 15m bars. See `docs/ib/STUDY_V12_DONCHIAN_3020.md`.

**A one-bar scalp is arithmetically dead here, and the IC says so before any rule is written.**
180 IC tests (Newey-West + BH) on nine years of US100: 22 survive, largest |IC| anywhere **0.0305**,
none reaches 0.05. Converted to points: at h=1 an IC of 0.03 is worth 0.39 pts against a 1.215-pt
round turn (0.32x); h=4 0.81 (0.67x); h=16 1.79 (1.48x). **You need IC >= 0.10 at h=1 to clear
costs.** And every price-vs-MA feature is MEAN-REVERTING at h=1 and ~zero at h=16, so an MA cross
carries no trend information at scalping range. Decile checks: ma_gap is non-monotone (D5 beats
D10), ADX and CHOP deciles are flat. See `docs/ib/STUDY_V13_MA_REGIME.md`.

**MA LENGTH is not a degree of freedom either.** 13/48 vs 12/48 vs 15/48, and 12/100 vs 12/90 vs
12/110, all land within 0.03 PF. What matters is that two pairs AGREE and that a regime filter is
on. Extends STUDY_MA_LAG from "MA type" to "MA length".

**A REGIME needs three independent readings; each one alone is worthless.** ADX>=25 as a standalone
trigger scores p 0.994 and CHOP<=50 scores p 0.990 -- the two worst rows in an 18-signal battery.
Required TOGETHER with an efficiency-ratio floor (ADX>=25 AND ER(20)>=0.30 AND CHOP14<=55) they take
a Donchian 30/20 breakout from PF 1.04 / p 0.690 to PF 1.24 / p 0.064 on research, and the
combination is positive on FIVE blocks across THREE asset classes and 22 years (US100 9yr research
1.24 and locked 1.46, US100-ISO 1.27, US30 1.26, XAU 1.14), 8/9 walk-forward folds, bootstrap
P(mean<=0) 0.0001. Watch the shape though: locked > research, which is the wrong direction.

**The short side was one bear market.** Short-as-specified loses on every block (p 0.65-0.96).
Short-INVERTED (fade a flush in an uptrend) looked significant on three equity blocks (p 0.003/
0.030/0.026) and is carried entirely by the 2021-10..2022-10 fold (PF 2.19, +33.80): 4/9 folds
elsewhere, bootstrap P(mean<=0) 0.099, and XAU PF 0.77 at p 1.000. Check WHICH FOLD carries a
result before believing it.

**Report the SHARE OF THE GRID that is profitable before reporting its top row.** A 1,290,240-cell
grid on 07:00-11:00 US30+US100 came back 58% profitable on BOTH instruments long and 44% short, so
the top of the ranking is the maximum of ~750,000 profitable draws. Row 1 showed PF 2.79/3.10 and
0.3% OF THE TOP 1000 STAYED PROFITABLE ON 2026 (0.0% kept PF>1.2, median 2026 PF 0.52). The short
side of the same grid held at 73.3%. Read what the TOP 1000 AGREE ON, never the best row. See
`docs/ib/STUDY_V14_WINDOW_GRID.md`.

**A cached exit tensor makes a million-cell grid cost one walk of the bars.** A trade's outcome
depends only on its SIGNAL BAR and its GEOMETRY, not on which indicator fired -- so walk the price
once per (bar, geometry) and every config becomes an array lookup plus a numba position-lock loop
over the signal bars only: **5.16M cells in 16 seconds** (`research/v14/v14tensor.py`). Verify it
before use: 16 geometries x 2 sides x 2 markets, exact trade counts and net within 1 point. The one
discrepancy found was the exit channel indexed a bar staler than eem.run, worth 0.20 pts/trade --
caught because the trade COUNT matched exactly while the net did not.

**In 07:00-11:00 the SHORT side works and it is mostly the ENTRY MECHANIC.** Same geometry, same
window, no indicator: a market order gives PF 0.77 on US30 train and a resting limit 0.75xATR(5)
gives 1.44; on US30 2026 it is 1.05 vs 1.43. Indicators add on top consistently (1.43 -> 1.82 on
US30 2026). Shorting a rally back UP into a resting limit is SELLING STRENGTH, which is why a short
book works here when "shorts lose by existing" holds everywhere else. Top-1000 consensus: ADX>=22
(80%), exit channel 25 (69%), limit entry (100%), stop 2.5N, TP 1.5-2R -- and MA mode OFF in 58%,
so the moving average is the LEAST important of the four components. CAVEAT THAT MATTERS: only 15m
bars exist for US30/US100, so this could NOT be settled on limit_entry.run_1m. A through-fill proxy
at 0.20N leaves all four cells positive (1.20-1.67) but that is reassurance, not proof.

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

**THERE IS A SIXTH INSTRUMENT, AND IT IS THE FIRST WHOSE CLOCK IS NOT A FIXED OFFSET.** BTCUSDT
15-minute, 295,882 bars 2017-12-31 to 2026-06-15, raw Binance klines (a SIXTH export format). Every
other feed here is a broker server that FOLLOWS US daylight saving, which is why -7h held year
round; BTC is stamped UTC, so winter prefers -5h and summer -4h against US30 (corr 0.1289 / 0.1625)
and `derive_offset`'s disagree-guard fires correctly for the first time. A true
UTC -> America/New_York CONVERSION scores each season's own best and 0.1337 pooled against 0.0908
for the best single shift. Three defects handled, not assumed: a MALFORMED FINAL ROW (empty
timestamps, prices present), 2 duplicate timestamps, and 14 bars with zero volume/trades/range
together -- an exchange outage. It is 24/7 (weekday counts flat 42,184-42,370), so every session
condition on this branch selects an arbitrary slice of a continuous tape. It also carries REAL
taker-side flow (`Taker buy base / Volume`, centred 0.4965) -- an actual order-flow imbalance, not
the proxy `features3.py` built. `research/edgelab/crypto.py`.

**BTC IS THE FIRST INSTRUMENT WHOSE COST IS NOT AN ASSUMPTION, AND THE COST KILLS THE GEOMETRY.**
Binance's 0.10%/side taker fee is published and exact; only 1bp of spread is assumed, 5% of the
total. All NINE shipped legs run there (the 15m source makes the 15m legs native and the 30m legs a
resample) and NONE transfers -- **every leg is NEGATIVE in absolute terms**. A 1xATR barrier on a
0.202% round turn needs **64.2-66.5%** to break even against actuals of 37-41%. **AND THE ZERO-COST
VARIANT INVERTS THE RANKING**, which is the warning: three legs pass BH WITH fees and none without,
because a minute-of-day control is not VOLATILITY-matched and a fixed percentage cost is a smaller
fraction of a wider barrier. Measured: M1's ATR ratio 1.20 and V4's 1.43 against V1's **1.01**, so
M1 and V4 are cost artifacts and V1 is not. V1 is again the best-behaved -- the only leg positive at
zero cost -- but misses BH at nine tests (p 0.020 vs a 0.011 threshold), so BTC is CONSISTENT with
V1, not a fourth confirmation. See `docs/ib/STUDY_BTC_LEGS.md`.

**A RANDOM ENTRY AT MATCHED RISK BEATS THE DONCHIAN BREAKOUT -- the third breakout to fail its own
control here.** The YouTube Turtle variant (20-bar entry, 10-bar stop, 4H 50 EMA filter, avoid
daily/weekly/monthly majors, 1R/2R/3R exits) scores +0.097 R out of sample on 1H, and a random
entry keeping every filter and exit scores **+0.197**. Excess is NEGATIVE in all four cells
(-0.031 to -0.100). Whatever it earns is the REGIME FILTER and the R:R GEOMETRY, not the channel.
**And the control had to be fixed first**: matching the exits is not enough, because the entry
determines the RISK -- a breakout bar sits at the top of its range so its channel stop is far
(median 0.693% of price on US30 60m) while a random bar's is near (0.372%, with 6.8% under a tenth
of the breakout median). The near-zero denominator made the first control print -2.08 R, which
FLATTERED the rule. **A control that flatters the thing it is tests is the one to distrust most.**
Match the risk distribution trade-for-trade, not just the exits. See
`docs/ib/STUDY_TURTLE_YOUTUBE.md`.

**SCORE A PROP-FIRM STRATEGY ON P(PASS), NOT EXPECTANCY, AND SWEEP THE RISK.** An evaluation is one
path with two absorbing barriers, so drawdown SHAPE decides it, not the mean. `research/vbt/prop.py`
models the trailing form -- target, a floor that ratchets up with equity highs and never comes back
down, a daily loss limit -- and reports P(pass)/P(bust)/P(timeout) separately, because "did not
fail" is not "passed". On the 1H candidate: P(pass) peaks at **48.1% at 0.50% risk**, falling to
30.1% at 1% and 16.8% at 2%, while 0.25% almost never busts and TIMES OUT 42% of the time. Risk per
trade is the dominant variable, not a preference.

**A CHANNEL STOP IS NOT A SAFE UNIT OF RISK, and it has now faked a result twice.** 110,250
configurations swept on the Turtle/regime family: the grid's own `ent=0` twin (same config, NO
breakout trigger) appears to show the trigger worth **+0.163 IS / +0.189 OOS**, helping in 89% of
88,200 pairs -- flatly contradicting the risk-matched control. The contradiction is the artifact:
`ent=0` enters at arbitrary bars where the channel stop is CLOSE, the R denominator collapses, and
adverse moves become huge multiples. Split by stop type, because an ATR stop CANNOT collapse:
channel +0.350/+0.417, **ATR +0.022/+0.018**. So **94% of the apparent contribution is the
denominator**, and the breakout is worth ~+0.02 R = nothing. Anything measured in R against a
channel stop must be re-checked with an ATR stop before it is believed.

**110,250 CONFIGURATIONS BOUGHT NOTHING.** Best in-sample config scores **+0.098 R out of sample
against the un-swept starting point's +0.097**. The top 0.1% is **100% long-only and 100% 5R
target** against population shares of 33% and 14% -- the sweep found the longest exposure to an
up-move in a sample where all six markets rose, which is drift, not a rule. Its neighbourhood is
unstable (rank 5 goes IS +0.424 -> OOS **-0.351**, one channel length from rank 3). And the
IS/OOS expectancy correlation of **+0.84** is NOT skill: it survives within geometry cells (+0.876)
because the same six markets rose in both blocks. See `docs/ib/STUDY_SWEEP_110K.md`.

**THE INTRADAY CONSTRAINT COSTS ~88% OF THE RESULT, and the 06:00 open is the worst part of it.**
Held to a 06:00-12:00 New York window with a HARD flat at 12:00, the best configuration scores
**+0.034 R OOS at PF 1.08**, against **+0.279 R at PF 1.35** for the same family allowed to hold for
days. Seventh independent confirmation. The mechanism is not cost: the exits fire on the CLOCK
rather than on the trade, so a 5R target mostly never arrives. **Moving the open from 06:00 to 09:30
raises OOS expectancy 35% on 38% fewer trades** (+0.034 -> +0.046, PF 1.08 -> 1.17) and IS PF
1.22 -> 1.44 -- the pre-open block is SUBTRACTIVE, and this replicates `STUDY_TREND_PULLBACK.md`'s
finding that 07:00-09:00 is the worst part of the day on all three indices. The cost model does not
widen the pre-RTH spread, so the real penalty is LARGER than measured. On 5-minute bars only 1.0% of
2,160 configurations are positive OOS, against 5.5% on 15-minute. See
`docs/ib/STUDY_INTRADAY_SESSION.md`.

**THE TAKE-PROFIT ON THE INTRADAY SYSTEM IS NEVER REACHED -- it is a stop-and-clock system wearing
a target.** 09:30-12:00 New York, 15m, 5R target: out of sample **0 of 1,027 trades reached it**;
15.1% stopped out and 84.9% were flattened on the clock. In-sample 5 of 1,651 (0.3%). The whole TP
axis is a PLATEAU from 1.5R to 5R (OOS +0.043 to +0.047, PF 1.16-1.18) and degrades sharply BELOW
1.5R (0.5R -> +0.014, PF 1.07) -- reassuring shape, but the plateau exists BECAUSE the target stops
binding: 7.9% reach 1.5R, 1.0% reach 3R, 0% reach 5R. **Setting 5R and setting "no target" are the
same strategy.** HEAT, out of sample: mean MAE **0.43 R** (p90 1.08), stopped trades 1.21 R because
price gaps through, flattened trades take only 0.29 R of heat but reach **+0.61 R of MFE** before
the clock closes them -- that give-back is the one actionable number. The few trades that ever
reached target drew down just **0.09 R**: on this sample a winner declares itself immediately.
Points per market (OOS risk / mean MAE): US30 204.8/81.9, US100 118.6/47.0, XAUUSD 19.6/6.1,
BTC 1172.3/472.6. See `docs/ib/STUDY_INTRADAY_HEAT.md`.

**A LABEL THAT COUNTS A TIMEOUT AS A LOSS MEASURES THE CLOCK, NOT THE MARKET.** Labelling a
session-flattened 1:1 trade as a loss made `min_to_close` separate **0.00% from 43.17%** and
volatility features 8.84% from 42.77% -- a bar near the flatten CANNOT reach the target and a fast
bar resolves before the bell, so anything that speeds resolution inflates the win rate. **64 of 117
features "passed" BH on a stopwatch.** Fix: drop bars with under 60 minutes of session left, and
label RESOLVED trades only.

**124 TURTLE FEATURES DO NOT GET NEAR 65% AT 1:1.** Corrected base rate **47.27%**, break-even
**58.36%** (1.0xATR stop, NQ 15m). Best single decile anywhere **58.25%** -- exactly the cost floor,
in-sample, post-selection. A sign-aligned composite of six independent features gives research top
decile 57.19% and **OOS 48.78%**, ten points BELOW break-even. 14 of 124 pass BH, 6 pass Bonferroni
at the effective count -- and 124 columns are only **47 principal components**. A KALMAN
local-level-plus-slope filter was added as a genuinely different estimator; its best feature ranks
23rd at p 0.045 and none survives correction. **Trend persistence predicts NEGATIVELY** here
(`dir_persist_20`, `ret24_consistency`, `slope_ema200_atr`, both Kalman slope features) -- the
seventh independent route to the same mean-reversion conclusion. Note also that a |rho| threshold
does NOT catch conceptual redundancy: five of six "independent" picks were all volatility level.
See `docs/ib/STUDY_TURTLE_FEATURES.md`.

**DIVERGENCE IS WORTH ABOUT ONE POINT, VOLUME SPIKES ARE NEGATIVE, AND THE STACKED GATES ARE NOISE.**
RSI and Stochastic bullish divergence as a confirmation entry on the intraday long 1:1 label
(base 46.45% OOS, break-even 58.36%): RSI alone **+0.67**, Stoch alone **+1.04**, both together
**+1.38** on 230 trades at p 0.362. Against the **+11.9 points** needed. RSI vs Stoch is a TIE that
flips across blocks (RSI better IS, Stoch better OOS) -- neither "works better". **VOLUME SPIKES
HURT LONGS, monotonically**: -2.45 points at 1.5x the time-of-day baseline, -17.88 at 2.0x. A spike
marks maximum participation, which is where a short-horizon move is most likely over -- consistent
with trend continuation being anti-predictive here. Stacking three filters at 1%/1%/13% firing rates
leaves **n=3**, and "100% win rate" on n=3 has a Clopper-Pearson lower bound of **29.2%**.

**DIVERGENCE MUST BE CONFIRMED-ONLY, AND THE AUDIT CAUGHT MY OWN SECOND LEAK.** A pivot low at bar i
needs bars i-k..i+k, so it is knowable at i+k, not i -- nearly every published divergence indicator
marks it at the pivot, which back-tests beautifully and cannot be traded. Worse, my `bars since
divergence` feature filled forward to the NEXT pivot's confirmation bar, so bar t knew when a future
pivot would confirm: the truncation audit read **+37 full against +999 truncated**. Fixed with a
plain forward scan. See `docs/ib/STUDY_DIVERGENCE_CONFIRM.md`.

**THE VIX FORECASTS THE SIZE OF THE NEXT MOVE AND NOT ITS STRAIGHTNESS.** Positive control first:
VIX vs forward realised vol scores IC **+0.63 research, +0.78 locked**, sign kept 91% -- the harness
is fine. Against a CHOP label the same 39 features give research-to-locked IC correlation
**-0.638**, a systematic sign INVERSION: 44 of 117 pass at alpha 0.05 against 6 expected, 29 survive
BH, and **21% keep their sign**; 7 of the top 50 do. The families with the LARGEST research IC keep
their sign LEAST (term structure proxy 0%, level 6%) while the volatility risk premium -- the one
column a price history cannot reproduce -- has a middling IC and the best stability (36%). Replicated
on NQ with 71 realised features: 426 IC tests give -0.047, and 2,556 control-gated trade conditions
give **-0.183**. A volatility reading does not tell you whether the next stretch trends.

**BUT HEAT IN ATR UNITS IS NOT FLAT, AND THAT IS A REAL SIZING ERROR.** Median MAE measured in ATR
units is **1.8-2.2x larger** in the LOW realised-volatility-percentile bucket than the high one --
NQ 15m locked 2.09 -> 1.24, NQ 30m locked 2.18 -> 0.98, monotone, stop-out 45.6% -> 31.5% -- and the
locked block reproduces the research slope value for value. The direction is the counter-intuitive
one: the ATR stop is BACKWARD-looking and volatility MEAN-REVERTS, so when vol sits low in its own
distribution ATR(14) has already contracted and a 2.0N stop is too SMALL. On SPX the VIX LEVEL is
flat across the same table (the ATR already scaled for it) while `VIX / realised20` roughly DOUBLES
heat from bottom quintile to top. Both instruments say one thing: heat is large exactly when forward
vol will exceed trailing vol. Ship: `stop = 2.5N if vol percentile <= 0.5 else 1.5N`. Locked PF
1.158 -> 1.249 (15m) and 1.156 -> 1.181 (30m); the NAIVE INVERSE is worse than flat on all six
cells, the threshold is a smooth plateau not a spike, and the exit mix moves 45% -> 18% stop-outs, so
it is not the R-denominator artifact that widening a stop always risks. It is a sizing correction on
an existing rule, not an edge. Caveats: 30m research POINTS fall while R rises; SPX daily leaves 8
locked trades after the position lock so nothing rests on that backtest; the SPX locked block
contains COVID; there is no VIX9D/VIX3M so the IMPLIED term structure was never testable.
Shipped as `pine/v22/V22_ADAPTIVE_VOL_STOP_strategy.pine`.
See `docs/ib/STUDY_V22_VOLATILITY.md`.

**V21'S CHOP FILTER DOES NOT SURVIVE ON THE ADAPTIVE-STOP BASE, AND IT IS NOT REDUNDANCY.** Re-tested
jointly on NQ: against a selectivity-matched control it scores 15m research p **0.037** then 15m
locked p **0.932** -- where a RANDOM filter of the same selectivity earns MORE -- and 30m 0.740 /
0.398. It passes once and inverts. The obvious explanation is wrong: correlation with the volatility
percentile over breakout signals is only **-0.230 / -0.258** and CHOP leans slightly AWAY from the
calm bucket (lift **0.85x / 0.88x**), so these are not two names for one filter. KEEP THE CAVEAT
ATTACHED: V21's result was POOLED OVER FIVE MARKETS on the FLAT-stop base and only NQ survived the
recycle, so this is one market on a different base -- CHOP is UNCONFIRMED here, not refuted, and it
ships as a default-off input rather than being deleted. The same re-test confirms the other two
V20/V21 components on evidence: linreg reading C is worth ~+0.005 R, and a 2R target is worse on
both timeframes and both blocks, which is the EIGHTH independent time no-take-profit has won. And
note the shape trap: on 30m the FULL STACK is the best locked cell in the table (+0.1105, PF 1.205)
while being far worse on 15m -- best-of-seven on one timeframe is not a finding.

**A STOP CAN ANCHOR TO THE SIGNAL BAR'S CLOSE, AND THAT IS WHAT LETS A SCRIPT PROTECT THE ENTRY
BAR.** The engine anchors to the ENTRY BAR'S OPEN, which no script can do -- at the moment the exit
order is written the fill price does not exist -- so placing the exit a bar late leaves the entry bar
naked (`STUDY_PINE_PARITY`: 4.4-13.0% of trades, -33 to -118 points). Anchoring to the signal close
is knowable at order time, so entry and exit go out together. Measured before adopting: **99.03% /
99.50% identical exit bars, R correlation 0.9935 / 0.9998**, locked PF 1.249 -> 1.241 and
1.181 -> 1.182. `research/v22/v22anchor.py`.

**AND PARITY CAUGHT THE BUG READING COULD NOT: an exit-bar marker updated BELOW the entry block.**
The first V22 draft was lint-clean and read correctly, and the stale `lastExitBar` let it re-enter on
the bar a trade closed -- **95 extra trades on 15m, 61 on 30m**, dragging script points per trade to
+0.92 against the engine's +4.31. Order the guard blocks so the exit is recorded BEFORE the entry
test runs on the same bar, and count `strategy.closedtrades` rather than watching
`strategy.position_size[1]`, which misses a trade that opens and stops out inside ONE bar. After the
fix: every series exact, **100.00% identical exit bars**, per-trade correlation 0.99997, and the only
residual is the round turn the engine nets and the harness does not.

**THE VIX CANNOT BE JOINED TO ANY FUTURES FEED HERE.** `data/VIX_daily.csv` ends 2021-12-31 and NQ
begins 2022-12-26 -- a 360-day gap, zero shared sessions. Its only partner on disk is
`data/SPX.csv` (2,226 overlapping sessions, 2012-01-03 to 2020-11-04). Every VIX number on this
branch is daily-scale evidence about the equity complex, transferred to intraday futures BY ANALOGY
and never by a join. What would unblock a real join: a VIX series covering 2022-2026, or a re-upload
of `US30_LONG_15m` / `US100_LONG_15m` / `XAU_ISO_15m`, whose spans do straddle 2012-2021.

**MOMENTUM DOES NOT ADD TO ADX OR CHOP EITHER -- CHOP ALONE IS THE ANSWER.** A declared 1,184-cell
grid on the V20 base (12 momentum readings x 3 rungs + OFF, x 4 ADX floors x 4 CHOP ceilings x 2
timeframes; 531 clear a 25-trade floor). **16 of 36 momentum settings beat the no-momentum baseline
on locked = 44%, chance is 50%** -- V16 reproducing on a different base. Against a same-selectivity
control on 30m: CHOP<=45 alone research p 0.000 -> **locked p 0.048**, the ONLY cell clearing both;
momentum alone 0.003 -> 0.750; ADX>=20 alone 0.417 -> 0.680; ADX+CHOP 0.345 -> 0.395; CHOP+momentum
0.022 -> 0.427. **Both additions destroy the one thing that worked.** On 15m the best momentum cell
goes research p 0.005 -> locked p **0.943**, where a random filter of the same selectivity beats it
94% of the time. THE PROOF OF REDUNDANCY IS IN THE GRID: every momentum reading at its ZERO rung
(`cmo14>=0`, `aroon21>=0`, `roc20>=0`, `tsmom20>=0`, `agree20_60>=0`) reproduces the no-momentum row
EXACTLY -- same 277/147 trades, same PF to three decimals. On a breakout bar they are not filters at
all; RSI>=55 removes **3.7%** of signals. And STACKING STARVES THE SAMPLE: 653 of 1,184 cells are
unscorable, 31 of the top 100 have ZERO locked trades, ADX>=30 vanishes entirely. Best readable cell
in the grid beats the no-momentum row by +0.047 PF on 4 fewer trades, which is noise and is the best
of 531. Grid population: 68.9% research PF>1, 54.9% locked, research-to-locked PF correlation +0.489,
top 100 mean research PF 1.369 against locked 1.163 -- that gap is the selection premium.
See `docs/ib/STUDY_V23_MOMENTUM_REGIME.md`.

**AN MA CROSSOVER ADDS NOTHING TO A DONCHIAN+CHOP BREAKOUT, AND THE ONLY GRADIENT IS LAG.** 1,016
declared cells (7 MA types x 9 pairs x 2 modes + off, x 4 CHOP x 2 timeframes) on the simplest base.
**442 of 988 MA cells beat their own same-CHOP same-timeframe no-MA baseline on locked = 45%, chance
is 50%**; mean locked PF change from adding an MA **+0.015**; research-to-locked PF correlation
**-0.097**. Type spread across all seven is **0.093 PF** and pair spread across all nine is **0.135**
-- and the apparent gradient with lag (SMA 1.208 down to TEMA 1.114) **DOES NOT SURVIVE
LAG-MATCHING and was withdrawn**: solve for the window giving each type the SAME lag and locked PF
goes 1.079 / 1.165 / 1.158 / 1.082 / 1.263 across lags 5/10/15/25/60, not monotone. **THE TYPE EFFECT
IS A SAMPLE-SIZE EFFECT** -- at matched lag the within-row spread across four types is **0.080 PF in
STATE mode (mean n 161) against 0.424 in CROSS mode (mean n 60)**, as low as 0.007 at the 4/10 row.
SMA and EMA need the IDENTICAL window at every target lag; DEMA, TEMA and KAMA cannot be lag-matched
at ANY lag, so they are a separate axis. What survives: the lag axis is **2.28x** the type axis, so
pick a lag and ignore the letter in front of it -- a restatement of `STUDY_MA_LAG` on a new base,
not an edge. HMA CROSS broken out on its own is the weakest family: **29 of 72 = 40%** beat baseline,
mean edge **-0.048 PF**. The 9/21 golden cross ranks
FIFTH OF NINE pairs. **A LOWER DRAWDOWN HERE IS JUST TRADING LESS**: adding an MA cuts locked
drawdown 4.6 R while keeping 68% of the trades, and no MA type reaches the no-MA baseline's
return/DD of 1.67. CROSS beats STATE on PF (1.182 vs 1.118) and drawdown (16.4 vs 23.0 R) on HALF
the trades (108 vs 222) -- the same artifact. Best research cell 15m `WMA 50/200 CROSS`+CHOP<=40
goes p 0.013 -> **locked PF 0.858, p 0.685**; the 30m best scores research PF **3.190 at p 0.000**
and cannot muster 30 locked trades. Top 40 mean research PF 1.623 -> locked 1.167. SHIP NOTHING: the
best configuration has no moving average in it -- **30m Donchian 30/20, 2.0N stop, no target,
CHOP<=40**, locked PF 1.318 / +0.1542 R / 11.6 R drawdown / ret-DD 1.67.
See `docs/ib/STUDY_V24_MA_CROSSOVER.md`.

**A LINEAR-REGRESSION 9/21 CROSS ADDS NOTHING EITHER, AND THE LAG TABLE PREDICTED IT.**
`ta.linreg(close,n,0)` fits a straight line exactly, so its RAMP LAG IS ZERO AT EVERY WINDOW -- it
sits with DEMA and TEMA, V24's worst two types. 484 declared cells (6 pairs x 5 readings x 4 R^2
floors + off, x 2 CHOP x 2 timeframes) on V24's winner: **197 of 478 beat their own baseline on
PROFIT FACTOR = 41%, and only 162 = 34% on SHARPE**, chance 50%, mean edge -0.048 PF and **-0.26
Sharpe**. Research-to-locked PF correlation **+0.025**. THE LITERAL ASK IS THE WORST READING: `9/21
VALUE cross` on 30m goes research PF 1.309 -> **locked 0.853 with Sharpe -0.43** (control p 0.880),
and on 15m 1.293 -> 0.858, Sharpe -0.52, p 0.917 -- against a baseline of 1.318 / +0.98. By reading,
the CROSS forms have the HIGHEST research PF (VALUE cross 1.181) and the LOWEST locked (1.021, Sharpe
0.02, 22% beat) while the STATE forms are neutral. **THE R-SQUARED GATE -- the one condition a moving
average cannot express -- IS MONOTONICALLY WRONG-WAY**: research PF rises 1.124 -> 1.141 with the
floor while locked PF falls 1.123 -> 1.088 and Sharpe 0.46 -> 0.27. 9/21 is the BEST of its six-pair
neighbourhood and still has a NEGATIVE mean edge (-0.026); pair spread is only 0.070 PF. Top 100 mean
research PF 1.299 -> locked 1.129 and Sharpe 0.70 -> 0.33, with 35/99 beating baseline PF and 28/99
beating its Sharpe. `9/21 SLOPE state` is the only cell above baseline on locked (1.370 / 1.08) and
it FAILS research at p 0.583 -- the wrong shape. Ship nothing.
See `docs/ib/STUDY_V25_LINREG_CROSS.md`.

**AN HMM READ THE STANDARD WAY IS A TWO-SIDED FILTER, AND THE MARKOV APPARATUS COLLAPSES TO THE STATE
LABEL.** Hand-rolled Gaussian HMM (Baum-Welch, validated on a simulated chain: means +0.796/-0.003/
-0.896 against true +0.8/0.0/-0.9; state accuracy SMOOTHED 97.5% vs FILTERED 93.8%). On NQ 30m as a
breakout gate: fit-on-all + smoothed decode gives locked PF **1.351**, the CAUSAL version of the same
model and rule gives **0.973** -- and the TRADE COUNTS ARE NEARLY IDENTICAL (194/194, 111/109), so
the leak is invisible in the count and shows only in which bars got labelled. A causal HMM needs BOTH
fixes: parameters from a block ending before the labelled bar, and the FILTERED posterior, never
smoothed or Viterbi. **AND THE FORECASTING MACHINERY IS A ROW LOOKUP**: 1/5/12/24-step
`p_bull - p_bear` each take exactly **3 distinct values over 35,701 bars**, the stationary
distribution takes **ONE**, and `state==Bull` vs `signal>0.3` has **Jaccard 1.0000** -- the same
filter wearing two names. Matrix powers add nothing to the state. As a directional gate in
07:00-11:00 NY on the Donchian+CHOP base, the regime is WORSE than no filter on locked in EVERY cell
with control p 0.95-1.00; the all-hours long goes research control p **0.00** -> locked **1.00**.
07:00-11:00 is worse than 09:30-11:00 on every comparable row, replicating STUDY_TREND_PULLBACK.
Fitted structure is stable across instruments though: NQ and US30 both give drifts ~+0.3/-0.24/+0.03,
diagonals ~0.94/0.94/0.91, and **Bull and Bear never transition directly** -- every change passes
through Sideways. See `docs/ib/STUDY_V27_HMM_REGIME.md`.

**MODEL CAPACITY IS MONOTONICALLY HARMFUL HERE, AND A GOOD CLASSIFIER CAN STILL DESTROY THE
STRATEGY.** 141 causal features at breakout signal bars, label = the R the trade actually earned,
PURGED+EMBARGOED walk-forward (overlapping trades make a naive K-fold train on the answer), every
model run again on SHUFFLED labels. AUC falls with depth in EVERY family: XGBoost d3 0.5603 -> d6
0.5347 -> d10 0.5233; MLP 2x64 0.5394 -> 4x128 0.5132 -> 6x256 **0.5060**, which is chance. The two
best models in the whole ladder are a REGULARISED RANDOM FOREST (0.5732) and LOGISTIC REGRESSION
(0.5585). **THE SHUFFLED TWIN IS MANDATORY**: the deepest net's shuffled twin earned **+0.2633** on
the headline "R top decile" statistic, more than any real model, which is how you learn that column
is noise. ON THE LOCKED BLOCK THE MARKETS DISAGREE: on NQ all nine models turn +0.0304 R NEGATIVE
(best -0.0028, worst -0.1194) while scoring AUC 0.52-0.58; on US30 all nine improve a -0.0090
baseline (best LightGBM +0.1275). **THE MECHANISM IS THE TAIL**: both markets show win rate rising
30-33% -> 36-39% exactly as trained, but NQ's p90 R FALLS 1.740 -> 1.340 while US30's HOLDS
1.872 -> 1.896. Train on win/lose and you get a win-rate optimiser; a breakout system earns in the
tail, so that objective is misaligned and whether it helps depends on whether the tail survives.
Read p90 of R in the selected set, not AUC. See `docs/ib/STUDY_V28_ML_CAPACITY.md`.

**THE US30 ML RESULT IS NOT CHOP, AND FORWARD CHOP IS NOT PREDICTABLE.** Two diagnostics settled
V28. First: CHOP14 <= median at the SAME 50% selectivity earns excess +0.0279 at **p 0.188** on US30
and **-0.1149 at p 0.988** on NQ, while the models earn +0.104 to +0.139 at **p 0.000** on US30 with
a Jaccard overlap of only **0.32-0.36** -- so the models select a substantially different half and
found something the one-line filter does not. Second: XGBoost on 74 volatility features + ADX fits
the FORWARD efficiency ratio at in-sample IC **0.41-0.70** and delivers locked IC **-0.017 to
+0.040**, AUC 0.49-0.52, and NEVER beats simply reading CHOP(14) today. CHOP describes the last 14
bars; nothing here forecasts the next 24. **ATR AS AN ENTRY REGIME FILTER IS ALSO NULL ON NQ**: 240
declared cells (4 families x parameters x 2 directions), only **4% clear a same-selectivity control
at p<=0.05 on either block against a 5% chance rate**, mean excess negative. On US30 25% clear on
research and 15% on locked, and exactly TWO cells survive both -- `atr_pct 500 <= 0.2` (research
+0.3682 p 0.003, locked +0.1611 PF 1.207 **p 0.003**) and its near-duplicate `atr_price 500 <= 0.2`
-- i.e. trade only when ATR sits in the bottom fifth of its own last 500 bars. Two survivors of 240
is what chance delivers at p<=0.05, and US30's locked baseline is NEGATIVE (-0.0139) so they rescue
a loser rather than improve a winner. Watch, do not trade. A published visual ledger of all sixteen
tested families lives at `docs/ib/verdict_ledger.html`.

**A GRADIENT BOOSTER FITS A PARAMETER SURFACE AT rho 0.96 AND PREDICTS THE HELD-OUT ONE AT 0.07.**
1,600 TPE (Bayesian) trials over 10 Turtle parameters, 07:00-11:00 New York with an 11:00 flatten,
both sides, two markets, research block only. **76-83% of the trial population is profitable on
research and 2-71% on locked** -- US30 long goes **83% -> 2%**. Rank (Spearman) transfer runs
+0.074 to +0.426, and PICKING THE TOP RESEARCH DECILE GIVES A NEGATIVE MEAN LOCKED SHARPE IN TWO OF
FOUR CELLS (-0.347, -0.780). The decisive test is the SURROGATE: XGBoost fits research at +0.906 to
**+0.960** and predicts locked at +0.049 to +0.445 -- a model with the capacity to find non-linear
structure found the research surface in full detail, and that detail does not survive the split.
**TWO OF FOUR OPTIMA CANNOT MUSTER 25 TRADES OUT OF SAMPLE**: optimising Sharpe in a hostile window
selects configurations that barely trade (NQ long best takes 48 of 377 available research signals).
The un-optimised baseline in that window is Sharpe **-2.2 to -3.8** on both sides of both markets,
the optimiser reaches +0.8/+1.2 on research, and the best locked result anywhere is US30 short at
Sharpe **+0.025** / PF 1.013 on 116 trades. A NEIGHBOURHOOD MEAN (best mean Sharpe over the 20
nearest trials) lands within 0.1 of the point optimum everywhere and rescues nothing. Run the
surrogate test before reading the top row of any future search.
See `docs/ib/STUDY_V30_BAYES_OPT.md`.

**THE MEAN OF EVERY RESULT ON THIS BRANCH IS +0.04 TO +0.08 R, AND NOT ONE ROW SEPARATES FROM IT.**
34 declared configurations -- the shipped rule, its regime ladder, six geometry axes, the five
rejected additions, four entry windows, the short mirror, the adaptive stop, four US30 rows -- each
given a day-block BOOTSTRAP for the edge and a PERMUTATION for the path. Equal-weighted the mean is
+0.0830 R research and +0.0846 locked; trade-weighted +0.0704 -> +0.0440. Both bootstraps exclude
zero. But **research-to-locked R correlation across the 32 shared rows is +0.215 Pearson / +0.088
Spearman**, and **all four rows the bootstrap called significant on research fail on locked** -- the
two STRONGEST of them (US30 base p 0.002, US30 CHOP<=40 p 0.007) INVERT to negative. Four passes
against 1.6 expected by chance is barely above the null, and research significance ran the wrong
way. The single row significant on locked failed research (p 0.215 -> 0.045), the WRONG SHAPE, for
the fourth time here. **THE WEIGHTING DECIDES THE SIGN OF THE DECAY**: equal-weighted the mean does
not decay at all (+0.0040) while trade-weighted it falls a third, entirely because US30 is 4 of 32
rows and a third of the locked trades. And the permutation splits the blocks cleanly -- mean
realised drawdown percentile **0.254 on research against 0.647 on locked** (share above the median
0.12 vs 0.69), so the research paths were smoother than a reshuffle of their own trades and the
locked paths rougher; locked MC p99 runs to **2.15x** the realised drawdown, which is the sizing
number. The edge belongs to the FAMILY, not to any choice made inside it.
See `docs/ib/STUDY_V31_MONTECARLO.md`.

**THE WIN RATE GOES UP 25-41% OUT OF SAMPLE AND SHARPE GOES DOWN, AND THAT IS THE WHOLE FINDING.**
43 new causal columns -- volume level against an expanding time-of-day baseline, ABSORPTION as
effort-without-result, EXHAUSTION as climax/wick-rejection/breakout-on-falling-volume, ANOMALY as a
joint outlier in (return, range, volume) plus the residual of the move on the participation, and a
flow proxy NAMED a proxy because no feed here carries bid/ask -- under XGBoost and LightGBM, purged
and embargoed, 240 scorable cells over 2 markets x 2 blocks x 2 objectives x 3 feature sets x 5
rungs. Trained on WIN/LOSE the ask is met and overshot: NQ locked **0.353 -> 0.441 (+25%,
control p 0.010)**, US30 locked **0.311 -> 0.440 (+41%, p 0.000)**, monotone in selectivity, 24-30
of 30 cells above baseline. **And Sharpe is LOWER than the unfiltered rule in three of the four
best cells** (NQ locked +0.21 against +0.45; the fourth is US30 locked where the baseline itself
loses), NO cell clears its control on PROFIT FACTOR on NQ, and Sharpe beats baseline in 2/30, 1/30,
2/30 and 14/30. **THE MECHANISM IS ISOLATED BY RUNNING BOTH OBJECTIVES ON THE SAME FOLDS**: trained
on win, p90 of R falls in ALL FOUR market-block cells (2.369->1.785, 1.788->1.558, 2.583->2.341,
2.069->1.696); trained on R it falls in NONE. **AND THE SHUFFLED-LABEL TWIN OUTSCORES THE REAL MODEL
IN 83 OF 120 RESEARCH CELLS (69%)** -- worst at the rungs that read best, real PF 1.433 against
shuffled 1.671. Above 50% means the noise floor is higher than the signal. Print p90 of R beside any
reported win-rate improvement on a breakout system. Note the prefix trap found here: `v22vol.build`
owns `vol.` for 71 VOLATILITY columns, so the volume family had to become `vlm.` or the
family-importance table credits volatility's weight to volume.
See `docs/ib/STUDY_V32_FLOW_ML.md`.

**A FULL OPTIMISATION PIPELINE RAISES OOS SHARPE 0.33 -> 1.13 AND STILL SHIPS NOTHING, BECAUSE THE
STATISTIC FAILS AT N=1.** 60/20/20 chronological split, ten parameter axes, **207,360**
configurations, objective 0.35 Sharpe + 0.30 PF + 0.20 return/DD + 0.15 neighbourhood robustness,
candidate taken as the CENTRE of the top-20 surviving region rather than its top row. US30 long
(60m Donchian 40/20, adaptive 2.5/1.5N stop, 2R, CHOP<=45, 09:30-16:00) reads OOS **PF 1.412,
Sharpe +1.13, DD 10.5R on 124 trades** against a baseline 1.118 / +0.33 / 24.7R, with stability
1.000 on every informative axis, 5/6 walk-forward folds and BOTH post-selection folds positive, and
PF still 1.019 at 3x costs. **THE DEFLATED SHARPE IS 0.0016 AGAINST 51,840 TRIALS -- AND 0.8101
AGAINST ONE.** Multiplicity is not what kills it; the observed +0.471 Sharpe on train+valid is not
significant before any correction, and positive skew (1.98) with kurtosis 11.3 makes it worse.
Report the DSR as a CURVE over assumed N, never one number, because the assumption is doing the
work. Two more things to carry: **TRAIN -> VALIDATION SHARPE RANK CORRELATION IS NEGATIVE IN ALL
FOUR CELLS** (-0.181, -0.330, -0.050, -0.375), the third independent measurement after V30's
surrogate (0.96 -> 0.07) and V31's cross-family (+0.215) that in-sample ranking carries no
information here; and the generalization gap is **POSITIVE** (+0.690 Sharpe), the wrong shape, for
the fifth time. Two objective defects worth not repeating: bounded normalisation that SATURATES at
1.000 cannot rank, and an ABSOLUTE trade floor admits 60m configs with 67 train trades and ZERO
validation trades -- use trades per year. And an axis that changes nothing must be excluded from a
stability score: `stop` is INERT whenever an adaptive vol policy is on, `adx_min` empties the sample
at 60m, and counting a flat line as four passing rungs is how a score reaches 1.000 measuring
nothing. Grid shape before its top row: PF>1 on train in 62.1% (US30 long), 2.2% (US30 short), 72.5%
(NQ long), 16.0% (NQ short). See `docs/ib/STUDY_V33_OPTIMIZER.md`.

**`limit_entry._walk_limit` HOLDS A BOOK OF RESTING ORDERS WHERE A SCRIPT HOLDS ONE, AND THAT WAS
THE WHOLE ENTRY-MECHANIC RESULT.** It assigns its position lock only on EXIT, so an order that is
resting and UNFILLED blocks nothing and trigger i+1 places its own while i's is still live. Counted:
on every-bar 5m signals a MEAN OF 2.45 orders are live at once with a maximum of 3 at `expiry=2`,
rising to a mean of 15.9 and a maximum of 19 at `expiry=18`, with more than one live **97.7%** of the
time. **THE SIGNATURE IS A RISING EDGE ON AN AXIS WHERE THE FILL RATE IS FLAT**: lengthening the
resting window leaves the fill rate at 0.139 from expiry 6 through 18 while $/signal climbs
-0.505 -> +0.228 -> +0.895 -> +1.400 -> +1.759 -> +2.115. Extra profit with no extra fills is the
engine choosing among orders it should not have had. The fix is ONE LINE -- an unfilled order holds
the lock until it expires -- and it deletes the effect: everybar 5m goes -0.022/+0.481/+0.748 to
**-0.127/-0.130/-0.192** at expiry 2/6/12, donch 5m +0.854/+2.285/+2.942 to **+0.335/+0.235/+0.019**,
and the monotone rise with resting time VANISHES. Trade count keeps 0.75-0.97, falling fastest where
concurrency was highest -- the same tell as `STUDY_V15_BOOK`. **THIS CORRECTS A MODULE THE BRANCH HAS
PUBLISHED FROM**: any figure in `STUDY_V10_LIMIT` or `STUDY_LIMIT_ENTRY` that let an order rest more
than a bar is inflated the same way, and `research/atme/`'s headline (+0.24 to +0.43 R/trade,
monotone in depth) is EXACTLY the shape this artifact produces and must be re-measured under a
one-order policy before it is relied on. On the corrected engine the pre-registered test fails on
every hypothesis: limit beats market in **17 of 32 cells on research (53%, chance is 50%)** and 18 of
32 on locked with a mean of **-0.515 $/signal**, depth is not monotone, research long **+0.351**
against short **-0.212** so it is drift not a mechanic, and research-to-locked Spearman is **+0.139**.
Score PER SIGNAL, never per trade: fills run 4-30%, and `donch 15m` long at depth 1.00 reads
**+$41.56 per trade** and **+$5.08 per signal**. `research/v34/v34one.py` is the corrected walker;
`limit_entry.py` is left untouched so earlier results stay reproducible.
See `docs/ib/STUDY_V34_MECHANIC.md`.

**THE INITIAL BALANCE IS A LEVEL PRICE IS ALREADY TOUCHING -- that is why it predicts direction and
why the prediction is worth nothing.** A booster on 25 causal window features predicts WHICH SIDE
BREAKS FIRST at **AUC 0.86** on a 0.495 base rate, which is far too high for a market prediction. It
is geometry: `f_close_pos` ALONE scores **0.8766**, beating the whole 25-feature model, and "the
high is nearer than the low" stated as pure arithmetic scores **0.8703** -- **the nearer edge breaks
first 78.6% of the time**. Dropping all seven position features only moves it to 0.822-0.833,
because when the extremes formed and the volume balance encode position indirectly. The median
distance from the window close to the edge that broke is **0.779 ATR**, so the level is already at
price, and break-trade R by that distance is NON-MONOTONE (+0.118, +0.278, -0.133, -0.076 by
quartile): 79% direction accuracy buys no edge. **THE 80% RULE IS NOT 80%** -- reversion is **0.937
across 38 window cells** (min 0.715, max 1.000), 0.969 for the classic IB, against **0.968 for
random same-length windows**, so breaks do not hold anywhere. **AND 09:30 IS NOT SPECIAL**: swept
over 11 starts x 4 lengths against 150 random same-length same-session controls each, **0 of 38
cells clear p<=0.05 on research where 1.9 are expected by chance**; the classic IB scores excess
+0.0314 at p 0.353. A coherent midday shape exists on research (windows ending 13:00-14:00 at
+0.063 to +0.090) and DOES NOT REPRODUCE: research-to-locked Spearman **+0.185**, sign kept
**0.447** -- worse than a coin flip -- and the top five research cells go +0.0895 -> -0.0113,
+0.0783 -> +0.0220, +0.0782 -> -0.0102, +0.0766 -> -0.0407, +0.0744 -> -0.0143. **EXTENSION IS
GOVERNED BY THE CLOCK, NOT THE WINDOW**: minutes remaining after the window correlate **+0.693 with
extension** and +0.518 with reversion, though only 0.094 R^2 with excess, and the tail effect is a
CLIFF below 90 minutes (-0.097) rather than a gradient. Do not re-run the Initial Balance in any
form. See `docs/ib/STUDY_V35_BALANCE.md`.

**THE LIQUIDITY-SWEEP -> IFVG REVERSAL HAS NO EDGE, AND TWO OF THE FINDINGS ARE MEASUREMENT ERRORS
OF MINE.** 1-minute NQ, four objective sweep definitions, the full FVG -> invalidation -> IFVG chain,
one live order, true 1-minute path, real MNQ costs. 5,400 declared cells: scored in R **1.4% clear
PF 1**, scored in dollars **16.1%**, and **ALL 24 MARGINAL AVERAGES ARE NEGATIVE IN BOTH UNITS**. The
best cell has no plateau (family mean -0.0067, entry edge +0.292 -> mid **-0.554** one step away) and
loses 84% of its edge on validation (+0.2510 -> -0.0064 over the top five). OOS was never opened
because nothing earned it.

**R IS NOT A SAFE UNIT WHEN THE STOP IS STRUCTURAL.** A stop beyond the sweep extreme can sit ticks
from entry: minimum risk **0.015 points**, 3.4% of trades under two points, and the smallest-risk
quintile reads **+0.6741 R while LOSING 1.41 points per trade**. Same failure as the channel stop in
`STUDY_SWEEP_110K` where 94% of the contribution was the denominator. It produced PF 7.332 and
R/trade +4.39 quartiles before it was caught. Score a structural-stop system in DOLLARS and report R
only as a diagnostic. Note the two units DISAGREE IN SIGN here and both are right: at one contract
the large-risk winners dominate, sized to constant risk the small-risk losers weigh equally -- so the
sizing rule decides the verdict, not the rule.

**A BEST-OF-N SUBGROUP SEARCH MUST BE SCORED AGAINST A NULL THAT ALSO TAKES ITS BEST OF N.** Reporting
the best of four quartiles per feature against a single-random-subset control gave **5 of 11 features
at p<=0.05 against 0.6 expected**. Under a null that shuffles, cuts into groups of the same sizes and
takes ITS best: **0 of 11**. The effective test count was 44, not 11.

Also: two causality leaks caught by the truncation audit BEFORE any result -- a session freeze in
wall-clock minutes handed evening bars NEXT-MORNING London levels (the trading day rolls at 18:00, so
freezes must be in minutes since the roll), and previous-day levels existed only if the current day
LATER had RTH bars. And a boosted quality score on 11 pre-entry features is null with the SHUFFLED
TWIN BEATING IT at the 25% and 10% keep rungs. Do not re-run this family.
See `docs/ib/STUDY_V36_SWEEP_IFVG.md`.

**THE IFVG MODEL'S OWN TIMEFRAME GRADIENT IS A COST GRADIENT.** The thread's model -- an
inversion aligned with order flow on M15 and M5, entered on the confirming M1 candle -- loses on
**0 of 32 declared cells** with a mean GROSS profit factor of **1.003**: a coin flip before a $4.78
round turn. Re-run at 5m and 15m entry with the barrier scaled to the entry timeframe's own ATR,
gross PF climbs monotonically 1.025 -> 1.053 -> **1.173** while the round turn stays flat at $4.7,
and the NET sign flips at 15 minutes (75% of cells profitable, best cell +13.71/trade clearing its
matched control at **p 0.005**). It is not an edge: the barrier grew, the edge did not. Out of
sample **0 of 16** 15-minute cells is profitable and the family mean goes +3.04 -> **-15.92**. Read
the ZERO-COST variant before believing a timeframe gradient. What DID replicate is order-flow
alignment itself -- +0.63 net, +0.63 gross, correct sign on both blocks and at every entry
timeframe -- and it is worth an order of magnitude less than the cost floor. The confirmation entry
is worth nothing. Order flow is made objective with NO new parameter, as the polarity of the most
recent inversion, which is the source's own definition ("disrespects bearish PD arrays" IS a
bullish inversion). See `docs/ib/STUDY_V37_IFVG_ORDERFLOW.md`.

**113,400 DONCHIAN x ATR x LINREG-MA x MA CELLS, AND EVERY AXIS INVERTS.** 92.5% of the grid is
profitable on research, so the top row is the max of ~105,000 profitable draws, and the
research-to-locked PF correlation is **-0.036 Pearson / +0.002 Spearman**. Top-100 mean research PF
**1.799 -> locked 0.978**. The best cell (30m Donchian 70/30, 2.5N, NO take profit, LRMA(50) both
readings, MA(250) with lrma>ma) reads research PF **1.909** and locked **0.907**. On all four
informative axes the setting research likes best is the one locked likes least, in exactly reversed
order: don_e 90 res 1.272/lock 1.035 against 15 at 1.129/1.093; lr_len 80 1.229/1.041 against 30 at
1.162/1.097; ma_read `lrma>ma` 1.250/1.061 against OFF at 1.140/1.072; stop 2.5N 1.250/1.056 against
1.0N at 1.131/1.097. **NO TAKE PROFIT is 91% of the top 100 against a 20% population share** -- the
ninth time, and the only axis whose research preference has ever held. Frozen and run on US30 and
US100, which had NO part in the search, it shows the `STUDY_V12_DONCHIAN_3020` shape -- **fails on
the market that chose it, holds on the ones that chose nothing** (US30 PF 1.324 over 551 trades,
US100 1.332 over 621, and the pre-2023 slices containing 2018/COVID/the 2022 bear are the BEST cells
at 1.364 and 1.386, 8 and 7 of 10 years positive). **AND 0 OF 8 CELLS CLEAR A MATCHED CONTROL
(p 0.077-0.382) AND 0 OF 8 CLEAR A SELECTIVITY CONTROL (p 0.090-0.554)**: the rule earns 2-3x a
random entry with the same geometry, consistently and in the right direction, and never at p<=0.05
-- while a RANDOM FILTER keeping the same number of breakout bars matches the LRMA/MA stack in every
cell. The exit geometry is the asset; the moving averages are not. A neighbourhood criterion
(best mean PF over +/-1 on every ordered axis) beat the top row on every fresh-market cell, so it
earns its keep. See `docs/ib/STUDY_V38_LINREG_GRID.md`.

**A SECOND ENGINE ON IDENTICAL SIGNALS PAID 2.1x MORE.** The V38 winner re-run in vectorbt 1.1.0
agrees on the SIGNAL SET (trade count ratio 0.92-0.94) and reports **+$256.25/trade against my
+$122.85** on US30 and +$67.37 against +$25.88 on US100. The entire gap is one convention: when a
stop and a channel exit fall inside the SAME bar, this branch takes the stop and vectorbt does not.
`STUDY_V10_LIMIT`'s lesson arriving through a different door -- any figure from a bar-level backtest
whose stop and exit can fall in one bar is a statement about the convention, not the edge. Run the
second engine as a TRANSCRIPTION check first (the count must match) and only then read the gap.

**THREE FEEDS RESTORED 2026-08-29 AND VERIFIED.** `US30_LONG_15m` sha256 **matches the registry
exactly** (24dcf2e1c7ba398f) so its bars are provably the studied copy; `US100_LONG_15m` matches on
row count and is now hashed (c449dddfbc06a943); the RTF unwraps to exactly the recorded 48,937 rows
and span, and its byte size is of the DERIVATIVE so rows+span are its identity, not bytes. All three
clocks re-derived independently: mean bar range peaks at minute-of-day 570 = 09:30 New York on every
one, with the ISO feed -- whose offset is STATED rather than derived -- agreeing, which is the
positive control. Cross-market validation is no longer blocked.

**A BOOTSTRAP MEAN THAT EXCLUDES ZERO IS NOT AN EDGE, AND 236 CELLS SAY SO.** 40 individual
indicator rules x 3 markets x 2 blocks on the shipped base (Donchian 30/20, 2.0N, no target, long),
each given a 1,000-draw day-block bootstrap, 1,000 permutations, and a 400-draw same-selectivity
control. Almost every rule reads a POSITIVE bootstrap mean -- NQ locked median **+$34.81/trade**,
30 of 40 with P(mean<=0) under 0.35 -- and **exactly 1 of 236 cells clears its control at p<=0.05
where 12 are expected by chance**, best p anywhere 0.087. It is ONE edge, the base geometry,
measured forty times: the unfiltered base itself reads +$17.31 research and +$37.65 locked on NQ.
CHOP is the best-behaved family and still does not clear (CHOP<=45 mean control p **0.178**,
CHOP<=40 **0.209** -- the two lowest in the table, positive on both blocks in all three markets),
which corroborates the shipped choice without proving it. **ADX GETS WORSE THE TIGHTER IT GETS AND
INVERTS**: >=20/25/30 runs +27.36/+20.75/+8.14 locked with control p 0.305/0.462/0.612, and on NQ
the two rules whose RESEARCH bootstrap excludes zero (ADX>=25 p 0.038, ADX>=30 p 0.050) both go
NEGATIVE on locked. **VOLATILITY-STATE RULES INVERT HARDEST**: calm +46.43 -> **-9.11** and ATR
contracting +31.56 -> **-20.44**, while their mirrors are top-five on locked -- which does not
refute V22, because where a STOP goes given heat is a different question from whether calm is a
profitable ENTRY filter. Every `close > MA` variant (SMA/EMA 50/100/200, linreg 9/21/50) lands in
+$19.69..+$25.89 with control p 0.377-0.502 on 1,050-1,150 of the base's ~1,160 trades -- they keep
99% of the signals and change nothing. Research-to-locked correlation is NEGATIVE in all three
markets (-0.516 / -0.036 / -0.205). **MC p99 drawdown is 1.7-2.2x the realised drawdown on every
cell** -- that is the sizing number and the most usable output here.
See `docs/ib/STUDY_V39_RULE_MONTECARLO.md`.

**A MOVING AVERAGE IS PRICED BY ITS DISTANCE, AND THAT IS THE ONLY FILTER OF SEVENTEEN THAT
EARNED A PLACE.** Donchian 40/25 long, MA(200) support, 07:00-11:00 NY with an 11:00 flatten, stop
swept: the base LOSES at every stop from 1.0N to 3.5N (PF 0.75-0.90, curve flat-to-falling, 15m
worse than 30m). 17 features in 8 declared concept families, each cut at two research quantiles and
scored against a same-selectivity control: **3 of 34 cells clear p<=0.05 against 1.7 expected, and
all three are the SAME family**. The survivor is `(close - MA200) / ATR`, top half of breakout bars,
p **0.017** -- NOT "close above the MA200", which is the base condition and worth nothing alone.
NQ research PF 0.903 -> 1.171 and locked 0.957 -> **1.208**. Restatement of `STUDY_KAMA_ENTRY` on a
new base. CAVEATS THAT STAY ATTACHED: bootstrap P(mean<=0) **0.300** on both blocks at n=46 locked;
realised locked drawdown $1,556 EXCEEDS the MC p99 of $1,457, so the path was unlucky and sizing
must exceed what is visible; helps US100 (1.055 -> 1.328) and does not rescue US30 (0.708 -> 0.757).

**A SESSION PREFERENCE DOES NOT TRANSFER, AND THIS TIME IT INVERTED THE OTHER WAY.** On the
Donchian 40/25 base, 09:30-11:00 is the **WORST** of seven windows (research PF 0.713 / locked
0.699, -$16.42 a trade) while 07:00-11:00 reads 0.903/0.957 and ALL HOURS WITH NO FLATTEN reads
**1.366 / 1.140**. The branch's standing finding -- 07:00-09:00 worst, a 09:30 start rescues an
intraday window -- is backwards here. The mechanism is the FLATTEN, not the start: a 40-bar entry
channel with a 25-bar exit needs room, and a four-hour box truncates exactly the trades the channel
exit exists to hold. The largest single improvement available to that strategy is switching the
session off.

**MEASURE FILTER CORRELATION ON THE SIGNAL BARS, AND PICK BY FAMILY BEFORE PICKING BY RHO.** A
filter only ever acts on the bars the base fires on, and family-first ordering is what stops a set
of picks that all pass a |rho| ceiling from being one idea (the recorded failure: five of six
"independent" picks were all volatility level). Doing it that way found **two EXACT duplicates in
this branch's own pool** -- `CHOP(14)` vs range efficiency at rho **1.0000**, because CHOP is
100*log10(sumTR/range)/log10(14), a monotone transform of range/sumTR; and close-position vs
upper-wick share at rho **1.0000**, because on an up bar one is the other minus one. Fourth time the
pool has been caught duplicating. Collapsing is CONSERVATIVE, so nothing published changes -- but a
drop-one test on a stack containing such a pair reports a filter contributing nothing when it was
never a second filter. See `docs/ib/STUDY_V40_INDEPENDENT_FILTERS.md`.

**AN EMA CROSS AS "FIRST SIGNAL" WITH A DONCHIAN "CONFIRMATION" IS WORTH EXACTLY NOTHING, AND THE
GRID ANTI-PREDICTS.** 103,680 nominal cells / **62,208 EFFECTIVE** (under mode `state` the
confirmation-window rungs are one cell -- an inert axis, and correcting against the nominal count
corrects for tests never run). The grid carries its own ablation: `cross` with win=0 IS the
Donchian-alone twin, giving 51,216 MATCHED PAIRS. Result: the EMA helps in 42.0% of pairs on
research and **50.0% on locked -- exactly chance** -- and the two modes invert in OPPOSITE
directions between blocks (`state` 63.5% research / 31.2% locked; `cross` 36.5% / 54.7%), which is
the signature of noise rather than of two mechanisms. Research-to-locked PF correlation
**-0.391 Pearson / -0.388 Spearman**, top-100 mean PF **2.781 -> 0.733**. 60m is the BEST research
marginal (1.374) and the WORST locked one (0.876) and the top 100 is 84% 60m. Cross-market on
US30/US100, which chose nothing: the EMA beats its own no-EMA twin in **3 of 6 cells where chance
is 3.0**, mean contribution **-$4.15/trade**, and the sign is decided by the MARKET -- it hurts in
all three US30 cells and helps in all three US100 cells. Walk-forward reads 5/6, 4/6 and 5/6 folds
positive and that is misleading: fold 5 is catastrophic in all three (PF 0.205/0.174/0.101) and
folds 5-6 are the recent block, so it is a decay curve wearing a robustness score.
See `docs/ib/STUDY_V41_EMA_DONCHIAN.md`.

**A CONFIRMATION THAT THE TRIGGER ALREADY IMPLIES CANNOT ADD ANYTHING -- measure the overlap first.**
EMA13 > EMA48 holds on **82.6% of Donchian breakout bars** against 36.9% of all bars (lift 2.24,
stable at 81.6% / 83.2% on 30m and 60m). So the state form removes a sixth of the signals and is
nearly free of information; only the RECENCY form is selective (a cross within 5 bars covers 16.8%
of breakouts, lift 3.64), which is why the top of the grid picks it exclusively. Same mechanism as
`STUDY_V16_MOMENTUM`'s 94.7% RSI pass rate. One cheap query before any sweep.

**THE INTRABAR STOP-VERSUS-EXIT CONVENTION IS WORTH UP TO 23x THE REPORTED EDGE ON HOURLY BARS.**
The V41 candidates re-run in vectorbt agree on the SIGNAL SET (trade-count ratio 0.92-1.00, one
cell exact at 130/130) and report **+$303.50/trade against my +$13.23** on US30 60m -- 22.9x --
and 2.5-3.0x on US100. The whole gap is that this branch takes the STOP when an ATR stop and a
channel exit fall in the same bar. V38 measured 2.1x for the same thing on 30-minute bars: **the
coarser the bar and the tighter the exit channel, the more of the "result" is the tie-break rule**.
Run the second engine as a TRANSCRIPTION check (the count must match) and read the gap as a
statement about the convention, never about the edge.

**A MILLION-CELL SEARCH FOUND GATE SETTINGS WHERE A COIN FLIP ALSO WORKS.** 1,843,200 nominal /
**1,152,000 EFFECTIVE** Turtle cells (the ladder is off whenever pyramid_step=0 OR max_units=1, so
7 of 16 (step, units) pairs collapse to one), scored by the **MEDIAN OF 8 WALK-FORWARD FOLDS**,
searched on US100 with US30 and NQ held back. **97.9% of the space is positive on that objective**
and 24.0% has all eight folds positive, so the best cell is the max of ~1.1M positive draws. The
three search-derived picks converge (240m, entry 40/40, exit2 30, 2.0N, pyr 0.25, 4 units) and
**ALL THREE FAIL their random-entry control on BOTH held-back markets (p 0.179-0.736)**, while the
un-searched preset the script already ships clears at **p 0.005 on all three**. THE MECHANISM IS IN
THE CONTROL COLUMN: a random entry in the population the SEARCHED gates admit earns **+0.68 to
+1.66 R/trade**, while in the population the SPEC's gates admit it **LOSES money on two of three
markets** (-0.285, -0.228, +0.111). The search did not find a trigger; it found a regime where
almost any entry works, and against that null the breakout has nothing left to add. Caveat: NQ is
25-56 trades and two picks produce NO scorable fold there at all.
See `docs/ib/STUDY_V42_TURTLE_MILLION.md`.

**A SURROGATE'S RANDOM-ROW CV IS INTERPOLATION ON A DENSE GRID -- HOLD OUT A WHOLE AXIS VALUE.**
The V42 surrogate reads in-sample R^2 **0.8765** and random-row 80/20 **0.8759** -- indistinguishable,
because every held-out cell has neighbours in training. Removing a whole axis VALUE from training
drops it to **0.3455 for timeframe**, 0.6488 for max_units, 0.7407 for the ATR multiple. Report the
by-axis number, not the random-row one: the first asks whether the model generalises to settings it
has not seen and the second asks whether it can interpolate between ones it has. Better than V30's
0.96-fits/0.07-predicts, and still not a forecaster.

**A CONTROL'S ENTRY RATE MUST BE n_target / ELIGIBLE BARS, NOT n_target / ALL BARS.** V42's first
random-entry control doubled the rate, which clustered the random entries, degraded the control and
made **every configuration clear at p 0.005**. It was caught only because `STUDY_TURTLE` measured
the ungated spec on the same market and timeframe at p 0.475 and the disagreement had to be
explained. `turtle/core.control` already had the right form. Fourth time a name-shadowing or
control-construction error has produced a too-good number here -- and `agg` as a DataFrame column
shadows `DataFrame.agg`, after `.first` and `.align`.

**A STOP CENSORS MAE, SO MEASURE ENTRY HEAT WITH THE STOP UNABLE TO BIND.** MAE is the right
statistic for how much heat an entry takes -- but a trade heading for -3.0 ATR that is stopped at
-2.0 records -2.0, so a mean MAE mixes real heat on survivors with the stop distance on the
stopped, weighted by a stop-out rate that runs **19% to 62%** across eight declared Donchian
configurations. Measured: the exit bar is **1.7% of MFE and 42.6% of MAE** (on a stopped trade it
is where the worst excursion happened, by construction) and **stop-out share correlates +0.978
with mean MAE**. Removing the exit bar is NOT the repair -- it discards real excursion. Widen the
stop until it cannot bind, or drop exits and read a FIXED HORIZON, and report in ATR AT ENTRY
never in R (R = atr_mult x ATR puts the stop back in the denominator: V40 at 1.5N is 8th of 8 on
MAE-in-R and 2nd on MAE-in-ATR). **The spread is LARGER uncensored than censored, 1.534 ATR against
0.779** -- the stop was compressing the differences between entries, not creating them, and V40
goes from mid-table as declared to the worst entry in the set. Against random bars in the same
regime at a fixed 20-bar horizon, **seven of eight breakouts take MORE adverse excursion**
(+0.18 to +0.87 ATR, p 0.83-1.00) -- a breakout enters at the top of its own range, the same
mechanism `research/atme/` found from the other side. They get more MFE too, so the ratio decides:
the UNFILTERED base scores **+0.002** against its control while every regime-filtered configuration
scores **+0.073 to +0.096**, and V40/V38 are negative. The trigger alone is nothing; the filter is
what makes it worth taking, which is STUDY_V21 reached from the excursion side. Lowest heat of any
tradeable configuration is the SHIPPED CHOP<=40 (2.449 uncensored / 2.990 at h20), below the base
it is built on. See `docs/ib/STUDY_V43_MAE_MFE.md`.

**MAXIMISING MFE AND MINIMISING MAE ARE THE SAME AXIS WITH OPPOSITE SIGNS, AND THE MAE RANKING
INVERTS ON THE UNIT.** 36 causal features (truncation-audit clean), NQ 5m/15m, 07:00-11:00 NY, long.
Across 78 cells the correlation between a cell's mean MFE and its mean MAE is **+0.617 to +0.945
Pearson**, and at a 90-minute horizon THREE OF FOUR features appear in BOTH top-4 lists in OPPOSITE
directions (`atr_pct250`, `atr_ratio`, `range_exp` wanted LOW for high MFE and HIGH for low MAE).
Worse, `vol.atr_pct250 high` has the LOWEST MAE of all 78 cells in ATR (1.63) and one of the HIGHEST
in POINTS (41.77) -- its ATR is 24.5 points against a 12-15 baseline, so "low MAE in ATR" is just a
HIGH-ATR BAR. **Report both units; the ratio MFE/MAE is the only one of the three where the ATR
denominator cancels.** Built on the ratio, four features per timeframe picked family-first
(max |rho| 0.414 / 0.701) and combined as a count, walked on the TRUE 1-MINUTE path: the no-filter
ABLATION is PF **0.865 / 0.903** -- 07:00-11:00 loses before any feature is applied -- and the stack
reaches 1.181 / 1.151 on research then **INVERTS on locked (PF 0.555 / 0.798, -6.25 / -4.51 pts a
trade), LOSING MORE THAN ITS OWN RANDOM CONTROL**. Barrier marginals are monotone toward wider on
both axes with the best setting at the GRID EDGE. Ships nothing. **What replicates is the TIMING: a
stop arrives about TWICE AS FAST AS A TARGET in all four cells and on both blocks** (5m 19 vs 38 min,
locked 25 vs 46; 15m 63 vs 76, locked 53 vs 110) -- a capital-efficiency fact, not an edge. And a
09:30-11:00 window flattened at 11:00 is structurally broken: **0 of 169 trades reached a 2R target
and 90-93% were flattened**, median time-to-flatten ZERO minutes. See
`docs/ib/STUDY_V44_SCALP_FEATURES.md`.

**MFE/MAE CANNOT ENGINEER A SCALPING TAKE PROFIT, AND THE REASON IS A BOUND, NOT A BACKTEST.**
P(MFE >= T) is an UPPER bound on the target-hit rate, never a win rate: the excursions record
whether each barrier was reached, never WHICH CAME FIRST. The distributions give a bracket --
p_lower = P(MFE>=T AND MAE<S), p_upper = P(MFE>=T) -- and the realised hit rate lands inside it in
**49 of 49** cells, so the theory is right. It is also nearly empty where a scalp lives: mean
bracket width **0.666 at a 0.5 ATR stop** against 0.167 at 3.0 ATR, narrowing monotonically as
barriers widen. Two corrections that bit here: the bound is on the TARGET-HIT rate, not the
PROFITABLE rate (a trade flattened in profit never touched the target, so the profitable rate can
legitimately exceed p_upper), and the two-outcome break-even p* = (S+C)/(T+S) is only valid where
the FLATTEN SHARE is small -- 1.4-5.0% at 0.5 ATR but **36.2%** at 3.0 ATR/5R. In practice, 7 stops
x 7 targets x 2 timeframes x 2 blocks on the unfiltered 07:00-11:00 population: **0 of 49
profitable on three blocks** and 1 of 49 on the fourth, every marginal average negative on every
axis, and **the target-hit rate below its own break-even in 196 of 196 cells** (mean shortfall
-0.088 to -0.118). THE TAKE PROFIT IS DOWNSTREAM OF THE ENTRY and that is now arithmetic, not
opinion. What it would take: **+36.0% relative lift in the target-hit rate; the best of 78 feature
cells delivers +28.9%**, so the pool's best filter covers 80% of the gap and stops. The single
candidate (`loc.d_ema200` top quintile, 0.75 ATR stop, 5R) beats its matched control on BOTH blocks
(p 0.067 / 0.253) and is unprofitable on both -- PF 1.000 research, 0.868 locked. And the position
lock is not cosmetic: the same cell reads 1.073 / +0.60 pts unlocked and 1.000 / -0.001 locked.
Timing sharpens as the stop tightens -- at 0.75 ATR a stop resolves in **6 minutes** against 32 for
a target, **5.3x**, against 2x at 1.5 ATR in STUDY_V44. See `docs/ib/STUDY_V45_TP_ENGINEERING.md`.

**CARVER'S BREAKOUT IS PROFITABLE ON EVERY MARKET AND LOSES TO A COIN FLIP ON NQ.** 999,717 of
1,036,800 declared cells (3 tf x 8 spans x 3 smoothings x 4 forecast exits x 5 stops x 5 targets x
3 holds x 6 entry thresholds x 2 modes x 4 chop ceilings), searched on US100 research only, US30 and
NQ held back, objective the MEDIAN of 8 walk-forward folds. Implementation verified against Carver's
own design target -- he scales so mean |forecast| ~ 10 and it measures **10.70-12.16** -- and the
truncation audit is clean at every span. **61.3% of the grid is profitable and 0.00% has all eight
folds positive.** Both frozen configurations are profitable on all four blocks INCLUDING the two
markets they never saw (PF 1.16-1.74) and **7 of 8 fail a random-entry control**; on NQ the random
entry EARNS MORE in both (+82.10 vs +20.34, +78.00 vs +55.43), and the control makes +40 to +82
points a trade on its own -- with a 3.0 ATR stop, no target and a 480-bar hold on markets that rose,
a coin flip is profitable. STUDY_TURTLE's drift-harvester finding on a different indicator. The
day-block bootstrap DOES exclude zero in three cells (0.009-0.044), which is the other question and
both are reported. Marginals: monotone to 60m, to a 3.0 ATR stop and to a 480-bar hold -- **three
axes at the GRID EDGE** -- NO TAKE PROFIT best for the **tenth** time, the forecast EXIT worthless,
CHOP off best, cross beating state. Top-1000 mean folds-positive 4.3/8 on 132 trades against the
grid's 1,825, so the ranking buys low-count cells again. **THE ONE DURABLE FINDING IS ABOUT CARVER:
his published span range 10-320 BRACKETS the optimum and span 5 -- faster than anything he publishes
-- is the ONLY NEGATIVE ROW** (PF 0.952), confirming his own caveat that fast breakouts are eaten by
costs. **AND THE vectorbt CROSS-CHECK FAILED TRANSCRIPTION AND IS REPORTED AS INCONCLUSIVE**: count
ratios 0.12-0.98, and with stops disabled it still gave 24 trades to my 165, so it is the EXITS --
`sl_stop` is a FRACTION OF PRICE while the stop here is a per-trade ATR multiple, and `td_stop` does
not exist in 1.1.0. No gap is read from it in either direction. MC p99 drawdown is 1.1-2.2x realised.
Ships nothing. See `docs/ib/STUDY_V46_CARVER.md`.

**PEAD IS NOT MEASURABLE ON THIS DATA AND THE TREND PREMIUM IS INVERTED.** Post-earnings
announcement drift is defined on SINGLE NAMES -- SUE from actual-vs-consensus EPS, drift over ~60
days -- and needs earnings dates, analyst consensus and per-stock returns. None exist here. What can
be tested is an INDEX-LEVEL ANALOGUE of the mechanism with the event identified endogenously from a
standardised move. Likewise most classical risk premia need a cross-section or a bond curve, and
**the variance risk premium needs IMPLIED vol, which no feed here carries** -- a realised variance
term structure is a proxy and must not be called the VRP. 30 causal daily features, 763 NQ sessions,
truncation-audit clean. **NOTHING SURVIVES BH**: over 120 tests the threshold is |t| >= 3.35 and the
best achieved is 2.50. THE OVERLAP CORRECTION IS THE STORY -- Newey-West at lag h deflates the naive
t by **1.9x to 3.2x**, so an IC of 0.31 that looks like t = -6.8 is t = -2.3; every "significant"
daily-horizon IC is manufactured by ignoring it. What replicates is the SIGN, and only for one
family: 56/80 risk-premium tests keep their sign on locked (p 0.0005) against **22/40 for the PEAD
family (p 0.636, exactly chance)**. **THE CLASSICAL TIME-SERIES MOMENTUM PREMIUM IS REVERSAL ON NQ**
-- 11 of 12 momentum cells negative on BOTH blocks and tsmom120 MONOTONE IN HORIZON on both
(research -0.112/-0.192/-0.246/-0.305, locked -0.070/-0.121/-0.212/-0.271). Eighth independent route
to mean reversion on this branch. The PEAD analogue's shape is SHORT-HORIZON CONTINUATION AND
LONG-HORIZON REVERSAL -- overreaction, the opposite of PEAD at the horizon PEAD is defined on -- and
not one cell reaches |t| >= 2 on both blocks. **THE NIGHT PREMIUM DOES NOT REPLICATE**: intraday
contributed MORE in total (+0.357 vs +0.292 log) and overnight wins only risk-adjusted, by 0.07
Sharpe. Turn of month, the one declared calendar hypothesis, fails at every horizon. Note the
binomial p on sign agreement OVERSTATES -- the 120 tests are not independent. See
`docs/ib/STUDY_V47_RISK_PREMIA_PEAD.md`.

**THE BREAKOUT'S OWN CONTEXT CARRIES NOTHING; THE RISK-PREMIUM / PEAD / RELEASE-CLOCK MATERIAL
CARRIES EVERYTHING -- AND NONE OF IT SURVIVES.** 39 causal features on a Donchian 30/20 base
(2.0N stop, channel exit, one unit, no target, long), searched on US100 with US30 held back, scored
with PURGED EMBARGOED CV because a trade occupies [signal, exit] and those windows OVERLAP -- a
naive time split leaks. Family ablation on US100 15m: **`bo only` (excess over channel, channel
width, ADX, CHOP, close position) scores CV IC -0.0784 at p 0.307**, and DROPPING IT IMPROVES THE
MODEL (+0.087 -> **+0.117** IC, lift +0.152, p 0.000). Coefficient mass rp 45.0% / pead 27.2% /
news 19.9% / **bo 7.9%**. So if a filter exists for this base it is in that material and not in the
channel. **But nothing clears a same-selectivity control on BOTH holdouts**: best locked p 0.117,
and **PEAD-only goes NEGATIVE on the unseen market** (-0.0434, p 0.891), the second study running to
find the PEAD family worthless. **THE NEURAL NETWORK LOSES TO RIDGE ON EVERY TIMEFRAME** -- OOF IC
+0.020 against +0.087 at 15m and NEGATIVE at 30m (-0.055) and 60m (-0.074). With 506-2,207 trades
against 39 features the net memorises and the linear model wins; deep learning bought nothing.
Only 15m is coherent (CV/locked/unseen IC +0.087/+0.086/+0.073, p 0.099/0.144); 30m fails its
holdout; **60m is negative for ALL THREE MODELS on research and then "passes" out of sample, the
wrong shape**. Largest coefficients: `rp.tsmom960_vs` **-0.19** (momentum negative again, NINTH
route to mean reversion here) and `news.in_window` -0.17. That second one is interpretable so it was
tested WITHOUT the model: breakouts inside a declared release window are worse in **6 of 6 US100
cells** and **INVERT on US30** (30m +0.2296 research, +0.2555 locked) -- 8 of 12 overall against 6
expected, 1 of 12 at p<=0.05 against 0.6. A market-specific artifact. **NO NEWS FEED IS ATTACHED AND
NONE WAS SCRAPED**: the 08:30/10:00/14:00 New York release windows are DECLARED, fixed, never
searched, and identify WHEN a release could land, never which or what it said -- a real release
calendar with surprise values is worth more than any further modelling. See
`docs/ib/STUDY_V48_ML_BREAKOUT_FILTER.md`.

**ADVERSE SELECTION ON A RESTING LIMIT GROWS WITH THE SIGNAL'S IMMEDIACY — CONFIRMED — AND AN EQUAL
AND OPPOSITE FORCE IN THE EXIT PATH CANCELS IT.** V49's post-mortem said the mechanism lived in a
COMPONENT and not in the net; tested directly at a FIXED fill rate (expiry swept per cell to
0.342-0.359 against V49's uncontrolled 0.173; rho(fill, SELECTION) +0.134 p 0.894 and
rho(expiry, SELECTION) +0.012, so both confounds are clean), SELECTION scores rho **-0.5887** at
permutation p 0.0000 against a pre-registered -0.50, monotone on all five quintiles (-0.4654 ->
-0.5751), holding SEPARATELY on each side (L -0.472, S -0.473, so it is not this sample's 89%
up-drift), surviving 2x cost (-0.545) and keeping its sign on locked (-0.312, decayed, the right
shape). The phi-invariant gap carries the identical gradient (-0.5890), and SELECTION = (1-phi) x gap
holds to 1e-6. **BUT V49 WAS WRONG TO CALL PRICE AN ARITHMETIC IDENTITY**: its MEAN is one (+0.4959
against a constructed 0.5000), its **DISPERSION IS AS LARGE AS SELECTION'S** (sd 0.0674 vs 0.0689,
range +0.21..+0.68) and it moves the OTHER WAY with immediacy at rho **+0.4711** — so the net is
8.3x smaller than its parts and reads only -0.228. **THE CHASING EXPLANATION IS REFUTED**: the
adverse open gap is +0.0000 ATR (worst cell 0.0054 R, rho -0.039 at p 0.718) because on continuous
futures the next open IS the prior close — there is no chasing cost here, and no market-entry
backtest on this branch is quietly paying one. **99.8% OF PRICE'S CROSS-FAMILY VARIANCE IS THE EXIT
PATH**: entry offset sd 0.0017, exit path sd 0.0673 spanning -0.289..+0.182 — two trades on the same
signal with the same risk denominator, differing only in a stop sitting 1 ATR lower and a clock
starting later. The entry price is an identity; the STOP'S LOCATION is the whole variable. SELECTION
is a COST, not an edge (negative in 88/88 cells; the limit beats the market in 34/88 = 38.6%), and
gate 6 could NOT be run because a recycle wiped US100/US30, so the brief's success criterion is not
met. Two rounds have now failed to span positive immediacy — a ~0.04 R common-mode cost drag pushes
both sides negative and MIRRORING DOES NOT FIX IT. Also fixed here: V49's `roc` families cut at a
WHOLE-SAMPLE `np.nanquantile`, a threshold that reads the future, flipping 0.82-1.30% of bars.
See `docs/ib/STUDY_V50_SELECTION.md`.

**THE MA 200 IS A FLOOR, NOT SUPPORT — AND IT IS THE ONLY ONE OF FOUR REQUESTED FILTERS THAT
EARNS ITS PLACE.** 1,161,216 configurations (4 entry x 4 exit x 4 stop x 6 MA200 x 4 cross x 14
absorption x 9 session x 3 timeframes x 2 markets) on a fresh SINGLE-entry / SINGLE-exit Donchian,
searched on US100's first 70% with US100 locked and the WHOLE of US30 held back. Scored against a
RANDOM FILTER OF THE SAME SELECTIVITY, 2,000 draws, on all three blocks: **price at least 1.5 ATR
ABOVE the MA200 clears at p 0.001 / 0.001 / 0.001** and decays research -> holdout, the right shape.
**The SUPPORT reading — above and WITHIN 3.0 ATR — clears research at p 0.001 and then reads 0.241
and 0.999**, with a random filter earning MORE THAN DOUBLE on US30 (+0.3066 against +0.1333). Third
inversion of a "not extended" ceiling into a floor on this branch (`STUDY_TURTLE_15M` did it on
EMA100 for PF 0.94 -> 1.58), now on a third market. The 13x48 CROSS clears BOTH US100 blocks
(p 0.000) and fails the market that had no part in the search (p 0.400 state, 0.995 cross<=20,
1.000 cross<=5) — two blocks of one index over an overlapping calendar are not two tests. ABSORPTION,
defined from the user's own chart as a spike-volume UP bar closing in the lower 40% of its range
(sellers absorbing the buying) and LABELLED A PROXY because no feed here carries bid/ask at price:
REQUIRING it fails all three blocks and LOSES MONEY on locked (-0.0995 R, PF 0.866), appears in
**0.00% of the sweep's top 1000 in five of six variants**, and worsens monotonically as the volume
threshold rises (1.5x +0.031/+0.022, 2.0x -0.015/+0.001) — `STUDY_DIVERGENCE_CONFIRM`'s volume-spike
result from the other side. Avoiding it clears locked and US30 and FAILS research, the wrong shape,
so it ships OFF. THE FLATTEN IS DESTRUCTIVE on every window (07:00-11:00 +0.0778 -> -0.0347;
08:00-12:00 +0.1111 -> +0.0049; at the shipped geometry +0.2548 -> **-0.0239, PF 0.950**) — eighth
confirmation of the intraday constraint. The shipped default beats a RANDOM ENTRY on research
(p 0.003) and on held-back US30 (p 0.001) and **FAILS on US100 locked (p 0.241)**, two of three —
and it is **THE FIRST CANDIDATE ON THIS BRANCH TO SURVIVE 2x THE ASSUMED SPREAD** (p 0.004/0.232/
0.003). Population first: 248,172 cells clear 100 trades and **75.5% of them are profitable**, so a
cell is the max of ~187,000 positive draws, and FOUR OF FOUR GEOMETRY AXES RUN TO THE GRID EDGE.
VECTORBT COULD NOT DO THIS: 1.1.0's `sl_stop` is a fraction of PRICE, not a per-trade ATR multiple,
and `td_stop`/`dt_stop` do not exist — the same defect that made V46's cross-check inconclusive. The
cached exit tensor did **1,161,216 configurations in 17.7 seconds**, verified against an independent
plain-Python reference on 15 cells (trade counts identical, mean R to 1e-9).
See `docs/ib/STUDY_V51_MA_ABSORPTION.md`.

**THE TURTLE SCRIPT'S OWN TWO GATES DO NOT SURVIVE, AND A FILTER IS A PROPERTY OF A GEOMETRY, NOT
OF A MARKET.** The shipped `TURTLE_LONG` presets hard-code `ADX < 22` and `EMA100 distance < 3.964
ATR`. Reduced to ONE entry and ONE exit and swept over 4,644,864 configurations (2 entry x 2 exit x
4 stop x 6 MA200 x 4 cross x 14 absorption x 4 ADX x 4 EMA-distance x 9 session x 3 tf x 2 markets,
19.3 s, kernel verified against an independent reference on 10 cells): `ADX < 22` clears research at
p 0.005 and is **BEATEN BY A RANDOM FILTER OF THE SAME SELECTIVITY on held-back US30 (+0.2039 vs
+0.2658, p 0.940)**; both gates together read **p 0.983** there. NOTHING in the table clears all
three blocks. **The inversions are real and the WRONG SHAPE**: ADX>=22 and ADX>=25 clear US30 at
p 0.014/0.011 and FAIL research at 0.334/1.000 — and `STUDY_TURTLE_15M` found these same two gates
inverted on **15m** where they DID transfer, so THE TIMEFRAME IS THE DIFFERENCE and that caveat
belongs on the 15m result. **V51's MA200 floor does not transfer either**: p 0.001 on all three
blocks at 60m Donchian geometry, **p 0.994** on US100 locked at 240m Turtle geometry. Same market,
same feature, different geometry. `require SELLER absorption` clears both US100 blocks (p 0.004,
0.017) on **n=48 and n=22** and fails US30 — and its sign is OPPOSITE to the 60m reading, so the
absorption axis is unresolved. Population: 237,681 scorable cells, **77.3% profitable**, the stop
axis runs off the grid edge, and the marginal average LIKES the script's gates (+0.1112 vs +0.1018
off) while the control says they are worth nothing — that gap is why the control exists. The flatten
is destructive on every window again (all-hours +0.1604 vs flattened -0.0000..+0.0172), the ninth
confirmation. See `docs/ib/STUDY_V52_TURTLE_ONE_SYSTEM.md`.

**ADDING A CONDITION BUYS RESEARCH SCORE AND NOT LOCKED SCORE, AND THE POPULATION SHOWS IT DIRECTLY.**
280,320 configurations on NQ (4 tf x 4 entry x 4 exit x 4 stop x 5 MA200 x 3 cross x 73 absorption),
every trading timeframe resampled from the SAME 1-minute series so lower-timeframe absorption and
trading bars align exactly. Grouped by NUMBER OF ACTIVE CONDITIONS: mean research R rises +0.0517 ->
+0.0709 -> +0.0812 while mean locked R does not move (+0.0780 -> +0.0895 -> +0.0845), and
**corr(research R, locked R) COLLAPSES from +0.2366 with no filter to +0.0579 with one and goes
NEGATIVE (-0.0382) with two.** That correlation, computed within a slice of the population, is an
overfitting diagnostic that needs no cell to be named -- use it. Same reading on the timeframe axis:
research rises monotonically to 60m (+0.1965) while locked FALLS to it (+0.0304), so 60m is the
overfit end and 30m is where the blocks agree (+0.1192/+0.0896). **PARAMETER-FREE ABSORPTION** --
volume >= its OWN rolling mean (ratio exactly 1.0) and the close on the wrong side of the bar's
MIDPOINT (exactly 0.5), replacing two tuned numbers -- read on 1/2/3/4/5/15m and mapped up to the
chart bar: **NO GRADIENT ACROSS THE LOWER TIMEFRAME** (locked +0.0734..+0.1357 scattered around the
+0.0808 no-filter baseline), and the surviving window parameter is INERT (50/100/200 -> +0.0887/
+0.0871/+0.0904), which is what removing a tuned number should look like. Nothing clears its control
on both blocks: the BARE BASE fails a random ENTRY (p 0.051 research, 0.109 locked) and every filter
fails a same-selectivity random filter on at least one block, with buyer absorption 3m/4m passing
LOCKED (p 0.048/0.007) while FAILING research (0.455/0.636) -- the wrong shape, fifth occurrence.
Absorption has now given THREE DIFFERENT ANSWERS in three studies (V51 60m US100: requiring it is in
0.00% of the top 1000; V52 240m: it clears both US100 blocks on n=22; V53 30m NQ: no gradient),
which is itself the answer. **VECTORBT FAILED ITS TRANSCRIPTION CHECK A THIRD TIME**: on the
ATR-stop-only geometry it produced **6 trades against the engine's 175** (ratio 0.034), unchanged
across five configurations (full OHLC, exits as an all-False Series, no exits arg, a scalar sl_stop,
stop_entry_price='fillprice'); its stop LEVEL is exact and its TIMING is not -- a position stayed
open 2023-01-31 to 2023-03-01 through a month price spent below the stop, swallowing 175 entry
signals into 11 orders. 30-SECOND ABSORPTION IS UNTESTABLE HERE (1m is the finest data) and was not
proxied. See `docs/ib/STUDY_V53_UNDERFIT.md`.

**ONE OF THE FOUR CVD STRUCTURE PATTERNS CLEARS BOTH BLOCKS, AND TESTING THEM SEPARATELY IS WHAT
MADE IT VISIBLE.** Price/CVD divergence implemented as four distinct patterns at CONFIRMED pivots
(a pivot at i needs i-k..i+k so it is stamped at i+k, never at the pivot), CVD read at the PRICE
pivot's own bar rather than from a pivot of the CVD series. On NQ 30m, Donchian 20/20, 2.0N, against
a same-selectivity random filter: **EXHAUSTED SELLERS (price LL + CVD HL) at k=3 within 20 bars
scores +0.3509 PF 1.696 p 0.001 on research and +0.3176 PF 1.648 p 0.009 on locked** -- and it
DECAYS across the split, the right shape. The other three fail locked (ABSORBED SELLING p 0.903,
EXHAUSTED BUYERS p 0.179, ABSORBED BUYING p 0.926), and **ABSORBED BUYING -- the most bearish of the
four -- is the only NEGATIVE row on both blocks** (-0.0852 research at k5, -0.0109 locked), which is
the sign a long-only system predicts. Collapsed into one "CVD divergence" flag the four would have
averaged into nothing. CAVEATS: n=88 on locked, ONE MARKET (CVD needs 1-minute bars and NQ is the
only feed with them, so no cross-market read), and **the CVD IS A PROXY** -- true aggressor delta is
unavailable here, so each lower-timeframe bar's whole volume is signed by its own direction, which
is TradingView's own rule; the Pine computes it with `request.security_lower_tf` rather than calling
a built-in so the identity with the research is provable. **THE KAMA EARNS NOTHING: not one of
SIXTEEN readings clears locked** (2 timeframes x 4 lengths x 2 modes). Three clear research at
p 0.000-0.007 then read 0.801-1.000. The length axis is non-monotone and flat (20 best, 100 worst,
10 between), exactly as `STUDY_MA_LAG` predicts from KAMA's 1.25-bar lag AT EVERY WINDOW -- there is
no best setting to ship. Session 08:00-12:00 passes LOCKED and FAILS research (p 0.185 -> 0.029, and
with the flatten 0.632 -> 0.000), the wrong shape for the sixth time; the flatten turns research
NEGATIVE (+0.1686 -> -0.0058). Implementation note: a recursive indicator that goes all-NaN reads as
"no signal" rather than as an error -- the first KAMA returned 99.9% NaN because ONE non-finite
smoothing constant propagated through the recursion. See `docs/ib/STUDY_V54_CVD_KAMA.md`.

**A UNION IS DILUTED BY ITS WEAKER MEMBER, MEASURED AGAIN AND THIS TIME ON THE ONE RULE THAT WORKS.**
Asked to fire on BOTH bullish CVD structures and to add the EMA 13x48 cross, both additions were
measured against the same 2,000-draw same-selectivity control that certified the original: EXHAUSTED
SELLERS alone holds at **research +0.3509 PF 1.696 p 0.000 / locked +0.3176 PF 1.648 p 0.005**;
adding ABSORBED SELLING takes the kept share from 21.5% to 41.8%, HALVES the edge to +0.1842 and
loses locked at **p 0.210**; the EMA13>EMA48 state takes locked from p 0.005 to **p 0.158** while
keeping research respectable (p 0.014) -- the classic shape of a filter fitted to the search block;
the FRESH cross destroys research outright (p 0.677). Absorbed selling clears RESEARCH at p 0.050
alone and p 0.002 with the EMA state and fails locked at 0.908/0.611/0.685 -- exactly how a weaker
member sneaks into a union when only the research block is read. Third independent failure of the
13x48 cross on a held-back read (V51 US30 p 0.400-1.000, V52 US30 p 0.400, V55 locked p 0.158).
**THE NEIGHBOURHOOD IS THE REAL EVIDENCE, NOT THE P-VALUE**: exhausted sellers is positive in ALL 16
cells of the pivot-width x recency-window grid on BOTH blocks (research +0.163..+0.550, locked
+0.043..+0.631) and falls monotonically as the window widens. k3/w20 is NOT the maximum -- k3/w5
scores +0.550/+0.631 -- and w20 ships anyway because it carries n=88 locked against w5's n=37; the
larger sample is worth more than the larger number. See `docs/ib/STUDY_V55_AUTOMATED_CVD.md`.

**THE SHIPPED PINE AND ITS OWN BACKTEST DID NOT AGREE, AND THE SCRIPT READ BETTER -- WHICH IS THE
GAP, NOT AN EDGE.** V55's order model rebuilt in Python and diffed against the engine on identical
signals: **245 trades against 254 (96.5%), one exit bar in five elsewhere, R corr 0.9833, and with a
4 ATR target the script read +15.2% BETTER than the research.** Three causes, two fixable:
(1) NO EXIT ORDER WAS LIVE DURING THE ENTRY BAR -- `strategy.exit` only runs on a bar where a
position already exists, so the first stop is placed at the CLOSE of the fill bar; fixed by placing
a FILL-RELATIVE bracket (`loss`/`profit` in ticks) at the SIGNAL bar. (2) THE RISK WAS ANCHORED TO
THE FILL BAR'S ATR; fixed with a `var pendAtr` stored at the signal bar. (3) NOT FIXABLE -- an order
placed at the close of bar j is live during bar j+1 while the engine applies bar j's level at bar j;
that residual is the remaining 12.3% of differing exit bars. After the fix: **trade count 99.6%,
same exit bar 87.7%, R correlation 0.9997, and the gap now reads CONSERVATIVE (-3.2%)** -- the right
direction. Same procedure as `STUDY_PINE_PARITY`; run it on every script that ships. **THE CVD
RESULT SURVIVES THE HONEST MODEL** (research +0.3051 p 0.002 / locked +0.3125 p 0.003 against
+0.3509/+0.3176 under the engine), so it is not an order-model artifact. **ADX: NOT ONE OF FOUR
EARNS A PLACE** -- the conventional floors LOWER the edge and fail research (>=20 p 0.281, >=25
p 0.553); the inverted ADX<=20 scores best and is **MODEL-DEPENDENT (p 0.100 under the script's
model against 0.027 under the engine's)**, which is not a result, on n=39 locked. **AN ATR TARGET
CLEARS ITS CONTROL ON BOTH BLOCKS AT 3/4/6 ATR AND STILL LOSES TO NO TARGET** on per-trade AND total
R (research 166 x 0.3051 = 50.6R against 210 x 0.1949 = 40.9R at 4 ATR): a target closes positions
sooner, frees the position lock, and admits more trades at a lower edge -- and the p-value improves
only because the CONTROL degrades too. Eleventh time no-target has won here.
See `docs/ib/STUDY_V56_PARITY_ADX_TP.md`.

**A BAR COUNT IS NOT A SETTING -- IT IS A SETTING TIMES A TIMEFRAME, AND MOVING A SCRIPT BETWEEN
CHARTS SILENTLY DIVIDES IT.** Asked why two specific longs never fired on a 1-minute US30 chart, the
answer was three separate blockers and one root cause. The researched pivot k=3 and window w=20 are
on 30-MINUTE bars = **90 and 600 MINUTES**; run as raw bar counts on a 1-minute chart they became 3
and 20 minutes, one THIRTIETH of their reach. The nearest exhaustion events were **320 and 54
minutes back** -- inside 600, far outside 20. The rule was not rejecting those setups, it could not
see them. Two smaller blockers: `high > channel` FAILED ON AN EXACT TICK EQUALITY (52985.6 vs
52985.6), and the user's own "require EMA13 > EMA48" override blocked the second bar independently
(53219.2 < 53219.9). FIXES: order-flow settings are now declared in MINUTES and converted via
`timeframe.in_seconds()`, so the same numbers mean the same thing on any chart; and a TOUCH now
counts as a break, which is measurably free on the researched base (research p 0.000 -> 0.001,
locked p 0.005 -> 0.005, 62 extra signal bars in 5,000). Also worth keeping: **a TradingView plot
export can be reverse-engineered to recover the settings that produced it** -- `highest(high,30)[1]`
and `lowest(low,20)[1]` were recovered EXACTLY by matching candidate lengths against the plotted
columns, which is how the entry channel was found to be 30 and not the shipped 20. And
`request.security_lower_tf` with a timeframe NOT strictly below the chart's returns nothing, so a
1-minute chart with the delta source left on "1" produces a FLAT CVD and no divergence can ever
fire -- the HUD now warns. Fitting the entry channel to <=26 WOULD make both bars fire and is
recorded as curve-fitting to two events on eleven days.
See `docs/ib/STUDY_V57_REVERSE_ENGINEER.md`.

**A SWEEP OVER TWO LEVELS IS A SWEEP OVER THEIR DIFFERENCE.** The Initial Balance family sets the
entry at retr x range inside the broken edge and the stop at stop x range from it, so the RISK is
`(stop - retr) x range` -- a difference of two swept numbers, which the grid can drive to nearly
zero. Ranked in R, all 25 leaders of 777,600 cells cleared a matched control at p 0.000 with the
control losing 0.4-0.6 R; the winner was an **11.6-point stop at 10:1** on 15-minute bars. Score in
ATR UNITS at the plan bar and take profit factor in POINTS. Same disease as `STUDY_SWEEP_110K`'s
channel stop, reached by construction rather than by accident. **And the FILL BAR IS AN EXIT BAR** --
when entry and stop sit a tenth of a range apart they are inside one 15m bar, and skipping it hands
the config a free option worth up to +0.09 ATR/trade to **49.5%** of the grid. Run both models,
print the gap, and place the bracket WITH the entry in the script so the two match.

**THE INITIAL BALANCE RETRACEMENT LOSES ON THREE MARKETS, AND A CONSENSUS IS NOT A MARGINAL.** As
published (60m IB, 25% entry, 60% stop, 50% target, both sides) it scores PF 0.83/0.78 US30,
0.92/0.85 US100, 0.940 NQ and **loses to a risk-matched random entry at p 0.76-0.99** -- vectorbt
agrees on the trade count 100.0% in all four cells, the first time it has matched here. 777,600
configs x 2 markets: 13% profitable on research, EVERY marginal negative at EVERY setting of EVERY
axis, 2/25 leaders positive on locked against 6-12 by chance, 0/25 clearing their control.
`EMA 13 under 48` was in **74%** of the top 1000 and FAILS on both US100 columns of the marginal
read; only the **ADX floor** beats `off` in all four market-block columns, and it only shrinks the
loss. Trading the break ITSELF is the worst entry rung in all four columns (deeper is better to 0.5
of the range, then the two markets disagree, so the pass-one ridge was an edge effect). No take
profit ties for best -- twelfth time. One cluster (IB30 long, 0.5 entry, 1.0 stop, no target,
ADX>=20 + range>=0.8x median + close upper half + EMA13 under 48) was read once on NQ, which chose
nothing: **+0.354 ATR/trade, PF 1.80, control p 0.003 on 48 TRADES** -- a footing, not a result,
and it was selected on two other markets' locked blocks. `docs/ib/STUDY_V58_INITIAL_BALANCE.md`.

**`NQ_1m` IS STAMPED IN UTC AND EVERY OTHER FEED HERE IS ALREADY NEW YORK.** A loader that forgets
to convert puts a 09:30 session window at 04:30 New York -- the pre-open block measured as the worst
part of the day four times -- and V58's NQ table went from 48 trades PF 1.80 to 89 trades PF 1.49
on it. `research/datasets.py` states every feed's clock. Read it before loading.

**AN EMA 16/64 CROSS WITH A FOUR-HOUR CEILING HAS NO EDGE ON THREE MARKETS, AND corr(RESEARCH,
LOCKED) IS -0.070.** 243,000 configs per market (3 entry mechanics x 3 sides x 6 stops x 5 targets
x 4 hold caps x 3 trails x 3 sessions x 5 ADX x 5 ATR): 21%/11% of the grid profitable, median
negative. As briefed it scores PF 0.948/0.849 US30, 0.898/0.947 US100, 1.004 NQ and loses to a
minute-of-day matched random entry running the SAME management at p 0.53-0.99; vectorbt agrees on
the trade count 99.4-99.9% and puts the GROSS edge at -3.35 to +1.58 points against round turns of
1.72 and 1.215 -- **smaller than the commission**. The ONLY condition beating `off` in all four
market-block columns is the ATR FLOOR (>=1.2x its trailing median), worth ~+0.02 against a hole of
-0.06 to -0.11; read once on NQ it earns +0.0567 where a RANDOM entry earns +0.0413 (control
p 0.449). **THE FOUR-HOUR CEILING IS FREE AND WORTHLESS** -- 1h to 4h spans 0.02 ATR/trade with no
consistent direction, so the holding constraint is not what is wrong with the family. The PLAIN
CROSS beats both waiting for a close beyond the cross bar AND waiting for a pullback to the fast
EMA, on both markets. `docs/ib/STUDY_V59_EMA_TREND_4H.md`.

**THE MOST-AGREED CONDITION OF A TOP-1000 CONSENSUS HAS NOW FAILED THE MARGINAL READ TWICE.** V58's
`EMA 13 under 48` was in 74% of the top 1000 and fails on both US100 columns; V59's `ADX <= 20` was
in 55% and splits (+0.0244 US30 locked, -0.0220 US100 locked). A consensus over a ranking is a
consensus over what the RANKING SELECTED FOR -- both markets were in it. Only the marginal average
over the WHOLE grid asks what a condition does. Run both and believe the second.

**A CONTROL THAT INHERITS A POSITION LOCK MUST INHERIT THE ORDER TOO.** V59's matched control samples
one random bar per signal; those come out in signal order, not chronological order, so the lock
(`skip while the previous trade is open`) rejected an arbitrary huge share and each draw kept a
different fraction of its trades. The spread exploded and a rule beating its control by +0.18
scored **p 0.404**. Sorting the sampled bars fixed it (0/25 clearing -> 6/25). **DIAGNOSE A NULL BY
ITS SPREAD, NOT ONLY ITS MEDIAN**: a control whose median is far below the rule and which still
cannot reject anything is broken.

**A NINJASCRIPT PORT'S HARDEST BUG IS A GUARD YOU DIDN'T NOTICE WAS LOad-BEARING.** Porting
`FTM_OPENING_RANGE_BREAKOUT_MNQ_v1_8_0_RC1` (2,872 lines) to Pine, I dropped `sameCashDate` --
the source's `barOpenEt.Date == currentCashDate` -- as apparent boilerplate. It is not: CME index
futures reopen at 18:00 ET and that bar belongs to the NEXT exchange trading day, so its
`closeMinuteEt` of 1082 is >= the 960 flatten and the 16:00 CASH-CLOSE BRANCH FIRED AT THE START
OF EVERY SESSION, blocking the day before it could trade. Lint was clean, the logic read
correctly, and the port produced **0 eligible sessions, 0 signals, 0 trades**. A Python
transliteration of the SHIPPED PINE run over real 1-minute bars found it in one pass; with the
guard restored the same run gives 473 eligible sessions, 458 admitted signals and 342 entries with
all four exit reasons reached. **TRANSLITERATE THE PORT AND RUN IT ON BARS -- a port that compiles
and does nothing looks exactly like a port that compiles and works.** `research/ftm/ftm_sim.py`.

**A WARM-UP LONGER THAN TRADINGVIEW'S BAR BUDGET IS A STRATEGY THAT NEVER TRADES.** The FTM port
compiled, loaded, showed its inputs -- and produced NO TRADES, because the rule refuses to order
until it holds **120 completed sessions** of opening-range history and 21 session closes. An ETH
1-minute series is ~1,380 bars a day, so Basic's 5,000 bars is 2.6 sessions, Premium's 20,000 is
**10.4** -- the warm-up can NEVER complete on any plan. Fix: compute the warm-up context inside a
`request.security` on 15 minutes, which carries its own bar budget and months of history. **The
09:30 15-minute bar IS the 09:30-09:45 opening range** -- verified on 764 dates, ZERO high/low
mismatches, and 735 cash closes identical to the 15:45 bar's close. Before blaming a port, compute
how many sessions its warm-up needs and divide the plan's bar budget by bars-per-day.

**A FAIL-CLOSED SYSTEM NEEDS EVERY GATE SWITCHABLE, NOT JUST THE ONE YOU SUSPECT.** The FTM port
showed an empty Strategy Tester three times while compiling cleanly, and each round I fixed the
gate I could see. There were FOUR that silently produce zero trades and only one was switchable:
the 120-session warm-up refusal; the lookback itself; MINUTE CONTIGUITY, which hard-fails in THREE
separate places (the opening range's minute sequence, its 15-bar count, and the signal bar's 15
constituents) and matters because **NinjaTrader's feed carries a bar for every minute while
TradingView omits minutes with no trades**; and the 23:00 UTC reference open, absent on any
RTH-only chart. Measured cost of relaxing each over 1.05M bars: warm gate OFF 342 -> 454 trades at
+0.1620 -> +0.1608 R and PF 1.351 -> 1.374; lookback 120 -> 40, 417 trades at +0.1600; contiguity
OFF, identical 342 trades at +0.1583. All four are now inputs, all four are counted separately, and
the panel names the binding one. **Enumerate every fail-closed path FIRST and make each one both
switchable and counted; debugging them one per round is how three rounds get spent.**

**THE PARAMETER THAT MADE THE STRATEGY UNRUNNABLE WAS WORTH NOTHING -- MEASURE BEFORE BLAMING THE
PLATFORM.** FTM refuses to trade until it holds **120** completed opening ranges, ~11,000
fifteen-minute bars, which only the largest TradingView plans load; the Strategy Tester was empty
twice. Varying ONLY that lookback over 1.05M bars: 120 -> 342 trades PF 1.351 +0.1620 R;
90 -> 371 PF 1.421 **+0.1905**; 60 -> 399 +0.1607; **40 -> 417 PF 1.375 +0.1600**; 20 -> 434 +0.1476.
**Forty sessions is as good as 120, loads on any plan, and costs 0.002 R a trade.** The 120 was
never earning its constraint. Every fail-closed gate is now COUNTED and the panel names the binding
one, because a blocked date and a date with no signal look identical from outside.

**THE CONTINUATION RULE APPLIES INSIDE AN UNCLOSED BRACKET, AND `pine_lint` WAS NOT CHECKING
THERE.** V61 shipped lint-clean and would not compile: `options = [...]` wrapped at 16 spaces, which
Pine reads as a block body -- CE10013, "expecting end of line without line continuation". The linter
tracked bracket depth and then SKIPPED the indent check entirely while depth > 0, so only a
statement's first continuation line was ever examined. Exactly the defect `STUDY_PINE_PARITY`
recorded on `TURTLE_4_FINALISTS` and it recurred because the linter was never fixed, only the file.
Now checked at every depth -- and the same scan found **three other shipped scripts that could not
have compiled**: `V37_IFVG_ORDERFLOW` (24 spaces), `V38_DONCHIAN_LINREG` (24) and
`V41_EMA_DONCHIAN_US100` (16). All 101 scripts in `pine/` are clean. A lint pass is only worth what
the linter checks; when a script fails to compile, fix the LINTER first and the file second.

**PINE FUNCTIONS CANNOT ASSIGN TO GLOBALS, AND LINT WILL NOT TELL YOU.** `pine_lint` checks
indentation, not scope. A helper that does `dayBlocked := true` is a compile error TradingView
raises and nothing here catches, so the audit is mechanical: parse every `name(args) =>` body and
flag any `:=`/`+=` on a name that is not a parameter or a local. Mutating an ARRAY handed to a
function is fine, which is the standard workaround. Keep every `strategy.*` order call in the main
scope too, so its placement is never in doubt -- V56's parity defect was exactly an order landing
one bar later than intended. In the FTM port this meant hoisting every declaration above one
contiguous main scope and turning SubmitEntry and ApplyFinalEntryRefinementOrSubmit into PURE
functions that return a plan, with the mutation and the order at a single gateway.

**THE FTM OPENING-RANGE STRATEGY CLEARS ITS MATCHED CONTROL, AND ITS OWN HEADLINE FEATURE IS ITS
WEAKEST PATH.** Backtested on 1.05M one-minute bars with MNQ specs: 342 trades, +$11,661 on
$50,000, PF 1.351, win 47.4%, +0.1620 R/trade, max DD -$3,032, ret/DD 3.85, Sharpe 1.46,
bootstrap P(mean<=0) 0.005 -- and **excess +0.1013 R over a random quarter-hour entry with
identical geometry and exits, p 0.004**. Three qualifications outrank the headline: the **top 5% of
trades are 117% of net** (the other 95% lose in aggregate); 2023 is FLAT (-$214) with only 2024
strong; and the **conditional 15:30 exit alone contributes MORE than the entire net result**
(+$14,687 of $11,661), so the exits carry it. Tagged by decision path, the PLAIN path (no
refinement branch) earns +0.20 R on 211 trades against the **RC1 direct action's +0.10 on 62** --
the 1.8.0 headline behaviour is a DILUTION on this sample. The direction model fires 7 times in
458 admitted signals. ConfidenceScaledPercent makes the most dollars ($24,676) and has the WORST
PF and 2.6x the drawdown, because it drops the defensive one-contract cap exactly where the
drawdown comes from -- the caps are the risk model. `docs/ib/STUDY_FTM_ORB_BACKTEST.md`.

**A CHANNEL-POSITION INDICATOR CANNOT FILTER A CHANNEL BREAKOUT -- AROON IS THE DONCHIAN, REARRANGED.**
Where the Aroon period is no longer than the Donchian entry length, the breakout bar IS the N-bar high,
so `Aroon Up = 100` and `osc >= 0` hold on **100.0% of breakout bars -- 60,000 bars, three markets, zero
exceptions**. `osc>=0` and `up>=70` remove NOT ONE signal; the only rung that binds (`osc>=50`) costs
10-20 $/trade on every locked block. Aroon also correlates **+0.57 to +0.60 with the EMA state it was
being added to**. In the top 1000 the Aroon axis distributes 20-29% across its four inert settings --
the signature of an axis the ranking cannot see. Third time on this branch (`STUDY_V16_MOMENTUM.md`:
RSI>=55 on 94.7% of breakout bars; `STUDY_RULE_ANATOMY.md`: eight literal duplicates). **Compute a
proposed filter's base rate ON THE TRIGGER'S OWN BARS before sweeping anything.** Also from the same
grid: no take profit wins 5 of 6 market-block columns (fifth confirmation), and ADX>=20 -- which the
leading cell uses -- beats `off` in only **2 of 6** while CHOP<=45 manages 4.
See `docs/ib/STUDY_V60_AROON.md`.

**A PERFECT PLATEAU IS STILL NOT EVIDENCE, and now there is a number.** The one-rung box around V60's
leader -- 128 cells varying seven axes at once -- is **100.0% profitable on research on ALL THREE
markets** and **26.6% on NQ's locked block** (39.8% US30). Every in-block walk-forward fold is positive
on all three markets too, in a hump shape that is weakest at both ends. Coherence rejects artefacts of
the SEARCH; it cannot see a REGIME. And `corr(research, locked)` was **-0.4426 on NQ** over 121,282
configurations -- when that number is negative, selecting on research is worse than not selecting.

**MEASURE THE MECHANISM YOU NAME -- I ATTRIBUTED A 4-22 POINT ENGINE GAP TO A CONVENTION WORTH 0.2
POINTS.** An independent vectorbt build of the V60 leader agreed on the SIGNAL SET at 99.6-99.9%
(every disagreement inside the EMA(62) warm-up) and on the TRADE COUNT at 97.6-100%, then reported
4 to 22 fewer points a trade. The obvious explanation -- `eem`/`v38grid` exit a Donchian channel
break at the CLOSE of the breaking bar, which no script can place, while a script fills at the NEXT
OPEN -- is WRONG: `mean(open[j+1] - close[j])` over those exits is **-0.21 / +0.10 / -0.03 / -0.22 /
+0.55 / -0.31 points**, an order of magnitude out and not even consistently signed. The real gap is
vectorbt's own execution: its STOP exits land on the SAME bar as the engine's and price **9 to 110
points worse**, and **10-18% of its exits do not fill at the `price=` series at all**. Three
vectorbt traps now recorded: `sl_stop` is a fraction resolved against the bar's CLOSE and not the
`price=` fill (solve for the fraction that reproduces your engine's ABSOLUTE level); an unshifted
exit signal with `price=open` is LOOKAHEAD, filling at the open of the bar whose close triggered it,
worth +22 to +100 points a trade; and its exit-price selection is not fully controlled by
`stop_exit_price`. **THE ARBITER OF WHAT A SHIPPED SCRIPT DOES IS THE SCRIPT'S OWN ORDER MODEL,
WRITTEN OUT** -- `research/v60/v60_parity.py` does that and lands at 99.5-100% of the trade count
and **-2.6% to +4.6%** of the engine's points, negative on every locked block, which is the
conservative direction. A third engine is a second opinion about EXECUTION; it is not a correction
to the research.

**AN INDICATOR THAT IS AN IDENTITY ON THE SIGNAL BAR CAN STILL BIND ONE BAR EARLIER, and that is
the only version worth testing.** Aroon read at the bar BEFORE a Donchian breakout is not forced to
100 -- the prior bar need not be the N-bar high -- so the condition can actually refuse a trade. On
NQ 60m at Donchian 55, `osc>=0` / `up>=70` / `osc>=-50` at the SIGNAL bar return 54 trades and
+67.30 research / -20.02 locked, IDENTICAL TO THE CENT to `off`; at the PRIOR bar they give 52 /
45 / 53 trades and +74.52 / +98.19 / +69.42. It is a different question ("was the trend already up
before the break"), not a rescue of the original one, and one market with 30-50 locked trades does
not overturn the whole-grid marginal. **Also: A PRESET MUST NOT DISARM A SWITCH.** The first build
of the V60 script overwrote `aroonMode` during preset resolution, so the one input a reader would
most want to try was dead unless they left the preset -- a preset sets what it has an opinion
about, and nothing else.

**A SESSION WINDOW AND A HARD FLATTEN, PRICED ON THREE MARKETS: the 16:00 flatten costs 57% / 69% /
61% of the research result per trade on NQ / US100 / US30 -- every market, every time -- and it
RAISES the trade count** (83 -> 103, 212 -> 260, 208 -> 259), which is where the cost goes: the
clock closes trades a channel exit would have held. **NO WINDOW BEATS ALL HOURS ON RESEARCH ON MORE
THAN ONE MARKET**, and US30 is NEGATIVE in both morning windows on both blocks (09:30-11:00
-1.66 / -56.91). NQ's +73.37 at 09:30-12:00 is the best research cell in the table and reads
-12.53 out of sample -- the single-market story a three-market table exists to prevent. Tenth
independent confirmation of the intraday finding. Two
mechanics the parity harness forced: **"flat by 16:00" means flat at the 16:00 OPEN**, so the order
is submitted on the bar before (`nyMin + tfMin >= flatMin`), which is where `tensor_stop`'s
`flat_mod` path fills; and **a signal whose fill would land at or after the cutoff must be REFUSED,
not opened** -- the engine takes those and closes them at the same open for zero P&L, diluting the
statistics. `research/v60/v60session.py`.

**THE MACD IS THE THIRD INDICATOR TO TURN OUT TO BE THE BREAKOUT RESTATED, ON ALL THREE MARKETS.**
`macd > 0` at 12/26/9 passes **100.0% of US30's Donchian-55 breakout bars** (162 trades, +48.44
research / +20.28 locked -- IDENTICAL to no filter), **99.9%** of US100's and **99.8%** of NQ's; at
8/21/5 NQ reaches 100.0% and is identical too. A close above the 55-bar high essentially guarantees EMA(12) > EMA(26). Joins
RSI(14)>=55 at 94.7% and `aroon osc>=0` at 100.0%. **COMPUTE A CONFIRMATION'S BASE RATE ON THE
TRIGGER'S OWN BARS BEFORE ITS P&L** -- two lines ahead of any sweep. The only MACD reading that
binds is a FRESH bullish cross (42-45% of signals) and it fails every shape test at once: locked
+9.48 NQ / **+99.44** US100 / +0.94 US30, while making US100's RESEARCH block worse (+26.61 ->
+19.70), and flipping from +9.48 to **-29.51** one parameter rung away on NQ. A spike, seen after
the holdout, which is worse than seeing one before. **And MA TYPE, which `STUDY_MA_LAG` established is NOT a degree of freedom
for a single average, IS one for the MACD**: it is a difference of two averages plus a third
smoothing, so the lag mismatch compounds and EMA/SMA readings of `hist > 0` agree on only **79.2%**
of bars against 89.5-97.3% for price-vs-MA rules.

**THE SAME SESSION FEATURE HAS OPPOSITE SIGNS ON TWO SYSTEMS, one market each -- which is the
definition of not knowing.** A hard flatten costs the V60 Donchian breakout 57% of its per-trade
result at 16:00 and appears to RESCUE the YouTube Turtle on NQ (IS +0.193 -> +0.121, OOS -0.090 ->
**+0.174**). But every gate added to that Turtle -- window, flatten, ADX floor -- moves IS DOWN and
OOS UP, which is the WRONG SHAPE and has been a defect twice before here; NQ is the ONE market of
six where those frozen rules failed OOS, so fixing it there is selection; the ADX gradient rises
+0.140 -> +0.156 -> +0.307 as n falls 62 -> 57 -> 36, which is what RESTRICTIVENESS ALONE looks
like; and the flatten RAISES the trade count 158 -> 326, so it is not filtering but cutting trades
short. **READ SUCH A GRID BY ITS MARGINAL AVERAGE PER AXIS, NEVER ITS TOP ROW**: over 685 scorable cells
of a combined window x flatten x ADX x MACD x Aroon grid, the top in-sample cell is a 40-trade
configuration scoring +0.682 that reads **-0.058** out of sample, while the MARGINAL CONSENSUS
(08:00-12:00, flatten 16:00, ADX>=20, MACD `hist>0 and rising`, Aroon `osc>=0` at length 25) keeps
64 trades at +0.414 and is the only one of the three positive on BOTH blocks at **+0.207 / PF 1.75**
-- with a smooth neighbourhood rather than a spike. That is what `pine/turtle2/YT_TURTLE_1H` ships
with, gates ON. MACD is the strongest axis there (+0.390 against +0.184 for off) and ADX the
weakest -- ADX OFF beats every floor on both blocks. **A FROZEN KERNEL IS COPIED, NEVER
PARAMETERISED** --
`research/turtle2/yt_gates.py` duplicates `ytturtle.run` and ASSERTS parity with it (158/158 and
70/70, identical R) rather than adding arguments three published studies would silently inherit.

**THE INITIAL BALANCE MODEL'S EDGE IS THE RETRACEMENT DEPTH -- A RESTING LIMIT WEARING AN IB
COSTUME.** Reverse-engineering the one V58 survivor: the retracement axis is MONOTONE across all
five rungs with its control p-value falling monotonically beside it -- 0.00 (buy the break)
**+0.0226 at p 1.000**, 0.10 +0.1072 (p 0.902), 0.25 (as published) +0.2148 (p 0.075), 0.40 +0.2397
(p 0.001), 0.50 **+0.3087 at p 0.000** on 329 trades. CHASING THE BREAK HAS NO EDGE AT ALL; the
edge appears only as you make the market come back to you. A retracement fraction of the IB range
IS a resting limit priced in IB units -- sixth independent route to `STUDY_LIMIT_ENTRY`/`atme`'s
finding, and the first where the limit was hiding inside someone else's indicator. **THE FOUR
DECLARED CONDITIONS BUY +0.0457 ATR/trade AND COST 85% OF THE SAMPLE** (unconditional geometry
+0.3087 on 329 trades at p 0.000 against the full rule's +0.3544 on 48). `ADX>=20` is BACKWARDS --
removing it gives +0.6489, and its ladder falls monotonically with ADX strength. Exactly one
condition carries: the LAST IB BAR'S CLOSE POSITION IN ITS OWN RANGE, alone +0.4132 on 222 trades,
with bottom-40% at **-0.3211** against upper-half +0.3544. IB LENGTH BARELY MATTERS (30/60/90 all
p 0.000), which is what a ruler rather than a signal looks like. Also here: no target beats every
target for the SIXTH time; the 48 selected days travel **-0.5945 ATR** and finish up 47.9% against
+0.1775 and 57.1% for all other days, so this is NOT M4's drift-picker; but 275% of net comes from
the 15:55 FLATTEN and -175% from the stops, so what is owned is a held directional position, not a
barrier system. **NQ IS NOW SPENT** -- reserved as the block that chose nothing, read once by V58
and ~60 cells by the anatomy, so every p-value there is descriptive from here on.
See `docs/ib/STUDY_V58_ANATOMY.md`.

**THE CMMA MEAN-REVERSION NOTEBOOK: NO LOOK-AHEAD, NO EDGE, AND COSTS ARE NOT THE PROBLEM.** A
daily `tanh((close - SMA5)/ATR5)` negated, scaled by a 21-day Kaufman efficiency ratio, EMA-smoothed
and shifted, executed 08:00-15:45 NY. The audit and the execution-alignment check are CLEAN and the
signal traded on day D is finalised at MIDNIGHT NEW YORK as day D begins, eight hours before the
08:00 entry, so this is not a leak -- it is an effect too
small to demonstrate. US100 nine years: **Sharpe +0.39 +- 0.33 net**, deflated Sharpe **0.057**
against 34 trials whose expected best-of-noise is **0.85**, PBO 0.35, three of nine years negative,
the best 1% of days **240% of net**. Three things inflate the notebook's number: `sr =
eq.mean()/eq.std()` on a CUMSUM IS NOT A SHARPE (it prints 0.875 where the real annualised figure
is 0.83 -- close by coincidence, and it hides a +-0.58 standard error); `pnl = signal *
(close - open)` SUMMED OVER INTRADAY BARS drops every gap between bars, worth +13% on NQ and +24%
on US100; and no costs, which here is the SMALLEST of the three because the EMA smoothing holds
turnover at 0.04 contracts a day and the breakeven is 24-29 bps against 0.9-2.6 charged. **THE
COMPONENT ATTRIBUTION INVERTS BETWEEN FEEDS**: on NQ the KER weighting is the whole strategy
(+0.76 with, +0.16 without) and bare `sign(cmma)` earns -0.01; on US100 bare `sign(cmma)` is the
BEST row at +0.46 and every layer of machinery makes it worse. `tanh` and the EMA smoothing never
help on either. Same four components, opposite conclusions -- that is fitting noise.
**AND `metrics.sharpe_standard_error` TAKES A PER-PERIOD SHARPE**: handing it an annualised one
returns a figure sqrt(252) too small (0.04 instead of 0.58 here), which is the notebook's own error
class. See `docs/ib/STUDY_CMMA.md`.

**THE SECOND PASS ON THE TREND DESIGN LANDED ON THE CELL ALREADY SHIPPED, AND US30 HAS NO VERSION.**
Window x flatten x ADX x stop re-chosen by the MINIMUM of NQ and US100 research R: the consensus is
09:30-14:00 / flat 16:00 / ADX 20 / stop 2.5, i.e. the defaults. Holding overnight is PF 1.72 on
US100 research and 1.22 on NQ -- a change the feeds disagree on is not made. The NQ + US100 book
on the overlapping OOS dates has daily correlation 0.90 (one index, no diversification). US30:
the design is null on every cell, and STUDY_MEGA_144K's surviving US30 configuration re-measured at
one unit with the CFD cost model is PF 1.05 / 0.86 / 0.98 on US30's own blocks and 1.25 on the
ISO 2026 tail where NO ADX filter does better (1.29) -- a regime. A second read of an already-read
block that disagrees with the first is recorded, not averaged. `research/mrl/tf_balance.py`,
`tf_us30.py`, `docs/ib/STUDY_NEW_DESIGN.md` §7.

**RE-SELECTING THE TREND DESIGN ON GOLD PRODUCED THE ASK ON RESEARCH AND NOTHING ON LOCKED.**
24,192 cells on XAUUSD15_MT (entry window, flatten, level session, side, EMA-distance and
ATR-expansion floors added as axes): the only axis with a marginal is the ENTRY WINDOW, 08:30-11:30
New York (gold's derived anchor) R +0.059 against -0.090 for 03:00-12:00. The marginal-consensus
cell is research 63.1% / PF 1.50 (control p 0.000) and locked 50.0% / PF 0.91 (p 0.52); the top
research cell is 1.75 -> 0.75; all eight locked neighbours are negative and "no target" is the
worst of them, the reverse of every index. The NQ defaults unchanged are research PF 0.89 -> locked
1.20 -- the wrong shape, gold's 2025 rally. No gold settings recommended. `research/mrl/tf_gold.py`,
`docs/ib/STUDY_NEW_DESIGN.md` §6.

**TWO STRATEGIES DESIGNED FROM THE LIBRARY, AND THE ARITHMETIC THAT SAYS WHY 66% AT PF 1.5 IS NOT
ON THIS DATA.** w* = 1.5(1+c)/(1.5(1+c)+q-c): the ask is open only at a target >= 0.8x the stop
and needs +10 to +13 points of win rate over a coin flip after costs, against honest lifts here of
+1 to +5. The mean-reversion limit design (E1 + E9 + E2 + location features, true 1-minute path)
first showed **81.3% / PF 1.90 on EVERY BAR with no rule** -- two engine artifacts: (1) `limit_entry`
lets the TARGET fire on the FILL MINUTE, whose high was made before the dip that filled the order
(STUDY_V10's artifact at minute scale; fixing it: 70.7% / PF 0.92); (2) it scans forward from
each signal so several orders rest and the OLDEST fills first (the eem.run defect), which showed
as every-bar 68% against 65% for random subsets. With one live order and a strict target the
every-bar limit is PF 0.81-1.02 on 256 geometries and on three 15m feeds -- **E1 at real costs is a
null**, corrected in the library. The best honest MRL design (quiet session + positive 30-min
return, limit 0.75xATR5, stop 3xATR14, target 0.75x) is 60.8% / PF 1.17 on NQ locked, p 0.020 on
win rate and 0.077 on PF against a random filter, bootstrap P(<=0) 0.21, and does not transfer.
The trend design (Donchian 55 + ADX>=20 + PRIOR RTH SESSION HIGH gate + 2.5xATR stop + 20-bar
exit + no target + 09:30-14:00, flat 15:45) is NQ research PF 1.40 p 0.013, locked 1.24 p 0.33,
US100 1.34 / 1.56 / 1.20 with two control passes, US30 null; the gate is the component (without
it locked PF 1.00) and no-target beat every target for the fourth time. It ships as
`pine/tfi/TFI_NQ_strategy.pine` with those numbers in its header. `research/mrl/`,
`docs/ib/STUDY_NEW_DESIGN.md`. A ninth export format arrived with it: `XAUUSD15_MT`, MT4 tab
export, 100,000-row cap, UTC-stamped (derived from gold's 08:30 New York anchor).

**REVERSE-ENGINEERING THE FTM OPENING-RANGE BREAKOUT: the edge is the breakout SIDE and the
first-signal TIMING, and everything else in 2,700 lines is inert.** Fourteen component switches
in `ftm_sim.KNOBS`, each removing one thing, over 1.05M one-minute bars: the kNN direction model
+0.003 R, the prior-day override -0.003, the high-ORB regime 0.000, the 15:30 rule -0.006, the
stop REMOVABLE (+0.163 vs +0.155 R, still p 0.004 against a random quarter-hour entry), and NO
TARGET better for the fourth time here (+0.191, p 0.030). The breakout side is worth +0.10 R over
a coin flip (five seeds +0.056) -- and ALWAYS LONG with the identical machine earns +0.171 R
overall and +0.256 against +0.096 in 2025. At the 10:00 decision the random-entry control earns
+0.020 and the rule +0.143; later signals ride drift the control rides too. Strip the target,
managed stop AND 15:30 rule together and the pass is gone (p 0.148) because the CONTROL rises to
+0.098, so the excess over random is partly the exit machine harvesting a tail a random entry
lacks. The 200-cell exit grid is 100% positive, collapses to 2 clusters / 5 components (median
pairwise corr 0.746 -- one strategy scored 200 ways), has IS->OOS Spearman -0.05 with the IS top
decile landing on the all-cell OOS mean, and its walk-forward "best" selector beats the defaults
by +0.027 R only by picking the 8R target every fold, i.e. no target. All selectors earn nothing
in 2025-H2. +-20% moves nothing by more than 0.07 R; costs survive 4x and die at 8x; DD realised
at the 47th MC percentile; a 60-day 6%/4%-trailing evaluation passes 19.9%, busts 13.5%, times
out 66.6%. The refinement delay branches are the fragile part: submit at the signal and 2025 goes
to -0.010 R. `research/ftm/ftm_anatomy.py`, `docs/ib/STUDY_FTM_ANATOMY.md`. THE MECHANISM LIST
NOW LIVES IN `docs/ib/EDGE_LIBRARY.md` -- ten controlled mechanisms, the five things they share,
and the twelve-step reverse-engineering procedure; add to it only on a controlled, unselected
block.

**THE IBS SESSION EA IS A DRIFT EXPOSURE WEARING A SIGNAL, and no optimiser beats its own
defaults.** Zeta FX's MQL5 expert (buy at the cash close after a session closing in its bottom
fifth, hold up to five sessions or until a top-fifth close, stop one session-range below) on a
2,352-cell grid over four feeds: research blocks 99.9% / 96.4% / 78.1% of cells positive (US100 /
NQ / US30), and a RANDOM SESSION with the identical stop, exit rule and hold earns +0.13 / +0.14
/ +0.09 R against the default's +0.24 / +0.22 / +0.05. On the three genuine test blocks the
default's excess over that control is **−0.005, +0.014 and −0.008 R** (p 0.51 / 0.46 / 0.52); the
only reserved block it clears is US30 ISO 2026 (p 0.035, n 27) where the control itself is
negative. The surface is smooth (neighbourhood coherence 0.96-0.98, so nothing is a spike), the
grid is genuinely diverse (117-137 clusters at corr 0.7, 37-47 components for 90% of variance,
NOT one rule in 2,352 hats), and the walk-forward re-runs the whole sweep per fold and STILL
loses to the author's fixed defaults on US100 (chosen cells +0.17-0.22 R at median WFE 0.09-0.39
against +0.23 at 0.91). Two mechanics worth keeping: (1) the optimiser's favourite, a 0.5x-range
stop, is the R DENOMINATOR shrinking -- R +0.377 vs +0.133 at 3.0x while POINTS per trade go
+15 vs +47 -- the channel-stop lesson again; (2) on a CFD feed "the first tick after 16:00" is
the 18:30 re-open (US30 has no bars 16:00-18:30 on 94% of days) and the EA silently skips any
day whose final session bar is missing -- both found by the bar-by-bar parity walk, which also
caught that a STOPPED trade re-enters on the same session while a rule exit waits one. 9/9
configs x 3 markets identical after those fixes. Costs are not the obstacle (0x-2x moves R by
0.01-0.03). Bootstrap "passes" on 83.5% of US100 cells at P<0.05 is the shape of drift, not
1,964 discoveries. See `docs/ib/STUDY_IBS_SESSION.md`, `research/ibs/`.

**A PUBLISHED PINE'S PARTIAL TAKE-PROFIT IS RE-ISSUED EVERY BAR, and the report you get is the
literal one.** The "Double Donchian Channel Breakout" script (50/30 channels, width > 3%, TP 2% on
50%, 100% equity, no stop) calls `strategy.exit("TP1", qty_percent = 50, limit = ...)` on every
bar a position exists; once the order has filled the next call creates a fresh one for half of
what REMAINS at a limit the market is already past, which fills at the open -- the position is
halved every bar price stays beyond +2%. Reproducing that (literal) against the author's evident
intent (one partial): US30 +22.2% vs +9.9%, US100 -43.6% vs -54.5%, NQ +0.1% vs -9.0% -- the
accident is a scale-out into strength and it is the better exit. Run on the three indices instead
of the BTC it was fitted to, 1-hour, whole file: it clears a trade-count-matched random-entry
control on US30 (p 0.037 inside the width regime) and fails on US100 (p 0.84, and NEGATIVE AT
ZERO COMMISSION, -23%) and NQ (p 0.37). The US30 pass is a two-rung island on the width filter
(2% -22%, 3% +22%, 4% +17%, 5% -14%) that inverts across timeframes (15m -4%, 4h -19%), and the
unfiltered breakout loses 34-51% on all three. Every control here is NEGATIVE: a 30-bar channel
exit with no stop on 100% of equity loses money on a random entry in a rising market. Also: the
header's own one-month window holds 0 / 3 / 1 trades. Seventh Donchian breakout on this branch
to fail its control on two of three markets. See `docs/ib/STUDY_DOUBLE_DONCHIAN.md`,
`research/ddc/`.

**THE STRAT COMBO ENGINE BEATS A RANDOM BAR AND STILL LOSES, because its geometry costs more
than its pattern earns.** Bar-type reversal combos (3-2, 1-3-2, 2-1-2, 3-1-2 with a colour rule
and a hammer bonus) plus a four-filter location score, traded as a one-bar stop order 20 broker
points past the trigger bar with the stop 20 points past the other side and a 2R target: 15m,
as configured, **US30 -0.250 R (1,315 trades, PF 0.71), US100 -0.116 (1,459, 0.85), NQ -0.090
(489, 0.88)**, negative on every block, both sides and 24 of 27 calendar years. At ZERO cost:
0.000 / +0.071 / -0.001. The combos DO beat a random trigger with the identical order (control
-0.379 / -0.256 / -0.145, p 0.000 / 0.000 / 0.18) -- worth +0.06 to +0.14 R -- and the cost of a
one-bar-range stop entered on a stop order is larger than that on every feed; stopped trades
lose 1.10-1.30 R because spread + stop slippage is 10-30% of that risk. The location score is
decoration: it passes 68-93% of triggers (a 5-point tolerance always finds a fractal in 200
bars), removing it is no worse, and a stricter score is worse. Every knob that helps -- wider
buffers (0 -> 100 pts: -0.44 -> -0.09 on US30), slower bars -- helps by widening the stop
relative to a fixed cost, and none crosses zero. Win rate tracks the driftless break-even at
every RR within two points: the barriers are hit by noise. "Points" are BROKER points (0.1 on a
one-decimal CFD quote); a two-decimal broker makes every tolerance 10x tighter and is off the
left edge of the scale ladder. Ninth bar-range-stop intraday entry on this branch to sit under
the cost floor. See `docs/ib/STUDY_THE_STRAT.md`, `research/strat/`.

**FTM 1.8.0-ALPHA.2 IS RC1 MINUS $641, and the two knobs it turns touch 21 of 342 sessions.**
The alpha.2 NinjaScript keeps the whole 1.4.1-rc.1 parent and changes the entry policy in two
places: the prior-session flip observes ONE minute instead of two (H5), and the intraday flip is
capped at one contract (H2). Same simulator, same 1.05M one-minute bars, two knobs: RC1 342
trades / $11,661 / +0.1620 R reproduced to the trade; alpha.2 342 / $11,020 / +0.1551 R; H5
alone -$199, the cap alone -$441, additive. Sixteen flips fire a minute earlier and four of them
land on the other side of a barrier (two each way); five intraday flips are halved and the path
was net positive so the cap costs money. It still clears the matched control (excess +0.094 R,
p 0.006) and EVERY qualification from STUDY_FTM_ORB_BACKTEST stands: top 5% of trades 121% of
net, the 15:30 conditional exit $14,208 of an $11,020 net, 2023 flat, 86% of net in the
unchanged control action. The 15m CFD feeds cannot run it -- the opening range, the admission
test and every refinement observation are defined on exact one-minute bars. See
`docs/ib/STUDY_FTM_ALPHA2.md`; `ftm_sim.run(prior_bars=, h2_cap=)`.

**A DAILY-SIGNAL / INTRADAY-EXECUTION PINE PORT HAS FOUR TRAPS AND ONE OF THEM IS FATAL.** Porting
the CMMA notebook: (1) the daily bars are NEW YORK CALENDAR DAYS, and `request.security(..., "D")`
on a CME future gives the 18:00-17:00 ETH SESSION instead -- accumulate them from the chart's own
intraday bars and require EXTENDED HOURS ON, or every daily high/low/TR loses the overnight;
(2) THE LAG IS EIGHT HOURS, NOT A DAY -- with `label='right'` the daily bar labelled D covers
calendar day D-1 and closes at midnight as D begins, and pandas' `.shift(1)` is consumed by the
notebook's own `index - 1 day` remap, so no further shift belongs in the script (an earlier draft
of `STUDY_CMMA.md` said D-2 and was wrong by a day); (3) `ewm(2)` IS `com=2`, alpha 1/3, not a span;
(4) `math.round` RETURNS A FLOAT and `strategy.position_size` IS A SERIES FLOAT, so a continuous
target and its order size must be cast with `int()` -- assigning either to an `int` declaration is
the "cannot assign a value of the series float type to a variable declared with the const int type"
compile error, and it is the one Pine emits INSTEAD of a report; (5) **PINE CANNOT TRADE FRACTIONAL
CONTRACTS AND A CONTINUOUS TARGET ROUNDS TO ZERO** -- mean
|signal| here is 0.076, so at a base size of 1 the strategy places NO TRADE ON ANY DAY. Measured:
base 1 -> 0 days traded, 5 -> 202 (Sharpe 0.54), 20 -> 526 (0.65), 50 -> 640 (0.71) against the
fractional 748 (0.70). At 50+ the rounding is free; below 20 it is material noise. Parity against
the engine: correlation **1.0000000000**, max |diff| 6.9e-17, fractional P&L identical to the tenth
of a point on both feeds. `research/cmma/cmma_parity.py`.

**THE CMMA "IMPROVEMENT" THAT SURVIVED WAS A REMOVAL, AND THE ONE THAT CONTRADICTED FOUR PRIOR
FINDINGS LOST.** Seven pre-declared candidates, each required to beat the notebook IN-SAMPLE ON
BOTH FEEDS before the holdout was read: only DROPPING tanh AND THE EMA SMOOTHING survived cleanly
(NQ +0.76 -> +0.83, US100 +0.22 -> +0.47 in-sample; holdout +0.73 -> **+1.99** and +0.65 ->
**+0.96**, PF 1.28 -> 1.83 and 1.23 -> 1.32). Both were components §4 of `STUDY_CMMA.md` had
already measured as inert. Deflated Sharpe still 0.16 against 40 trials; holdout better than
in-sample on both feeds, which is the regime warning. **Starting the session at 09:30 instead of
08:00 HURT on both feeds** (NQ +0.76 -> +0.57, US100 +0.22 -> 0.00) -- the opposite of the four
prior 07:00-09:30-is-worst findings, because this is a HELD DAILY POSITION and not an intraday
entry, and a held position wants the pre-open hour. Vol-targeting helped NQ and zeroed US100: the
inversion again. Without tanh the signal is unbounded (99th pct 0.75, max 1.55), so the Pine's
position cap is load-bearing even though it never binds at a base of 50.
`research/cmma/cmma_improve.py`.

**A FILTERED STRATEGY CAN CARRY AN UNFILTERED ONE'S POSITION INSIDE IT, AND THE PORT HAS TO CARRY IT
TOO.** The ATR-phase-momentum NinjaScript keeps a "control shadow" -- the position the raw
oscillator rule WOULD hold -- and gates only the ENTRY on the VWAP filter: a cross to the side the
shadow already holds is a no-op even when the real position is flat, an opposite cross outside the
window flattens the shadow and exits only the held side, and a rejected reversal still exits. Drop
the shadow and a rejected long is silently retried on the next cross, which is a different strategy
with more trades. Ported as `pine/apm/APM_SESSION_VWAP_strategy.pine` with the recursions seeded as
the source seeds them (EMA at the first close, ATR as the mean of the first 14 true ranges, not
`ta.ema`/`ta.atr`) and every fail-closed path -- frozen calendar, decision-bar gap, session carry,
reset with exposure -- COUNTED on the panel and, by default, converted to flatten-and-block rather
than the source's permanent halt. Transliterated and run on NQ 1m built into exact UTC 10-minute
buckets: 104 trades, 101 of them cash-close exits, 36 blocked sessions, zero reversals in three
years. A control-flow check only; no control has been run on the family.

**THE APM SESSION-VWAP RULE'S DIRECTION CALL IS REAL AND ITS ENTRY IS A COST, and it is the first
grid here whose research ranking transferred.** Three matched controls on the ported NinjaScript
(docs/ib/STUDY_APM_VWAP.md): keep the rule's bars and flip a coin for the side and the rule wins
(NQ p 0.05 / 0.001, US100 0.012 / 0.034); keep the rule's SESSIONS and SIDE and enter at a random
bar in the window and the CONTROL wins on every block of every feed (p 0.85-1.00), because the fill
has already chased a median **3.97 ATR of a 4.99 ATR day**. Always-long is negative on NQ research
and every US100 block, so it is not drift. A 3-ATR excursion from the EMA21 is inside a 2.5-ATR VWAP
band 85% of the time in the 09:00 hour and **0% after 11:00**, so the source's entry window is the
filter restated. Random-entry control: NQ research p 0.054, US100 research / validation 0.019 /
0.032, US100 test **0.230** with 2025 at -27 a trade, US30 null over nine years. Grid: NQ 89%
profitable on research and **corr(research, locked) +0.52**, top decile +40.8 -> +57.8; US100
+0.31; US30 **-0.34** with the research top decile reading -50 on test -- the instrument decides.
Walk-forward re-selection loses to the author's constants on NQ (+0.2 vs +62.7) and US100 (-1.7 vs
+25.3): the optimiser buys count. Research P(mean<=0) 0.052 on 70 trades, locked read 34 trades,
p99 drawdown ~$2,400 per MNQ, and one contract on $50k cannot pass a 6% evaluation (two pass 42-70%,
bust 15-24%). Not live-ready; forward-test 40+ trades. `research/apm/`.

**THE APM EDGE IS A CONJUNCTION, AND THE OBVIOUS RESTATEMENT OF IT IS NULL.** Stripped of the
indicator, the direction call is "a 3-bar-sustained displacement of >= 3 ATR from a PRE-MARKET-
ANCHORED average (EMA21 on 10-minute bars carries the overnight), taken in the first hour while
the session VWAP is still within 2.5 ATR of price, continues to the cash close" -- E11 in the
library. The tempting restatement, a >= 3 ATR drive from the 09:30 open, is null at every rung
of a 0.5-5.0 ladder on NQ and US100 (+5.5 / -1.0 on 4x the trades, p 0.19 / 0.41) even though 93
of the APM's 104 NQ trades are such days: the rule is selecting the quarter of big-drive days that
continue, and the drive's size is not how. The published first-half-hour momentum is +0.6 / +0.4.
Remove the VWAP band (+13.3 / +3.6) or the smoothing (+9.3 / +4.9) and the research pass is gone
on both feeds; remove both and it is +0.3 / +1.6; bolt the band onto the plain drive and nothing
happens (+7.8 / +1.2). **Feature engineering on the rule's own trades ships nothing**: 17 causal
features in 8 families, 34 tests a feed, 2 and 5 at p <= 0.10 against 3.4 expected; the one
two-feed pick (VWAP distance below its median) reads NQ locked p 0.377 and US100 test p 0.872 with
the kept half at -15.6 against a base of +15.3, and it is the rule's own admission variable
restated. `research/apm/apm_edge.py`.

**A NO-STOP TARGET SYSTEM PUTS ALL OF ITS RISK IN 9% OF ITS TRADES, and the natural R unit for it is
a denominator trap.** The Raschke trend-day EA (fade the open back to a 20-EMA of RTH 15m closes,
after a session that was BOTH a trend day and never touched that EMA; target = the live EMA, flatten
at the close, no stop) selects 4.8-6.1% of sessions and wins 72-86% of them. Pooled over NQ, US100,
US30 and US30_ISO -- 298 trades -- it earns **+0.104% of entry price at P(mean<=0) 0.0054**, and
**271 target exits average +0.222% while 27 clock exits average -1.077%, carrying -93% of net**.
Measured in the obvious "R" (the entry-to-target distance) the same 298 trades score **-0.213 with a
worst of -114.3 R**, from ONE trade whose gap was 0.0001% of price: the same collapsing denominator
as `STUDY_SWEEP_110K`'s channel stop. Use percent of price. The conjunction is the whole rule --
both filters off leaves 453 research trades at -1.3 -- but **US30 is null on every block over nine
years (control p 0.245-0.494) and US100 FAILS research (p 0.224) while passing validation and test**,
the wrong shape, and re-selecting the 168-cell grid walk-forward gives -0.4 and -1.2 pts/trade
against the shipped constants' +30.1 and +26.6. Not live-ready; no library entry.
`docs/ib/STUDY_TRENDDAY_EMA.md`.

**A 15-MINUTE FEED CAN PRICE ITS OWN MISSING MINUTE.** The EA fills one minute after the session
open, which no 15-minute file can do. Running both resolutions of NQ through the same engine: the
trade sets are IDENTICAL (43/43, correlation 0.9975) and the 15-minute fill is **1.8 points per trade
WORSE**, so every CFD figure is a floor rather than a flattery. A target-only exit needs no intrabar
ordering -- there is no stop competing with it -- which is why the approximation is confined to the
entry. Measure the gap; never assume its sign.

**THE CHART TIMEFRAME DECIDES WHETHER A PINE PORT IS THE STRATEGY OR A COUSIN OF IT.** The trend-day
EA decides its direction from the SESSION-OPEN BAR'S OPEN, so the earliest fill Pine can reach is the
open of the bar AFTER that one: minute 1 on a 1-minute chart, minute 15 on a 15-minute chart. Diffed
against the engine by `td_parity.py`, the 1-minute port is EXACT — 43/43 trades, same entry bar, same
side, same exit bar, correlation **1.0000**, and the only gap (+0.09 pts) is `strategy.close_all()`
filling at the last bar's OPEN because it cannot sell the close of the bar that triggers it. On
15-minute files the SAME script keeps 98 of 125 US100 trades and 94 of 106 US30 trades, every shared
trade agreeing on side and exit bar and NONE on the entry bar: a fifth of the trades never open
because price reaches the EMA inside the first bar. The research figures for a 15m feed describe the
EA, not the script on that chart. And the later fills score HIGHER per trade on FEWER trades
(+40.97 on 43, +50.15 on 39, +44.89 on 29), which is selection, not improvement.

**ENTRIES AND PROFIT FACTOR TRADE AGAINST EACH OTHER SMOOTHLY, AND THE BEST CELLS TRADE LESS.**
Asked for 5x the entries at PF 2.0 on every market, a 127,008-cell sweep of the trend-day family
returned **0 cells** -- on the RESEARCH block, the easiest number the data can produce -- and 0 at
PF 1.5 or even 1.3. The frontier of the best worst-feed PF is monotone: 1.92 at 1x, 1.70 at 2x, 1.41
at 3x, **1.28 at 5x**, 1.20 at 8x. **The top 1,000 cells have a MEDIAN ENTRY MULTIPLE OF 0.42x** --
the grid's best configurations are TIGHTER than the shipped rule, not looser, which is what a day
filter that IS the edge implies. The best 2x cell (EMA 15, trend 50%, up to 2 touched buckets) holds
on every reserved block of every feed and lifts stitched Sharpe 0.79 -> 0.97, and its EMA axis is a
SPIKE (1.01 / **1.70** / 0.96 / 0.97); requiring every immediate neighbour on every axis to clear
even 1.30 leaves **0 cells at 2x**, the best worst-neighbour PF anywhere being 1.23. Research-to-
reserved Spearman over 124,000 cells runs -0.074 to +0.219 and is NEGATIVE on US30's test block, so
a survivor is one draw and not skill. Fifth large search on this branch to buy nothing.
`docs/ib/STUDY_TRENDDAY_EMA.md` section 12.

**CACHE THE DAY FILTER, NOT THE TRADES, WHEN THE FILTER IS SEQUENTIAL.** The trend-day EA's
cross-session EMA, its resets and its causal touch test depend only on (EMA period, bucket length),
so 14 sequential walks produce per-session statistics plus the EMA after every bucket, and the other
SEVEN axes then cost a walk over the qualified sessions alone -- roughly 1% of the file. 127,008
cells in **18 seconds**. Same idea as `research/v14/v14tensor.py` but keyed on the FILTER rather than
the geometry, which is the right split whenever the expensive part is recursive state.

**A SECOND INDICATOR CANNOT REFILL A POOL THE FIRST ONE EMPTIED.** Asked to raise the trend-day
frontier at 3x/5x/8x entries with a Donchian channel, 543,948 more cells per market -- gate (closed
at the channel extreme), stop (cut when price breaks it), midpoint target -- moved the rungs by
**+0.07 / +0.02 / +0.01** profit factor, from a search **129x larger**. The gate and the midpoint
target are NEGATIVE at every rung; only the "stop" helps, and **0% of the winning cells' trades ever
exit on it** -- every finalist places it a quarter to a half width BEYOND the channel, so it is an
entry filter wearing a stop's name. Placed INSIDE the channel it does fire (19% at three quarters in,
36% at the extreme) and never reaches the frontier, the same answer a gap-multiple stop gave
(1.70 -> 1.19). Coherence got WORSE with the extra axes (best worst-neighbour PF 1.07 at 3x against
1.18 without), the top 1,000's median entry multiple fell to **0.05x**, and in vectorbt every
risk-adjusted measure falls monotonically with entries (Sharpe 0.97 at 2x -> 0.71 -> 0.50 -> 0.42;
drawdown -12% -> -20%). The frontier is a property of the DAY FILTER, which is the edge itself.

**AN INDICATOR WHOSE WINDOW IS IN MINUTES CHANGES THE STRATEGY WHEN THE BAR SIZE CHANGES.** The RTH
VWAP Drift study's efficiency ratio is `|C[i]-C[i-n]| / sum|C[j]-C[j-1]|` with n = 30 MINUTES / the
bar size: at 1 minute that is 30 price points and 30 zig-zags in the denominator, at 15 minutes it is
**TWO**, so the ratio saturates. Median ER on NQ is **0.154 at 1m against 0.742 at 15m**, its 0.30
floor passes **18.7% of bars against 99.0%**, and the same code on the same three years produces
**162 signals at 1 minute and 1,057 at 15**. A 15-minute run of that study is a materially LOOSER
strategy, not a coarser view of the same one. Check a filter's PASS RATE at both resolutions before
porting anything between them.

**A REAL DIRECTION CALL WORTH LESS THAN THE ROUND TURN IS STILL A NULL.** RTH VWAP Drift EVO 1 (fade
back INTO a trend: the prior 15m bucket closed above a rising session VWAP, this one dipped to touch
it and closed back above, plus a drift and efficiency-ratio gate; stop at the bucket extreme, target
2R) beats a coin-flip side ON ITS OWN BARS at **p 0.000 on every 15-minute block of three feeds**, and
inverting it loses 0.2-0.4 R a trade -- the pattern genuinely knows which way to lean. Pooled over
4,477 trades it earns **+0.079 R GROSS and -0.010 R NET** (P(mean<=0) 0.69), so the entire result sits
inside the spread. Its own headline filter is inert or harmful (the ER floor changes 8 of 1,178 US100
signals and the NQ grid marginal falls -0.10 -> -0.30 R as the floor rises), its VWAP-slope filter
removes one signal in a thousand, and **its backtest books the entry at the bucket CLOSE -- a price
that has already passed when the signal exists -- worth 0.03 to 0.09 R a trade against a -0.01 R
edge**. Read the win rate against the geometry's own break-even (33.3% at a 2R target), not 50%.
See `docs/ib/STUDY_VWAP_DRIFT.md`.

**THE FIVE MOST PROFITABLE STRATEGIES ON THIS BRANCH SHARE ONE PLATEAU AND NOT ONE CONTROL PASS.**
Eight shipped strategies put into ONE unit -- percent of entry price for one unit, after each
feed's own costs -- and ranked on the RESEARCH block only: IBS session +9.91 %/yr, V56 CVD +7.94,
FTM ORB +6.38, APM VWAP +2.44, TFI +2.43, then trend-day +1.02, VWAP drift +0.85, CMMA +0.63. The
top five then took the same battery. **Every one of them passes the parameter neighbourhood
(73-100% of perturbed out-of-sample cells profitable) and NO STRATEGY WITH MORE THAN ONE RESERVED
BLOCK CLEARS ITS OWN MATCHED CONTROL ON A MAJORITY OF THEM** -- IBS 3 of 7, APM 1 of 5, TFI 1 of 7,
FTM 0 of 1, V56 1 of 1. The day-block bootstrap is worse: 1/7, 2/5, 1/7, 0/1, 0/1. **THREE OF FIVE
GREW OUT OF SAMPLE**, APM on all three feeds including one whose research block LOSES money --
the seventh occurrence of the wrong shape here. **AND A CONTROL COMPUTED OVER ALL TRADES IS A
RESEARCH-BLOCK STATISTIC**: FTM's published +0.1013 R excess at p 0.004 reproduces exactly over
all 342 trades (p 0.005) and reads **p 0.152 on the 147 locked-block trades alone**. Same error
class as ranking a feature over both blocks, reached from the other direction; it applies to any
figure on this branch quoted over "all trades". What HAS changed is cost: all five survive 2x the
assumed spread on the feeds where they are profitable, against the earlier candidates that
*every one* died at 1.5x -- these hold wider barriers longer, so a fixed round turn is a smaller
fraction of the trade. The binding objection is no longer execution, it is that +0.05 to +0.32
percent of price a trade over 87-702 out-of-sample trades does not separate from a matched null.
Funded evaluation, 60 days / +8% / -6% static, sampled over EVERY session zero-filled: at 2x
notional **P(neither) is 57-87% on four of the five** and raising leverage buys pass and bust
together. Permutation says the realised drawdown was LUCKY on IBS US100 (percentile 0.01, MC p99
27.2% against a realised 8.4%) and UNLUCKY on V56 locked (0.94) and TFI US100 research (0.98) --
size for the p99, not the backtest. What would move it is MORE RESERVED BLOCKS, not more
strategies. See `docs/ib/STUDY_TOP5.md`.

**OPTIMISING THE ONE RULE THAT WORKS FOUND NOTHING, AND THE POPULATION SAYS WHY: THE TOP 1% OF
RESEARCH CELLS IS WORSE OUT OF SAMPLE THAN THE AVERAGE CELL.** 2,177,280 nominal / **725,760
EFFECTIVE** cells on the V56 CVD base (the maximum-hold axis is INERT -- with a channel exit and an
ATR stop one always fires first), sweeping timeframe, both channels, stop, target, pivot k, window
w, the gate ON at each (k,w) or OFF, plus four filters that survived elsewhere here (V40's MA200
FLOOR, V21/V39's CHOP, V17's prior-RTH-session-high level, V22's adaptive stop). Tensor verified
against `v56core.walk`: **0 exit-bar mismatches, max |dR| 9e-7**. **97.8% of the scorable grid is
profitable on research**, so the top row is the max of ~1.2M positive draws, and
**corr(research, locked) = -0.026 Pearson / -0.020 Spearman** over 1,223,943 cells: top 100
+0.4005 -> +0.0425, **top 1% +0.2315 -> -0.0017 against the WHOLE POPULATION's +0.0508**. Nine
declared finalists, **not one beats the incumbent's locked per-trade result** (+0.1428%), and the
incumbent is the only one clearing its control there (p 0.012) -- F3 and F5 "clear" against control
medians of -0.057 and -0.038, i.e. they beat a null that loses money. **SCORE IN PERCENT OF PRICE,
NOT R, AND THE STOP AXIS INVERTS**: mean R runs 1.5N +0.347 -> 3.0N +0.175 while total percent runs
+7.5 -> +9.1, because R divides by the stop -- the first R ranking put a +2.33 R cell on top whose
actual return was +0.32%. **THE TWO NULLS SPLIT THE ANSWER**: the incumbent clears a same-selectivity
random FILTER on locked (p 0.012) and FAILS a random ENTRY (0.204); the unfiltered 15m geometry does
the reverse (1.000 / **0.002**). No cell clears both. **AND THE ABLATION IS THE BEST EVIDENCE THE
GATE HAS ANYWHERE**: one geometry, gate swept, both blocks -- it raises per-trade edge in **12 of 14
cells across two geometries**, and is negative in TOTAL return everywhere because it removes 70-90%
of the signals (off +14.0% total / +0.061 a trade against the best rung's +8.7% / +0.098). The one
real improvement is not a parameter: the same idea on **15-minute bars** (Donchian 15/30, 3.0N,
6 ATR target, k3/w30) takes 2.4x the trades for **+17.91% locked total against +12.14%**, Sharpe
+1.89 against +1.12, and clears the ENTRY null at p 0.020 -- picked from a 16-cell ablation read
AFTER the locked block, so descriptive. No target won for the THIRTEENTH time. Both presets diffed
under the script's own order model and both are CONSERVATIVE (-1.5% / -5.8% locked).
`pine/v61/V61_CVD_OPTIMISED_strategy.pine`, `docs/ib/STUDY_V61_CVD_OPTIMISED.md`.

**THE MONEY FLOW INDEX AND EMA-CROSS MOMENTUM ARE BOTH NULL ON A BREAKOUT, AND THE BASE-RATE TABLE
SAID SO BEFORE THE BACKTEST.** `MFI(9)>=50` passes **91.7%** of NQ 30m Donchian-20 breakout bars
against 52.4% of bars in general, `MFI(14)>=60` 77.2%, `EMA 21/55 spread rising` **91.1%** -- a
breakout IS a money-flow event and IS an EMA-spread event. Only two readings in the pool bind: the
overbought CEILING `MFI<=80` (58.6%, and the only lift BELOW 1 at 0.67) and the RECENCY form of the
cross (14.9%). Fourth measurement of this mechanism after RSI 94.7%, Aroon 100.0% and MACD
99.8-100.0%. 3,096,576 cells built so **every filtered cell has an exact `off` twin**, which makes
the ablation free: matched pairs improved, chance 50% -- **MFI 57.8% research -> 49.3% LOCKED**
(Spearman -0.257), **EMA 59.0% -> 58.0% with the ORDERING INVERTED at Spearman -0.618** (`cross<=5`
13/48 helps 30.3% on research and **85.3%** on locked; `spread>0 and rising` 21/55 goes 82.5% ->
55.8%). **THE DROP-ONE AT THE BEST CELL IS DECISIVE**: as found n84 +0.1203 PF 1.68 entry-null
p 0.070; drop the MFI +0.1025 p 0.065; drop the EMA +0.1080 p 0.100; **drop BOTH n128 +0.0978,
p 0.061 -- more TOTAL return (12.5% against 10.1%) and the best p in the table**; drop the CVD gate
as well and it dies (PF 1.15, p 0.179). The gate carries the strategy and the confirmations
subtract. Population transfer again: **top 100 research +0.3410 -> locked -0.0300, 27% profitable,
against the whole population's +0.0461**. Removing ADX and CHOP cost nothing. No target won for the
FOURTEENTH time -- the best cell's own no-target neighbour reads +0.2620 on locked against its
+0.1203. Ships `pine/v62/V62_CVD_MFI_EMA_strategy.pine` with both readings present and DEFAULT OFF,
each tooltip carrying its own locked matched-pairs share. **AND IT IS NOT A SCALP AND CANNOT BE
MADE ONE**: the incumbent's median hold is **660 minutes** with **0.0% of trades under 15 minutes**
and 11.1% under an hour, the 15m preset's is 315, and the tightest cell the grid allows (1.5N stop,
3 ATR target, 10-bar exit, 15m) still holds a median 90 minutes and earns **+0.0229 %/trade at PF
1.23** against the incumbent's +0.1263 at 1.66. Both scalping axes are MONOTONE THE WRONG WAY over
a million cells -- stop 1.5N +0.0506 -> 3.0N +0.0704, target 3 ATR +0.0439 -> none +0.0845 -- and
winners hold **5.4x longer than losers** (1290 against 240 minutes), so the edge is in exactly the
tail a scalp cuts off. Not a cost problem: at a 1-3 ATR stop on NQ 30m the round turn is 2-6% of
risk. Eleventh confirmation of the intraday-constraint finding.
See `docs/ib/STUDY_V62_MFI_EMA.md`.

**A TREND DESIGN ON A VWAP, A TRIPLE EMA CROSS AND ATR IS POSITIVE ON 7 OF 8 BLOCKS ACROSS THREE
MARKETS -- AND THE VOLUME IN "VWAP" DOES NOTHING.** 146,880 configurations searched on US100's
RESEARCH BLOCK ONLY, then frozen and read once on US100's later blocks, the WHOLE of US30 and the
WHOLE of NQ. Shipped rule: 30m, long only, EMA 13>34>89 aligned for at most 30 bars, close above a
RISING session VWAP, ATR(14) >= its own 50-bar mean, 1.5N stop, NO trail, NO target, hard cap 480
bars. Percent of entry price: US100 +0.2200/+0.1596/+0.3842, US30 +0.1799/+0.1352/+0.1797, NQ
+0.3585 research and **-0.0401 locked**; PF 0.90-2.28; it clears a random ENTRY with identical
geometry on **4 of the 7 blocks that chose nothing** and a random FILTER on 4. **THE COMPONENT TEST:
over 69,003 matched pairs the volume-weighted anchor beats its UNWEIGHTED twin in 55.7%, mean
+0.0096 Sharpe** -- a session average price does the same job, so do not let a script depend on a
volume feed for this. **REMOVING THE CHANDELIER TRAIL WAS WORTH 3.6x THE PER-TRADE RESULT**
(+0.0406 -> +0.1465, PF 1.24 -> 1.46) and more in total: a trail is a take profit wearing a stop's
name, which is the no-target finding reached from the exit side for the fifteenth time. **AND THE
MAXIMUM HOLD, WHICH V61/V62 MEASURED INERT, IS LOAD-BEARING HERE** because there is no channel
exit -- 60/120/240/480/960 bars pool at +0.0590/+0.1054/+0.1427/+0.1988/+0.2484, monotone toward
longer, and the median WINNER exits on the cap after TEN TRADING DAYS. Read the trade profile before
trading it: **it wins 9-19% of the time**, 86% of trades stop out, the capped 14% supply **261-264%
of net**, and the longest out-of-sample losing run is **28**. Costs are not binding (+0.0225 at 4x).
Watch the shape: the block that CHOSE the cell fails both its controls there (0.924 / 0.282) while
the blocks that chose nothing pass, and the pooled bootstrap overstates because US100 and US30 are
the same weeks. Parity: correlation 1.0000, gap +0.1%/+0.3%/-0.0%. **AND THE VWAP IS NOT SUPPORT**: split the
strategy's own trades by distance from it at entry and the NEAREST quartile is the WORST
(+0.1325 against +0.2636 and +0.2538 for the two middle quartiles), the shape is a hump not a
gradient, and Spearman(distance, result) is **-0.0495**. What the condition contributes is being on
the right side of a RISING anchor -- a state, not a location -- worth +0.0385 %/trade over no VWAP
at all. Its two LOCATION readings both score better than the shipped state form on the blocks that
chose nothing (floor +0.2204 PF 1.67, ceiling +0.2076 on 7/7) and the floor was the WORST reading on
the search block, so the same feature ranks oppositely on two geometries -- STUDY_V52 again.
**ATR AS A REGIME FILTER: THE DIRECTION IS THE FINDING, AND IT IS THE EXPANSION SIDE.** 86 declared
readings (expansion vs a rolling mean, ATR percentile, the same on ATR/price, and the slope) x BOTH
directions, each against a same-selectivity random filter, on eight blocks of three markets. Every
FLOOR/RISING family is positive (+0.006 to +0.047 mean edge, beats the no-regime baseline 57-71%)
and every CEILING/FALLING family is negative (-0.028 to -0.054, beats it 34-48%). **That INVERTS
V28**, whose only survivor of 240 cells was `atr percentile 500 <= 0.2` -- the bottom fifth -- which
re-run here improves **3 of 7** blocks at **-0.0615** and clears its control once. Fourth time a
volatility-state rule's sign has moved: run both directions or run neither. Three readings improve
on 7/7 blocks that chose nothing -- `atr/sma250>=1.2` (+0.0981, keeps 15.3%), `atr pct100>=0.6`
(+0.0874), `atr/sma100>=1.0` (+0.0845) -- against 0.67 expected by chance, with the blocks NOT
independent so read it as modest. **The shipped `atr/sma50>=1.0` is 5/7 at +0.0693 and the sma100
rung at the SAME selectivity is 7/7 at +0.0845**, so it ships as an input rather than the default
because it was picked after the blocks were read. **AND 21.9% OF 602 CELLS CLEAR THEIR CONTROL
AGAINST A 5% CHANCE RATE WHILE ONLY 49.3% BEAT THE NO-REGIME BASELINE** -- both true because the two
directions cancel; read the direction split, never the pooled share. Every reading has a NEGATIVE
edge on the one block that CHOSE the strategy. And the same gate scored 7/7 in the drop-one and 5/7
here with nothing changed but the base (the drop-one still had the trail on) -- STUDY_V52's
geometry lesson again.
**A HARD FLATTEN COSTS 86% OF THE EDGE ON A TEN-DAY-HOLD TREND FOLLOWER, AND A WALK-FORWARD
OPTIMISER FREE TO TAKE IT TOOK IT IN 0 OF 36 FOLDS.** Seven entry windows x flatten on/off on the
V63 design, pooled over the seven blocks that chose nothing: **the flatten is -0.1710 %/trade
averaged over the seven windows** and four of the seven flattened windows are NEGATIVE, closing
55-72% of all trades on the clock -- mechanism plain, the median WINNER holds 240 hours and exits on
the 480-bar cap. Twelfth confirmation and the most extreme instance. **NO ENTRY WINDOW BEATS ALL
HOURS** (+0.1988); the one row worth knowing is 09:30-12:00 without a flatten at +0.1964 on HALF the
trades and **7/7 blocks positive against 6/7** -- same edge, more consistent, less exposure, not an
improvement. The flatten's real attraction is drawdown, 16.5% -> 4.3-5.6% pooled, and **the
permutation puts those realised drawdowns at the 2nd-6th percentile of their own distributions with
a p99 of 13-15%**, so most of that comfort is luck. WALK-FORWARD: the window, flatten and stop
re-chosen in every training fold from 60 declared cells, expanding and rolling, three markets --
WFE 1.38/1.28 on US100, **0.71/0.60 on US30**, 0.95/1.01 on NQ, **mean 0.99**, and the fixed
constants are positive on 5-6 of 6 folds everywhere against the re-chosen 3-6. Fifth re-optimiser
to lose to the author's constants here. The chosen windows disagree across markets, which is what a
parameter with no information looks like. Both mechanics ship as inputs, DEFAULT OFF.
**A PER-TRADE OPTIMUM ON AN AXIS THAT ALSO CHANGES THE TRADE COUNT IS NOT AN OPTIMUM.** 405-cell
stop x target x partial sweep on V63 (9 stops 0.75N-12N where 12N cannot bind, 15 targets in BOTH
parameterisations because 2R behind a 1.5N stop is 3 ATR and behind a 3N stop is 6 ATR, 3 partials),
pooled over the seven blocks that chose nothing; 405 of 405 scorable and **99.8% profitable**, so
read the marginals. **THE STOP AXIS GIVES THREE DIFFERENT ANSWERS IN THREE UNITS**: per trade it is
MONOTONE WIDER (+0.015 at 0.75N to +0.232 at 12N), in R it PEAKS AT 2.5N (+0.139), and in TOTAL
MONEY AT ONE UNIT IT IS FLAT (+169.0 / +171.0 / +163.1 / +172.0 / +133.9 at 1.5/2.5/4/6/12N) while
max drawdown climbs MONOTONICALLY 16.5 -> 21.4 -> 20.5 -> 26.1 -> 38.2. **Return-over-drawdown
therefore picks the TIGHTEST rung, 1.5N at 10.3 against 8.0 / 7.9 / 6.6 / 3.5** -- and it risks
0.37% of entry price a trade against 6N's 1.53%. The per-trade column is a trade-count artifact
(434 trades at 6N against 850 at 1.5N). This CORRECTS two earlier per-trade readings in the same
study that preferred 2.5N. **AND THE STOP EARNS ITS PLACE**: at 12N total falls to +133.9 and
bootstrap P(mean<=0) rises 0.0003 -> 0.0137, so removing it is worse than having it. NO TAKE PROFIT
wins monotonically in BOTH parameterisations -- the SIXTEENTH time -- and **every target clears its
own break-even win rate and still loses to no target** (0.5R needs 66.7% and gets 68.5%; 8R needs
11.1% and gets 30.5%), with the shortfall GROWING with the target because the trades that reach a
wide one were going further. Partials subtract (none +0.1071, half at 1R +0.0746). The scalping
corner is dead AND is a tie-break artifact: `0.75N / 0.5R` is -0.0044 %/trade on 4,399 trades with
a **5.5% ambiguous share against 0.0% for every wide cell**.
See `docs/ib/STUDY_V63_TREND_VWAP.md`.

**A SIXTH RE-OPTIMISER LOSES TO THE AUTHOR'S CONSTANTS, THIS TIME 6 OF 6 CELLS AT MEAN WFE 0.17.**
The Saty-phase / ATR-normalised-momentum configuration as specified (EMA 21, ATR 21, smoothing 4,
+/-100 zones, 09:30-10:30 entry, opposing-extreme exit, 2.5 ATR VWAP band) walked forward with all
six parameters re-chosen inside every training window from a 2,304-cell grid CENTRED ON THE GIVEN
VALUES, rolling and expanding, three markets. Re-chosen against given: NQ +0.0684 / +0.0592 against
**+0.3123**, US100 +0.0006 / +0.0698 against **+0.2702**, US30 both worse and both negative -- and
on FOLD CONSISTENCY the given constants win 7/7 and 11/13 against the re-chosen 5/7 and 7-9/13.
**THE OPTIMISER NEVER SETTLES**: its per-fold choices agree with its own first fold only 38-52% of
the time over six axes, and it keeps the given value in `vwap` 0/7 and `ema` 1/7 on NQ. A parameter
whose optimum moves every fold has no information in it. **REPORT WFE ONLY AGAINST A POSITIVE
BASELINE** -- US30's given baseline is -0.0195 and the ratio came out at -24 MILLION before the
guard was added. The configuration itself is a TWO-MARKET one: US100 +0.1913/+0.2933/+0.2469 on
three blocks at PF 1.90-2.53 and NQ +0.1394/+0.3805, against **US30 negative on two of three blocks**
and never above PF 1.05. Note also what the port cannot represent: the 61.8 golden-ratio zone is
drawn and never traded on, and two of the twelve given numbers have no field to map to.
See `docs/ib/STUDY_APM_WFO.md`.

**WHAT A TREND-FOLLOWING SCALP NEEDS, MEASURED: THE CLOCK, PARTICIPATION AND A VOLATILITY FLOOR --
AND IT STILL DOES NOT CLEAR.** 31 declared conditions x 2 triggers (Donchian 20 breakout, EMA
13/34/89 stack) x 2 GEOMETRIES (scalp = 0.75N stop / 1.5 ATR target / 24-bar cap; swing = 2.5N / no
target / 480 bars) x 6 feed-timeframes x every block. **THE GEOMETRY FLIPS THE SIGN BEFORE ANY
INDICATOR**: the same triggers earn -0.0033 and -0.0052 %/trade at scalp geometry (4/16 and 3/16
blocks positive) and **+0.0948 and +0.1191 at swing** (12/16 and 14/16). **AND THE ZERO-COST
VARIANT SAYS IT IS NOT EXECUTION**: gross is only +0.0039 / +0.0023 while the cost is +0.0073 /
+0.0085 -- the round turn EXCEEDS the entire gross edge. Win rate at scalp is **34.3% / 33.6%
against a driftless 2R bound of 33.3%**, so the trigger has no directional edge at that payoff at
all. **COST AS A FRACTION OF RISK IS THE NUMBER**: 24.4% of a 0.75N stop on NQ 5m (break-even 41.5%)
against 1.8% of a 2.5N stop on US100 60m (33.9%) -- a 13x spread that no indicator closes.
**EVERY FAMILY IS WORTH A TENTH AS MUCH AT SCALP GEOMETRY**: trend +0.0032 vs +0.0287, regime
+0.0008 vs +0.0259, momentum +0.0016 vs +0.0197. **THE CLOCK IS THE ONLY FAMILY THAT DOES NOT
SHRINK** (+0.0076 scalp vs +0.0075 swing) and is the largest scalp contributor of any family -- for
a scalp, WHEN beats WHICH INDICATOR. **TWO CONDITIONS INVERT AND BOTH INVERSIONS ARE MECHANICAL**:
`ADX>=25` is the 2nd-best swing condition (+0.0587, 78%) and NEGATIVE at scalp, because trend
strength needs a trade long enough to pay; `volume >= 1.5x its time-of-day mean` is the BEST scalp
condition (+0.0093) and the WORST swing one (**-0.0549**), because a participation spike marks a
move resolving now. And the popular confirmations are the trigger restated once more --
`close>EMA50` passes **93.7%** of signals, MACD>0 93.2%, ROC>0 91.0%, EMA13>48 90.9%, Aroon 88.1%.
Ranked scalp answer: session filter, participation floor, ATR floor, MA200 DISTANCE (not the
cross), prior-RTH-session high (81% of cells, the most consistent in the table).
See `docs/ib/STUDY_SCALP_REQUIREMENTS.md`.

**AN EXECUTION OVERLAY ON A BREAKOUT IS A PULLBACK ENTRY WEARING A COST COSTUME, AND THE POSITION
LOCK DECIDES WHICH OBJECTION YOU SEE.** A 1-minute `(close - EMA20)/ATR20` reversion signal
scheduling the entries of a 30m Donchian 20 / 2.5N breakout on NQ -- stop level, exit clock and
size identical in both arms, so only the entry timestamp moves. **WITHOUT A POSITION LOCK the
baseline is 5,045 overlapping trades, ~6.7 concurrent a day, and the overlay reads +436.8 points
on +107,608 (+0.41%): placebo percentile 87.5 (p 0.125), paired block bootstrap p 0.706 / 0.357,
haircut breakeven 0.0210 bps a side against half the Roll implied effective spread of 0.1871
(ratio 0.11), and 62.4% of the gain is DROPPED TRADES -- n=4, all losers -- while the claim being
sold is fill quality.** WITH the lock (227 trades, +62.04 pts, Sharpe 1.249) the picture inverts:
**Δ +508.5 (+3.61%), attribution 100.0% entry price with 0 dropped and 0 added, placebo percentile
100.0 (p 0.000), bootstrap p 0.083 / 0.099, haircut ratio 2.98, and the K sweep rises then
PLATEAUS** (+118/+150/+406/+508/+506/+518 at K = 5/10/15/30/60/120) instead of being shapeless.
Cost cancels exactly -- Δ is +508 at 1x, 2x, 4x and 8x the round turn -- because the trade counts
are identical. **AND THE BLOCK SPLIT KILLS IT ANYWAY: research +0.586 %/trade at placebo p 0.125
with a MEDIAN of exactly +0.000 points, locked +5.526 at p 0.000** -- absent where it was chosen,
present where it should decay, the wrong shape for the eighth time, with **83% of the gain in the
locked block and the top 5% of trades (11 of 227) supplying 101.1% of it**. The mechanism is named
by the size: mean entry improvement **+1.162 bps against half a spread of 0.1871 -- 6.2x**, which
no waiting can capture, so it is a better LEVEL after a median 3-minute pullback and not a better
fill. That makes it a SIGNAL change carrying a signal's selection burden, the sixth route to
`STUDY_LIMIT_ENTRY` / `research/atme/`. Two screening gates also fail before anything is built:
the fast drift at signal bars is **-0.0422 bps against a slow accrual of +1.4880 bps/min (0.03x**,
where the skill asks for comparable) and the direct fast edge of +0.0304 bps is **0.16x** half the
Roll spread, so the reversion is substantially BID-ASK BOUNCE. Confirms `STUDY_V50_SELECTION` from
the execution side: the adverse open gap on continuous futures is +0.0000 ATR because the next open
IS the prior close, so there is no shortfall for a scheduler to recover. **REPORT THE BASELINE'S
CONCURRENCY BEFORE REPORTING AN OVERLAY'S ATTRIBUTION** -- an unlocked baseline counts the same move
twenty times and turns a price effect into a population effect.
`research/overlay/`, `docs/ib/STUDY_OVERLAY_DONCHIAN.md`.

**AN OPENING-RANGE GATE CALIBRATED TO THE WRONG TIMEFRAME MAKES A STRATEGY UNTESTABLE, AND THAT IS
THE WHOLE RESULT OF ORB v1.** A one-trade-per-session opening-range breakout built exactly to
spec on NQ (5m bars, 09:30-09:45 range, HTF EMA20/50 read from the last CLOSED 15m bar, session
VWAP, ATR(14) frozen at the signal, volume SMA(20) shifted one bar, 0.25% equity risk, 1xATR stop,
50% out at 1R then breakeven then 2R). **`range_size / ATR` compares a 15-MINUTE range to an ATR
measured on an unstated timeframe, and that unstated choice moves the gate's pass rate from 1.4%
(15m ATR) to 95.3% (240m)**. Under the literal reading -- ATR on the trading bars -- the median
ratio is **2.45** so the specified [0.3, 1.5] band keeps the QUIETEST NINTH of sessions (11.1%), a
compression filter, and the rule fires **31 times in 765 sessions**. Everything downstream rests
on 15 / 5 / 11 trades. The shape is wrong for the ninth time here: **development -$88.31/trade at
PF 0.367 and Sharpe -1.35, validation +$127.60 at PF 4.15, out-of-sample +$25.39 at PF 1.250** --
it loses on the only block permitted to choose. It clears NO control: a random post-range bar with
the same session, side and 1R/2R geometry scores **p 0.478**, a coin-flip side on its own bars
**p 0.516**, day-block bootstrap P(mean<=0) **0.629** whole-sample and 0.379 out of sample. It does
beat always-long on the same bars (-$28.29 against -$13.14), which is the weakest of the three
nulls. **COSTS ARE NOT THE BINDING CONSTRAINT, WHICH IS RARE HERE**: doubling slippage costs
$0.80-$1.83 a trade because a 1xATR stop on 5m NQ is ~28 points against a 1.72-point round turn --
**6% of risk**, against the 24% a 0.75xATR scalping stop carries. 4,320-cell sensitivity: **only
24.2% of 3,835 scorable cells are profitable in-sample**, corr(IS, OOS) +0.186 Pearson, and EVERY
axis marginal is negative except a 240-minute ATR, which wins by making the gate inert. The spec's
own values are the BEST setting on three axes (ratio band, HTF, trading timeframe) and the WORST on
two (buffer, stop) -- the stop preferring 1.5N over 1.0N replicates the monotone-toward-wider
finding for the seventh family. **The marginal consensus chosen on dev+validation goes +$6.22
in-sample to -$26.50 out of sample with a 9-trade losing streak**, the seventh re-optimiser here to
lose to its starting point. Two mechanics worth keeping: **the intrabar tie-break was ANSWERED
rather than assumed** -- exits walked on the 1-minute path leave **0.00%** of trades with a stop
and a target in the same minute, and flipping the assumption is worth exactly **$0**; and at 0.25%
risk on $100k with MNQ's $2 point value the median size is 3 lots, so **on 12.9% of trades the
"exit 50%" instruction rounds to ZERO lots** and is simply unavailable. ORB v1 is a SINGLE-MARKET
result -- US100/US30 are 15-minute here and can carry neither a 15-minute opening range nor a
1-minute exit path. `research/orb/`, `docs/ib/STUDY_ORB_V1.md`.

**THE ORB GATE WAS WRITTEN FOR A 15-MINUTE CHART, AND A SECOND TIMEFRAME IS WHAT SHOWED IT.** Run
on 15-minute bars the opening range is ONE BAR, so `range_size / ATR(14)` is ~1 BY CONSTRUCTION --
median 1.54 NQ / 1.61 US100 / 1.54 US30 / 1.88 US30_ISO against **2.45 on 5-minute bars** -- and
the specified [0.3, 1.5] band passes **30-47% of sessions instead of 11%**. The spec's numbers are
internally consistent only where the trading bar IS the range. Frozen and run unfiltered on four
feeds (724 trades, 10 blocks): **1 of 10 blocks clears a random-entry control at p<=0.05 -- US30
research at p 0.007 -- and it is the block that would choose**, while US30's own validation and
test read **p 0.983 / 0.973** and an INDEPENDENT SECOND PROVIDER over a different span reads
**p 0.990**. Cost is 3.7-5.4% of a 1xATR stop on every feed and 2x slippage moves expectancy
$0.81-$5.14 and flips no sign, so execution is not the objection. **THE REGIME FILTER'S CHOP
EXCLUSION IS THE ONE COMPONENT THAT AGREES ACROSS ALL FOUR FEEDS**: ADX(14)/DI on completed 15m
bars with EMA20/50, a normalised slope and hysteresis classifies **17.0-18.2% BULL / 14.6-15.4%
BEAR / 66.7-67.7% CHOP** on every market, and the trades it REMOVES lose money 4 of 4 (-$5.15,
-$15.33, -$9.75, -$64.79; PF 0.49-0.95) while removing 54-58% of the sample. **BUT THE HYSTERESIS
IS INERT** -- collapsing entry=exit=25 reclassifies **0.8-0.9% of bars**, because ADX(14) on 15m
rarely lingers in the 20-25 band, and the `adx_exit` axis is flat TO THE CENT across 15/18/20. And
the direction gate is the weak half: BEAR is the WORST bucket on NQ (-$83.10, PF 0.377) and
US30_ISO (-$68.58, PF 0.291) while being fine on US30. Filtered vs unfiltered on the four reserved
blocks: **two improve and two do not**, and the one that gets much worse (US30 test PF 0.537 ->
0.332) is the market whose research block looked best; only US100's test crosses zero (PF 1.047,
n 26). Drawdown falls on every feed and so does the trade count by 54-58%, which is the same
artifact `STUDY_V24` recorded. **324-cell threshold sweep: 66.7% profitable in-sample and
corr(IS, OOS) = -0.633 Pearson / -0.656 Spearman**, so tuning these thresholds is worse than not
tuning them -- and the share profitable is EXACTLY 66.7% at every setting of every axis because
two of three markets are profitable regardless: **the spread across MARKETS (-48 to +44) is an
order of magnitude larger than the spread across THRESHOLDS within a market (<=10)**. ADX entry is
the only axis with a gradient and it runs the OPPOSITE way on NQ (looser better) from US100/US30
(tighter better). Ship nothing; keep the CHOP exclusion as a loss-avoidance finding, drop the ADX
exit threshold as decoration.

**6,000 OPTUNA TRIALS ON THE ONE RULE THAT WORKS BOUGHT RESEARCH SCORE AND NOTHING ELSE, AND THE
WALK-FORWARD OBJECTIVE TRANSFERRED WORST OF THREE.** TPE and NSGA-II over a CONTINUOUS space the
V61 grid could not reach (stop [1,4] then [1,8], both channels every integer to 80 then 150, MA200
floor and CHOP ceiling continuous), evaluator verified to reproduce the published grid TO THE CENT
on both blocks. **Research total climbed +18.88% -> +40.93% -> +55.40% as the search got harder and
the box got wider; locked total went +12.14% -> +8.62% -> +16.34% against the shipped 15m preset's
+17.91%.** Research Sharpe rose monotonically with search effort (1.37 -> 1.71 -> 2.11 -> 2.54 ->
2.81) and **locked Sharpe did not follow at all** (1.19, 1.71, 1.70, 1.03, 0.87). NOT ONE of six
finalists beat the shipped presets out of sample. **THE MEDIAN-OF-8-FOLDS OBJECTIVE -- adopted on
this branch precisely because raw return fails -- WAS THE WORST**: research +26.43% -> locked
**-0.07%**, the only losing finalist, and it bought a 63-trade cell. **WIDEN THE BOX AND THE
OPTIMUM RUNS TO THE NEW CEILING** -- stop 7.61 of an 8.0 limit, target 10.35 of 12.0 -- which is a
stop that cannot bind and a target never reached, i.e. the optimiser rediscovering no-take-profit
and a wide stop through the back door for the sixteenth time. **THE ONE DURABLE OUTPUT IS fANOVA
IMPORTANCE**: timeframe 0.477 and the CVD recency window w 0.209 carry the objective while pivot
k 0.006, prior-session-high 0.003, adaptive stop 0.005 and max hold 0.012 are noise -- the max-hold
reading independently confirms V61's own inert-axis accounting, and interaction-aware importance is
something a one-axis marginal cannot give. The V30 surrogate reproduces: random-row R^2 **+0.8956**
against **-6.92** holding out a whole timeframe, worse than predicting the mean. **AND A POSITIVE
TRANSFER CORRELATION CAN BE AN ARTEFACT OF THE SAMPLER**: over 2,496 distinct configs
corr(research, locked) is **+0.32 Pearson**, against the exhaustive grid's -0.026, because TPE
concentrates in a narrow good region so the correlation is measured over a restricted range with
both ends positive -- 99.1% of the sampled population is profitable on research. It says the
neighbourhood is uniformly decent, NOT that research ranking picks winners; the seven-row finalist
table says the opposite. **A SAMPLER CANNOT BEAT AN EXHAUSTIVE SEARCH ON THE SAME SPACE** -- only
reach the same maximum faster -- so a Bayesian study on an already-gridded rule is worth running
only for the continuum, a different objective, or interaction-aware importance. Ships nothing as
default; one Pareto cell is added to the V61 script as a third NON-DEFAULT preset (locked +14.80%,
PF 1.513, Sharpe 1.70, maxDD **-4.23%** against the 15m preset's +17.91 / 1.479 / 1.71 / -5.64 --
better return-over-drawdown 3.50 vs 3.18, less return, same Sharpe) with DESCRIPTIVE stamped on it.
See `docs/ib/STUDY_V64_OPTUNA.md`.

**THE SEVENTH RE-OPTIMISER LOSES OVER ALL NINE FOLDS AND WINS ON FOUR, AND BOTH READINGS ARE
REPORTED.** Walk-forward on the V61 CVD rule with the selection RE-RUN INSIDE every training
window (19,200 declared cells, 9 quarterly test folds, rolling 4Q and expanding, five arms
including a RANDOM cell from the same grid). Over all nine folds the shipped 15m preset wins both
schemes: **+34.27% against a re-chosen +28.20% rolling and +24.50% expanding**, with a random grid
cell at +8.28% -- and the 15m preset is the only arm with **NO LOSING QUARTER** (9/9 positive,
worst fold +1.70). **BUT THE FIXED ARMS HAD ALREADY SEEN FIVE OF THE NINE FOLDS** -- the research
block ends 2024-11-27 -- so the head-to-head is re-read on the four post-cut quarters, where the
schemes DISAGREE: rolling FIXED15 +17.07 against re-chosen +14.23, expanding **re-chosen +19.84
against +17.07**. Four folds cannot separate them; that expanding win is the first time on this
branch a re-optimiser has come out ahead on any honest slice. **WHAT BOTH SCHEMES AGREE ON is the
distinction that matters: selecting from this family beats picking from it ARBITRARILY (3/4
post-cut folds, 8/9 and 5/9 overall) while re-selecting EVERY FOLD does not beat NEVER selecting.**
**NORMALISE WFE BY SPAN OR IT IS A SPAN RATIO**: raw sum-OOS/sum-IS reads 0.145 and 0.094 because
training is 4-12 quarters and testing is 1; per-quarter it is **0.582 rolling and 0.751 expanding**,
and the expanding scheme has the higher efficiency with the LOWER absolute return. **THE STABILITY
TABLE IS THE BEST OUTPUT**: the optimiser picks entry channel **15 in 9/9 folds** and exit **30 in
8/9** -- exactly the shipped 15m preset's channels, and NEVER the incumbent's 20/20 -- and NO TAKE
PROFIT in **8/9**, chosen freshly inside every training window, the seventeenth confirmation. On
timeframe, stop, k and w its modal share is 44-78% and it never settles, and freezing the agreed
axes to re-choose only the wandering four helps expanding (+28.39) and hurts rolling (+23.36), so
the wandering is not cleanly the problem either. **AND ON THE WALK-FORWARD OOS SPAN ALL THREE ARMS
CLEAR A GEOMETRY-MATCHED RANDOM ENTRY AT p 0.000** (incumbent +0.1512 %/trade against a control
median +0.0438; 15m preset +0.0745 against +0.0174) -- the strongest evidence the rule has, on a
span where nothing was selected. Note entry 15 is the grid MINIMUM, so that axis sits on the box
edge as it did in the Optuna study. See `docs/ib/STUDY_V64_WFO.md`.

**A PRICE-JITTER PERTURBATION IS THE ONLY ONE THAT MOVES THE SIGNAL, AND V61 SURVIVES 750 OF 750
DRAWS.** Jitter every bar's OHLC independently, repair the bar (high = max of the four, low = min)
and RECOMPUTE ATR(14), both Donchian channels and the CVD pivot structure FROM the jittered bars:
at 0.5/1/2 ticks of noise, 250 draws each, all three V61 presets keep their sign **1.000** of the
time, trade counts move 85->87 / 209->211 / 166->166, and the zero-noise case reproduces the
reference to the cent. An execution perturbation (slip U(0,2x), cost U(0.5x,2x) applied INSIDE the
walk) gives a p5-p95 band **half a percentage point wide** and P(total<=0) 0.000, because a 2-3 ATR
stop on NQ is 60-90 points against a 1.72-point round turn -- run it first so the demanding tests
are not mistaken for it. Dropping 40% of fills leaves all three positive. **THE PARAMETER
PERTURBATION INVERTS THE USUAL RANKING**: under a joint jitter on six axes the INCUMBENT -- the
only pre-declared cell that cleared its control -- reads p5 **+0.71**, P(<=0) **0.036**, worst
one-rung neighbour **+4.24** (a 1 ATR target costs two-thirds of the result) and only **41% of its
neighbours beat it**, so it sits near the top of a narrow ridge; the 15m preset and the Pareto cell
read p5 +13.59 / +10.41, P(<=0) 0.000, and **75% / 70% of jittered neighbours BEAT them** -- the
lower quartile of their own neighbourhood is what a cell that was NOT cherry-picked from a spike
looks like. `hold` is exactly inert again (swing 0.00), the third confirmation. **AND THE BOOTSTRAP
IS THE WEAK LINK, NOT THE ROBUSTNESS**: on the locked block NO preset's 95% CI cleanly excludes
zero and the incumbent's P(mean<=0) is **0.110 on 85 trades**, while the 15m preset and Pareto reach
0.027 / 0.026 on 208 and 166 trades with a SMALLER per-trade edge -- i.e. through sample size.
`STUDY_V15_BOOK`'s split reproduces exactly: the same rule reads **p 0.000 against a matched
random entry** on the walk-forward span and **0.110 against zero** here. **The permutation says the
incumbent's realised path was UNLUCKY** -- its drawdown sits at the **95th percentile** of
reshuffles of its own trades (the other two at 0.65 / 0.60), the opposite of this branch's usual
finding -- and MC p99 drawdown is **1.19x / 1.73x / 1.84x** the realised, which is the sizing
number. Caveat that stays attached (`STUDY_ATME_LIVE`): a perturbation prices execution and data
noise ON THE TRADES YOU SELECTED and can never price the SELECTION.
See `docs/ib/STUDY_V64_MONTECARLO.md`.

**THE "IB 25 RETRACEMENT" IS NEGATIVE GROSS AND ITS WIN RATE IS ITS OWN BREAK-EVEN.** A posted
discretionary rule -- VWAP anchored 09:30, nothing before the 10:20 close, fib on the 09:30-10:30
range, resting limit at 25% from the target-side extreme, target that extreme, stop at 50%, no
entries past 12:00 or after a sweep -- transcribed to NQ 1-minute with ONE live order and one trade
a session. Research **-0.0169 % of entry price per trade, PF 0.807, -$6.55 an MNQ contract**;
locked +0.0097 / PF 1.111 / +$4.42 -- losing on the block that would select it, the wrong shape for
the TENTH time. **It is negative GROSS (-0.0047, -$0.11 a trade)**, so better fills cannot rescue
it, and it **loses to a random entry MINUTE in the same window with the same side and barriers at
p 0.845**; research bootstrap P(mean<=0) **0.965**. **THE POST'S OWN BEST OBSERVATION IS CORRECT
AND WORTHLESS**: moving the stop to 75% raises the win rate 48.4% -> 66.4% exactly as claimed and
expectancy stays negative, because the win rate tracks the driftless break-even at EVERY rung --
32.5 vs 28.6, 48.4 vs 50.0, 56.5 vs 60.0, 66.4 vs 66.7, 74.2 vs 75.0. **THE TWO JUDGEMENT CALLS
THE POST INSISTS ON EARN NOTHING**: over 16 cells of VWAP-slope threshold x VWAP-cross ceiling not
one is positive, the chop ceiling removes **63% of the sample and changes the per-trade result by
0.0001**, and the slope threshold is monotonically HARMFUL. The two "don't trade after" rules are
the two that hurt or do nothing -- the sweep veto COSTS money and the 12:00 cutoff is free and
worthless. The long side loses (-0.0322, PF 0.669) against a nearly flat short side in a market
that rose 89%. **AND V58's MONOTONE RETRACEMENT LADDER DOES NOT REPRODUCE**: here every rung is
negative and the shape is non-monotone, because V58's family retraced a BREAKOUT while this one
fades back toward the range extreme -- two families sharing a fib tool and nothing else. **IN MNQ
TERMS**: $2 a point, round turn **$3.44** = 1.72 points = **6.5% of a $53 median risk**, one
contract loses **~$1,050 a year** on research with a **$2,480** drawdown, and it is negative even
at FEES ONLY (-$3.21 a trade) which no one achieves. Only `retr 0.50 / stop 0.75` clears its own
break-even (36.0% against 33.3%) and it is gross **+$4.24** / net **-$0.20** -- a pure cost
problem, unlike the posted geometry. **AND A DOLLAR ANSWER NEEDS THE SYNTHETIC-LEVEL DEFLATOR**:
measured against US100 over 862 overlapping days the stored NQ level runs **1.2563 -> 1.0182**
above the real index, so dollar figures are inflated **11.7%** on the research block and 2.6% on
locked -- percent of price, R and win rates are unaffected, dollars are not.
**TWO SIGN ERRORS WERE CAUGHT HERE AND BOTH BY A DIAGNOSTIC RATHER THAN BY READING**: the matched
control had its target and stop swapped so every control trade exited instantly in profit (median
+0.1513, 5-95% band of **ZERO WIDTH** -- a null with no spread is broken); and slippage was applied
in the trader's FAVOUR at both entry and exit, worth 2 x slip = 0.5 points = **$1.00 an MNQ trade**,
caught because expectancy ROSE with the assumed slippage, which is impossible for a fixed trade set.
Slippage hurts only if the entry is worse by `+ side x slip` AND the exit by `- side x slip`; one
sign backwards halves the charge, both backwards pays it out. Sixth control/sign error on this
branch. Single market -- US100/US30 are 15-minute here and cannot resolve a 10:20 close or a
1-minute limit fill. See `docs/ib/STUDY_IB25_RETRACEMENT.md`.

**A FIXED-POINT TRAILING STOP ON AN ATR STOP INVERTS THE REWARD:RISK BY ARITHMETIC, AND THE
SUBMITTED "NQ SCALPING SYSTEM" LOSES ON ANY ENTRY.** EMA89 trend, EMA8/21 pullback >= 15 pts,
StochRSI reset-then-cross, 06:00-11:30 Chicago, ATR stop 1.5x / target 2.5x, 5 MNQ -- with the
screenshot's "Always use Fixed Points for Trail" ON at 15 / 8. Transcribed with its ORDER MODEL
(indicator parity 3e-8) and run on NQ 1m/5m/15m and 9 years of US100: **negative on 8 of 8 blocks**
(PF 0.37-0.67). NQ 5m: research **PF 0.393, -$92,951**; locked 0.445, -$67,843; exits 62% trail,
37% stop, **1% target**, median hold 1-2 bars. **Median ATR(14) on 5m NQ is 10.4 points, so a
15-point arm sits at the stop distance and 60% of the way to the target**, and 62% of trades exit
at ~+7 against -16 stops. Trail OFF: PF 0.393 -> **0.863** research, 0.445 -> 0.972 locked -- and
the code's own ATR-scaled trail (1.0 / 0.5) is just as bad at this ATR (0.397); 60/30 points is
0.750. Nothing with a trail beat no trail. **THE EXIT MACHINE'S RANDOM-ENTRY CONTROL BAND IS
ENTIRELY NEGATIVE**: [-0.0447, -0.0376] %/trade at the configured geometry, so it loses on any entry
and the rule sits inside it (p 0.177); trail off, a random bar BEATS the rule (p 0.730). **THE NAKED
FILL BAR HID A THIRD OF THE LOSS**: protecting it takes research PF 0.393 -> **0.151** and -$92,951
-> -$118,465, because a 16-point stop on a 10-point-ATR bar is hit inside the fill bar; Pine's
intrabar path vs stop-first is worth 0.004 PF. **THE ENTRY HAS NO REPRODUCIBLE INFORMATION**: at a
fixed 15-30 minute horizon with no exits the SHORT signal reads +0.13 / +0.21 ATR over a random bar
on NQ 5m research (p 0.007 / 0.000) and **-0.03 / -0.00 on NQ 5m locked (p 0.64 / 0.48)**, negative
on NQ 15m both blocks, absent on US100 -- one block noticed it and none reproduces it; the long side
is null everywhere. Ablation: the EMA89 gate is the only condition that helps (0.863 -> 0.785
without it); pullback depth, EMA touch and StochRSI reset are inert to +-0.03; shorts do the damage
(0.789 vs longs 0.942) in a market that rose 89%. **160-cell geometry sweep on the short entry:
0 of 80 net-profitable, 10 of 80 gross**; the long side's net-positive cells are all no-target /
no-hold -- 60-151 trades at 1-5% win rates, multi-month longs in a rising market. **729-cell
walk-forward with in-fold re-selection: a RANDOM cell beats both the re-chosen and the fixed
constants in both schemes** (rolling -4.85 vs -5.76 / -7.76; expanding -5.19 vs -16.42 / -7.76),
the eighth re-optimiser here to lose and the first to lose to a random cell; it picks the widest
target offered in 8/9 folds. Monte Carlo on the trail-off variant: **P(total > 0) = 0.000 on
research under execution noise and under price jitter with the indicators recomputed**; research
bootstrap CI [-0.0273, **-0.0014**] excludes zero on the NEGATIVE side, P(mean<=0) 0.984. Session
is inert (+-0.02) and 09:30 is WORSE here -- third time a session preference has not transferred.
Shipped as `pine/scalp89/NQ_SCALPING_SYSTEM_v2_strategy.pine` with the trail default OFF, a
fill-relative bracket placed WITH the entry, and an isconfirmed guard: mechanics corrected, no edge
claimed, the header carries the numbers. `research/scalp89/`, `docs/ib/STUDY_SCALP89.md`.

**A DIVERSIFIED TREND ENSEMBLE BUILT TO SPEC PASSES EVERY IMPLEMENTATION TEST AND HAS NO EDGE ON
TWO EQUITY INDICES -- WHICH THE SPEC PREDICTED.** The uploaded design (five EWMAC sleeves 4/16 to
64/256 with hard-coded scalars, FDM from a given sleeve-correlation matrix, vol blend 0.70/0.30 over
span 32 / 2560, rolling-5-year IDM capped 2.5, tau 0.20, a 0.10 no-trade buffer, t+1-OPEN execution,
no optimisation) built as `research/trend/` per its own layout. Its engine is BREADTH -- 15-30
instruments across four asset classes -- and what is on disk is US100 + US30: **N = 2, one asset
class**, which the spec calls a coin flip. **The three mandated tests pass on first run with no
refit**: alignment corr 0.023 / 0.015 (and the skill's diagnostic shows same-bar execution would
have manufactured Sharpe **1.13 / 0.82** against 0.19 / -0.22 next-bar); E|F| lands at 9.8-12.2 with
the scalars AS GIVEN, confirming they are properties of the filter; the one-time calibration hits
tau exactly at c = **0.7885** -- and note the sign: two correlated indices run the book HOTTER than
target (0.254), not cooler as the spec's 20-instrument simulation did (0.133). Buffering cuts
turnover to **7.9 / 9.4 turns a year**. Then the battery: training net Sharpe **-0.037**, deflated
Sharpe **0.039** at N = 12 (expected best-of-12 from noise +0.65), breakeven cost **NEGATIVE**,
random-strategy null percentile **47**, block-bootstrap P(Sharpe<0) **0.54**, and a +-25%
perturbation surface that is a **flat plateau at zero** -- the implementation is not fitted to noise
and there is nothing under it. **THE SPEC's 1260/252 WALK-FORWARD YIELDS ONE FOLD on 6.5 years**
(Sharpe -0.80); a labelled 756/252 supplement gives +0.88 / +0.52 / -0.80, sd 0.88, and the spread is
the finding. **CPCV IS DEGENERATE ON A PARAMETER-FREE STRATEGY**: all five paths read -0.056 with
sd 0.000 because every path reassembles the same fixed series; it measures selection variance and
there is none. **2022 -- trend following's best year on a diversified book -- was -20.1% at Sharpe
-1.15 here while the system was SHORT US100 on 83% of days and US100 fell 33.8%**: whipsawed by the
bear rallies a single asset class cannot escape, and the vol terciles say the same (low +0.96, high
**-1.06**, the opposite of crisis convexity). Holdout, read once: **+0.54**, better than training,
the WRONG SHAPE, failing the spec's own within-0.3 criterion; 2023H2 caught the rally at +1.79.
Ships the machinery, claims no edge. What would test the DESIGN is the registry's absent feeds --
XAUUSD 5m, EURUSD 30m, BTC 15m -- which take N to 5 across three asset classes. Two repository
notes: `research/metrics.py` has an IndentationError at line 178 and cannot be imported; and the
pipeline modules push `research/` to the front of sys.path, so a skill directory must be inserted
AFTER them or its `metrics` / `splits` are shadowed -- the fourth name-shadowing bug this session.
`docs/ib/STUDY_TREND_ENSEMBLE.md`.

**NO DECLARED INDICATOR RAISES THE 07:00-11:00 SCALP'S LOCKED PROFIT FACTOR, AND THE ONE RESEARCH SURVIVOR IS ADX -- WHICH INVERTS AGAIN.** Asked for a +25% lift in LOCKED PF: 38 conditions in eight families at the signal bar, each against a same-selectivity random filter on research, BH at q 0.10, survivors read ONCE on locked. Base (15m, 07-11 NY, Donchian **10/10** -- the Optuna log's '7/8' was the evaluator clipping to CH_MIN=10, corrected in the shipped Pine -- 3.19N, 2.3 ATR target, 230-min hold): research PF 1.164, locked 1.110. **Best in-sample lift in the pool is +12.3%**, half the ask; 3 of 38 clear p<=0.05 (1.9 expected); only `ADX>=20` survives BH, and on locked it reads **1.110 -> 1.047 (-5.7%)**, total +6.0% -> +2.1%, random filter p 0.764 -- V39/V52/V60's inversion reproduced on a scalp. Its mirror `ADX<20` is the pool's worst research row (PF 0.79), which is why the floor looked strong. The clock is the next best (08:30 start +8.6%, p 0.012; before-09:30-only -17.1%, the pre-open block subtractive a fourth time) and fails correction; participation floors are -0.4 / -15.9%; the bullish CVD patterns that carried V54/V55 at 30m are -4.4 / -2.6% here; RSI>=55 passes 82% of the signal bars, MACD>0 90%, +DI>-DI 94% -- the trigger restated. A +25% lift in locked PF is not a filter-sized effect on a coin-flip base whose edge is its exit geometry. See `docs/ib/STUDY_SCALP_FILTERS.md`.

**A PRIOR-SESSION TPO SINGLE PRINT OVERHEAD IS THE FIRST FILTER TO LIFT THE 07:00-11:00 SCALP'S LOCKED PROFIT FACTOR BY A QUARTER, AND EVERY OTHER PROFILE, EMA AND ATR READING FAILS.** 45 causal features (18 volume-profile from the 1-minute file, 14 TPO from 30-minute letters on 2.5-point bins, 7 EMA, 6 ATR; truncation audit and `volprofile.leakage_check` clean), 43 entry conditions against a same-selectivity random filter, 37 target rules against a random target at the SAME distance distribution, 27 stop rules in three units, one locked read. `prior-session single print within 3 ATR above the close` is the ONE BH survivor of 43 (6 at p<=0.05 vs 2.1 expected): research PF 1.164 -> **1.446** (p 0.000), locked 1.110 -> **1.382 (+24.5%, p 0.016)**, Sharpe 0.73 -> 2.02 on 187 trades, positive every calendar year, decaying across the split. Mechanism: MAE 3.69 vs 4.44 ATR outside with MFE unchanged -- the breakout heads into a zone yesterday's auction crossed in one letter. It can only exist below yesterday's high, so it co-selects `below the prior RTH high` 100%, and the drop-one settles it: below-the-high WITHOUT a near single print reads PF 1.04 research / 0.81 locked. The ladder is a HUMP (2 ATR 1.30, 3 ATR 1.45, 4 ATR 1.32, 5 ATR 1.24) with the 3-6 ATR bands NEGATIVE, so the ceiling was chosen. **EMA200 as support fails every reading** (above-and-within-1-ATR is the family's WORST cell, PF 0.93); **every bullish EMA 13/48 reading LOWERS PF** (state passes 74% of breakout bars; fresh cross 0.99, p 0.82) and the only reading that clears research is the COUNTER-state, 13 < 48 (1.31, p 0.020, fails BH); **no profile level beats the fixed 2.3 ATR target** (the IB high clears a same-distance random target and still loses, 1.139 vs 1.164); the fixed stop ladder peaks at 3.0 ATR in %/trade, R AND return/DD together, and every structural stop (below VAL / POC / IB low / HVN / EMA) is <= the fixed multiple it falls back to. Caveats attached: one market, one geometry, locked bootstrap P(mean<=0) **0.056** so it clears its control and not zero, MC p99 drawdown **2.8x** realised. Two audit catches: a prior-session value assigned only on days that already had RTH bars (8/12 probes failed) and early-close sessions never frozen (found by the Pine parity diff at 99.4%, now **100.00% on 70,685 bars**). `research/inst/vp_tpo.py`, `pine/inst/VP_TPO_SCALP_strategy.pine`, `docs/ib/STUDY_VP_TPO_SCALP.md`.

**THE SINGLE PRINT IS A 2023-2025 NASDAQ REGIME, AND THE LOPEZ DE PRADO NUMBERS SAID SO BEFORE THE READS.** A specialist's handoff on the VP/TPO study was executed in its own order. Tier 0: gated locked R/trade **+0.037** (t 0.75) against +0.053 %/trade -- half the edge at constant risk; the shipped gated run was already the single-walker veto build (`O._walk` skips a vetoed signal without taking the lock; 32 lock-freed locked trades read PF 0.92); a DAY-CLUSTERED random-filter null moves locked p from 0.008 to **0.044**. Deflated Sharpe on research **0.57 at 43 trials, 0.33 at 152**; MinBTL 495-661 days against 599 held; power at the locked R-effect ~1,300 trades. Tier 1: the single print survives EVERY bin definition (1-10 points, price-proportional, ATR-scaled: 67 of 72 cells clear on research) so it is not a resolution artefact -- and **CSCV over the 360-cell construction x stop grid gives PBO 0.519**, the population uniformly positive and the ranking inside it worthless. The extension variables carry no conditional IC inside the gate (-0.09..+0.02), which closed the moving-average question; the stop inside the gate still peaks at 3.0 ATR; the day effect (+1.16 vs -0.23 ATR on research, p 0.012) does not replicate on locked (p 0.67). Tier 2, pre-registered and read once with a scale-invariant bin (0.10 x session ATR) and a 4 ATR ceiling: **US100 BEFORE 2022-12-26, seven unseen years of the same index, PF 0.907 on 1,092 trades against a base of 0.970, worse than a random filter (p 0.90); US30 2016-2025 PF 0.927 against 0.973 (p 0.83)**; it reproduces only on the SAME WEEKS of US100 (1.354, p 0.004), which is feed parity and not evidence. All three MA cells negative on both unseen blocks. The short mirror clears its research control (p 0.020) at PF 1.05 and is not worth a read. **The gate now ships DEFAULT OFF.** A rule that holds where it was chosen and fails everywhere it was not is the mirror image of V12/V38/V52 and the same lesson: two blocks of one index over one calendar are not two tests. `research/inst/vp_next*.py`, `docs/ib/STUDY_VP_TPO_NEXT.md`.

**A MECHANISM-FIRST PRIMARY WAS BUILT AND KILLED BY ITS OWN GATE 1 IN ONE SESSION, AND THE CONDITIONING VARIABLE IS WHAT KILLED IT.** The levered-ETF close rebalance, chosen from the mechanism catalogue because it is the only entry derivable from OHLCV alone: a fund with leverage L and NAV N must trade `L*N*r*(L-1)` into the close to restore its daily multiple, and every coefficient `L(L-1)` is POSITIVE for L>1 AND for L<0 -- so long-levered and inverse funds all buy an up day and sell a down day. **The side is sign(r), forced by arithmetic, zero fitted thresholds**; the one declared parameter is the observation time. Causality audit 0 mismatches. **Gate 1 FAILS on every market**: US100 8.9 yr 2,074 events **-0.00864 %/event p 1.000**, US30 8.7 yr 2,045 events **-0.01186 p 1.000** -- and it is NOT cost, because GROSS is +0.00055 on US100 (the round turn is **1,662%** of it) and NEGATIVE at -0.00611 on US30. **THE DECISIVE EVIDENCE IS THE RELAXED GATE**: the mechanism says flow is proportional to |r|, so the upper half of |r| must be where the edge is, and it is where the losses are (US100 -0.01563 vs -0.00164, US30 -0.01841 vs -0.00531), with the quintile gradient running the wrong way on both -- **the mechanism's own conditioning variable predicts the opposite of the mechanism**. Granularity is not the hiding place: on NQ 1-minute, tightening to the last FIVE minutes leaves gross at +0.00111. Not drift either (always-long -0.00005 / -0.00761). The SIDE FLIP is positive (US30 p 0.010, US100 p 0.086) and is **recorded, not adopted** -- it is the second of two looks, and writing a new mechanism story around it is precisely the failure the architecture exists to prevent. 14 trials counted; no deflation needed because nothing survived to deflate. **Cost of the verdict: one module, two scripts, no features written, no holdout spent** -- against `STUDY_VP_TPO_SCALP`, where the same answer took 45 features, 152 looks and a cross-market read. What would reopen it: actual levered-ETF AUM and flow, or single-stock/sector ETFs where levered AUM is large against underlying liquidity. See `docs/ib/STUDY_LEV_ETF_REBALANCE.md`.

**OPTUNA IN 07:00-11:00 WITH A FOUR-HOUR CAP: TWO OF THREE RESEARCH RANKINGS ARE NEGATIVELY CORRELATED WITH THE LOCKED RESULT, AND THE ONE SURVIVOR IS A COIN FLIP WITH A SMALL EDGE.** 3,600 TPE trials over 5/15m x entry 5-120 x exit 3-80 x stop x target x hold 5-240 min x adaptive x MA x CHOP x PSH, research only. The constraints alone take the cell from research +19.5% to **+5.4%** (PF 2.50 -> 1.42) and it then fails a locked random-entry control (p 0.285). Populations: total and PF>=100/yr are **35% locked-profitable** with corr(research, locked) **-0.182 / -0.065** -- selecting on research is worse than not selecting, V30's shape reproduced. Finalists: the PF optimum INVERTS (research 1.53 -> locked **0.84**, MA floor at the box edge); the Sharpe optimum survives on 37 trades and fails its control (p 0.32); the total optimum -- **15m Donchian 10/10, 3.19N, 2.3 ATR target, 230-min hold, no filters** -- is the only one clearing a random entry in the window on BOTH blocks (locked p 0.040 / 0.015): **PF 1.13 at a 49% win rate on 387 trades, +6.9%**, with a 20% locked-positive neighbourhood and its channels at the evaluator's floor (the search's 5-9 range was clipped). 5m bars were searched and chosen by none of the three objectives. fANOVA: stop 0.70 / 0.29 / 0.64. Fourteenth confirmation that a window plus a hold cap costs most of a trend rule's edge. See `docs/ib/STUDY_BAYESOPT_SCALP.md`.

**BAYESIAN OPTIMISATION BUYS THE OBJECTIVE YOU NAME AT THE COST OF THE ONES YOU DON'T -- and on the Donchian family the only optimum that held was the one that traded profit factor for count.** 3,700 Optuna trials (three multivariate-TPE studies of 1,200 on research total / PF at >=100 per yr / Sharpe, plus a 100-trial Gaussian-process study) over a continuous space the 504k grid could not reach, research block only, finalists read once on locked and then scored against a random entry with their own geometry. PF finalist: research 2.59 -> **locked 1.59** (the cell reads 1.93), stop at the box edge (0.61 of [0.5, 4]), control p 0.170. Sharpe finalist: research **7.38 -> locked -2.22, PF 0.72** on 41 trades, three parameters at box edges, ranking Spearman **-0.03**. GP finalist: **five parameters at box edges** (entry min; exit, stop, target, hold max), a random entry with its geometry earns +20.6% research / +10.6% locked on its own and it fails its research control (p 0.270) -- the optimiser rediscovering 'be long as much as possible'. **fANOVA: the stop carries 0.90 / 0.78 / 0.56 of the total / Sharpe / GP objectives** -- an optimiser told to make money here mostly learns to widen the stop. The one real finding: the TPE-total finalist (RTH, **11-bar** entry, 47 exit, 3.8N, 3.2 ATR target, ~1-day hold, NO filters) is a different strategy in the same family -- ~320 trades/yr at PF 1.36-1.41 -- that earns **+27.3% locked against the cell's +8.1%**, top-10 neighbourhood 100% locked-positive at +22.0%, and **clears a random entry on locked at p 0.010 / 0.000** (control +4.5%). The cell itself, controlled for the first time, reads locked **p 0.050 / 0.090** -- borderline. Nothing reaches PF 2 out of sample at any count. See `docs/ib/STUDY_BAYESOPT_DONCHIAN.md`.

**CONFORMAL PREDICTION CERTIFIES THAT NO TRADE OF THE DONCHIAN CELL IS PREDICTABLY PROFITABLE, AND MORE DATA DID NOT CHANGE THAT.** Conformalized quantile regression (Romano-Patterson-Candes) on LightGBM quantile pairs plus V28's regularised random forest, trained on the WHOLE Donchian-55 RTH family (2,693 labelled bars, uniqueness weights for concurrency 2.0) rather than the cell's 192 trades, with the 37 audited e48 features, purged/embargoed folds and shuffled twins. Coverage lands 0.79-0.91 per fold and **0.89 on locked against a 0.90 target**, so the calibration is right -- and the calibrated 90% interval on a trade's R is **+/-4.6 R wide** (Q 3.4-5.5 per fold, 4.62 locked): the lower bound is below zero, and below -1 R, on EVERY trade in both blocks, and the predicted median R is negative on every trade (a 23% win rate stated back). AutoBNN's failure was not calibration; it was predictability. The random forest is the best of a null lot for the third time (V28, EMA48, here): research IC **+0.118** against its twin's -0.127, **+0.027 on locked**; its top-60% rule reads PF 3.04 vs a random subset's 2.51 (p 0.138) and, read descriptively on locked, raises PF 1.92 -> 2.29 while cutting total **+8.02% -> +5.17%** -- count traded for ratio, not an improvement; its '> 0' rule keeps 4 of 105 locked trades. Sizing by its rank moves the locked total +0.4 points and the research total -1.5. See `docs/ib/STUDY_CONFORMAL.md`.

**AUTOBNN ADDS NOTHING TO A DONCHIAN BREAKOUT, AND ITS FORECASTER IS NEGATIVELY INFORMED ON THE BARS THE STRATEGY FIRES ON.** Google's compositional Bayesian neural network re-implemented in torch (the reference needs the full TensorFlow stack): linear/periodic/RBF/Matern leaves under sum, product and changepoint, ELBO structure search, mean-field VI, sampled posterior predictive; positive control passes at the noise floor (`linear+periodic` on a trend plus cycle, RMSE 0.099 vs sd 0.10). On the Edge Finder's 55/30 cell (research PF 2.495 / locked 1.916): as a FORECASTER GATE the structure rotates every fold, the 26-bar forecast has IC **-0.070** on the signal bars with mean P(up) 0.242 (a breakout read as an excursion to revert -- the twelfth route to mean reversion here), and every threshold is worse than the base AND worse than a random filter (p 0.77-0.97); the pre-declared locked read goes 1.916 -> 1.416 on 19 trades. As a BAYESIAN META-LABEL on eight causal features the OOF IC is **+0.071 against the shuffled twin's +0.068**; one rung of five clears a random subset (keep-70 p 0.023) with its twin a whisker behind; the 'confident' rule (mean - sd > 0) keeps **2 trades** because the posterior sd exceeds the mean almost everywhere -- honest and useless; and the pre-declared locked read **kept 105 of 105** because every locked posterior mean sat above the research cut: the outputs are NOT CALIBRATED ACROSS THE SPLIT, so no research threshold means anything out of sample. A grammar that picks a different structure in every fold has found the noise. See `docs/ib/STUDY_AUTOBNN.md`.

**PF 2.0 AT 200 TRADES A YEAR INTRADAY DOES NOT EXIST ON THIS DATA, AND THE FRONTIER SAYS WHERE IT STOPS.** Asked for it directly: 2,792,878 intraday configurations (V61 tensor with 2/4/6.5h hold caps and RTH entries, NQ 5/15/30m, >=40 research trades) contain **ZERO** cells at PF >= 2.0 and >= 200 trades/yr ON THE RESEARCH BLOCK, where 89.5% of cells are profitable and the best reads PF 7.3. PF >= 2 exists in 442,847 cells at a MEDIAN of 31 trades/yr. The envelope of best research PF by minimum count, then that cell on locked: >=100 **2.173 -> 1.514** (the only one that holds), >=150 1.824 -> 0.754, >=200 **1.616 -> 0.878**, >=300 1.458 -> 0.981, >=500 1.236 -> 0.982. corr(PF research, PF locked) +0.149 over 2.79M cells; top 1% 3.48 -> 1.22 = the population's 1.22. DSR of the best cell 0.87 at N = 2.79M and it reads PF 0.90 locked -- the DSR prices multiplicity, not regime. The ARITHMETIC: PF 2 needs a **+16 to +20 point** win-rate lift over the driftless base at every geometry after costs (w* = 2(1+c)/(2(1+c)+q-c)); the best honest lifts here are +1 to +5. The hold cap costs only 0.06-0.09 PF (2h vs swing) -- the COUNT is set by the entry, and every cell above ~150/yr loses its PF out of sample whatever it holds. **THE STRONGEST HONEST OBJECT IS A BOOK**: the seven leg x feed pairs positive on research (FTM NQ, APM NQ/US100, TFI NQ/US100, trend-day NQ/US100; daily-return correlations 0.01-0.19) pool to **129 trades/yr PF 1.402 Sharpe 2.13 research, 186/yr PF 1.608 Sharpe 2.87 reserved** -- needing +15.3 points of win rate for PF 2, with 73-91% of net in the top 5% of trades and the wrong (better-OOS) shape. **META-LABELING WITH AN R-REGRESSION OBJECTIVE** (the tail-preserving form V28/V32/EMA48 called for) on the 344-trades/yr envelope cell: OOF IC +0.03, the shuffled twins read PF 1.46/1.51 at keep-60 = the real models, nothing clears a random filter, and the pre-declared locked read INVERTS (base 1.051 -> kept **0.865**, IC -0.015). p90 of R rose 5.19 -> 6.53 in the kept set, so the objective did keep the tail; there was nothing to keep. Ridge's top coefficient is RSI14 at -1.31, the eleventh route to mean reversion. See `docs/ib/STUDY_INSTITUTIONAL_FRONTIER.md`.

**A PULLBACK-TO-THE-EMA GATE ON A BREAKOUT HAS A LIFT BELOW ONE, AND THE PLATEAU THAT SURVIVES IT INVERTS OUT OF SAMPLE.** The submitted Turtle Scalp (US30 15m, 07:00-11:00 NY, 2R target, 4 units, armed stop, 11:00 flatten) transliterated with its own order model -- **899 locked trades against the script header's 898** -- then given EMA150 as trend side, a 20/50 cross aligned with EMA200, and a pullback to EMA20 before the Donchian fires. Base rates first: EMA150 passes 85.8% of breakout bars, the 20>50>200 state 58.3%, and the pullback **0.66-0.94x** -- a breakout bar is away from its EMA20 by construction, so requiring a recent touch keeps the STALLED ones. Alone the pullback turns the script negative (PF 0.981) and a random filter of the same selectivity beats it in **100% of draws**; the full ask fails its control (p 0.837) and reads locked **PF 0.949**, test 0.831, worse than the ungated script on US30, US100 and NQ. The drop-one consensus -- EMA150 + 20>50>200, no pullback -- clears its research control at **p 0.000** with a PERFECT PLATEAU (six EMA-length neighbours PF 1.21-1.29, Sharpe 1.09-1.34) and then reads **US30 locked PF 0.848, Sharpe -1.12, test PF 0.717, random filter p 1.000**, bootstrap P(mean<=0) 0.911. Fifth perfect plateau on this branch to fail out of sample. EMA150 is REDUNDANT once 20>50>200 is on (identical trade set). No take profit beat the 2R target for the eighteenth time (+0.339 vs +0.190 R); removing the flatten is positive on every held-back block but is an overnight strategy. The script sets NO commission and NO slippage -- its own report is at zero cost, and 2x the real cost takes the ask to PF 1.001. Ships with all three gates as inputs, DEFAULT OFF. See `docs/ib/STUDY_TURTLE_SCALP_EMA.md`.

**V54'S CVD SPLIT REPRODUCES ON A DIFFERENT BASE AND A DIFFERENT TIMEFRAME: THE TWO BULLISH PATTERNS WORK, THE TWO BEARISH ONES DO NOT.** The four patterns added as the confirmation at a level (50% session midline + 1H/4H swings, NQ 15m, 1.5N stop + 1/1 ATR trail), each tested SEPARATELY per `STUDY_V55`: sellers exhaustion (price LL + CVD HL) research +0.0085 PF 1.102 / locked +0.0051 PF 1.044, sellers absorption (price HL + CVD LL) +0.0089 / +0.0034 -- both positive on both blocks and DECAYING across the split -- against buyers exhaustion **-0.0127 / -0.0142** and buyers absorption -0.0066 / -0.0007, both NEGATIVE on both. Same two winners, same weakest member (absorbed buying) as V54 found on a Donchian breakout at 30m. **CVD is the only confirmation tested here that takes the rule above break-even** (levels alone -0.0042, + bubble -0.0070, + CVD +0.0085, + both +0.0179 on n=270) **and none of it clears a random-entry control** (research p 0.220/0.240, locked 0.535/0.685). The k x w neighbourhood falls monotonically as the recency window widens at every pivot width, reproducing V55's shape. **And the flatten costs money in 7 OF 7 WINDOWS** (09:30-11:00 +0.0160 -> +0.0083; all hours -0.0070 -> -0.0091), the thirteenth confirmation. See `docs/ib/STUDY_ABSORPTION_LEVELS.md`.

**A TRAILING STOP IS A TAKE PROFIT WEARING A STOP'S NAME, AND ON THIS BASE IT IS THE ENTIRE RESULT -- ON A COIN FLIP TOO.** The 50% session level + 1H/4H ICT swings + absorption bubbles, combined as a reversal system on NQ 15m: as specified (1.5 ATR stop, 1.0/1.0 ATR trail) it reads research **PF 0.920** and locked **0.778**, losing on both blocks, and a RANDOM ENTRY with the identical stop and trail beats it on both (p 0.865 / 0.990). TIGHTENING the trail improves every statistic monotonically -- 0.25/0.25 ATR gives **PF 1.751 at a 75.2% win rate on a 1-BAR median hold** -- and that is geometry, not signal: the random entry with the same trail reads 1.617 / 73.7%, clears at p 0.045 on research and then **WINS on locked** (rule 1.684, random 1.787, p 0.610). **~46% of that cell is the intrabar tie-break** (0.25 ATR = 5.7 pts on NQ 15m; stop-first instead of Pine's path takes +0.0237 -> +0.0129), reproducing the sub-0.5-ATR rule on a TRAIL rather than a barrier pair. NOTE THE SIGN IS OPPOSITE to `STUDY_EMA48_VWAP_DL`, where a trail was destructive at every setting -- same root cause, the trail's distance relative to the BAR'S OWN RANGE sets the win rate before any signal is consulted. **BOTH FILTERS SUBTRACT**: drop-one gives full rule +0.0034 / PF 1.061, minus absorption **+0.0096 / 1.181**, minus the levels +0.0088 / 1.159 -- the conjunction is worse than either half. **And the published absorption threshold is nearly unconditional** (`scaledVol >= 0.1` passes **78.7%** of bars; the A-E buckets only change the DOT SIZE), though unlike RSI/Aroon/MACD/MFI on a breakout it is NOT the trigger restated -- its lift on level-touch bars is a real 1.15-1.55x. Removing the trail is NOT the fix here and the grid marginal saying so is degenerate: the design has only a stop and a trail, so no-trail cells hold to the stop (110 trades, 1.8% win, 20-bar median). Given a real exit instead, every no-trail arm is worse. See `docs/ib/STUDY_ABSORPTION_LEVELS.md`.

**`strategy.exit` PLACED ON THE SIGNAL BAR ARMS ONLY THE TRAIL THERE, AND THAT WAS WORTH 1.1 PF ON THE SCALPING SYSTEM.** Calling `strategy.exit(..., stop=slPrice, limit=tpPrice, trail_points=..., trail_offset=...)` on every bar including the one the entry fills is standard Pine, and it is a trap: `slPrice`/`tpPrice` are set from `strategy.position_avg_price`, which does not exist until one bar AFTER the fill, so on the FILL BAR ITSELF the position carries a live TRAIL and NO hard stop, no target -- while the trail's own distances were captured before the entry and are already known. The first transliteration of the submitted NQ Scalping System left the fill bar fully naked instead (no trail either), understating it: NQ 15m research **PF 0.669 -> 1.739**, win 46.1% -> 70.3%, same rule and costs, verified trade-for-trade against an independent Python reference. A 15-minute bar's median range (19.0 pts) exceeds the 15-point trail-arm distance, so the trail activates **inside the fill bar on ~62% of entries** -- a third of all trades exit there, 100% winners by construction. It still does not clear a matched control (15m p 0.18-0.21; 5m passes only on the block that would select it). Any script whose exit order references `strategy.position_avg_price` needs its FILL BAR modelled with exactly the pieces that are actually non-`na` there, not as fully protected and not as fully naked. See `docs/ib/STUDY_SCALP89.md`.

**AN ATR TRAIL ON AN ATR STOP INVERTS THE GEOMETRY JUST AS A FIXED-POINT ONE DID, AND DEEP LEARNING
ON THE RESULT REPRODUCES V28 LINE FOR LINE.** Asked for EMA 13/48 x VWAP-as-support/resistance x
1.5 ATR stop x trailing stop, then feature engineering and deep learning for a profitable intraday
strategy. A declared 24-cell grid (cross fresh/state x VWAP off/state/touch x trail on/off x
flatten on/off) on NQ 5m: **trail ON averages PF 0.201, trail OFF 1.309**, every trail-on cell PF
0.15-0.23, and the random-entry control band with the trail is **entirely negative
[-0.0664, -0.0563]** with the rule slightly WORSE than random inside it (p 0.937). The trail
ladder improves monotonically as it WIDENS (arm 0.5 / off 0.5 PF **0.03**; 2.0 / 2.0 0.77) and
never reaches no-trail; the stop ladder 1.0 -> 3.0 ATR is flat and negative (V18 stands). Without
the trail the intraday base is break-even (PF 1.02, random entry p 0.163); the only cells above PF
1.3 are no-trail NO-FLATTEN -- 99-224 trades at **1-3% win rates**, multi-day longs in a market that
rose 89%. The VWAP STATE gate is the one component with a positive marginal (+0.03 %/trade); the
TOUCH reading is the worst of three. **37 causal features in 8 families, truncation audit 0 leaks.**
ML ladder (ridge/logistic -> LightGBM -> XGBoost -> MLP 2x64 -> MLP 4x128, purged + embargoed,
every model beside a shuffled twin): on the as-asked PF-0.19 base, **capacity is monotonically
harmful on the R objective (MLP 4x128 IC -0.038, AUC 0.47) and LOGISTIC REGRESSION WINS THE WHOLE
LADDER** (IC 0.141, AUC 0.625; locked IC 0.148, AUC 0.660) -- and the best subset it can find is
**-0.30 R at PF 0.32**: a filter cannot make a PF-0.2 base profitable, only less bad. On the
no-trail PF-1.05 base, **5 of 20 research cells clear a same-selectivity random filter at p<=0.05
against 1 expected** (LightGBM win p 0.034, MLP 4x128 win 0.010/0.050, XGBoost) -- and the
PRE-DECLARED locked read (logistic, best research IC) **INVERTS**: locked base +0.113 R / PF 1.164,
filtered 30% **-0.078 / PF 0.870** (p 0.844 vs random) while the classifier still ranks (IC 0.141),
because a win/lose model keeps the high-probability trades and a trend system earns in the
low-probability tail -- p90 falls 2.40 -> 1.85. **Read p90 of R, not AUC.** The research cells that
passed were NOT read on locked because the rule was fixed before any block opened; one read is one
read. Ridge's largest coefficient on the no-trail base is RSI14 at **-0.78** -- momentum NEGATIVE at
the signal bar, the tenth route to mean reversion here. Locked base 1.164 against research 1.052 is
the wrong shape for the base itself. **Operational**: two torch processes on four cores oversubscribe
threads and ran 31 minutes without producing a row that one process produces in twelve -- run torch
ladders sequentially or pin `torch.set_num_threads`. See `docs/ib/STUDY_EMA48_VWAP_DL.md`.

**THE DONCHIAN BREAKOUT ON GOLD IS A BULL-MARKET DRIFT EXPOSURE, AND A TWO-LAYER BUILD KILLED IT AT
BOTH GATES.** Full mechanism-first build on `XAU_ISO_15m` (clock re-derived NY+7, pre-2010 excluded,
three blocks: primary-fit 2010-2017, meta 2018-2022, locked 2023-2026 where gold rose **167.8%**).
600 Optuna trials on the primary block ALONE picked **SHORT-only** -- a fit to gold's 2010-2017 bear
-- and inverted: block B -0.00404 p 1.000, block C -0.06174 p 1.000. Five geometries FROZEN from
other markets x three sides: **0 of 15 cells clear p<=0.10 on block A and 0 of 15 on block B**; 4 of
15 clear on block C and **all four are LONG**. **GROSS-POSITIVE 14/15 ON BLOCK A AGAINST NET-POSITIVE
4/15 -- gold's cost floor is the binding constraint, not the signal**, and the 0.30 USD/oz round turn
is an assumption no feed here can check. The random-entry drift control prices the block-C passes
exactly as `STUDY_TURTLE` predicts: the breakout beats a coin flip with the same exits at p 0.000 on
C and on **0 of 4 cells on A and 1 of 4 on B** -- present only in the block opened last, the wrong
shape for the eleventh time. **THE META LAYER WAS AT THE NOISE FLOOR BEFORE GATE 2 RAN**: 28 causal
features (FFD fracdiff with **d = 0.7** chosen by ADF on block A only, 97-bar fixed window; a
Baum-Welch HMM fitted on block A and read **FILTERED** only -- filtered and smoothed labels agree on
96.4% of bars, which is why STUDY_V27's leak is easy to miss), truncation audit **0 mismatches**, and
OOF AUC **0.487 / 0.510 / 0.478** with **every IC negative** and the shuffled twins indistinguishable.
Gate 2 on UNSIZED returns: **0 of 18 declared cells clear**; best rf@70% p 0.122 and **p 0.198 against
a random filter of the same selectivity**; the logistic model's uplift falls MONOTONICALLY as it
filters harder. One read of block C: the filter adds **+0.00423 %/event at random-filter p 0.443**.
Corrected DSR curve **0.17-0.38** against E[max SR|null] 0.16-0.19 over 690 counted trials; White's
reality check **p 0.276 FAIL**. **AND `var_trials` DECIDES THE DSR, SO STATE WHAT IT IS MEASURED
OVER**: the first run printed **0.9919** because it was fed the variance of the 18 Gate-2 UPLIFTS
instead of the 639 trial SHARPES -- the same error class as the VP/TPO study with the opposite sign
(there it was estimated from annualised figures and came out too HARSH, 0.571 against 0.912). One
thing did work: block C kept **72.3%** against a 70% target, so purged embargoed CV on a properly
frozen transform DOES produce a score whose distribution transfers -- the opposite of
`STUDY_AUTOBNN`, where a research threshold kept 105 of 105 locked events. Second consecutive primary
killed at Gate 1. See `docs/ib/STUDY_XAU_TWO_LAYER.md`.

**A COST IS A FRACTION OF RISK AND ES IS THE CHEAPER CONTRACT IN DOLLARS AND THE DEARER ONE IN R.**
Asked for the IB-25 retracement on ES: **no ES series exists on this branch** (sixteen feeds, none
the S&P; US100/US30 are 15m and cannot resolve a 10:20 close or a 1-minute limit fill), so the ES
question was split into the half that is arithmetic and the half that needs bars. The rule sizes its
stop as a FRACTION OF THE MORNING RANGE, and a morning range is a percentage of the index -- median
risk **0.151% of price** over 527 NQ trades. At equal percentage risk an **MES round turn is 7.7% of
risk against MNQ's 3.2%, a factor of 2.37**, because ES's 0.25 tick is 0.0037% of a 6,800 index
against 0.0010% of a 25,000 one (3.7x) and the fee is spread over 2.5x fewer points. Re-charging the
NQ series at each contract's RELATIVE cost -- same bars, same trades, only the cost moving -- takes
research from -0.0099 %/trade PF 0.871 (MNQ) to **-0.0170 PF 0.796 (MES)**. Same trap as
`STUDY_TURTLE_15M` charging NQ's points in gold's. **But cost is not the binding objection**: the
rule is **negative GROSS at zero fee and zero slippage (-0.0047 %/trade research)**, so no broker or
contract size rescues it, and it still loses on the block that would select it while winning on
locked -- the wrong shape for the tenth time. Ships as `pine/ib25/IB25_RETRACEMENT_ES_strategy.pine`
with the post's defaults, no edge claimed, the numbers in the header, and the panel printing the
**driftless break-even beside the win rate** -- because the post's own best observation (stop to 75%
lifts the win rate 48.4% -> 66.4%) moves the break-even to 66.7% at the same time, and the win rate
tracks its own bound within 1.5 points at every rung of the ladder.
See `docs/ib/STUDY_IB25_ES.md`.

**CVD IS THE FIRST FEATURE FAMILY HERE TO PASS THE BASE-RATE CHECK AND IT STILL HAS NO EDGE ON GOLD,
AND ITS OWN POLARITY IS INVERTED.** 60 causal CVD features on a Donchian breakout in XAUUSD. Gold's
finest feed is 15m, so the delta is built from 15m SUB-BARS under a 60m chart (**4 sub-bars a bar**)
and a 240m chart (16) against V54's 30 on NQ -- and gold's volume is TICK VOLUME, so the proxy signs
TICK COUNTS where NQ signed contracts. Both degradations stay attached to every number.
**THE BASE-RATE CHECK PASSES FOR THE FIRST TIME**: only **2 of 120** feature cells pass >95% of
signal bars (one is the breakout distance by construction), against RSI's 94.7%, Aroon's 100.0%,
MACD's 99.8-100.0% and MFI's 91.7% -- CVD is a genuinely different reading of a breakout bar, not
the trigger restated, which is why the study was worth running. **THEN 13 OF 229 SCREENED CELLS
CLEAR p<=0.05 AGAINST 11.5 EXPECTED**, 1 survives BH, and **every continuous CVD reading has a
NEGATIVE mean edge** -- slope, z-score, rank, the bar's own signed delta, the sub-bar imbalance,
price-per-unit-delta and CVD-confirms-the-break all subtract (95 cells, 0 hits). Whatever is there
is in the discrete pivot patterns only. **THE SIGN STRUCTURE IS THE DECISIVE EVIDENCE AND IT IS
BACKWARDS**: on a LONG-only base the BEARISH patterns mean **+0.108** against the BULLISH ones'
**+0.009** -- 11x -- and `absorbed_buying`, the most bearish of the four and the ONLY row negative
on both blocks when V54 measured it on NQ, is the BEST pattern on gold (+0.1145, positive in 94.4%
of cells). A condition that works whichever way its own directional test points is not that
directional test; same class of evidence as `STUDY_LEV_ETF_REBALANCE`. **THE PIVOT-ONLY ABLATION IS
THE SECOND REAL POSITIVE**: strip the CVD comparison and keep only "a confirmed swing point occurred
in the last w bars" and the edge collapses to **+0.0027** (pivot low) / +0.0167 (any pivot) against
+0.066 / +0.122 for the specified patterns, beating pivot-only in 67% / 87% of matched cells -- so
the CVD is NOT decoration. But a COIN FLIP kept at the same fraction of pivots clears only at 60m
k2/w20 (p 0.013 / 0.050 / 0.090) and fails everywhere else (0.19-0.43), and every arm's pooled
block-C edge is NEGATIVE. What survives is ONE cell -- `exhausted_sellers k2 w20` at 60m, exactly
the pattern V54/V55 ship on NQ -- positive on all three gold blocks (+0.0799 p 0.020 / +0.0866
p 0.060 / +0.1621 p 0.065, PF 1.642 -> 2.197 on C, kept 36% against a 38% target so the selectivity
transfers). That is a near-replication on an independent market, not a result: one cell of 229, a
polarity-inverted family, and block C is a SECOND read of gold's locked block after
STUDY_XAU_TWO_LAYER's 690 trials. Truncation audit **0 mismatches**. **AND THE PARITY HARNESS CAUGHT A METHOD ERROR IN MY OWN
SCREEN**: the screen scored every feature as a SUBSET (split the ungated run's realised trades) and
a script can only run a VETO (the gate decides which bars may OPEN a trade, so refusing one releases
the position lock and admits a LATER breakout the ungated run never saw -- 82/56/34 such trades
earning -0.148/+0.062/-0.177). `STUDY_AUCTION`'s rule restated: filter the TRIGGERS and re-simulate.
Scored as a veto against a RANDOM GATE passing the same fraction of bars, also re-simulated, the
result is BETTER SHAPED than the subset framing: **research p 0.003 / 0.003 and locked p 0.110**,
PF 1.193 / 1.411 / 1.776 against an ungated 1.101 / 1.076 / 1.642 -- it clears both research blocks
and DECAYS on the locked one, where the subset framing had it growing. **It still loses TOTAL RETURN
on two blocks of three** (24.67->22.54, 12.03->26.97, 56.96->33.50) because it raises PF by removing
53% of the trades, which is STUDY_V61's finding reproduced. Pine parity: **100.00% identical exit
bars, per-trade correlation 1.0000, conservative on all three blocks**, with Pine's strict
`ta.pivotlow` agreeing with the research pivot set at Jaccard 0.9922. Ships as
`pine/xaucvd/XAU_CVD_DONCHIAN_strategy.pine` with the VETO numbers in the header and no edge claimed.
Finer delta scores weakly
better (240m div-family +0.069 vs 60m +0.014) while producing exactly chance hits, so resolution is
suggestive at best. **DO NOT RE-RUN the continuous CVD readings.** What would move it is 1-MINUTE
GOLD BARS. See `docs/ib/STUDY_XAU_CVD_FEATURES.md`.

**THE FLATTEN IS THE COST, NOT THE WINDOW -- AND AN OPTUNA RANKING WITH THE SESSION AXIS OPEN IS
NEGATIVELY CORRELATED WITH THE HOLDOUT.** The V61 CVD rule run as a user actually configured it
(07:00-11:00 New York + flatten, touch on, 15m and 30m). **Adding the flatten to an all-hours run
costs 0.4-0.5 PROFIT FACTOR on every timeframe and both blocks** (30m 1.784/1.611 -> 1.348/1.170 all
hours; 15m 1.570/1.869 -> 1.359/1.323) while adding the WINDOW alone costs little and on 30m locked
HELPS (1.683 / **2.853**, ret/DD 5.80). Fourteenth confirmation. **ON A 15-MINUTE CHART THE PRESET IS
A DIFFERENT STRATEGY**: the order-flow settings are in MINUTES so k3/w20 becomes k6/w40 with the same
time reach, but the CHANNELS are in BARS so 20/20 is HALF the time reach -- and the CVD is coarser
(15 sub-bars a bar against 30). 15m as shipped is the best-behaved leg measured (locked PF 1.869,
ret/DD 8.23, Sharpe 2.07, bootstrap P(mean<=0) **0.008 research / 0.003 locked**, the only leg
excluding zero on both), while the user's 15m + flatten reads **1.151 research / 1.859 locked** --
the wrong shape -- with research P(mean<=0) **0.314** and 67% of its jittered neighbours BEATING it.
**OPTUNA, 2,400 trials over two objectives with session start/end/flatten searchable, research block
only: corr(research PF, locked PF) = -0.458 and -0.417 Pearson**, top 1% by research PF 2.44 ->
**0.749** against the whole population's 1.099, and BOTH optima invert (PF optimum 2.472 -> **0.604**,
total -6.25%; ret/DD optimum 21.09 ret/DD -> PF **0.910**, total -2.12%). Ninth optimiser here to lose
to the author's constants, and a bigger box than STUDY_V64_OPTUNA's gave a worse result.
**THE PORTFOLIO IS THE ONE REAL IMPROVEMENT AND ITS CASE IS REGRET, NOT RETURN**: the two all-hours
legs correlate **0.36** in daily returns (against STUDY_HYPO's 0.87-0.96 and STUDY_TOP5's 0.90), the
best research leg (30m, ret/DD 10.02) COLLAPSES to 2.26 on locked while the best locked leg (15m,
9.58) was second on research, and the 50/50 is first on research (12.06, lowest drawdown of any arm)
and second on locked (6.06) -- it loses a strict ret/DD test out of sample and wins on Sharpe and
drawdown. Also: **the shipped script sets NO commission and NO slippage**, so a Strategy Tester
report is gross unless Properties is changed; measured cost is 4.6-21.9% of gross and worst where
the flatten is on. MC p99 drawdown 1.2-3.5x realised. See `docs/ib/STUDY_V61_SESSION.md`.

**THE V61 CVD RULE DOES NOT TRANSFER TO US30, AND ITS OWN GATE IS SUBTRACTIVE THERE.** Frozen --
geometry and 90/600-minute order-flow windows carried from NQ, nothing fitted -- and run on
`US30_LONG_15m` (193,942 bars, 2016-2025, sha256 24dcf2e1c7ba398f, byte-identical to the disk copy),
which chose none of it, so BOTH blocks are out of sample. **CVD needs sub-bars and this feed's
finest is 15m**, so the incumbent's 30m chart would get TWO sub-bars a bar; it runs on 60m with
FOUR, against the THIRTY the NQ result used, and on TICK VOLUME rather than contracts -- the same
pair of degradations `STUDY_XAU_CVD_FEATURES` accepted on gold. Result: PF **1.146 / 1.101**,
ret/DD 0.75 / 0.49 against NQ's 1.784 / 1.611 at 10.02 / 8.23; at MATCHED TIME REACH (10/10 on 60m =
NQ's 600 minutes) it is **0.943 on block B**. **ALL THREE NULLS BEAT IT**: a random ENTRY with the
same geometry earns 20.95 against the rule's 10.94 on block A (p 0.870 / 0.507), a random FILTER
keeping the same number of the ungated base's trades earns 22.81 (p 0.760 / 0.595), and ALWAYS-LONG
beats it on both blocks (15.12 / 29.55). Cost is 2.2% of the stop, so it is not cost.
**THE GATE CUTS BOTH TRADES AND EDGE**: gate OFF reads PF 1.265 / 1.143 at 21.96 / 14.42 pts a trade
on 568 / 353 trades against gate ON's 1.146 / 1.101 at 10.94 / 10.16 on 208 / 142 -- on NQ the gate
RAISED per-trade edge in 12 of 14 cells and only cut total return; on US30 it cuts both. **The NQ
FLATTEN finding does not replicate** (+0.081 block A, -0.091 block B, no consistent sign) but the
07:00-11:00 + flatten configuration is **below PF 1.0 on both US30 blocks** (0.965 / 0.883) with
bootstrap P(mean<=0) 0.568 / 0.651. **AND A DECORRELATED LEG STILL HAS TO HAVE AN EDGE**: US30
correlates only **0.226 / 0.105** with the two NQ legs in daily dollars and adding it takes the book
from ret/DD 13.34 / Sharpe 1.78 to **9.37 / 1.60** -- `STUDY_SEMIVARIANCE`'s finding reproduced on a
real leg rather than a simulated coin flip. What would settle whether this refutes CVD or only its
resolution here is **1-minute US30 bars**. See `docs/ib/STUDY_V61_US30.md`.

**THE STRONGEST META LAYER ON THIS BRANCH, AND IT STILL DOES NOT CLEAR OUT OF SAMPLE.** Full
feature-engineering pass on the V61 CVD rule at NQ 15m under the mechanism-first architecture: 51
causal features in 7 declared families from raw OHLCV, fracdiff and a causal HMM as META FEATURES
ONLY. **GATE 1 DECIDED WHICH PRIMARY WAS ELIGIBLE**: 15m all-hours clears both blocks (p 0.006 /
0.005) while 15m 07:00-11:00 + flatten FAILS research (p 0.330), so the meta layer was built on the
former -- building it on the latter is the move the two gates exist to prevent. Fracdiff d = **0.8**
by ADF on research only; HMM fitted on research and read FILTERED, with filtered and smoothed labels
agreeing on **96.8%** of bars, which is why STUDY_V27's leak is easy to miss. Truncation audit
**0 mismatches / 1,020**. Screen: **2 of 51 features pass >95% of signal bars** so the pool binds;
**9 of 51 clear p<=0.05 against 2.6 expected**, every family contributing at least one; **0 exact
duplicates** with correlation measured ON THE SIGNAL BARS -- and `vol.rv96` vs `regime.hmm_side`
reads **0.945**, so the HMM's sideways state is very nearly realised volatility, worth knowing before
crediting the Markov apparatus. Stability: **18 of 51 hold their sign across both research halves AND
all three volatility regimes** against ~6.4 expected; 8 of 10 family-first picks survive. Gate 2 with
a RETURN objective (not win/lose): rf OOF IC **+0.1637 against a shuffled twin's -0.0460**, and
**4 of 20 declared cells clear BOTH nulls**, best rf@40% uplift **+0.1101 at bootstrap p 0.006 and
random-filter p 0.007**. **DROP-ONE: ALL 8 FEATURES CONTRIBUTE** -- removing any one lowers the
uplift, `mom.roc240` by -0.150. **ONE LOCKED READ: PF 1.862 -> 2.707 on 56 of 125 events, uplift
+0.0538, and a random filter of the same size gives p 0.145** -- directionally right, not
significant. It kept **45% against the 40% it was set for**, so the score IS calibrated across the
split (the opposite of STUDY_AUTOBNN); total return falls **12.78% -> 8.74%** because it removes 55%
of the trades; and p90 of R in the kept set is BELOW baseline for all four models, so even a return
objective trims the tail slightly. Deflated Sharpe **0.750** against an expected best-of-null 0.218
over 136 counted looks, White's reality check **p 0.011 PASS**. Ships nothing: 125 locked events
cannot separate a +0.05 %/event uplift from noise, and the fix is MORE EVENTS, not more searching.
**Both fracdiff z-scores are NEGATIVE**, the twelfth route to mean reversion here.
**WHAT SHIPS IS THE RIDGE SCORE, BECAUSE A FOREST CANNOT GO INTO PINE AND THE COUNT INVERTS.** The
linear score is positive at every keep fraction on BOTH blocks (locked 0.1267/0.1266/0.1281/0.1233
%/ev at PF 2.057/2.008/1.977/1.886 against a base 0.1022/1.862) and significant at none (p 0.187 to
0.334); the COUNT 0-8 is monotone on research (Spearman +0.667) and every locked rung falls BELOW
the unfiltered base (0.0889 / 0.0547 / 0.0263 at T>=3/5/6, p 0.75-0.84), so it ships visible and
not recommended. **THREE OF EIGHT RIDGE COEFFICIENTS HAVE THE OPPOSITE SIGN TO THEIR UNIVARIATE IC**
-- multicollinearity exploited conditionally, and the least stable part of the model -- so each
feature also ships as a standalone switch. **PARITY: the fracdiff weights match to 0.000e+00, the
FFD series to 8.9e-15 from bar 300 (the 0.51 correlation over ALL bars is warm-up and no event lives
there), the HMM filtered posterior to 1.0e-06 at matched ddof, and the ridge score's take/skip
decision agrees on 99.4-99.7% of events.** Two conventions recorded not hidden: Pine's `ta.stdev` is
POPULATION where pandas is SAMPLE (1.0052 at n=96, changes no decision), and the research shifted the
CVD by a FULL-SAMPLE minimum before the log -- it sits at bar 177 so it never binds, but it is not
causal by construction and the script uses an EXPANDING minimum instead.
Ships `pine/v65/V65_CVD_META_FEATURES_strategy.pine`, meta layer DEFAULT OFF.
See `docs/ib/STUDY_V61_FEATURES_15M.md`.

**A STOCHASTIC OSCILLATOR AND A SESSION VWAP ARE 83% THE SAME COLUMN, AND A PLAIN ATR TRAILING MEAN
IS A CLOCK.** VWAP + Stochastic + ATR built to spec on NQ 15m, 31,752 declared cells. **corr(%K,
(close - VWAP)/ATR) = +0.831**: the oversold cross sits BELOW the session VWAP on **92.6%** of its
own bars against 44.3% in general (lift 2.09x) and the short mirror sits above it on **94.4%**
(1.69x), so the VWAP cannot be an independent confirmation of the stochastic. Sixth confirmation-is-
the-trigger finding here after RSI 94.7%, Aroon 100.0%, MACD 99.8-100.0%, MFI 91.7% and EMA13>48
90.9% -- and the FIRST measured as a correlation rather than a pass rate, which is the sharper
instrument: use it whenever both readings are continuous. **THE TRIGGER DOES NOT BEAT A COIN FLIP**:
against a random entry with the same side, stop, target, hold cap, costs and position lock, **0 of 8
declared geometry cells clear p<=0.05** (best 0.43), and the two long cells that make money make
EXACTLY what a random bar makes (+0.0553 against +0.0581; +0.1518 against +0.1492). Long is
gross-positive 4/4 and short gross-NEGATIVE 4/4 in a market that rose 89% -- drift. **THE WIN RATE IS
ITS OWN BREAK-EVEN** (51.38% against a driftless 51.44%, 50.82 against 51.08) and **cost is only
1.4-2.9% of the stop**, so for once cost is not the objection: the barriers are hit by noise. The
marginal-consensus cell fails both nulls on research (0.482 / 0.530) AND locked (0.292 / 0.184),
GROWS on locked (wrong shape, twelfth time), reads n=42 / n=9, and is NEGATIVE on both research
blocks of US100 and US30 which chose nothing (PF 0.787 / 0.741) while positive on both their locked
blocks. Grid 37.1% profitable -- hostile by this branch's standards. No take profit won for the
NINETEENTH time; the hold cap is an inert axis; stochastic length and level span 0.008 %/trade.
**AND `atr / sma(atr, n)` IS NOT A VOLATILITY READING ON A 24-HOUR TAPE**: NQ's RTH ATR is 34.8
against 13.1 overnight (2.7x), so an RTH bar clears its own 50-bar trailing mean **98.9%** of the
time against 25.1% of overnight bars -- every rung of it is inert on any session-restricted trigger.
A CAUSAL TIME-OF-DAY BASELINE (mean ATR at this minute-of-day over prior sessions, min 20 obs) lands
at 51.4% within RTH. Same repair `STUDY_V32_FLOW_ML` made for volume; it is required for ATR too.
On that fixed baseline the ATR sign INVERTED AGAIN -- ceilings positive (`ceil<=1.0` +0.0062),
floors negative (`floor>=1.2` -0.0228) -- agreeing with STUDY_V28 and reversing STUDY_V63, the fifth
move. Parity 51/51 trades, correlation 1.0000, 98.04% identical exit bars, gap +1.7% / -0.2%.
See `docs/ib/STUDY_VWAP_STOCH_ATR.md`.

**THE INITIAL BALANCE MECHANISM IS ABSENT ON US30 AT EVERY RETRACEMENT DEPTH, AND 3,600 OPTUNA
TRIALS FOUND A LONG DRIFT EXPOSURE THAT DIES ON THE ONE BLOCK NOTHING TOUCHED.** Two-layer build on
`US30_LONG_15m` with the walker verified against the V58 tensor (945/945 and 989/989 trade counts,
838/847 days to the cent). As published: **-0.0167 %/trade, bootstrap p 1.000, GROSS NEGATIVE at
zero cost** (Gate 1 FAIL), and the mechanism's own prediction fails -- the retracement ladder that
was monotone on NQ (`STUDY_V58_ANATOMY`) is FLAT here at every rung (-0.008 .. -0.018), its control
p falling only because the CONTROL worsens. **A RULE THAT BEATS A LOSING NULL IS STILL A LOSING
RULE.** Optuna, research only: 62.6% of trials profitable, fANOVA 0.94 on the IB-range CEILING in
all three studies; the total optimum set the retracement to **0.007 -- it discarded the mechanism
and buys the break** -- and ALWAYS-LONG on its own days earns more (+0.0675 vs +0.0450, and +0.1222
vs +0.0426 on locked). One locked read: the PF optimum (90-min IB, retracement 0.455, both sides)
is the only finalist clearing a random entry (+0.0662, PF 1.57, p 0.002 on 91 trades), then
**US30_ISO's 288 post-2025-07 sessions, a different provider no search saw, read EVERY finalist
NEGATIVE** (-0.057 p 0.996 / -0.093 / -0.041 at a 2.2% win rate) with always-long negative too.
30 causal meta features (audit 0/1,200 after two construction artefacts of mine failed 80/1,200;
HMM filtered vs smoothed 96.0%; FFD d 0.3): 4/15 Gate-2 cells clear both nulls on research **with
the best model's OOF IC at -0.145** -- it ranks backwards and its top 40% is positive, V28's shape
-- and on locked the score is NOT CALIBRATED (keep 40% kept 15%) and that cell INVERTS. DSR 0.000
at 3,698 looks. **ON A CFD FEED THE FIRST BAR AFTER 15:55 IS THE 18:30 RE-OPEN on 1,247 of 2,246
sessions** (16:00 exists on 153): a flatten filled at 'the next bar's open' holds through the cash
close and showed as +0.087 R on BOTH sides -- exit at the last pre-cutoff close, submit the script's
flatten on the bar before, and run it on a 1-5m chart. Also: Pine's fill-bar path (green O-L-H-C)
PAYS A TARGET ON THE FILL BAR for a limit filled on the way down -- STUDY_V10's artifact on the
script side, worth +3% on the published cell -- so the parity harness models it rather than the
research adopting it. Ships `pine/ibus30/IB_US30_strategy.pine`, no edge claimed.
See `docs/ib/STUDY_IB_US30_OPTUNA.md`.

**A "VOLUME" COLUMN THAT DOES NOT CORRELATE WITH THE BAR RANGE IS NOT VOLUME, AND IT MAKES A SPEC
UNRUNNABLE BEFORE ANY BACKTEST.** The uploaded `XAUUSD15.csv` (= `XAUUSD15_MT`) has a sixth field
reading **exactly 15 on 99.62% of rows**, sd 0.185, correlation with the bar's own range **+0.0048**
against **+0.641** for `XAU_ISO_15m`'s real tick volume -- it is the bar's LENGTH IN MINUTES. Two
consequences are arithmetic: `V > 1.1 x SMA20(V)` fires on **33 of 100,000 bars (0.033%)**, and a
VWAP over a constant V **IS** the unweighted mean of the typical price. Check `corr(volume, high-low)`
before running any volume rule anywhere; the registry now carries the defect.

**THE BHATTI VWAP-EMA GOLD PAPER (SSRN 6650958) REPORTS NO BACKTEST, AND MEASURED ON GOLD IT LOSES
WHERE IT WOULD BE CHOSEN AND BEATS ONLY A CONTROL THAT LOSES MORE.** Its section 6.1 ASSUMES the
outcome distribution (full win 0.30 / partial 0.20 / breakeven 0.08 / loss 0.42) and Monte Carlos
it, so 45.3% win, +0.414R, PF 1.76 and Sharpe 3.99 are arithmetic from the assumption. Built
literally on `XAU_ISO_15m` (371,586 bars 2010-2026, research to 2020-05, gold's cost floor): LONG
research **-0.0447 R PF 0.916** on 378 trades -> locked **+0.1423 PF 1.318** on 214, GROWING out of
sample (wrong shape, 13th time); SHORT negative on both. **A random New York entry with the identical
stop, target, trail, costs and lock earns -0.2573 R on research**, so it clears its control at
p 0.0025 while losing money -- STUDY_IB_US30_OPTUNA's sentence from the other side. **THE ASSUMED
DISTRIBUTION IS WRONG**: the 3R target is hit on **12.4%** of trades against an assumed 30%,
INDEPENDENTLY ON BOTH SIDES, and **61.1% die on the trail at -0.190 R** -- the paper's four-outcome
table calls that a breakeven. **C2, THE VWAP CONDITION, PASSES 87.8% of the bars already satisfying
the other five** and C6 (range) 92.7% -- 7th confirmation-is-the-trigger finding -- while C3 (the
EMA50 pullback) at 29.9% is the only binding one; C4b engulfing supplies 84% of signals and the pin
bar 22%. **SECTION 7.4 IS DEAD CODE**: switching the EMA20 final-leg tightening off reproduces the
result TO THE CENT, because floating profit rarely reaches 2.5R before the trail fires. **THE VOLUME
WEIGHTING DOES NOTHING** (-0.0436 unweighted against -0.0447), STUDY_V63 on a third market. **THE
SPEC'S OWN ATR IS 5-8x TOO LARGE** -- it assumes $12-20 where the measured 15m median is **$2.35** --
so its 0.24R cost assumption is 2.3x the real 0.1032R, and the rule is POSITIVE GROSS (+0.0762 R)
and negative net: the round turn is the whole difference. **THE ONE COMPONENT CARRYING INFORMATION
INVERTS**: raising C5 from 1.0x to 2.0x is monotone on research (-0.0678 -> +0.3745) and beats a
same-selectivity random filter at every rung (p 0.030 -> 0.000), then reads **Spearman +1.000
research against -0.900 locked** with every locked rung failing its control (p 0.24-0.69). The
spec's own value is rank 2-4 of its own ladder on ALL EIGHT axes; the stop is monotone toward wider
(8th family), no target ties best (20th), the session flatten is destructive (15th). 9 of 16 years
positive, and **2024 -- the paper's own sample -- is the 2nd best year in sixteen** at +0.2440 R
PF 1.55 against its claimed +0.414 PF 1.76. **MY OWN BUG, caught by a plateau being too perfect**:
the first neighbourhood swept EMA and ATR periods against series CACHED in `build()`, so five rungs
returned identical numbers to four decimals. Parity: counts 0.998-1.000, R corr 0.978, same exit bar
96.6% -- and the close-only trail's structural gap (research exits AT the breaching close, a script
at the NEXT bar's open) moves the exit bar on **63% of trades** and the result by **~1% of R**,
because the trail fires on a close that already breached.
**AND 3,600 OPTUNA TRIALS ON IT FIND A GOLD RALLY.** Every free parameter swept on the research
block, three TPE studies, locked logged and never used: 62% of trials profitable, **fANOVA 0.85-0.90
on the VOLUME MULTIPLE in all three objectives** -- the one component whose gradient inverts across
the split -- with `tgt_R` the only other axis above 0.12 Spearman. ONE LOCKED READ of three
finalists plus the published rule: **all four beat a matched random entry (p 0.000-0.033) and NOT
ONE separates from zero** (day-block bootstrap P(mean<=0) 0.054 / 0.075 / 0.096 / 0.176, every 95%
CI containing zero) -- STUDY_V15_BOOK's split reproduced, because the random entry loses money.
**DSR 0.000 for all four at 3,660 counted trials.** MC p99 drawdown is 1.4-1.7x realised.
**94.4% OF THE BEST FINALIST'S LOCKED RESULT COMES FROM 2025-26**, when gold rose ~60%, leaving
**+0.015 R/trade** over 123 trades before it -- and the OPTIMISER MADE THE BETA EXPOSURE WORSE, the
published rule being the least concentrated of the four at 23.8%. Its ret/DD finalist collapses
**10.06 -> 0.85** out of sample; its best research cell is a SPIKE (6.7% of its own +-10% neighbours
beat it). Walk-forward with the selection re-run per fold reads +0.1490 against a random cell's
+0.0943 -- **and the whole advantage is ONE FOLD OF FOUR TRADES: excluding 2025 the random cell wins
(+0.1047 vs +0.0593)**, the eleventh re-optimiser to lose here. Year-to-year the totR finalist
correlates **+0.965** with the published rule and PF with ret/DD **+0.936** -- three "different"
optimised configurations are two strategies. **AND THE SIGNAL SET IS BROKER-DEPENDENT**: C5 alone
takes the long side from 904 trades to 592, and one XAUUSD feed's tick count is not another's, which
is why a Strategy Tester on a different provider shows a different trade count for identical rules.
Also resolved: the paper's own session is ambiguous -- "the New York session open (13:30 UTC)" is
09:30 NY only under DST and 08:30 in winter -- and the literal UTC reading is the BETTER of the two
(research -0.0229 vs -0.0447), so the headline used the less flattering one.
**AND THE FORMAL OVERFITTING TEST SEPARATES TWO THINGS THAT GET THE SAME NAME.** CSCV over 1,199
sampled configurations x 193 months, 16 blocks, all **C(16,8) = 12,870** symmetric splits:
**PBO = 0.561** -- the in-sample winner lands BELOW the out-of-sample median in 56% of splits, which
by Bailey/Lopez de Prado's reading means the selection procedure is ACTIVELY HARMFUL. The IS-best
cell's statistic goes **+0.2454 -> +0.0139** out of sample and **the slope of OOS on IS is -1.27**:
the better a configuration looks in sample the worse it does out of it, which is the fANOVA finding
(the search tunes the volume multiple, whose gradient inverts) reached from another angle. In a
13-fold walk-forward with the selection re-run each fold the optimiser is the WORST of three arms --
**+5.57 R against a random cell's +27.02 and the published constants' +15.56** -- the eleventh
re-optimiser here to lose to the author's constants and the first to also lose to a coin flip, with
its IN-SAMPLE totals climbing 13.5 -> 47.2 R across folds while OOS does not follow. **BUT THE
PUBLISHED RULE ITSELF IS NOT OVERFIT**: it was never fitted to gold, its median IS rank across the
12,870 splits is **0.444** (a below-median cell in its own grid), and its ten numbers rank 2nd-4th
of 3-5 on all eight ladders. Rolled forward with NOTHING re-selected (36m train / 12m test, 13
folds) it reads mean IS +0.0078 against mean OOS -0.0012 with **corr(IS, OOS) = -0.434** -- a
three-year window anti-predicts the next year even when nothing is fitted, so that is REGIME, not
curve-fitting. Distinguish the three questions: is the rule fitted (rolling WF with no
re-selection), is the search overfit (WF with re-selection), and what is P(overfit) (CSCV/PBO).
**RUN PER PRESET, THE GENERALIZATION GAP SEPARATES THEM CLEANLY AND NOT THE WAY YOU WOULD GUESS**:
the two EXHAUSTIVE-GRID winners are the overfit ones (sweep neighbourhood +0.285 gap, OOS -0.058 on
2/5 folds; sweep top row +0.266, OOS +0.081 on 4/7) while all three OPTUNA cells hold
(-0.023 / -0.008 / +0.062 gap, 10/13, 10/11, 9/12 folds positive) -- the maximum of a large discrete
grid buys a low-count cell, and those two support only 5 and 7 folds. Median in-sample rank among
1,199 pool cells: the five fitted presets 0.707-0.984, the PUBLISHED rule **0.443, below median**,
which is the cleanest single sign a configuration was chosen by convention and not by search.
**AND SYMMETRIC CSCV CANNOT MEASURE A FIXED CELL'S RANK DROP** -- for every split the COMPLEMENT is
also a split, so a fixed column's IS and OOS rank distributions are identical and both the
difference of medians and the median pairwise difference are IDENTICALLY ZERO by construction (my
first pass reported 0.000 for all six and that was the design, not a result). PBO escapes it because
its subject, the argmax, CHANGES with the split; for a fixed cell read the DISPERSION of the rank
swing and the walk-forward gap instead. Also: **putting cells fitted on the tested data INTO the
CSCV pool lowers PBO** (0.561 grid-only -> 0.465 with the five fitted presets), so the pool must
contain nothing chosen on that data.
**AND "IT HOLDS OUT OF SAMPLE" DECOMPOSES INTO SAMPLE SIZE PLUS BETA, NOT AN EDGE.** Asked why the
two Optuna presets kept their result while the sweep cells did not, four explanations were tested.
**corr(walk-forward folds, generalization gap) = -0.951** across the six presets (corr with trade
count -0.690): the two that "hold" are simply the two with the most trades and folds, and a gap
shrinks toward zero as its estimate gets less noisy -- arithmetic, not mechanism. Monthly R
correlates 0.22-0.30 with GOLD ITSELF and the beta term accounts for **24% to 113%** of each
preset's total R (112.7% for the published rule -- the whole result IS the exposure). **THE
DECISIVE TEST: on the SAME days, entering at the SESSION OPEN with THE SAME ATR STOP beats the rule
in 11 of 12 preset-blocks**, on per-trade R and on return-over-drawdown alike, and it cannot be
accused of more risk -- its worst trades match the rules' to two decimals (-1.06..-1.58 against
-1.05..-1.49). The six conditions select days on which gold rose and then enter LATE AND WORSE than
simply being there. **AND THE PRESET WITH THE SMALLEST GAP IS THE MOST GOLD-DEPENDENT**: Optuna
total-R earns **+9.17 R in folds where gold rose against +0.28 where it fell (32x)**, corr with the
fold's gold return +0.485, and it holds because gold rose in 9 of 13 out-of-sample folds. The two
SWEEP cells correlate **0.91** with each other -- one configuration with two names, which is why
they fail together. Before crediting any "holds out of sample", check the fold count, the beta, and
whether a naive always-in version of the same exposure beats it.
See `docs/ib/STUDY_VWAP_EMA_GOLD.md`.

**THE SAME RULE ON TWO EQUITY INDICES THAT HAD NO PART IN WRITING IT: NOTHING, AND THIS TIME IT IS
NOT COST.** Bhatti's VWAP-EMA spec frozen and run on `US100_LONG_15m` (206,703 bars) and
`US30_LONG_15m` (193,663), with `US30_ISO_15m` (48,937 bars, a DIFFERENT PROVIDER, 2024-08..2026-08)
held as a RESERVED FORWARD BLOCK no search touched. All three clocks RE-DERIVED (mean bar range
peaks at minute-of-day 570 = 09:30 New York on every one) and all three volume columns checked
(corr with bar range +0.71..+0.77 against the `XAUUSD15_MT` fake column's +0.005). **THE ROUND TURN
IS 2.5-4.3% OF RISK HERE AGAINST GOLD'S 17%**, so the gold verdict -- positive gross, negative net,
the cost is the whole difference -- CANNOT be the explanation; removing cost entirely still leaves
the rule within noise of zero. **TWO CELLS CLEAR A MATCHED CONTROL ON RESEARCH AND BOTH INVERT**:
US30 long +0.1975 R p 0.003 -> locked -0.0762 p 0.663, US100 short +0.0174 p 0.010 -> **-0.1509**
p 0.793; win rates run 22.9-31.5% against a 26.1% break-even at the 3R geometry, so the barriers
are hit by noise. Base rates: **C6 (range >= 0.8 ATR) passes 95-98% of the bars the other five
already admit** on every feed and both sides and C2 (the VWAP condition in the paper's title)
78-90%, while only C3, the EMA50 pullback, binds at 29-33% -- the rule is a pullback filter with
five decorations, the same reading gold gave. 4,800 Optuna trials on the two research blocks:
85-93% of every population profitable on research and **30-69% on locked**, and the top 1% of the
research ranking is AT OR BELOW the whole population's locked mean in three of six studies. One
locked read at a stated multiplicity of 4,840: all six finalists clear their control on research at
p <= 0.010, **NONE clears on locked (best 0.100) and none excludes zero (best 0.270)**; research
PFs of 2.48/3.54/4.02 land at 1.24/1.13/0.96. **THE DEFLATED SHARPE IS DECISIVE WHEN `var_trials`
IS MEASURED OVER THE TRIAL SHARPES**: 0.006178 over 4,116 scorable trials gives
**E[max Sharpe | pure noise] = 0.2892 at 4,840 looks against a best achieved 0.1446** -- the best
thing the search found is BELOW the noise floor. All six finalists independently chose NO TAKE
PROFIT (21st time); the three US30 finalists correlate **0.60-0.91** in daily R, one strategy with
three names. See `docs/ib/STUDY_VWAP_EMA_INDICES.md`, `research/vwapema/ve_markets.py`,
`run_m1.py`..`run_m7`.

**A META LAYER CANNOT RESCUE A PRIMARY THAT FAILS GATE 1, AND THE SHUFFLED TWIN IS WHAT SHOWS IT.**
The mechanism-first architecture run on the VWAP-EMA event stream. PHASE 0 FIRST: the rule names no
counterparty -- no constrained flow, no risk transfer, ten tuned numbers -- so it is a fitted
pattern carrying the full deflation burden. GATE 1, scored on percent of entry price before any
feature exists: **the primary passes on every block it was CHOSEN on and on none of the others**
(US100 short research p 0.013 -> locked 1.000; US100 long 0.025 -> 0.379; US30 long 0.083 -> 0.269;
forward 0.117). 51 causal features in nine declared prefixes, truncation audit **0/40**, and every
family's IC above its own shuffled twin -- unusual here. Then the ladder (ridge -> RF -> LightGBM ->
XGBoost d3/d6 -> MLP 2x64 -> MLP 4x128, purged and embargoed, objective = the RETURN): **13 of 14
real ICs are NEGATIVE and the SHUFFLED TWIN BEATS THE REAL MODEL IN 71% OF CELLS ON IC** (64% at
keep-30%, 50% at keep-50%). Above 50% the noise floor is higher than the signal; at 71% the models
rank events worse than random labels do. Capacity is inert again -- mlp 4x128 is no better than
ridge, the fourth family to show it. Gate 2 passes 8 of 42 cells and ALL EIGHT are the one primary
whose locked block reads **p 1.000 at -0.0029% of price**, so it is `STUDY_EMA48_VWAP_DL`
reproduced: a filter makes a dead base less bad, never alive. Deflation over M=42 kept candidates
(avg pairwise corr +0.007, effective N 41.7): best Sharpe/event +0.1936 against an
**E[max|noise] of 0.1021**, DSR **0.895**, and **White's reality check p 0.103 FAIL** -- the two
disagree because the DSR deflates ONE Sharpe and the reality check bootstraps the MAXIMUM over
candidates, which is the right statistic for a 42-candidate search.
**AND THE ONE THING THAT REPLICATES IS THE ANOMALY DIRECTION: AN EVENT ON AN UNUSUAL BAR IS A WORSE
EVENT.** Autoencoder reconstruction error (fitted on research only, never sees a label) has a
NEGATIVE rank correlation with the event's return in **9 of 10 feed x cell x block cells, mean rho
-0.093, including BOTH reads on the reserved forward block**; Mahalanobis 9/10 (-0.074), joint
outlier z 9/10 (-0.064), isolation forest 8/10 (-0.079). The supervised screen agrees from the
other side -- the two strongest single features are the CAUSAL TIME-OF-DAY constructions and both
are negative, `vlm.tod_ratio` **-0.219** and `vol.atr_tod` **-0.214**. That is a statement about the
rule's own C5 volume-spike condition, not a new filter, and it agrees with
`STUDY_DIVERGENCE_CONFIRM` (volume spikes hurt longs monotonically). CAVEATS THAT STAY ATTACHED:
the quintile means are NOT monotone, so the consistency is in the rank correlation only; and the
ten cells are NOT independent (six configurations, three feeds, two of them the same US30 data at
different splits, indices correlated 0.758 over one calendar), so nine of ten is nearer three
confirmations. The pre-declared locked read splits on CALIBRATION: US30's score keeps 50.7% against
the 50% it was set for and its p90 RISES, while US100's keeps **73.8%** and its p90 FALLS -- a
research threshold that does not mean the same thing out of sample, `STUDY_AUTOBNN`'s failure in a
milder form. **TWO CONSTRUCTION RULES EARNED HERE**: measure volatility and participation against a
CAUSAL TIME-OF-DAY baseline, never a trailing mean, because on a 24-hour tape an RTH bar clears its
own trailing ATR mean ~99% of the time; and a recursive filter that returns ALL-NaN reads as "no
signal" rather than as an error -- the first HMM did exactly that because 15-minute log returns are
~1e-4, the Gaussian emission reached ~400 and the scaled backward recursion divided by a scale that
had underflowed to 1e-300, fixed by standardising inside the fit. Also: `trn.above_slow` has a
coefficient of variation of EXACTLY 0.0000 on the event bars because `close > EMA200` IS condition
C1 -- the base-rate check catching the trigger restated for the eighth time.
See `docs/ib/STUDY_VWANOM.md`, `research/vwanom/`.

**THE THREE OVERFITTING QUESTIONS GAVE DIFFERENT ANSWERS ON TWO INDICES CORRELATED 0.758.**
Rolling walk-forward with NOTHING re-selected: `corr(IS, OOS)` negative in 6 of 8 rows -- regime,
not curve-fitting -- with the published rule's gap +0.003 on US100 and the two US30 grid winners at
**+0.63 and +0.70**. Walk-forward with the selection RE-RUN each fold looks like the first
optimiser win on this branch (US100 +0.858 against the constants' +0.099) and **IT IS ENTIRELY
PRE-CUT**: on the folds whose TEST window post-dates the research cut the re-chosen arm is the
WORST arm on both feeds (-0.174, -0.358), losing to the constants AND to a random cell -- twelfth
re-optimiser to lose here, second to also lose to a coin flip. **PBO IS 0.126 ON US100 AND 0.517 ON
US30** (above the half that means the selection is actively harmful) with the US30 in-sample winner
going +1.630 -> **-0.118**; the slope of OOS on IS is POSITIVE on both, where gold's was -1.27. The
published rule's median in-sample rank in its own 400-cell pool is **0.165 / 0.485, below median on
both** -- the cleanest single sign a configuration was chosen by convention, reproducing gold's
0.443.

**THE VOLUME MULTIPLE'S GRADIENT IS REAL, SURVIVES BOTH BLOCKS, AND CLEARS NOTHING.** fANOVA gives
it 0.22-0.46 of every objective and Spearman(vol_mult, R) is positive in 8 of 10 feed x side x
block cells (US30 long research **+0.964**, locked +0.929) -- the opposite of gold, where the same
axis inverted. Against a same-selectivity RANDOM FILTER re-simulated end to end, **0 of 70 rungs
clear p <= 0.05 where 3.5 are expected by chance**, best p anywhere 0.060 and best on any locked
block 0.180; removing the range condition C6 gives the same answer, so it is not that confound.
The mechanism is selectivity -- the ladder takes the kept share from 92% to 33% and the control
climbs with the rule (`STUDY_V12`'s ATR-expansion finding again). **AND THE TWO CELLS THAT ARE
GENUINELY UNSEEN ARE THE TWO WITHOUT THE GRADIENT**: on the reserved forward block the long ladder
is flat (rho +0.000) and the short ladder negative (-0.429).

**AND THE FRAMING TEST REPRODUCES ON THREE MORE MARKETS.** On the same days, same side, an entry at
the session open carrying THE RULE'S OWN ATR STOP beats the rule in **120 of 158** side x regime x
cell x block cells, mean edge negative in every one of the four side x regime cells (-0.103 to
-0.362) and on every feed. Note the control's own level before crediting an excess over it: a
session-open entry earns **+0.15 to +0.32 R on BOTH sides** in markets that rose 144% and 420%.
**The gold REGIME finding does NOT transfer**: a bull filter helped long in 6 of 6 gold presets and
helps only **2 of 7** US30-long locked cells, where bear-only is better in 5 of 7 -- and these
indices are 80.6-83.7% bull against gold's 63.4%, so there is barely a bear sample. Cross-market,
all three US30 finalists are LONG and all three transfer positively to US100 (one at p 0.047) while
all three US100 finalists are SHORT and two of three fail on US30 -- which is what drift predicts,
not an edge. One of six finalists survives the forward block (US30 total R, +0.157 R PF 1.311 on
325 trades, control p 0.103).

**AND THE INTRABAR CONVENTION IS THE LARGEST NUMBER IN THE STUDY, WITH NO CONSISTENT SIGN.**
vectorbt run as a TRANSCRIPTION CHECK first: letting the close-only EMA trail fire on the bar the
position filled costs 14-17% of the trade count on all three feeds (ratio 0.831/0.851/0.857 FAIL),
exactly as it did on gold (0.841) -- and the P&L then reads BETTER, so the COUNT is what catches
it. Blocked from the fill bar the counts match (0.987/1.000/0.982 PASS) and the same signals then
price **+86.8% on US100, +9.2% on US30 and -67.1% on US30_ISO** apart, because this branch takes the
STOP when an ATR stop and a close-only trail fall inside one bar and vectorbt resolves it by its own
order. `STUDY_V38` measured 2.1x and `STUDY_V41` 22.9x for the same class. A second engine is a
second opinion about EXECUTION, never a correction to the research.
**AND SPLIT BY REGIME, LONG-IN-BULL WINS EVERY PRESET AND SHORT IS NEGATIVE IN 18 OF 18.** A causal
regime label (gold's daily close against its own 200-day EMA, LAGGED one session; 63.4% of session
bars bull, but the locked block is 76.2% bull) applied as a FILTER and RE-SIMULATED, not as a split
of realised trades -- refusing a signal frees the position lock and admits a later one, so the two
readings are different questions. **Bull-only beats both-regimes on locked in 6 of 6 presets and
bear-only is worse in 6 of 6** (best cell Optuna totR long-in-bull +0.328 R on n=130); short is
negative in **18 of 18** locked cells. **But the bull preference is 4/6 on RESEARCH and 6/6 on
LOCKED**, and the two presets that disagree there are the published rule and the best Optuna cell --
a filter that is chosen where it may not be chosen is the wrong way round, and the locked block
being 76% bull is most of it. **The short side inverted**: short-in-BULL is the best short setting
on research (positive in 5 of 6) and the WORST of three on locked for 4 of 6. **AND CONDITIONING ON
THE REGIME RESCUES NOTHING** -- the session-open control with the rule's OWN ATR stop beats the rule
in **47 of 48 cells** (mean edge -0.305 to -0.483 in every side x regime cell), so the six
conditions enter later and worse than simply being there, separately in bull days and in bear days.
Note the control column itself: a session-open SHORT earns +0.394 R in bull and +0.210 in bear on a
market that rose 148.9%, which is the EMA trail's asymmetry and not a direction call -- read a
control's own level before crediting an excess over it.

**A COMMA-SEPARATED PINE DECLARATION TYPES ONLY ITS FIRST NAME, AND THE LINTER SAID THE FILE WAS
FINE BECAUSE IT NEVER OPENED IT.** `float a = na, d = na, eb = na` compiles the first binding and
declares the rest BY INFERENCE, so TradingView rejects the line with "Value with NA type cannot be
assigned to a variable that was defined without type keyword" -- pointing at a line that reads as
though it declares the type explicitly. PIN_POSTERIOR shipped that way and produced **0 trades**
("This report requires trade data"). The deeper defect is the linter: `pine_lint.py`'s CLI
**ignored its arguments entirely** and linted only the 800 machine-EMITTED scripts, so
`pine_lint.py some_file.pine` printed a clean bill of health for a file it never read. Both fixed
-- `multi_decl_problems` flags the declaration list (and the silent case too, where a literal
initialiser compiles and the later names merely lose their declared type), and the CLI now lints
paths given to it and, with no arguments, every file under `pine/` as well as the emitted set:
**125 files on disk, 0 problems**. Fourth linter gap found this way, after the continuation-indent
rule that shipped four scripts that could not compile. **A LINT PASS IS ONLY WORTH WHAT THE LINTER
CHECKS, AND ONLY IF IT READ THE FILE.**

**AND A POISSON LIKELIHOOD IS NOT SCALE INVARIANT, SO A "NORMALISER" IS NOT COSMETIC.** The same
script weighted B and S by RAW contract volume where the research divides by the mean volume per
in-window minute. `k*log(lam) - lam` with k in the tens of thousands makes the three hypotheses'
log-likelihoods differ by hundreds, so the posterior saturates at 0 or 1 on the first bar of every
session -- a different strategy, not a rescaled one. Fixed with an EXPANDING mean of the in-window
sub-bar volume (the research's constant is full-sample and unreadable by a script). The
transliteration then reproduces the research at **86-88% of the trade count and PF 1.031-1.085
against 1.037-1.078**, reading WORSE at the two thresholds where it differs most, which is the
conservative direction. Three irreducible gaps recorded in the header: the causal normaliser, the
stop rounded to a tick because `strategy.exit(loss=)` is priced in ticks, and a trail that acts on
a CLOSE and fills at the next open because a repriced stop cannot protect the fill bar. Found by
`research/pin/pin_parity.py`, not by reading -- the fourth time on this branch.

**A BETTER ESTIMATOR OF A MISSPECIFIED MODEL MEASURES THE MISSPECIFICATION MORE PRECISELY.** The
Griffin-Oberoi-Oduro (2018) Bayesian PIN estimator -- Gibbs sampling with data augmentation on the
informed part of each count -- replaces Yan's moment estimator on the same NQ event stream, same
bars, same decision rule, so anything that moves IS the estimator. It is unambiguously the better
estimator: four chains from hostile starts give **R-hat 0.9999-1.0024**, it recovers a known truth
on simulated data at T=60/120/400 with the credible interval covering every time, it quantifies
uncertainty, and it DROPS A FREE PARAMETER -- Yan needs event periods labelled before it can
estimate anything (the causal replacement was a trailing-sd rule with a threshold `evK`), while the
Gibbs sampler infers D_t as a LATENT VARIABLE. It moves **PIN from 0.0142 to 0.1554**, straight into
the equity literature's 0.10-0.20 band, exactly as the paper predicts for a liquid asset, and lifts
mu/(lb+ls) from 0.052 to 0.325 so the posterior can finally move off its prior. The two estimators
agree on lambda_b (corr 0.976) and on NOTHING else across the same 735 windows -- delta **-0.009**,
PIN **0.051** -- so never quote a PIN without naming the estimator.
**AND IT IS ALL DISPERSION.** The fit returns **delta = 0.93**, i.e. 93% of news events are BAD, on
a sample where the index rose 89%. A Poisson's variance EQUALS its mean, and mu is the only
parameter that can add variance, so the model's sole way to explain a wider spread is to invent
informed traders -- nothing in the estimator separates "informed traders arrived" from "this series
is more variable than a Poisson". NQ's volume-weighted B and S run **var/mean 14.65 and 18.89**
(bar counts 2.46/2.42), and S is the noisier series, which is exactly why delta puts the big mu on
the sell side: **delta is reporting which series is noisier, not which way the news went.** The
posterior predictive confirms it -- with mu maxed at 84.8 the fitted model produces sd(B) 15.0
against an observed **48.5, a ratio of 3.24**: the informed component is a variance sponge and still
falls three-fold short. **THE PLACEBO SETTLES IT**: fit the same estimator to negative-binomial data
with B and S drawn INDEPENDENTLY -- no news process in it at all -- and PIN comes out 0.0162 /
0.0368 / 0.0731 / **0.1066** / **0.1487** at var/mean 1/2/5/10/20. NQ's dispersion maps to
0.11-0.15 and NQ measures 0.1554. **The PIN is what the estimator returns on data with no
information in it whatsoever.** Duarte-Young (2009) and Gan-Wei-Johnstone (2017), both cited in the
paper, make this argument; the placebo is the version needing no theory. **RUN THE ESTIMATOR ON
INFORMATION-FREE DATA WITH THE SAME NUISANCE STRUCTURE BEFORE BELIEVING THE NUMBER IT RETURNS ON
REAL DATA** -- eight seconds, and it was the only test here that produced a verdict on its own.
**AND THE BETTER ESTIMATOR MAKES THE WORSE STRATEGY.** Gate 1, research only, both constructions:
**0 of 8 cells clear a matched random entry (best p 0.595), the excess is negative in all 8, and
every cell is unprofitable** -- session build PF 0.966-0.985, interval build 0.859-0.936, against
the Yan version's 1.037-1.116. Locked was NOT opened. The threshold has stopped filtering (1,125
trades at 0.50 against 950 at 0.95, where Yan went 722 -> 119) because at mu/(lb+ls) 0.33 the
posterior saturates -- decisive on 17,834 of 28,164 bars at the 0.85 rung, which is an imbalance
sign wearing a confident number. **The paper's OWN preferred construction is the worse of the two**:
fixing the news type over 10-minute intervals, its explicit proposal, gives the lowest PF in the
table on a mean period count of 5.0. A parameter estimate agreeing with the literature is not
evidence when the literature's estimate is of the same misspecified model. What would reopen it is
not a better estimator -- that has been tried -- but trade-and-quote data with the AGGRESSOR SIDE,
or single names around scheduled events. Also: their equation **(5b) is a typo**, `Be(nu+T1+T2,
T2+tau)` copied from the alpha line above it; the correct `Be(nu+T1, tau+T2)` recovers a true delta
of 0.30 as 0.293 where the published form returns 0.589. See `docs/ib/STUDY_PIN_BAYES.md`.

**SIXTY-FIVE FEATURES LOSE TO SEVEN, AND ONE PARKINSON ESTIMATOR BEATS ALL SIXTY-FIVE.** Deep
learning on the meta layer of a Gate-1-passing primary (NQ 15m; four primaries declared and scored
against a matched random entry FIRST, two eligible, and the one with the MOST EVENTS chosen because
`STUDY_V61_FEATURES_15M`'s own conclusion was that 125 locked events cannot separate a +0.05 uplift
-- P3 at 680 research events / 353 a year against P1's 225). 65 causal features in 8 declared
families, truncation audit **0 mismatches / 1,020**, 996 events. Ladder ridge -> rf -> lgbm ->
xgb d3/d6 -> MLP 2x32/2x64/4x128, purged and embargoed, uniqueness weights, objective = the R
earned, every model beside a SHUFFLED TWIN. **THE REGULARISED RANDOM FOREST WINS FOR THE FIFTH TIME**
(IC +0.1021) while ridge is NEGATIVE (-0.0494) and the deepest net reaches +0.0196 with no gradient
in depth -- capacity is not the constraint, again. The twin wins **2 of 8 = 25%**, the best noise
floor measured here (S3 58%, VWANOM 71%), so there IS signal. **THEN THE 8-SEED FAMILY ABLATION
(seed sd 0.004) SAYS SIX OF EIGHT FAMILIES MAKE THE MODEL WORSE**: dropping regime +0.0188 (t +6.8),
mom +0.0167 (+10.1), struct +0.0164 (+6.5), ffd +0.0145 (+7.5), trend +0.0068 (+2.6), volu +0.0027
(+0.9); only vol (-0.0574, **t -17.8**) and pin (-0.0061, t -2.6) are load-bearing. Pushed to its
conclusion: **vol+pin 21 features IC 0.1762, vol alone 7 features 0.1407, `vol.parkinson` ALONE
0.1501, everything 0.0983** -- seven beat sixty-five at **t +17.08** and one beats sixty-five. With
659 events and 65 columns the model fits noise; FEATURE ENGINEERING IS SUBTRACTIVE HERE and the
answer to "maximise it" is to delete most of the inputs.
**AND PIN EARNS A META PLACE AFTER FAILING AS A PRIMARY.** Adding the 14-column `pin.*` family to
volatility alone is **+0.0355 at t +16.68**; to everything else +0.0061 at t +2.60; and PIN ALONE is
**negatively informed (IC -0.0087, t -84)**. It is not a volatility duplicate -- mean |rho| of a
pin.* feature to its nearest volatility feature is **0.161** (max 0.307) -- so the demotion was right
in both directions: as a PRIMARY it is a dispersion statistic dressed as a probability, as a
CONDITIONING variable on top of volatility it adds something volatility does not carry. Its base
rate is also the tell: mean |lift-1| on the trigger's own bars is **0.087, the lowest of eight
families** (volu 0.730, ffd 0.458).
**AND THE SCORE IS CALIBRATED WHILE THE RANKING INVERTS, WHICH IS A CLEANER FAILURE THAN THE USUAL
ONE.** Gate 2 on the best set: research keep-30% gives **+0.0857 uplift, PF 1.249 -> 1.709, boot
p 0.050, random-filter p 0.027** -- 1 of 5 cells clearing both nulls. Locked (a SECOND read, so
descriptive -- P3's block was opened in `STUDY_BAYESOPT_DONCHIAN`): **every rung is negative and the
best research rung is the worst out of sample**, -0.0621 uplift at **PF 0.952**, monotone in how hard
it filters. But the threshold keeps **26.4% when asked for 30%** (largest gap 0.036), so it IS
calibrated -- the opposite of `STUDY_AUTOBNN`'s 105-of-105 -- which rules out the explanation
usually reached for. The mechanism is in the target-hit rate: **42.9% -> 43.9% while PF goes 1.249
-> 1.709**, so the model avoids losers rather than selecting trades that go further -- STUDY_V32's
win-rate mechanism, and it does not transfer. **Deflated Sharpe 0.163 over 134 counted looks**:
per-event Sharpe 0.1023 against an expected best-of-noise of **0.1410**, i.e. BELOW the noise floor
of its own search.
**AND THE PORTABLE FORM BEAT THE UNPORTABLE ONE.** A random forest cannot be written in Pine, so
the seven volatility features were re-fitted as a RIDGE with exported constants: OOF IC **0.1527
against the forest's 0.1407**. All seven univariate ICs point the SAME way -- higher volatility,
higher R (atr_pct +0.243, parkinson +0.236, rv96 +0.161, atr_rank250 +0.121, atr_ratio50 +0.101,
rv_ratio +0.057, vol_of_vol +0.010) -- agreeing with STUDY_V63 and inverting STUDY_V28, the SIXTH
move of a volatility-state rule's sign here. **THREE OF SEVEN RIDGE COEFFICIENTS HAVE THE OPPOSITE
SIGN TO THEIR OWN UNIVARIATE IC**, so each feature also ships as a standalone switch. Re-simulated
as VETOES rather than split out of realised trades (`STUDY_AUCTION`), off reads research PF 1.358 /
locked 1.336, ridge keep-0.60 1.423 / 1.385 and count>=5 **1.546 / 1.722** -- both better than the
subset framing, neither changing the verdict, since the ridge gate beats the base on NONE of five
locked rungs as a subset and the count gate is better on LOCKED than on research, the wrong shape.
Both ship DEFAULT OFF. Parity: research 689 script against 680 engine, **96.44% identical exit
bars**, corr 0.9951, +3.2%; locked **337/337, 97.61%**, 0.9974, **-2.8% conservative**; the
hard-coded thresholds keep 70.4/60.7/50.9/40.7/30.9% against 70/60/50/40/30 targets.
**AND THIS RULE'S ATR IS WILDER'S, NOT THE BRANCH'S USUAL `ema(tr,14)`** -- `sess_core._atr` is
`ewm(alpha=1/14, adjust=False)`, so the Pine needs `ta.atr(14)` and the standing instruction is
backwards for this one file. Ships `pine/v66/V66_VOL7_DONCHIAN_strategy.pine`.

**AND THE FRAMING DECIDED THE VERDICT: SCORED AS A VETO AGAINST A RANDOM GATE, THE COUNT FORM
CLEARS BOTH BLOCKS.** Everything in the study first scored the filters as a SUBSET of the base run's
realised trades, which is not what a script does -- a filter is a VETO, and refusing a signal
releases the position lock and admits a later breakout the unfiltered run never saw
(`STUDY_AUCTION`; `STUDY_XAU_CVD_FEATURES` measured that the two framings disagree). Re-scored
against a RANDOM GATE OF THE SAME SELECTIVITY, re-simulated end to end, 400 draws a rung: research p
**0.110 / 0.022 / 0.005 / 0.003 / 0.000** at T>=3/4/5/6/7 against locked **0.003 / 0.000 / 0.000 /
0.003 / 0.185** -- **three of five rungs clear on BOTH blocks and the research p-value is MONOTONE
in T across all five**, which is the gradient-in-both-directions evidence `STUDY_V17` called the
real kind. The two failures are at opposite ends for readable reasons: T>=3 keeps 52% of bars and is
barely a filter, T>=7 leaves **34 locked trades**. It still ships OFF: the locked excess exceeds the
research excess at EVERY rung (+0.068 vs +0.014, +0.090 vs +0.030, **+0.187 vs +0.055**, +0.148 vs
+0.067), the locked block had already been read once before this was scored, and the OTHER TWO NULLS
-- a day-block bootstrap against zero and a random filter over TRADES -- both failed. Three nulls,
two answers; report which one a p-value came from. Counted looks now 144.

**p90 OF R IS DEGENERATE ON A TARGET-CAPPED PRIMARY.** P3 runs a 3.2 ATR target behind a 3.8 ATR
stop, so a winner's R is capped at 0.842 and p90 reads **0.835 for every subset in the study** -- the
branch's standing instruction to read p90 of R rather than AUC silently measures NOTHING there. On a
capped primary ask the tail question as the TARGET-HIT RATE instead. And: `sess_core` labels a
session `YYYYMMDD` as an int while the first PIN build used epoch-days, so zero days joined, every
`pin.*` value came back NaN, and the pipeline printed "events with a complete feature row: 0" rather
than raising -- the all-NaN-reads-as-no-signal trap from `STUDY_V54` through a different door. Print
a join's overlap count before using it. What would move this is EVENTS, not capacity and not
features: both were swept and both are negative. See `docs/ib/STUDY_V66_DL_META.md`.

**`math.max()` RETURNS A FLOAT WHATEVER IT IS HANDED, SO `int x = math.max(1, int(y))` DOES NOT
COMPILE.** It reads as though the inner cast settles the type and it does not: TradingView rejects
the line with "cannot assign a value of the series float type to a variable declared with the const
int type" -- the same error the CMMA port hit on `math.round`, which is one instance of the general
rule that EVERY `math.*` is float-typed. The cast has to wrap the WHOLE expression. Added to
`pine_lint` as `int_assign_problems`, and the new check immediately found the SAME bug in TWO OTHER
SHIPPED SCRIPTS (`VP_TPO_SCALP` on `math.floor`, `PIN_POSTERIOR` on `math.max`), one of which had
already been sent out. All 126 files on disk are clean. **Fifth linter gap found by a script that
would not compile** -- and again the fix went into the linter first.

**AND A BACKGROUND RUN THAT SHOWS NO OUTPUT IS USUALLY THE HARNESS, NOT THE JOB.** Three separate
mistakes hid every long run in this session: `python x.py > file.log 2>&1` sends stdout to the FILE,
so the task's own output is empty and every read of it truthfully reports nothing; Python
BLOCK-buffers when stdout is not a TTY (`isatty` is False here), so even the log stays empty for
minutes; and `... | tail -N` CANNOT STREAM, because tail holds the whole stream until the writer
exits. A fourth: an `until ... pgrep -f run_x.py` waiter MATCHES ITS OWN COMMAND LINE and can wait
forever. `research/runlog.sh` fixes all of it -- tee instead of a redirect, PYTHONUNBUFFERED plus
`stdbuf -oL`, never a tail -- and a `Monitor` on the log then streams progress and result rows as
they happen.

**A 249-ITERATION LOOP PER BAR IS A TIMEOUT RISK, AND THE BUILT-IN IS INDISTINGUISHABLE.** The
research's `pandas rolling(250).rank(pct=True)` includes the current bar and averages ties, which
`ta.percentrank` does not, so V66's first draft wrote the exact form out as a loop. Measured on
70,436 bars the two agree at **correlation 1.000000, mean |diff| 0.00203**, and the take/skip
decision matches on **99.3-99.7%** of events at every threshold -- while the built-in removes ~17M
loop iterations over a three-year 15m chart. Measure the cheap built-in against the exact
definition before writing a loop to reproduce a pandas convention; here the built-in also landed
CLOSER to the target kept fractions (70.1/60.0/50.1/40.3/30.4 against 70/60/50/40/30).

**MOVEMENT DECOMPOSES AND ONLY HALF OF IT IS FORECASTABLE -- AND AN OUT-OF-SAMPLE IC OF 0.71 BOUGHT
NOTHING.** Eight declared targets x four horizons on NQ 15m, each scored against ITS OWN TRAILING
REALISATION (STUDY_V28: nothing ever beat reading CHOP today) with every t through Newey-West at lag
h (STUDY_V47: the naive t is 1.9-3.2x too generous), audit 0/852, direction included deliberately as
the control that must fail. Best of 71 causal volatility features, mean over horizons: **range
expansion 0.602, realised vol 0.529, TIME-TO-TOUCH 0.437, MFE 0.343, MAE 0.343, magnitude 0.294**
against **straightness 0.041 and DIRECTION 0.060** -- a tenfold gap in IC and up to thirtyfold in t
(NW t 62/49/-91 against 4.4/3.1). How far and how fast is forecastable; which way and how straight
is not. `STUDY_V22`'s split reproduced on a different instrument and construction. NOTE what is not
claimed: "beats baseline" is worthless for dir and er because their baselines are ~0.00.
**AND MY FIRST NULL WAS TOO EASY BY A FACTOR OF 5.6.** Each |IC| is the MAXIMUM OF 71 FEATURES, which
one shuffled twin cannot price, so the whole sweep was re-run on permuted targets. FREELY permuting
destroys the target's autocorrelation, and an IC on 46,000 OVERLAPPING observations of a persistent
target has a far larger standard error than that implies: the free null's p95 sat at **~0.014 for
EVERY target regardless of its persistence** and **32 of 32 cells cleared it, including direction**.
A test everything passes is not a test. Fixed with a CIRCULAR BLOCK PERMUTATION at 20x the horizon --
local structure kept, only the alignment destroyed -- whose p95 correctly SCALES WITH PERSISTENCE
(0.107 rng, 0.102 rv, 0.049 er) and averages **0.0774 against the free null's 0.0139**. Then **26 of
32 clear: the six real targets 4/4 each by 2.4-5.7x, straightness 2/4 by 1.1x, DIRECTION 0/4.**
STUDY_V47's naive-t error reached from the opposite direction. **A PERMUTATION NULL ON OVERLAPPING
DATA MUST PERMUTE BLOCKS.**
**AN HMM'S STATES ARE VOLATILITY STATES, AND ITS OWN DURATION FEATURE IS 5x WORSE THAN PARKINSON AT
THE DURATION TARGET.** Causal HMM (research-only parameters, FILTERED posterior, smoothed kept only
as the diagnostic): bear mu -0.0024 at the HIGHEST vol (rv 0.137), sideways +0.0011 at the LOWEST
(0.065), bull +0.0028 between; self-transitions 0.964/0.990/0.985 giving expected sojourns of **28,
100 and 65 bars** -- selloffs are the shortest-lived state and chop the most persistent. **0 of 32
cells where any HMM column beats the best of 71 volatility features** (largest HMM |IC| 0.478 against
0.688). The mechanism is in the columns: `p_bear` peaks against realised vol at +0.428, `p_side` at
**-0.478** and the sojourn feature at -0.467, because the long-sojourn sideways state IS the
low-volatility state. Sharpest instance: on time-to-touch the SOJOURN feature -- the natural duration
reading -- manages **0.087** where a Parkinson estimator manages **0.442**. **AND THE COLLAPSE TEST
SHARPENS STUDY_V27 RATHER THAN REPEATING IT**: V27 found Jaccard 1.0000 on a signal with THREE
distinct values, dismissible as a coarse-signal artefact; this signal takes **25,044** distinct values
and still overlaps the bare state label at **0.9757**. Filtered vs smoothed agreement **96.1%**,
reproducing V27's 96-97% -- which is why the leak is easy to miss.
**FORECAST QUALITY AND DECISION VALUE ARE NEARLY UNRELATED, MEASURED.** A ridge on the seven-feature
set forecasting forward realised vol scores **in-sample IC 0.729 and LOCKED IC 0.7065** -- among the
highest out-of-sample ICs on this branch -- with a stop multiplier spanning 0.54-1.84, so it moves
the stop materially. Substituted for the trailing ATR on the Gate-1-passing P3 primary, four arms
re-simulated end to end: **fixed 3.8N PF 1.358 / 1.344, V22's percentile rule 1.309 / 1.320,
forecast-scaled 1.310 / 1.299, forecast SHUFFLED 1.211 / 1.342.** THE FIXED STOP WINS ON BOTH BLOCKS,
and against its own shuffled twin the forecast reads **+0.099 research and -0.044 LOCKED** -- it
beats its noise twin where it was fitted and loses to it where it was not. **An IC of 0.71 out of
sample bought zero**, because the ATR stop ALREADY CONTAINS the volatility information and a better
estimate of the same quantity has nothing left to add. Always run the shuffled twin of the FORECAST,
not just of the model. (V22's rule also losing to fixed is not a refutation of V22 -- that was a flat
1.5/2.5N base with no target against this 3.8N stop with a 3.2 ATR target; STUDY_V52's geometry
lesson.) What is worth keeping is `ttb`: the most predictable target in the grid, and the cheapest
honest statement about a trade -- how long before +/-1 ATR resolves. It prices PATIENCE, not
direction. See `docs/ib/STUDY_V67_MOVEMENT.md`.

**SLIDE THE CUT BEFORE CALLING AN INVERSION A DECAY, AND THEN ASK WHETHER A RANDOM ENTRY FAILED
TOO.** A US30 Donchian-20 + EMA200 breakout in 07:00-11:00 New York with a fixed 50-point stop and a
150-point target reads research +1.513 pts / PF 1.041 and holdout -1.722 / 0.956, and three cheap
tests settle what that means. **(1) SLIDE THE SPLIT**: across eleven cut points from 40% to 90% of
the trades the research-minus-holdout gap is POSITIVE AT ALL ELEVEN (min +0.0259 R, median +0.1078,
max +0.1767) and the research half is positive at every one -- so the date is not the explanation,
though the POINT-barrier version is only 8/11 and goes NEGATIVE at the two latest cuts, so the two
parameterisations do not agree there is decay at all. **(2) SPLIT THE WALK-FORWARD AT THE CUT**: a
12-cell barrier x ADX grid re-chosen inside every training window looks like the rare optimiser win
(expanding +0.1713 R against the constants' +0.0918) and **THE WHOLE ADVANTAGE IS PRE-CUT** -- on the
three folds whose test window post-dates the research block every arm is negative, the fixed arm is
**0/3**, and a RANDOM CELL is least bad (-0.0289 against re-chosen -0.0712). Thirteenth re-optimiser
here to lose to the author's constants, third to also lose to a coin flip -- and its selection is
STABLE (`1.25 ATR, ADX>=25` in 6 of 8 folds), so an optimiser that settles on one cell is not
thereby right. **(3) THE FRAMING TEST IS DECISIVE**: on the holdout a RANDOM ENTRY in the same window
with the same geometry BEATS the rule (-0.0303 against -0.0761, p 0.815) while **ALWAYS-LONG in that
window is POSITIVE** (+0.0280 against the rule's -0.0761) -- so 2023-2025 is not a bad market for
being long in that window, it is a bad market for this breakout; removing the window entirely
reproduces the inversion (+0.0365 -> -0.0589), so the session is not the cause either. The failure is
in the TRIGGER. And the research pass's own null earns **-0.0458**, i.e. random entries in that
window lose money, so part of a p 0.000 is a hostile window rather than a good trigger.
**AND TEN YEARS COULD NEVER HAVE ANSWERED IT**: annual mean R runs -0.160 to +0.147 with sd **0.1075**
around a YEAR-weighted mean of +0.0108 (trade-weighted +0.0282; `corr(trades in a year, that year's
mean R)` is **+0.527**, so unlike `STUDY_TREND_LONG` the busy years are the GOOD ones and the
trade-weighted figure is the flattering one) -- a two-sd separation from zero needs ~380 years.
Two repairs failed informatively: **ATR barriers** made the geometry scale-free (a 50-point stop is
4.23 ATR in 2016 and 1.10 in 2025) and left the inversion WIDER at 1.0 and 1.25 ATR, so the drift was
real and was not what was wrong; and **ADX flips winner five times in ten years** while median ADX
stays flat at 21.8-24.5, so neither block is telling the truth about it. Cost is NOT the objection
for once -- the round turn is 4.58% of a 50-point stop and the win rates sit within two points of
their own driftless bounds -- so this family fails on DIRECTION. Six of seven models lost to their
shuffled twins. See `docs/ib/STUDY_DL50.md`, `research/dl50/run_d9.py`, `run_d10.py`.

**HOLD THE EXPOSURE FIXED AND US30's TIMING IS WORTH NOTHING -- 1 OF 60 DECLARED CELLS AGAINST 3.0
EXPECTED BY CHANCE.** Asked for an edge on US30 alone. Four primaries died in four runs, each with
its null in front. **(1) MEAN REVERSION, tested head-on for the first time on this market** because
twelve routes here had pointed at it while every US30 primary ever tested was a breakout: side
FORCED to `-sign(d)` on a displacement `d = (close - close[n])/ATR`, and **every declared fade cell
is negative before any barrier** while the mechanism's own conditioning variable inverts -- the
quintile gradient FALLS in 7 of 8 cells, `STUDY_LEV_ETF_REBALANCE`'s kill reproduced. **(2) ITS
MIRROR IS NOT DRIFT AND STILL DIES**: given each side its OWN drift baseline it beats drift on BOTH
(+0.0769 long / +0.0775 short ATR excess) on research and INVERTS on both (-0.0654 / -0.0730) on
the holdout, with the drift itself collapsing +0.0977 -> +0.0265. **(3) THE OVERNIGHT PREMIUM IS
EXPOSURE, NOT TIMING** -- zero fitted parameters, net +0.0337/+0.0092/+0.0538 %/session on three
blocks, decaying then returning on a reserved DIFFERENT-PROVIDER forward feed, research skew -1.08
exactly as risk transfer predicts, **90.2% of the research block's whole move arriving overnight**
-- and a RANDOM 15-HOUR WINDOW EARNS THE SAME on all three (p 0.405 / 0.782 / 0.383), with
always-long better risk-adjusted on the holdout. **(4) THE HEADLINE**: that null is the sharp
instrument, so hold the exposure EXACTLY fixed -- long at the next open, hold exactly L bars, exit
at an open, no stop, no target, nothing to fit, cost identical in both arms and cancelling -- and
put 20 declared conditions in seven families (every family that has ever cleared anything here) x 3
holding lengths through it: **1 of 60 clears p<=0.05 where 3.0 are expected, 0 survive BH**. That
is the cleanest statement of why eight Donchian breakouts, the IB, the VWAP-EMA spec and the volume
profile all failed the same way on this market. **THE NULL IS THE METHOD**: a circular shift of the
condition's OWN MASK within the block keeps its count and run-length structure EXACTLY and destroys
only its alignment with price -- a random-BAR null has too narrow a spread on clustered conditions
and passes everything, which is the `research/edgelab` 17,121-of-27,786 defect. **(5) THE ONE
CONDITION WITH A PRIOR INVERTS A SEVENTH TIME**: `ATR percentile <= 0.2`, one of only two survivors
of V28's 240 US30 cells at p 0.003, scored here as a REPLICATION reads research p 0.021 -> holdout
**0.888** -> forward 0.746, and its MIRROR clears the holdout at **p 0.005** while failing the other
two. **(6) WHAT REPLICATED IS A SIZING FACT, NOT AN EDGE, AND IT SURVIVED THE FORWARD FEED**: median
forward realised vol / trailing ATR by ATR percentile is 3.364/2.936/2.535/2.177/1.926 on research,
3.746 -> 1.867 on locked and 2.930 -> 1.728 on the different-provider block -- monotone all three
times, so `STUDY_V22`'s mechanism confirms on a third instrument and **an ATR stop's real width
varies about 2x with the volatility percentile**. **(7) AND ITS ACTIONABLE FORM DOES NOT TRANSFER**:
with the signal stripped out entirely (long the RTH open, out at the RTH close or the stop, one
trade a session) adaptive-minus-fixed-2.0N reads +0.0136 / **-0.0192** / +0.0126 and the NAIVE
INVERSE is the BEST policy on the holdout (PF 1.206, Sharpe 0.91) -- because the CALM SHARE ITSELF
MOVES, 47.9% -> 23.3% -> 22.0%, so a rule keyed to a fixed percentile cut is a different rule in
each block. The base is null on both US30L blocks and NEGATIVE at every stop on the forward one.
What would move it is 1-MINUTE US30 BARS, not more parameter search -- the exposure-matched test IS
that question in its strongest form and it came back below chance.
See `docs/ib/STUDY_MR30.md`, `research/mr30/`.

**A CIRCULAR SHIFT IS AN EXACT NULL FOR A MAX-OVER-FEATURES IC, AND FFT GIVES EVERY SHIFT AT ONCE.**
Asked to attack US30 15m by feature-engineering ANOMALIES and INEFFICIENCIES to predict MOVES rather
than prices. The reported statistic is the MAXIMUM |IC| over 100 features, which no single shuffled
twin can price, and the targets overlap so a free permutation is far too easy (`STUDY_V67`: p95 at
~0.014 for every target regardless of persistence, 32 of 32 cells clearing including direction). A
circular shift of the TARGET preserves its entire autocorrelation exactly -- it is the same vector --
and destroys only alignment; and the circular cross-correlation `irfft(conj(rfft(x)) * rfft(y))/n`
gives one feature's IC at ALL n shifts, so the max over features at each shift is the EXACT null
distribution of the statistic being reported: **~180,000 draws instead of a few hundred, cheaper
than the naive loop.** Use it wherever a best-of-N IC is quoted on overlapping data.
**V67's SPLIT REPLICATES ON A SECOND INSTRUMENT**: over 8 declared targets x 3 horizons, mfe 3.03x
the null, rng 2.96x, TIME-TO-TOUCH 2.86x, mae 2.76x, rv 2.68x, mag 2.62x, straightness 1.21x and
**DIRECTION 1.02x** -- and every movement target also clears its own TRAILING REALISATION, the bar
STUDY_V28 set. Direction's one "pass" is an IC of 0.0270, real against a shift and far too small to
pay a round turn. Truncation audit 0/120. **AND THE ANOMALY FAMILY IS NOT A VOLATILITY RENAME** --
PCA reconstruction error, Mahalanobis, isolation forest and a torch autoencoder, ALL fitted on block
A only and none ever seeing a label, correlate with the ATR percentile on the trigger's own bars at
just **+0.099 / +0.179 / +0.230 / +0.130**; this branch has caught its own pool duplicating seven
times and here it does not. **`STUDY_VWANOM`'s DIRECTION STRENGTHENS TO 12 OF 12**: rho(detector,
trade return) is NEGATIVE in every cell across three blocks and TWO PROVIDERS (research -0.169 to
-0.206, holdout -0.073 to -0.123, forward -0.028 to -0.088), decaying across the split, the right
shape. **AND IT CONVERTS INTO NOTHING, FOR A READABLE REASON**: VWANOM's own caveat that the
quantile means are NOT monotone is what decides it -- on the reserved forward block the TOP-QUARTILE
MEAN IS HIGHER (+0.0575 vs +0.0295) while rho is negative, so the negative correlation lives in the
MIDDLE of the distribution and not in the tail a veto cuts. Re-simulated as a VETO against a random
gate of the same selectivity it clears on both US30L blocks (holdout p **0.000** on a base that
loses money) and on the different-provider block **7 of 8 cells have a NEGATIVE uplift and none
clears** (best p 0.387). **AND THE ADAPTIVE HOLD CAP LOSES TO ITS OWN SHUFFLED FORECAST** -- every
hold cap here is a constant and time-to-touch is the one predictable thing an ATR stop says nothing
about, so a ridge forecasting it (research IC +0.3344, **holdout +0.4150**) set the cap at 2x the
forecast: research +0.0032 %/trade against a shuffled twin's -0.0042, forward block **+0.0099
against the twin's +0.0126**, and the FIXED cap beats both on every block. Trade count nearly
triples (1745 -> 5023) because shorter caps release the position lock, so the adaptive policy is a
DIFFERENT STRATEGY and the shuffled arm is the only honest comparison. **THE PATTERN ACROSS V67 AND
THIS STUDY IS ONE STATEMENT: a movement forecast can only pay where it prices something the ATR does
not already price, and both candidates -- the STOP WIDTH and the HOLD CAP -- turn out to be already
priced.** See `docs/ib/STUDY_MV30.md`, `research/mv30/`.

## Tooling

| module | what it does |
| --- | --- |
| `research/test_suite.py` | 57-test battery on one strategy |
| `research/quant_brain.py` | features, regimes, metrics, improvement engine, portfolio |
| `research/alpha_factory2.py` | 16.2M strategy generator, 115 conditions |
| `research/vol_sizing.py` | the eight named volatility-sizing methods |
| `research/intrabar.py` | true 1-minute path execution modelling |
| `research/pine_export.py` | Pine strategy + indicator emitters |
| `research/v67/` | movement vs price: `v67core.py` (eight declared targets incl. a duration target and direction as the control, each with its own trailing baseline, plus a Newey-West t and a BH helper), `run_v1` (audit then the whole grid), `run_v2` (the max-of-71 null, cached, and the causal HMM with V27's collapse and filtered-vs-smoothed diagnostics and an expected-sojourn feature), `run_v3` (the CIRCULAR BLOCK permutation that replaces it), `run_v4` (the decision test: a vol forecast against the fixed stop, V22's rule and its own SHUFFLED twin) |
| `research/dl50/` | the fixed-point / ATR barrier study on US30: `d50core.py` (both walkers, Wilder's ADX returning BOTH DIs, the break-even the geometry implies, the point-stop-in-ATR drift table), `d50feat.py` (50 causal features in 8 families with a causal time-of-day baseline), `run_d1..d8` (geometry -> base rates -> the model ladder beside shuffled twins -> the window and flatten -> ATR barriers and the ADX gate -> the year decomposition), `run_d9.py` (slide the cut across eleven split points; walk-forward with in-fold re-selection beside the constants and a random cell; the sign noise priced by day-block bootstrap), `run_d10.py` (the walk-forward split at the research cut, and the framing test -- the rule against a random entry, always-long, and no window, all in the same block) |
| `research/mr30/` | US30 alone, four primaries under the two-gate architecture: `mr30core.py` (Phase 0 in the docstring, the displacement event stream with the side FORCED by the mechanism, three blocks incl. a different-provider forward feed, an ATR-barrier walker and a sorted matched control), `run_g0.py` (cost as a fraction of risk, the geometry-free forward-return read with Newey-West t, and the mechanism's own quintile gradient), `run_g1.py` (the mirror split by side against each side's OWN drift baseline), `run_g2.py` (the parameter-free session decomposition and the by-hour table), `run_g3.py` (Gate 1 on the overnight premium: a random SAME-LENGTH window, always-long, the vol gradient, every year), `run_g4.py` (**the exposure-matched timing test** -- 20 declared conditions x 3 holding lengths against a CIRCULAR SHIFT of each condition's own mask, which preserves count and clustering exactly), `run_g5.py` (the ATR percentile as a pre-registered replication across three blocks, its mirror, and V22's mechanism), `run_g6.py` (the sizing fact as a stop policy, with the naive inverse as its falsifier) |
| `research/mv30/` | US30 15m, movement not price: `mv30core.py` (71 volatility columns plus a declared INEFFICIENCY family -- Lo-MacKinlay variance ratios at four lags x three windows, rolling AR(1), Roll's implied spread from the same serial covariance, Amihud illiquidity, vol-clustering persistence, bar shape against causal time-of-day baselines -- plus the truncation audit), `run_m1.py` (**the exact circular-shift null**: one FFT per feature gives its IC at every shift, so the max over features at each shift is the exact null of a best-of-N IC, ~180k draws; eight targets x three horizons with direction as the control), `run_m2.py` (four unsupervised detectors -- PCA / Mahalanobis / isolation forest / torch autoencoder -- fitted on the research block only and never shown a label, then read against MOVEMENT and against TRADE OUTCOME separately), `run_m3.py` (the volatility-rename check on the trigger's own bars, then the anomaly as a VETO re-simulated against a random gate of the same selectivity on all three blocks), `run_m4.py` (the adaptive hold cap from a time-to-touch forecast, against a fixed cap AND against the same forecast SHUFFLED) |
| `research/runlog.sh` | run a script so its output is LIVE -- tee not `>`, unbuffered, never piped through `tail`; pair it with a `Monitor` on the log |
| `research/pine_lint.py` | **run before shipping any Pine** — there is no compiler here; with no arguments it lints the emitted scripts AND every file under `pine/`, and it takes paths |
| `research/pin/` | the EKOP/Yan PIN mixture: causal four-step fit, the three-hypothesis posterior, the volume-weighted B/S construction, the matched control, and `pin_parity.py` — the shipped Pine's own order model run on bars |
| `research/pin/pin_bayes.py` | the Griffin-Oberoi-Oduro Gibbs sampler for the same mixture — data augmentation, the corrected (5b), a simulate-and-recover positive control, and the dispersion placebo that reads the estimator's floor on information-free data |
| `research/v66/` | deep learning on the meta layer: `v66core.py` (four declared primaries, Gate 1 on each, and a matched random entry forced through `ent_hi` so geometry/exits/lock are identical), `v66pin.py` (the PIN mixture as a causal 14-column feature family), `run_d1..d6` (Gate 1 -> features + audit + base rates -> the eight-model ladder beside shuffled twins -> 8-seed family ablation -> Gate 2 on the best set with a locked read and the deflation), `_mlmod.py` (shared model plumbing so the runners cannot drift apart) |
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
| `research/strat/` | The Strat combo engine: bar types, four location filters, one-bar stop order, trade-matched control |
| `research/ddc/` | the Double Donchian Pine's order model, literal vs intended TP, trade-matched controls |
| `research/mrl/` | the two library-built designs: strict 1-minute limit walk, 15m bar walk, ladders with a random-filter gate, the trend grid |
| `research/orb/` | ORB v1 to spec: causal build with the ATR timeframe as an explicit axis, signals vectorised, exits walked on the TRUE 1-minute path, equity-compounding sizing with whole-lot flooring, a truncation audit, three matched controls and a 4,320-cell sensitivity sweep read by marginal average; `orb_feeds.py` adds the three 15m feeds with per-market contract specs and `orb_regime.py` the ADX/DI/slope regime as a sequential hysteresis state machine, frozen on completed 15m bars and forward-filled |
| `research/overlay/` | the fast-alpha execution overlay: a 1-minute reversion gate scheduling Donchian entries, the four screening gates, the seven-part battery (Roll bounce floor, random-delay placebo, PnL attribution, paired block bootstrap, tails, cost sweep and fill haircut, missed-trade census), and the same battery re-run on a POSITION-LOCKED baseline with the placebo inside each block |
| `research/scalpreq/` | the scalp-requirements experiment: 31 conditions x 2 triggers x 2 geometries x 6 feed-timeframes, with base rates, the cost-as-a-fraction-of-risk table and the zero-cost variant |
| `research/v63/` | the VWAP / triple-EMA / ATR trend design: three feeds with real volume, a chandelier-trail tensor, search on one market and a frozen read on three, drop-one and the binding hold axis |
| `research/v62/` | the confirmation study: base rates on the trigger's own bars, a 3.1M-cell grid in exact on/off twins, matched pairs on both blocks, and the drop-one |
| `research/v64/` | Optuna on V61, its walk-forward and its Monte Carlo: a continuous-space numba evaluator verified to the cent against the published grid, three Optuna studies, fANOVA importance, the box-edge re-run, the V30 hold-out-an-axis surrogate; `run_wfo*.py` in-fold re-selection with a random-cell arm, span-normalised WFE and a geometry-matched control; `run_mc.py` perturbation (price jitter with the indicators RECOMPUTED, execution, missed fills, parameters) beside the permutation and the bootstrap |
| `research/v61feat/` | feature engineering on the V61 15m rule under the two-gate architecture: `v61feat.py` (51 causal features in 7 declared families, FFD fracdiff with d by ADF on research only, a Baum-Welch HMM read FILTERED with the smoothed version kept only as a leakage diagnostic, truncation audit), `run_feat1.py` (Gate 1 on two candidate primaries, base rates on the trigger's own bars, IC against shuffled twins, redundancy measured ON THE SIGNAL BARS with family-first selection, stability across research halves and volatility regimes), `run_feat2.py` (purged embargoed CV with a RETURN objective, Gate 2 against a bootstrap and a same-selectivity random filter, drop-one incremental value, one locked read with the kept fraction reported, deflation and White's reality check), `run_feat3.py` (the two PORTABLE forms measured before any Pine is written -- the sign-aligned count ladder and a ridge whose every constant is exported, plus the frozen HMM parameters and fracdiff weights), `feat_parity.py` (the shipped script's fracdiff recursion and HMM forward pass reproduced in Python and diffed against the research), `plot_feat.py` |
| `research/vwapema/` | the Bhatti VWAP-EMA gold spec built literally and tested: `vecore.py` (the six conditions, the close-only EMA trail, the intrabar initial stop, a volume-free VWAP twin, and `periods()` so a period ladder recomputes its series instead of reading a cached one), `run_ve1.py` (condition base rates BEFORE any P&L, cost as a fraction of risk, the break-even the geometry implies, the paper's assumed distribution against the measured one, the matched control as a gate, and the zero-cost / spec-cost / no-target / no-tighten / flatten / volume-free arms), `run_ve2.py` (drop-one, the neighbourhood, ONE locked read with the trial count stated, the paper's own 2024 slice, by-year), `run_ve3.py` (the corrected neighbourhood, the long drop-one, the volume gradient against a same-selectivity random filter, the exit ablation), `run_ve4.py` (that gradient read once on locked, labelled descriptive), `run_optuna.py` (3,600 trials over all fourteen axes on research only, population shape, marginals, fANOVA, box edges), `run_ve5.py` (ONE locked read of the finalists with matched controls, day-block bootstrap for the edge and permutation for the path, parameter perturbation, three correlation matrices, deflated Sharpe), `run_ve6.py` (concentration in the 2025 rally and a walk-forward with the selection re-run inside every fold beside a random cell), `run_why.py` / `run_why2.py` (why a preset 'holds': the monthly correlation matrix against gold itself, the beta decomposition, selectivity, the fold-level gold split, and a session-open control carrying the rule's OWN stop so it cannot be accused of more risk), `run_wfo_presets.py` (the same battery per shipped preset: per-split IS/OOS ranks, the pairwise-drop degeneracy, a clean-pool PBO, and a rolling walk-forward per preset), `run_wfo_pbo.py` (the three overfitting questions: a rolling walk-forward with nothing re-selected, CSCV/PBO over a per-month return matrix, and a walk-forward with the selection re-run each fold beside a random cell), `ve_vbt.py` (vectorbt as a second engine, transcription-checked first), `ve_parity.py` (the script's order model, with the close-only trail modelled both ways), `plot_ve.py` |
| `research/ibopt/` | the Initial Balance retracement on US30 under the two-gate architecture: `ibcore.py` (Phase 0 in the docstring, a continuously parameterised per-day walker verified against the V58 tensor, the 18:30-re-open flatten trap fixed, gap-through fills, a risk-matched random-entry control), `run_gate1.py` (the published primary, arms, the retracement ladder the mechanism predicts), `run_optuna.py` (three TPE studies on research only, locked logged and never used, marginals, box edges, fANOVA), `run_gate1_finalists.py` (both nulls plus ALWAYS-SIDE on the same days), `ibfeat.py` (30 causal side-oriented features in six families, FFD d by ADF on research, HMM read filtered, truncation audit), `run_gate2.py` (screen, purged CV with a return objective, shuffled twins, Gate 2 vs bootstrap and random filter, drop-one, the portable ridge), `run_locked.py` (ONE read: finalists, meta layer, deflation, the US30_ISO post-2025-07 block), `ib_parity.py` (the Pine's order model incl. the fill-bar target the broker emulator pays), `plot_ibopt.py` |
| `research/vstoch/` | VWAP x Stochastic x ATR: the design declared in the module docstring before any search, a causal TIME-OF-DAY ATR baseline beside the broken trailing-mean one, base rates on the trigger's own bars, the trigger against a random entry at four geometries, a 31,752-cell declared grid read by marginal average, both nulls, one locked read, a frozen cross-market read, the zero-cost variant, the win rate against its own driftless bound, and `vstoch_parity.py` -- the shipped Pine's order model diffed against the engine |
| `research/v61sess/` | the V61 rule as a user configures it: `sess_core.py` (the SCRIPT's order model with the session window, the flatten filling at the next open, and touch-as-break), `run_iss_oss.py` (IS/OOS on both timeframes, the window-vs-flatten ablation, the channel-time-reach control, and the zero-cost comparison), `run_optuna.py` (2,400 trials over two objectives with the session axis open, research only, population shape before any top row, box-edge check), `run_mc_portfolio.py` (the four Monte Carlos per leg, daily-return leg correlation, and combinations scored against the BEST single leg), `us30_core.py` + `run_us30.py` + `run_us30_mc.py` (the same rule FROZEN on US30 with the CVD built from 15m sub-bars, three nulls, the gate ablation, and the cross-market book), `plot_sess.py`, `plot_us30.py` |
| `research/v61/` | the CVD optimisation: a verified exit tensor (725,760 configs in ~4s a timeframe), research-only marginals, one locked read, the second null, the gate ablation and both presets' parity |
| `research/top5/` | **the cross-strategy battery** -- one trade table for eight engines, the ranking in percent of price, each strategy's own control, IS/OOS + two Monte Carlos + robustness + a nine-gate live-readiness scorecard |
| `research/ftm/ftm_anatomy.py` | FTM reverse-engineering: drop-one anatomy, 200-cell grid, walk-forward, clusters, robustness, MC |
| `docs/ib/EDGE_LIBRARY.md` | **the mechanism library** -- what survived, what it is, how to take a new strategy apart |
| `research/ema48/` | EMA 13/48 x VWAP S/R x ATR stop x ATR trail on the scalp89 order model: the declared 24-cell grid, ablations, stop and trail ladders, random-entry control, cross-feed reads; `e48_features.py` (37 causal features, 8 families, truncation audit); `run_ml.py` the purged-embargoed ladder ridge -> logistic -> LightGBM -> XGBoost -> MLP with shuffled twins, same-selectivity random filter, one locked read per base |
| `research/trend/` | the diversified trend ensemble to its spec's own layout: `config.yaml` (constants, split date, calibration c), `data.py` daily panel with t+1-open execution, `volatility.py`, `forecast.py` (sleeves, scalars, FDM), `portfolio.py` (rolling IDM, sizing, buffered trade-to-the-edge), `trend_costs.py` (drag rule), `backtest.py`, `validate.py` (the full section 8 battery on the skill's scripts), `tests/` (alignment, scalars, vol target), `research_log.md` |
| `research/scalp89/` | the submitted NQ Scalping System transcribed with its order model (naked fill bar, Pine intrabar path, no flatten -- each modelled both ways), exit-machine and entry ablations, fixed-horizon signal tests on four feed-blocks, matched controls, a 160-cell geometry sweep, a 729-cell in-fold walk-forward with a random-cell arm, and a perturbation Monte Carlo with the indicators recomputed; `research_log.md` carries the trial count |
| `research/inst/vp_tpo.py` | 45 causal features -- volume profile (1-minute source mapped to the closed 15m bar), TPO letters / value area / single prints / IB, EMA200 and EMA 13/48 readings, ATR variables -- with `truncation_audit` and `walk_tp`, a per-bar-stop / per-bar-target walker exact against the engine |
| `research/inst/run_vp_scalp.py` | the VP/TPO/EMA/ATR battery on the 07:00-11:00 scalp: base rates, feature IC with a shuffled null, 43 entry conditions vs a same-selectivity control with BH, 37 target rules vs a same-distance random target, 27 stop rules in three units, one locked read; `run_vp_scalp2.py` ladder / co-selection / mechanism / years / bootstrap, `run_vp_scalp3.py` the drop-one, `vp_tpo_parity.py` the shipped Pine's profile diffed bar by bar |
| `research/xaucvd/` | gold x Donchian x CVD: `xcvd.py` (chart bars with the CVD built from 15m sub-bars, 60 causal features in six declared families, truncation audit), `run_xcvd.py` (the base against a random entry FIRST, base rates on the trigger's own bars, the whole pool against same-selectivity random filters with BH, the four patterns kept separate), `run_xcvd2.py` (audit, the bullish-vs-bearish sign-structure test, the k x w neighbourhood, one locked read, the sub-bar-resolution check), `run_xcvd3.py` (the pivot-only ablation and the coin-flip-in-place-of-CVD control), `run_xcvd4.py` (veto vs subset, and the veto against a random GATE re-simulated end to end), `xcvd_parity.py` (the shipped Pine's order model in Python, run under BOTH the research pivot definition and Pine's stricter `ta.pivotlow`) |
| `research/xau/` | the XAUUSD two-layer build: `xau_core.py` (data admission with the clock re-derived, three blocks, gold's cost model, the Donchian primary as an event stream), `run_phase0_gate1.py` (Phase 0 written before any code, Optuna on the primary block alone, Gate 1 with a side-flip and zero-cost arm and a cost stress), `run_frozen.py` (five geometries frozen from other markets x three sides x three blocks), `run_drift_control.py` (the same side, exits and trade count entered at RANDOM bars), `xau_meta.py` (FFD fracdiff with d chosen by ADF on the primary block, a causal HMM read FILTERED with the smoothed version kept only as a leakage diagnostic, 28 features, truncation audit), `run_meta_gate2.py` (purged embargoed CV, shuffled twins, Gate 2 on unsized returns with sizing reported not credited, one locked read, deflation), `run_deflate_fix.py` (the DSR recomputed over the right trial population) |
| `research/lev/lev_core.py`, `run_gate1.py` | the mechanism-first primary: Phase 0 spec in the module docstring, the `L(L-1)` arithmetic that forces the side, the event stream with one declared parameter, a causality audit that rebuilds every trigger from bars ending at entry, then Gate 1 strict and relaxed with the side-flip and always-long arms and the observation-time trial count |
| `research/inst/vp_next0.py` … `vp_next2.py` | the VP/TPO handoff executed: R-space read, veto-vs-subset, day-clustered null, PSR/DSR/MinBTL/power (`vp_next0`); `vp_tpo2.py` the profile parameterised by bin mode / letter / side; bin x letter x ceiling sweep and CSCV PBO over the construction x stop grid (`vp_next1`); stop inside the gate on p99 drawdown, extension-factor IC, extended drop-one, day effect and random entry inside the gate's days (`vp_next1b`); the pre-registered US100-pre-2022 / US30 / short-mirror reads with bar-matched, day-clustered and random-entry nulls (`vp_next2`) |
| `research/inst/run_scalp_filters.py` | 38 declared conditions in eight families on the 07:00-11:00 scalp base: base rates on the signal bars, each against a same-selectivity random filter on research, BH across the pool, pair stacks, one locked read of the survivors against a locked random filter |
| `research/inst/run_bayesopt_scalp.py` | the same Optuna harness under a 07:00-11:00 NY entry window and a 4-hour hold cap, 5m and 15m, three objectives, finalists read once on locked and scored against a random entry inside the window at the same rate, box-edge check, fANOVA, transfer |
| `research/inst/run_bayesopt.py` | Optuna (multivariate TPE x3 objectives, GP sampler) over the continuous Donchian space on research only, every trial's locked result logged and never used, finalists read once, box-edge check, fANOVA, transfer per study; `run_bayesopt_ctl.py` the random-entry control at each finalist's own geometry and rate |
| `research/inst/run_conformal.py` | conformalized quantile regression + a regularised random forest on one cell, trained on the whole Donchian family with uniqueness weights, 37 audited features, purged/embargoed folds, shuffled twins, a same-size random-subset null, coverage checked per fold, one pre-declared locked read (CQR lower bound > 0) |
| `research/inst/autobnn.py` | AutoBNN rebuilt in torch (compositional Bayesian leaves, ELBO structure search, mean-field VI, sampled posterior predictive) with a positive control; `run_autobnn.py` runs it as a forecaster gate and as a Bayesian meta-label on one cell, each beside a shuffled twin and a same-selectivity null, one pre-declared locked read per arm |
| `research/inst/` | the PF-2-at-200/yr question answered as a frontier: `frontier.py` (the win-rate arithmetic for PF 2, the V61 tensor with intraday hold caps and RTH entries over 4.08M cells, the PF-vs-count envelope read once on locked, the DSR at the trial count), `book.py` / `book2.py` (every validated intraday leg pooled in percent of price with per-feed costs, leg correlations, the research-selected book), `meta.py` (meta-labeling with a regression-on-R objective, purged and embargoed, shuffled twins, same-selectivity null, one locked read) |
| `research/s310/` | the same rule at TEN MINUTES with the whole battery: `t10core.py` (the 10m build, a cell runner with overridable price arrays so the jitter MC reuses it untouched, a SORTED matched random entry, a coin-flip-side null, four Monte Carlos, and a vectorised pivot kernel asserted identical to the reference), `run_t1.py` (cost as a fraction of risk first, then the carry-vs-matched-minutes reading of k and w and their neighbourhood, and the 5m comparison), `run_t2.py` (630 geometry cells read by MARGINAL AVERAGE with the inert axis collapsed, plus the one-rung box), `run_t3.py` (bootstrap for the edge, permutation for the path, execution perturbation, and price jitter with the pivots/CVD/ATR all recomputed), `run_t4.py` (correlation matrices across cells, across timeframes and against always-long, on zero-filled daily P&L), `run_t5.py` (both nulls, the year-by-year regime split, the deflated Sharpe at the counted trial count and White's reality check), `plot_s310.py` |
| `research/s3nn/` | the neural-network meta layer on S3: `nn_data.py` (the event stream, 49 causal features in 9 declared families, an UNLOCKED labeller so the training rows are not the position lock's survivors, a truncation audit and Lopez de Prado uniqueness), `nn_model.py` (purged embargoed folds, the eight-model ladder, a torch MLP fitted on weighted squared error in R), `run_n1.py` (Gate 1, the training-set sizing and the audit), `run_n2.py` (the ladder beside its shuffled-label twin), `run_n3.py` (Gate 2 against a day-block bootstrap AND a same-selectivity random filter, plus the ensembles), `run_n4.py` (the win/lose contrast on the SAME folds, the win-rate arithmetic PF 1.5/2/3 requires, and Sharpe zero-filled over every research day), `plot_nn.py` |
| `research/tscalp/` | the submitted Turtle Scalp Pine transliterated with its order model (armed stop, late re-anchor, pyramid bracket, 2R target, flatten at the next open), three EMA gates as entry masks, base rates on the breakout bars, a 36-cell grid by marginal, drop-one, same-selectivity control, cross-market, three Monte Carlos, neighbourhood, and one descriptive locked read |
| `research/absorb/` | the 50% session level + MTF ICT swings + absorption bubbles as one reversal system: causal construction with a truncation audit, base rates and lift BEFORE any P&L, a 211-cell grid read by marginal average, the exit tested fairly (no-trail arms given a real exit), drop-one, random-entry and same-selectivity controls at every trail width, the intrabar tie-break split, and one locked read |
| `research/scalp89/s89_pine.py` | the CORRECTED order model -- what `strategy.exit` actually does on the fill bar when its stop/limit args are still `na`; verified trade-for-trade against `research/scalp89/test_pine.py`'s independent reference |
| `research/ib25/` | the posted IB-25 retracement: session VWAP, a running 09:30-10:30 range, one live limit order a session, the three prose conditions codified as explicit parameters, the retracement and stop ladders against their own driftless break-even, a random-entry-minute control, one locked read, and `run_ib25_mnq.py` -- the dollar view with the synthetic-level deflator |
| `research/ib25/run_ib25_es.py` | the ES question without an ES feed: the rule's risk as a percentage of price, each contract's round turn as a fraction of THAT risk, the NQ series re-charged at every contract's relative cost, the zero-cost variant, and the win rate against its own driftless break-even at five geometries |
| `research/ibs/` | the IBS session EA: cached tensor, bar-by-bar parity, stability / MC / clusters / walk-forward / judge |
| `research/cmma/` | the CMMA notebook, re-implemented honestly: accounting, costs, deflation, holdout |
| `research/cmma/cmma_stats.py` | its profit factor, win rate and hold time, per DAY and per stance |
| `research/cmma/cmma_parity.py` | the shipped Pine's own logic, diffed against the engine (corr 1.0000000000) |
| `research/cmma/cmma_improve.py` | seven pre-declared candidates, two-feed agreement gate, one holdout read |
| `research/v58/v58_anatomy.py` | **what creates the IB edge** — exit split, infinite stop, day-vs-bar, drop-one, ladders |
| `research/hpfilter.py` | HP trend, causal vs full-sample, and the leak between them |
| `research/ma_lag.py` | moving-average lag/smoothness, matched-lag equivalence, turn delay |
| `research/edgelab/crypto.py` | BTC 15m: the sixth instrument, a UTC clock, real taker-side flow |
| `research/btc_legs.py`, `run_btc_legs.py` | all nine shipped legs on BTC, with the volatility-artifact diagnostic |
| `research/eurusd_legs.py`, `run_eurusd_legs.py` | the shipped 30m legs on EURUSD, matched control, BH |
| `research/vbt/sweep_engine.py`, `run_sweep.py`, `analyse_sweep.py` | the 110,250-config sweep, IS selection, one OOS read |
| `research/turtlefeat/divergence.py` | confirmed-only RSI/Stoch divergence + volume spikes, leakage-audited |
| `research/turtlefeat/` | 124 causal Turtle features + Kalman state, redundancy and 1:1 separation tests |
| `research/vbt/heat.py` | MAE/MFE in POINTS and in R, split by exit reason and by market |
| `research/vbt/intraday.py`, `run_intraday.py` | session-windowed intraday engine; nothing can hold past the flatten |
| `research/vbt/prop.py` | prop-firm evaluation: trailing DD, daily loss, P(pass) by day-block bootstrap |
| `research/vbt/mae_mfe.py` | per-trade MFE/MAE in R on the finest series; capture and heat |
| `research/turtle2/` | the original Turtle and the YouTube variant, frozen, with risk-matched controls |
| `research/v22/v22vol.py` | 71 causal realised-volatility features + the forward efficiency-ratio label |
| `research/v22/v22run.py`, `v22trade.py` | 426 IC tests and 2,556 control-gated trade conditions on NQ |
| `research/v22/v22stop.py`, `v22destroy.py` | the declared stop policies, and the three attacks on them |
| `research/v22/v22vix.py` | SPX x VIX daily: 39 causal VIX features, the VRP, a small daily engine |
| `research/v22/v22vixrun.py`, `v22vixtrade.py` | the positive control, the chop IC test, the VIX heat table |
| `research/v22/v22anchor.py`, `v22_parity.py` | the signal-close stop anchor, and the shipped script diffed against the engine |
| `research/v22/v22stack.py` | the V20/V21 components re-tested jointly with the adaptive stop |
| `research/v23/v23mom.py` | momentum x ADX x CHOP on the V20 base: marginal averages, top 100, controls, lift |
| `research/v24/v24ma.py` | 7 MA types x 9 pairs x 2 modes x CHOP: the lag table, drawdowns, and the no-MA baseline |
| `research/v24/v24hma.py` | HMA CROSS cell by cell, and the lag-matched test that withdrew the type gradient |
| `research/v25/v25lr.py` | the linreg 9/21 cross: 484 cells, value/slope/forecast readings, R^2 gate, controls |
| `research/v31/v31mc.py` | **the two Monte Carlos** — day-block bootstrap for the edge, permutation for the path, over all 34 declared configurations |
| `research/v32/v32flow.py` | 43 causal volume / absorption / exhaustion / anomaly / flow-proxy columns, truncation-audited |
| `research/v32/v32run.py`, `v32sum.py`, `v32imp.py` | XGB + LightGBM on both objectives, shuffled twin, selectivity control; the counts, and importance by source frame |
| `research/v33/v33core.py` | the strategy spec, its parameter classification, a cached engine and the multi-objective score |
| `research/v33/v33opt.py`, `run_grid.py`, `rescore.py` | the 207,360-cell grid on TRAIN, neighbourhood robustness, one read of VALID |
| `research/v33/v33robust.py`, `run_final.py`, `dsr_sweep.py` | perturbation, regimes, walk-forward, MC, cost stress, deflated Sharpe as a curve, and the ONE OOS read |
| `research/v34/v34one.py` | **the corrected limit walker** — one live resting order, which is what a script can place |
| `research/v34/order_audit.py` | counts simultaneous resting orders directly, rather than arguing about them from the source |
| `research/v34/v34mech.py`, `run_v34.py`, `expiry_cal.py` | the five pre-registered hypotheses, 32 declared cells, per-SIGNAL accounting |
| `research/v35/v35bal.py` | any window as a mechanism — 25 causal features, first break, extension, reversion, and a same-length random-start control |
| `research/v35/v35run.py`, `v35ml.py`, `v35why.py` | the 44-cell window sweep, the boosters on both targets, and the anatomy of the 0.86 direction AUC |
| `research/v36/levels.py` | liquidity pools with confirmation-lagged pivots, roll-relative session freezes and a truncation audit |
| `research/v36/setup.py`, `engine.py` | four sweep definitions, the FVG->IFVG chain, and a one-live-order 1-minute engine |
| `research/v36/run_grid.py`, `run_valid.py`, `run_filter.py`, `quartile_fix.py` | the 5,400-cell grid, the neighbourhood and validation reads, and the best-of-N correction |
| `research/v37/ofa.py` | order flow as inversion polarity; age-bounded FVG/IFVG; HTF->1m mapping |
| `research/v37/run_v37.py`, `run_tf.py` | the thread's IFVG model, its ablations, the zero-cost gate, entry-timeframe sweep |
| `research/v38/v38grid.py` | the 113,400-cell grid: cached exit tensor, 756 signal sets x 75 geometries, position lock |
| `research/v38/v38feeds.py` | the three restored feeds, clocks re-derived, per-instrument tick and point value |
| `research/v38/run_v38.py`, `run_v38b.py`, `run_v38c.py`, `run_v38_vbt.py` | grid shape and marginals; three candidates and one locked read; the two controls; vectorbt as a second engine |
| `research/v39/v39mc.py`, `run_v39.py` | **the per-rule Monte Carlo** — 40 indicator rules x 3 markets x 2 blocks, bootstrap for the edge, permutation for the path, same-selectivity control on every cell |
| `research/v40/v40feat.py`, `run_v40.py` | 17 features in 8 declared families, signal-bar correlation, family-then-rho selection, the stop sweep and the window table |
| `research/v41/v41seq.py` | the sequenced EMA-cross -> Donchian-confirmation grid, with inert-axis and built-in-control flags |
| `research/v41/run_v41.py` … `run_v41d.py` | the 103,680-cell sweep and pairwise ablation; signal and strategy correlation; perturbation, walk-forward, bootstrap, cost stress, DSR; the cross-market controls and vectorbt |
| `research/v42/v42grid.py` | the 1.84M-cell Turtle space, the fold-median objective, inert-axis accounting |
| `research/v42/v42surro.py` | the grid surrogate and its held-out-by-axis fit test |
| `research/v42/run_v42.py`, `run_v42b.py`, `run_v42c.py` | the parallel sweep; shape, marginals and robust regions; the frozen read on held-back markets with the matched control |
| `research/v43/` | MAE/MFE on eight declared Donchian configurations: both normalisations, the censoring diagnostic, uncensored heat at a fixed horizon, matched controls |
| `research/v44/` | 36 causal features scored by excursion in ATR **and points**; the ratio-picked scalp, its no-filter ablation, a 1-minute barrier walker and time-to-target/time-to-stop |
| `research/v45/` | take-profit engineering from MFE/MAE: the break-even algebra, the p_lower/p_upper bracket, a 1-minute first-touch walker, and the what-would-it-take calculation |
| `research/v46/` | Carver's breakout forecast + causality audit; the 999,717-cell sweep in 73s; freeze, held-back markets, random-entry control, both Monte Carlos, and the vectorbt check that failed parity |
| `research/v47/` | causal daily frame with an exact RTH/overnight split; 30 risk-premium and PEAD-analogue features; drift-vs-reversal test, Newey-West ICs, BH |
| `research/v48/` | Donchian base + 39 risk-premium/PEAD/release-clock features; purged embargoed CV with ridge, LightGBM and a small MLP; family ablation and coefficient attribution |
| `research/v50/` | SELECTION at a FIXED fill rate: a cost-invariant time-to-fill calibrator, both sides, the PRICE split into entry offset and exit path, and the chasing test |
| `research/v51/` | the 1.16M-config single-entry Donchian sweep: MA200 as a level, 13x48, an absorption proxy, session+flatten; tensor verified against an independent reference |
| `research/v52/` | the Turtle reduced to one entry/one exit: 4.64M cells, its own ADX and EMA100 gates swept in BOTH directions, same-selectivity control on three blocks |
| `research/v53/` | parameter-free lower-timeframe absorption, the 280,320-cell underfitting sweep, and the vectorbt transcription check |
| `research/v54/` | the CVD proxy, confirmed-pivot four-pattern divergence, KAMA on an independent timeframe sampled causally |
| `research/v55/` | the automated CVD gate: union vs single pattern, the EMA cross, and the full k x w neighbourhood |
| `research/v56/` | **the dual order-model walker** -- the research engine and the Pine script's own model in one function, diffed trade for trade; plus ADX and an ATR target |
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
| `research/turtle15/pine_parity.py` | the shipped Pine's order model in Python, diffed against the engine |
| `research/ftm/ftm_backtest.py` | its backtest report: sizing modes, exit split, decision path, matched control |
| `research/ftm/ftm_sim.py` | the shipped FTM Pine transliterated to Python and run on real 1m bars |
| `pine/apm/APM_SESSION_VWAP_strategy.pine` | the ATR-phase-momentum / session-VWAP NinjaScript, ported: control shadow, cash close, every fail-closed path counted |
| `research/apm/apm_sim.py` | that Pine's order model on exact UTC 10-minute buckets from NQ 1m; prints the source's terminal counts |
| `research/apm/apm_core.py`, `apm_run.py` | **the APM battery** -- one numba walk per configuration, three matched controls, anatomy, 12,960-cell grid, walk-forward, both Monte Carlos, clusters, funded evaluation |
| `research/apm/apm_wfo.py` | the walk-forward on a user-given configuration: explicit parameter mapping, a grid centred on it, rolling and expanding folds, WFE guarded against a negative baseline |
| `research/apm/apm_edge.py` | the mechanism without the indicator (drive ladder, published momentum, the two-half decomposition) and 17 causal features on the rule's trades |
| `research/trendday/td_core.py`, `td_run.py` | the Raschke trend-day / untouched-EMA EA: the exact order model, its 1m-vs-15m parity, day and mirrored-side controls, grid, walk-forward, MC, regimes |
| `research/trendday/td_parity.py` | **the shipped Pine's order model in Python, diffed against the engine** — exact at 1m, a different strategy at 15m |
| `research/trendday/td_sweep.py`, `td_analyse.py`, `td_finalist.py` | the 127,008-cell two-phase sweep (day filter cached per EMA/bucket), research-only selection by the worst feed, coherence gate, one reserved read |
| `research/trendday/td_sweep2.py`, `td_dc_analyse.py`, `td_dc_final.py` | the same family with a Donchian gate / stop / midpoint target, 543,948 cells, and the vectorbt ladder |
| `research/vwapdrift/vd_core.py`, `vd_run.py` | the RTH VWAP Drift EVO 1 ACSIL study: cached VWAP/ER indicators, both fill models, coin-flip-side controls, anatomy, grid, MC, regimes |
| `research/v59/v59core.py` | the EMA 16/64 exit tensor: 243,000 configs, dual lock kernels, duration-based hold |
| `research/v59/v59judge.py`, `v59lock.py`, `v59_nq.py` | the sorted matched control, the one locked read, the NQ read |
| `research/v58/v58ib.py` | the Initial Balance tensor: 777,600 configs in one walk, both exit models |
| `research/v58/run_v58.py`, `v58judge.py`, `v58lock.py` | the sweep, the risk-matched control gate, the one locked read |
| `research/v58/v58_vbt.py` | the vectorbt second opinion -- 100.0% trade-count agreement |
| `research/v58/v58_nq.py` | the cluster read once on NQ, which chose nothing |
| `research/tune.py` | **the tuning loop** — `tune.py -i`, or one command; indicators/time/entry/TP/SL |
| `research/tuner.py` | its engine: cached exit tensor, rule language, `run` / `sweep` / `reveal` |
| `research/indpool.py` | 42 indicators with the PERIOD as an argument, memoised |
| `research/fastbars.py` | disk-cached bars; 4.5s -> 0.1s cold start |
| `research/donchian/` | the Donchian/EMA/ADX/CHOP reproduction, its control gate and drop-one |
| `research/costs.py` | itemised fees, broker presets, bar-dependent slippage; `real_costs.py` reports the damage |
| `research/v15/v15book.py` | the V15 book: features, both legs, the two geometries |
| `research/v15/v15_parity.py` | **the order-model diff** — the script's one live order vs the engine's eight |
| `research/v15/run_book.py` | the whole V15 table: mechanic, control gate, walk-forward, MC, prop |
| `research/v21/v21regime.py` | the 110-cell ADX x CHOP grid, with selectivity and drift-priced nulls |
| `research/v20/v20linreg.py` | validated rolling OLS + four pre-declared "regression confirms" readings |
| `research/v19/v19frozen.py` | V17's rule frozen and run on four markets that never saw it |
| `research/v19/v19attack.py` | drop-one, perturbation, walk-forward, cost stress, Monte Carlo |
| `research/v19/v19verdict.py` | **the regime-matched control** — random entries from the same up-trend bars |
| `research/v18/v18diag.py` | ADF, AR(1) half-life, Hurst, Lo-MacKinlay VR, Newey-West corr — no statsmodels |
| `research/v18/v18coint.py` | Engle-Granger both ways on five series, 15m and daily, with a positive control |
| `research/v18/v18multi.py` | the spec on every instrument, each with its OWN tick, point value and spread |
| `research/v18/v18results.py` | EV/PF/DD, the 625-cell robustness grid, drawdown consensus, MC |
| `research/v17/v17feat.py` | 21 engineered breakout features, both directions, all causal |
| `research/v17/v17run.py` | the 285-condition sweep; Sharpe over ALL days; same-selectivity null |
| `research/v17/v17judge.py` | ladders, the single locked read, matched controls, stability |
| `research/v16/v16mom.py` | the 58-score momentum pool, signed and side-mirrored |
| `research/v16/v16core.py` | Donchian outcomes precomputed per signal bar + numba position lock |
| `research/v16/v16run.py` | the 2,167-condition sweep and its same-selectivity null |
| `research/v16/v16verdict.py` | **the replication test** — research survivors read once on locked |
| `research/v60/v60core.py` | the V41+Aroon tensor: 142,560 distinct cells a market, inert axes collapsed |
| `research/v60/v60judge.py` | the condition correlation matrix and the marginal-per-axis table |
| `research/v60/v60aroon.py` | the Aroon-Donchian identity, checked bar by bar |
| `research/v60/v60robust.py` | the ladder, the one-rung box, and the in-block walk-forward |
| `research/v60/v60_vbt.py` | the vectorbt second opinion: transcription, order model, fill attribution |
| `research/v60/v60_parity.py` | the shipped V60 Pine's own order model, diffed against the engine |
| `research/v60/v60session.py` | the Aroon reading bar, and the session window x flatten grid |
| `research/v60/v60macd.py` | eight MACD readings x three parameter sets, base rate on breakout bars first |
| `research/turtle2/yt_gates.py` | the YT Turtle with a window, a flatten and an ADX floor; parity-asserted copy |
| `src/lib/quant/tuner/` | the same tuner in TypeScript, running in the browser at `/quant/tune` |

## Pine

Three definitional traps, all of which have shipped broken once: ATR is `ta.ema(ta.tr(true), 14)`
not `ta.atr`; bare `hour`/`minute` are **exchange** time (Chicago for CME) not New York; CCI is on
`hlc3`. Entries require `barstate.isconfirmed` so the Strategy Tester's "Script execution"
checkboxes cannot change the result — without it, tick evaluation fires 5.1× as many signals with
80% on bars that never satisfied the rule. **And guarding the ENTRIES is not enough: guard every
block that writes `var` state.** The Turtle script's `lastWin := close > firstFill` was unguarded, and
mid-bar `close` is the current price — `lastWin` drives the System 1 skip, so it chose which
breakouts to take from a price the bar-close run cannot see. Ticking the three boxes moved the same
rules from −913 / PF 0.994 / 11,398 trades to +62,278 / PF 1.416 / **14,462** trades. The trade count
is the tell, and the bar-close run is the correct one. Ask of every line: does it read a series that
differs mid-bar, and does anything durable depend on the answer? `close`, `high`, `low`, `ta.atr`,
`ta.dmi`, `strategy.opentrades` all do. **If a checkbox changes the report, the report is about the
checkbox.** And guard the WHOLE coupled set, not some of it: guarding the state blocks while leaving
`strategy.exit` open was a half-fix that made it worse — a mid-bar fill re-ran the script with
`stopLvl` still `na`, so the exit fell through to the CHANNEL LOW and cut positions early, leaving
850 trades / PF 1.642 against 762 / PF 1.188. Placement time and trigger time are different things:
a strategy order persists once placed, so setting it at the close still leaves it live intrabar.
Two more ways a report is wrong before its rules are: **the account too small to take the trades**
(US100, same script and range, 850 trades at 100K against 4,806 at 1M — the broker emulator REJECTS
unfundable orders silently, and the rejections cluster where price is high and the ladder is
already large), and **fills that are free** (this script set no commission and no slippage —
`Commission load 0.00%`). Read the TRADE COUNT and the COMMISSION LOAD before the P&L.
See `docs/ib/STUDY_TICK_RECALC.md`.

**A NEURAL NETWORK ON THE STRONGEST SCALP CANDIDATE HERE IS NULL, AND THE SHUFFLED TWIN SAYS SO
BEFORE ANY P-VALUE.** Eight models (ridge -> regularised forest -> LightGBM -> XGBoost d3/d6 -> MLP
2x32/2x64/4x128) on S3's order-flow-exhaustion events, NQ 5m 07:00-11:00 NY, purged embargoed folds,
uniqueness weights, objective = the R EARNED, every model beside a shuffled-label twin. **The twin
beats the real model in 14 of 24 cells (58%)** and **every tree model has a NEGATIVE IC** -- rf, lgbm
and both boosters rank the events backwards and their top decile LOSES (rf@30% -0.194 R, PF 0.614).
**Gate 2: 0 of 24 cells clear a same-selectivity random filter OR a day-block bootstrap**, best
control p **0.348**, and **p90 of R falls below baseline in 21 of 24 cells** on the objective chosen
to preserve the tail. **CAPACITY IS INERT, WHICH IS NOT V28's FINDING** -- ridge -0.012, 2x32 +0.031,
2x64 -0.014, 4x128 +0.018 is one number with noise on it; neither "deeper is worse" nor "deeper is
better", which is what a null looks like when the architecture axis is swept. Ensembling INVERTS the
score (full ensemble p 0.984-0.990) because it averages in five backwards-ranking models. **THE
ARITHMETIC IS THE DURABLE OUTPUT**: mean win +0.824 R against mean loss -0.859 R at a 0.519 win rate,
so **PF 2.0 needs +15.7 points of win rate and the best of 99 model cells delivered +3.0** -- one
fifth of the gap, holding the win/loss SIZES fixed, which is the generous reading. Sharpe rises
0.293 -> 0.707 at keep-50% and is bought by trading less, not by choosing better.
**TWO SETUP DEFECTS CAUGHT BY THE CHECKS BEFORE ANY MODEL RAN**: `ctx.atr_rank_day` ranked ATR against
the WHOLE session so a mid-morning bar saw the rest of the morning (truncation audit 20 of 900, now
0 of 900); and the training set was 380 rows against 45 features, which **widening the signal window
does not fix** (w=60 gives 383, three more than w=20). The fix is to drop the POSITION LOCK FOR
LABELLING ONLY -- the lock decides which events one account can ACT on, not which have a well-defined
outcome -- taking it to 1,672 events / 1,140 research / effective n 960, and it is what makes the
labels genuinely overlap (mean 1.62 concurrent, uniqueness min 0.340) so purged folds and uniqueness
weights stop being decoration. The strategy still runs LOCKED at inference. Note purging then costs
only 0.3% of training rows, because an 11:00 flatten makes labels short and overlap binds only at
fold boundaries. 99 trials counted, **NO LOCKED READ TAKEN** -- nothing cleared Gate 2 on research, so
the block is unspent. What would move it is more EVENTS (1,140 rows is six years of one market at
~190/yr), not more capacity. See `docs/ib/STUDY_S3_NEURAL_NET.md`, `research/s3nn/`.

**THE SAME RULE ON A 10-MINUTE CHART LOSES AT EVERY ONE OF 630 GEOMETRY CELLS ON THE BLOCK THAT MAY
CHOOSE IT, AND THE DEFLATION THEN KILLS THE 5-MINUTE VERSION TOO.** S3 flow exhaustion (confirmed
price pivot against a CVD pivot of the opposite sign) resampled from NQ_1m to 10m, 07:00-11:00 NY,
flat at 11:00. **k and w are BAR COUNTS, so carrying them doubles their reach in minutes** -- both
readings were declared: CARRY k3/w20 (30/200 min) reads research **-7.49 pts PF 0.696 Sharpe -1.34**
and locked +5.97/1.217, MATCHED k2/w10 (20/100 min) reads -3.28/0.876 and +10.63/1.352. Matching the
MINUTES beats carrying the numbers and both are negative on research. **COST IS RULED OUT IN
ADVANCE**: the 1.72-pt round turn is **2.93% of a 3xATR stop at 10m against 3.78% at 5m**, so the
wider bar is CHEAPER -- and the execution MC gives **P(total<=0) = 1.00** on both 10m research arms.
630-cell geometry grid: **0.0% profitable on research and 99.2% on locked, corr(research, locked)
-0.823 Pearson**; every marginal negative on research at every setting of every axis; the 96-cell
one-rung box **0% / 100%**. Nulls: a random entry with the same geometry BEATS the rule on research
(p 0.922 / 0.678) and so does a **coin flip on its own bars** (p 0.958 / 0.735), so at 10m the
direction call is worth less than nothing. The 10m carry research bootstrap CI is
**[-15.46, -0.05] -- it excludes zero on the NEGATIVE side**, a significant LOSS, while neither 10m
locked arm separates from zero (0.239 / 0.103). Price jitter with the pivots, CVD and ATR ALL
RECOMPUTED keeps the sign in **100%** of draws -- robust, and robustly negative.
**THE 10m DEFLATION STANDS AND MY EXTENSION OF IT TO 5m WAS WRONG -- CORRECTED BELOW.** White's
reality check over the 28 10-minute candidates reads **p 0.660 FAIL**.
**AND THE TIMEFRAMES DISAGREE ONLY ABOUT WHEN THE REGIME TURNED**: by year the 5m rule goes
-1.82 / +8.45 / +10.32 across 2023/24/25 while 10m goes -10.08 / -5.53 / +6.02 -- the sign flips
during 2024 at 5m (inside research) and not until 2025 at 10m (inside locked), which is the entire
difference between the two verdicts. Daily P&L correlation between the two timeframes is only
**+0.107 research / +0.034 locked**, so the 10m run is an INDEPENDENT read on the same idea rather
than a coarser view of it, and correlation with always-long is -0.04..+0.08 on every arm so neither
is drift. Across 15 (k,w) cells median pairwise corr is +0.349 with 5 of 15 components carrying 90%
of variance -- a real family, not one rule in fifteen hats, which is what makes 0% research
profitability across it hard to dismiss. Also here: `s5sig._pivots` is a Python loop over every bar,
which made a jitter MC that recomputes the signal cost hours; `t10core.pivots_fast` is a
`sliding_window_view` twin **asserted identical at k=1..5 and on three declared cells before use**,
200x faster. See `docs/ib/STUDY_S3_10M.md`, `research/s310/`.

**FTM ALPHA.2 OUT OF SAMPLE: PROFITABLE, AND NOTHING ABOUT IT SEPARATES FROM A NULL.** Split at
2025-01-01 with every control computed INSIDE its own block, the published +0.1013 R excess at
p 0.004 reproduces STUDY_TOP5's correction on both versions -- RC1 p **0.005 in sample -> 0.151
out**, alpha.2 **0.005 -> 0.257** -- and the control itself EARNS +0.056 R, so the null is
profitable and the rule adds +0.040 R to it out of sample. **THE ALPHA.2 POLICY CHANGE HELPS IN
SAMPLE AND HURTS OUT OF SAMPLE** (+0.1999 vs RC1's +0.1942, then +0.0956 vs +0.1194). **`h2_cap`
HAS NO EFFECT ON R AT ALL** -- identical +0.1551 at every value, cap 0/2/3 producing the IDENTICAL
net so two of four settings are inert; it only cuts SIZE on a handful of flips, worth -$441 and
nothing else. `prior_bars` has NO GRADIENT (OOS R 0.0956/0.1194/0.1041/0.1307/0.1208 at 1-5) and
alpha.2 picked the WORST rung while the best is 4, which nobody chose; in-sample R is IDENTICAL at
2,3,4,5. **DROP-ONE: 8 OF 12 COMPONENTS IMPROVE THE OOS RESULT WHEN REMOVED, AND ALWAYS-LONG WITH
THE IDENTICAL EXIT MACHINE EARNS 2.7x THE RULE** (+0.2564 vs +0.0956, PF 1.663 vs 1.252) while
being WORSE in sample -- the whole direction apparatus helps where it was developed and hurts where
it was not. The direction call is worth **+0.025 R over a coin flip out of sample against +0.216 in
sample**. Only the entry refinement is load-bearing OOS (-0.0105 without it). No take profit won
for the 24th time. The four TradingView compatibility gates IMPROVE the result (454 trades at
+0.1222 OOS against the source's 342 at +0.0956), and the lookback axis is flat across 20-120,
confirming the 120-session warm-up never earned its constraint. **MC: the OOS block does not clear
zero** (P(mean<=0) 0.138, CI [-21.33, +74.74]) and p99 drawdown is 2.0x realised. **COST IS NOT THE
OBJECTION AND R IS BLIND TO IT** -- profitable at 4x, with R/trade IDENTICAL at every multiplier,
so quote DOLLARS whenever cost is the question. **FORWARD TEST: 500 trades = 3.1 YEARS to show the
OOS mean differs from zero**, and the S3 win-rate shortcut does NOT transfer because FTM's payoff
ratio is 1.38:1 (break-even 42.1%, actual 47.6%) -- the edge is the PAYOFF, which converges slowly.
Monitor the EXIT MIX instead: stop 50%, cond1530 20%, close1600 16%, target 14%, with the 15:30
rule alone +206% of OOS net and stops -368%. **AND EVERY PUBLISHED FTM FIGURE IS ON A SAMPLE MISSING NOVEMBER TO FEBRUARY.** Six months of the
26 contain ZERO trades and the feed is complete in all of them (27-30k bars each) -- the strategy
refuses, under every configuration of the four compatibility gates. The cause is the mandatory
**23:00 UTC reference open**: in summer that minute is 19:00 New York, mid-session, and in winter it
is 18:00 New York, the CME session-open minute, for which this feed carries NO BAR. Measured, 23:00
UTC bars per month run **20-23 from March to October and ZERO in Dec/Jan/Feb**, November 0-2. A date
without it blocks entirely, so `STUDY_FTM_ORB_BACKTEST`, `STUDY_FTM_ANATOMY`, `STUDY_FTM_ALPHA2` and
everything above describe a MARCH-TO-OCTOBER strategy. **And the shipped Pine does not do this** --
its `refOpenFallback` defaults ON and substitutes the session's first bar, giving **578 trades /
+$15,017 / +0.1119 R / ret-DD 7.16 against the research's 342 / +$10,319 / +0.1551 / 4.02**: 69% more
trades for 46% more dollars at a 28% LOWER per-trade R, with the 179 winter trades earning -0.0136 R.
The script and every number in its header are different strategies. Deflated for the synthetic NQ
levels the studied version earns **$4,814/yr on $50,000 = 9.6%/yr at a 5.1% worst drawdown**.
`ftm_sim.run(ref_fallback=)` reproduces either. See `docs/ib/STUDY_FTM_OOS.md`,
`research/ftm/run_o1.py`..`run_o4.py`.

**A SCALE-FREE MINIMUM RANGE IS THE RIGHT FIX FOR A COST PROBLEM AND IT RESCUES NOTHING, BECAUSE THE
GROSS EDGE IS THE DRIFTLESS BOUND.** The Loadish Starboard multi-session ORB's Asia and London
sessions lose where New York does not, and `STUDY_V69_ORB` attributed it to arithmetic. Tested
rather than asserted, with the prediction written down first -- **if the attribution is right, GROSS
profit factor must stay FLAT across range buckets while NET rises**, since a range filter cannot
change what a market does, only the denominator a fixed cost is divided by. It is right and it is
quantitative: cost/risk runs **0.098 / 0.071 / 0.026** across Asia / London / NY against break-even
gaps of **-0.082 / -0.061 / -0.010**, near-proportional, and along every ladder cost/risk falls
monotonically (Asia 0.115 -> 0.048) while net PF converges upward on a gross PF that does not move
(Asia 1.000 -> 1.010 -> 0.999 -> 0.904). **WHICH IS WHY IT RESCUES NOTHING: a range gate moves net
toward gross and can never pass it, so GROSS IS THE CEILING -- and gross win rate lands within HALF A
POINT of the driftless bound in all three sessions** (0.5507 / 0.5587 / 0.5514 against 0.5556 at
RR 0.8). The barriers are hit by noise; there is nothing under the cost to uncover. Fourth family
after `STUDY_THE_STRAT`, `STUDY_IB25_RETRACEMENT` and `STUDY_VWAP_STOCH_ATR`. **0 of 9 gate cells
clear a same-selectivity random filter** over session instances re-simulated (best p 0.087; Asia is
beaten by the random filter in all three of its cells), so no locked read was taken. **AND THE
POINTS GATE IS ONLY WRONG ACROSS SESSIONS** -- inside one session price level moves slowly so points
and percent are nearly the same cut, and ladder C is not measurably worse than percent-of-price or
x-ATR there; the defect is ONE GLOBAL INPUT applied to three sessions whose ranges differ four-fold,
so a value that gates Asia passes essentially every New York instance. **BEFORE BUILDING A FILTER TO
FIX A COST PROBLEM, READ THE GROSS RESULT** -- it is the ceiling the filter is climbing toward, and
if it sits at the geometry's own break-even the filter cannot help however well it is designed.
See `docs/ib/STUDY_V69_ORB.md` section R5, `research/v69/run_r5.py`.

**NO MARKET-DATA HOST IS REACHABLE FROM THIS ENVIRONMENT.** CBOE (`cdn.cboe.com`), Stooq and Yahoo
Finance all answered **403 at the CONNECT** -- an organization egress-policy denial, not a transient
failure, and the agent proxy's README says to report such denials rather than retry them. So the
V69 script's shipped `useVixFilter` (default ON, 17.00 ceiling) cannot be evaluated, and CLAUDE.md's
standing finding that **the VIX cannot be joined to any futures feed here** stands for a second
reason: not only does `data/VIX_daily.csv` end 2021-12-31, but no replacement can be fetched. A VIX
series covering 2022-2026 has to arrive by upload, like every other feed on this branch.

**AN INTRABAR CONVENTION WAS WORTH TWICE THE ENTIRE EDGE, AND IT HAD TO BE SETTLED ON FINER DATA
RATHER THAN CHOSEN.** The CrackingMarkets intraday volatility breakout (daily ATR(5); long at
`open + 0.4xATR`, short at `open - 0.4xATR`; stop AT the session open so risk is exactly 0.4xATR;
one attempt a side a day; no target; exit at the stop or the close) puts the stop and the entry
inside one 15-minute bar. Resolving that as a stop -- this branch's standing convention -- gave
PF 0.69-0.76 and a losing strategy at an "ambiguous" share of 18-19%. **THE CONVENTION IS FLATLY
WRONG ON THE SESSION'S FIRST BAR: it OPENS at the stop, so its low is at or below it with
probability 1 and the flag carries no information at all.** 100.0% of first-bar entries are flagged
and they are 12.4-12.9% of ALL trades; excluding them the genuine share is 6.3%. Settled on NQ
1-minute data -- same rule, same sessions, resampled to 15m so only the resolution differs -- **the
1-minute ambiguous share is EXACTLY 0.000**, because the stop is 0.4 of a DAILY ATR away and no
single minute spans it. The 15m convention that reproduces the truth is the optimistic one, at
**correlation 1.0000 and 100% identical exit reasons**; blanket pessimism was worth **-0.1029
%/trade, more than twice the whole edge, and flipped the sign**. For this geometry 15-minute bars
are adequate and the article's 1-minute data buys nothing. Before applying an intrabar tie-break,
ask whether the flag can fire STRUCTURALLY -- an entry bar that opens at the stop always trips it.

**THE BREAKOUT LEVEL IS THE WORST PART OF THE BREAKOUT, MEASURED A THIRD WAY.** Against a
RISK-MATCHED random entry on the SAME days and SAME sides (stop 0.4xATR from that entry, same close
exit), the rule loses at **p 1.000 on all four blocks of two feeds**: random earns +0.1058 to
+0.1557 where the rule earns +0.0045 to +0.0473. Read with the all-days control (which the rule
beats at p 0.000-0.020), **day selection is worth +0.11 to +0.17 %/trade and the timing is worth
-0.09 to -0.15** -- days that travel 0.4xATR from the open trend, and entering anywhere on them
beats entering at the level. `research/atme/` and `STUDY_V43` from a third direction. **BUT THAT
CONTROL IS NOT TRADEABLE** -- the day is in the sample BECAUSE the level broke, so a random bar can
precede the break and knows what the trader does not. The FEASIBLE version (enter at a random bar
at or after the break) SPLITS AND THE SPLITS DISAGREE: US100 fails research (p 0.850) and passes
locked (0.000), US30 the reverse (0.010 / 0.212), forward block 0.470. Noise, not a mechanism.

**AND ALWAYS-IN BEATS IT ON EVERY BLOCK.** Buy the open, sell the close, no stop, no ATR, no
shorting: it wins on TOTAL RETURN on all five blocks and on Sharpe on three of five. Gate 1 reads
US100 PF 1.020 research / 1.190 locked, US30 1.023 / 1.084, NQ 1-minute 1.226, and **US30_ISO --
the reserved forward block from a DIFFERENT provider -- 0.963, negative, where always-in made
+12.5%**. No block's day-block bootstrap excludes zero (best P(mean<=0) 0.061). At the article's own
0.33% sizing: 3.1-6.0%/yr on US100, 1.1-2.8% on US30, 5.6% for the two-market book at Sharpe 0.63,
against a claimed 27%/yr at 1.04 -- though six markets across two asset classes from 2018 is a
different test and the legs here correlate +0.375, so the diversification the article has is real
work nothing on this branch can represent. **COST IS NOT THE OBJECTION, WHICH IS RARE HERE**: the
round turn is 1.5-3.2% of the stop because the stop is 0.4 of a DAILY ATR, and it survives 2x costs
on three of four blocks. The 0.4 multiple INVERTS between feeds (US100's marginal rises monotonically
to 0.8 where 0.4 is the WORST rung; US30 falls off a cliff at 0.8 where 0.4 is among the best), the
ATR PERIOD is close to inert as the author claims, and the author's own named enhancement -- filter
out low-volatility days -- clears **0 of 8 rungs** against a same-selectivity random filter. Two
trades occur on 11.3% of sessions and both are live at once on **0.1%**, structurally: `dn < open <
up` with the stop AT the open, so the short trigger is unreachable while a long is open. Parity:
trade count 1.000 / 0.999, same exit bar 0.9971 / 0.9990, correlation 0.9977 / 0.9970 -- and **the
END-OF-DAY CONVENTION IS 25-84% OF THE RESULT** (`strategy.close_all()` fills at the next bar's open,
worth -0.0051 %/trade on US100 and +0.0070 on US30, no consistent sign).
Ships `pine/volbo/VOLBO_ATR_BREAKOUT_strategy.pine` with the numbers in its header and no edge
claimed. See `docs/ib/STUDY_VOLBO_BREAKOUT.md`, `research/volbo/`.

**`research/ivb.py` ALREADY EXISTED (Initial Value Breakout) AND A NEW `research/ivb/` PACKAGE
SHADOWED IT SILENTLY** -- `from ivb import ivbcore` resolved to the MODULE and raised ImportError,
which is the lucky failure; a name that had resolved would have imported the wrong code. Sixth
name-collision on this branch after `.first`, `.align`, `agg`, `metrics` and the `vol.`/`vlm.`
feature prefixes. Check `ls research/<name>.py` before creating `research/<name>/`.

**A VOLUME-PROFILE FEATURE FAMILY CAN BE CLEAN, CAUSAL AND BINDING AND STILL CLEAR NOTHING -- AND
THE ADVANCED QUANT LAYER SUBTRACTED FROM BOTH PRIMARIES.** Max Anderson's *Volume Profile Analysis*
plus a combined US30 study guide (Forthmann/Whalestrader/Anderson), built on the uploaded
`us30_20162025_15m_data1.csv` -- sha256 24dcf2e1c7ba398f, BYTE-IDENTICAL to `US30_LONG_15m`, so both
blocks are second reads. **`Volume` IS ZERO ON 100% OF ROWS and `TickVolume` is the real column**
(corr with bar range +0.7661), so every profile here is a TICK COUNT profile; the study guide reaches
the same conclusion independently and correctly rules the whole order-flow layer (footprint, delta,
absorption) MEANINGLESS on a CFD feed, because those tools read an aggressor side a CFD does not
have. 2,246 RTH profiles, bins scale-free at 0.10 x session ATR, POC inside the value area on 100.0%
of sessions. **52 causal features** -- 22 volume-profile (POC/VAH/VAL distances, nearest HVN/LVN,
STACKED-POC counts, the bullish/bearish/neutral distribution taxonomy, developing intraday POC) plus
30 advanced quant (Parkinson/Garman-Klass, vol-of-vol, ATR rank, the same quantities against a CAUSAL
TIME-OF-DAY baseline, fracdiff d=0.2 by ADF on research only, a Baum-Welch HMM read FILTERED,
momentum, structure). **Truncation audit 3/3 on profiles and 0 mismatches of 23 on the rolling quant
features**, and the BASE-RATE CHECK PASSED FOR THE FIRST TIME IN THIS FAMILY -- no feature exceeds 95%
on the trigger's own bars, largest lift `inside_va` at 2.92x. **GATE 1 ON FIVE PRIMARIES: 0 of 10
tests clear p<=0.05 against 0.5 expected.** HVN retracement 1.008/1.045 (p 0.440/0.440), LVN breakout
1.054/1.086 (0.200/0.340), NAKED POC 1.124/1.273 (0.200/**0.100**, the best), open rejection reverse
1.021/1.034 (0.500/0.260) -- and **POC SHIFT, WHICH THE GUIDE CALLS "THE BEST TREND-ENTRY SIGNAL IN
THE BOOK", IS THE ONLY NEGATIVE PRIMARY ON RESEARCH** (PF 0.907, p 0.620) and positive only on the
holdout, the wrong shape for the 14th time. Cost is NOT the objection: the round turn is 2.1-2.6% of
a 1.5xATR stop and every primary is gross-positive. **GATE 2 IS THE REAL FINDING: EVERY UPLIFT AT
EVERY KEEP FRACTION ON BOTH PRIMARIES IS NEGATIVE** (LVN -0.0035/-0.0005/-0.0255, naked POC
-0.0409/-0.0379/-0.0087) at random-veto p 0.420-0.700, scored as a VETO and re-simulated; the
holdout kept-50% read is WORSE than the base on both (LVN +0.0215 -> **-0.0525**, naked POC +0.1065
-> +0.0620) and **the threshold is not calibrated across the split** (kept 0.575-0.600 against a 0.50
target). The SHUFFLED TWIN wins 1 of 4 models on LVN and **2 of 4 on naked POC**. DSR 0.1015 at 14
counted trials. Third volume-profile result here, agreeing with `STUDY_AUCTION` (7 of 172 passes,
fewer than chance, 0 surviving) and `STUDY_VP_TPO_NEXT` (the one NQ survivor scoring PF 0.927 against
0.973 ON THIS EXACT US30 FILE). **DO NOT RE-RUN THIS FAMILY.**
See `docs/ib/STUDY_VP_US30.md`, `research/vpus30/`.

**A DONCHIAN BREAK ON US30 IS PROFITABLE ON EVERY CELL AND DISTINGUISHABLE FROM A COIN FLIP ON
NONE, AND THE META LAYER'S ICs TRANSFER WHILE ITS UPLIFT DOES NOT.** `STUDY_VP_US30`'s profile
setups were demoted to the meta layer and a Donchian channel break with an ATR stop made the
primary. Gate 1, 8 declared cells (entry 20/55 x stop 2.0/3.0N x long/both, opposite-20 channel
exit, no target, entries RTH, exits on the full frame): **all eight are net-profitable on BOTH
blocks (PF 1.02-1.13) and 0 of 8 clear a risk-matched random entry** (best p 0.150 against 0.4
expected), with cost at 1.4-2.7% of the stop so cost is not the objection. Eighth Donchian breakout
here to fail its own control. 66 features (22 VP + 30 quant + 14 new `don.*`), truncation audit
**0/168**, and the base-rate check binds honestly for once -- only `p_neut` and `don.age` are
degenerate on the trigger's own bars and the largest lift is **1.75x**, against RSI's 94.7%,
Aroon's 100.0% and MACD's 99.8%. Screen: **8 of 128 veto cells clear against 6.4 expected**, and the
two leaders are `p_bull` and `stack5` -- exactly the two constructions in Anderson's book that were
NOT in `STUDY_AUCTION`'s 47-condition pool. Ladder: **twin wins 0 of 4**, the cleanest noise floor
measured here, **ridge wins outright** (IC +0.0755 against rf 0.0438, xgb 0.0334, lgbm 0.0178) --
sixth family where the linear model beats every booster. Gate 2 clears 2 of 12 (0.6 expected), both
ridge, monotone in selectivity, research P(uplift<=0) 0.066. **AND THE FAMILY ABLATION SAYS THE
REQUESTED FEATURES ARE THE MOST HARMFUL**: dropping `don`, `ffd`, `hmm` and `str` all IMPROVE the
model and the 40-feature load-bearing subset (vol/vp/tod/mom) scores 0.0890 against 62 features'
0.0755 -- feature engineering subtractive for the fifth time. **ONE HOLDOUT READ: uplift +0.0016,
IC -0.0032, a random gate of the same size EARNS MORE (p 0.525), total return 12.87% -> 6.94%** --
and the threshold **kept 0.507 against the 0.50 it was set for**, so it is CALIBRATED and the
failure is predictability, not `STUDY_AUTOBNN`'s miscalibration. DSR **0.427 at 157 looks**:
per-trade Sharpe 0.0350 against an expected best-of-noise **0.0452**, below its own noise floor.
**THE TRANSFER DIAGNOSTIC IS THE FINDING AND IT IS A DIFFERENT FAILURE FROM THE USUAL ONE**: across
62 features `corr(research IC, holdout IC)` is **+0.641 Pearson with the sign kept 71%** -- far
above this branch's usual -0.03 to +0.2 -- while mean |IC| halves **0.0707 -> 0.0386**. The
direction survives and the SIZE does not, so a high transfer correlation is not evidence a filter
will work. **AND THE EIGHT STRONGEST FEATURES ARE ONE FEATURE**: `d_poc`/`d_vah`/`d_val`/`dev_pos`/
`d_ema78`/`d_ema26`/`rsi14`/`ffd.z250` have mean pairwise **|rho| 0.820 on the signal bars**
(d_ema26 vs rsi14 **0.99**) and all point one way -- the further above its references price already
is when the channel breaks, the better -- which is `STUDY_V40`'s distance finding with the POC and
value edges in place of an MA. **Seventh pool-duplication catch**, two of them EXACT:
`dev_pos == str.sess_pos` (rho 1.0000, `vpquant` reads the column) and
`don.atr_pct == don.stop_pct` (a constant multiple). Ships nothing.
See `docs/ib/STUDY_VP_DONCHIAN_US30.md`.
