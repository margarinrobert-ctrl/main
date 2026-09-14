# V61 — optimising the CVD exhausted-sellers rule, 2,177,280 cells

`research/v61/` — `v61core.py` (the cached exit tensor and the sweep), `v61_verify.py` (the tensor
diffed against the published walker), `run_v61.py` (population, marginals, finalists — research
only), `run_v61b.py` (one locked read), `run_v61c.py` (the second null and the live tests),
`run_v61d.py` (the ablation), `v61_parity.py` (both presets under the script's own order model).
Output in `results/v61/`. Ships `pine/v61/V61_CVD_OPTIMISED_strategy.pine`.

---

## 1. What was swept, and what was declared before it ran

The shipped cell is NQ 30m, Donchian 20 entry / 20 exit, 2.0×ATR14 stop, no target, long only,
gated on price making a lower low while the CVD proxy makes a higher low at a confirmed pivot of
half-width k=3 within a 20-bar window (`STUDY_V54`/`V55`/`V56`).

| group | axis | settings |
|---|---|---|
| geometry | timeframe | 15 / 30 / 60 |
| | Donchian entry | 15 / 20 / 30 / 40 / 55 |
| | channel exit | 10 / 20 / 30 |
| | stop | 1.5 / 2.0 / 2.5 / 3.0 × ATR14 |
| | target | none / 3 / 4 / 6 × ATR |
| | maximum hold | 240 / 480 / 960 bars |
| signal | pivot half-width k | 2 / 3 / 4 / 5 |
| | recency window w | 5 / 10 / 20 / 30 / 40 |
| | the gate itself | ON at each (k, w), or **OFF** — the ablation that makes its contribution readable |
| filters | `(close − SMA200)/ATR ≥` | off / 0 / 1 / 2 (`STUDY_V40` — a FLOOR, not support) |
| | `CHOP(14) ≤` | off / 45 / 40 (`STUDY_V21`, `STUDY_V39`) |
| | `close >` prior RTH session high | off / on (`STUDY_V17`) |
| | adaptive stop | off / tighten by 1.0 ATR above the volatility median (`STUDY_V22`) |

Every additive filter is something that survived somewhere else on this branch, so the space is
declared rather than fished. **2,177,280 nominal cells; 725,760 EFFECTIVE** — the maximum-hold axis
is INERT, every setting identical to four decimals, because with a channel exit and an ATR stop one
of the two always fires first. `STUDY_V33`: an axis that changes nothing must be excluded, or a
stability score counts a flat line as passing rungs.

**The tensor was verified before it was used.** `v61_verify.py` diffs it against `v56core.walk` —
the walker the published result came from — on fifteen geometries across three timeframes:
**0 exit-bar mismatches and max |ΔR| 9×10⁻⁷** on 10,715 / 5,516 / 2,712 signal bars. 725,760
configurations a timeframe run in about four seconds.

## 2. The unit, and the axis that disagrees with itself

Scored in **percent of entry price**, not R. The first pass ranked on R and produced a top cell at
**+2.33 R** whose actual return was +0.319% of price — because R divides by the stop, so halving the
stop roughly doubles R for the same money. The stop axis then reads in exactly opposite directions:

| stop | mean R | mean total % of price |
|---|---|---|
| 1.5 N | **+0.347** | +7.5% |
| 2.0 N | +0.241 | +8.1% |
| 2.5 N | +0.203 | +8.7% |
| 3.0 N | +0.175 | **+9.1%** |

Same disease as `STUDY_SWEEP_110K`'s channel stop (94% of an apparent contribution was the
denominator) and `STUDY_V36`'s +0.674 R on trades losing 1.41 points, reached by a third route.
**R is a diagnostic here; percent of price is the score.**

## 3. The population, before any row of it

- 1,228,200 cells clear a 60-trade research floor (56.4%).
- **97.8% of them are profitable on research** — median +0.0667 % per trade, median PF 1.429. The
  best cell is the maximum of ~1.2 million positive draws.
- By timeframe: 15m 97.0% profitable, 30m **99.6%**, 60m 95.7%.

Marginal average per axis, on total percent of price (`results/v61/stage_a.txt` has all of them):

```
tf     15: +8.5%   30: +8.4%   60: +7.8%
exN    30: +8.6%   20: +8.6%   10: +7.8%
tp    none: +9.6%   6N: +8.9%   4N: +7.9%   3N: +7.0%      <- no target wins, the 13th time
adapt   off: +8.9%   on: +7.8%
chop    40: +8.4%   45: +8.4%   off: +8.2%
psh     on: +8.8%   off: +7.9%                              <- the largest additive filter
ma      2.0: +8.5%  0.0: +8.3%  off: +8.2%
cvd    off: +14.0% / +0.061 per trade   |   best gate rung: +8.7% / +0.098 per trade
```

That last line is the whole study in one row: **the gate earns the most per trade and OFF earns the
most in total**, because the gate removes 70–90% of the signals.

## 4. The one locked read

Nine finalists were declared on research — the marginal consensus, the top cell by total, by
per-trade, by an annualised trade Sharpe, the best one-rung neighbourhood MEAN (a neighbourhood
minimum is the over-correction `STUDY_1R_PROCEDURE` measured costing $18,970), and four more with
the CVD gate REQUIRED — plus the incumbent. Then the locked block was read once.

| cell | research %/trade | locked %/trade | locked total | locked PF | filter-null p |
|---|---|---|---|---|---|
| **S incumbent** | +0.1203 | **+0.1428** | +12.14% | 1.60 | **0.012** |
| F1 marginal consensus | +0.0915 | +0.0828 | +9.69% | 1.48 | 0.579 |
| F2 top research total | +0.0386 | +0.0590 | +28.39% | 1.29 | 1.000 (it filters nothing) |
| F3 best neighbourhood | +0.2994 | +0.0406 | +2.43% | 1.13 | 0.031 |
| F4 top research Sharpe | +0.2175 | +0.0536 | +1.72% | 1.37 | 0.196 |
| F5 top research per trade | +0.4543 | +0.0834 | +3.42% | 1.25 | 0.004 |
| G1 CVD kept: consensus | +0.0826 | +0.0453 | +3.49% | 1.30 | 0.717 |
| G2 CVD kept: top total | +0.1083 | +0.0384 | +5.68% | 1.20 | 0.927 |
| G3 CVD kept: top Sharpe | +0.2175 | +0.0536 | +1.72% | 1.37 | 0.196 |

**NOT ONE OF THE NINE BEATS THE INCUMBENT'S LOCKED PER-TRADE RESULT**, and the incumbent is the
only pre-declared cell that clears its control at p ≤ 0.05 on the locked block with a control that
is itself profitable. (F3 and F5 "clear" against control medians of −0.057 and −0.038 — they beat a
null that loses money while earning +0.04 and +0.08 themselves.)

**And the population says selecting on research was worse than not selecting:**

```
corr(research %/trade, locked %/trade)   Pearson -0.0262   Spearman -0.0202   (1,223,943 cells)
  top 100      research +0.4005  ->  locked +0.0425     73% profitable on locked
  top 1%       research +0.2315  ->  locked -0.0017     43% profitable on locked
  top decile   research +0.1624  ->  locked +0.0259     60% profitable on locked
  ALL CELLS    research +0.0722  ->  locked +0.0508     82% profitable on locked
```

The top 1% of research cells average **−0.0017** on the locked block against the whole population's
**+0.0508**. This is the sharpest version of a finding this branch has now made six ways
(`STUDY_V30` 0.96 fits / 0.07 predicts, `STUDY_V33` negative rank correlation in all four cells,
`STUDY_V60` −0.4426): a research ranking on this data does not carry.

## 5. The second null, which changes the answer

Stage B scored every cell against a random FILTER of the same selectivity. That is the right null
for a filter and the wrong one for a cell that filters nothing. Against a **random ENTRY** with the
same geometry, block, trade count and position lock (`STUDY_V11`'s gate):

| cell | research rule / random | p | locked rule / random | p |
|---|---|---|---|---|
| S incumbent | +0.1203 / +0.0137 | 0.000 | +0.1428 / +0.0567 | **0.204** |
| F2 unfiltered 15m | +0.0386 / +0.0146 | 0.000 | +0.0590 / +0.0189 | **0.002** |
| F1 marginal consensus | +0.0915 / +0.0065 | 0.000 | +0.0828 / +0.0685 | 0.432 |
| G2 CVD kept: top total | +0.1083 / +0.0065 | 0.000 | +0.0384 / +0.0552 | 0.615 |
| F3 best neighbourhood | +0.2994 / +0.0812 | 0.000 | +0.0406 / −0.0067 | 0.340 |

**The incumbent clears the filter null and fails the entry null; the unfiltered geometry does the
reverse.** No cell in the study clears both on the locked block. Read together they say the gate is
worth something on the 30-minute geometry and the trigger is not, and the 15-minute geometry beats a
random entry without any gate at all.

## 6. The ablation, which is the best evidence the gate has

One geometry, the gate switched on and swept, both blocks, everything else identical
(`results/v61/stage_d.txt`):

**Shipped 30m geometry** (Donchian 20/20, 2.0 N, no target) — percent per trade, research / locked:

| gate | keeps | research | locked |
|---|---|---|---|
| off | 100% | +0.0387 | +0.0571 |
| k2 w20 | 28% | +0.0920 | +0.1172 |
| k3 w10 | 12% | +0.1357 | +0.0918 |
| **k3 w20 (shipped)** | 22% | +0.1203 | +0.1428 |
| k3 w30 | 30% | +0.0929 | +0.1442 |
| k4 w20 | 17% | +0.1108 | +0.1214 |
| k5 w20 | 14% | +0.0891 | +0.1947 |
| k5 w40 | 27% | +0.0401 | +0.1773 |

**15m geometry** (Donchian 15/30, 3.0 N, 6 ATR target): off +0.0386 / +0.0590, and six of the seven
gate settings beat that on each block.

**The gate raises the per-trade edge in 12 of 14 cells across two geometries and both blocks.**
That is the strongest evidence for it anywhere on this branch — `STUDY_V54` and `V55` only ever had
one geometry — and it is a *per-trade* statement. In total return the gate is negative everywhere,
because 70–90% of the signals go with it.

## 7. What ships

`pine/v61/V61_CVD_OPTIMISED_strategy.pine`, one script with two presets. Both were diffed against
the research engine under the script's own order model (`v61_parity.py`), and both come back
CONSERVATIVE, which is the right direction:

| preset | trade count | identical exit bar | R correlation | research gap | locked gap |
|---|---|---|---|---|---|
| incumbent 30m | 242 / 242 (1.000) | 88.8% | 0.9998 | −4.9% | −1.5% |
| high activity 15m | 614 / 617 (0.995) | 93.7% | 0.9992 | −9.9% | −5.8% |

**INCUMBENT — 30m, Donchian 20/20, 2.0 N, no target, k3 / w20 (90 / 600 minutes).**
Locked +0.1428 %/trade, +12.14% total on 85 trades, PF 1.60. Filter null p 0.012, entry null 0.204.
It remains the recommendation: it is the only pre-declared cell that survived the locked block.

**HIGH ACTIVITY — 15m, Donchian 15 entry / 30 exit, 3.0 N stop, 6 ATR target, k3 / w30 (45 / 450
minutes).** Locked +0.0861 %/trade, **+17.91% total on 208 trades**, PF 1.48, Sharpe +1.89 against
the incumbent's +1.12. Filter null p 0.066, entry null **p 0.020**. 2.4× the trades and ~48% more
total return on the locked block at 60% of the per-trade edge.

**The second preset was picked from a 16-cell ablation read AFTER the locked block, so its
p-values are descriptive, not significance.** It is offered because it is the configuration the
evidence points at for total return with the gate retained, and labelled so nobody mistakes it for
a pre-registered result.

Robustness on both, from `results/v61/stage_c.txt`: the one-rung neighbourhood is **100%
profitable on both blocks** for the incumbent (9 neighbours, locked mean +0.1330) and for F2 and
F1; cost stress leaves the incumbent at +0.1197 %/trade at **4×** the assumed cost and F2 at
+0.0438; six chronological folds are positive 6/6 for the incumbent and F2. A 60-day 8%/−6% funded
evaluation at 2× notional gives the incumbent 34% pass / 9% bust / **57% neither** and F2 65% / 25%
/ 10%.

## 8. What this study is worth

1. **The optimisation did not find a better cell, and the population explains why.** With 97.8% of
   a 1.2-million-cell grid profitable on research and a research-to-locked correlation of −0.026,
   there was nothing to find; the top 1% of research cells is worse out of sample than the average
   cell.
2. **The incumbent is not beaten.** Nine declared finalists, none with a higher locked per-trade
   result, and it is the only one whose control passes there.
3. **The gate is real per trade and expensive in total.** 12 of 14 ablation cells, two geometries,
   both blocks — and it is why the strategy takes 85 locked trades instead of 249.
4. **The largest genuine improvement available is not a parameter.** It is trading the same idea on
   15-minute bars, which trades 2.4× as often for 48% more total return and clears the harder of
   the two nulls out of sample. That is a change of geometry, not a tuning.
5. Still ONE MARKET. The CVD proxy needs 1-minute bars and NQ is the only feed here that has them.
   Nothing in this study is a cross-market read, and the locked block has now been read by four
   studies, so its p-values are descriptive from here on.
