# CMMA mean reversion on MNQ — evaluation

## Verdict

**No demonstrable edge, but not a broken backtest either — and the distinction matters.** The
notebook has no look-ahead: the audit is clean, the execution-alignment check is clean, and the
signal traded on date *D* is built from data through the end of calendar day *D−2*. What it does
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
