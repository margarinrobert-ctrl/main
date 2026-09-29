# The section-12 rule, frozen and run on four markets that had no part in finding it

`STUDY_US30_SCALP_0711` section 12 derived a rule from three agents' component findings rather than
searching for one — **Donchian 20 long, entries 07:00-11:00 New York, flat at the 11:00 open, a
50-point stop and a 150-point target**, with five arms of which `conventional (+ema align +adx>=25)`
is the arm that must lose if the ADX inversion is real. On US30 it is positive on all six research /
holdout / forward cells and **inside its own MDE in every one of them**: confirmed in direction,
unproven in size. Section 12 also named the binding constraint exactly — 1,073 trades at 80% power
against 400 in hand.

Running it on markets that chose nothing is therefore two things at once: the strongest validation
available, and the only route to more events. This is that execution. **98 declared cells, no
sweep, one read each.** `research/us30xmkt/`, figure `docs/ib/team_xmkt.png`.

**The short answer: the frozen rule does not survive contact with four fresh markets, and the two
traps the brief named are both live.** Pooled over 4,893 trades on four markets the base rule earns
**−0.0455 ATR a trade against an MDE of 0.0993** — the power target was hit (the MDE fell 1.68x
from US30's own 0.1606 at this geometry, and PF 1.2 is inside resolution for the first time) and the
edge went negative rather than shrinking. Of the two pre-declared component findings, **the ADX ceiling does not
replicate (5 of 14 cells, 0 of 4 markets) and the EMA alignment weakly does (9 of 14, 2 of 4)** —
and the arm that had to lose beat its base more often than either (10 of 14). A third condition
handed over mid-run by the rate workstream, `ema34>ema89`, is the best-travelling object in the
study at **10 of 14 with a +0.029 ATR mean edge**, and the fast half of the same stack, `ema13>34`,
is **actively harmful at 2 of 14 and −0.050**.

---

## 1. The feeds, the clocks re-derived, and the parity assertion

`python research/datasets.py` first. Five feeds, all verified on disk; three clocks re-derived from
the branch's standing positive control (mean bar range by minute-of-day must peak at 570 = 09:30
New York) and gold's read against **its own 08:30 anchor**, because gold does not key on the equity
open:

| market | source | bars | span (New York) | sessions | range peak | reads |
|---|---|---|---|---|---|---|
| US30 | `US30_LONG_15m` | 193,942 | 2016-10-26 → 2025-07-15 | 2,704 | **570** | 09:30 ✓ |
| US100 | `US100_LONG_15m` | 206,703 | 2016-11-14 → 2025-10-01 | 2,747 | **570** | 09:30 ✓ |
| NQ | `NQ_1m` → 15m | 70,685 | 2022-12-26 → 2025-12-11 | 923 | **570** | 09:30 ✓ |
| XAU | `XAU_ISO_15m`, pre-2010 excluded | 371,586 | 2010-01-03 → 2026-01-30 | 4,958 | **510** | 08:30 ✓ |
| US30I | `US30_ISO_15m` | 48,937 | 2024-08-19 → 2026-08-26 | 632 | **570** | 09:30 ✓ |

`NQ_1m` is stamped in UTC and every other feed here is already New York; it is loaded through
`nqdata.load_bars` and the tz dropped. A peak at minute 270 would have meant the conversion had not
happened.

**Blocks.** US30 keeps `mr30core`'s published cut so the parity assertion is exact. US30I is the one
forward block (2025-07-16 on, 349 sessions). Every other market splits at its own first 70% of
sessions — **both halves are out of sample**, since these markets chose nothing, so the split
reports consistency and selects nothing.

**PARITY.** The section-12 kernel is COPIED into `xm_core.py`, not parameterised (`STUDY_V60`: a
frozen kernel is copied and asserted against its original, never given new arguments three published
studies would silently inherit). `run_x1.py` asserts it before any other market is read:

- the three masks (`adx<=20`, `adx>=25`, `ema align`) are **identical on all 193,928 bars**;
- Wilder ADX **max |diff| 0.000e+00**;
- all ten US30 cells reproduce **exactly** on trade count, entry bar, exit bar and points —
  `+adx<=20` reads **+6.260 research / +4.596 holdout**, the published figures to the cent.

---

## 2. Cost as a fraction of the stop — and why a point barrier is five different trades

The frozen 50/150 is expressed two ways: **literally in each market's own points** (which is a
different trade on every market) and at the **matched ATR multiple** fixed on US30's own in-window
research median ATR, 50/31.00 = **1.6127N** and 150/31.00 = **4.8380N** (which is the same trade).
Research-block, in-window medians:

| market | median price | median ATR(14) | round turn | **50 pts is** | cost/risk PTS | matched stop in pts | **cost/risk ATR** |
|---|---|---|---|---|---|---|---|
| US30 | 26,547 | 31.19 | 2.29 | 1.60N | 4.58% | 50.3 | **4.55%** |
| US100 | 8,313 | 13.65 | 1.215 | **3.66N** | 2.43% | 22.0 | **5.52%** |
| NQ | 18,924 | 22.83 | 1.72 | **2.19N** | 3.44% | 36.8 | **4.67%** |
| XAU | 1,312 | 2.044 | 0.30 | **24.47N** | 0.60% | 3.30 | **9.10%** |
| US30I | 48,389 | 53.31 | 2.29 | **0.94N** | 4.58% | 86.0 | **2.66%** |

**A fixed 50-point stop is a 24.5 ATR stop on gold and a 0.94 ATR stop on the ISO Dow feed — a
factor of twenty-six.** That is `TEAM_POOLED_WINDOW`'s 0.97N-vs-2.20N finding at its extreme and
`STUDY_TURTLE_15M`'s error (NQ's round turn charged in gold's points) in its cross-market form. Any
points figure compared across these five feeds is measuring the price level.

**Gold's cost floor is about 2x the indices', not 3x, once expressed as a fraction of its own
stop** — 9.10% against 4.55-5.52% — because the matched ATR geometry scales the stop with gold's
own volatility. The registry's ~3x is a statement about a scalping stop, and this is not one.

---

## 3. The overlap matrix — measured before any market is called independent

Donchian-20 long, in-window, over each pair's contemporaneous span. The share of the row market's
signal bars that are also the column market's **at the identical timestamp**:

| pair | shared days | n(a) | n(b) | same bar a→b | b→a | ±2 bars a→b |
|---|---|---|---|---|---|---|
| **US100 / NQ** | 423 | 1,252 | 1,201 | **81.9%** | **85.4%** | **93.7%** |
| **US30 / US30I** | 137 | 376 | 385 | **91.2%** | **89.1%** | **95.7%** |
| US30 / US100 | 1,023 | 3,267 | 3,665 | 43.3% | 38.6% | 65.0% |
| NQ / US30I | 158 | 577 | 584 | 37.3% | 36.8% | 55.8% |
| US30 / NQ | 302 | 1,042 | 1,136 | 34.8% | 32.0% | 58.7% |
| US100 / US30I | 133 | 515 | 464 | 34.0% | 37.7% | 54.2% |
| **XAU / everything** | 114-782 | — | — | **9.1-14.5%** | — | 23.8-34.7% |

Daily leg correlation on the base arm, ATR units, over shared dates: **US100/NQ +0.879**,
**US30/US30I +0.922**, US30/US100 +0.276, US30/NQ +0.203, and **XAU against all four −0.010 to
+0.248**. `STUDY_TREND_LONG`'s objection applies twice here: there are not five markets, there are
**three objects — the Dow (two feeds), the Nasdaq (two feeds), and gold.**

**Effective sample size**, from a standard error clustered on the calendar date across markets:

| pooled set | nominal n | **effective n** | retention | SE inflation |
|---|---|---|---|---|
| all four fresh markets | 4,893 | **3,865** | 79.0% | 1.14x |
| de-duplicated (US30I + US100 + XAU) | 4,301 | **4,134** | 96.1% | 1.02x |

**Adding NQ to US100 adds 592 trades and REMOVES 269 effective ones.** A second feed of the same
index does not merely fail to add power — pooled with date clustering it subtracts it, because the
duplicated trades inflate the cluster sums without adding independent dates. That is the sharpest
form the branch's standing warning has taken, and it is why the de-duplicated set has the smaller
MDE (0.0957) despite having 592 fewer trades.

---

## 4. The two pre-declared hypotheses, read exactly as declared

Declared in `run_x3.py`'s docstring before any of these markets was read.

> **H1 THE ADX INVERSION.** `adx<=20` beat its block's base in 12 of 12 US30 cells. PASS on a market
> := `+adx<=20` > `base` in every block at both parameterisations. Reported per cell against a 50%
> chance rate.
> **H2 THE EMA ALIGNMENT.** `ema13>34>89` was positive 6/6 on US30. Same pass criterion.
> **H3 THE ARM THAT MUST LOSE.** If the inversion is real, `conventional` must be beaten by both of
> its own components separately.

| arm | cells beating base | chance | markets passing | cells positive |
|---|---|---|---|---|
| **H1 `+adx<=20`** | **5 / 14 (35.7%)** | 50% | **0 of 4** | 6 / 14 |
| **H2 `+ema align`** | **9 / 14 (64.3%)** | 50% | **2 of 4** (US100, US30I) | 4 / 14 |
| `+both` | 7 / 14 (50.0%) | 50% | 0 of 4 | 7 / 14 |
| **H3 `conventional`** | **10 / 14 (71.4%)** | 50% | 1 of 4 | 6 / 14 |

**H1 fails.** `+adx<=20` beats its base on 0 of 4 markets and 5 of 14 cells — below chance. On the
markets individually it is 1/4 on NQ, 1/4 on US100, 2/4 on XAU, 1/2 on US30I.

**H2 is weakly consistent**, 9 of 14 with US100 4/4 and US30I 2/2, but it is positive in only 4 of
14 cells: on most of these markets it is a smaller loss, not a profit.

**H3 is falsified in the wrong direction.** The arm placed in the table *because it had to lose*
beats its base more often than any other arm, and on the three "A" blocks (US100, NQ, XAU) it is the
**best of the five arms** in ATR units. That is not evidence that `adx>=25` works; it is evidence
that the ADX axis carries nothing here in either direction, and that the 12/12 US30 record was a
property of that market, that block and that unit.

**And the rate workstream reached the same place from the other side while this was running**
(sections 14-15): the 12/12 ADX record was measured at **entry channel 20 only**, and varying the
channel takes `+adx<=20` to 15 of 18 cells against its own same-selectivity null but only **3 of 6
on the reserved forward feed** (median p 0.617), while `+ema align` is 18 of 18 including 6/6 there.
Two independent attacks — a different channel on the same market, and the same channel on different
markets — say the same thing about which half of the section-12 rule is load-bearing.

**Base rates first, so none of this is a selectivity artifact** (`run_x5.py`). ADX is a ratio and is
scale-free, so unlike an ATR percentile a fixed threshold really is the same filter everywhere: the
median ADX on breakout bars is **24.8-26.8 on all five feeds**, `adx<=20` keeps **22.4-27.8%** of
signals and `ema align` passes **60.2-72.5%** (lift 1.53-1.67) — binding on every market, and
nowhere near the 84-95% pass rates that make a confirmation the trigger restated. The
`STUDY_MR30` kept-share-drift failure mode is not available here. And `rho(adx<=20, ema align)` on
the signal bars runs **−0.118 to +0.076** across all nine market-blocks, reproducing US30's −0.1185:
they are two genuine axes everywhere, which is why they were worth stacking and why the stack's
failure is informative.

---

## 5. The third condition, handed over mid-run — and it is the one that travels

**Provenance, stated so it cannot be misread.** H1 and H2 above were declared before any read and
are reported as declared whatever follows. `ema34>ema89` arrived *after* that read, from
`research/us30rate/` (sections 14-15), which varied the entry channel on US30 and found the EMA
stack to be one inequality. It is therefore a **weaker pre-declaration** than H1/H2 — but the
evidence behind it is all US30, and these four markets chose none of it, so the read is genuinely
out of sample. 28 further declared cells (`run_x8.py`).

| arm | beats base | positive | beats the FULL alignment | mean edge (ATR/trade) |
|---|---|---|---|---|
| **`+ema34>89`** | **10 / 14** | 6 / 14 | **9 / 14** | **+0.0291** |
| `+ema align` (as declared) | 9 / 14 | 4 / 14 | — | +0.0198 |
| `+adx<=20` | 5 / 14 | 6 / 14 | 5 / 14 | +0.0041 |
| **`+ema13>34`** | **2 / 14** | 3 / 14 | 2 / 14 | **−0.0498** |

**The rate workstream's decomposition replicates on four fresh markets: the slow half is the whole
condition and the fast half is negative.** `ema13>34` alone beats its base in 2 of 14 cells with a
mean edge of −0.050 ATR — worse than any other arm in the study — while `ema34>89` alone beats the
full three-EMA alignment in 9 of 14. On US30's own blocks the same ordering holds
(`+ema34>89` +0.1335/+0.0018 against `+ema13>34` +0.0942/−0.1418 in ATR units).

That is the one component finding this workstream can report as reproducing. It is still small:
+0.029 ATR a trade against a pooled MDE of 0.099.

---

## 6. The pooled read, and the MDE — the number this workstream exists to move

Pooled in ATR units at the matched geometry, standard errors clustered on the calendar date across
markets:

| set | n | n_eff | mean (ATR/trade) | **MDE at 80% power** | ratio | PF |
|---|---|---|---|---|---|---|
| **US30 alone, this geometry** | 1,546 | 1,561 | **+0.0381** | **0.1606** | 0.24 | 1.036 |
| US100 | 1,712 | 1,711 | −0.0264 | 0.1515 | −0.17 | — |
| NQ | 592 | 569 | −0.0810 | 0.2655 | −0.31 | — |
| XAU | 2,349 | 2,332 | −0.0864 | 0.1237 | −0.70 | — |
| US30I (forward) | 240 | 228 | **+0.3050** | 0.4601 | 0.66 | 1.354 |
| **de-duplicated 3** | 4,301 | **4,134** | **−0.0406** | **0.0957** | −0.42 | 0.956 |
| **all four** | 4,893 | 3,865 | **−0.0455** | **0.0993** | −0.46 | 0.951 |

**The power target was met and the effect was not there.** The MDE fell from US30's **0.1606 to
0.0957 ATR a trade — a 1.68x improvement** (against `TEAM_POOLED_WINDOW`'s 0.1849 on its own
consensus cell, which is a different geometry) — and what the pooled sample can now resolve is
exactly the bar the window has to clear:

| | required edge (from the pooled population's own win/loss magnitudes) | vs pooled MDE 0.0993 |
|---|---|---|
| PF 1.1 | +0.0882 | 0.89x — **just outside** |
| **PF 1.2** | **+0.1700** | **1.71x — INSIDE RESOLUTION** |
| PF 1.5 | +0.3836 | 3.86x — inside |

**A PF-1.2 rule in this window is now detectable across four markets, and there is not one.** The
measured pooled edge is −0.0455, and detecting an effect of the observed size at the observed
dispersion would take **23,282 trades**. `TEAM_POOLED_WINDOW`'s finding reproduces on a wider set
and with a better MDE: the error bar shrank 1.7x and the mean fell from US30's +0.038 to −0.046, so
the t-statistic got *worse*, and this time it changed sign.

**Nulls.** Of the 70 cells, **0 are outside their own MDE**, 27 of 70 are positive, and **6 of 70
clear a matched random entry at p ≤ 0.05 against 3.5 expected by chance** — and two of those six are
cells where the rule loses money and merely beats a null that loses more (XAU A base −0.1043 against
a control median of −0.1892). Four cells clear a day-block bootstrap against zero. **The control
median is negative in 60 of 70 cells**: a random long entry in this window with this geometry loses
money on essentially every market and block here, which is the context any "clears its control"
claim on this branch needs printed beside it.

The one cell that looks like something is **US30I `+ema align`: +0.4403 ATR, PF 1.538, control
p 0.0325, bootstrap 0.0147 on 150 trades** — on the feed that is 91% duplicated with US30 and was
already read once as section 12's C_forward. It is a second read of a known block, and its MDE is
0.5874 against a mean of 0.4403.

---

## 7. The unit problem — section 12's headline is a points figure

x3 turned up something the section-12 tables could not show, because they were scored in points.
On US30's research block, on the same trades and the same geometry:

| unit | base | `+adx<=20` | verdict |
|---|---|---|---|
| points per trade (§12's unit, §12's parameterisation) | +0.956 | **+6.260** | arm wins by +5.30 |
| **ATR units per trade** | **+0.0493** | **+0.0359** | **arm LOSES by 0.013** |
| points per trade, matched ATR geometry | +3.406 | **+9.056** | arm wins by +5.65 |
| **ATR units, matched ATR geometry** | **+0.0841** | **+0.0339** | **arm LOSES by 0.050** |

Over all 72 arm × market × block × parameterisation comparisons the two units disagree in **10
(13.9%)**, and `+adx<=20` is the arm they disagree about most — **11 of 18 beating base in points
against 7 of 18 in ATR units** — with **both** of US30's research cells among the disagreements.
`+ema align` is the most unit-robust arm (15/18 vs 13/18, 2 disagreements).

The mechanism is a weighting one, not a denominator collapse: `adx<=20` selects **calmer** bars
(median ATR at the signal bar 0.894x the base's, below 1.0 on **9 of 9** market-blocks), and its
point advantage is carried by the minority of high-ATR trades — on US30's four cells
`rho(ATR at signal, points)` inside the ADX arm is **+0.085 / +0.170 / +0.100 / +0.219, positive in
all four**, against **−0.040 / +0.005 / +0.032 / −0.247** for the base. Weight every trade
equally at constant risk and the advantage is not there. This is `STUDY_V63`'s "the stop axis gives
three different answers in three units" asked of a **filter** rather than a geometry, and the answer
is the same: report both, and never let a points figure stand alone across markets or across eras.

It does not make section 12 wrong on its own terms — one contract on US30, `+adx<=20` did earn
+6.26 points a trade — but it does mean the arm's advantage is a statement about which bars carry
the most volatility, and it is why the same arm is 5 of 14 everywhere else.

---

## 8. Gross against net — cost is not the objection, except on gold

`run_x9.py`, at the matched geometry, cost entering as `round turn / ATR at the signal bar`:

| market | block | n | **gross** | cost | **net** | gross PF |
|---|---|---|---|---|---|---|
| US30 | A research | 1,058 | +0.1822 | 0.0981 | +0.0841 | 1.220 |
| US30 | B holdout | 488 | +0.0027 | 0.0644 | −0.0617 | 1.003 |
| US100 | A | 1,178 | +0.0942 | 0.1389 | −0.0447 | 1.110 |
| US100 | B | 534 | +0.0687 | 0.0546 | +0.0141 | 1.076 |
| **NQ** | A | 419 | **−0.0023** | 0.0806 | −0.0830 | 0.998 |
| **NQ** | B | 173 | **−0.0171** | 0.0592 | −0.0763 | 0.980 |
| XAU | A | 1,570 | +0.0588 | 0.1631 | −0.1043 | 1.072 |
| XAU | B | 779 | +0.0502 | 0.1004 | −0.0502 | 1.058 |
| US30I | C forward | 240 | +0.3523 | 0.0473 | +0.3050 | 1.423 |
| **pooled, all four** | | 4,893 | **+0.0735** | 0.1190 | **−0.0455** | 1.086 |

**The round turn is 162% of the pooled gross edge.** Gold is the extreme case — gross-positive on
both blocks and net-negative on both, with the cost 2.8x and 2.0x its own gross edge — so gold is a
**cost** failure, and `STUDY_XAU_TWO_LAYER`'s reading of the same market reproduces. **NQ is
gross-NEGATIVE on both blocks**, so it is a signal failure and no execution improvement reaches it.

And the decisive line: **the pooled GROSS edge, +0.0735, is still inside its own gross MDE of
0.0992** (ratio 0.74). Removing the entire round turn from four markets and 4,893 trades does not
produce a detectable effect. That closes off the "it is a cost problem" reading at the pooled level
even though it is the right reading for gold alone.

---

## 9. Trades a year, and what would actually settle section 12

Section 12's requirement was **1,073 trades of `+adx<=20` at 50/150 on US30, against 400 in hand**,
with the different-provider forward feed accruing them. Measured on `US30_ISO` over its 349
post-2025-07 sessions (1.385 years):

| arm | trades on C_forward | **per year** | years to reach 1,073 |
|---|---|---|---|
| base | 240 | **173** | 6.2 |
| `+ema align` | 150 | 108 | 9.9 |
| `conventional` | 94 | 68 | 15.8 |
| **`+adx<=20`** | 73 | **53** | **20.3** |
| `+both` | 40 | 29 | 37.0 |

**Waiting for the ISO feed to settle the ADX arm takes twenty years.** Pooling was the alternative
and it has now been run: it bought a 1.68x MDE improvement, brought PF 1.2 inside resolution, and
returned a negative edge.

---

## Verdict

**The frozen section-12 rule does not survive the markets that had no part in finding it, and its
two component findings separate cleanly: the ADX ceiling is a US30-block-and-unit artifact, and the
EMA condition is real, small, and simpler than it was written.**

- **PARITY EXACT** on all ten US30 cells before anything else was read — trade count, entry bar,
  exit bar and points, ADX max |diff| 0.000e+00.
- **H1 fails: `+adx<=20` beats its base in 5 of 14 fresh cells (chance 50%) and 0 of 4 markets**,
  while `conventional` — the arm placed in the table because it had to lose — beats its base in 10
  of 14 and is the best arm on three of the four "A" blocks. The ADX axis carries nothing here in
  either direction.
- **H2 is weakly consistent (9 of 14, 2 of 4 markets) and the rate workstream's simplification is
  better: `ema34>ema89` alone is 10 of 14 at +0.029 ATR and beats the full alignment in 9 of 14,
  while `ema13>34` alone is 2 of 14 at −0.050.** Drop the 13-EMA.
- **Points are not comparable and it is worth twenty-six-fold here** — 50 points is 24.5 ATR on gold
  and 0.94 ATR on the ISO Dow — and even *within* US30 the points and ATR-unit readings disagree
  about the flagship arm in the flagship block.
- **Two feeds of one index are worse than useless when pooled**: adding NQ to US100 adds 592 trades
  and removes 269 effective ones. There are three objects here, not five.
- **Pooling worked and found nothing**: MDE 0.1606 → 0.0957, PF 1.2 now inside resolution at 1.71x
  the MDE, measured edge **−0.0455 net and +0.0735 gross**, the gross figure itself inside its own
  MDE. 0 of 70 cells outside their MDE; 6 of 70 clear a matched control against 3.5 expected, two of
  those while losing money.

**What this changes.** Section 12's single actionable recommendation — *removing `adx>=25` is the
one change the evidence supports without qualification* — survives, because nothing here supports
the ADX floor either. What does not survive is the positive half of it: **do not add `adx<=20`**.
The condition worth carrying forward from this family is `ema34>ema89`, and it is worth about +0.03
ATR a trade, which is a third of what the pooled sample can resolve.

**What would move it, in order.** (1) **Nothing in the parameter space** — 98 declared cells across
four markets, three of them structurally independent, is the widest honest read this window has had,
and the gross edge is inside its own MDE. (2) **A cheaper round turn**, which is the only lever that
is decisive on gold (2.8x its gross edge) and worth 1.6x the pooled gross edge overall. (3)
**1-minute bars for US30 and US100**, which fix the measurement rather than the sample. A fifth
index feed would not help: the overlap matrix says the marginal one is already the third object.

---

### Files and trial count

`research/us30xmkt/xm_core.py` (loaders, clocks, the COPIED frozen kernel, date-clustered SE,
matched control, day-block bootstrap), `run_x1.py` (feeds, clocks, **the parity assertion**, cost as
a fraction of the stop), `run_x2.py` (overlap matrix, leg correlation, effective n), `run_x3.py`
(**the 70 declared cells, one read each**, both parameterisations, control and bootstrap on every
one), `run_x4.py` (replication counts, pooled read, MDE at every count), `run_x5.py` (base rates on
the trigger's own bars, kept shares, condition correlation), `run_x6.py` / `run_x7.py` (the unit
decomposition and the three weightings), `run_x8.py` (**the 28 further cells of the third
condition**), `run_x9.py` (gross against net), `plot_xmkt.py`.

**Trial count: 98 declared cells** — 70 (5 arms × 2 parameterisations × 7 blocks of 4 markets) plus
28 (2 new arms × 2 parameterisations × 7 blocks). No sweep was run and no parameter was chosen on
any of these markets. `run_x6`, `run_x7` and `run_x9` re-express the same trades in other units and
add no configurations. US30's ten cells are reproductions of published numbers, not new trials.
