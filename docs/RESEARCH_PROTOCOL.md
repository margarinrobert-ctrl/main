# Systematic futures research protocol

A rules-based pipeline for deciding whether an intraday futures strategy has a **statistically valid
edge** — built for scalping horizons on instruments like NQ, ES, CL and XAU/USD, where the cost of
trading is the same order of magnitude as the signal.

The code lives in `src/lib/quant/`. The whole protocol runs from one command:

```bash
npx tsx scripts/quant-ingest.ts  --in raw.csv --out data/NQ_5m.csv --tf 5 --tz America/New_York
npx tsx scripts/quant-research.ts --data data/NQ_5m.csv --symbol NQ --out docs/STUDY_NQ.md
```

> Research tooling for education and analysis. Nothing here is financial advice, and a strategy that
> passes every gate below has earned a paper-trading slot, not a live account.

---

## 1. The premise: costs first, signal second

At a five-minute horizon on NQ a round turn costs **1 tick of spread + 1 tick of slippage per side +
$4.00 commission ≈ 3.8 ticks ($19)**. A typical 5-minute NQ bar in the quiet part of the session
moves about 36 ticks. So the strategy must forecast roughly **10% of a bar's range, correctly, on
average, forever** — before it has made a cent.

That arithmetic, not the entry logic, is what kills nearly every scalping idea. Every number in this
stack is therefore reported in **ticks**, next to the cost line:

| quantity | meaning |
| --- | --- |
| `grossEdgeTicks` | mean price move captured per trade, before costs |
| `costTicks` | modelled round turn |
| `netEdgeTicks` | what is actually left |
| `breakEvenCostTicks` | the cost at which the edge dies — the safety margin |

If `netEdgeTicks` is negative, no amount of parameter tuning, position sizing or machine learning
changes the conclusion.

---

## 2. The stages, and what each one can kill

The order is deliberate: the cheapest, most lethal tests run first.

### Stage 0 — Engine null calibration
Run the whole library over **simulated martingale bars** with costs switched off. There is no edge in
that series by construction, so anything significantly profitable is a **bug**: look-ahead, an exit
that resolves in the trader's favour, a cost that never got charged.

This stage also prices the engine's one deliberate pessimism. When a single bar contains both the
stop and the target, the trade is booked as a **loss**, because the intrabar path is unknown. The
report shows how often that rule fires (`ambiguous bars`) and what it costs, so results can be read
as conservative by a known amount rather than by an unknown one.

A matching **power check** injects a known AR(1) momentum coefficient and confirms detection scales
with it — a pipeline that cannot find a planted effect is not evidence of absence.

### Stage 1 — Data audit
Duplicates, out-of-order stamps, impossible OHLC, missing-data holes, and bad prints. Gaps that recur
at a fixed local time are labelled **structural** (the CME maintenance break, the weekend) and those
that happen once are labelled **missing data** — conflating the two makes a clean file look broken.

Bad prints are detected against a **robust (MAD) scale**, not the standard deviation, because
intraday index futures are fat-tailed and the outliers would otherwise set the very threshold meant
to catch them.

### Stage 2 — Alpha discovery: *is there anything to trade?*
Before any rule exists, measure the predictability in the series itself:

- **Return autocorrelation** with Bartlett errors — momentum or reversal, and at what lag.
- **Lo-MacKinlay variance ratios**, heteroskedasticity-robust, so volatility clustering alone cannot
  reject the random walk.
- **Time-of-day profile** — mean signed move (where a seasonality edge would live) and mean absolute
  move (where scalping opportunity lives), with FDR correction across buckets.
- **Event studies** on the classic hypotheses (continuation after a large bar, reversal after a large
  bar, volume-surge continuation, three-bar runs, compression breaks), reported at several horizons.

Two corrections make this stage honest, and both matter enormously:

1. **Drift adjustment.** On a market that trended as hard as NQ did over 2023-2025, any condition
   that fires long more often than short earns a large raw forward return from exposure alone. The
   reported edge is `mean(side × forward) − mean(side) × mean(forward)`, which removes it.
2. **HAC lag ≥ horizon.** Overlapping *h*-bar forward windows induce MA(*h*−1) dependence; using the
   default Newey-West lag would overstate every t-statistic in the table.

The stage ends with the **predictability budget**: the largest drift-adjusted conditional edge that
survives false-discovery control, divided by the cost. Below 1.0, no rule at any parameters can work.

### Stage 3 — In-sample parameter search
Grid search on the research set only. **The winner's Sharpe is not evidence** — it is the maximum of
however many configurations were tried. What is evidence is the shape of the surface, reported as:

- **neighbour stability** — median objective of the winner's one-grid-step neighbours ÷ the winner's
- **verdict** — `plateau` (broad, survives perturbation), `ridge`, or `spike` (mined noise)

A strategy whose edge evaporates when a lookback moves from 20 to 21 never had one.

### Stage 4 — Reality check and SPA
**White's Reality Check** and **Hansen's SPA** over the candidate set, using a stationary block
bootstrap applied to the whole cross-section so correlation between candidates is preserved. This
answers the question a research sweep actually raises: *I kept the best of K — is the best better
than luck?*

### Stage 5 — Probability of backtest overfitting (CSCV)
Splits the daily P&L of many configurations into contiguous blocks, and for every balanced train/test
partition asks where the in-sample winner lands out of sample. **PBO** is the share of partitions
where it falls below the median.

This tests the **selection procedure**, not any single strategy. PBO above 0.5 means a better
in-sample number is actively bad news.

### Stage 6 — Walk-forward
Rolling re-optimisation: fit on 120 sessions, trade the next 40 with those parameters, step, repeat.
The stitched test windows are the first genuinely out-of-sample record, and they include the cost of
*having to choose parameters* — which a single in-sample fit hides entirely.

Reported alongside: **walk-forward efficiency** (median OOS objective ÷ median IS objective) and
**parameter stability** (how often each parameter kept the same value across folds). Efficiency is
reported as undefined when the in-sample median is not positive, because a ratio of two negatives
looks like success.

### Stage 7 — Deflated Sharpe
The **Deflated Sharpe Ratio** (Bailey & López de Prado) restates the out-of-sample Sharpe as a
probability, given: the actual number of configurations evaluated across the whole study, the
cross-sectional dispersion of trial Sharpes, and the skew and kurtosis of the realised daily stream.

Also reported: a **stationary-bootstrap 95% CI** on the Sharpe, and the **minimum track record
length** needed to establish the result — usually the most sobering number in the report.

Family-wide error control (**Benjamini-Hochberg** and **Holm**) is applied across strategies.

### Stage 8 — Robustness
Applied to the out-of-sample record only:

| probe | what it catches |
| --- | --- |
| cost sensitivity sweep | an edge that exists only at exactly the modelled spread |
| sub-period consistency | P&L delivered in one lucky window |
| regime breakdown (year / month / hour / weekday / volatility tercile) | an edge concentrated in one regime |
| exit-reason mix | "profitability" that is really the time stop rarely firing |
| Monte Carlo trade reshuffling | the drawdown distribution behind the single observed path |

### Stage 9 — Portfolio combination
Correlation of out-of-sample **daily P&L** decides whether a second strategy adds anything; two
breakout rules at r = 0.8 are one strategy paying two commissions. Streams are scaled to unit daily
volatility so weights express **risk** allocation, then combined under equal, inverse-vol, risk-parity
and long-only min-variance schemes. Reported: diversification ratio, risk contributions, and the
Sharpe uplift over the best single strategy — the only reason to combine at all.

### Stage 10 — Locked holdout
The final 30% of the sample, untouched by every stage above, evaluated **once**. It is the only
number in the study that never influenced a decision.

---

## 3. The gates

A strategy is called tradeable only if it clears all ten:

| # | gate | rationale |
| --- | --- | --- |
| 1 | ≥ 100 out-of-sample trades | below that, nothing is measurable |
| 2 | positive net edge after costs | the arithmetic in §1 |
| 3 | HAC t-stat > 2 | serial dependence priced in |
| 4 | Deflated Sharpe > 0.95 | survives the size of the search |
| 5 | PBO < 0.30 | the selection procedure carries information |
| 6 | survives ≥ 1.5× modelled costs | spreads widen exactly when signals fire |
| 7 | parameter surface is not a spike | not mined from noise |
| 8 | profitable in ≥ 60% of sub-periods | not one lucky window |
| 9 | no single year > 60% of P&L | not one regime |
| 10 | walk-forward efficiency ≥ 0.4 | the fit transfers forward |

The thresholds are harsh on purpose. At scalping horizons the null hypothesis is right the
overwhelming majority of the time, so the burden of proof sits with the strategy.

---

## 4. Reading a negative result correctly

Most honest studies end with nothing passing. That result says:

> *These rules, on this instrument, in this session, at this timeframe, under this cost model, over
> this sample, do not demonstrate an edge.*

It does **not** say the market is unpredictable. The productive responses, in order of expected
value:

1. **Change the cost regime.** Move from NQ to MNQ, or from taking liquidity to posting it. Halving
   the cost line does more for a marginal strategy than any parameter search.
2. **Change the session.** The report's time-of-day profile shows where range actually is.
3. **Add information the price series does not contain** — order flow, book imbalance, positioning,
   the options-derived dealer state this repo already computes elsewhere. Rules built from OHLC alone
   are competing with everyone who has the same OHLC.
4. **Change the horizon.** The variance-ratio table says at which horizons the series departs from a
   random walk, if it does anywhere.

What is *not* a productive response is widening the parameter grid until something passes. That is
precisely what stages 3–7 exist to detect, and they will detect it.

---

## 5. Extending the stack

### Adding an instrument (XAU/USD, CL, ES, …)

Specs live in `src/lib/quant/instruments.ts`. Exchange facts (tick size, tick value) are fixed; the
cost fields are **assumptions you should challenge**, and `costSensitivity()` reports how much of any
result survives if they are wrong by 2×.

| id | tick | tick value | modelled spread | session (local) |
| --- | --- | --- | --- | --- |
| `XAUUSD` | 0.01 | $1.00 | 20 ticks | 03:00–17:00 ET |
| `GC` / `MGC` | 0.10 | $10.00 / $1.00 | 1 tick | 03:00–17:00 ET |
| `CL` / `MCL` | 0.01 | $10.00 / $1.00 | 1 tick | 09:00–14:30 ET (pit) |
| `ES` | 0.25 | $12.50 | 1 tick | 09:30–16:00 ET |
| `NQ` | 0.25 | $5.00 | 1 tick | 09:30–16:00 ET |

Spot gold deserves particular care: a 20-cent retail spread on a 100 oz lot is **$20 per round turn
before commission**, which is a far higher hurdle than the tick table suggests. Run the cost
sensitivity sweep before believing any XAU/USD scalping result.

Then ingest and run:

```bash
npx tsx scripts/quant-ingest.ts  --in gold_1min.csv --out data/XAUUSD_5m.csv --tf 5 --tz America/New_York
npx tsx scripts/quant-research.ts --data data/XAUUSD_5m.csv --symbol XAUUSD --out docs/STUDY_XAUUSD.md
```

The ingest script reads timestamps as **exchange wall clock** and converts to true UTC, so a file
stamped in US Eastern survives both DST transitions; resampling is anchored to local midnight so a
5-minute bucket lines up with the session open instead of straddling it.

### Adding a strategy

Implement the `Strategy` interface in `src/lib/quant/strategies/`:

```ts
export const myEdge: Strategy = {
  id: "my-edge",
  label: "...",
  family: "mean-reversion",
  rationale: "one sentence on the ECONOMIC mechanism — why does someone lose money to this?",
  defaults: { lookback: 20, stopAtr: 1, rr: 1.5, maxBars: 20 },
  space: { lookback: { values: [10, 20, 40] }, /* ... */ },
  build(bars, p, inst) {
    const a = atr(bars, 14);
    return (i) => (/* decide using ONLY bars[0..i] */ null);
  },
};
```

Two hard rules:

- **The closure may not read `bars` beyond `i`.** `backtest.test.ts` enforces this by truncating the
  series and re-checking every decision — a new strategy is automatically covered by that test.
- **`rationale` must name a mechanism**, not a pattern. "Resting stops cluster beyond swing extremes,
  and filling them removes the fuel for continuation" is a mechanism. "Price bounces off the 200 EMA"
  is not, and a rule without one has no reason to keep working after it is discovered.

Register it in `strategies/index.ts`. Keep `tod-control` in the universe: it is a deliberate **null
benchmark** — a fixed-hour entry with no predictive content — and any candidate that cannot clearly
beat it has demonstrated nothing.

---

## 6. Module map

| module | responsibility |
| --- | --- |
| `types.ts` | Bar, Instrument, Trade, Strategy contracts |
| `clock.ts` | exchange-local time, DST rule verified against ICU |
| `instruments.ts` | contract specs and the cost model |
| `data.ts` | CSV ingestion, integrity audit, chronological splits |
| `series.ts` | causal indicators (NaN warm-up, never zero) |
| `synth.ts` | GARCH + fat-tail simulator for null calibration only |
| `backtest.ts` | next-bar fills, pessimistic intrabar, full costs |
| `strategies/` | the candidate universe + the null benchmark |
| `alpha.ts` | autocorrelation, variance ratios, event studies, budget |
| `stats.ts` | Sharpe, HAC t-stats, drawdown, tick-denominated edge |
| `bootstrap.ts` | stationary bootstrap, Reality Check, SPA |
| `deflated.ts` | PSR, Deflated Sharpe, minimum track record |
| `multipletest.ts` | Benjamini-Hochberg, Holm |
| `optimize.ts` | grid search, plateau/spike diagnosis |
| `walkforward.ts` | rolling and anchored walk-forward |
| `cpcv.ts` | combinatorially symmetric CV, PBO |
| `robustness.ts` | cost, regime, sub-period probes, go/no-go gates |
| `montecarlo.ts` | trade reshuffling, drawdown distribution, ruin |
| `portfolio.ts` | correlation, risk-based weights, diversification |
| `report.ts` | markdown rendering |

---

## 7. Reproducibility

Every bootstrap, permutation and Monte Carlo path is seeded (`--seed`, default `20250822`), so a
reported p-value is reproducible to the digit. Data files are **not** committed — they are large and
usually licensed — so a study is reproduced by re-running the ingest command against the source file
named in the study's own header.
