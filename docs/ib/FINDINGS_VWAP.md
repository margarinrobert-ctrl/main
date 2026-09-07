# VWAP bands on NQ — mean reversion, and a hypothesis that failed

Full report: [`STUDY_VWAP.md`](STUDY_VWAP.md). Strategy: `src/lib/quant/strategies/vwapBands.ts`.

5-minute NQ, 766 RTH sessions split 537 research / 229 holdout, realistic fills, 3.80-tick round turn.

## Short answer

Fading VWAP bands on NQ **loses consistently and significantly**. Thirteen pre-specified variants,
covering both band constructions, both entry timings and four anchor windows — none is tradeable.

## 1. What "VWAP bands" means, tested both ways

The classical construction is **volume-weighted sigma**: the dispersion of typical price around VWAP
so far this session, weighted by volume, so the bands widen when heavy volume trades away from the
average. The common alternative is **VWAP ± k × ATR**, which knows about bar range and nothing about
where volume traded. Both are implemented, plus the wider of the two.

| # | variant | research | holdout |
| --- | --- | --- | --- |
| 1 | sigma k2, enter on the stretch | −6.6t, PF 0.85, **t=−3.73** | −6.6t, PF 0.90 |
| 2 | sigma k2, wait for close back inside | −4.1t, PF 0.90, **t=−2.12** | −9.2t, PF 0.86 |
| 3 | ATR k2, enter on the stretch | −6.0t, PF 0.86, **t=−3.84** | −8.0t, PF 0.87 |
| 4 | ATR k2, wait for close back inside | −5.3t, PF 0.88, t=−1.97 | −11.0t, PF 0.82, t=−2.70 |
| 5 | wider of both, confirmed | +2.1t, PF 1.04 | −1.1t, PF 0.99 |
| 6 | sigma k2.5, confirmed | −8.7t, PF 0.79, **t=−3.45** | −5.4t, PF 0.91 |
| 7 | sigma k2, target only halfway to VWAP | −7.1t, PF 0.81, **t=−4.55** | −12.7t, PF 0.79, t=−2.72 |
| 8 | sigma k2, calm regime only | −2.8t, PF 0.93 | −10.8t, PF 0.84 |
| 9 | sigma k2, after the first hour only | +2.2t, PF 1.05 | −2.9t, PF 0.96 |

Neither band construction rescues the other, and the ATR version is not an improvement — variant 3
is the second-worst result in the table. Waiting for confirmation (a close back inside the band)
helps a little and not enough.

## 2. A hypothesis, stated in advance, and its failure

The alpha stage measured mean reversion at a specific horizon: **VR(10) = 0.928 (z = −2.81)** and
VR(20) = 0.918. Session-anchored VWAP by mid-afternoon aggregates five or six hours of trade — far
longer than that. So the prediction was: **an anchor matching the 10–20 bar horizon should beat the
session anchor.**

Same rule, only the anchor changed:

| anchor | research | holdout |
| --- | --- | --- |
| session-anchored VWAP | −4.1t, t=−2.12 | −9.2t, t=−1.61 |
| rolling **12**-bar VWAP | −3.4t, t=−1.93 | −1.7t, t=−0.40 |
| rolling **20**-bar VWAP | −5.6t, t=−2.17 | −4.9t, t=−0.95 |
| rolling **40**-bar VWAP | **+4.1t, t=1.31** | **+3.7t, t=0.42** |

**The hypothesis failed.** The horizons it predicted would work (12 and 20 bars) are negative; the
only positive anchor is 40 bars — roughly 3.3 hours, which is *longer* than the horizon the variance
ratio pointed at, not shorter. The mechanism I proposed does not explain the result.

The 40-bar row is one of four tested, significant in neither half. Retrofitting a story onto it would
be exactly the error this whole protocol exists to prevent, so it is recorded as noise.

## 3. Volume weighting does not earn its keep

The best mean-reversion result on this data remains `ou-reversion`, a plain rolling **simple** mean
with a z-score entry and the mean as the target:

| | research | holdout |
| --- | --- | --- |
| ou-reversion (20-bar simple mean, z ≥ 2.5) | +12.4t, PF 1.13, t=1.65 | +6.4t, PF 1.05, t=0.42 |
| best VWAP-band variant (rolling 40) | +4.1t, PF 1.08, t=1.31 | +3.7t, PF 1.05, t=0.42 |

Volume-weighting the anchor did not help. Neither is significant; the simple mean is simply less bad.

## 4. Full protocol

| | result |
| --- | --- |
| best of 800 configurations, in-sample | Sharpe 2.19 |
| same procedure, walk-forward | Sharpe **−1.04**, −16.5 ticks/trade, PF 0.782 |
| walk-forward efficiency | −0.56 |
| folds profitable | 29% |
| PBO | 0.234 |
| deflated Sharpe | 0.000 |

Note PBO of 0.234 here — the *lowest* of any study in this repo, meaning selection was comparatively
informative. It still produced a walk-forward Sharpe of −1.04, because a selection procedure can be
informative about which configuration is least bad while every configuration is still bad.

## 5. A bug worth recording

The first run of variants 1 and 3 reported win rates of **1–4%**. That was not a finding, it was a
defect: on a knife-catch entry price has already closed well beyond the band, so the band-derived
stop could land on the *wrong side of the fill* and stop the trade out instantly. The stop is now
clamped to sit at least half an ATR beyond the entry.

The tell was the win rate. A 1% win rate is not a bad strategy, it is a broken one, and any number
that implausible should be treated as a bug until proven otherwise.

## 6. Where this leaves mean reversion on NQ

Reversion at the 10–20 bar horizon is real and measured (VR z = −2.81). Every attempt to monetise it
— session VWAP, rolling VWAP, sigma bands, ATR bands, rolling simple mean — lands between −16 and
+12 ticks per trade, with no configuration significant out of sample. The effect exists and is
smaller than the cost of trading it, which is the same conclusion the very first study reached from
the predictability budget.
