# Multiple timeframes, twelve validation tests, parameter sensitivity, and Pine export

Four additions to the generator, and one result that is genuinely new.

## 1. Every timeframe, not just 30 minutes

The same 115 conditions and 32 exit geometries, swept separately on each bar size. 16,228,800
strategies per timeframe.

| bars | scored | median locked | best on research | → LOCKED | top-1,000 that are long |
| --- | --- | --- | --- | --- | --- |
| 15m | 12,463,001 | −$1,000 | 25,819 | 3,861 | **100%** |
| 30m | 12,050,899 | −$743 | 25,397 | 8,490 | **100%** |
| 60m | 11,272,656 | −$558 | 25,525 | 5,162 | **100%** |

Section 4c holds on every bar size independently.

### A rule's research performance transfers strongly across bar sizes

Rank correlation of research P&L for the same rule and geometry:

| | |
| --- | --- |
| 15m vs 30m | **+0.857** |
| 30m vs 60m | **+0.839** |
| 15m vs 60m | **+0.758** |

That is worth knowing on its own: whatever the search is finding, it is **not** an artefact of bar
size. It survives being re-measured on a different sampling of the same tape.

### And this makes a new filter available

Require a rule to be profitable **in both directions on the research block of every timeframe**.
Only **2,043 of 8,114,400** rule/geometry pairs qualify. Reading the locked blocks once:

| | |
| --- | --- |
| still positive on **all three** locked blocks | **422 (20.7%)** |
| chance, if the three timeframes were independent | **13.2%** |

**This is the first filter on this branch that transfers better than chance.** The direction-neutral
filter transferred *worse* than chance (15.4% against 24.0%). Cross-timeframe agreement is the
first constraint measured here that carries information about the future rather than about the fit.

The effect is modest — 20.7% against 13.2% is a lift of 1.57, not a licence — but it is the right
sign, which nothing else here has been.

### Addendum: the 5-minute sweep finished, and it tightens the same result

`research/alpha_multi.py` globs whatever sweeps exist in `/tmp`, so the numbers above are the
**three-timeframe** run (15m, 30m, 60m). The 5-minute sweep completed afterwards and the same
script now reads four:

| | three timeframes | four timeframes |
| --- | --- | --- |
| pairs profitable both ways on every research block | 2,043 | **131** |
| still positive on every locked block | 422 (20.7%) | **20 (15.3%)** |
| chance if the timeframes were independent | 13.2% | **5.1%** |
| lift | ×1.57 | **×3.00** |

Adding a fourth bar size makes the filter much stricter and roughly doubles the lift. Treat the
×3.00 with care: it rests on 20 survivors out of 131 against an expected 6.7, which is a real
excess but a small sample. Both runs point the same way; the four-timeframe run points harder.

Reproduce either by removing or restoring `/tmp/af2_5m.npz`. The sweeps are not committed — each
is regenerated in about 93 seconds by `python3 research/alpha_factory2.py <tf>`.

## 2. The twelve-test battery

`research/validation.py` runs all of them from one input: per-trade P&L plus the session each trade
**entered** and **exited**. That last field is what makes purging possible — a trade straddling a
fold boundary has seen both sides of it.

| test | what it can kill |
| --- | --- |
| in-sample | nothing; it is the fit, reported as a reference |
| out-of-sample | a fit that does not transfer at all |
| holdout, read once | everything else |
| train/test split at 50/60/65/70/80 | a result that depends on where the split lands |
| rolling window | a result that lives in one stretch of the sample |
| expanding window | a result that decays as data arrives |
| walk-forward analysis | a fixed rule that stops working forward |
| walk-forward optimisation | the **selection procedure**, re-run every fold |
| anchored walk-forward | the same, training always from the start |
| purged K-fold | leakage from trades straddling a fold edge |
| embargoed CV | leakage from serial correlation just after a test fold |
| combinatorial purged CV | the probability of backtest overfitting (PBO) |

Calibration check: run on synthetic noise with a positive mean, the battery returns **PBO = 100%**
and a third of CPCV paths negative — which is the correct answer for a series with no structure.

## 3. Parameter sensitivity

`research/param_test.py` moves every parameter one step at a time — stop multiple, target, session
cutoff, bar size, direction, **and dropping each condition in turn**, which is the test most
sweeps omit and usually the most informative.

On `RSI14<30 AND Williams%R<-80 AND ADX>25`, both directions, 2.5×ATR stop, 3R target:

| | locked $ |
| --- | --- |
| **the rule as chosen** | **5,325** |
| stop 1.5×ATR | 12,266 |
| target 2.0R | 8,968 |
| target 1.0R | **−1,184** |
| 60-minute bars | 7,933 |
| 15-minute bars | −40 |
| drop `ADX>25` | **−2,496** |
| longs only | 7,585 |
| **shorts only** | **−2,260** |

12 neighbours, median $3,977, **67% positive**, worst −$2,496. A moderate plateau, not a spike.

Two things the sweep exposes that the headline does not: the rule needs a **far target** (1.0R and
1.5R both lose), and it is still **long-carried out of sample** despite being selected for
two-sided profitability on research.

## 4. Pine export

`research/pine_export.py` turns any generated rule into a **TradingView strategy** and a matching
**indicator** with alerts and a live condition table. All 115 conditions have exact Pine
expressions.

Two definitions are pinned deliberately, both because they have already gone wrong here:

- **ATR is `ta.ema(ta.tr(true), 14)`**, alpha 2/15 — not `ta.atr`, which is Wilder's RMA at alpha
  1/14 and would move every stop.
- **Clock conditions take an explicit timezone**, because Pine's bare `hour`/`minute` are in the
  exchange timezone (Chicago for CME) while the research is New York.
- **CCI is emitted as `ta.cci(hlc3, 20)`**, not `ta.cci(close, 20)`, to match the research's
  typical-price definition. That one was caught while writing the exporter.

Every emitted file carries its measured figures, its exit geometry, and the standing warning that
the logic is transcribed from a verified engine but the syntax has not met a compiler.

## Reproduce

```
python3 research/alpha_factory2.py 15 30 60   # one 16.2M sweep per timeframe
python3 research/alpha_multi.py               # cross-timeframe transfer and the filter
python3 research/validation.py                # the battery, calibrated on noise
python3 research/param_test.py                # sensitivity on one rule
python3 research/pine_export.py               # strategy + indicator emitters
```
