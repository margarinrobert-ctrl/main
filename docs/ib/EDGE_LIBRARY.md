# EDGE_LIBRARY — the reverse-engineered mechanisms that survived, and how to use them

This is the distilled companion to `EDGE_LEDGER.md`. The ledger records every brief and its
verdict; this file keeps only the MECHANISMS that survived their own controls, states what each
one actually is once the indicator names are stripped off, records the evidence and its
qualifications, and ends with the procedure for taking a brand-new strategy apart. Entries are
added only when a mechanism has cleared a matched control on a block it was not selected on.

Read it with one rule in mind: **a strategy is a bundle of an entry, a location, an exit
geometry, a session and a sizing rule, and on this branch the edge has almost never been in the
entry.** Every reverse-engineering below found the money somewhere the author was not looking.

---

## 1. Mechanisms with real, controlled evidence

| # | mechanism, stripped of its indicator | where it was found | evidence (controlled, out of selection) | what it is NOT | qualifications |
| --- | --- | --- | --- | --- | --- |
| E1 | **Short-horizon mean reversion at the EXECUTION layer**: a resting limit 0.75–1.0×ATR(5) against the move, instead of a market order, on a trade you were making anyway | `STUDY_LIMIT_ENTRY`, `STUDY_ATME`, `STUDY_V10_LIMIT`, `STUDY_V14_WINDOW_GRID`; **corrected by `STUDY_NEW_DESIGN`** | +$4 to +$38/trade on every bar with no rule, both sides, four markets, at broker-only costs and touch fills. **With ONE live order, the target allowed only from the minute after the fill, through-fill and real MNQ costs, the every-bar entry is PF 0.81–1.02 on 256 geometries and the lift over the driftless base is 0 to +3 points**; the same on three 15-minute feeds | a signal (0.28 ticks); an add-on to a good signal; and at real costs, a standalone edge | the +0.24 to +0.43 R figures stand only for a market-order comparison; the mechanic is worth a better fill on a trade taken for another reason, nothing more |
| E2 | **The exit geometry of a trend follower: ATR stop, N-bar channel exit, ONE unit, NO target, market order** | `STUDY_V11_MARKET`, `STUDY_V12_DONCHIAN_3020`, `STUDY_INTRADAY_HEAT` | Donchian 55 + ADX≥25 + 2.5N + 20-bar exit beats a random-bar control at p 0.007 and a same-selectivity filter at p 0.016 on NQ locked; "no take profit" beat every target tested three independent times; 0 of 1,027 OOS trades ever reached a 5R target | the breakout trigger (fails its control at 30/20 on US30, p 0.06–0.29); the ladder (drawdown ×3) | drawdown triples out of sample; channel length decides whether the trigger carries information; a channel stop is NOT a safe unit of risk |
| E3 | **ADX ≥ 25 as a REGIME FLOOR on a breakout, with two independent readings** | `STUDY_V11_MARKET`, `STUDY_TURTLE_15M`, `STUDY_V13_MA_REGIME` | at ADX≥15 the same system fails at p 0.12–0.43, at ≥25 it passes; ADX≥25 AND ER(20)≥0.30 AND CHOP≤55 lifts a 30/20 breakout from PF 1.04/p 0.69 to 1.24/p 0.064 and is positive on five blocks, three asset classes, 22 years | a standalone trigger (p 0.994 alone); a momentum confirmation on a breakout (99% of breakout bars already pass) | inverts on the instrument it was fitted to (US30 2026); locked > research on US100, the wrong shape; exploits the control's lack of volatility matching |
| E4 | **A LEVEL from the last completed session as a breakout gate: the prior RTH session's high** | `STUDY_V17_FEATURES` | takes V11 from locked PF 1.31 → 1.78, Sharpe 1.05 → 1.55, and from failing its matched control (p 0.213) to passing (p 0.014); gradient sign-consistent on both blocks | a trend state (every daily trend tested p 0.23–1.00); the prior close (p 0.150) | one replication of a gradient, not a result; its pool of 285 was null overall **Replicated intraday in `STUDY_NEW_DESIGN`**: on a 15m Donchian 55 breakout held inside the session, the gate takes NQ locked PF 1.00 → 1.24 and is the only component whose removal kills the cell; the same rule is PF 1.34 / 1.56 / 1.20 on US100's three blocks with two control passes |
| E5 | **Retracement DEPTH into a session range before the entry** | `STUDY_V58_ANATOMY` (the IB model) | monotone across all five rungs, 0.00 → 0.50: +0.023 (p 1.000) → +0.309 (p 0.000) against its control; every other condition in the model is inert | the Initial Balance itself (14 IB features, 0 survive); ADX ≥ 20 (backwards) | the NQ block is spent for this family; needs a second instrument |
| E6 | **Three near-independent gates on a 15-minute Turtle, INVERTED from the source: ADX floor, EMA-distance floor, ATR-expansion floor** | `STUDY_TURTLE_15M` | PF 0.94 → 1.58 research, 1.56 holdout; frozen and applied to US30 and XAUUSD both flip from negative to positive; the count of gates gives a monotone chop score | the source's ceilings (both inverted); 07:00–11:00 (worst window) | NQ holdout n 88, bootstrap [−23.9, +140.7]; the 2026 forward slice is the worst; costs must be a fraction of the stop before comparing markets |
| E7 | **A daily-scale barrier pair that pays at the TIME exit: V1** | `STUDY_1R_MORE`, `STUDY_EURUSD_LEGS`, `STUDY_US100`, `STUDY_BTC_LEGS` | the only rule with THREE independent confirmations: NQ (decays across the split, the right shape), US100's nine unseen years (+9.2, p 0.0001), EURUSD 30m from a non-overlapping era (+0.0716 R, p 0.000, 1,501 trades); BTC consistent but not a pass at nine tests | M4's day filter (98 trades at −0.103 on FX) | P&L 57/43 between the barrier pair and the time exit; positive in all four FX sub-periods but significant only in two |
| E8 | **The SIDE and the TIMING of the first quarter-hour close beyond a 15-minute opening range, held to the cash close with NO target** | `STUDY_FTM_ANATOMY` (from `STUDY_FTM_ORB_BACKTEST`, `STUDY_FTM_ALPHA2`) | beats a random quarter-hour entry with identical management at p 0.004–0.030 in every configuration that keeps a stop or a target; the breakout side is worth +0.10 R over a coin flip; no target +0.191 vs +0.155 R; at the 10:00 decision the control earns +0.020 and the rule +0.143 | the direction model (+0.003 R), the prior-day override, the high-ORB regime, the admission tests, the 15:30 rule, the stop (removable at +0.163 R) — each inert; the alpha.2 policy changes (−$641) | +0.09 R excess; top 5% of trades 121% of net; "always long" beats it in 2025 (+0.256 vs +0.096); the last six months are flat for all 200 cells; NQ path with synthetic levels |
| E9 | **The session as a filter — trade 09:30–11:00 if you were going to trade 07:00–11:00, and never 07:00–09:00** | `STUDY_TREND_PULLBACK`, `STUDY_SCALP_TREND`, `STUDY_INTRADAY_SESSION` | 4× the per-trade result on 44% fewer trades; 07:00–09:00 is −0.18 to −0.43 R on all three indices, three independent confirmations; moving the open 06:00 → 09:30 raises OOS 35% | a transferable window (09:30–11:00 is the WORST of seven on V16); a reason to flatten (a fixed-time flatten costs half the edge without a window) | a session preference is strategy-specific: measure it per family |
| E10 | **SAM scalps on the INTRABAR estimator, normalised** | `STUDY_SAM_SCALP` | four scalps beat a matched control on the holdout and lift book Sharpe 3.73 → 4.57; the same signal looked null across 4,032 combinations until normalised (ratio, trailing z, the CROSS) | the bar-return version (p 0.354); anything TradingView can compute at 5m | needs intrabar data |
| E11 | **A SUSTAINED displacement of >= 3 ATR from a PRE-MARKET-ANCHORED average, taken in the first hour while the session VWAP is still within 2.5 ATR of price, continues to the cash close** (the APM phase-momentum rule, stripped) | `STUDY_APM_VWAP` §10 | against a coin-flip side on its own bars: NQ research +24.0 (p 0.050), NQ locked +62.8 (p 0.000), US100 research +10.8 (p 0.018), validation +34.5 (p 0.015) -- the constants are the author's, none was chosen on these blocks; inverting the side loses on every index block, always-long is negative, so it is the SIGN not drift; remove either half and the research pass is gone on both feeds (band off +13.3 / +3.6, no smoothing +9.3 / +4.9, both off +0.3 / +1.6) | the opening drive (>= 3 ATR from the 09:30 open is +5.5 / -1.0 on 4x the trades, p 0.19 / 0.41, and no rung of a 0.5-5.0 ladder passes); the published first-half-hour momentum (+0.6 / +0.4, null); the drive with the same VWAP band bolted on (+7.8 / +1.2); the entry window (the band is the clock, 0% of crosses after 11:00 are inside it); the opposite-cross exit; any of 17 causal features (§11) | US100 test p 0.279 with 2025 at -27 a trade; US30 null over nine years; gold research null; locked > research on NQ and gold (a regime); the fill is late by construction (a same-day same-side random bar beats it, with look-ahead, and the realisable earlier entry is worse); 70 research trades with P(mean<=0) 0.052; walk-forward re-selection loses to the constants |

**What is NOT in this table, deliberately:** the Donchian trigger, MACD, Aroon, RSI-on-breakout,
volume profile, Initial Balance features, calendar conditions, volume spikes, divergence,
MA-type, the trend-pullback family, the intraday scalp at any bar-range stop, the ORB's direction
model, the IBS session signal, the Double Donchian width filter, The Strat's combos and location
score, the plain opening drive and the published first-half-hour intraday momentum (both null
on NQ and US100 while E11 passes on the same days). Each failed its control or was found to be a restatement of the trigger. The ledger has
the numbers.

---

## 2. The five things every surviving mechanism has in common

1. **It is an exit, a location or an execution rule, not an entry.** E1, E2, E4, E5, E7, E8 are
   all about WHERE the trade is placed or HOW it leaves. Five trend-following briefs resolved into
   mean reversion; the entry mechanic was worth ten times the entry signal. The two exceptions,
   E8 and E11, are DIRECTION calls held to the cash close with no target -- and in both the fill
   itself is late and the money is in the sign and the hold.
2. **It has a GRADIENT.** E4's ladder is sign-consistent in both directions; E5 is monotone over
   five rungs; E6's gate count is a monotone chop score; E3 fails at 15 and passes at 25. A win
   rate that exists at one threshold is not a mechanism.
3. **It clears the SAME-GEOMETRY random control, not a population mean.** Random entries with the
   same side, stop, target, hold, session and lock price in the drift, the session and the exit
   machine. Everything above beat that null; everything excluded from the table did not.
4. **It decays out of sample, it does not appear there.** E7 decays across the NQ split; E8's
   IS→OOS; E2's drawdown triples. Passing on the holdout while failing research is the wrong
   shape and has been seen twice.
5. **It is small.** +0.05 to +0.30 R per trade, and in win-rate terms +1 to +5 points. Anything larger on this branch has been a leak, a
   fill artefact, a denominator, or a checkbox.

---

## 3. How to apply this to a brand-new strategy (the reverse-engineering procedure)

Run these in order; stop at the first one that fails and say so. Each is a script that exists.

1. **Reproduce the order model, not the rules.** Write the platform's fill logic (next-open fills,
   stop-before-target on a touched bar, partial exits re-issuing, one live order, session
   breaks) and diff it trade-for-trade against your engine. `research/ibs/ibs_parity.py`,
   `research/v15/v15_parity.py`, `research/turtle15/pine_parity.py`. Every port here was wrong
   at least once before this step.
   For a LIMIT entry add two checks the one-minute path does not make on its own: the target
   may not fire on the fill minute (its high was made before the dip that filled you, worth
   81% → 71% win and PF 1.9 → 0.9 in `STUDY_NEW_DESIGN`), and only ONE order may rest (a
   scan-forward engine lets the oldest of several fill first).
2. **Split net P&L by EXIT REASON first.** Stop / target / time / conditional. A rule earning at the
   time exit is a direction bet; one earning at the target is a tail harvest. `oner_anom`,
   `ftm_anatomy` stage A.
3. **Run the same-geometry random control BEFORE anything else.** Random entry bar (or session)
   with the identical side, stop, target, hold and lock, matched on trades TAKEN, drawn from the
   same regime if there is one. p > 0.05 here ends the study. `ibs_core.matched_control`,
   `ddc_core.control`, `strat_core.control`, `ftm_backtest.control`.
4. **Widen the stop to infinity and remove the target.** If the result barely moves, the barriers
   are decoration and the edge is a day or direction filter (`STUDY_M4_ANATOMY`). If the result
   collapses, the edge IS the geometry and the entry is replaceable.
5. **Drop one component at a time, and swap the direction for a coin flip.** Which removal costs
   the most? Which costs nothing? A component that costs nothing is not part of the strategy.
   `ftm_sim.KNOBS`, `research/dropone.py`.
6. **Read the parameter grid by the SHARE that is profitable and the MARGINAL per axis**, never the
   top row; require a neighbourhood; check rank stability from research to validation
   (Spearman) and whether the research top decile beats the AVERAGE cell out of sample.
   `ibs_run.stability`, `ftm_anatomy` stage B.
7. **Walk forward with the SEARCH INSIDE THE FOLD**, and compare the chosen cells against the
   author's fixed defaults. On this branch no optimiser has beaten fixed defaults out of sample.
8. **Cluster the grid by daily-P&L correlation.** How many strategies is it really? The top 25 has
   been one rule in 25 hats; a diverse grid that is 99% positive is drift, not discovery.
9. **Express every cost as a FRACTION OF THE STOP**, stress it 0×/1.5×/2×, and check the win rate
   against the driftless break-even for the geometry. A scalping stop needs 60–95% at 1:1.
10. **Bootstrap for the edge, permute for the path, and never read an endpoint off a permutation.**
    Day-block bootstrap when trades cluster inside sessions. `validate.monte_carlo`,
    `ftm_anatomy` stage F.
11. **Hold back an untouched final block and read it ONCE**, stating the multiplicity. US30 ISO
    2026 and US100's pre-2023 years are the two on this branch.
12. **If it survives, write down what it IS in one sentence without an indicator name**, and add it
    to §1 with its qualifications. If it does not, add the mechanism to the excluded list so the
    next brief does not re-run it.

The failure modes that have cost the most here, in order: reading a fill the platform cannot
make; scoring against a population mean instead of a matched control; selecting on both blocks;
a channel stop or a tight stop as the R denominator; a leak in a two-sided filter or an
`ent_bar` read; a checkbox in the Strategy Tester; and believing the top row of a grid.
