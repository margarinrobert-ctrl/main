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

## Reproduce

```bash
python3 research/best_versions.py    # the three versions, the book, MNQ, and the argmax comparison
python3 research/bos_report.py       # the battery V2 came out of
python3 research/validate.py         # re-verifies V1
```
