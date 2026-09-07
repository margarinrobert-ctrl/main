# Feature engineering, and what the features are actually worth

*What was built:* 48 new features in three families the existing library could not produce, taking
it from 86 to **134** — all causal, all proven so by recomputation rather than assertion.

*What they are worth:* on this instrument, essentially nothing for direct prediction, and the
measurement of that is the deliverable. One feature out of 1,072 tests survives multiple-testing
correction, and its edge is **4% of a round turn**. Meanwhile 134 features turn out to be about
**28 independent dimensions**.

---

## 1. What was added, and why each family exists

`features.build` works from the chart bar's OHLCV. Each new family needs something that bar does
not contain, and each was added because a specific result in this repository showed it carries
information the bar alone cannot.

| family | features | what it measures | why |
| --- | --- | --- | --- |
| **microstructure** | 9 | intrabar path efficiency, up-minute and up-volume share, realized variance against squared range, where in the bar the high and low printed, and their order | a 30-minute bar with a 40-point range is a different object depending on whether price walked there once or thrashed. None of that is recoverable from OHLC. |
| **semivariance** | 32 | RS+ / RS− split at 4 windows × 2 estimators × (raw, ratio, z-score, RS+ share) | `STUDY_SAM_SCALP.md`: on 5-minute bars the surviving edge is specifically in the **intrabar** semivariance, and the bar-return version of the same rule fails its matched control. That is a direct demonstration this family is not a reparameterisation of volatility. |
| **auction** | 7 | signed distances to prior POC / VAH / VAL in ATRs, position within prior and developing value | `STUDY_AUCTION.md` found no auction *condition* worth adding to a rule. "These carry no information" is a different claim, and the continuous versions let anyone test it. |

**Two bugs died in the leakage harness before any result existed.** The intrabar high/low position
was first computed with a Python loop over a million 1-minute bars and did not finish inside a
two-minute budget; it is a groupby now. More importantly, the semivariance family originally
imported its intrabar split from `newsignals`, which caches **by timeframe** — so a truncated
history returned full-length arrays and the leakage check compared a 25,004-bar series against a
35,721-bar one instead of catching a peek. Deriving it from the passed bars is both correct and
one pass cheaper. After both fixes: `leakage check: CLEAN`.

## 2. Do any of them predict? The protocol

Four things that are usually skipped, and each changes the answer:

1. **An overlap-aware standard error.** A forward return over *h* bars evaluated at every bar
   gives h-fold overlapping observations; a naive t-statistic on 35,000 of those is inflated by
   roughly √h. Newey-West with lag *h* is the minimum fix.
2. **Multiplicity, stated first.** 134 features × 4 horizons = **536 tests per timeframe**, so
   **27 clear p < 0.05 by chance**.
3. **Replication over significance.** The research block chooses nothing here, but a feature whose
   information coefficient keeps the **same sign** on the locked block has said something. Under
   the null that is a coin flip.
4. **Redundancy.** 134 features is not 134 dimensions.

Target: forward return over 1, 3, 6 and 12 bars, normalised by the ATR known at the decision bar —
because every strategy here sizes its barriers in ATRs, so "how far did it go" only means
something relative to how far it was moving anyway.

## 3. The answer

| | 30m | 15m |
| --- | --- | --- |
| tests | 536 | 536 |
| expected at p < 0.05 by chance | 27 | 27 |
| **survive Benjamini-Hochberg at q < 0.10** | **0** | **1** |

The single survivor, on 15-minute bars:

| feature | h | IC research | t | IC locked | t | q | sign |
| --- | --- | --- | --- | --- | --- | --- | --- |
| close position in bar | 1 | −0.020 | −4.27 | −0.032 | −5.01 | 0.011 | same |

A bar closing near its high is followed by a slightly *lower* next bar — textbook short-horizon
reversal, and it does keep its sign on the holdout. So: is it worth anything?

**Next-bar move by where the bar closed in its range, in ticks:**

| | 15m research | 15m locked | 30m research | 30m locked |
| --- | --- | --- | --- | --- |
| closed in low third | +0.72 | +4.51 | +0.18 | +5.64 |
| middle third | +0.99 | −1.61 | +1.30 | −0.43 |
| closed in high third | +0.44 | −1.04 | **+2.79** | −1.61 |
| **low minus high** | **+0.28** | +5.55 | **−2.61** | +7.24 |
| a round turn costs | **6.0 ticks** | | | |

On the **research block** — the only block allowed to inform a decision — the 15-minute effect is
**0.28 ticks against a 6.0-tick round turn**, four percent of costs. And the 30-minute version has
the **opposite sign** on research: bars closing strong were followed by *more* strength, +2.79
ticks. The locked block looks tradeable on both, and that is exactly the number nobody is allowed
to select on.

The one feature that survives 1,072 tests is a real microstructure effect that is far too small to
trade and unstable in sign across timeframes.

## 4. Redundancy: 134 features, 28 dimensions

| | 30m | 15m |
| --- | --- | --- |
| clusters at \|ρ\| ≥ 0.9 | 83 | 85 |
| principal components for 90% of variance | **28** | **28** |
| for 99% of variance | 74 | 75 |

Stable across timeframes. The largest clusters are the obvious ones and worth naming because they
show what is duplicated:

* `dist EMA20 / ATR` absorbs RSI14, RSI14 − 50, BB position and three more — **an oscillator and a
  normalised distance from a short moving average are the same measurement.**
* `return 2b / ATR` absorbs `return 2b`, `return 2b / vol` and **`SAM raw b2`** — at a 2-bar
  window the bar-return semivariance asymmetry *is* the 2-bar return. The intrabar version is not
  absorbed, which is the redundancy analysis independently confirming why the 5-minute result
  needed the intrabar estimator.
* `return 5b / ATR` absorbs `RS+ share b5`, same story one window out.

## 5. Do any features separate a winning trade from a losing one?

Every feature read at the **signal** bar (not `ent_bar`, which is the fill — see
`STUDY_AUCTION.md` for what that mistake produces), across the shipped strategies:

| | 30m | 15m |
| --- | --- | --- |
| trades (research block) | 581 | 217 |
| features tested | 134 | 134 |
| **survive BH at q < 0.10** | **0** | **0** |
| best research p | 0.043 (q 0.995) | 0.041 (q 0.992) |
| top feature | SAM ratio i2 | BB width / mean50 |

The top features **differ completely between timeframes**, which is the signature of noise: a real
separator would top both lists.

### A protocol bug in my own module, worth recording

The first version of `trade_separation` ranked features over **all** trades, both blocks. Its top
twelve on 30m were all the same family — 2-bar semivariance and 2-bar return — which looked like a
coherent finding, so it was carried to a single pooled test. That test came back:

    research  p(dollars) 0.0815   p(win rate) 0.1939
    LOCKED    p(dollars) 0.0235   p(win rate) 0.0280

**Passing on the holdout while failing on research is the wrong shape**, and the reason was that
the family had been chosen using a ranking that included holdout trades. Re-ranked on the research
block alone, the same family sits at p = 0.043 with q = 0.995 and nothing is carried anywhere.
`trade_separation` now defaults to `block="research"` and says why in its docstring.

## 6. What this library is actually for

1. **Not direct prediction.** One survivor in 1,072 tests, worth 4% of a round turn. Any pipeline
   that ranks these by IC and trades the top of the list is fitting noise, and the multiplicity
   figure — 27 by chance per timeframe — is why it will look like it is working.
2. **Conditioning and description**, which is what the rest of this repository uses features for:
   regime labels, matched controls, redundancy-aware selection, and explaining a rule after it has
   passed a holdout.
3. **The harness is the asset.** `leakage_check` caught two real bugs here before either could
   produce a number, and `sig_bar` prevents the fill-bar error that faked a p = 0.0005 result
   earlier in this branch. A feature library without both is a liability.
4. **Feature count is vanity.** 134 features are 28 dimensions. Adding a 135th correlated at 0.95
   with an existing one adds a test to the multiplicity budget and no information.

## Files

| | |
| --- | --- |
| `research/features.py` | the 86 base features (unchanged) |
| `research/features2.py` | microstructure, semivariance and auction families; `build_all`, `leakage_check` |
| `research/feature_eval.py` | IC with Newey-West and BH, redundancy clustering, trade separation |

Measured on MNQ, 2022-12-26 → 2025-12-12. Costs quoted as one tick spread plus one tick slippage
each side and $1.00 commission per round turn = 6.0 ticks. Research tooling for education and
analysis, not financial advice.
