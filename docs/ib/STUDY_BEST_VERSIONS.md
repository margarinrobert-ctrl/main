# The best defensible versions, and what combining them does

**Request:** *"make the best versions possible with the most profitable combinations."*

**One caution, stated once and then set aside:** "most profitable combination" is the thing this
project has measured as harmful three separate times — best-of-K landed at the 9th–23rd percentile
of out-of-sample outcomes across searches of 225,792, 2,400 and 400,226 configurations. So these
versions are built from what **replicated**, not from what maximises the backtest, and the in-sample
maximum is reported beside each choice so the gap is visible.

Code: `research/best_versions.py`. Pine: `NQ_BosChoch.pine`, `NQ_InitialBalance.pine`.

## The versions

| version | net $ | $/yr | trades | $/trade | PF | **Sharpe** | Sortino | Calmar | **maxDD%** | maxDD $ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **V1** IB retracement (validated) | 29,657 | 9,769 | 167 | 178 | 1.66 | **1.44** | 1.43 | 1.60 | **5.6** | 7,577 |
| **V2** BOS/CHoCH 30m + range filter | 71,483 | 23,547 | 147 | 486 | 1.54 | 1.00 | 1.37 | 1.25 | 15.6 | 20,664 |
| **V3** book, equal dollars | 101,140 | 33,317 | 282 | 359 | 1.59 | 1.33 | 2.06 | 1.86 | 13.9 | 21,063 |
| **V3** book, inverse-volatility | 78,076 | 25,719 | 282 | 277 | 1.65 | 1.65 | 2.60 | 2.51 | **8.4** | 11,980 |
| **V3** book + volatility sizing | **105,711** | **34,822** | 262 | 403 | **1.88** | **1.71** | **3.09** | **3.62** | 7.4 | 12,250 |

NQ, 765 sessions, Dec 2022 – Dec 2025, all figures net of $19–24 per round turn.

**The combination is the real result.** Correlation of daily P&L between V1 and V2 is **+0.094**, and
they trade on the same session only **4.2% of the time** — different timeframes, different
mechanisms, almost no overlap. Combining them raises Sharpe from 1.44/1.00 to **1.71** while cutting
max drawdown to **7.4%**, better than either leg alone. That improvement is arithmetic from
uncorrelated streams, not from tuning anything.

## Two defects found and fixed while building this

**1. Fills outside the session — 41% of the profit.** At 30m, a signal on the last RTH bar (15:30)
fills on the *next* bar, which opens at 16:00, after the cash close. **23 of 168 entries (14%) filled
there and produced $42,979 of $103,765 — 41% of all profit** — on a 1-tick spread assumption that
does not hold in post-close liquidity. Requiring the *fill* bar to be in session as well as the
signal bar drops V2 from $103,765 to **$71,483 (−31%)**. The table above is the corrected number.

**2. A timezone mismatch that silently zeroed a leg.** The parquet round-trip stripped the timezone,
so a tz-aware bar index never compared equal to a tz-naive calendar and V2's daily series came back
as all zeros. It printed as "0 trades" rather than as an error.

The same class of bug appears in the Pine: my first draft computed the fill-bar session gate with an
expression identical to the signal-bar gate, so it gated nothing. It now uses `session.islastbar`.

## What each version is

### V1 — IB retracement *(the only validated edge in this project)*

> Build the initial balance 09:30–10:30 ET. On a **close** beyond either edge, **rest a limit** at a
> 50% retracement of that range. Stop at 80% of the range from the broken edge. Fixed **1:2** target.
> **Both sides.** Flat at 11:59. One trade per session.

`n = 167`, **+0.3248R**, block bootstrap 95% CI **[+0.1614, +0.4895]**, **P(mean ≤ 0) = 0.0000**,
PBO 0.17–0.24. Its edge is a passive fill and 0.22 trades a day, not a superior forecast.

### V2 — BOS/CHoCH 30m + range filter *(a hypothesis, not an edge)*

> 30-minute NQ, 09:30–16:00. Fractal swings confirmed k=3 bars later. Enter on the **second** BOS in
> the prevailing direction at the next bar's open. Require close on the trend side of EMA(200).
> **Refuse any entry within 1 × ATR of the EMA-200.** Stop 2 × ATR(14). Exit on the opposite BOS
> (CHoCH) or the stop. Signal bar *and* fill bar both inside the session.

The range filter is the one component that replicated: 0.5, 1.0 and 1.5 ATR all improved on 0
(+$554, +$618, +$524 vs +$428/trade before the fill correction) — a plateau, not a spike. It was
motivated by the strongest statistic in the BOS study: **−$474/trade at t = −5.26** for breaks taken
inside the range.

**t = 1.88.** It does not reach 2, and the 30m timeframe was chosen from 8 while the filter was
chosen from 5 — an honest hurdle over ~40 cells is E[max z] ≈ 2.7. **V2 does not clear it.**

## The in-sample maximum, for comparison

Searching all 450 cells of (EMA × ATR-multiple × swing k × range filter) at 30m:

```
best of 450:  EMA 50, ATR x1.5, k=2, no range filter
              $115,099 over 287 trades ($401/trade), t = 2.28, Sharpe 1.16
V2 as specified: $71,483, Sharpe 1.00, t = 1.88

E[max z] over 450 cells ~ 3.50 from noise alone. The winner reaches 2.28.
```

The argmax is **$43,616 richer and less believable**: it clears no hurdle, it drops the filter that
replicated, and it sets k=2 — the swing length that was *negative* at 15m and had a different
optimum at every timeframe. V2 is the pre-specified cell on purpose.

## MNQ translation — the only tradeable form at retail risk

| version | net $ | $/yr | maxDD $ |
| --- | --- | --- | --- |
| V1 on MNQ, 1 contract | 2,966 | 977 | 758 |
| V2 on MNQ, 1 contract | 7,148 | 2,355 | 2,066 |
| V3 book on MNQ, 1+1 | 10,114 | 3,332 | 2,106 |

A 2×ATR stop on 30-minute NQ risks about **$2,000 per contract**, so at $100–$300 fixed risk every
signal rounds to zero contracts. On MNQ the same stop is ~$200 and the strategy becomes expressible.
Capital base above is $10,000 rather than $100,000.

## How to read these numbers

**V1 is validated.** Bootstrap CI excludes zero, PBO is low, it was pre-specified in an earlier study
and re-verified here.

**V2 is not.** It is the best surviving cell of a battery that classified the concept **WEAK EDGE**:
1m and 2m are significantly negative, 5m loses to coin-flip entries, 60m has PBO 0.814, and 94% of
the 30m profit came from 3 of 12 quarters. Its t of 1.88 is suggestive and nothing more.

**V3's diversification is real** — +0.094 correlation is not a modelling artifact, the two rules
genuinely fire on different days. But a book is only as sound as its legs, and one of these two is a
hypothesis. The Sharpe of 1.71 should be read as "what this would have been", not as an expectation.

**The single test that would most change all of this is ES data.** Two uncorrelated NQ strategies in
one three-year bull market is still one instrument and one regime.


## Out-of-sample test — and a correction to the framing above

Run after the fact, because V2 and V3 had **no** clean out-of-sample evidence: the 30-minute
timeframe was chosen from 8 and the range filter from 5 values, both with the whole sample visible.
Split on session boundaries at **2024-11-28**: 497 research sessions, **268 locked**.

| version | research $ | research Sharpe | **LOCKED $** | **LOCKED Sharpe** | locked trades |
| --- | --- | --- | --- | --- | --- |
| **V1** IB retracement | 29,621 | 2.34 | **36** | **0.00** | 56 |
| **V2** BOS/CHoCH 30m + filter | 24,411 | 0.71 | **47,072** | **1.39** | 56 |
| **V3** book (equal $) | 54,032 | 1.45 | 47,108 | 1.32 | 97 |

**This reverses the framing in the sections above, and the reversal is the finding.**

### V1 has decayed to nothing

Half-yearly, V1 earned +$816, +$3,990, +$9,718, +$7,384, +$9,664 — and then **−$408 and −$1,507
across both halves of 2025.** Its locked-block result is **$36 over 56 trades**.

The bootstrap CI of [+0.1614, +0.4895] quoted earlier is a **full-sample** statistic, and the full
sample is dominated by 2023–2024. It was not wrong, but it describes a period that has ended. On the
last 268 sessions the validated edge is indistinguishable from zero. Its earlier documented decay
(0.414R research → 0.116R holdout) continued to ~0.

### V2 held up, and its parameter surface transfers

| tf | filter | research $ | res Sharpe | **LOCKED $** | **lock Sharpe** |
| --- | --- | --- | --- | --- | --- |
| 5m | 1.0 | −16,174 | −0.33 | 12,134 | 0.28 |
| 15m | 1.0 | 11,294 | 0.27 | 20,403 | 0.60 |
| **30m** | **1.0** | 24,411 | 0.71 | **47,072** | **1.39** |
| 30m | 1.5 | 20,100 | 0.59 | 45,737 | 1.46 |
| 60m | 0.0 | 35,168 | 1.13 | 28,065 | 1.07 |

**Spearman rank correlation research → holdout across the 20 cells: +0.711.** 19 of 20 cells are
profitable on the holdout; 16 of 20 on both halves.

That is unlike every other search in this project — the IB grid gave −0.079 and the 400,226-cell
trend search +0.11. A rank correlation of +0.71 means the research half genuinely told you something
about the holdout half. It is the first time that has happened here.

### The honest simulation

Choosing the timeframe *and* the filter on the research portion only, then opening the holdout once:

```
chosen on research only:  60m, no range filter   (research $35,168, Sharpe 1.13)
its LOCKED result:        $28,065, Sharpe 1.07
V2 as shipped (30m/1.0):  $47,072, Sharpe 1.39 on the same block
```

The procedure picked a *different* cell than the one shipped, and that cell still returned **Sharpe
1.07 out of sample**. This is the number to believe: it is what someone following the method, with no
knowledge of the future, would have got.

### The book, built honestly

| | research | **LOCKED** |
| --- | --- | --- |
| book with research-chosen V2 | $64,789, Sharpe 1.90 | **$28,101, Sharpe 1.05** |
| V1 alone on the same block | — | $36, Sharpe 0.00 |

Correlation on the locked block: **−0.065** — still uncorrelated. But the book's out-of-sample Sharpe
of 1.05 is **V2 carrying it entirely**, because V1 contributed $36.

### What to conclude

**V2 is not concentrated luck.** Half-yearly it is positive in 5 of its 6 active halves (+$20,537,
+$2,483, +$19,690, +$10,693, +$28,343), with only 2023-H1 negative at −$10,262. Its worst period is
its earliest.

**But 147 trades is still 147 trades**, one instrument, one bull market, and the parameters were
chosen with the holdout visible. The clean number is the honest simulation's **Sharpe 1.07**, not the
1.39 of the shipped cell.

**The corrected ranking, forward-looking:** V2 > book > V1. That inverts what the full-sample
statistics said, and it is the more useful answer, because the question is what happens next rather
than what happened on average since 2022.


## Test scorecard — V2 as shipped

Run against the exact specification (30m, EMA 200, 2×ATR, k=3, refuse within 1 ATR, in-session
fills). `research/bos_scorecard.py`.

```
n = 147   net $71,483   $486/trade   PF 1.54   Sharpe 1.02   maxDD 15.6%   t = 1.88
```

| # | test | result | verdict |
| --- | --- | --- | --- |
| 1 | profitable after full costs | +$71,483, PF 1.54 | **PASS** |
| 2 | positive gross *and* net | both | **PASS** |
| 3 | random-entry control | 95.3rd percentile | **PASS** |
| 4 | Monte Carlo, 20k paths | P(loss) 0.0%, median DD 15.1% | **PASS** |
| 5 | cost sensitivity | still profitable at 6× costs | **PASS** |
| 6 | locked holdout | $47,072, Sharpe 1.39 | **PASS** |
| 7 | honest simulation (select on research only) | Sharpe 1.07 OOS | **PASS** |
| 8 | research→holdout rank correlation | **+0.711** | **PASS** |
| 9 | parameter plateau (EMA × ATR multiple) | 36/36 cells positive | **PASS** |
| 10 | both sides profitable | longs $47,412 (t 2.41), shorts $24,071 (t 1.02) | **PASS** |
| 11 | half-yearly consistency | 5 of 6 positive | **PASS** |
| 12 | no look-ahead | 7-bar delay measured, pivots unit-tested | **PASS** |
| 12b | walk-forward, positive out of sample | all 4 variants positive (+$5,204 to +$60,569) | **PASS** |
| 13 | **bootstrap CI excludes zero** | **[−$30, +$1,045]**, P(edge≤0) 3.3% | **FAIL** |
| 14 | **probability of backtest overfitting** | **PBO 0.571** | **FAIL** |
| 15 | **multiple testing, 40 cells** | t 1.88 vs hurdle 2.72 | **FAIL** |
| 16 | **multiple testing, 72 cells** | t 1.88 vs hurdle 2.92 | **FAIL** |
| 17 | **swing-length stability** | different optimum at every timeframe | **FAIL** |
| 18 | **ablation consistency** | 4 of 5 components flip sign | **FAIL** |
| 18b | **walk-forward beats the fixed cell** | fixed +$69,311 (Sharpe 1.24) vs best re-selection +$60,569 (0.97) | **FAIL** |
| 19 | cross-instrument (ES) | no data | **NOT RUN** |

**13 passed, 7 failed, 1 could not be run.**

### The two failures that matter most

**PBO = 0.571.** The configuration that looks best in-sample lands in the *bottom half* out of sample
57% of the time — worse than a coin flip. Adding the range filter made this *worse* (0.471 → 0.571).
Whatever is working here, the procedure for finding it does not generalise.

**t = 1.88 against a hurdle of 2.72.** The 30-minute timeframe was chosen from 8 and the filter from
5. A best-of-40 search draws E[max z] ≈ 2.72 from noise alone. This does not clear it.

### The tension, stated rather than resolved

Tests 6–8 are genuinely strong: the holdout returned Sharpe 1.39, the honest selection procedure
returned 1.07, and the research→holdout rank correlation of **+0.711** is unlike anything else in this
repository (the IB grid gave −0.079; the 400,226-cell trend search +0.11).

Tests 13–16 are genuinely damning: the confidence interval crosses zero and the selection procedure
is worse than random.

Both are true. The reconciliation is probably that the *level* of performance in any single cell is
noisy (hence PBO and the wide CI), while the *ordering* across cells carries real information (hence
+0.711). That is consistent with a small real effect buried in a lot of variance — which is exactly
what 147 trades on one instrument in one bull market cannot settle.

## Reproduce

```bash
python3 research/best_versions.py    # the three versions, the book, MNQ, and the argmax comparison
python3 research/bos_report.py       # the battery V2 came out of
python3 research/validate.py         # re-verifies V1 (full-sample)
python3 research/best_oos.py         # the locked-split test and the honest simulation
python3 research/bos_scorecard.py    # the 19-test scorecard on the shipped spec
```
