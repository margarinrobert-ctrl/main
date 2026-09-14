# V43 — MAE and MFE across every declared Donchian configuration

**MAE is the right statistic for entry heat. Measured without the stop censoring it, the shipped
CHOP ≤ 40 configuration has the lowest of any tradeable configuration here — and every breakout
still takes more heat than a random bar in the same regime.**

Eight declared Donchian long breakouts, NQ, ATR stop and channel exit, no take profit, one unit.
`research/v43/v43_maemfe.py`, `v43_uncensored.py`, `v43_exitbar.py`.

---

## 1. Two artifacts sit between MAE and a cross-configuration comparison

Both are the stop, and neither is a defect in the measure.

**MAE in R is the stop multiple in disguise.** R is `atr_mult × ATR`, so the stop is the
*denominator*. The same trade at 2.5N reports 20% less heat than at 2.0N. Ranking by MAE-in-R
ranks by stop width, and the ordering inverts when you divide by ATR instead:

| config | stop | MAE in R | rank | MAE in ATR | rank |
| --- | --- | --- | --- | --- | --- |
| V40 40/25 MA200-distance | 1.5N | 1.306 | **8th (worst)** | 1.958 | **2nd (best)** |
| V38 70/30 (geometry only) | 2.5N | 0.926 | 3rd | 2.316 | **8th** |

**And the stop censors the excursion itself.** A trade heading for −3.0 ATR that is stopped at
−2.0 ATR records −2.0. So a mean MAE mixes real heat on survivors with the stop distance on the
stopped, weighted by the stop-out rate — which runs **19% to 62%** across these eight.

The censoring is measurable. The exit bar contributes **1.7% of MFE and 42.6% of MAE**, because on
a stopped-out trade the exit bar is where the worst excursion happened by construction; and across
the eight configurations **stop-out share correlates +0.978 with mean MAE**. Removing the exit bar
is *not* a repair — it discards real adverse excursion and is biased low. The repair is to stop
censoring, which is what `STUDY_M4_ANATOMY` already prescribed for barrier systems: widen the stop
until it cannot bind, then read the distribution.

---

## 2. Uncensored entry heat — the measurement that answers the question

All figures in **ATR at entry**, never in R (dividing by risk puts the stop back in the
denominator). Two uncensored views: the configuration's own entry and channel exit with the stop
set where it cannot bind; and a **fixed 20-bar horizon from each real entry with no exit at all**,
which removes the last asymmetry — a longer exit channel gives a trade more time to draw down.

| config | tf | declared (censored) | no stop | **h20 MAE** | h20 MFE | h20 ratio |
| --- | --- | --- | --- | --- | --- | --- |
| **V42 SPEC 20/55** | 240 | 1.517 | **1.588** | **2.309** | 2.812 | **1.218** |
| **V24 shipped CHOP≤40** | 30 | 1.884 | **2.449** | **2.990** | 3.140 | **1.050** |
| V21 CHOP≤45 | 30 | 2.011 | 2.553 | 3.090 | 3.201 | 1.036 |
| V38 70/30 (geom) | 30 | 2.295 | 2.738 | 3.181 | 2.803 | 0.881 |
| V12 30/20 ADX≥25 | 15 | 1.936 | 2.555 | 3.219 | 3.266 | 1.014 |
| V11 55/20 2.5N ADX≥25 | 15 | 2.135 | 2.616 | 3.363 | **3.440** | 1.023 |
| base 30/20 unfiltered | 30 | 2.036 | 2.484 | 3.405 | 3.197 | 0.939 |
| V40 40/25 1.5N MA200d | 15 | 1.924 | **3.122** | **3.705** | 3.373 | 0.911 |

**The spread is larger uncensored than censored — 1.534 ATR against 0.779.** The stop was
compressing the differences between these entries, not creating them. V40 is the clearest case:
its 1.5N stop made it look mid-table as declared (1.924) and it is the *worst* entry in the set
once the stop stops truncating (3.122 / 3.705).

---

## 3. Against a random bar in the same regime

Fixed 20-bar horizon, no exits, random bars drawn from the same gated population, matched on count,
200 draws. With no stop and a fixed horizon, nothing differs between the two except *when* they
enter.

| config | MAE | control | Δ | p | MFE | Δ | ratio | c_ratio | **Δratio** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V42 SPEC | 2.309 | 2.585 | **−0.276** | **0.165** | 2.812 | −0.004 | 1.218 | 1.089 | **+0.128** |
| V24 shipped CHOP≤40 | 2.990 | 2.747 | +0.243 | 0.975 | 3.140 | +0.520 | 1.050 | 0.954 | **+0.096** |
| V21 CHOP≤45 | 3.090 | 2.846 | +0.244 | 0.955 | 3.201 | +0.514 | 1.036 | 0.944 | +0.092 |
| V11 ADX≥25 | 3.363 | 2.871 | +0.493 | 1.000 | 3.440 | +0.722 | 1.023 | 0.947 | +0.076 |
| V12 ADX≥25 | 3.219 | 2.879 | +0.340 | 0.990 | 3.266 | +0.554 | 1.014 | 0.942 | +0.073 |
| base unfiltered | 3.405 | 3.015 | +0.390 | 0.990 | 3.197 | +0.373 | 0.939 | 0.937 | **+0.002** |
| V38 (geom) | 3.181 | 3.005 | +0.176 | 0.825 | 2.803 | −0.049 | 0.881 | 0.949 | −0.068 |
| V40 MA200d | 3.705 | 2.835 | **+0.869** | 1.000 | 3.373 | +0.499 | 0.911 | 1.014 | **−0.103** |

**Seven of eight breakouts take MORE adverse excursion than a random bar in the same regime**, at
p 0.825–1.000. The mechanism is not mysterious and the branch has measured it from the other side:
a breakout bar enters at the top of its own range, so price retraces into the position immediately
— `research/atme/` found a stop entry degrades monotonically with distance while a limit entry
improves, and called chasing a breakout the most reliably destructive choice in that search.

**They also get more MFE**, so the question is the ratio — and there the result separates:

- **The unfiltered base gets +0.002.** In an unconditional population the breakout buys extra heat
  and extra excursion in equal measure and the ratio does not move. The trigger, alone, is nothing.
- **Every regime-filtered configuration gets +0.073 to +0.096.** Inside CHOP ≤ 40 or ADX ≥ 25 the
  same trigger converts more excursion than heat.
- **V40 and V38 are negative.** V38's MFE is actually *below* its control (−0.049).

That is `STUDY_V21`'s conclusion reached from the excursion side rather than from P&L: the filter
is what makes the breakout worth taking, and CHOP is the filter that does it.

---

## 4. The answers

**Lowest MAE: V24 shipped, CHOP ≤ 40** — 2.449 ATR uncensored, 2.990 at a fixed 20-bar horizon,
lowest median too (1.815). It beats the unfiltered base it is built on (2.484 / 3.405), so the
filter genuinely reduces entry heat rather than just trading less. V42 SPEC is lower still (1.588 /
2.309) and is the only configuration that takes *less* heat than its control — but it is **n = 60**
on 240-minute bars, a different animal from the intraday rows, and under-powered.

**Highest MFE: V11 55/20 ADX≥25** at a fixed horizon (3.440 ATR), which is also the longest-held of
the 15-minute rows at 28–32 bars. On natural life with no stop it is **V40** (4.698) — and V40 is
simultaneously the worst MAE, so it is not a favourable entry, it is a volatile one.

**Best on the only unit-free measure — MFE/MAE against its own control — is V24 shipped** (+0.096),
which is the configuration already shipped.

**What is actually usable:** stop-out rate drives declared MAE at ρ 0.978, so if the goal is less
heat the lever is the stop multiple and the regime filter, not the channel length and not the
entry. A restatement of `STUDY_V18_COINT_EWMAC`'s monotone stop axis and `STUDY_V22`'s adaptive
stop, reached from the excursion side.

## Caveats

One market (NQ). No bootstrap on the Δ columns — they are point estimates; the control's `p` is a
draw-share, not a hypothesis test with a multiplicity correction over eight configurations. V38 is
run as **geometry only**, without its LRMA/MA stack, so that row is not V38. V42 runs with the
**ladder off** so it is comparable to the one-unit rows; it ships with four units, which changes
the fill the excursions anchor to. The fixed-horizon trade set still comes from each
configuration's own position-locked entries, so the entry *sets* differ even though the horizon
does not.

## Files

`research/v43/v43_maemfe.py` · `v43_uncensored.py` · `v43_exitbar.py` ·
`results/v43/v43_maemfe.csv`, `v43_uncensored.csv`, `v43_uncensored_control_h20.csv`,
`v43_exitbar.csv`, `v43_exitreason.csv`.
