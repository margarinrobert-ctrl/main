# NQ Scalping System — evaluation

`research/scalp89/`, `results/scalp89/`, `pine/scalp89/NQ_SCALPING_SYSTEM_v2_strategy.pine`.
Research log with the full trial count: `research/scalp89/research_log.md`.

## Verdict

**No edge, at any confidence, on any block, in any variant — and the submitted configuration
loses money on any entry at all.** As configured (5 MNQ, trail fixed at 15 / 8 points) it scores
**PF 0.393 and −$92,951 on the research block, PF 0.445 and −$67,843 on the locked block**, and is
negative on eight of eight blocks across NQ 1m / 5m / 15m and nine years of US100. The single
destructive component is the trailing stop, which inverts the reward:risk by construction;
removing it recovers about $65,000 of the $93,000 research loss and leaves **PF 0.863 / 0.972** —
still negative, still failing a random entry (p 0.730), still robustly below zero under every
perturbation (P(total > 0) = 0.000 across execution noise and price jitter on research).

The entry has no reproducible information. Its one positive reading — the short side at a 15–30
minute horizon on NQ 5m research, p 0.000–0.007 — is absent on NQ 5m locked (p 0.48–0.64),
negative on NQ 15m on both blocks, and absent on US100. What would change this verdict: a
different entry. Nothing in a 160-cell geometry sweep, a 729-cell walk-forward, or the exit
machine can rescue a signal that carries nothing.

## Setup

| | |
| --- | --- |
| Instrument | NQ 1-minute (true volume), 2022-12-26 → 2025-12-11, 923 sessions; run as 1m / 5m / 15m. US100 15m 2016-11 → 2025-10 as a second feed. |
| Working base | NQ 5m — the bar size is unstated in the submission; 5m matches "15-point pullback" and a 1-minute warm-up |
| Holdout | first 65% of sessions research / last 35% locked, cut **2024-11-27** — the branch's standing split |
| Costs | MNQ: $2/pt, 0.25 tick, 0.86 pts a side (0.25 spread + 0.25 slip + 0.36 fees = $3.44 a round turn). US100 in its own points. |
| Configuration | the **screenshot's** values, which override the code defaults: 5 contracts, EMA89 / EMA8 / EMA21, pullback ≥ 15 pts over 10 bars, StochRSI 14/14/3/3 reset ≤ 20 within 8 bars then %K×%D, 06:00–11:30 Chicago (07:00–12:30 NY) skipping the first minute, ATR(14) stop 1.5× / target 2.5×, **trail ON, "Always use Fixed Points" ON at 15 / 8 points**, all filters and early exits off |
| Trials | ~200 research-block configurations, ~32 locked-block reads (see the log) |

### The transcription is of the ORDER MODEL, not just the rules

Indicator parity against independent references is exact (Wilder RSI max |diff| 3e-8; `ta.atr` is
Wilder's RMA, `ta.stoch(rsi,rsi,rsi,n)` the plain StochRSI, `ta.highest/lowest` inclusive,
`ta.crossover` = `a[1] <= b[1] and a > b`). Three things in the script are not rules and each was
modelled both ways:

- **The fill bar is naked.** `strategy.exit` is called after the block that sets the stop, on the
  fill bar's close, so nothing protects the position during the fill bar. Modelled as written and
  with the bracket live on the fill bar.
- **Pine's intrabar path.** When stop and target fall in one bar the emulator assumes open →
  nearer extreme → farther extreme. Modelled as the emulator does it and as stop-first.
- **No session flatten.** Entries are windowed; positions run on stop / target / trail alone and
  can carry overnight. Modelled as written; a flatten was tested as a variant.

## The exit machine — where the loss comes from

NQ 5m research, everything else as configured:

| Exit variant | n | %/trade | PF | Win | Exit mix | $ at 5 MNQ |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| **as configured: trail fixed 15 / 8** | 1,309 | −0.0392 | **0.393** | 49.9% | trail 62% · stop 37% · **target 1%** | **−92,951** |
| trail OFF: plain 1.5 / 2.5 ATR bracket | 1,178 | −0.0145 | **0.863** | 38.8% | stop 61% · target 39% | −27,612 |
| trail in ATR (1.0 / 0.5, the code default) | 1,344 | −0.0352 | 0.397 | 48.9% | trail 69% | −86,006 |
| trail fixed 30 / 15 | 1,233 | −0.0433 | 0.483 | 45.1% | stop 50% · trail 41% | −96,124 |
| trail fixed 60 / 30 | 1,190 | −0.0247 | 0.750 | 40.3% | stop 59% · target 28% | −51,245 |

**Median ATR(14) on 5m NQ is 10.4 points.** So the stop is ~16 points, the target ~26 — and a
trail that arms at 15 and trails by 8 fires on 62% of trades at about +7 before the target has a
chance. A 50% win rate paying +7 against −16 is PF 0.39. This is not a market finding; it is
arithmetic, and the code's own header warned about it before the "Always use Fixed Points" toggle
overrode the ATR scaling. No trail setting measured beats no trail.

**The naked fill bar hides a third of the loss.** Protecting it — the correct model of a live
bracket — takes research PF 0.393 → **0.151** and −$92,951 → **−$118,465**, win rate 49.9% →
29.9%. A 16-point stop on a 10-point-ATR bar is hit inside the fill bar often. Pine's path
assumption versus stop-first is worth 0.004 PF — negligible.

## The entry — no reproducible information

**Ablation, trail off, research:**

| Drop | n | PF | Δ PF |
| --- | ---: | ---: | ---: |
| (all conditions) | 1,178 | 0.863 | — |
| EMA89 trend gate | 2,810 | 0.785 | **−0.078** — the only condition that helps |
| 15-pt pullback depth | 1,263 | 0.857 | −0.006 |
| EMA8/21 touch | 1,239 | 0.893 | +0.030 — better without it |
| StochRSI reset | 1,616 | 0.869 | +0.006 |
| session window | 3,556 | 0.880 | +0.017 |
| **longs only** | 625 | **0.942** | |
| **shorts only** | 580 | **0.789** | |

Shorts do most of the damage, in a market that rose 89%.

**Fixed-horizon forward return at signal bars, no exits, ATR units, excess over a random
in-session bar of the same block:**

| Feed | Block | h ≈ 15 min | h ≈ 30 min | h ≈ 60 min |
| --- | --- | ---: | ---: | ---: |
| NQ 5m | research | short **+0.128 (p 0.007)** | short **+0.205 (p 0.000)** | short +0.203 (p 0.067) |
| NQ 5m | **locked** | short −0.026 (p 0.64) | short −0.000 (p 0.48) | short −0.031 (p 0.55) |
| NQ 15m | research | −0.047 | −0.133 | −0.054 |
| NQ 15m | locked | −0.117 | −0.053 | −0.030 |
| US100 15m | research | +0.064 (p 0.12) | +0.023 | −0.046 |
| US100 15m | locked | −0.058 | −0.039 | +0.103 (p 0.24) |

One block noticed a short-side effect and no other block reproduces it. The long side is null
everywhere; NQ 5m locked h=6 reads +0.24 at p 0.020 with research at p 0.22 — the wrong shape.

**Matched control (same long/short mix, random in-session bar, identical exit machine):**

| Variant | Observed | Control median | Control 5–95% | p |
| --- | ---: | ---: | --- | ---: |
| trail OFF | −0.0145 | −0.0121 | [−0.0203, −0.0043] | **0.730** |
| as configured | −0.0392 | −0.0413 | **[−0.0447, −0.0376]** | 0.177 |

The configured exit machine's control band is **entirely negative**: it loses on any entry.

## Geometry — 160 cells, research, trail off, by marginal average

| Side | Cells net-profitable | Cells gross-profitable | Best marginal cell vs random entry |
| --- | ---: | ---: | --- |
| **short** | **0 / 80** | 10 / 80 | stop 1.0 / target 1.0 / hold 12: −0.0144 net, −0.0017 gross, control p 0.033 |
| long | 6 / 80 | 51 / 80 | every net-positive cell is `no target, no hold` — 60–151 trades at 1–5% win rates, a few multi-month longs in a rising market |

The short signal's 15–30 minute information, where it existed, is worth ~0.2 ATR ≈ 2 points
against a 1.72-point round turn: informational, not monetizable, and gone on every other block.

## Session

07:00–12:30 NY as configured PF 0.863; 09:30–12:30 **0.854**; 09:30–16:00 0.879; all hours
0.880; adding a 15:55 flatten 0.864. The window is inert to ±0.02 and the branch's 09:30 finding
does not transfer here — third time a session preference has failed to transfer.

## Cross-feed and cross-timeframe

| Feed / tf | As configured (res / locked PF) | Trail off (res / locked PF) |
| --- | --- | --- |
| NQ 1m | 0.368 / 0.373 | 0.781 / 0.877 |
| NQ 5m | 0.393 / 0.445 | 0.863 / 0.972 |
| NQ 15m | 0.606 / 0.669 | **1.006** / 0.971 |
| US100 15m | 0.530 / 0.633 | 0.919 / 0.963 |

Eight of eight negative as configured; seven of eight with the trail off, the eighth at zero. The
damage scales with frequency because a fixed round turn is a larger share of a smaller stop.

## Walk-forward — 729 declared cells, selection re-run inside every fold, trail off

trend EMA {55, 89, 144} × fast EMA {5, 8, 13} × min pullback {0, 15, 30} × reset {5, 8, 12} ×
stop {1.0, 1.5, 2.0} × target {1.5, 2.5, 4.0}; 9 quarterly test folds.

| Scheme | RE-CHOSEN | FIXED (screenshot) | **RANDOM cell** |
| --- | ---: | ---: | ---: |
| rolling 4Q | −5.76 (3/9) | −7.76 (4/9) | **−4.85** (3/9) |
| expanding | −16.42 (3/9) | −7.76 (4/9) | **−5.19** (3/9) |
| post-cut 2025Q1+ | −3.48 / −5.74 | −0.33 | **+1.08 / +0.98** |

**A random cell from the grid beats both the re-chosen and the fixed constants in both schemes.**
The in-sample "best" cell is itself negative in most training windows (expanding IS totals −1.6 to
−4.3 through 2025Q1), so the optimiser is choosing the least-bad member of a losing family. It
picks target 4.0 — the widest offered — in 8 of 9 folds, and nothing else settles. Eighth
re-optimiser on this branch to lose; first to lose to a random cell.

## Monte Carlo — trail off, NQ 5m

| | Research | Locked |
| --- | --- | --- |
| Execution: slip U(0,2×), cost U(0.5×,2×), 1,000 draws | total% p5–p95 [−28.4, −11.1], realised −17.1, **P(>0) 0.000** | [−6.9, +0.4], realised −2.2, P(>0) 0.078 |
| Price jitter 0.5 / 1 / 2 ticks, **indicators recomputed**, 150 draws each | P(>0) **0.000 / 0.000 / 0.000** | 0.000 / 0.007 / 0.040 |
| Permutation (path) | realised DD 22.9%, MC p99 25.4%, realised at the **93rd** percentile | realised 7.0%, p99 15.8%, 11th percentile |
| Bootstrap (edge) | mean −0.0145, CI [−0.0273, **−0.0014**], P(≤0) **0.984** | −0.0032, CI [−0.0255, +0.0203], P(≤0) 0.610 |

On research the bootstrap CI excludes zero on the *negative* side. On locked it cannot separate
from zero either way. The perturbations say the loss is not an artefact of exact prices or fills.

## What was corrected in the shipped script, and what it is worth

`pine/scalp89/NQ_SCALPING_SYSTEM_v2_strategy.pine` keeps every input and every default of the
submission except three, and adds nothing the evidence did not ask for:

1. **Trail default OFF** and "Always use Fixed Points" default OFF, both with the measured cost in
   the tooltip. Worth PF 0.39 → 0.86 research.
2. **Fill bar protected**: a fill-relative bracket (`loss=` / `profit=` in ticks off the signal
   bar's ATR, frozen in a `var`) placed *with* the entry, so the stop is live from the first tick.
   The submission's absolute `stop=` / `limit=` set one bar later left the fill bar naked — and
   that defect was flattering the backtest by ~$25,000.
3. **`barstate.isconfirmed` guard** on the entry and every `var` write, so the Strategy Tester's
   execution checkboxes cannot change the report (STUDY_TICK_RECALC: 5.1× the signals without it).

**Those corrections make the mechanics right. They do not produce an edge.** The header of the
script says so in its own numbers, and the HUD repeats it on the chart. If the entry is ever
replaced with one that carries information, this is the order model to put it in.

## Weaknesses of this evaluation

- Bar size was not specified; 5m was chosen because 15 points and a 1-minute warm-up only make
  sense below 15m. The 1m and 15m runs bracket it and agree.
- The US100 feed's volume is tick volume — irrelevant here because the volume filter is off.
- The short-side fixed-horizon reading on NQ 5m research is the one number in the study that
  could be read as promising; it was tested on four other blocks before being called noise, and
  those reads were pre-declared (same horizons, same statistic).

---

## Addendum: why TradingView shows +$60,868 / PF 3.08 / 84% wins on the same script

`research/scalp89/run_tv.py`, `results/scalp89/tv_reconcile.txt`. The screenshot: Last 365 days,
Deep Backtesting, $5M capital, **"Script execution ①"** — one intrabar execution option ticked —
287 trades, 84.0% profitable, PF 3.081, max drawdown 0.05%.

Three candidate explanations; two can be measured here, one cannot.

**1. Bar magnifier (finer exit resolution) — measured, and it is not the reason.** Walking the
same 5m signals' stop, target and trail on the *true 1-minute path* instead of the 5m bar's OHLC
moves research PF **0.393 → 0.428** and −$92,951 → −$75,084 (win 49.9% → 57.1%). A real but small
improvement; nothing near 3.08.

**2. The window — partly unmeasurable.** "Last 365 days" is 2025-09 → 2026-09 and this data
ends 2025-12-11, so nine of the twelve months on the screen are unseen here. The three months of
overlap read **PF 0.347, −$20,622** on 5m and 0.652 / −$5,886 on 15m in a bar-close model. 287
trades a year is the 15m cadence (~240/yr here), not 5m (~650).

**3. The ticked execution option on an unguarded script — the explanation, and only the user can
confirm it.** `strategy.entry` fires on `flat and longCond` with no `barstate.isconfirmed`; with
"On every tick" / "After order is filled" enabled, the entry fires on the first intrabar tick that
satisfies the rule — `low <= fastEma` at the exact touch, a `%K/%D` crossover that flickers true
mid-bar — and buys the dip at its bottom tick, after which a 15/8 trail locks about +7 on the
bounce. That is what an 84% win rate on this geometry requires: the arithmetic in section 3 of the
reconcile output shows the same average win (+9.3) and average loss (−23.4) give PF 0.40 at the
bar-close win rate of 50% and PF 2.08 at 84% — the *entries* must be at prices the bar close does
not offer. `STUDY_TICK_RECALC` measured exactly this on the Turtle: 5.1× the signals, 80% on bars
that never satisfied the rule at the close, −913 → +62,278. **If a checkbox changes the report,
the report is about the checkbox.** The decisive test is to untick it and re-run; v2 is guarded
so the boxes cannot change its result.

Two cosmetic items: $5M capital makes a $2,500 drawdown read as 0.05%, and the Deep Backtesting
banner notes the trades are not drawn on the chart.

### Correction to the addendum above

The "buy the touch" mechanism I named was **tested and does not reproduce the screenshot**
(`run_touch.py`, `results/scalp89/touch.txt`). Filling at the intrabar EMA8 touch on bars that
confirm at the close gives research **PF 0.419 / 55.3% wins** against the bar-close model's 0.428 /
57.1% — the touch sits a median +0.10 points better than the next open on a 5-minute bar, which is
nothing. The implementable version, a resting limit at the EMA8 that fills on every eligible touch,
is **PF 0.193** (0.461 with the trail off) on 2.6× the trades — the adverse-selection result
`STUDY_V50_SELECTION` predicts for a limit that fills the touches that never confirm.

So the screenshot's 84% / PF 3.08 is not "buying the touch". What remains is the platform
recalculating the script on forming-bar or post-fill state — entries on bars that never confirm at
the close, or same-bar re-entries after a fill — and which of the three execution options is
ticked decides which. That has not been emulated here. The decisive test is unchanged and costs
two minutes: untick the option and re-run. What is settled: **no bar-close or limit-order
implementation of this entry reaches PF 2 on any block, any geometry, or any timeframe measured.**
