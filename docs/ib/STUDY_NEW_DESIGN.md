# STUDY_NEW_DESIGN — two intraday strategies built from the edge library, and what they measure

**Brief.** Design a brand-new intraday strategy from zero with a mathematical basis, using every
edge measured here, aiming at profit factor ≥ 1.50 and win rate ≥ 66%, with feature engineering
if needed; then "try trend following". Two designs were built, each from library entries only,
each selected on the research block alone and read once on the locked block against the
branch's controls. **Neither reaches the ask, and the arithmetic in §1 says why nothing honest
on this data would.** The trend-following design is the one with evidence and ships as a Pine
strategy. Two engine artifacts were found on the way, one of them new, and both are recorded
because they would have delivered the ask on paper.

Code: `research/mrl/mrl_design.py` (mean reversion), `research/mrl/tf_design.py` (trend),
`mrl_walk.py` (the strict one-minute limit walk), `mrl_bar.py` (the 15-minute shape check).
Outputs in `results/mrl/`. NQ one-minute bars 2022-12-26 to 2025-12-11 for the limit design
(the only feed with a minute path), 15-minute NQ / US100 / US30 for the trend design, and the
newly registered `XAUUSD15_MT` (UTC clock, derived) as a shape feed.

---

## 1. The arithmetic that sets the geometry

With a stop of 1 unit, a target of q units and an all-in cost c in stop units, the win rate that
delivers PF 1.5 is w* = 1.5(1 + c) / (1.5(1 + c) + q − c). The driftless base of the barrier
pair is 1 / (1 + q).

| q | driftless base | w* at c = 0 | c = 0.03 | c = 0.06 |
| ---: | ---: | ---: | ---: | ---: |
| 0.5 | 66.7% | 75.0% | 76.7% | 78.3% |
| 0.75 | 57.1% | 66.7% | 68.2% | 69.7% |
| 0.8 | 55.6% | 65.2% | 66.7% | 68.2% |
| 1.0 | 50.0% | 60.0% | 61.4% | 62.8% |

**66% AND PF 1.5 is open only at q ≥ 0.8, and there it needs +10 to +13 points of win rate over
a coin flip after costs.** The largest controlled lifts this branch has ever measured are +0.10 R
(the FTM breakout side over a coin flip) and +0.31 R (the IB retracement depth), which in
win-rate terms at these geometries are single digits. The design target was therefore stated as
"buy +12 points", and the only mechanism in the library that had ever claimed lifts of that
order was E1, mean reversion at the execution layer. That is where the first design went.

## 2. Design A — MRL, mean reversion at a level with a limit fill

**Components.** E1: a resting limit k × ATR(5) below each 5-minute close, live for `expiry`
bars, one order at a time, filled only through the level, walked on the true one-minute path.
E2: an ATR(14) stop; the target as a fraction q of it. E9: entries 09:30–15:00, flat 15:55.
E4/E5 as causal features on the 5-minute bars: retracement depth into the session range,
distance from session VWAP, prior-session high/low distance, the 30-minute return, opening-range
position, session range in ATR, ATR regime, hour, bar shape. Real MNQ costs (1.44× the
module's broker-only constant), through-fill 1 tick.

**What the first pass found, and why it was wrong.** The every-bar base grid — 256 geometries,
no rule at all — showed **81.3% win, PF 1.90, +$8.55 a trade** at limit 1.0 × ATR5, stop 1.0,
q 0.5, three-bar life. That is the ask, exceeded, with no signal. It was two engine artifacts:

1. **The fill-minute target.** `limit_entry._walk_limit` checks the target on the minute the
   limit fills. A limit below the close is reached on the way DOWN, so that minute's high was
   made before the fill and cannot pay a target after it. This is `STUDY_V10`'s first artifact
   at one-minute scale. Letting the target fire only from the next minute takes the cell to
   **70.7% / PF 0.92 / −$1.17**; 42% of its exits had been on the fill minute.
2. **Several live orders.** The engine scans forward from each signal in turn, so with a
   three-bar life and a signal on every bar, three orders rest at once and the oldest fills
   first — `eem.run`'s defect from `STUDY_V15_BOOK`. It surfaced as every-bar entries earning
   68% while random subsets of the same bars earned 65%. With one live order held untouched,
   the every-bar base is **PF 0.81–1.02 on all 256 cells**, the win rate at q 0.5 is 65.4%
   against a driftless 66.7%, and the limit mechanic's lift is **0 to +3 points**.

`mrl_walk.py` carries both corrections. On the three 15-minute feeds the same every-bar entry is
PF 0.81–0.96 (bar level, strict). **E1 at real costs, one order, and a strict fill is a null on
this data, and the library entry is corrected accordingly.**

**Feature ladders (research, corrected engine).** Quintile ladders of every feature, each
scored against a random filter of the same selectivity (300 draws) with the control's own
median printed, monotone ladders required. At q 0.5 / stop 3.0: 2 of 13 features pass (opening-
range position top quintile 67.3% / PF 1.03; prior-day-low distance); at q 0.75: the same two.
Lifts are +1 to +2 points of win rate and +0.1 PF. Pairs on research:

| geometry | filters | n | win | PF | $/trade | random filter win / PF |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| q 0.75, stop 3 | session range ATR bottom quintile & 30-min return top 40% | 426 | 61.7% | 1.18 | +9.52 | 55.7% / 0.94 |
| q 0.75, stop 3 | retracement < 40% from high & session range bottom | 418 | 61.5% | 1.18 | +9.45 | 55.4% / 0.93 |
| q 0.5, stop 3 | session range bottom & 30-min return top 40% | 480 | 69.2% | 1.11 | +4.59 | 64.8% / 0.92 |

**The locked read (once), primary design = q 0.75, stop 3 × ATR14, limit 0.75 × ATR5, three-bar
life, quiet session + positive 30-minute return:**

| block | every bar (control) | the design | random filter of the same selectivity |
| --- | --- | --- | --- |
| research | n 1,703, 57.0%, PF 0.95, −$2.71 | n 426, **61.7%, PF 1.18, +$9.52**, Sharpe 1.00 | 55.7% p 0.000 / PF 0.94 p 0.000 |
| **locked** | n 886, 57.8%, PF 1.01, +$0.57 | n 194, **60.8%, PF 1.17, +$13.43**, Sharpe 0.80 | 56.8% **p 0.020** / PF 1.00 **p 0.077** |

Neighbours on locked: limit 0.5 fails (PF 0.94), limit 1.0 holds (1.08), stop 2.0 fails (1.05),
q 0.5 gives 69.2% at PF 1.10, q 1.0 gives 53% at 1.09. Exit split on locked: stops −$14,696,
targets +$17,519. Costs 1.5× / 2× → PF 1.14 / 1.11; through-fill 4 ticks → 1.16; order life 1
bar → 1.31 on 174 trades; +20% on the stop → 1.23, −20% on the limit → 1.00. Windows: 09:30–
11:00 carries it (PF 1.22), 11:00–13:00 is 19 trades at PF 3.3 and 13:00–15:00 is one trade.
Bootstrap P(mean R ≤ 0) **0.213**, session-block 0.215. 2024 (17 trades) negative, 2025 positive.
**Shape on the 15-minute feeds: US100 research PF 0.88, validation 0.92, test 1.35; US30 0.98 /
0.90 / 1.02; gold 1.09 / 1.01.** It does not transfer, and on NQ locked it is a 60.8% / 1.17
strategy that clears a random filter on win rate and not on profit factor.

## 3. Design B — TFI, an intraday trend follower

**Components.** E2: market order at the next open, 2.5 × ATR(14) stop, 20-bar channel exit, one
unit, no target. E3: ADX(14) ≥ 20 floor. E4: the breakout close must also exceed the prior
completed RTH session's high, accumulated on the feed's own bars. E9: entries 09:30–14:00, flat
at the 15:45 close. Trigger: close crossing above the 55-bar Donchian high on 15-minute bars.
Grid on research: channel {20, 55} × ADX {0, 20, 25} × gate {off, on} × stop {1.5, 2.5} × exit
{10, 20} × target {none, 0.75, 1.0}, both sides.

**Research marginals, long side (144 cells, 93% PF > 1, none ≥ 1.5, none ≥ 66%):** no target
+0.108 R against +0.033 with a 0.75 × target (fourth time here); the gate +0.083 against +0.052;
ADX 20 +0.075 against 0 +0.060; stop 2.5 over 1.5; channel length indifferent. Shorts: median R
−0.008. The marginal-consensus cell is Donchian 55, ADX ≥ 20, gate on, stop 2.5, exit 20, no
target.

| block | n | win | PF | R | Sharpe (all days) | control R | p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ research | 145 | 50.3% | 1.40 | +0.143 | 1.09 | +0.020 | **0.013** |
| **NQ locked** | 81 | 55.6% | 1.24 | +0.047 | 0.58 | +0.016 | 0.327 |
| US100 research | 362 | 53.9% | 1.34 | +0.136 | 0.83 | −0.000 | **0.000** |
| US100 validation | 125 | 57.6% | **1.56** | +0.188 | 1.28 | +0.049 | **0.000** |
| US100 test | 126 | 51.6% | 1.20 | +0.077 | 0.58 | −0.011 | 0.080 |
| US30 research | 335 | 46.3% | 0.97 | +0.006 | −0.07 | −0.036 | 0.093 |
| US30 validation | 134 | 49.3% | 1.01 | +0.013 | 0.04 | −0.006 | 0.387 |
| US30 test | 108 | 42.6% | 0.92 | −0.034 | −0.23 | +0.009 | 0.707 |

**What carries it, on NQ locked:** remove the prior-session-high gate and PF goes 1.24 → **1.00**;
remove the ADX floor → 1.10; ADX ≥ 25 → 1.45 on 63 trades; the short mirror → 0.85; a 1.0 × target
→ 1.18 at 55.6% and a 0.75 × target → 1.32 at 60.2% (the win-rate variants, both worse per trade);
costs 2× → 1.19. 61–63% of exits are the 15:45 flatten, which is the intraday constraint doing
what `STUDY_INTRADAY_SESSION` said it does. NQ locked bootstrap P(mean R ≤ 0) 0.339; 2025 alone
R −0.015 on 72 trades. Top 5% of locked trades are 190% of net.

## 4. Verdict

| | MRL (mean reversion, limit) | TFI (trend, breakout) |
| --- | --- | --- |
| research NQ | 61.7% / PF 1.18, beats random filter | 50.3% / PF 1.40, beats random bar p 0.013 |
| locked NQ | 60.8% / PF 1.17, p 0.020 win, 0.077 PF | 55.6% / PF 1.24, p 0.327 |
| other feeds | null (US100 0.88–1.35, US30 0.90–1.02, gold ~1.0) | US100 1.34 / 1.56 / 1.20 with two control passes; US30 null |
| the ask | no | no |

**The ask is not met, and the reason is arithmetic, not effort.** 66% at PF 1.5 needs +12 points
of win rate over a coin flip after costs; the honest lifts available on this data are +1 to +5.
The two designs that came closest did so by the two routes the library predicts: a quiet-session
limit entry buys about four points of win rate, and a level-gated breakout with no target buys
about +0.10 R with a 50% win rate. Anything that showed the ask being met — and one thing did,
at 81% and PF 1.9 — was the engine.

What would change it: a second one-minute feed for the limit design, since the 15-minute
feeds cannot settle a limit question; bid/ask data, since every cost here is an assumption; and
for the trend design, dropping the intraday flatten, which the branch has measured at roughly
half the edge on every trend family it has tried.

## 5. What ships

`pine/tfi/TFI_NQ_strategy.pine` — Design B as a TradingView strategy: 15-minute chart, extended
hours on, the prior-session high accumulated from the chart's own RTH bars, entries 09:30–14:00
New York, flat at the 16:00 open. Its header states the numbers above. The MRL design is not
shipped as a script: a limit strategy whose evidence lives on a one-minute path should not be
handed to a bar-level tester.

---

## 6. Addendum — "improve it for XAUUSD"

`research/mrl/tf_gold.py`, on `XAUUSD15_MT` (UTC clock), research 2022-06 to 2024-12, locked
2025-01 to 2026-08. Gold's cost floor is ~3× the indices' and its breakout was negative gross at
scalping stops (`STUDY_XAUUSD_SCALP`), so the axes fixed for NQ became axes: entry window (four),
flatten (12:00 / 16:00), the session the prior-day level is taken from (three), side, plus the two
floors that flipped gold before (`STUDY_TURTLE_15M`): EMA(100) distance ≥ 2 ATR and ATR expansion
≥ 1.1. 24,192 cells.

**Research grid.** Longs: 56% of cells PF > 1, median R −0.008; shorts 34%, median −0.034. One
axis moves the marginal: the entry window. 08:30–11:30 New York (gold's own anchor hour) gives
R +0.059 / PF 1.18 against −0.090 for 03:00–12:00 and −0.022 for the NQ window 09:30–14:00. Every
other axis is within ±0.03 R. Inside that window the marginal consensus is: prior-day level over
the whole day, flat 16:00, channel 55, ADX ≥ 25, gate on, EMA-distance floor 2.0, no ATR floor,
stop 1.5, exit 10, target 1.0 × stop.

**The locked read, once, three cells:**

| cell | research | locked | locked control p |
| --- | --- | --- | ---: |
| NQ defaults on gold, unchanged | n 152, 46.1%, **PF 0.89**, R −0.068 (p 0.68) | n 88, 53.4%, **PF 1.20**, R +0.055 | 0.167 |
| gold consensus (marginal per axis in the window) | n 103, 63.1%, **PF 1.50**, R +0.222 (p 0.000) | n 64, 50.0%, **PF 0.91**, R −0.033 | 0.520 |
| top research cell (max of 24,192) | n 94, 61.7%, **PF 1.75**, R +0.133 (p 0.000) | n 61, 50.8%, **PF 0.75**, R −0.086 | 0.947 |

All eight locked neighbours of the consensus are negative (PF 0.68–0.91); "no target" is the
worst of them (0.68), the opposite of every index result. Cost 1.5× takes the consensus to 0.85.
2025 alone: the consensus R +0.004, the top cell −0.136.

**Verdict.** Re-selecting on gold produces exactly the ask on research — 63% and PF 1.50 — and
none of it survives 2025–26. The only cell that is positive on the locked block is the one that
was NOT selected on gold, and it FAILED gold's research block, which is the wrong shape
(`CLAUDE.md`: passing on the holdout while failing research is a defect, not a result) and is
gold's 2025 rally wearing a channel. The 08:30–11:30 window is the one gold-specific finding and
it agrees with the registry's derived anchor, but it did not carry. **No gold settings are
recommended**; the script carries the extra inputs (level session, the two floors, the target) so
the variants can be run, with the NQ defaults unchanged. What would change it: the twenty-year
`XAU_ISO_15m` feed, absent from disk this session, which has the 2011–2020 gold regimes this
four-year file does not.

---

## 7. Addendum — "more balanced, PF 1.50 on locked with a control pass", and a US30 version

**The rule.** Nothing may be selected on the locked block, so "PF 1.50 on locked" cannot be a
target; what can be done is to pull the levers the library names, choose by agreement on TWO
feeds' research blocks, and read the reserved blocks once. `research/mrl/tf_balance.py`.

**Second-pass grid** (window × flatten × ADX × stop, channel 55 / exit 20 / gate on / no target
held; scored by the minimum of NQ and US100 research R):

| axis | two-feed min R | NQ R / PF | US100 R / PF | US30 R |
| --- | ---: | --- | --- | ---: |
| window 09:30–11:00 / 12:00 / 14:00 | +0.059 / +0.071 / **+0.084** | +0.059 / +0.071 / +0.087 | +0.220 / +0.209 / +0.214 | +0.07 / +0.07 / +0.05 |
| flat 16:00 / hold overnight | **+0.089** / +0.053 | +0.092 (1.29) / +0.053 (1.22) | +0.148 (1.37) / **+0.280 (1.72)** | +0.006 / +0.119 |
| ADX 20 / 25 | **+0.100** / +0.043 | +0.103 / +0.043 | +0.213 / +0.216 | +0.066 / +0.059 |
| stop 2.0 / 2.5 / 3.0 | +0.080 / **+0.091** / +0.044 | +0.082 / +0.092 / +0.044 | +0.211 / +0.222 / +0.209 | |

**The two-feed consensus is the shipped cell** — 09:30–14:00, flat 16:00, ADX 20, stop 2.5 —
so the reserved reads are unchanged: NQ locked PF 1.24 p 0.32, US100 validation 1.56 p 0.000,
US100 test 1.20 p 0.09, US30 null. The one lever that moves anything is **holding overnight**,
which takes US100 research to PF 1.72 (+0.28 R) but NQ to 1.22 (+0.05), and a change the two feeds
disagree on is not made. **The two-market book** of NQ and US100 on their overlapping out-of-sample
dates (2024-11 to 2025-09): daily-R PF 1.18, Sharpe 0.58, **daily correlation 0.90** — the two
feeds are the same index, and there is no diversification to be had between them.

**A US30 version.** `research/mrl/tf_us30.py`. This design is a null on US30 on every cell of the
first pass (0.97 / 1.01 / 0.92). The one US30 configuration on this branch that survived a genuine
forward block — `STUDY_MEGA_144K`'s Donchian 30/20, ADX ≥ 15, 2.5 × ATR stop, 2R target, all hours,
no flatten — re-measured here at one unit with the retail CFD cost model:

| block | n | win | PF | R | control p |
| --- | ---: | ---: | ---: | ---: | ---: |
| US30 research | 1,491 | 38.0% | 1.05 | +0.016 | 0.87 |
| US30 validation | 583 | 35.2% | 0.86 | −0.085 | 0.90 |
| US30 test | 486 | 38.1% | 0.98 | −0.004 | 0.57 |
| US30 ISO 2024–25 | 426 | 39.2% | 1.10 | +0.056 | 0.16 |
| **US30 ISO 2026** | 203 | 40.4% | **1.25** | +0.112 | 0.095 |
| NQ locked | 312 | 39.4% | 1.10 | +0.060 | 0.25 |
| US100 test | 570 | 39.1% | 1.15 | +0.053 | 0.62 |

It is positive on the 2026 tail only, and there **removing the ADX filter entirely does better
(PF 1.29)**, as does every target from 1.5R to 3R — the whole neighbourhood is up in 2026 and
down before it, which is a regime, not a rule. Its intraday form (09:30–14:00, flat 16:00) is
1.04 / 1.02 / 1.00 on US30's blocks and 0.80 on 2026. The earlier study's US30 2026 figure (PF
1.19, p 0.0013) was three units in a different engine with a different cost model, and it was
already a one-time read; this is a second read, and it does not agree. **No US30 settings are
recommended.** The script carries a flatten switch and a 24-hour entry window so that form can be
run; its defaults remain the NQ cell.
