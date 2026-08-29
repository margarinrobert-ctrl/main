# Donchian breakout scalping, 07:00–11:00 New York

Research into whether a Donchian-channel trend-following breakout has a tradable
edge in the 07:00–11:00 New York window, on 15-minute bars.

**Instruments.** NAS (Nasdaq-100), 206,703 bars, 2016-11-14 → 2025-10-01, 2,747
sessions. US30 (Dow), 193,942 bars, 2016-10-26 → 2025-07-15, 2,704 sessions.
A third file, an independent-broker US30 feed with explicit New York offsets, is
used only for timezone calibration and feed checks.

**Split.** First 65% of *sessions* is research; the rest is locked. Chronological,
computed on sessions so no partial day straddles the boundary. **The locked block
has not been read.**

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
| `docs/donchian/ledger.jsonl` | the experiment ledger |
