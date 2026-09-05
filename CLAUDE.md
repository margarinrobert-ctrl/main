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
| `research/strat/` | The Strat combo engine: bar types, four location filters, one-bar stop order, trade-matched control |
| `research/ddc/` | the Double Donchian Pine's order model, literal vs intended TP, trade-matched controls |
| `research/mrl/` | the two library-built designs: strict 1-minute limit walk, 15m bar walk, ladders with a random-filter gate, the trend grid |
| `research/orb/` | ORB v1 to spec: causal build with the ATR timeframe as an explicit axis, signals vectorised, exits walked on the TRUE 1-minute path, equity-compounding sizing with whole-lot flooring, a truncation audit, three matched controls and a 4,320-cell sensitivity sweep read by marginal average; `orb_feeds.py` adds the three 15m feeds with per-market contract specs and `orb_regime.py` the ADX/DI/slope regime as a sequential hysteresis state machine, frozen on completed 15m bars and forward-filled |
| `research/overlay/` | the fast-alpha execution overlay: a 1-minute reversion gate scheduling Donchian entries, the four screening gates, the seven-part battery (Roll bounce floor, random-delay placebo, PnL attribution, paired block bootstrap, tails, cost sweep and fill haircut, missed-trade census), and the same battery re-run on a POSITION-LOCKED baseline with the placebo inside each block |
| `research/scalpreq/` | the scalp-requirements experiment: 31 conditions x 2 triggers x 2 geometries x 6 feed-timeframes, with base rates, the cost-as-a-fraction-of-risk table and the zero-cost variant |
| `research/v63/` | the VWAP / triple-EMA / ATR trend design: three feeds with real volume, a chandelier-trail tensor, search on one market and a frozen read on three, drop-one and the binding hold axis |
| `research/v62/` | the confirmation study: base rates on the trigger's own bars, a 3.1M-cell grid in exact on/off twins, matched pairs on both blocks, and the drop-one |
| `research/v64/` | Optuna on V61, its walk-forward and its Monte Carlo: a continuous-space numba evaluator verified to the cent against the published grid, three Optuna studies, fANOVA importance, the box-edge re-run, the V30 hold-out-an-axis surrogate; `run_wfo*.py` in-fold re-selection with a random-cell arm, span-normalised WFE and a geometry-matched control; `run_mc.py` perturbation (price jitter with the indicators RECOMPUTED, execution, missed fills, parameters) beside the permutation and the bootstrap |
| `research/v61/` | the CVD optimisation: a verified exit tensor (725,760 configs in ~4s a timeframe), research-only marginals, one locked read, the second null, the gate ablation and both presets' parity |
| `research/top5/` | **the cross-strategy battery** -- one trade table for eight engines, the ranking in percent of price, each strategy's own control, IS/OOS + two Monte Carlos + robustness + a nine-gate live-readiness scorecard |
| `research/ftm/ftm_anatomy.py` | FTM reverse-engineering: drop-one anatomy, 200-cell grid, walk-forward, clusters, robustness, MC |
| `docs/ib/EDGE_LIBRARY.md` | **the mechanism library** -- what survived, what it is, how to take a new strategy apart |
| `research/ema48/` | EMA 13/48 x VWAP S/R x ATR stop x ATR trail on the scalp89 order model: the declared 24-cell grid, ablations, stop and trail ladders, random-entry control, cross-feed reads; `e48_features.py` (37 causal features, 8 families, truncation audit); `run_ml.py` the purged-embargoed ladder ridge -> logistic -> LightGBM -> XGBoost -> MLP with shuffled twins, same-selectivity random filter, one locked read per base |
| `research/trend/` | the diversified trend ensemble to its spec's own layout: `config.yaml` (constants, split date, calibration c), `data.py` daily panel with t+1-open execution, `volatility.py`, `forecast.py` (sleeves, scalars, FDM), `portfolio.py` (rolling IDM, sizing, buffered trade-to-the-edge), `trend_costs.py` (drag rule), `backtest.py`, `validate.py` (the full section 8 battery on the skill's scripts), `tests/` (alignment, scalars, vol target), `research_log.md` |
| `research/scalp89/` | the submitted NQ Scalping System transcribed with its order model (naked fill bar, Pine intrabar path, no flatten -- each modelled both ways), exit-machine and entry ablations, fixed-horizon signal tests on four feed-blocks, matched controls, a 160-cell geometry sweep, a 729-cell in-fold walk-forward with a random-cell arm, and a perturbation Monte Carlo with the indicators recomputed; `research_log.md` carries the trial count |
| `research/inst/` | the PF-2-at-200/yr question answered as a frontier: `frontier.py` (the win-rate arithmetic for PF 2, the V61 tensor with intraday hold caps and RTH entries over 4.08M cells, the PF-vs-count envelope read once on locked, the DSR at the trial count), `book.py` / `book2.py` (every validated intraday leg pooled in percent of price with per-feed costs, leg correlations, the research-selected book), `meta.py` (meta-labeling with a regression-on-R objective, purged and embargoed, shuffled twins, same-selectivity null, one locked read) |
| `research/tscalp/` | the submitted Turtle Scalp Pine transliterated with its order model (armed stop, late re-anchor, pyramid bracket, 2R target, flatten at the next open), three EMA gates as entry masks, base rates on the breakout bars, a 36-cell grid by marginal, drop-one, same-selectivity control, cross-market, three Monte Carlos, neighbourhood, and one descriptive locked read |
| `research/absorb/` | the 50% session level + MTF ICT swings + absorption bubbles as one reversal system: causal construction with a truncation audit, base rates and lift BEFORE any P&L, a 211-cell grid read by marginal average, the exit tested fairly (no-trail arms given a real exit), drop-one, random-entry and same-selectivity controls at every trail width, the intrabar tie-break split, and one locked read |
| `research/scalp89/s89_pine.py` | the CORRECTED order model -- what `strategy.exit` actually does on the fill bar when its stop/limit args are still `na`; verified trade-for-trade against `research/scalp89/test_pine.py`'s independent reference |
| `research/ib25/` | the posted IB-25 retracement: session VWAP, a running 09:30-10:30 range, one live limit order a session, the three prose conditions codified as explicit parameters, the retracement and stop ladders against their own driftless break-even, a random-entry-minute control, one locked read, and `run_ib25_mnq.py` -- the dollar view with the synthetic-level deflator |
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
