# TEAM_TF_TRANSLATION -- converting the 09:00-range TV configuration from 30s to 1-15m

Workstream: why `na_live.TV` (range 09:00-09:05, break from 09:27, last entry 10:00, flat 11:00,
both sides, loose fresh 13x48 EMA cross within 7 minutes, 100/100 POINT barriers, breakeven
+43 -> +3, opposite-cross exit) is PF 1.60 at 30 seconds and loses at 1-5 minutes, what the
correct per-timeframe conversion of every parameter is, and whether any honest conversion reaches
PF 1.5. Code and CSVs: `research/nineam/tfx/` (`tfx_core.py`, `run_t1..t5.py`). Fill model
`fix=1` throughout; round turn 2.29 points; bootstraps are DAY-block (`_day = eday`).

**THE SAMPLE CAVEAT THAT GOVERNS EVERY NUMBER BELOW.** Every timeframe is a resample of ONE file,
`US30_30s`, and the 09:00 range exists on only **92 sessions (2026-04-30..2026-09-16)**. 30s, 1m,
2m, 3m, 4m, 5m and 15m are seven views of one 92-session sample, not seven tests; nothing may be
pooled or counted across them. Research half = first 46 tradeable sessions (to 2026-07-14),
second half = last 46, split once on the 30s calendar and applied to every timeframe.

## 1. Parameter census (`t1_census.csv`)

| parameter | unit in the script | 30s | 1m | 2m | 3m | 4m | 5m | 15m |
|---|---|---|---|---|---|---|---|---|
| EMA 13/48 | **BARS** | 6.5/24 min | 13/48 | 26/96 | 39/144 | 52/192 | 65/240 | 195/720 |
| fresh-cross reach 7 min | minutes -> `max(1,round(7/tf))` bars | 14 bars* | 7 | 4 (=8 min) | 2 (6) | 2 (8) | 1 (5) | 1 (15) |
| ATR 14 | bars | **inert** -- signal set and every trade identical at ATR 7/14/45 on all 7 TFs | | | | | | |
| range [540,545) | bar STAMPS | 5 min | 5 | 6 | 6 | 8 | 5 | **15** |
| entry window 567-600 | minutes | 66 bars | 33 | 16 | 11 | 8 | 6 | **2** |
| flatten 660 | minutes | exact on every TF (fires on 0-6.7% of trades) | | | | | | |
| 100/100 points | price | intrabar ambiguity **0.000 on every TF**; stop filled through the market 1.9% / 4.2 / 13.6 / 9.1 / 6.7 / 6.3 / 12.5% | | | | | | |

Coverage of 09:00-11:00 on the 92 sessions is **1.00 at every TF**, so inside the window a 30s
bar count IS a clock (the omitted bars are elsewhere in the day). The measured clock span of the
EMA and cross windows at the signal bars equals the nominal one to two decimals.

\* **SURPRISE / PARITY BUG.** Both shipped Pines compute `tfMin = math.max(1.0, seconds/60)`, so
on a 30-SECOND chart `crossBars = round(7/1) = 7` bars = **3.5 minutes**, not the 14 bars every
30s study in this repo (`na_s30`, `na_live`, sections 22-26, `fwd_track`, `fwd_live`) models.
The two are different rules on the same bars (below, section 5). `flatNow` has the same clamp and
submits the 11:00 flatten one 30s bar early. Not fixed here (pine/ is read-only for this task).

## 2. Diagnostics before P&L (`t1_diag.csv`, `t1_exitmix.csv`)

| tf | ungated breaks | kept by gate | keep rate | gate base rate | trades | sess | +0.71 relabelled | median hold | fill beyond range edge |
|---|---|---|---|---|---|---|---|---|---|
| 30s | 161 | 56 | 0.348 | 0.198 | 54 | 52 | 33% | 3.0 min | 7.9 pts |
| 1m | 161 | 28 | 0.174 | 0.148 | 24 | 24 | 25% | 3.5 | 17.4 |
| 2m | 160 | 27 | 0.169 | 0.124 | 22 | 20 | 32% | 4.0 | 43.2 |
| 3m | 161 | 13 | 0.081 | 0.070 | 11 | 9 | 36% | 6.0 | 42.3 |
| 4m | 159 | 16 | 0.101 | 0.088 | 15 | 13 | 27% | 12.0 | 41.5 |
| 5m | 153 | 18 | 0.118 | 0.058 | 16 | 14 | 31% | 10.0 | 65.0 |
| 15m | 145 | 10 | 0.069 | 0.063 | 8 | 8 | 0% | 22.5 | 117.5 |

**The trade-count collapse (54 -> 8) is entirely the gate.** The ungated trigger is the same
~160 breaks on all 92 sessions at every timeframe; what changes is how often a fresh 13x48 cross
sits within 7 minutes of it. Because 13/48 are bar counts, the averages' reach grows 30-fold from
30s to 15m while the recency window stays at ~7 minutes (1 bar at 5m/15m), so a qualifying cross
becomes rare: gate base rate 19.8% -> 6.3% of window bars. All 52 of the 30s trade sessions
still have an ungated break at every TF; only 19 / 12 / 7 / 8 / 9 / 3 of them trade at
1/2/3/4/5/15m. Exit mix at 30s: stop/ratchet 46%, target 35%, opposite cross 19%, flatten 0%.

A second change grows with bar size: **the trigger stops being a break.** The share of ungated
triggers that fire on the FIRST eligible bar (price already beyond the range at 09:27) is 48% at
30s/1m, 60% 2m, 62% 3m, 83% 4m, 88% 5m, 94% 15m.

## 3. Declared conversion arms (`t2_arms.csv`), 92 sessions, 400-draw nulls

(a) as configured; (b) EMA held at matched minutes, bars = max(1,round(6.5/tf)) / max(2,round(24/tf));
(c) (b) + cross reach in CLOCK minutes (floor(7/tf) bars, 0 allowed) + range from bars lying
entirely inside 09:00-09:05 (irreducible at 15m, where no bar fits).

| tf | arm | EMA bars | n | %/trade | PF | delivered/MDE | p entry | p gate | P(mean<=0) |
|---|---|---|---|---|---|---|---|---|---|
| 30s | a=b=c | 13/48 | 54 | +0.0250 | 1.601 | 0.48 | 0.075 | 0.043 | 0.100 |
| 1m | a | 13/48 | 24 | -0.0261 | 0.644 | -0.31 | 0.735 | 0.762 | 0.813 |
| 1m | b=c | 7/24 | 67 | +0.0206 | 1.466 | 0.44 | 0.185 | 0.018 | 0.111 |
| 2m | a | 13/48 | 22 | -0.0318 | 0.530 | -0.39 | 0.630 | 0.797 | 0.863 |
| 2m | b | 3/12 | 74 | +0.0032 | 1.060 | 0.07 | 0.507 | 0.170 | 0.419 |
| 2m | c | 3/12 | 69 | +0.0149 | 1.306 | 0.31 | 0.355 | 0.058 | 0.195 |
| 3m | a | 13/48 | 11 | -0.0094 | 0.846 | -0.07 | 0.705 | 0.370 | 0.612 |
| 3m | c | 2/8 | 62 | +0.0142 | 1.286 | 0.28 | 0.605 | 0.025 | 0.218 |
| 4m | a | 13/48 | 15 | -0.0340 | 0.527 | -0.34 | 0.915 | 0.605 | 0.838 |
| 4m | c | 2/6 | 58 | +0.0048 | 1.078 | 0.09 | 0.463 | 0.105 | 0.395 |
| 5m | a | 13/48 | 16 | -0.0161 | 0.748 | -0.16 | 0.490 | 0.650 | 0.696 |
| 5m | b=c | 1/5 | 62 | -0.0178 | 0.677 | -0.40 | 0.932 | 0.645 | 0.872 |
| 15m | a | 13/48 | 8 | +0.1021 | 3.697 | 0.65 | 0.193 | 0.030 | 0.032 |
| 15m | c | 1/2 | 40 | -0.0634 | 0.400 | -0.91 | 1.000 | 0.990 | 0.994 |

Holding the EMAs in minutes restores the trade count on every TF (58-74) and restores 1m almost
exactly (PF 1.466 vs 1.601). It does NOT restore 3m-15m. At 15m the matched EMA is degenerate --
EMA(1) is the close itself -- so the 30s gate has no 15m representation at all; the 15m (a) row's
PF 3.70 is 8 trades on 8 sessions, 3 of them in the research half at -0.0387.

**Latency decomposition (`t2_latency.csv`).** Keep the 30s rule, gate and 30s exits unchanged and
move ONLY the fill to the close of the tf-bar containing the touch (what a bar-close market order
on a tf chart does): median extra delay +0.5 / +0.5 / +2.5 / +1.25 / +2.5 / +4.25 min, and
**PF 1.601 -> 1.539 (1m) / 1.646 (2m) / 0.927 (3m) / 1.078 (4m) / 0.798 (5m) / 0.745 (15m)** on
the same 54-56 triggers. The 3m/4m non-monotonicity is bar alignment: half the triggers sit on
the 09:27 bar, which a 3m bar (09:27-09:30) delays 2.5 min and a 4m bar (09:24-09:28) only 1.
Replicates `run_n26`'s latency table (a 3-minute delay inverts the edge) by a different route.

## 4. Drop-one on arm (c) (`t3_dropone.csv`), paired deltas in %/trade

| tf | full | -gate | -breakeven | -opposite-cross exit |
|---|---|---|---|---|
| 30s | +0.0250 (PF 1.60) | -0.0427 | +0.0047 | -0.0012 |
| 1m | +0.0206 (1.47) | -0.0389 | +0.0091 | +0.0034 |
| 2m | +0.0149 (1.31) | -0.0237 | +0.0065 | +0.0024 |
| 3m | +0.0142 (1.29) | -0.0431 | +0.0069 | +0.0053 |
| 4m | +0.0048 (1.08) | -0.0200 | +0.0074 | +0.0023 |
| 5m | -0.0178 (0.68) | +0.0053 | -0.0130 | +0.0129 |
| 15m | -0.0634 (0.40) | +0.0456 | -0.0005 | 0.0000 |

The gate is the only load-bearing component: ungated, the rule loses on every TF (-0.009 to
-0.029 %/trade, PF 0.66-0.87). It stops carrying at 5m/15m, where removing it helps -- the
conversion has broken the gate itself there. Breakeven and the opposite-cross exit each subtract
on 5 of 7 TFs (as `run_n7`/`run_n12` found); removing breakeven drops the win rate ~0.65 -> 0.50
while raising %/trade, i.e. the 60-70% win rate is partly the +0.71 relabelling (25-36% of trades).
Every delta is inside its own MDE (0.034-0.074).

## 5. One declared 27-cell grid per TF, research half only (`t4_grid.csv`, `t4_consensus.csv`)

Axes: EMA reach (3.25/12, 6.5/24, 13/48 min) x cross reach in clock minutes (3.5, 7, 14) x last
entry (590, 600, 615). Effective cells after collapsing identical research trade sets: 21 / 22 /
26 / 24 / 25 / 26 / **4** (at 15m the whole cross axis is one cell). E[max t | noise] printed
before reading: 1.92 / 1.94 / 2.01 / 1.98 / 2.00 / 2.01 / 1.05, all against 2.802.

Research share profitable: 30s 0.667, 1m 0.778, 2m 0.370, 3m **0.037**, 4m 0.593, 5m **0.000**,
15m **0.000**. The EMA-reach marginal is best at **6.5/24 minutes** on 30s, 1m, 2m, 3m and 4m and
the 13/48-minute row (= 1m bars carried as counts) is worst or near-worst on every one of them:
the grid independently picks the minutes conversion. Best research |t| per TF 2.82 / 1.16 / 2.44
/ 2.41 / 0.95 / 2.05 / 2.91 -- none above 2.802 except 30s and 15m, and both of those are cells
the marginal read does not choose (15m's is a negative t).

Consensus cells read once on the second half:

| tf | consensus cell | research n / PF | second n / PF | 2nd delivered/MDE | 2nd p entry | 2nd p gate | 2nd P(mean<=0) | win vs driftless BE 0.511 | trades needed |
|---|---|---|---|---|---|---|---|---|---|
| 30s | 13/48 bars, cross<=14m, end 615 | 42 / 1.654 | 39 / 1.255 | 0.20 | 0.273 | 0.025 | 0.277 | 0.615 | 945 |
| 1m | 7/24, cross<=14m, end 600 | 44 / 1.508 | 42 / 1.109 | 0.10 | 0.585 | 0.033 | 0.401 | 0.619 | 4,370 |
| 2m | 3/12, cross<=3.5m, end 600 | 29 / 1.778 | 25 / **1.630** | 0.34 | 0.453 | 0.085 | 0.159 | 0.680 | 211 |
| 3m | 2/8, cross<=3.5m, end 600 | 24 / 1.103 | 28 / **1.536** | 0.32 | 0.642 | 0.022 | 0.186 | 0.679 | 281 |
| 4m | 2/6, cross<=3.5m, end 615 | 26 / 1.430 | 20 / 1.008 | 0.01 | 0.600 | 0.130 | 0.494 | 0.600 | 679,545 |
| 5m | 1/2, cross<=3.5m, end 600 | 19 / 0.956 | 11 / 0.496 | -0.26 | 0.570 | 0.502 | 0.796 | 0.455 | -- |
| 15m | 1/3, cross<=3.5m, end 590 | 23 / 0.352 | 19 / 0.539 | -0.41 | 0.953 | 0.843 | 0.876 | 0.421 | -- |

"Trades needed" = (2.802 sd / mean)^2 on the second half. At the 92-session rate the positive rows
trade 0.5-0.9 times a session (~130-225 trades a year), so 211 trades is ~1-2 years of forward
data with 09:00 pre-open coverage. The realised-payoff break-even (avg win vs avg loss) is
0.54-0.60, not 0.511, because the ratchet books +0.71 wins against ~-25 to -75 point losses;
the four positive second-half rows clear it by +2.2 (1m), +5.2 (30s), +9.9 (3m) and +11.2 (2m) points
of win rate.

## 6. The PF 1.5 verdict per timeframe (`t5_verdict.csv`)

(i) PF >= 1.5, delivered/MDE >= 1, both nulls p <= 0.05; (ii) PF >= 1.5 but unresolvable at this
n; (iii) PF < 1.5. Judged on the second-half read of the consensus cell -- the only read nothing
was chosen on -- with the declared conversion arm (c) over all 92 sessions beside it.

| tf | arm (c), 92 sess: n / PF / ratio | consensus, 2nd half: n / PF / ratio / p entry / p gate | verdict |
|---|---|---|---|
| 30s | 54 / 1.601 / 0.48 | 39 / 1.255 / 0.20 / 0.273 / 0.025 | **iii** on the honest read (the configured cell itself is ii: 1.601 over 92 sessions, 0.48x MDE) |
| 1m | 67 / 1.466 / 0.44 | 42 / 1.109 / 0.10 / 0.585 / 0.033 | **iii** |
| 2m | 69 / 1.306 / 0.31 | 25 / 1.630 / 0.34 / 0.453 / 0.085 | **ii** -- reached on both halves (1.78 / 1.63), 0.34x MDE, entry null not cleared |
| 3m | 62 / 1.286 / 0.28 | 28 / 1.536 / 0.32 / 0.642 / 0.022 | **ii, wrong shape** -- research PF 1.10 with 3.7% of its grid profitable; 2nd half better than research |
| 4m | 58 / 1.078 / 0.09 | 20 / 1.008 / 0.01 / 0.600 / 0.130 | **iii** |
| 5m | 62 / 0.677 / -0.40 | 11 / 0.496 / -0.26 / 0.570 / 0.502 | **iii** -- 0% of research grid profitable |
| 15m | 40 / 0.400 / -0.91 | 19 / 0.539 / -0.41 / 0.953 / 0.843 | **iii** -- 0% profitable; 4 effective cells; the gate cannot be represented |

No timeframe reaches (i), and 30s itself does not: the configured 30s cell is 0.48x its MDE with
an entry-null p of 0.075. Nothing on 1m-15m clears a matched random ENTRY on any read (best 0.185);
several clear the random GATE (1m 0.018-0.035, 3m 0.022-0.025), which is the question "is the fresh
cross better than a random veto of the same size" -- it says the gate carries information, not
that the strategy beats zero.

**The Pine's own 30s reading (section 1 footnote), scored as a second look (`t5_pine30s.csv`):**
crossBars = 7 bars (3.5 min) gives **39 trades, +0.0593 %/trade, PF 3.149, win 0.795, 1.00x MDE,
entry-null p 0.005, gate-null p 0.000, P(mean<=0) 0.004**, PF 3.28 / 3.07 on the two halves. It
is exactly at its MDE, it is a cell of the declared 30s grid (research t 1.75 there, below the
1.92 noise floor for that grid, and not the cell the marginal read picks), and it is measured on
the same 92 sessions every 30s study here has already read. It is the strongest row in the
workstream and it is ONE sample; treat it as the configuration to forward-test, not a result.

## 7. Mechanism, in five sentences

The ungated 09:00-range trigger is identical on every chart (~160 breaks on 92 sessions); the
trade count collapses because EMA 13/48 are bar counts, so their reach grows 30-fold from 30s to
15m while the 7-minute fresh-cross window does not, and a qualifying cross becomes rare (keep rate
0.35 -> 0.07). Converting the EMAs to minutes restores the count everywhere and restores the
result at 1m (PF 1.47) but not beyond 2-3m, because the edge lives in the first 1-2 minutes after
the touch and a bar-close market order on a tf chart fills up to a whole bar later -- median fill
7.9 points beyond the range edge at 30s, 43 at 2m, 65 at 5m, 118 at 15m, and the latency alone,
imposed on the unchanged 30s rule, takes PF 1.60 to 0.80 at 5m and 0.75 at 15m. At 4m+ the
trigger also stops being a break (83-94% of triggers are "already beyond the range at 09:27"),
the range is not the 09:00-09:05 range (8 min at 4m, 15 at 15m), and at 15m the minutes-matched
gate degenerates to EMA(1). The parts that are parameters convert correctly in minutes; the part
that kills 3m-15m -- detection latency at bar close -- is not a parameter and cannot be converted.

## 8. What would change this

- **Calendar with 09:00 pre-open coverage.** All seven timeframes share 92 sessions; the 2m row needs
  ~211 trades at its second-half effect (~1-1.5 years); the Pine-30s row is already at its MDE
  (39) but was found after the sample had been read many times, so it needs a fresh 40+. Only more sessions resolve it; resampling to
  another bar size adds none.
- **An order model without bar-close latency** -- a resting stop at the range edge (TV bar
  magnifier / `request.security_lower_tf`) -- would remove the one irreducible mechanism; it is a
  different order model and would need its own parity harness.
- **The Pine clamp.** Decide whether the intended 30s rule is 7 minutes (research, 14 bars) or
  what TradingView actually runs (7 bars); every 30s figure in this repo models the former.
- A second US30 provider or index at 30s/1m with pre-open bars, to make any row a second test.
