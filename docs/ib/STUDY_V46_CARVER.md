# V46 — Carver's breakout, 999,717 configurations, and what the control does to them

**Every frozen configuration is profitable on every market including two it never saw — and 7 of 8
fail a random-entry control, with the random entry beating Carver outright on NQ in both. What the
sweep found is the exit geometry and the drift, not the indicator.**

Search on US100 (research block only), US30 and NQ held back. `research/v46/`.

---

## 1. The indicator, implemented and verified

Carver's breakout, to the published definition:

```
max_N, min_N = rolling max/min of price over N ;  mean_N = (max_N + min_N)/2
raw          = (price − mean_N) / (max_N − min_N)        ∈ [−0.5, +0.5]
forecast     = clip( 40 × EWMA(raw, span = N/4), −20, +20 )
```

**Positive control on the implementation:** Carver picks the scalar so that mean |forecast| ≈ 10.
Measured here across his span set: **10.70 to 12.16**. The truncation audit — recompute on history
truncated at bar *i*, require the value to match — is **clean at every span and smoothing**.

This is *not* a Donchian breakout, which matters given how much of this branch is one. Donchian is
binary and fires at a new extreme; this is continuous, range-normalised position within the channel,
smoothed. And it is *not* Carver's system: he uses the forecast as a continuous position size across
many instruments and speeds. Adapting it to a single-contract barrier trade is mine, and a result
here is a statement about that adaptation.

---

## 2. The grid

3 timeframes × 8 spans × 3 smoothings × 4 exit thresholds × 5 stops × 5 targets × 3 max holds ×
6 entry thresholds × 2 modes × 4 chop ceilings = **1,036,800 nominal, 999,717 scorable** (96.4%).
Objective: the **median of 8 walk-forward folds**, not the aggregate.

*A million vectorbt simulations is many hours on four cores, so the sweep runs on this branch's
cached-exit-tensor architecture — 999,717 cells in **73 seconds** — and vectorbt was reserved for
the second-engine check in §6.*

**Population before any ranking:**

| | |
| --- | --- |
| PF > 1 | **61.3%** |
| fold median > 0 | 59.2% |
| **all 8 folds positive** | **0.00%** |
| median PF / pts | 1.029 / +0.61 |

The best cell is the maximum of ~613,000 profitable draws, and **not one configuration in a million
has all eight folds positive.**

### Marginal averages (read these, not the top row)

| axis | direction |
| --- | --- |
| timeframe | monotone to **60m** (1.043 → 1.073 → 1.118) |
| stop | monotone to **3.0 ATR**, the grid edge (1.046 → 1.094) |
| max hold | monotone to **480 bars**, the grid edge (1.049 → 1.101) |
| take profit | **none** best by a distance (1.149 vs 1.005–1.105) — the **tenth** time on this branch |
| forecast exit | **off** best (1.099 vs 1.065–1.075) — Carver's own signal adds nothing as an exit |
| entry mode | **cross** 1.131 vs state 1.027 |
| chop filter | **off** best (1.090 vs 1.064–1.079) |

### Carver's own span range brackets the optimum

| span | PF | pts | share PF>1 | |
| --- | --- | --- | --- | --- |
| 5 | **0.952** | **−0.09** | 28.7% | my extension, faster than his set |
| 10 | 0.992 | +0.27 | 44.6% | Carver's fastest |
| 40 | 1.078 | +2.74 | 74.3% | |
| 160 | 1.135 | +4.23 | 69.2% | |
| 320 | 1.131 | +3.79 | 66.4% | Carver's slowest |
| 640 | 1.088 | +2.64 | 66.2% | my extension, slower than his set |

**Span 5 is the only negative row in the table**, and it is the one variant faster than anything
Carver publishes — an independent confirmation of his own caveat that the fastest breakouts are
eaten by costs. His published range contains the peak and both of my extensions fall back.

---

## 3. The two frozen candidates

**CONSENSUS** — the modal setting of each axis over the top 1000 by fold median (STUDY_V14's rule):
60m, span 320, smooth 8, entry cross ≥ 5, stop 3.0N, no target, hold 480, no chop, no forecast exit.
Axis agreement: hold **99.2%**, tf **93.7%**, no-target **82.5%**, no-forecast-exit 62.8%, stop 3.0
46.3% — but span only 27.4% and entry threshold 21.6%.

**TOP ROW** — the single best cell, carried only so the gap can be read: 60m, span 80, smooth 2,
entry cross ≥ 0, otherwise identical.

Two warnings attached before any result: **three axes sit at the edge of the grid** (stop 3.0, hold
480, tf 60), so the optimum was not bracketed; and **top-1000 mean folds-positive is 4.3 of 8** on
a mean of 132 trades against the grid's 1,825 — the ranking is buying low-trade-count cells, which
is exactly what V42 measured.

This is also not a scalp: hold 480 at 60m is twenty days.

---

## 4. The frozen read — and the control

| cfg | market | block | n | PF | pts | **control pts** | **p** | boot P(≤0) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CONSENSUS | US100 | research | 67 | 1.741 | +57.99 | +40.23 | 0.260 | 0.074 |
| CONSENSUS | US100 | **LOCKED** | 42 | 1.643 | +84.38 | +73.54 | 0.407 | 0.144 |
| CONSENSUS | **US30** | never seen | 98 | 1.682 | +114.48 | +59.91 | 0.145 | 0.044 |
| CONSENSUS | **NQ** | never seen | 41 | 1.159 | +20.34 | **+82.10** | **0.880** | 0.405 |
| TOP ROW | US100 | research | 102 | 1.656 | +59.95 | +47.87 | 0.302 | 0.035 |
| TOP ROW | US100 | **LOCKED** | 63 | 1.694 | +95.62 | +60.25 | 0.205 | 0.094 |
| TOP ROW | **US30** | never seen | 165 | 1.736 | +145.37 | +59.65 | **0.033** | 0.009 |
| TOP ROW | **NQ** | never seen | 67 | 1.379 | +55.43 | **+78.00** | 0.667 | 0.207 |

**Every cell is profitable, including on both held-back markets — and 7 of 8 fail their control.**
Only TOP ROW on US30 clears at p 0.033, one of eight uncorrected tests where 0.4 is expected by
chance.

**On NQ the random entry beats Carver in both configurations** (+82.10 against +20.34, +78.00
against +55.43). The control is earning **+40 to +82 points a trade on its own**: with a 3.0 ATR
stop, no target and a twenty-day hold on markets that rose, a coin flip makes money. That is
`STUDY_TURTLE`'s finding reproduced on a different indicator — *a trailing-stop system is a drift
harvester, so score it against the drift it is harvesting.*

Note the two questions are separate and both are answered here: the day-block bootstrap excludes
zero in three cells (US30 0.044 / 0.009, US100 research 0.035), so the *edge against zero* is real
in those. It is the *excess over a matched control* that is not.

---

## 5. Monte Carlo

Day-block bootstrap for the edge, permutation for the path — permuting cannot move the endpoint, so
only drawdown is read from it.

| cfg / market | realised DD | MC median | p95 | **p99** | p99 / realised |
| --- | --- | --- | --- | --- | --- |
| CONSENSUS US100 locked | 2,259 | 1,746 | 2,816 | 3,253 | 1.44× |
| CONSENSUS US30 | 2,933 | 3,337 | 5,430 | 6,520 | 2.22× |
| TOP ROW US100 research | 3,194 | 1,743 | 2,797 | 3,489 | 1.09× |
| TOP ROW US30 | 4,412 | 4,821 | 7,747 | 9,223 | 2.09× |

**Size for the p99, which is 1.1–2.2× the realised drawdown.** TOP ROW on US100 research realised
3,194 against an MC median of 1,743 — that path was unluckier than a reshuffle of its own trades,
so the visible drawdown understates nothing there.

Intrabar-ambiguous share is **0.0% of trades** on every cell, because with no take profit the stop
and target cannot collide inside one bar.

---

## 6. The vectorbt cross-check did not achieve parity, and is reported as inconclusive

The protocol is transcription first — the trade **count** must match, proving both engines see the
same signal set — and only then read the P&L gap as a statement about convention. **That count
never matched:** ratios 0.12 to 0.98, with vectorbt's P&L landing at almost exactly minus the fixed
fee, i.e. closing trades near their entry.

Diagnosed rather than left as a mystery: with stops disabled entirely vectorbt still produced 24
trades to my 165, so it is the **exits**, not the stop. `sl_stop` in vectorbt 1.1.0 is a **fraction
of price**, while the stop here is a **multiple of ATR that varies per trade**; a per-bar array does
not pin to the entry bar's value, and `td_stop` does not exist in this version. Feeding vectorbt my
own exit bars did not recover parity either.

**So no gap is read from it in either direction.** The V38/V41 cross-checks that worked found 2.1×
and 22.9× convention gaps; this one establishes nothing, and the §4 numbers rest on one engine.
Given no take profit, the collision that produced those earlier gaps cannot occur here — which is a
reason to expect agreement, not evidence of it.

---

## 7. Verdict

**Ships nothing.** The search is real, the indicator is correctly implemented and causal, and the
result generalises to two unseen markets — but a random entry with the same exits captures most or
all of it, and beats it outright on NQ. What the million cells found is a wide stop, no target and a
long hold on markets that rose. Three axes ran to the grid edge, no configuration has all eight
folds positive, and the second engine could not be made to agree.

The one durable finding is about Carver rather than about a strategy: **his published span range
10–320 brackets the optimum, and the faster variant he warns about is the only negative row.**

## Caveats

Uncorrected p-values over 8 frozen tests and a 999,717-cell search. The consensus configuration's
span and entry-threshold agreement is weak (27.4%, 21.6%). NQ contributes 41–67 trades. US30's
costs are assumed, not measured, like every feed here except EURUSD. The 15m→60m resample uses each
feed's own clock as recorded in `research/datasets.py`.

## Files

`research/v46/carver.py` (indicator + audit) · `v46grid.py` (exit tensor, lock, grid) ·
`run_v46.py` (the sweep) · `run_v46b.py` (freeze, holdout, control, both Monte Carlos) ·
`run_v46_vbt.py` (the second engine, inconclusive) · `results/v46/`.
