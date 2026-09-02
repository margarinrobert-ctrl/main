# Donchian breakout scalping, 07:00–11:00 New York

> **VERDICT: NO VALIDATED EDGE FOUND.** All 8 pre-registered holdout comparisons
> failed (§10). The 62,640-cell VectorBT sweep's best sits inside its null (§11). The
> EMA-cross × ATR variant failed walk-forward on every clause (§12).

Research into whether a Donchian-channel trend-following breakout has a tradable
edge in the 07:00–11:00 New York window, on 15-minute bars.

**Instruments.** NAS (Nasdaq-100), 206,703 bars, 2016-11-14 → 2025-10-01, 2,747
sessions. US30 (Dow), 193,942 bars, 2016-10-26 → 2025-07-15, 2,704 sessions.
A third file, an independent-broker US30 feed with explicit New York offsets, is
used only for timezone calibration and feed checks.

**Split.** First 65% of *sessions* is research; the rest is locked. Chronological,
computed on sessions so no partial day straddles the boundary. **The locked block
was opened twice, for §10 and §11, and not again for §12.**

> Research tooling for education and analysis. Nothing here is financial advice.

---

## The result

**The Donchian breakout in this window has no gross directional edge on either
instrument.** It is not a real effect that transaction costs happen to eat — it
loses money at a round turn of *zero*, and its excess over a geometry-matched
control is statistically indistinguishable from zero.

Five tests support this, and each would have caught a *different* failure mode:

| test | what it would have caught | result |
| --- | --- | --- |
| matched control | a real but small edge | excess ≈ 0 at every lookback, z ∈ [−1.34, +0.16] |
| FDR event studies | a conditional edge at breakout events | 0 of 170 survive BH q=0.10 |
| CSCV / PBO | a tunable profitable region | 0 of 140 configs profitable; PBO 0.526 |
| gross decomposition | an edge destroyed by costs | gross negative at zero cost |
| ML quality filter | a separable subpopulation | real ranking skill, +0.15 pts/trade |

---

## 1. Timezone — the study depended on getting this right

Both CSVs carry naked timestamps. Absolute prices cannot settle the question: the
files differ from the reference feed by a ~39-point CFD/futures basis. Two
basis-invariant methods agree exactly:

- **Return correlation.** 15m log returns against the reference feed (explicit
  `-04:00` stamps) peak at **0.749 at UTC+3**, against a 0.05 noise floor.
- **Volume seasonality.** The largest daily activity jump sits at **CSV 16:30 in
  both summer and winter** — the 09:30 cash open.

So **New York = CSV − 7h**, and because the peak does not move between seasons the
feed tracks DST and the offset is stable year-round. The window is CSV 14:00–18:00.

## 2. Scoring against zero is invalid on this engine

Stage-0 calibration over driftless synthetic series found **t-vs-zero fires at
29–33%** against a nominal 5%. The cause is not a bug: barrier geometry under a
time limit has non-zero expectation even on a martingale — negative for
tight-stop/wide-target pairs, positive for the reverse.

Diagnostics ruled out the alternatives. The gap-fill rule contributes exactly
0.000; longs and shorts are symmetric (+1.93 vs +2.00); and a **geometry-stripped
null gives t ≈ 0**, which clears the engine of look-ahead. A power check confirms
detection scales monotonically with planted AR(1) momentum (t = −2.03 → +3.69 as
φ goes 0 → 0.20), so the pipeline can find an effect that is there.

The **matched control** — random entries with the same side mix, same ATR geometry
and same minute-of-day histogram — absorbs that bias, firing at **0.0% over 24
independent null series**. Every number in this study is scored against it.

## 3. Independent validation found a real engine bug

`verify_engine.py` reimplements the simulator as a naive bar-by-bar event loop,
written from the stated rules rather than from the engine's source, and asserts
the two agree trade-for-trade. It found **1,009 disagreements in 76,572 trades**
across 36 configurations, all one signature: the vectorised engine resolved a stop
or target on a bar the loop had already flattened at the open — using price action
from after the position closed.

Flatten now wins ties against both barriers; stop still wins ties against target,
since the intrabar path is unknown. After the fix, **0 disagreements**. Stage 0
and the baseline were recomputed; both conclusions held.

## 4. Baseline

NAS research block, one trade per session, 2.0 pt round turn + 0.25 pt slippage
per side, stop 1.5 ATR / target 2.0 ATR:

| entry lookback | n | exp | control | excess | z | p |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | 1,479 | −2.64 | −2.61 | −0.03 | −0.04 | 0.500 |
| 10 | 1,461 | −3.16 | −2.70 | −0.46 | −0.52 | 0.707 |
| 20 | 1,395 | −2.50 | −2.64 | +0.14 | +0.16 | 0.463 |
| 40 | 1,284 | −2.87 | −2.64 | −0.23 | −0.25 | 0.593 |
| 80 | 892 | −3.38 | −2.52 | −0.86 | −0.75 | 0.783 |

Window baselines are all negative: 07:00–11:00 −2.50; 07:00–09:30 −2.08;
09:30–11:00 −3.55.

## 5. Gross vs net — the decisive decomposition

With costs and slippage switched **off**, and scored against a cost-free control:

| lookback | NAS gross/ATR | US30 gross/ATR |
| --- | --- | --- |
| 5 | −0.041 | −0.067 |
| 10 | −0.076 | −0.051 |
| 20 | **−0.026** | **−0.026** |
| 40 | −0.051 | −0.036 |
| 80 | −0.088 | +0.096 |

Negative at 9 of 10 lookbacks, clustered in −0.026 to −0.088 ATR, gross excess
insignificant everywhere (smallest p 0.173). The two instruments agree to three
decimals at n=20 despite their breakout events overlapping at only Jaccard 0.26.

The one positive cell (US30 n=80, +0.096 ATR, p=0.173) is one of ten, is not
significant, and still loses 1.99 pts net. Recorded, not pursued.

**This rules out the standard remedies together.** A cheaper venue, a larger
contract, a wider barrier and a longer hold all scale the signal and the cost in
the same proportion, and the signal is zero.

## 6. What *did* show real structure

Two findings are genuinely real and both die at the same wall.

**ML breakout-quality ranking.** LightGBM over 32 causal features, purged 6-fold
CV with a 32-bar embargo. Out-of-fold **AUC 0.5785** against a permutation null of
**0.4975 ± 0.0084** built by shuffling labels and re-running the whole pipeline —
**z = +9.70**, so the CV does not leak. Seed sd 0.0010; no ablation moves it more
than 0.004; dropping all time features costs 0.0276 and still leaves 0.5510.

And it is worthless: filtering to the top decile moves expectancy from −2.73 to
**+0.15 pts/trade**, break-even cost multiple **1.05**, matched-control p 0.080,
and P&L concentrated in the final third (−1.74 / +0.29 / +1.89). **REJECTED.**

Note what this skill actually is: ranking which of several *zero-edge* trades is
least bad. That is not a directional edge.

**Entry mechanic.** A resting stop order at the channel level fills **2.2–2.6
points better** than the next-bar open — the size of the whole round turn. But the
paired P&L difference averages only +0.19, because it is monotone in stop width
and channel length:

| paired Δ | stop 1.5 | stop 2.0 | stop 2.5 |
| --- | --- | --- | --- |
| n=10 | +1.33 | +1.47 | +2.36 |
| n=20 | −1.63 | +0.88 | +2.14 |
| n=40 | −4.07 | −1.71 | +0.96 |

Monotone in both directions is mechanism, not noise: entering 2.4 points earlier
also puts you in the noise the confirmation bar would have filtered, so a tight
stop gives back more than the fill gained. Best cell still loses 0.78 pts/trade.
**A better fill is not the same as a better trade.**

## 7. Methodological notes

- **Instrument independence.** 15m returns correlate 0.83 (0.74 in-window), but
  breakout *events* co-occur at Jaccard 0.23–0.28, φ 0.32–0.37. US30 confirmation
  is real partial evidence, not a second independent test.
- **Selection procedure.** PBO 0.526 with a degradation slope of −1.298 means a
  better research number from the standard grid is *evidence against* a candidate.
- **A control must match the mechanic.** A first pass scored the stop-entry book
  against a next-open control and produced an untrustworthy `excess` column. The
  paired design replaced it.


## 8. What the agent fleet found

Nine specialist quants were dispatched over the research block, each with stated
hypotheses and the matched control as a gate. Four have reported: **1,331
configurations**, 43 hypothesis families killed.

### The convergence

Three agents, starting from different hypotheses and sharing no code path,
arrived at the same mechanism — **break magnitude**:

| agent | its framing | result |
| --- | --- | --- |
| Donchian discovery | `buffer_atr`: close must exceed the channel by k·ATR | plateau, 28/28 cells positive |
| Volatility | ATR-normalised break distance `thru > 1.0` | *"the cleanest shape in the study"* |
| Breakout statistics | normalised thrust, median split | exc +2.93, p=0.005; US30 +4.3 |

The volatility agent measured the overlap itself: **70% Jaccard** with the
Donchian agent's book. So three agents produced *two* findings, not four —
break magnitude, and pre-window trend state (ADX@07:00).

### The decisive measurement

The breakout statistics agent measured the population rather than searching it,
and produced the sentence that contains the whole study:

> At the traded 1.5 stop / 2.0 target the break wins **43.1%** against a **40.1%**
> control with breakeven at **42.9%** — it clears its own geometry by 0.3 points
> and its cost by nothing.

The break *is* informative. In a symmetric k·ATR race it beats a matched control
at every width from 1.0 ATR up, peaking at 51.1% vs 47.7% (z=+3.72), and a
session-block bootstrap that prices in ~3 triggers/session gives **+3.39% ± 1.06%,
p=0.0025**. At tight barriers it is *worse* than random (23.7% vs 25.0% at 0.25 ATR).
A 108-cell geometry surface gives a maximum gross excess of **+0.085R**.

So: real information, roughly an order of magnitude below the cost floor.

### Killed by the fleet

EMA structure · EMA slope · higher-timeframe trend · session-anchored channels ·
channel compression · close-position-in-bar · range compression · ATR percentile
regime · overnight range · intraday range spent · the false breakout (26.2/37.6/56.2%
re-entry vs 25.5/36.6/56.5% distance-matched) · strong-close confirmation
(monotonically *worse*) · **momentum without the channel** (−0.21, which rules out
reading rule D as a momentum filter in Donchian clothing).

### Two corrections the fleet forced on me

1. **The episode check.** The volatility agent killed its own ATR-regime finding —
   *"this is the finding I most wanted to be real"* — by showing the damage was
   59% concentrated in five months. I had made a similar claim without that check.
   Running it on my numbers showed I had overstated the effect ~3× (74–77% of the
   damage in five crisis months).
2. **Rule C dropped.** That correction removed the justification for the low-ATR
   leg of my sharpened rule. Under a criterion fixed before looking, C failed and
   was dropped, leaving the simpler rule B.

## 9. The frozen rule set

| rule | definition |
| --- | --- |
| **A** | Donchian(20) breakout, stop 1.5 ATR, target 2.0 ATR, 07:00–11:00 NY, one trade/session |
| **B** | A, gated on ADX(14)@07:00 > 30 |
| **D** | A, requiring close to exceed the channel by 1.0 × ATR14 |

Frozen in `reveal.py` before the locked block is opened. **6 pre-registered
comparisons** (3 rules × 2 instruments), threshold **p < 0.0083**.

Declared research multiplicity: **1,485**. That correction applies to the
research p-values, which selected these rules — *not* to the holdout, which is
pre-registered. Applying it twice would double-count the search.

Rule D is the only configuration in the study with positive post-cost expectancy
on research (+0.858 pts/trade, excess +3.33, p=0.0075), and was reproduced
independently from its written description alone, agreeing to machine precision.


## 10. THE REVEAL — no validated edge found

The locked block was opened **once**, with four rules frozen in `reveal.py`
before any locked number was read: **8 pre-registered comparisons at p < 0.00625**.

**All eight fail.**

| rule | instrument | research excess | research p | locked excess | locked p |
| --- | --- | --- | --- | --- | --- |
| A baseline | NAS | −0.21 | 0.585 | +0.40 | 0.403 |
| B ADX@07:00>30 | NAS | **+5.08** | **0.0025** | **−0.75** | 0.576 |
| D break > 1 ATR | NAS | +2.44 | 0.039 | +0.59 | 0.439 |
| E thrust q0.70 | NAS | **+3.80** | **0.0013** | **−1.62** | 0.740 |
| A baseline | US30 | −0.75 | 0.646 | −0.37 | 0.558 |
| B ADX@07:00>30 | US30 | +2.88 | 0.228 | −0.75 | 0.536 |
| D break > 1 ATR | US30 | **+7.12** | **0.0125** | **−6.66** | 0.920 |
| E thrust q0.70 | US30 | +4.88 | 0.041 | +1.91 | 0.338 |

Every rule that was significant on research **decays** rather than appearing on
the holdout — the correct shape for an overfit rule, not the "wrong shape" defect.

### The audits called it in advance

The adversarial auditors refuted all three Donchian candidates *before* the
reveal, and for the right reasons:

- **Not leakage.** Eight independent probes came back clean; the rule was
  reproduced exactly from its text; the selectivity test *passed* at p=0.0019
  against 20,000 random filters.
- **Effective multiplicity.** The "28 cells, 100% positive" plateau I had called
  the study's best evidence sits on a nested surface with mean pairwise
  session-P&L correlation **0.60** — worth **~2.4 independent observations, not 28**.
  Li & Ji effective test count on the 56-cell surface: **M_eff = 19**.
  Perturbation verdict on rule D: **ridge**, not plateau.
- **Regime concentration.** Dropping 2021 alone took US30 rule D from
  excess +7.57 (z=2.41) to **+4.99 (z=1.43, p=0.079)**; dropping 2020+2021 turned
  expectancy negative.

The audit predicted rule D's US30 result would not generalise. On the locked
block it returns **−11.89 pts/trade, excess −6.66**.

Twenty of the thirty-two audit agents failed on a spend limit, so **rules B and E
reached the holdout unaudited**. Both failed there anyway.

### The pre-registered prediction was not confirmed

E>D was recorded in code before the reveal, on the strength of the residualisation
dissection. NAS gives the **reverse** ordering (D +0.59, E −1.62); US30 gives the
predicted one (E +1.91, D −6.66). One each way, both statistically zero — so the
dissection did not predict out-of-sample behaviour, though with both effects
absent the test had no power to detect an ordering.

### Final answer

**NO VALIDATED EDGE FOUND.**

The Donchian breakout in 07:00–11:00 New York, on NAS and US30 15-minute bars,
2016–2025, has no tradable edge. The central claim is confirmed out of sample:
the baseline is negative on the locked block on both instruments with excess over
a matched control indistinguishable from zero.

What the study *did* establish is narrower and more durable: the break carries
real, bootstrap-confirmed information about which way price races to a wide
barrier (+3.39% ± 1.06%, p=0.0025), worth **0.3 percentage points against a
breakeven of 42.9%** — which pays for nothing against a 2.25-point round turn.
Real signal, an order of magnitude below the cost floor.


## 11. VectorBT max-combination sweep — the best of 62,640 is inside the null

A 169,344-cell sweep (14 lookbacks x 21 ATR buffers x 12 stops x 12 targets, both
sides, both instruments), 118,800 cells clearing a 100-trade floor.

**The apparent result:** US30 long showed 56% of cells positive and a best cell at
**+25.99 pts/trade**.

**Why it is an artefact:** the top-50 cells use a median of **125 trades against the
grid median of 285**, all sit in one narrow region, and across all 118,800 cells the
correlation between trade count and expectancy is **−0.259**. The winners of a large
sweep are its smallest samples.

**The calibration.** A first null using driftless synthetic bars was *discarded, not
reported*: it produced only ~15,000 qualifying cells against the real grid's ~62,000,
so max-of-15k vs max-of-62k favoured the real data by construction. The replacement
keeps real prices, real bar geometry and real signal density, destroying only the
signal-to-forward-return alignment via a circular shift — so cell counts match to
within 0.5%.

| grid | cells | median exp | max exp | frac > 0 |
| --- | --- | --- | --- | --- |
| **Real NAS** | 62,640 | −2.37 | **+7.22** | 18.1% |
| shift-null 2131 | 62,352 | −3.01 | **+7.52** | 9.6% |
| shift-null 5119 | 62,064 | −3.51 | **+5.87** | 3.9% |

**The real grid's best cell sits inside the null range.** The best of 62,640
combinations is indistinguishable from what the identical machinery produces with
the signal alignment destroyed.

The real grid does have more positive cells than the null (18.1% vs 9.6%) — that is
genuine long-side drift in a bull sample, not edge, since the *extreme*, which is what
a sweep selects on, is indistinguishable.

*Caveats: only 2 of 4 planned nulls completed (two died under memory pressure, two
container restarts interrupted the run), so this is a range, not a dispersion
estimate — no z or p is quoted. Two vectorbt harness bugs were found and fixed before
any result was produced: default close-fill instead of next-open, and a NaN exit
price on every forced session exit.*

## 12. EMA-cross × ATR-regime variant — requested follow-up, walk-forward FAIL

The follow-up asked for the most profitable Donchian breakout that also requires an
EMA cross and an ATR condition, 07:00–11:00 New York, flat at 11:00. This section is
that search, run under the same discipline as everything above. The locked block was
**not** opened for it — it has already been read twice (§10, §11) — so the
out-of-sample test here is a walk-forward *inside* the research block that re-selects
the configuration on every training window. The selection rule and the pass criterion
were both written into the ledger (E0021) before the search finished.

**Grid.** Donchian lookback {10, 20, 40} × EMA pair {5/20, 8/21, 9/34, 13/50, 20/50,
50/200} × alignment mode {state, cross within 4 bars, cross within 8 bars, separation
≥ 0.25 ATR, ≥ 0.5 ATR} × ATR regime {none, percentile < 0.8, percentile 0.2–0.8,
expansion ratio > 1.2} × stop/target {1.0/2.0, 1.5/2.0, 2.0/3.0} = 1,080 cells per
instrument, 2,160 in total. The ATR percentile is a causal 250-bar rank; the
expansion ratio is ATR(14) now over ATR(14) eight bars earlier. Every cell is a close-confirmed break of the
prior-bar channel, one trade per session, market at the next open, ATR stop and target
frozen at the signal bar, time stop 16 bars, forced flat at 11:00, costs as in §4.
Every cell is scored against the matched control of §2.

### 12a. Research block — the gate adds nothing

| | NAS | US30 |
| --- | --- | --- |
| cells positive after costs | 12 / 1080 (1.1%) | 94 / 1080 (8.7%) |
| cells with excess > 0 and p < 0.05 | 9 / 1080 | 21 / 1080 |
| expected at p < 0.05 by chance | ~54 | ~54 |
| median excess over control (pts) | +0.12 | +0.57 |

Fewer cells pass than a nominal 5% rate would produce — the control's p-value is
calibrated to a 0% false-positive rate on null series (§2), so this is a conservative
p, not evidence of anti-edge. What it does say is that nothing in the family stands out.

**No ingredient moves the family out of negative expectancy.** Mean expectancy after
costs by alignment mode runs from -2.07 (sep0.5) to -3.17
(cross8) pts per trade; by ATR filter from -2.19 (pct<0.8) to
-2.88 (none). The fast-EMA marginal is not smooth: period 13 is
the worst at -3.55 while 8 and 9 on either side of it sit at -2.27
and -2.29. A real edge decays smoothly across a parameter; a spike like that
is noise.

**At identical geometry the EMA gate does not beat the ungated breakout.** For each of
the nine (lookback, stop/target) pairs the mean expectancy of the 30 EMA-gated variants
matches the ungated cell to within about a quarter point, and the *mean excess* over the
control is the same sign and size. The gate's best cell in each row improves on the
ungated only by taking fewer trades — selectivity 0.06–0.16 — which is what any random
subsample of a losing population does at its upper tail.

**The top of the table is where the variance is.** All 12 of the top 12 NAS cells
by excess use the rarest alignment mode (a cross within the last 4 bars) together with an
ATR-percentile filter, at selectivity 0.06–0.16. The cross-within-4 mode has the
*second-worst* marginal mean. The extremes of a search come from its noisiest members,
which is exactly what a pre-declared selector plus a walk-forward exist to catch.

### 12b. The pre-declared selector

The rule, fixed before the results: among NAS cells with ≥ 100 trades, the highest
excess over the control subject to expectancy > 0 after costs and p < 0.05.
3 cells qualified. The winner:

| lookback | EMA | mode | ATR filter | stop/target | trades | exp (pts) | excess | z | p | selectivity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20 | 8/21 | cross4 | pct<0.8 | 2.0/3.0 | 438 | +1.05 | +3.32 | +1.78 | 0.0467 | 0.15 |

That is a research-block number for the best of 1,080 with a 200-draw control; p 0.047
at the extreme of that many cells is, on its own, nothing.

### 12c. Walk-forward — FAIL on every clause, in both configurations

Re-select the best configuration (by mean net per trade, ≥ 30 training trades) from
all 1,053 candidate books on each training window; trade the next block with it;
stitch the out-of-sample blocks. Pass required, in *both* configurations: (a) stitched
OOS expectancy > 0 with a bootstrap 95% CI excluding zero; (b) ≥ 60% of folds
profitable; (c) median OOS expectancy > 0.

| train/test (sessions) | folds | profitable | median IS | median OOS | stitched OOS [95% CI] | worst fold | modal config kept | a / b / c |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 300/100 | 14 | 29% | +3.63 | -2.72 | -3.90 [-8.32, +0.56] | -13.70 | 14% | FAIL / FAIL / FAIL |
| 500/150 | 8 | 38% | +2.65 | -2.95 | -2.19 [-8.05, +3.37] | -10.26 | 25% | FAIL / FAIL / FAIL |

**Verdict: FAIL.** The in-sample median flips from clearly positive to clearly
negative the moment the choice is charged for, the chosen configuration changes on
almost every fold, and the stitched out-of-sample expectancy is negative in both
configurations. This is the signature of selecting on noise, and it is the same shape
as §10 and §11.

### 12d. What was delivered

`pine/DonchianEmaCross.pine` is a parameterised Pine v6 strategy implementing the whole
family (all five alignment modes, all four ATR filters, the geometry, the window, the
one-trade-per-session rule, ATR as `ta.ema(ta.tr(true), n)`, New York clock, confirmed
bars). Its defaults are set to the pre-declared research winner because that was the
declared procedure, and its header states in plain text that the walk-forward failed and
that the defaults describe the past sample, not an expectation. Lint-clean under
`research/pine_lint.py`.

**Prior, as recorded in E0021 before the search: "the EMA gate is expected to add
nothing."** It added nothing. The family joins the register: no validated edge.

## Files

| file | role |
| --- | --- |
| `ingest.py`, `tzcal.py`, `dstcheck.py` | data audit and timezone identification |
| `data.py` | canonical New York datasets and the session-based 65/35 split |
| `engine.py` | cached forward-walk tensors; geometry as an array index |
| `verify_engine.py` | independent event-loop validator |
| `control.py`, `lab.py` | matched-control gate and shared agent API |
| `null_test.py`, `null_diag*.py`, `null_control*.py` | Stage-0 calibration |
| `baseline.py`, `budget.py`, `pbo.py`, `gross.py`, `gross_us30.py` | the core results |
| `agent_ml.py`, `agent_ml_attack.py` | ML filter and its adversarial audit |
| `stop_entry.py`, `stop_entry_paired.py` | entry-mechanic tests |
| `indep.py`, `robust.py` | independence measurement; robustness battery |
| `emacross.py`, `emacross_eval.py`, `emacross_finalize.py`, `emacross_report.py` | §12 EMA-cross × ATR search, walk-forward, pre-declared finalizer |
| `pine/DonchianEmaCross.pine` | §12 parameterised strategy, defaults = research winner, header = walk-forward FAIL |
| `docs/donchian/ledger.jsonl` | the experiment ledger |
