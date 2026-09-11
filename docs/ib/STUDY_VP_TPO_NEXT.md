# STUDY: the VP/TPO handoff executed -- the single print does not survive the years it never saw

**Brief.** `NEXT_VP_TPO_SCALP.md`, a specialist's audit of `STUDY_VP_TPO_SCALP.md`, laid out three
tiers: three free checks that could end the work, five research-only robustness items, then a set of
pre-registered reads on the feeds the NQ selection never touched. It asked for the process to be run
under Lopez de Prado's discipline. This note is the result, in the handoff's own order.

**Code.** `research/inst/vp_next0.py` (Tier 0 + PSR/DSR/MinBTL/power), `vp_tpo2.py` (parameterised
profile), `vp_next1.py` (bin x letter x ceiling sweep + CSCV), `vp_next1b.py` (stop inside the gate,
extension factor, extended drop-one, day effect), `vp_next2.py` (the pre-registered reads),
`vp_next_plot.py`. Outputs `results/inst/vp_next*.txt`.

## Verdict

**Toward abandoning, by the handoff's own pre-registered criterion.** On US100 before 2022-12-26 --
seven years of the same index the NQ selection never saw -- the gate reads **PF 0.907 on 1,092 trades**
against an abandon line of 1.10, is WORSE than its base (0.970) and worse than a random filter of the
same selectivity (day-clustered p 0.90). On US30, the mechanism test, **0.927 against a base of 0.973**
(p 0.83). On US100 AFTER 2022-12-26 -- the same weeks as NQ -- the 3 ATR gate reproduces at PF 1.354,
p 0.004, which is what a feed-parity block is supposed to do and is not evidence. The single print is a
2023-2025 Nasdaq regime, not a mechanism. The shipped Pine now defaults the gate OFF.

## Tier 0 -- the free checks (`vp_next0.py`)

**0.1 R/trade.** Gated locked reads **+0.037 R/trade** against +0.053 %/trade; PF in R units 1.122
against 1.382 in percent; t 0.75 per trade, 0.73 day-clustered. Positive, so the kill criterion did not
fire, but the edge is roughly half as large at constant risk as in percent of price -- the profitable
trades carry the larger ATR. The base itself is negative in R on locked (-0.008), as the handoff
suspected.

**0.2 The deployable trade set already existed.** `O._walk` tests the gate at the signal bar and
`continue`s without taking the position lock, so the shipped "gated" run IS the single-walker,
gate-as-veto build. Of the 187 locked gated trades 155 are base trades and 32 were admitted because a
vetoed signal freed the lock -- and those 32 read PF 0.92. The post-hoc subset of base trades reads
1.512 on 166; the veto build 1.382 on 187 stays the number of record.

**0.3 Day-clustered null.** Random signal DAYS at the gate's own day rate (141 of 228 locked signal
days), bar count matched: locked **p 0.044 on PF, 0.024 on the mean**, against 0.008 bar-matched. The
handoff predicted "nearer 0.05 than 0.016" and that is where it landed.

**Lopez de Prado statistics.** Zero-filled daily Sharpe: research 1.96 annualised (skew +1.2, kurtosis
12.7), locked 1.38 (skew +4.4, kurtosis 45). PSR(0) 0.999 research, 0.970 locked. **Deflated Sharpe on
research: 0.57 at 43 trials, 0.33 at 152** -- the trial-population sd of daily Sharpe (0.0525, from
the 41 scorable conditions) puts the expected best-of-noise at 0.117-0.141 per day against the observed
0.123. MinBTL 495-661 trading days against 599 in research. Power at the observed locked R-effect
(d 0.054): **1,300 trades for t 1.96, ~90 forward months**; the handoff's 284 was in percent space.

## Tier 1 -- research only

**1.1 Construction robustness + CSCV (`vp_next1.py`).** 8 bin definitions (1 / 2.5 / 5 / 10 points,
two price-proportional, two ATR-scaled) x 3 letters (15 / 30 / 60 min) x 3 ceilings: **67 of 72 cells
clear p <= 0.05** on research, every bin marginal PF 1.31-1.40, ATR-scaled and price-proportional bins
the best. The single print is NOT a resolution artefact. `0.10 x session ATR` (median 3.4 points on NQ,
1.6 on US100, 3.0 on US30) was fixed as the scale-invariant definition for Tier 2. **CSCV over the 360
construction x stop configurations, 586 research days, 12,870 splits: PBO 0.519** -- the in-sample best
ranks below the out-of-sample median half the time, the OOS rank of the IS best is 0.477, and the
degradation slope is -0.75. The population median SR is +0.092/day and P(OOS SR < 0 | IS best) is 0.03:
the family was uniformly positive on research and the ranking inside it carried nothing.

**1.2 Stop inside the gate (`vp_next1b.py`).** Research R/trade 1.5 ATR +0.033, 2.0 +0.082, 2.5
+0.087, **3.0 +0.091**, 3.19 +0.085, 4.0 +0.065; total over MC p99 drawdown peaks at 3.0 (3.15). The
handoff's expectation that the optimum would move tighter inside the gate did not materialise on
research; 3.0 was pre-registered. (Locked, descriptive, preferred 1.5 ATR at PF 1.571 -- the wrong-shape
trap, recorded and not acted on.)

**1.3 Extension factor.** Spearman of the single-print distance with the extension variables:
EMA13-48 -0.23, EMA200 -0.18, prior POC -0.40, VWAP -0.14, prior high -0.49. Conditional IC of the
extension variables against 15-bar forward return INSIDE the gate: -0.02, +0.02, -0.03, -0.09 -- no
independent information. The single print's own IC is -0.098 with decile monotonicity -0.70. **The MA
question closed: no MA leg.**

**1.4 Extended drop-one.** The gate beats the ungated set in the low and middle terciles of every
extension variable (EMA200 low tercile: gated 1.65 vs 1.03) and not in the top tercile (0.87 vs 1.18) --
the gate works when price is not extended, which is the latent "room above" reading, and it motivated
cell B below.

**1.5 The day effect without the Donchian.** Research: single-print days run +1.16 ATR open-to-close
against -0.23 (Welch p 0.012). Locked: -0.24 against +0.12 (p 0.67) -- the day effect does not
replicate. A random entry inside the gate's own days earns PF 1.22-1.32 on both blocks and the gated
breakout beats it only at p 0.04-0.06 on the mean. Read together: on the NQ sample the gate selected
good long days, that selection did not persist, and the breakout added little inside them.

## Tier 2 -- the pre-registered reads (`vp_next2.py`)

Frozen before any feed was opened: Donchian 10/10, 07:00-11:00 NY, 3.0 ATR stop, 2.3 ATR target, 230
minutes; gate = prior-session single print, 30-minute letters, bin 0.10 x session ATR, ceiling 4 ATR
primary / 3 ATR secondary; three MA cells (A: EMA13 < EMA48; B: (close-EMA200)/ATR <= NQ-research 2/3
quantile = 5.46; C: (close-VWAP07)/ATR <= 1/3 quantile = 0.57); nulls = bar-matched and day-clustered
random filter (250 each), random entry (150), day-block bootstrap, PSR. Thirteen reads, stated.

| block | base n / PF | gate 4 ATR n / PF | day-clustered p | gate 3 ATR n / PF | p |
| --- | --- | --- | --- | --- | --- |
| **US100 before 2022-12-26 (primary)** | 2264 / 0.970 | **1092 / 0.907** | 0.904 | 984 / 0.883 | 0.904 |
| US100 after 2022-12-26 (parity, same weeks as NQ) | 1125 / 1.122 | 556 / 1.203 | 0.164 | 480 / **1.354** | 0.004 |
| **US30 2016-2025 (mechanism)** | 3131 / 0.973 | **1555 / 0.927** | 0.828 | 1383 / 0.900 | 0.944 |

By year on US100 pre-2022 the gate reads 0.50 / 0.96 / 0.70 / 1.29 / 0.80 / 0.93 / 1.03 -- one positive
year in seven, and 2019 is the base's best year too. On US30's own split it is 0.97 / 0.79 / 1.02
against the base's 1.04 / 0.87 / 0.92. The three MA cells are negative on both unseen blocks (A 0.924 /
0.839, B 0.916 / 0.932, C 0.993 / 0.856) and the random-entry null beats every cell on US30.

**The short mirror on NQ research** (single print within 4 ATR below a downside breakout): base PF
0.945, gated **1.050**, clears its same-selectivity control at p 0.020, locked 1.136 descriptive. A
symmetric, small, one-market effect that would need its own cross-market read and, given the long
side's result, is not worth one.

## What this says

- The NQ finding was real on NQ and replicated once, on the block it was built to be read on. It was
  also present on the SAME WEEKS of a second Nasdaq feed. On seven earlier years of that index and on
  nine years of the Dow it is absent and slightly harmful. That is a regime, and `STUDY_V12`,
  `STUDY_V38` and `STUDY_V52` on this branch all recorded the same shape from the other direction (a
  rule failing where it was chosen and holding where it was not); this one holds where it was chosen and
  fails everywhere else.
- The Lopez de Prado numbers said so before the reads: DSR 0.33-0.57 on research, PBO 0.52 over the
  construction grid, MinBTL longer than the research block at the trial count. They did not say the
  finding was false; they said the sample could not distinguish it from the best of the trials, which is
  exactly the state a cross-market read resolves.
- The base scalp itself is null off-sample (US100 pre-2022 0.970, US30 0.973): the 07:00-11:00 Donchian
  10/10 window is a 2023-2025 Nasdaq object too.

## Do not

Re-tune the ceiling, bin or letter on NQ; run the VAH interaction; add a 44th condition; run the
Tier 3 meta-labelling (conditional on a positive Tier 2 and it was not). What would reopen the family: a
different base geometry on which the single print is tested fresh on US30 first, or a real order-flow
feed to replace the letter-count proxy of "no acceptance".
