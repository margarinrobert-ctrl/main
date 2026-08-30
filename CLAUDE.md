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
