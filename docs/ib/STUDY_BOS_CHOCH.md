# BOS / CHoCH on NQ index futures — full validation battery

**Verdict: WEAK EDGE.** Not tradeable at the timeframes the brief prioritises (1m, 5m), unproven at
15m/30m, and refuted at 60m by its own overfitting diagnostic. Nothing in this study survives
correction for the number of tests run.

Code: `research/bos_choch.py` (engine), `research/bos_report.py` (battery).

---

## 0. What could not be tested — stated before any result

**This repository contains NQ 1-minute bars only.** There is no ES, MES, or any second instrument.
The cross-instrument test — *"determine whether the edge survives across independent instruments…
if it works only on NQ, explicitly state that"* — **cannot be run.**

**It works only on NQ, because NQ is the only thing there is.** Every number below is one instrument
in one three-year bull market. MNQ figures are the same price series re-priced at $2/point with micro
commissions: that tests position sizing and cost sensitivity, and is **not independent evidence**.

Also unavailable: VIX (substituted with an ATR-percentile proxy) and per-contract data to verify the
vendor's roll adjustment.

---

## 1. Specification and the causality audit

```
LONG   two consecutive bullish BOS (close > last CONFIRMED swing high) while close > EMA(200).
       Enter at the OPEN OF THE NEXT BAR. Stop 2 x ATR(14) below entry.
       Exit on bearish CHoCH (close < relevant confirmed swing low) at the next open, or on the stop.
SHORT  mirror.
```

**No look-ahead, and the cost is measured.** A fractal swing at bar *t* needs *k* bars either side, so
it is not knowable until *t+k*. Pivots come from `smc.swing_pivots` (18 unit tests). The measured
consequence:

| timeframe | mean bars from authorising pivot to entry |
| --- | --- |
| 1m | **7.8** |
| 5m | **7.7** |
| 15m | 7.1 |
| 30m | 6.8 |
| 60m | 7.2 |

At k=3 the theoretical floor is 3 bars; the realised delay is ~7.7, because the break must also
happen *after* confirmation. On 1-minute bars that is nearly 8 minutes of the move already gone.

**Stop fills are not assumed.** A stop is a market order once touched: if the bar *opens* through it,
the fill is the open, not the stop price. Gap risk is charged. A separate 1-tick stop-slippage
allowance is added on top of entry costs.

**Costs:** $4.00 commission+fees per round turn, 1 tick spread, 1 tick entry slippage, 1 tick extra on
stop exits — ≈$24/round turn on NQ at the baseline.

---

## 2. Baseline (no parameters optimised) — NQ, RTH 09:30–16:00

| tf | n | net $ | $/trade | PF | win% | Sharpe | maxDD% | **t** | E[R] | gross $ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **1m** | 4,517 | −143,285 | −31.7 | 0.89 | 31.0 | −1.44 | 158.0 | **−2.45** | −0.004 | −34,877 |
| **2m** | 2,386 | −147,836 | −62.0 | 0.85 | 32.0 | −1.56 | 149.0 | **−2.68** | −0.030 | −90,572 |
| **5m** | 1,054 | −20,686 | −19.6 | 0.97 | 35.1 | −0.21 | 42.7 | −0.34 | −0.020 | +4,610 |
| **15m** | 418 | +37,261 | +89.1 | 1.12 | 42.6 | 0.46 | 42.0 | 0.76 | +0.038 | +47,293 |
| **30m** | 194 | +83,104 | +428.4 | 1.46 | 39.2 | 0.89 | 23.1 | 1.42 | +0.175 | +87,760 |
| **60m** | 59 | +81,452 | +1380.5 | 2.23 | 45.8 | 1.03 | 19.3 | 1.77 | +0.403 | +82,868 |
| 120m | 35 | −14,496 | −414.2 | 0.80 | 34.3 | −0.30 | 34.8 | −0.37 | +0.095 | −13,656 |

**The two timeframes with enough trades to say anything are significantly negative.** 1m and 2m are
the only cells in the entire study reaching |t| > 2, and both are losses. Performance rises
monotonically with timeframe while *n* collapses — 60m's Sharpe of 1.03 rests on **59 trades**.

**Is there a structural timeframe advantage?** E[R] also rises with timeframe (−0.004 → +0.403), so
this is not purely the cost ratio. But the rise is inseparable from the collapse in sample size, and
120m — the next step up — is *negative*. A genuine structural advantage would not stop at 60m.

---

## 3. Timeframe × session matrix (net $/trade, n in parentheses)

| tf | globex 24h | RTH | NY morning | NY afternoon | overnight | 09:30–10:30 | 09:30–11:30 | 10:00–12:00 | 13:30–16:00 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1m | −30.3 (15211) | −31.7 (4517) | −35.4 (1902) | −32.7 (2744) | −29.3 (10896) | **+7.8 (947)** | −30.2 (1582) | −67.0 (1519) | −23.2 (1784) |
| 2m | −37.4 (7689) | −62.0 (2386) | −107.9 (1065) | −33.4 (1456) | −26.7 (5527) | −16.4 (551) | −98.2 (921) | −133.0 (872) | −35.7 (971) |
| 5m | −21.9 (3010) | −19.6 (1054) | −6.8 (534) | −3.9 (697) | −17.3 (2190) | **+68.6 (233)** | +27.2 (436) | −6.3 (457) | −78.1 (507) |
| 15m | +51.0 (1000) | +89.1 (418) | −75.5 (163) | +113.8 (312) | +3.5 (772) | −177.9 (76) | −170.1 (129) | −119.3 (129) | +3.6 (217) |
| 30m | +111.8 (514) | **+428.4 (194)** | +780.4 (56) | +398.2 (151) | +98.0 (433) | — | +659.0 (49) | +780.4 (56) | +300.6 (109) |
| 60m | +226.9 (252) | +1380.5 (59) | — | +800.9 (50) | +47.5 (239) | — | — | — | +1502.5 (36) |
| 120m | −755.1 (135) | −414.2 (35) | — | −414.2 (35) | −737.8 (124) | — | — | — | — |

**This table is 72 tests.** A Bonferroni threshold at 5% requires **|t| > 3.4**; the largest |t|
anywhere in the study is 2.68, and it is negative. The 09:30–10:30 window is the only place the fast
timeframes turn positive, and the two cells disagree with their neighbours in every direction —
the signature of noise, not of a session effect.

---

## 4. The random-entry control — the decisive test

Coin-flip entries, identical count, identical long/short mix, identical 2×ATR stop, identical CHoCH
exit, identical costs. 200 replications.

| tf | BOS net $ | random mean | random sd | random 95th | **BOS percentile** |
| --- | --- | --- | --- | --- | --- |
| 5m | −20,686 | −2,124 | 46,291 | 64,868 | **35.0%** |
| 15m | +37,261 | +6,538 | 39,943 | 72,575 | 78.5% |
| 30m | +83,104 | −3,827 | 42,369 | 72,074 | **98.0%** |
| 60m | +81,452 | −2,220 | 27,256 | 40,589 | **99.0%** |

**At 5m, BOS is worse than a coin flip.** Random entries with the same risk management beat it 65% of
the time. The signal is not merely weak there — it is anti-informative.

At 30m and 60m, BOS clears the control at ~2% and ~1%. That is the strongest positive evidence in
this study. It is also **1 of 4 timeframes tested**, so the corrected significance is ~0.04–0.08, and
the control's standard deviation ($42k, $27k) is half the effect being measured — the test has very
little power.

---

## 5. Parameter stability

**Stable axes.** At 30m and 60m the EMA × ATR-multiple surface is a broad plateau: every one of 36
cells at 30m is positive (+$160 to +$544/trade), and every one at 60m (+$531 to +$1,743). That is a
genuine plateau, unlike the trend-pullback study where 35 of 37 neighbours flipped sign.

**One fragile axis, and it is the one that defines the strategy.** Swing length `k`:

| tf | k=2 | k=3 | k=5 | k=8 | k=12 |
| --- | --- | --- | --- | --- | --- |
| 5m | −61.2 | −19.6 | −15.4 | −39.4 | **+67.7** |
| 15m | −25.8 | +89.1 | +333.6 | **+369.4** | +149.6 |
| 30m | +431.1 | +428.4 | +505.5 | **+31.4** | **+68.8** |
| 60m | +727.3 | +1380.5 | +716.6 | — | — |

The best `k` is 12 at 5m, 8 at 15m, 5 at 30m, 3 at 60m — a different answer at every timeframe, with
sign flips between adjacent values. **Swing length is what "market structure" means**, and it has no
stable setting.

---

## 6. Walk-forward, by calendar quarter

Every out-of-sample block, reported separately.

**5m** — 13 quarters, 4 positive, cumulative **−$20,686**. Never above water after 2023-Q1 except a
brief crossing in 2025-Q3.

**15m** — cumulative **−$38,055 by 2024-Q1**, then recovers to +$37,261. A single quarter
(2024-Q4, n=39) contributes **+$44,019** — more than the entire final total.

**30m** — cumulative −$19,030 by 2023-Q2, then climbs to +$83,104. **Three of twelve quarters
(2024-Q4, 2025-Q2, 2025-Q4) provide $77,859 — 94% of all profit.** The last of those is **7 trades
producing $20,249.**

That is concentration, not consistency. A strategy whose three-year result rests on three quarters
has not demonstrated an edge; it has demonstrated that three quarters were favourable.

---

## 7. Regime analysis

| regime | 5m | 15m | 30m |
| --- | --- | --- | --- |
| high ATR (>66th pct) | −12.7 (t −0.21) | +87.8 (t 0.70) | +570.0 (t 1.55) |
| **far from EMA200 (>2 ATR — trending)** | **+108.0 (t 1.38)** | **+239.3 (t 1.59)** | **+659.0 (t 1.64)** |
| **near EMA200 (<1 ATR — ranging)** | **−474.2 (t −5.26)** | −304.7 (t −1.55) | −480.4 (t −0.88) |
| above EMA200 (bull) | +74.2 (t 1.04) | +330.8 (**t 2.17**) | +385.3 (t 1.59) |
| below EMA200 (bear) | −137.1 (t −1.41) | −203.7 (t −1.13) | +481.3 (t 0.95) |

**The single strongest statistic in this entire study is −$474/trade at t = −5.26**: BOS/CHoCH in a
range, at 5m. That is the one result that would survive Bonferroni, and it is a *loss*. A consistent
negative is worth more than an inconsistent positive: **do not run this in a range.**

**Where does the edge come from?** Not from market structure — from *already being in a trend*. The
"far from EMA200" bucket is positive at every timeframe and the "near EMA200" bucket negative at
every timeframe. That is close to tautological for a trend-following rule, and it means the hidden
exposure is **trend persistence**, not BOS information. Confirming it: the bull/bear split at 5m and
15m is strongly asymmetric (long side positive, short side negative), which is the 2022–25 NQ uptrend.

---

## 8. Ablation — no component has a consistent contribution

Change in $/trade when a component is removed or altered:

| change | 5m | 15m | 30m | 60m | consistent? |
| --- | --- | --- | --- | --- | --- |
| remove EMA-200 filter | +1.6 | **−47.7** | **+31.0** | −583.9 | **no** |
| enter on 1st BOS instead of 2nd | −25.5 | −55.9 | −226.5 | −827.5 | yes (2nd better) |
| enter on 3rd BOS instead of 2nd | **+108.6** | **−201.3** | +528.2 | −311.0 | **no** |
| remove ATR stop | −10.1 | −21.8 | −103.1 | **+164.1** | **no** |
| remove CHoCH exit | **+26.5** | **+146.1** | **−257.3** | −741.8 | **no** |

**Four of five components change sign across timeframes.** Only "the second BOS beats the first"
holds everywhere — and at 5m and 30m the *third* BOS beats the second, so it is really "more
confirmation is better", i.e. trade less, which is a cost statement rather than a structure one.

Long/short decomposition:

| tf | longs only | shorts only |
| --- | --- | --- |
| 5m | +$29,985 | −$50,671 |
| 15m | +$83,871 (t 2.22) | −$46,610 (t −1.37) |
| **30m** | **+$44,072** | **+$39,033** |
| 60m | +$65,666 (t 3.64) | +$15,786 (t 0.44) |

30m is the **only** timeframe where both sides work. Everywhere else the result is the long side, and
the long side is the index.

---

## 9. Monte Carlo, bootstrap, and probability of backtest overfitting

| tf | net $ | bootstrap 95% CI ($/trade) | P(edge ≤ 0) | median MC DD | p95 MC DD | P(loss) | risk of ruin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5m | −20,686 | [−121.2, +87.4] | 64.7% | 54.7% | 81.5% | 100.0% | 0.0% |
| 15m | +37,261 | [−126.0, +311.5] | 22.0% | 27.1% | 44.4% | 0.0% | 0.0% |
| 30m | +83,104 | [−79.7, +1015.4] | **5.1%** | 18.8% | 33.0% | 0.0% | 0.0% |
| 60m | +81,452 | **[+18.9, +3058.4]** | **2.3%** | 11.0% | 19.5% | 0.0% | 0.0% |

60m is the only cell whose bootstrap CI excludes zero. Then:

| tf | **PBO** | median OOS rank of the in-sample winner |
| --- | --- | --- |
| 5m | 0.700 | 0.444 |
| **15m** | **0.014** | 0.815 |
| 30m | 0.471 | 0.537 |
| **60m** | **0.814** | **0.111** |

**This is the study's decisive contradiction.** The timeframe with the only significant bootstrap CI
(60m) has **PBO 0.814** — the configuration that looks best in-sample lands in the bottom half out of
sample 81% of the time, and at a median rank of 0.111. Its apparent edge is a selection artifact.

Conversely 15m has an excellent PBO of 0.014 — its selection procedure genuinely generalises — but
its edge is not significant (t = 0.76, 22% chance the true edge is ≤ 0). 30m sits at PBO 0.471, which
is a coin flip: the selection carries no information either way.

**No timeframe has both a significant edge and a trustworthy selection procedure.**

---

## 10. Cost and slippage sensitivity

| tf | 0× (gross) | 0.5× | 1× (baseline) | 1.5× | 2× | break-even multiple |
| --- | --- | --- | --- | --- | --- | --- |
| 5m | +6,795 | −6,945 | −20,686 | −34,426 | −48,167 | **0.3×** |
| 15m | +47,953 | +42,607 | +37,261 | +31,915 | +26,569 | 4.5× |
| 30m | +88,010 | +85,557 | +83,104 | +80,651 | +78,198 | >6× |
| 60m | +82,938 | +82,195 | +81,452 | +80,709 | +79,966 | >6× |

**5m dies at 30% of realistic costs** — its entire gross edge of $6,795 is consumed three times over.
30m and 60m are almost cost-insensitive because they trade 194 and 59 times in three years. That
robustness is real but it is a consequence of rarity, not of signal quality.

---

## 11. Position sizing — and why NQ is the wrong contract for this

Median 2×ATR stop: **78.4 points at 15m, 100.1 points at 30m.**

| | risk per 1 contract (median) | $100 risk | $200 | $300 | 0.25% of $100k | 0.50% | 1.00% |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **NQ 15m** | **$1,567** | 100% untradeable | 100% | 100% | 100% | 100% | 93% |
| **MNQ 15m** | $157 | 93% untradeable | 27% | 9% | 14% | 1% | 0% |
| **NQ 30m** | **$2,003** | 100% untradeable | 100% | 100% | 100% | 100% | 99% |
| **MNQ 30m** | $200 | 99% untradeable | 51% | 21% | 31% | 2% | 1% |

**A 2×ATR stop on NQ cannot be risked at $100–$300 per trade.** One contract risks $1,567–$2,003, so
every signal rounds to zero contracts. Even 1% of a $100,000 account ($1,000) leaves 93–99% of
signals untradeable.

**MNQ is the only way to express this strategy at retail risk sizes.** At $300 fixed risk MNQ gives
1.48 contracts on average at 15m. This is a genuine, actionable finding: the brief's risk levels are
incompatible with the full-size contract.

---

## 12. Failure modes

1. **Ranges.** −$474/trade at t = −5.26 when price is within 1 ATR of the EMA200 (5m).
2. **Fast timeframes.** 1m and 2m are significantly negative; 5m is beaten by random entries.
3. **Confirmation delay.** ~7.7 bars from authorising pivot to fill — on 1-minute bars, most of the move.
4. **Concentration.** 94% of the 30m result comes from 3 of 12 quarters; one contributes $20,249 on 7 trades.
5. **Short side.** Negative at 5m, 15m and (weakly) 60m. Only 30m has a working short side.
6. **Contract size.** Untradeable on NQ at the brief's risk levels.
7. **Selection fragility.** Swing length `k` has a different optimum at every timeframe.

---

## 13. Final verdict

### **WEAK EDGE**

Per timeframe:

| timeframe | classification | reason |
| --- | --- | --- |
| 1m, 2m | **OVERFIT / NO EDGE** | significantly negative (t = −2.45, −2.68) |
| 5m | **NO EDGE** | worse than random entries (35th pct); dies at 0.3× costs; PBO 0.70 |
| 15m | **PROMISING BUT UNPROVEN** | good PBO (0.014) but t = 0.76, 22% chance of no edge, one quarter carries it |
| 30m | **PROMISING BUT UNPROVEN** | beats random at 98th pct, P(edge≤0) 5.1%, both sides work — but PBO 0.471 and 94% of profit from 3 quarters |
| 60m | **OVERFIT** | best headline, **PBO 0.814**, n = 59 |

**Overall: WEAK EDGE**, and specifically weak *where the brief wants it*. The objective was intraday
futures scalping at 1m–30m. The strategy is significantly negative at 1m–2m, anti-informative at 5m,
and only suggestive at 30m — which is no longer scalping at 194 trades in three years.

**Does market structure provide predictive information?** The evidence says: **not by itself.** The
regime table shows the returns come from already being in a trend, not from where the swings broke;
the ablation shows four of five components flip sign across timeframes; and the one component that
holds everywhere ("require more confirmation") is a statement about trading less, not about
structure.

**What would change this verdict:** ES data. A rule that is genuinely structural should work on the
S&P as well as the Nasdaq, and one instrument in one bull market cannot distinguish "market
structure works" from "2023–25 NQ trended". That test costs nothing but the data and is worth more
than every table above.

### The simplest version that is not refuted

Not recommended for capital, but this is what the evidence points at if anything:

> **30-minute NQ, RTH 09:30–16:00.** Swing k = 3. Enter on the second BOS in the prevailing
> direction, at the next bar's open. EMA-200 filter **optional** (removing it improved results:
> +$459 vs +$428/trade). Stop 2 × ATR(14). Exit on CHoCH. Both sides. Traded on **MNQ**, not NQ,
> at 0.5% account risk.
>
> n = 194 over 3 years, +$428/trade, PF 1.46, Sharpe 0.89, max DD 23.1%, **t = 1.42**,
> bootstrap 95% CI [−$79.7, +$1015.4], PBO 0.471.
>
> Add the one filter that replicated: **skip entries within 1 ATR of the EMA-200.**

The t-statistic does not reach 2, the CI contains zero, and the selection procedure carries no
information. It is a hypothesis, not an edge.

---

## 14. Reproduce

```bash
python3 research/bos_report.py     # baseline, timeframe x session, stability, control, ablation, WF, regime
```
