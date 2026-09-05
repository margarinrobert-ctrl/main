# STUDY_FTM_ANATOMY — reverse-engineering the FTM opening-range breakout: where the edge is

**Brief.** Walk-forward, parameter, cluster, robustness and Monte Carlo tests on
`FTM_OPENING_RANGE_BREAKOUT_MNQ_v1_8_0_ALPHA2`, reverse-engineer it for the edge, and start a
durable library of reverse-engineered mechanisms (`docs/ib/EDGE_LIBRARY.md`). Everything here is
`research/ftm/ftm_anatomy.py` over the strategy's own simulator (`ftm_sim.py`, now with fourteen
component switches that each default to the shipped behaviour), on 1,048,575 real one-minute NQ
bars, 2022-12-26 to 2025-12-11, MNQ contract specs, the shipped FixedDollar sizing. Output in
`results/ftm/anatomy.txt`. The 15-minute US30 and US100 feeds cannot run a strategy whose opening
range, admission test and refinement observations are all defined on exact one-minute bars, so
NQ is the only run, with the caveats the two earlier FTM studies carry: NQ path not MNQ,
synthetic levels (basis-point features distorted), and the first ~120 sessions unable to trade.

**In-sample is 2023–2024 (195 trades), out-of-sample is 2025 (147).** Nothing below was selected
on 2025 except inside the walk-forward, whose folds are declared in advance. R is in points over
the sized stop, gross of the $2.50 per-contract reserve (worth 0.016 R); dollars are net of it.

---

## 1. The verdict in five lines

1. **The edge is the breakout SIDE and the breakout TIMING, not the machine around them.** The
   direction model, the prior-day override, the high-ORB regime plan, the stop, the 15:30 rule
   and the admission tests each contribute between −0.01 and +0.03 R. Remove the kNN and the
   prior-day override together and the result is +0.158 R against +0.155.
2. **The stop is decoration.** Placed at 100× the opening range, i.e. no stop, the strategy earns
   +0.163 R against +0.155, still beats its control (p 0.004), and the drawdown rises only from
   $2,870 to $3,976. The stop costs −136 R at the barrier and saves nothing.
3. **No target is better** (+0.191 R, p 0.030), for the fourth independent time on this branch. The
   grid agrees on both blocks: target 8R is the best level in-sample and second-best out.
4. **"Always long" with the identical machine earns more** (+0.171 R, control +0.031, p 0.000), and
   in 2025 it earns +0.256 against the breakout side's +0.096. In-sample the breakout side won
   (+0.190 against +0.107). What the side is worth over a coin flip is +0.10 R; what it is worth
   over "just buy" is +0.08 R in 2023–24 and −0.16 R in 2025.
5. **It is one strategy.** The 200-cell exit-geometry grid collapses to 2 clusters and 5 principal
   components at median pairwise correlation 0.746; rank stability from in-sample to out is
   Spearman −0.05 and the in-sample top decile lands exactly on the all-cell mean out of sample.
   No optimiser found anything the defaults do not already do.

---

## 2. Anatomy: one component at a time

Every row re-runs the whole strategy with ONE thing changed. `ctl` is the random quarter-hour
entry on the same sessions with the identical management (500 draws), `p` the share of draws
at or above the row.

| variant | n | net | R | PF | win | IS R | OOS R | control | p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **as shipped, alpha.2** | 342 | $11,020 | +0.155 | 1.34 | 47% | +0.200 | +0.096 | +0.065 | **0.008** |
| RC1 (prior 2 bars, no cap) | 342 | $11,661 | +0.162 | 1.35 | 47% | +0.194 | +0.119 | | |
| stop placed at 2× ORB | 342 | $12,650 | +0.178 | 1.34 | 53% | +0.217 | +0.126 | | |
| stop placed at 4× ORB | 341 | $8,426 | +0.123 | 1.21 | 53% | +0.181 | +0.047 | | |
| **no stop** (100× ORB) | 341 | $10,400 | +0.163 | 1.27 | 53% | +0.225 | +0.081 | +0.051 | **0.004** |
| **no profit target** | 342 | $13,654 | **+0.191** | **1.41** | 44% | +0.236 | +0.133 | +0.095 | **0.030** |
| no managed stop | 342 | $9,573 | +0.131 | 1.27 | 43% | +0.158 | +0.094 | | |
| no 15:30 conditional exit | 342 | $11,250 | +0.161 | 1.34 | 49% | +0.202 | +0.106 | +0.065 | 0.006 |
| stop + 16:00 flatten only | 342 | $10,524 | +0.147 | 1.28 | 43% | +0.141 | +0.155 | +0.098 | **0.148** |
| no kNN direction model | 342 | $11,141 | +0.155 | 1.34 | 47% | +0.190 | +0.107 | | |
| no prior-day override | 342 | $11,048 | +0.158 | 1.33 | 47% | +0.200 | +0.103 | | |
| **raw breakout side** (no kNN, no prior) | 342 | $11,168 | +0.158 | 1.34 | 47% | +0.190 | +0.115 | +0.074 | 0.012 |
| no refinement (submit at the signal) | 342 | $8,601 | +0.116 | 1.24 | 46% | +0.210 | **−0.010** | +0.070 | **0.120** |
| no direct action | 342 | $10,421 | +0.143 | 1.32 | 47% | +0.179 | +0.095 | | |
| no admission geometry | 345 | $10,210 | +0.130 | 1.31 | 46% | +0.140 | +0.116 | | |
| no touch veto | 362 | $10,939 | +0.147 | 1.31 | 47% | +0.203 | +0.076 | | |
| no admission at all | 364 | $10,206 | +0.126 | 1.29 | 46% | +0.150 | +0.095 | +0.063 | 0.062 |
| always the 3R plan (no high-ORB regime) | 342 | $11,047 | +0.156 | 1.34 | 46% | +0.193 | +0.105 | | |
| **10:00 signal only** | 145 | $4,358 | +0.143 | 1.28 | 46% | +0.190 | +0.096 | **+0.020** | **0.020** |
| **always long** | 341 | $13,032 | **+0.171** | 1.36 | 46% | +0.107 | **+0.256** | +0.031 | **0.000** |
| always short | 342 | −$46 | −0.002 | 1.00 | 41% | +0.115 | −0.158 | | |
| random side, 5 seeds (mean) | 341 | | +0.056 | | | | | +0.013 | 0.000 |
| no warm-up requirement | 454 | $15,219 | +0.153 | 1.35 | 46% | +0.181 | +0.096 | | |

**Exit split, sum of R by exit reason:**

| variant | stop | target | 15:30 | 16:00 | stop share |
| --- | ---: | ---: | ---: | ---: | ---: |
| as shipped | −135.7 | +104.5 | +58.7 | +25.5 | 49% |
| no stop | +2.5 | +119.0 | −93.5 | +27.6 | 10% |
| no target | −137.7 | 0 | +174.5 | +28.7 | 52% |
| no 15:30 exit | −138.7 | +108.7 | 0 | +85.0 | 50% |
| stop + 16:00 only | −161.0 | 0 | 0 | +211.3 | 47% |

What that says:

* **Direction.** Coin flip +0.056, breakout side +0.158, always long +0.171, always short −0.002.
  The breakout side carries +0.10 R of information over a coin flip — that is real, and it is the
  whole "signal". The kNN model (+0.003 R), the prior-day override (−0.003), the high-ORB regime
  (−0.000) and the alpha.2 policy changes (−0.007) are inert. A quarter of the source file
  decides nothing.
* **Timing.** The control earns +0.065 R on the same sessions; at the 10:00 decision alone it
  earns +0.020, and the rule +0.143 there. The first quarter-hour after the range is where the
  breakout timing is worth most over a random entry, and later signals ride drift the control
  also rides.
* **Barriers.** The stop can be removed. The target should be. Together with the managed stop and
  the 15:30 rule they form the exit machine; strip ALL of them and the rule still earns +0.147
  but the control earns +0.098 and the pass is gone (p 0.148). So the excess over a random entry
  is partly the exit machine's response to the trade — the managed stop (+0.024 R) and the
  15:30 rule (−0.006) are neutral alone but the target harvests the tail that a random entry
  does not have.
* **Refinement.** The weak-signal delay, the high-vol vote and the prior/intraday observation
  branches are worth +0.04 R overall and ALL of 2025: submit at the signal and 2025 goes to
  −0.010 R. That is the most fragile component here and the one alpha.2 was editing.

---

## 3. Parameter grid — 200 exit-geometry cells, and eleven ladders

Stop {0.75, 1.0, 1.25, 1.5, 2.0}× ORB × target {1.5, 2, 3, 4, 8}R × managed trigger {0.75, 1.25,
2.0, off} × 15:30 exit {on, off}. **200 of 200 cells positive; 96% positive in-sample and 100%
out.** The shipped cell is the 82.5th percentile in-sample and the 49.5th out.

| axis | in-sample marginal R | out-of-sample marginal R |
| --- | --- | --- |
| stop mult | 0.75: +0.094, 1.0: +0.065, 1.25: +0.170, 1.5: +0.167, 2.0: +0.158 | 0.75: **+0.132**, 1.0: +0.109, 1.25: +0.108, 1.5: +0.078, 2.0: +0.066 |
| target R | 1.5: +0.064, 2: +0.119, 3: +0.147, 4: +0.150, 8: **+0.175** | 1.5: +0.080, 2: +0.081, 3: +0.102, 4: **+0.117**, 8: +0.114 |
| managed trigger | 0.75: +0.141, 1.25: +0.139, 2.0: +0.127, off: +0.116 | 0.75: **+0.120**, 1.25: +0.095, 2.0: +0.082, off: +0.097 |
| 15:30 exit | off +0.128, on +0.134 | off +0.098, on +0.099 |

The target axis is the only one that agrees across blocks: **wider is better, and 8R is
"no target"**. The stop axis INVERTS (tight stops best out of sample, worst in), the managed
trigger is flat, the 15:30 exit does nothing. Rank stability IS→OOS Spearman **−0.052**; the
in-sample top decile (+0.221) lands at **+0.099** out of sample, exactly the all-cell mean.
Neighbourhood coherence 0.953 — a smooth hill, not a spike, and not a ridge either.

**One-at-a-time ladders** (whole sample, shipped value starred): admission body 0/0.15*/0.3/0.45 →
+0.163/+0.155/+0.155/+0.158; close location 0.4–0.8 → +0.132/+0.143/+0.155*/+0.172/+0.117;
touches 1–5 → +0.146/+0.162/+0.155*/+0.169/+0.167; ORB quantile 0.5/0.75*/0.9 →
+0.154/+0.155/+0.143; kNN flip threshold 0.55/0.65*/0.75/2.0 → +0.130/+0.155/+0.155/+0.155 (the
model only ever HURTS when allowed to act); prior-day 150/300*/600/off → +0.157/+0.155/+0.158/
+0.158; 15:30 profit boundary 0.5–2.0 → +0.151/+0.155*/+0.160/+0.164; VWAP distance
10/20*/40/off → +0.143/+0.155/+0.128/+0.141. Every ladder is flat to within 0.03 R except the
close-location cliff at 0.8 and the kNN at 0.55.

---

## 4. Walk-forward — the search inside the fold

Anchored training on everything before the fold, four half-year folds, three selectors over
the 200-cell grid.

| selector | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | concatenated OOS |
| --- | ---: | ---: | ---: | ---: | --- |
| best cell by R | +0.267 | +0.266 | +0.215 | +0.040 | **+0.197 R, $13,252, PF 1.43, 4/4** |
| plateau cell | +0.267 | +0.273 | +0.178 | −0.024 | +0.174 R, $12,940, PF 1.42, 3/4 |
| shipped defaults | +0.180 | +0.295 | +0.165 | +0.032 | +0.170 R, $11,169, PF 1.38, 4/4 |

The "best" selector picks the same thing every fold — stop 1.5×, **target 8R** — and beats the
defaults by +0.027 R out of sample, entirely because removing the target is better (§2). It is the
first walk-forward on this branch where the optimiser beat the author's defaults, and it did so
by finding one thing the branch already knew. **All three selectors fall to +0.04 / −0.02 / +0.03
in 2025-H2.** The last six months are flat for every cell in the grid.

---

## 5. Clusters

**Cells.** 200 cells → **2 clusters** at within-correlation 0.7; **5 principal components**
explain 90% of the variance; median pairwise correlation 0.746. The exit geometry does not change
the trade set, so the grid is one strategy scored 200 ways. The larger cluster (120 cells,
IS +0.165) decays to +0.084 out of sample; the smaller (80 cells, IS +0.080) improves to +0.121.

**Trades.** k-means (k=4) on the 14 direction features, fitted on 2023–24, read on 2025:

| cluster | IS n | IS R | OOS n | OOS R | what it is |
| --- | ---: | ---: | ---: | ---: | --- |
| 2 | 19 | **+0.423** | 29 | +0.074 | wide ORB, far from VWAP — the in-sample winners, gone |
| 1 | 51 | +0.202 | 50 | **+0.174** | prior 5-day return aligned with the breakout — continuation |
| 3 | 87 | +0.169 | 43 | +0.044 | the typical signal |
| 0 | 38 | +0.156 | 25 | +0.053 | prior 5-day return against the breakout |

Per-feature tercile splits (top third minus bottom third of R) agree in sign from IS to OOS on
**57% of features**, chance being 50%. VWAP distance is the strongest in-sample separator (+0.42
R) and keeps +0.10 out; the aligned 30-minute return keeps +0.32 → +0.27; `orb_bps` flips sign.
The one feature that holds strongly on both blocks is `weekday_sin` (+0.35 → +0.38), and calendar
conditions are banned from selection here for the reason `STUDY_1R_PROCEDURE` records.

---

## 6. Robustness

* **±20% perturbation** on twelve parameters: largest move 0.068 R, no sign flips. The two
  sensitive knobs are the stop multiple ×0.8 (+0.087 — a tighter stop hurts) and the kNN flip
  threshold ×0.8 (+0.105 — the model hurts when it fires more).
* **Cost.** The $2.50 reserve is 0.016 R per contract. Net at $0 / 2.5 / 5 / 10 / 20 per contract:
  $12,180 / $11,020 / $9,860 / $7,540 / $2,900. It survives four times its assumed cost and dies at
  eight. Slippage beyond the reserved tick is not modelled.
* **Warm-up off** +0.153 (454 trades); **loose contiguity** +0.158; **lookback 40 / 60** +0.153 /
  +0.155.
* **Bootstrap** on trades P(mean R ≤ 0) 0.006, 90% CI [+0.049, +0.265]; **day-block bootstrap**
  0.008, [+0.047, +0.264].
* **Shape.** IS +0.200 → OOS +0.096: decays, the right shape.

## 7. Monte Carlo

* **Permutation** of the 342 realised trades at the shipped $535 risk (10,000 paths): max
  drawdown median $2,935, p95 $4,655, p99 $5,604. The realised $2,870 sits at the 47th percentile
  — neither lucky nor unlucky.
* **1% of equity per trade**: max drawdown median 11.5%, p95 17.6%, P(DD > 10%) 0.73; final
  equity multiple over the sample (bootstrap) median 1.66, 5th percentile 1.15, P(< 1) 0.011.
* **60-trading-day evaluation**, $50,000, +6% target, 4% trailing floor, shipped sizing, from
  day-block draws: **P(pass) 19.9%, P(bust) 13.5%, P(neither) 66.6%.** Sized to survive, it grinds
  — the same distribution problem `STUDY_V15_BOOK` recorded.

---

## 8. What the strategy IS, in one sentence without indicator names

*After a 15-minute opening range, take the side of the first quarter-hour close beyond it,
hold to the cash close with no target, and accept that in a rising year "just buy" does the
same.* The stop, the direction model, the regime plan, the admission tests and the 15:30 rule
can be removed one at a time without changing the answer; the target should be. Its evidence
against a random entry is real (p 0.004–0.030 in every configuration that keeps the target or
the stop) and small (+0.09 R), and the six months to the end of 2025 earned nothing under any
parameter set. Added to `EDGE_LIBRARY.md` as E8 with those qualifications.

## 9. Files

| file | what |
| --- | --- |
| `research/ftm/ftm_sim.py` | the simulator, now with `KNOBS` (fourteen component switches, all default-off) and 14 feature columns per trade |
| `research/ftm/ftm_anatomy.py` | stages A–F, four-process pool, `results/ftm/anatomy.txt` |
| `results/ftm/grid_cells.csv`, `grid_trades.pkl`, `anatomy_variants.pkl`, `walkforward.csv` | every cell and variant |
| `docs/ib/EDGE_LIBRARY.md` | the durable list of mechanisms and the procedure |
