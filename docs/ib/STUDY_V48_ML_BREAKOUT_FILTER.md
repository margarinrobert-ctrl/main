# V48 — Machine learning on risk-premium, PEAD-analogue and release-clock features, as a Donchian filter

**The features the brief asked for carry everything the model uses and the breakout's own context
carries nothing — and none of it clears a same-selectivity control on both holdouts. The neural
network loses to ridge on every timeframe.**

Donchian breakout base (30/20, 2.0N stop, channel exit, one unit, no target, long). 39 causal
features. Search on US100, US30 held back. `research/v48/`.

---

## 0. Data, and what "news" means here

All three feeds restored and **verified byte-identical to the registry for the third time**:
US100_LONG `c449dddfbc06a943` / 206,703 rows, US30_LONG `24dcf2e1c7ba398f` / 193,942 rows.
`research/datasets.py` reports 4 of 4 present feeds identical to the studied copies.

**No news feed is attached and none was scraped.** What is used is that US macro releases land on a
FIXED, PUBLIC New York clock — 08:30, 10:00, 14:00 — so those windows are **declared**, with fixed
definitions, never searched. That is the discipline this repo applies to calendar structure: a
published regularity may enter as one pre-registered hypothesis, never as a grid axis. It identifies
*when* a release could have landed, never which one or what it said. **A real release calendar with
surprise values would upgrade this materially and is the single most valuable thing to add.**

**PEAD remains an analogue** — it is defined on single-name earnings surprises and cannot be
computed from index OHLCV.

---

## 1. The base

| market | tf | trades | R/trade | PF | win |
| --- | --- | --- | --- | --- | --- |
| US100 | 15m | 3,411 | +0.0819 | 1.130 | 29.6% |
| US100 | 30m | 1,917 | +0.1022 | 1.173 | 32.7% |
| US100 | 60m | 803 | +0.1585 | 1.281 | 34.6% |
| US30 | 60m | 742 | +0.2020 | 1.352 | 34.4% |

---

## 2. The models, on purged embargoed CV

A trade occupies [signal bar, exit bar] and those windows overlap, so every fold **purges** training
trades intersecting the test window and **embargoes** a further block. Without that the CV leaks.

**US100 15m** (2,207 research trades, baseline +0.0578 R):

| model | OOF IC | kept R | base R | lift | p vs random |
| --- | --- | --- | --- | --- | --- |
| **ridge** | **+0.0870** | +0.1799 | +0.0578 | **+0.1220** | **0.004** |
| lgbm | +0.0988 | +0.1398 | +0.0578 | +0.0819 | 0.034 |
| **mlp** | **+0.0203** | +0.0876 | +0.0578 | +0.0298 | 0.258 |

**The neural network loses to ridge on every timeframe** — IC +0.020 against +0.087 at 15m, and
**negative** at 30m (−0.055) and 60m (−0.074). With 506 to 2,207 trades against 39 features this is
the expected outcome and it is reported rather than buried: the net memorises, the linear model
wins, and "deep learning" bought nothing here.

**Frozen read, best model per timeframe:**

| tf | model | US100 LOCKED lift | p | US30 (unseen) lift | p |
| --- | --- | --- | --- | --- | --- |
| 15m | ridge | **+0.0774** | 0.099 | **+0.0376** | 0.144 |
| 30m | lgbm | **−0.0226** | 0.602 | +0.0953 | 0.021 |
| 60m | ridge | +0.0236 | 0.411 | +0.1239 | 0.054 |

Only 15m is coherent — positive on CV, locked and the unseen market, with the IC stable at +0.087 /
+0.086 / +0.073. **Neither holdout reaches p ≤ 0.05.** 30m fails its holdout outright. 60m is
negative for *all three models* on research and then "passes" out of sample, which this repo records
as a defect, not a result.

---

## 3. The ablation — which family does the work

US100 15m, ridge, purged CV then one locked read:

| feature set | k | CV IC | CV lift | CV p | LOCK lift | LOCK p | US30 lift | US30 p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **bo only** (breakout context) | 6 | **−0.0784** | +0.0220 | 0.307 | +0.0059 | 0.461 | +0.0364 | 0.168 |
| rp only (risk premia) | 20 | +0.0944 | +0.1047 | **0.006** | +0.0221 | 0.374 | +0.0672 | 0.034 |
| pead only | 9 | +0.0714 | +0.0892 | 0.022 | +0.0387 | 0.270 | **−0.0434** | 0.891 |
| news only (release clock) | 4 | **+0.1919** | +0.1057 | 0.009 | +0.0443 | 0.230 | +0.0401 | 0.135 |
| ALL FOUR | 39 | +0.0870 | +0.1220 | 0.003 | **+0.0774** | 0.117 | +0.0376 | 0.159 |
| **everything EXCEPT bo** | 33 | **+0.1170** | **+0.1522** | **0.000** | +0.0692 | 0.136 | +0.0352 | 0.164 |

**This answers the brief.** The breakout's own context features — excess over the channel, channel
width, ADX, CHOP, close position — carry **nothing** (CV IC −0.078, p 0.307), and *dropping them
improves the model* (+0.087 → +0.117 IC). The risk-premium, PEAD-analogue and release-clock material
is what the model is using. Coefficient mass confirms it: **rp 45.0%, pead 27.2%, news 19.9%,
bo 7.9%** — and `news` carries the highest mass per feature (mean |coef| 0.116 on just 4).

**And none of it survives.** Best locked p is 0.117; no family is significant on both holdouts.
**PEAD-only goes negative on the unseen market** (−0.0434, p 0.891) — the same verdict V47 reached
when the PEAD family's signs agreed with the holdout at exactly chance.

### The two largest coefficients

```
rp.tsmom960_vs   -0.19175      long-horizon momentum, NEGATIVE
news.in_window   -0.17069      avoid breakouts inside a release window
```

**Momentum enters negatively again** — the ninth independent route to mean reversion on this branch,
and the same inversion V47 measured directly.

---

## 4. Testing the strongest coefficient directly

`news.in_window` is interpretable, so it does not need the model. Breakouts inside a declared release
window against those outside:

| market | in-window worse? | detail |
| --- | --- | --- |
| **US100** | **6 of 6 cells** | −0.034 to −0.245 R, one at p 0.049 |
| **US30** | **3 of 6 — and it INVERTS** | 30m research +0.2296, locked +0.2555 (p 0.896, 0.947) |

Overall **8 of 12 cells worse against 6 expected**, **1 of 12 at p ≤ 0.05 against 0.6 expected**,
mean difference −0.0233 R.

**The model's strongest signal is a US100-specific artifact.** On the held-back market it reverses,
and on 30m US30 breakouts inside the release window earn *a quarter of an R more*.

---

## 5. Verdict

**Ships nothing.** What it establishes:

- **The requested families are what the model uses** — breakout context contributes nothing and
  removing it helps. If a filter for this base exists, it is in this material, not in the channel.
- **Nothing clears a same-selectivity control on both holdouts.** The one coherent cell (15m ridge)
  holds its sign and its IC across three blocks at p 0.099 / 0.144.
- **The neural network is beaten by ridge everywhere**, and negatively so at two of three
  timeframes.
- **PEAD inverts out of sample**, for the second study running.
- **The release-window effect does not transfer** between markets.

## Caveats

Nine feature sets × three blocks, three models × three timeframes, all uncorrected — the p-values
are draw-shares. US30's costs are assumed, not measured. The release windows identify timing only,
with no surprise magnitude or direction; that is the study's main limitation and the reason a real
release calendar is worth more than any further modelling here.

## Files

`research/v48/v48base.py` (Donchian base) · `v48feat.py` (39 features + truncation audit) ·
`v48ml.py` (purged embargoed CV, ridge / LightGBM / MLP) · `run_v48.py` · `results/v48/`.
