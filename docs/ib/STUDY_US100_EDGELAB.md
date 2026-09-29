# US100 morning-session edge lab: 27,786 tests, one candidate left standing, and it is not 80%

*A 54-section brief asked for a long-only US100 scalping edge between 07:00 and 11:00 New York,
targeting roughly 1:1 with a win rate at or above 80% — with the explicit instruction that 80% is
a filter, not an assumption, and that a negative result must be reported as one.*

**It is a negative result, with one qualified exception.** No configuration reached 80%. The best
out-of-sample number in the study is **56.9% at a 1.5R target over 109 trades**, and it was
selected out of 27,786 tests, so even that is a candidate rather than an edge.

`research/edgelab/`. One command: `python3 research/edgelab/run_all.py`.

---

## 1. What the data can and cannot answer

The supplied file is **US100 CFD, 15-minute, 2016-11-14 → 2025-10-01, 206,703 bars**. Clean: 0
duplicate stamps, 0 OHLC violations, 0 non-positive prices, 0.09% zero-range bars, 1.40% off-grid
gaps (weekends and holidays).

Three limits are structural and are stated before any result:

* **It is 15-minute only.** Brief §38 asks for 1-minute data at final validation and §39 for a
  1m/3m/5m entry timeframe. Neither is possible. The consequence is measured rather than waved at
  — see §2.
* **`Volume` is identically zero.** `TickVolume` is a broker tick *count*, not centralised
  exchange volume, so every volume feature is prefixed `tick_` and none of it is comparable to
  futures volume (brief §12).
* **It is a CFD feed and is kept separate from the NQ futures series in this repo** (brief §1).
  They are not mixed. This branch has already established that the stored NQ price *levels* are
  synthetic; nothing here depends on NQ.

**The clock is verified, not assumed** (brief §2). The file stamps are a broker wall clock, not
UTC. `data.verify_clock()` locates the 09:30 activity step separately in Dec–Feb and Jun–Aug: both
land on hour 9 after a constant −7h shift, so the broker follows US daylight saving and the fixed
shift is right year-round. Had they disagreed, the fixed offset would have been wrong for half of
every year.

## 2. The two measurements that constrain everything else

**Costs eat the target.** Charged as a fraction of the stop distance (spread 1.0pt RTH / 2.0pt
pre-RTH, 0.25pt entry slip, 0.75pt stop slip — a broker *assumption*, not a measurement, since
OHLC bars carry no spread):

| stop | median stop | cost in R | win rate needed to break even at 1:1 | actual base rate, gross |
| --- | ---: | ---: | ---: | ---: |
| 0.25×ATR | 4.3 pt | 0.90 R | **95.1%** | 27.0% |
| 0.35×ATR | 3.9 pt | 0.68 R | 84.0% | 27.0% |
| 0.50×ATR | 5.5 pt | 0.47 R | **71.5%** | 42.1% |
| 1.00×ATR | 11.1 pt | 0.24 R | 61.9% | 47.0% |
| 2.00×ATR | 22.1 pt | 0.12 R | 55.9% | 49.9% |
| 2.50×ATR | 27.7 pt | 0.10 R | **54.8%** | 50.9% |

A true scalp — a 4-point stop — needs a **95% win rate** to break even on this cost model. That is
the single most important number in the study, and it is arithmetic, not opinion: the tighter the
stop, the larger the fixed round trip looms against it.

**At tight stops the 15-minute bar cannot resolve the trade.** When a bar's low touches the stop
*and* its high touches the target, OHLC cannot say which came first. Brief §38 forbids resolving
that favourably, so the rule here is **stop first, always**, and every trade carries an `ambig`
flag:

| stop | 0.25×ATR | 0.35×ATR | 0.50×ATR | 0.75×ATR | 1.0×ATR | 1.5×ATR | 2.5×ATR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ambiguous | **47.4%** | 31.0% | 16.7% | 8.6% | 6.5% | 4.0% | 0.9% |

At 0.25×ATR nearly half the outcomes are set by the tie-break rather than by the market. **Any
result at a sub-0.5×ATR stop is unmeasurable on this file**, whichever way it points. Everything
below uses 1.5×ATR, where the ambiguous share is 4.0% and 0.0% for the surviving rules.

## 3. When in the morning a long actually works

Every eligible bar, no rule, discovery block, 1.0×ATR / 1:1 (brief §8, §29):

| bucket | 07:00 | 07:30 | 08:00 | 08:30 | 09:00 | 09:30 | 10:00 | 10:30 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| win % | 46.2 | 45.1 | 44.5 | 44.7 | **38.5** | 47.2 | 51.8 | **52.8** |
| E[R] | −0.46 | −0.48 | −0.48 | −0.45 | −0.51 | −0.21 | −0.09 | **−0.06** |
| ambiguous % | 1.2 | 2.5 | 6.7 | 10.3 | **26.1** | 4.1 | 0.6 | 0.2 |

Three things, none of them assumed in advance:

1. **Expectancy rises monotonically through the morning.** The briefed window's first two hours
   are its worst part.
2. **09:00–09:30 is the worst bucket and is also the least measurable** — 26% ambiguous, the
   pre-open volatility spike straddling both barriers inside one bar.
3. **Nothing is positive.** The best bucket is still −0.06R. This confirms and sharpens a result
   this branch already had on NQ (`STUDY_TREND_PULLBACK.md`): trade the late morning, not the
   pre-market — but the late morning is only *less bad* as a baseline.

Other descriptive answers: wider stops beat tighter ones monotonically (a cost effect, §2);
expectancy is nearly flat across targets 0.5R–2.0R (−0.37 to −0.30); **median holding time is one
bar**, so a maximum-hold rule beyond ~2 bars changes nothing (brief §41, §42); winners' MAE 90th
percentile is 0.82R against losers' median 1.44R (brief §17, §19).

## 4. The search, and the reason its p-values do not mean what they look like

101 causal features → 726 binary conditions → singles, then pairs and triples seeded from
survivors, across **3 windows × 6 geometries = 27,786 tests**, all on the discovery block
(2016-11 → 2021-12). Every candidate scored against a **minute-of-day matched control**, because
the base rate varies by 15 points across this window and a rule that fires at 10:30 inherits
10:30's base rate.

**17,121 of 27,786 tests "passed" Benjamini-Hochberg at q=0.10.** That is not 17,121 discoveries;
it is a symptom. Two causes, both fixed:

* **Trades inside one session are not independent.** The top rules fire 2–3 times a day on the
  same move. The unit of inference is the **day**, so `fast.score_days` compares mean-R-per-day
  and its control resamples *days*, matching clustering as well as timing.
* **The top 25 was one rule wearing 25 hats** — the same trades reached through permuted
  conditions. Candidates are collapsed by trade-set Jaccard overlap above 0.5.

## 5. What survived, and what did not

Five distinct candidates, frozen after discovery — conditions, thresholds, geometry, window — then
measured on blocks that had never been read:

| rule (1.5×ATR stop, 1.5R target) | disc n / win | **valid** n / win / E[R] | **prod** n / win / E[R] |
| --- | ---: | ---: | ---: |
| `dist_pdc>5.50 AND pos_in_range20>0.859 AND roc20>2.96` | 260 / **65.0%** | 63 / 46.0% / −0.02 | 95 / 46.3% / +0.08 |
| `dist_pdc>5.50 AND dist_orh15>0.19 AND dist_sess_high>−0.40` | 229 / **63.8%** | 51 / 47.1% / −0.01 | 82 / 47.6% / +0.09 |
| `bos_up AND dist_pdh>1.88 AND dist_pdc>5.50` | 161 / **63.4%** | — | 44 / 50.0% / +0.15 |
| **`dist_ema50>2.68 AND or60_broken_up AND roc20>2.96`** | 161 / **65.2%** | 59 / **54.2%** / +0.14 | 50 / **60.0%** / +0.37 |
| `dist_pdl>8.53 AND dist_sess_high>−0.40 AND dist_low20>4.34` | 152 / **61.8%** | 50 / 50.0% / +0.09 | 53 / 47.2% / +0.12 |

**Four of five collapse to their control.** Discovery win rates of 62–65% become 46–50% out of
sample, which is the base rate. That is the textbook overfit signature and it is what 27,786 tests
buys you.

Half-year buckets from 2022 — the only folds whose thresholds were fixed before the data was seen:

| | 2022H1 | 2022H2 | 2023H1 | 2023H2 | 2024H1 | 2024H2 | 2025 | **all** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| candidate 1 | −0.75 | +0.31 | +0.21 | −0.18 | +0.68 | +0.37 | **−0.27** | +0.04 |
| candidate 2 | −0.66 | +0.13 | +0.54 | −0.63 | +0.23 | +0.35 | **−0.15** | +0.05 |
| candidate 5 | +0.02 | −0.18 | +0.44 | −0.41 | +0.25 | +0.74 | **−0.24** | +0.11 |
| **candidate 4** | −0.32 | +0.04 | +0.40 | +0.11 | +0.43 | +0.46 | **+0.22** | **+0.25** |

*(E[R] per trade)*

Candidate 4 — **an opening-range breakout held above the 50 EMA with 20-bar momentum** — is
positive in **6 of 7** half-years including 2025, where every other candidate is firmly negative.
109 out-of-sample trades, 56.9% win, +0.248R per trade, +27.0R total.

## 6. Why candidate 4's p-value must not be read at face value

Three separate reasons, all of which cut the same way:

1. **It was picked by looking at production.** The Monte Carlo and importance analysis below rank
   candidates by their production expectancy. That is selection on the block brief §47 reserves
   for a single final read. The mitigation is that **all five candidates' out-of-sample columns
   are reported above**, so the shortlist is visible rather than just its winner — but "best of
   five, chosen after the fact" is not a clean 0.052.
2. **It is one survivor of 27,786 tests.** Its production p of 0.052 is nowhere near surviving
   that multiplicity, and its validation p is 0.383.
3. **The rolling walk-forward inside discovery is contaminated.** It shows 5/6 folds positive at
   +0.33R — but the thresholds were chosen on the whole discovery block, so folds 0–3 are
   in-sample for that choice. **Only folds 4 and 5 (2022, 2023) are meaningful, and they are the
   two weakest** (−0.10 and +0.28). The honest walk-forward is §5's half-year table, not this one.

**Bootstrap on the 109 out-of-sample trades** (resampled with replacement — permuting trade order
cannot change the endpoint, and an earlier version of this function reported a permutation
"endpoint distribution" 0.6R wide, which was meaningless):

| | mean R p05 | mean R p50 | mean R p95 | P(edge ≤ 0) | median DD | 95th DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| candidate 4, OOS | +0.068 | +0.248 | +0.431 | 1.1% | 6.4R | 10.3R |

That 1.1% is conditional on these 109 trades being an unbiased sample of the rule's future, which
selection makes unlikely.

**Condition contribution** (brief §26), dropping each in turn:

| dropped | discovery ΔE[R] | out-of-sample ΔE[R] |
| --- | ---: | ---: |
| `dist_ema50_atr>2.677` | +0.123 | +0.058 |
| `or60_broken_up==1` | **+0.229** | **+0.103** |
| `roc20_atr>2.961` | +0.089 | **−0.050** |

The opening-range breakout carries the rule on both blocks. **The momentum condition is worth
*negative* expectancy out of sample** — dropping it improves the result — so the third leg is
fitted, not real.

## 7. The anomaly engine, and the hypothesis the brief named

Anomalies are classified `NORMAL / UNUSUAL / EXTREME` by **trailing** robust z (median/MAD), never
deleted, and each class measured separately (brief §14, §15). Nine families, split by sign.

The brief asks specifically whether *a large bearish impulse in a bullish trend → stabilisation →
bullish recovery* is a setup, and instructs that the data decide. **It decides against it.** On
discovery, an extreme bearish body is the single worst long condition tested: **38.1% win against
a 48.4% control, −10.3 excess, −0.365R**. Large down bars continue down; they do not recover.

Its mirror was the only anomaly with positive expectancy — an **extreme bullish body**, 59.4% win
against 48.7%, +0.061R, p 0.000. It does not survive either:

| | n | win | control | excess | E[R] | p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| discovery | 170 | 59.4% | 48.7% | +10.7 | +0.061 | 0.000 |
| validation | 64 | 50.0% | 48.7% | +1.3 | −0.054 | 0.375 |
| production | 54 | 53.7% | 48.2% | +5.5 | −0.010 | 0.268 |

So **extreme momentum produces continuation, not exhaustion** (brief §6) — but only in the block
where it was found.

## 8. Verdict

Under brief §46's labels:

| | status |
| --- | --- |
| 80% win rate at 1:1 after costs | **REJECTED** — nothing reached it; the arithmetic in §2 shows a true scalp needs 95% |
| candidates 1, 2, 3, 5 | **REJECTED** — out-of-sample win rates equal their control |
| extreme-bullish-body anomaly | **REJECTED** — excess survives, expectancy does not |
| candidate 4 (ORB + 50 EMA + momentum) | **PROMISING** — never ROBUST |

`ROBUST` was defined before the results were seen and requires positive out-of-sample expectancy,
a positive walk-forward aggregate, and adequate sample. Candidate 4 meets the first two and fails
the third: 109 out-of-sample trades, one survivor of 27,786 tests, chosen partly by looking at
production, with one of its three conditions actively harmful out of sample.

**What would change the answer**, in order of value:

1. **1-minute US100 data.** It removes the §2 ambiguity ceiling (47% at a scalping stop), which is
   the hard constraint on the brief's actual target. Nothing else unlocks a tight stop.
2. **Re-run the shortlist with production held back properly.** Candidate 4 should be re-frozen
   from discovery+validation only and read once on 2024–2025 — a clean test this study cannot now
   perform on that block, because it has been looked at.
3. **Drop the momentum leg.** `roc20_atr>2.961` costs 0.050R out of sample. A two-condition
   version of candidate 4 is the first thing to test on new data.
4. **Give up on 80%.** At 1:1 after realistic costs the break-even is 55–62% depending on stop,
   and the observed ceiling on unseen data is 57%. A 1.5R target with a ~57% win rate is a
   materially better-posed objective than 1:1 at 80%, and it is the one the data actually offers.

## Files

| | |
| --- | --- |
| `research/edgelab/data.py` | loader, DST-verified clock, itemised CFD cost model |
| `research/edgelab/features.py` | 101 causal features (price, volatility, trend, momentum, structure, session, opening range, tick activity) |
| `research/edgelab/labels.py` | triple-barrier in R, MFE/MAE, ambiguity accounting, cached outcome tensor |
| `research/edgelab/audit.py` | truncation-based look-ahead audit |
| `research/edgelab/splits.py` | discovery / validation / production, purged and embargoed walk-forward |
| `research/edgelab/anomaly.py` | trailing robust-z classification and anomaly→edge table |
| `research/edgelab/discover.py` | condition generation, matched control, conditional probability |
| `research/edgelab/fast.py` | cached-outcome scoring, day-clustered control, exactness assertion |
| `research/edgelab/validate.py` | Frozen rules, walk-forward, Monte Carlo, parameter surface, status labels |
| `research/edgelab/live.py` | frozen-rule signal preview; sends no orders |
| `research/edgelab/run_all.py` | the whole pipeline in one command |

Measured on US100 CFD 15-minute data, 2016-11 → 2025-10, one unit, costs as stated in §2 and
assumed rather than measured. Research tooling for education and analysis, not financial advice.
