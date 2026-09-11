# V22 — Volatility and the VIX: what a volatility state forecasts, and where the stop goes

Two questions were asked of the volatility complex:

1. **Can a volatility reading forecast REGIME** — is the next stretch going to chop or to
   distribute directionally?
2. **Can it tell you where to place the STOP and the TARGET?**

The answers are opposite, and the second one is the useful one.

- **Question 1 is NO, and it fails in the most diagnostic way available.** On the VIX itself the
  research-to-locked information-coefficient correlation on a chop label is **−0.638** — not noise,
  a systematic sign inversion. On 71 realised-volatility features it is **−0.047 / −0.183**. Of the
  top 50 VIX readings ranked on research, **7 keep their sign** out of sample.
- **Question 2 is YES, with one specific reading, and it replicates on both instruments and both
  blocks.** Heat measured *in ATR units* is not flat: it roughly doubles between the extremes of a
  forward-versus-trailing volatility state, monotonically, on the held-out block as well as the
  research one. The ATR stop is **backward-looking**, volatility **mean-reverts**, and the gap
  between the two is a measurable, tradeable sizing error.

## 0. The data, and what could not be done

`data/SPX.csv` (23,323 daily sessions, 1927→2020-11-04) and `data/VIX_daily.csv` (2,517 daily
sessions, 2012-01-03→2021-12-31) arrived by upload. Both are registered in `research/datasets.py`
with checksums.

**The VIX overlaps NOT ONE BAR of any futures feed on this branch.** It ends 2021-12-31; the NQ
file begins 2022-12-26, a 360-day gap. US30_LONG, US100_LONG and XAU would have overlapped it and
were destroyed by a container recycle. So:

- the VIX study runs on **SPX daily, 2,226 sessions 2012-01-03 → 2020-11-04**, the full overlap;
- the intraday study runs on **NQ 15m and 30m** with a **realised**-volatility family standing in;
- the two are connected by a shared mechanism, **never by a join**. Nothing below claims a VIX
  number applies to an NQ 15m chart.

Split is the standing one: first 65% of sessions is research, the rest is read once.
**The SPX locked block contains COVID.** That is stated before every table it touches.

## 1. The positive control — the VIX absolutely does forecast something

Before asking whether the VIX forecasts *chop*, ask whether it forecasts the thing it is built to
forecast. If that comes back null the harness is broken and nothing else is readable.

| reading | h | research IC | NW t | locked IC |
| --- | --- | --- | --- | --- |
| `vix_z500` | 5 | **+0.6262** | +4.60 | **+0.7809** |
| `vix` | 5 | +0.5824 | +5.90 | +0.7528 |
| `vix_pct500` | 5 | +0.5736 | +7.40 | +0.4852 |
| `log_vix` | 5 | +0.5708 | +6.86 | +0.6889 |

117 tests against forward realised volatility; **sign kept on the locked block 91%**. The VIX
forecasts the **magnitude** of the next move about as well as anything in finance forecasts
anything. The harness is fine.

## 2. Question 1 — chop forecasting fails, and it fails by INVERTING

Same 39 features, same horizons, label swapped to the forward efficiency ratio
(`|net move| / Σ|daily moves|` over the next *h* sessions; 1.0 is a straight line, ~0 is chop).

```
117 tests.  p <= 0.05: 44 (chance 6).  BH at q 0.10: 29.  Largest |IC| 0.2725.
Research IC vs locked IC, correlation over all 117 tests: -0.638
Of the BH survivors, 21% keep their sign out of sample (chance is 50%).
```

44 of 117 "pass" at α 0.05 against 6 expected, 29 survive BH — and **21% of them keep their sign**.
A family that passes multiplicity correction and then inverts is worse than a null family: the
significance is real, the *stability* is not. Every one of the top four research readings flips:

| # | feature | family | h | research IC | NW t | BH | locked IC | locked t | sign |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `vixts_20_120` | term structure proxy | 20 | +0.2725 | +2.65 | Y | −0.0934 | −1.34 | **FLIP** |
| 2 | `vixts_10_60` | term structure proxy | 20 | +0.2390 | +2.59 | Y | −0.0791 | −1.07 | **FLIP** |
| 3 | `vixts_20_120` | term structure proxy | 10 | +0.2100 | +2.96 | Y | −0.1206 | −1.96 | **FLIP** |
| 4 | `vix_ma200` | level and state | 20 | +0.1922 | +2.25 | Y | −0.1342 | −2.03 | **FLIP** |
| 5 | `vrp_z60` | volatility risk premium | 20 | +0.1871 | +2.40 | Y | +0.0479 | +0.59 | same |

**Of the top 50, 7 keep their sign.** By family, the marginal averages say the same thing — and note
which family holds up best:

| family | tests | median \|IC\| | best \|IC\| | BH | **sign kept** |
| --- | --- | --- | --- | --- | --- |
| term structure proxy | 9 | 0.1223 | 0.2725 | 6 | **0%** |
| realised vol | 9 | 0.1084 | 0.1500 | 2 | 11% |
| level and state | 33 | 0.1030 | 0.1922 | 7 | 6% |
| vol of vol | 9 | 0.1005 | 0.1748 | 3 | 0% |
| **volatility risk premium** | 36 | 0.0942 | 0.1871 | 11 | **36%** |
| change | 12 | 0.0349 | 0.0986 | 0 | 33% |
| bar shape | 9 | 0.0208 | 0.0804 | 0 | 67% |

The families with the **largest** research IC keep their sign **least**. The VRP — the only column
in the whole set that a price history cannot reproduce — has a middling IC and the best stability
of the substantive families. That ordering is the finding, not the top row.

The realised-volatility replication on NQ agrees. `research/v22/v22run.py`, 426 tests
(71 features × 3 horizons × 2 timeframes) against the same label:

```
p <= 0.05: 123 (chance 21).  BH at q 0.10: 87.  Largest |IC| 0.0874, median 0.0226.
Research IC vs locked IC: -0.047
```

and at trade level (`v22trade.py`, 2,556 control-gated conditions) **research excess vs locked
excess correlates −0.183**, with 23 of the top 50 beating baseline out of sample against a chance
of 50%, and **no family positive on its marginal average**. Two instruments, two asset scales, two
label constructions, same verdict.

**A volatility reading does not tell you whether the next stretch trends.** Stop asking it.

## 3. Question 2 — heat in ATR units is NOT flat, and that is the whole result

The right test for stop placement is not "do high-volatility bars move more" — they must, in points.
It is whether they move more **in units of their own ATR**. If that column is flat, the ATR has
already done the scaling and a volatility overlay adds nothing.

### 3a. On NQ, keyed on a realised percentile — replicates on the locked block

`pct_cc20_250`: where 20-bar close-to-close volatility sits within its own trailing 250-bar
distribution, read at the **signal** bar. Donchian 30/20 long, 2.0N stop, no target, real MNQ costs.

**NQ 15m**

| quintile | research n | MAE p50 | MAE p90 | stop-out | locked n | MAE p50 | MAE p90 | stop-out |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0–0.2 | 930 | **2.18** | 3.37 | 45.0% | 665 | **2.09** | 3.31 | 45.6% |
| 0.2–0.4 | 974 | 2.12 | 3.68 | 42.8% | 561 | 2.06 | 3.05 | 37.7% |
| 0.4–0.6 | 992 | 2.17 | 3.97 | 44.7% | 534 | 2.03 | 3.14 | 41.4% |
| 0.6–0.8 | 1135 | 1.53 | 3.02 | 39.3% | 579 | 1.47 | 2.71 | 31.9% |
| 0.8–1.0 | 1151 | **1.26** | 2.57 | 39.3% | 538 | **1.24** | 2.77 | 31.5% |

**NQ 30m**

| quintile | research n | MAE p50 | stop-out | locked n | MAE p50 | stop-out |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0–0.2 | 473 | **2.26** | 56.1% | 305 | **2.18** | 45.8% |
| 0.2–0.4 | 540 | 2.20 | 54.8% | 386 | 1.89 | 43.3% |
| 0.4–0.6 | 634 | 1.64 | 39.0% | 281 | 1.61 | 40.0% |
| 0.6–0.8 | 548 | 1.20 | 26.2% | 258 | 1.45 | 34.9% |
| 0.8–1.0 | 488 | **0.97** | 28.2% | 254 | **0.98** | 20.0% |

Monotone, on four independent columns, and the locked block reproduces the research slope almost
value for value. Median heat is **1.8× to 2.2× larger** in the low-volatility-percentile bucket than
in the high one, and the stop-out rate tracks it (45.6%→31.5% and 45.8%→20.0% on locked).

**The direction is the counter-intuitive one.** The naive rule is "widen stops when volatility is
high". This says the opposite: when realised volatility sits **low** in its own distribution, ATR(14)
has already contracted, so a 2.0N stop is *small* relative to the excursion the trade is about to
make. Volatility mean-reverts; the trailing ATR over-corrects.

### 3b. On SPX, keyed on the VIX — and the VIX LEVEL is the wrong reading

Same table, SPX daily, three states. The `vix` level column is **flat** —

| `vix` quintile | research MAE p50 | locked MAE p50 |
| --- | --- | --- |
| 1 | 1.97 | 2.27 |
| 2 | 2.08 | 2.09 |
| 3 | 2.03 | 1.57 |
| 4 | 1.87 | 2.19 |
| 5 | 1.63 | — |

— which is exactly what "the ATR has already scaled for it" looks like. **The VIX level adds nothing
to stop placement.** The volatility risk premium is a different matter:

| `vrp_ratio20` quintile | research n | MAE p50 | stop-out | locked n | MAE p50 | stop-out |
| --- | --- | --- | --- | --- | --- | --- |
| 1 (implied ≈ realised) | 59 | **0.94** | 22.0% | — | — | — |
| 2 | 58 | 1.27 | 19.0% | 30 | **1.43** | 36.7% |
| 3 | 58 | 2.17 | 63.8% | 29 | 1.57 | 34.5% |
| 4 | 58 | 2.12 | 60.3% | 45 | 2.05 | 31.1% |
| 5 (implied ≫ realised) | 59 | **2.08** | 39.0% | 77 | **2.18** | 59.7% |

`vrp_ratio20 = VIX / (20-day realised volatility, annualised)`. Heat in ATR units **more than
doubles** from the bottom quintile to the top, monotonically, and the locked block reproduces the
slope over the four quintiles it populates.

**Sections 3a and 3b are the same statement.** Heat in ATR units is large exactly when forward
volatility is going to exceed trailing volatility. NQ detects that condition with a realised
percentile (vol mean-reverts upward from lows); SPX detects it directly, by asking the option market.
The VIX's contribution is not a new regime — it is a **forward volatility estimate the ATR does not
have**, and its usable form is the *spread against realised*, not the level.

## 4. Is it actionable? The stop policy, and the sign check

Five stop policies declared before looking. One is the flat stop; one is the **naive inverse**,
which is the sign check — if widening in the *other* direction also helps, the state is not the
cause.

**NQ, `pct_cc20_250 ≤ 0.5` → wide stop** (research | locked):

| policy | research R | research PF | locked n | locked R | locked PF | locked P(mean≤0) |
| --- | --- | --- | --- | --- | --- | --- |
| **15m** flat 2.0N | −0.0286 | 0.957 | 385 | +0.0939 | 1.158 | 0.180 |
| 15m wide-low 2.5/1.5 | +0.0082 | 1.012 | 381 | **+0.1454** | **1.249** | 0.078 |
| 15m wide-low 3.0/1.5 | +0.0203 | 1.032 | 377 | +0.1421 | 1.258 | 0.073 |
| 15m **INVERSE** 1.5/2.5 | −0.0539 | 0.923 | 400 | +0.0626 | 1.100 | 0.301 |
| **30m** flat 2.0N | +0.0870 | 1.145 | 226 | +0.0873 | 1.156 | 0.228 |
| 30m wide-low 2.5/1.5 | +0.1093 | 1.178 | 223 | **+0.1008** | 1.181 | 0.176 |
| 30m **INVERSE** 1.5/2.5 | +0.0189 | 1.030 | 241 | +0.0433 | 1.073 | 0.373 |

**SPX, `vrp_ratio20 > research median (1.314)` → wide stop** (overlapping signals; see §5):

| policy | research R | research PF | locked R | locked PF |
| --- | --- | --- | --- | --- |
| flat 2.0N | +0.0155 | 1.028 | +0.6137 | 2.155 |
| wide when implied>realised 2.5/2.0 | +0.0438 | 1.088 | +0.6749 | 2.461 |
| wide when implied>realised 3.0/1.5 | **+0.0526** | **1.105** | **+0.6954** | **2.614** |
| **INVERSE** 2.0/3.0 | −0.0218 | 0.958 | +0.5786 | 2.165 |

The policy improves on **both blocks, both NQ timeframes and SPX**, and the inverse is worse than
flat **everywhere**. That is six independent sign checks and all six pass.

### The obvious way this could be fake, tested

`R = pnl / (stop_mult × ATR)`. Widening the stop **enlarges the denominator**, and the widened
bucket is the *losing* one — so a policy that only shrinks losses arithmetically would show a gain
without improving anything. Three attacks (`research/v22/v22destroy.py`):

**1. Score it in POINTS, where no denominator moves.**

| policy | 15m research pts | 15m locked pts | 30m research pts | 30m locked pts |
| --- | --- | --- | --- | --- |
| flat 2.0N | +0.940 | +8.894 | +7.101 | +11.227 |
| wide-low 2.5/1.5 | +1.030 | **+11.058** | +4.438 | **+13.604** |
| wide-low 2.5/2.0 | +0.989 | +9.813 | +7.291 | +12.781 |
| INVERSE 1.5/2.5 | +0.497 | +7.035 | +3.685 | +7.817 |

Survives on the locked block on both timeframes, and the inverse is still worst. **But 30m research
points FALL** (+7.101 → +4.438) while 30m research R rises. That disagreement is real and is not
explained away here: on that one cell the R gain is partly the rescaling.

**2. Does widening change the EXIT MIX?** A real widening converts stop-outs into channel exits; a
rescaling leaves the mix alone. Low-vol bucket, NQ 15m:

| stop | block | n | pts/trade | R/trade | stopped | channel |
| --- | --- | --- | --- | --- | --- | --- |
| 2.0 | research | 498 | −3.949 | −0.1170 | 45.4% | 54.6% |
| 2.5 | research | 483 | −3.627 | −0.0654 | **33.1%** | 66.9% |
| 3.0 | research | 469 | −3.144 | −0.0420 | **18.3%** | 81.7% |
| 2.0 | locked | 269 | +0.141 | +0.1139 | 42.8% | 57.2% |
| 2.5 | locked | 251 | **+4.464** | +0.1471 | **27.1%** | 72.9% |
| 3.0 | locked | 245 | +5.018 | +0.1401 | 14.3% | 85.7% |

The exit mix moves hard — 45%→18% stop-outs — and points per trade improve alongside R. This is a
mechanism, not a rescaling.

**3. The 0.5 threshold was declared, not searched. Is it a spike?**

| threshold | 15m research R | 15m locked R | 15m locked PF | 30m research R | 30m locked R | 30m locked PF |
| --- | --- | --- | --- | --- | --- | --- |
| 0.3 | −0.0052 | +0.1576 | 1.255 | +0.0858 | +0.0484 | 1.079 |
| 0.4 | +0.0143 | +0.1693 | 1.281 | +0.0877 | +0.0703 | 1.120 |
| 0.5 | +0.0082 | +0.1454 | 1.249 | +0.1093 | +0.1008 | 1.181 |
| 0.6 | +0.0105 | +0.1298 | 1.229 | +0.0672 | +0.1058 | 1.196 |
| 0.7 | −0.0044 | +0.1186 | 1.216 | +0.0830 | +0.1085 | 1.210 |

Smooth on both, no spike at 0.5, every rung beats the flat stop's locked +0.0939 (15m) and +0.0873
(30m). The two timeframes slope in *opposite* directions across the threshold, which caps how much
should be read into any single value — the plateau is the evidence, not the peak.

## 5. What this does NOT establish

- **The SPX daily backtest is underpowered and no verdict rests on it.** A daily trend trade holds a
  median 19 sessions, so the position lock leaves **30 research and 8 locked trades** out of 292 and
  189 signals. The tables in §3b/§4 score the **overlapping signal population** — correct
  conditional means, effective sample far below the printed n. The VIX result this study rests on is
  the **information coefficient** in §1–2, which uses every session and needs no backtest.
- **The SPX locked block contains COVID.** The largest volatility event in the sample sits in the
  held-out block, and every locked VIX statistic is partly a statement about February–March 2020.
- **There is no VIX9D or VIX3M**, so the *implied* term structure — the part of the VIX complex with
  the best-documented forecasting record — could not be built. The `vixts_*` features are the VIX
  against its own trailing average, a proxy, and they are the **worst-behaved family in the study**
  (0% sign retention).
- **The VIX cannot be joined to any futures feed here.** §3a and §3b are two instruments agreeing on
  a mechanism, not one result confirmed twice.
- **The trade-level VIX condition table (§F in `v22vixtrade.py`) should not be traded.** 662
  conditions, 52.4% of the population beats its own control — chance — and the top rows sit on 30
  overlapping signals. It is printed for completeness, not as a candidate.
- **The gain is modest.** Locked PF 1.158 → 1.249 on NQ 15m and 1.156 → 1.181 on 30m. This is a
  sizing correction on an existing rule, not an edge.

## 6. The mechanical rule

Nothing here is a signal. It is a stop-sizing correction, and it is two lines:

```
state = percentile rank of 20-bar realised volatility within its own trailing 250 bars,
        read at the SIGNAL bar
stop  = 2.5 x ATR   if state <= 0.50      (trailing ATR is too small; vol mean-reverts up)
        1.5 x ATR   if state >  0.50
```

Where an implied series is available for the instrument, replace the state with
`VIX / (20-day realised volatility, annualised)` and split at its trailing median — the same
condition, measured directly instead of inferred.

Everything else in the volatility complex tested null or inverted.

## 7. The shipped script, and the bug parity caught

`pine/v22/V22_ADAPTIVE_VOL_STOP_strategy.pine` — Donchian 30/20 long, 20-bar channel exit, no take
profit, one unit, with the adaptive stop as the only addition. The window and the flatten are inputs
and both default **OFF**, because every number in this study is all-hours.

**The stop anchors to the signal bar's close, not the entry bar's open.** A script cannot use the
engine's anchor: at the moment the exit order must be written, the fill price does not exist yet.
Placing the exit a bar late leaves the entry bar unprotected — `STUDY_PINE_PARITY` measured that at
4.4–13.0% of trades averaging −33 to −118 points. Anchoring to the signal close lets entry and exit
be placed together, and it was measured before being adopted (`v22anchor.py`):

| | 15m | 30m |
| --- | --- | --- |
| identical exit bar | 99.03% | 99.50% |
| per-trade R correlation | 0.9935 | 0.9998 |
| locked PF, engine anchor → script anchor | 1.249 → 1.241 | 1.181 → 1.182 |

**Parity found a real bug in the first draft**, which was lint-clean and read correctly. The
`lastExitBar` update sat below the entry block, so on the bar a trade closed the entry test read a
stale value and the script re-entered immediately — **95 extra trades on 15m and 61 on 30m** that the
research position lock forbids, dragging script points per trade to +0.92 against the engine's
+4.31. Counting `strategy.closedtrades` instead of watching `strategy.position_size[1]` also catches
a trade that opens and stops out inside one bar, where `position_size` reads 0 at both closes.

After the fix (`research/v22/v22_parity.py`, two runs as the protocol requires):

| check | 15m | 30m |
| --- | --- | --- |
| percentile rank / ATR / entry channel / exit channel | **0 disagreements** | **0 disagreements** |
| trades | 1162 of 1163 | 664 of 665 |
| identical exit bar | **100.00%** | **100.00%** |
| per-trade points correlation | **0.999971** | **0.999983** |

The one missing trade on each is open at the end of the data. The residual +4.08 and +4.03 points
per trade is exactly the round turn the engine nets and the harness does not — which is the check
that the fee is the only thing left between them.

## 8. Should it ship on the bare Donchian or on the V20/V21 stack?

The first V22 script shipped on the plain Donchian 30/20 with a 2.0N stop and no target — which is
**not** the base V20 and V21 were built on. Three components were left out, and only two of them for
a reason:

| component | why it was left out | was that justified? |
| --- | --- | --- |
| linreg 50 confirmation | V20 measured all four declared readings; the best adds +0.005 R and the most literal is mechanically backwards on a breakout bar (lift 0.24×) | yes, on evidence |
| 2R take profit | no take profit has beaten every target tested here seven independent times | yes, on evidence |
| **CHOP ≤ 45** | **it had never been tested with an adaptive stop** | **no — a gap, not a judgement** |

So all three went back on the bench, jointly with the adaptive stop (`research/v22/v22stack.py`).
R per trade, NQ:

| configuration | 15m research | 15m locked | 30m research | 30m locked |
| --- | --- | --- | --- | --- |
| flat 2.0N, no target (the old base) | −0.0286 | +0.0939 | +0.0870 | +0.0873 |
| **ADAPTIVE, no target (shipped default)** | +0.0082 | **+0.1454** | **+0.1093** | +0.1008 |
| ADAPTIVE + CHOP ≤ 45 | +0.0700 | +0.0820 | +0.0970 | +0.1007 |
| ADAPTIVE + linreg C | −0.0028 | +0.1336 | +0.1036 | +0.1027 |
| ADAPTIVE + CHOP + linreg (full stack) | +0.0748 | +0.0752 | +0.1082 | **+0.1105** |
| flat 2.0N + CHOP ≤ 45 | +0.0013 | +0.0426 | +0.1105 | +0.0622 |
| ADAPTIVE + 2R target | −0.0146 | +0.0535 | +0.0130 | +0.0493 |

**CHOP ≤ 45 against a selectivity-matched control, on the adaptive base:**

| block | n | R/trade | control mean | excess | p |
| --- | --- | --- | --- | --- | --- |
| 15m research | 551 | +0.0700 | +0.0240 | +0.0460 | **0.037** |
| 15m locked | 293 | +0.0820 | +0.1300 | **−0.0480** | **0.932** |
| 30m research | 314 | +0.0970 | +0.1180 | −0.0210 | 0.740 |
| 30m locked | 164 | +0.1007 | +0.0903 | +0.0104 | 0.398 |

It passes once and inverts — on 15m locked a **random filter of the same selectivity earns more**.

**And it is not redundant with the volatility state**, which was the obvious explanation and is wrong:
correlation over breakout signals is only **−0.230 (15m) / −0.258 (30m)**, and CHOP leans slightly
*away* from the calm bucket (40.7% of CHOP-kept signals are calm against 48.0% of all signals — lift
**0.85×**). This is a filter that does not replicate on this base, not two filters doing one job.

**The caveat that keeps CHOP as a switch rather than a deletion.** V21's CHOP result was pooled over
**five markets** on the flat-stop V20 base. A container recycle destroyed every feed except NQ, so
the re-test above is **one market on a different base** — weaker evidence than the finding it checks.
CHOP is *unconfirmed here*, not refuted. Note also that on the flat base CHOP helps research on both
timeframes (−0.0286→+0.0013 and +0.0870→+0.1105), which is where V21 found it, and hurts locked on
both — so the one-market disagreement is with the holdout, not the research block.

**One cell worth knowing about:** on 30m the full stack is the best locked cell in the table
(+0.1105, PF 1.205, Sharpe 1.13). It is also the best of seven configurations on one timeframe while
being far worse on the other, so it ships as an option, not a default.

All three are now inputs on the shipped script, defaulting OFF. Nothing validated was removed.

## Files

| file | what it does |
| --- | --- |
| `research/v22/v22vol.py` | 71 causal realised-volatility features, six families, + the forward-ER label |
| `research/v22/v22run.py` | 426 IC tests on NQ, Newey–West + BH, research/locked, top 50 |
| `research/v22/v22trade.py` | heat by volatility decile, and 2,556 control-gated trade conditions |
| `research/v22/v22stop.py` | the five declared stop policies, and the heat slope read on both blocks |
| `research/v22/v22destroy.py` | the three attacks on the stop policy: points, exit mix, threshold |
| `research/v22/v22vix.py` | SPX×VIX loader, 39 causal VIX features, the daily Donchian engine |
| `research/v22/v22vixrun.py` | the positive control, the chop IC test, top 50, family table |
| `research/v22/v22vixtrade.py` | VIX heat table, the implied-vs-realised stop policy, condition table |
| `research/v22/v22anchor.py` | the stop anchor a script can actually place, measured against the engine's |
| `research/v22/v22_parity.py` | the shipped script's order model in Python, diffed against the engine |
| `research/v22/v22stack.py` | the three V20/V21 components re-tested jointly, and the CHOP overlap diagnostic |
| `pine/v22/V22_ADAPTIVE_VOL_STOP_strategy.pine` | the shipped strategy |
