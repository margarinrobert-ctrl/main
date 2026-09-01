# CMMA mean reversion on MNQ — evaluation

## Verdict

**No demonstrable edge, but not a broken backtest either — and the distinction matters.** The
notebook has no look-ahead: the audit is clean, the execution-alignment check is clean, and the
signal traded on date *D* is finalised at **midnight New York as day *D* begins, eight hours
before the 08:00 entry**. What it does
not have is evidence. On nine years of the same index the strategy earns a **Sharpe of 0.39 ± 0.33
net of costs**, its **deflated Sharpe is 0.057** against the 34-configuration sweep the notebook
itself runs, and the **expected best-of-34 random tries would have scored 0.85** — nearly four
times the observed 0.22 in-sample. Three of nine years are negative, the best 1% of days are 240%
of net profit, and the component attribution *inverts* between the two feeds: on NQ the KER
weighting is the entire signal and raw CMMA is worthless; on US100 raw CMMA is the best row and the
machinery halves it. That is what fitting noise looks like.

**What would change my mind:** the shift null does pass on the long sample (p 0.045), and the
holdout held on both feeds. If the same parameters, frozen, cleared a matched control on a third
instrument that had no part in this, that would be a real footing. Costs are *not* the obstacle
here — which is unusual and worth knowing.

## Setup

MNQ (NQ price path, 2022-12→2025-12, 748 traded days) and US100 (2016-11→2025-10, 2,262 traded
days) · daily signal, intraday execution 08:00–15:45 New York · holdout = last 30% of traded days
(NQ split 2025-01-30, US100 split 2023-02-15) · costs $1.44/round turn + 1 tick slippage a side =
1.22 points · **34 trials** counted in the deflation (the notebook's own sweeps are additional).

## Performance, net of costs

| | days | pts/day | Sharpe | ±SE | max DD | win |
|---|---:|---:|---:|---:|---:|---:|
| **NQ** in-sample | 523 | +0.942 | +0.76 | 0.70 | −1.1% | 48.9% |
| **NQ** holdout | 225 | +1.817 | +0.73 | 1.06 | −2.1% | 50.2% |
| **US100** in-sample | 1,583 | +0.199 | +0.22 | 0.40 | −6.3% | 47.2% |
| **US100** holdout | 679 | +1.154 | +0.65 | 0.61 | −6.8% | 49.0% |
| **US100** full sample | 2,262 | +0.486 | **+0.39** | **0.33** | −6.8% | 47.7% |

**Every Sharpe here is within one standard error of zero.** Deflated Sharpe **0.150** (NQ) /
**0.057** (US100); expected max Sharpe from noise across 34 trials **1.48** / **0.85** against
observed 0.76 / 0.22. PBO **0.54** (NQ, "selection no better than random") / **0.35** (US100,
"meaningful overfitting risk"). Breakeven cost **23.7 / 28.7 bps** against 0.9 / 2.6 bps charged.

## Three things in the notebook that inflate the number

**1. `sr = eq.mean() / eq.std()` is not a Sharpe ratio.** `eq` is a `cumsum` — this is the mean of
an *equity curve* divided by its own standard deviation. It is large for any curve that trends, it
does not scale with √time, it is not comparable between strategies, and it cannot carry a standard
error. On NQ it prints **0.875** and the true annualised Sharpe of that same series is **+0.83** —
close by coincidence of this sample, not because the formula is right. The number that matters is
the one it hides: **± 0.58**.

**2. `pnl = signal * (close - open)` summed over intraday bars drops every gap between bars.** The
quantity a trader receives for holding 08:00→15:45 is `close[15:45] − open[08:00]`; summing bar
bodies discards each `open[t] − close[t−1]` jump. Worth **+122 points on NQ (+13% of net)** and
**+263 on US100 (+24%)**.

**3. No costs.** Here this is the *smallest* of the three: the EMA smoothing keeps mean daily
turnover at 0.04 contracts, so costs take only 3.9% (NQ) / 9.0% (US100) of gross. The strategy
survives to ~20 bps and dies at 50. **Cost realism is not what kills this one.**

## The component attribution inverts between markets

In-sample, net, each piece removed one at a time:

| | NQ Sharpe | US100 Sharpe |
|---|---:|---:|
| CMMA as briefed | **+0.76** | +0.22 |
| without KER weighting | **+0.16** | +0.18 |
| without tanh bounding | +0.78 | +0.24 |
| without the EMA smoothing | +0.78 | **+0.43** |
| `sign(cmma)` only, no scaling | **−0.01** | **+0.46** |

On NQ the KER weighting *is* the strategy — remove it and the Sharpe collapses from 0.76 to 0.16,
and the bare sign of CMMA earns nothing at all. On US100 the bare sign of CMMA is the **best** row
and every layer of machinery makes it worse. **The same four components, opposite conclusions on
two feeds of the same index.** Note also that `tanh` and the EMA smoothing *never* help on either
feed — removing them improves both — so two of the four described mechanisms are decoration.

## Robustness

- **Block bootstrap** (full sample, net): NQ P(Sharpe ≤ 0) = 4.6%, P(< 0.5) = 27.9%; US100
  P(Sharpe ≤ 0) = 6.1%, **P(< 0.5) = 67.5%**.
- **Shift null** — the same position series applied to the wrong dates: NQ p **0.078** ("not
  distinguishable from randomly-timed trading with the same exposure profile"), US100 p **0.045**
  ("timing carries information"). The long sample passes; the short one does not.
- **By year** (US100, net Sharpe): 2017 −1.08, 2018 −0.84, 2019 +0.76, 2020 +0.67, 2021 +0.32,
  2022 +0.60, 2023 −0.19, **2024 +1.24**, 2025 +0.34. Carried by 2024; the two worst years open
  the sample.
- **Concentration:** the best 1% of days are **135% of net on NQ** and **240% on US100**; the best
  5% are 267% and 496%. Remove the top 1% of days and both are losers.
- **Information coefficient** 0.068 (NQ) / 0.037 (US100) — small and plausible. Above ~0.15 would
  have suggested a leak.

## Profit factor, win rate, timeframe, holding time

**Timeframe:** signal on **daily** bars, executed intraday **08:00–15:45 New York = 7.75 hours a
day**, flat overnight and at weekends. Execution bars are 1-minute on NQ, 15-minute on US100.

Net of costs, full sample:

| | NQ (3 yr) | US100 (9 yr) |
|---|---:|---:|
| **profit factor, per day** | **1.251** | **1.127** |
| **win rate, per day** | **49.3%** | **47.7%** |
| profit factor, per directional stance | 2.023 | 1.534 |
| win rate, per stance | 76.3% | 71.7% |
| **mean hold, per stance** | **6.56 trading days** (median 5, max 38) | **6.96** (median 5, max 65) |
| exposure-hours per stance | 50.9 | 53.9 |
| mean absolute target | 0.076 contracts | 0.085 |

**The per-day and per-stance figures are the same strategy counted two ways, and the difference is
not an improvement.** The position is a *continuous* target in [−1, 1] that is re-sized daily, so
there is no discrete trade with an entry and an exit. Grouping consecutive same-side days into one
"stance" nets winning days against losing days inside each run, which is what lifts the profit
factor from 1.13 to 1.53 and the win rate from 47.7% to 71.7%. **The per-day row is the honest one**
— it matches the unit the Sharpe is computed on. Quoting 71.7% as a win rate would be the same kind
of framing error as the notebook's Sharpe.

Two further readings from the same table:

* **The short side is twice as frequent as the long and worse at it** — US100: 1,466 short days at
  PF 1.103 and 45.2% wins against 796 long days at PF 1.161 and 52.5%. A contrarian signal on a
  rising index is short most of the time, which is the fifth time on this branch that a short book
  has lost by existing.
* **Mean absolute exposure is 0.08 contracts.** The +0.49 to +1.21 points a day is earned on that,
  not on one contract; scaled to full size the drawdowns scale with it.

## Weaknesses

- The effect is smaller than the noise floor at this sample size. To distinguish Sharpe 0.4 from 0
  at 95% confidence needs roughly 25 years of daily data; there are nine.
- The notebook's own sweep (cells 20–28) plus the decile-plot threshold filter (cells 31–32) were
  all run on the full sample, so its reported configuration is post-selection. The 34 trials
  counted here are a *lower* bound.
- NQ's stored price levels are synthetic (`STUDY_US100.md`), so its points-per-day figures are
  distorted; Sharpe, win rate and ATR-relative measures are not.
- The position is a continuous target in [−1, 1] with mean absolute exposure of only 0.08. Scaled
  to a tradeable size the drawdowns scale with it.

## The Pine port

`pine/cmma/CMMA_MNQ_strategy.pine`, diffed against the research engine rather than asserted
(`research/cmma/cmma_parity.py`), in both the shipped configuration (no tanh, no smoothing) and
the notebook's original:

| | NQ | US100 |
| --- | --- | --- |
| signal days compared | 901 | 2,724 |
| correlation | **1.0000000000** | **1.0000000000** |
| max abs difference | 6.9e−17 | 1.3e−14 |
| fractional P&L | +901.5 pts both | +1,099.0 pts both |

Four things the port has to get right, each of which would silently change the strategy:

1. **The daily bars are New York calendar days, not exchange sessions.** The notebook resamples
   midnight-to-midnight; TradingView's `"D"` on a CME future is the 18:00–17:00 ETH session. The
   script accumulates its own daily bars from the chart's intraday bars, so **extended hours must
   be on** or every daily high, low and true range is missing the overnight.
2. **The lag is eight hours, not a day.** With `label='right'` the daily bar labelled *D* covers
   calendar day *D−1* and closes at midnight as *D* begins; the `.shift(1)` is then consumed by the
   notebook's own `index − 1 day` remap. Verified against the data — an earlier draft of this study
   said *D−2* and that was wrong by a day. Adding a shift would trade a day late; removing one
   would be lookahead.
3. **`ewm(2)` is `com=2`, not `span=2`** — pandas' first positional argument is the centre of mass,
   so alpha is 1/3. Reading it as a span makes the filter twice as fast.
4. **Pine cannot trade fractional contracts, and this is the only place the port is inexact.** Mean
   absolute signal is 0.076, so at a base size of 1 the rounded target is **zero on every single
   day and nothing trades at all**. Measured cost of the rounding by base size (NQ, per
   contract-equivalent):

| contracts at full signal | 1 | 5 | 10 | 20 | 50 | 100 | exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| days traded | **0** | 202 | 370 | 526 | 640 | 691 | 748 |
| Sharpe | — | +0.54 | +0.92 | +0.65 | +0.71 | +0.69 | +0.70 |

At 50 and above the rounding is free; below 20 it is material noise in both directions. The script
defaults to 50, which is a mean position near 4 MNQ and a maximum near 24.

## Can it perform better — seven pre-declared candidates, two feeds

`research/cmma/cmma_improve.py`. Because the component attribution inverts between NQ and US100, a
change chosen on one feed is exactly the trap; a candidate survives only if it beats the notebook
**in-sample on both**, and the holdout is read once, after. Net of costs:

| candidate | NQ IS | US100 IS | survives | NQ holdout | US100 holdout |
| --- | ---: | ---: | :---: | ---: | ---: |
| A as briefed | +0.76 | +0.22 | base | +0.73 (PF 1.28) | +0.65 (PF 1.23) |
| B start 09:30 instead of 08:00 | +0.57 | +0.00 | no | | |
| **C no tanh, no EMA smoothing** | **+0.83** | **+0.47** | **yes** | **+1.99 (PF 1.83)** | **+0.96 (PF 1.32)** |
| D = B + C | +0.69 | +0.27 | no | | |
| E vol-targeted | +0.86 | +0.04 | no | | |
| F dead band | +0.87 | +0.24 | yes | +0.86 (PF 1.39) | +0.73 (PF 1.31) |
| G = D + E | +0.97 | +0.00 | no | | |

Standard errors are 0.70 (NQ IS), 0.40 (US100 IS), 1.06 and 0.61 on the holdouts.

**C ships as the default.** It is the only candidate that beats the notebook on both feeds
in-sample *and* on both holdouts, and it is the removal of two components §4 had already measured
as inert — not the addition of anything. Three caveats stay attached: its deflated Sharpe is
**0.16** against a 40-trial search, so it is still not distinguishable from the best of 40 random
tries; its holdout is *better* than its in-sample on both feeds, which this branch treats as a
regime warning and not a result (the notebook's own version shows the same shape, so the recent
block is simply kinder to this family); and without `tanh` the signal is unbounded — mean
|signal| 0.076 → 0.137, 99th percentile 0.75, maximum seen 1.55 — so the Pine's position cap is
load-bearing, though at a base of 50 it never actually binds.

**Two results worth having even though they lost.** Starting at 09:30 instead of 08:00 (B) *hurt*
on both feeds, against `CLAUDE.md`'s four prior findings that 07:00–09:30 is the worst part of the
day — this daily-signal strategy wants the pre-open hour, which is consistent with it being a
held directional position rather than an intraday entry. And vol-targeting (E) helped NQ and
flattened US100 to zero, which is the inversion again.

## Next tests

1. **Freeze `sign(cmma)` with no KER, no tanh, no smoothing** — the best US100 row and the simplest
   hypothesis — and read it once on a market that had no part in this.
2. **Score it against a matched control**, not against zero: random entries with the same daily
   exposure profile and the same session. The shift null is a first approximation of this and it is
   borderline.
3. **Test whether KER alone is a timing signal**, independent of CMMA. On NQ it carried everything,
   which is either a finding or the artifact the US100 column says it is.

---

| file | what it does |
| --- | --- |
| `research/cmma/cmma_core.py` | the strategy, the session accounting, the cost model, the split |
| `research/cmma/cmma_test.py` | audit, accounting decomposition, sweep, deflation, holdout, robustness |
| `results/cmma_NQ.txt`, `results/cmma_US100L.txt` | raw output |
