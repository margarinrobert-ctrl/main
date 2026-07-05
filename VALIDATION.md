# Validating "Semivariance Contrarian — Best (SAM-Best)"

## An institutional-grade research report on whether the edge is real

**Subject:** `SemivarianceContrarian.pine` — long-only contrarian on NAS100, signal = rolling
sum of daily realized semivariance asymmetry (RS⁺ − RS⁻) computed from 30-minute returns,
graded position = share of windows W ∈ [2, 30] with SAM < 0.

| Item | Claimed value (from the embedded study) |
|---|---|
| Market / feed | NAS100 (CFD-style symbol), 30-minute bars |
| Sample | 2,278 trading days, Nov 2016 – Sep 2025 (≈ 9.04 years) |
| Costs modeled | 2 bps per side commission only |
| Full-sample Sharpe (ensemble, 1×) | 0.83 |
| CAGR | 15.1 % |
| Max drawdown | −24.9 % |
| t-statistic of mean daily return | 2.51 |
| Average exposure | 0.58× |
| Walk-forward OOS Sharpe / efficiency | 0.79 / 0.94 (ensemble); 0.19 / 0.16 (refit best single W) |
| Monte Carlo | P(edge < 0) = 0.13 %, P(50 % DD) = 0.1 % |
| Buy & hold benchmark Sharpe | 0.73 |

Everything in this table is taken from the study described in the script's comments
(`backtests/nas100_semivariance/`). That study is **not in this repository**, so this report
treats every number as a *claim to be audited*, not a verified fact. Where the claims are
internally consistent I say so (several cross-check well); where the study is silent, that
silence is itself a finding.

---

# Part I — Executive Assessment

## I.1 What this strategy actually is

The signal comes from the realized-semivariance literature (Barndorff-Nielsen, Kinnebrock &
Shephard 2010; applied by Baruník, Kočenda & Vácha, SSRN 2815151): split each day's realized
variance into the part contributed by negative 30-minute returns (RS⁻, "bad volatility") and
positive returns (RS⁺, "good volatility"):

```
RS⁺_d = Σ_i r²_{d,i} · 1{r_{d,i} > 0}        RS⁻_d = Σ_i r²_{d,i} · 1{r_{d,i} < 0}

SAM_W(d) = Σ_{k=d−W+1..d} ( RS⁺_k − RS⁻_k )
```

Go long when SAM_W < 0 — i.e., **buy after stretches where downside volatility dominated**.
Economically this is a dip-buyer with a volatility-asymmetry filter: it monetizes the
short-horizon overreaction / risk-premium payoff that follows panicky selling in a structurally
upward-drifting index. That prior matters for validation: a long-only dip-buying rule on NAS100
over 2016–2025 sits on one of the most favorable beta tailwinds in market history, so the
central statistical question is not "did it make money" but **"did it beat an exposure-matched
long position by more than selection luck explains."**

### The "intraday" clarification — read this first

You asked for the evaluation "for intraday trading." As written, **SAM-Best is not an intraday
strategy**. It computes its signal intraday (from 30-minute bars) but it decides once per day,
holds overnight, and typical exposure episodes last days to weeks (average exposure 0.58×
across 9 years is impossible for a flat-by-close system). This distinction drives the whole
validation program:

- **Overnight gap risk is the dominant tail risk**, not intraday slippage. Stress tests (§8)
  must center on gaps taken at full conviction.
- **Financing cost of holding a levered CFD overnight is a first-order cost** the study did not
  model (§7). This is the single largest threat to the claimed 15.1 % CAGR.
- If you intend to force it flat by each session close (true day-trading), that is a
  **different strategy**: it forfeits the overnight component of the contrarian payoff (for
  equity indices, a large share of the drift and of post-panic rebounds accrues overnight),
  roughly doubles round-trips and therefore costs, and none of the study's statistics transfer.
  An intraday-only variant must restart the validation pipeline (§18) from step 4.

Throughout the report, "intraday" concerns appear where they belong: the 30-minute sampling of
the estimator (§3, §9), intraday execution of the daily rebalance (§7), and intraday crash
dynamics (§8).

## I.2 What the embedded study already did — credit where due

Mapped against the test battery in Part II, the study is unusually good for retail-grade work:

| Validation concept | Study's coverage | Quality |
|---|---|---|
| Parameter sensitivity (§3) | Full sweep W = 1..30, all positive, plateau W 4–13; ensemble = plateau integration | Strong — this is exactly how institutions neutralize a fitted parameter |
| Strategy-space audit (§12) | 90 configs (30 W × {contrarian, momentum} × sides) evaluated, correlations clustered | Good raw material for PBO/SPA — but those tests were not actually run |
| Walk-forward (§1) | Rolling 756d IS / 126d OOS; showed per-fold reoptimization of W destroys the edge | Strong, and the honest finding (0.16 efficiency for the refit) is a credibility signal |
| Monte Carlo (§2) | 2,000–10,000 paths per config; ruin probabilities; sizing sweep that *rejected* 2× and martingale | Good discipline; method (IID vs block) unstated — must be rerun as block bootstrap |
| Anti-leverage discipline | 1× cap justified by measured P(50 % DD); martingale removed | Institutionally correct instinct |
| Look-ahead hygiene | Signal uses only completed days; first-bar return excludes the overnight gap from RS | Correct (verified in the code — Appendix A) |

Several claims cross-check internally, which raises confidence that the study was actually run
rather than invented: t = 2.51 ≈ 0.83 × √9.04 exactly as it should; the claimed P(50 % DD) ≈
0.1 % matches a diffusion approximation from the claimed drift and vol to within a factor of ~2
(§2.7); 2,278 days ≈ 252 × 9.04 matches the stated date range.

## I.3 The seven material gaps

These are ordered by how much each one threatens the deployment decision.

**Gap 1 — There is no untouched out-of-sample data left, and the ensemble itself was chosen
after seeing everything.** The walk-forward result is real evidence, but the *decision* "use
the plateau ensemble rather than single-W, long-only rather than long-short, contrarian rather
than momentum, 1× rather than 2×" was made with full knowledge of all 2,278 days, including the
walk-forward OOS segments. Every byte of history has now been consumed by selection. The only
true holdout is the future: a pre-registered forward test (§5.4) is now **mandatory**, not
optional.

**Gap 2 — No formal multiple-testing accounting, and the sample is exactly at the minimum
length for the number of trials run.** At least 90 configurations were evaluated (plus sizing
variants, plus the other strategies in this repository — the trial count that matters is
everything you looked at, ever, on this instrument). The Minimum Backtest Length calculation
(§12.4) for N = 90 trials and a target Sharpe of 0.83 gives **≈ 9.0 years — precisely the
length of the sample**. In other words, the backtest is *just barely* long enough for a Sharpe
of 0.83 to be distinguishable from the best of 90 noise strategies, with no margin. Deflated
Sharpe Ratio, PBO via CPCV, and an SPA test over the full 90-config universe (§11, §12) must be
computed before believing the headline.

**Gap 3 — The reported t-stat tests the wrong hypothesis.** t = 2.51 says mean returns are
above zero. On a long-only NAS100 strategy over 2016–2025, most of that is beta. The relevant
test is the **paired alpha test**: regress strategy daily returns on the index's daily returns
and test the intercept with Newey–West errors (§11.3), or equivalently t-test the daily spread
versus a 0.58×-exposure buy-and-hold. Sharpe 0.83 vs benchmark 0.73 with lower drawdown is
encouraging but the *difference* has never been tested; a 0.10 Sharpe gap over 9 years is
roughly a 0.3-sigma event on its own (§11.2) — indistinguishable from luck without the paired
structure (correlation between the two return streams is what gives the paired test its power).

**Gap 4 — The cost model is incomplete for the instrument it targets.** 2 bps/side commission
is modeled; a CFD's overnight financing is not. At an average 0.58× notional exposure and a
typical index-CFD financing rate of benchmark + 2.5–3 % (call it ~6.5 % p.a. through this
sample's rate regimes), the unmodeled drag is roughly **0.58 × 6.5 % ≈ 3.8 % of equity per
year** — a quarter of the claimed CAGR, taking net Sharpe from 0.83 to roughly 0.55–0.65
before spread costs (§7.2). On futures (NQ/MNQ) the financing is embedded in the basis at
near-benchmark rates and this drag mostly disappears — instrument choice is not a detail here,
it is the difference between deployable and not.

**Gap 5 — One instrument, one bull-heavy sample.** Nov 2016–Sep 2025 contains three sharp,
fast-recovering corrections (Q4 2018, Mar 2020, 2022) and zero slow multi-year bears
(2000–02, 2008-style). A contrarian dip-buyer's nightmare regime — persistent grinding decline
where bad-vol dominance keeps it long the whole way down — is essentially absent from the
sample (§6). Cross-market pseudo-out-of-sample (SPX, DAX, Nikkei, RTY on identical rules) and
extended-history cash-index tests are the cheapest available antidote.

**Gap 6 — The Monte Carlo method is unspecified, and IID resampling flatters drawdowns.**
Equity-index daily returns have strong volatility clustering; reshuffling destroys it and
typically **understates** max-drawdown quantiles by 20–40 % for strategies whose exposure
correlates with volatility (this one's does, by construction — it levers up after bad-vol
spikes). The entire MC suite must be re-run with stationary/block bootstrap (§2, §10) before
the 0.1 % ruin figure is quotable.

**Gap 7 — Execution realism is untested.** Fills at the close of the first 30-minute bar with
zero slippage, no spread, no latency, no partial fills, no missed rebalances. The daily-graded
rebalancing (vote share changes of ≥10 % trigger orders) creates steady turnover whose cost
sensitivity has not been swept (§7). A strategy with ~0.8 gross Sharpe at daily rebalance
frequency usually survives realistic index costs — but "usually" is not a test.

## I.4 Verdict

**SAM-Best is a legitimate research candidate with unusually honest homework behind it, and it
is not yet deployable.** On the 0–100 robustness framework of §16 it scores **≈ 61/100** on
the study's own claims — squarely in the "continue validating, paper trade, do not risk
meaningful capital" band. The path to a deployable ~75+ is concrete and finite:

1. Re-run Monte Carlo as stationary block bootstrap (§2, §10) — days of work.
2. Compute DSR, PBO (via CPCV), and SPA over the archived 90-config universe (§11–12) — days.
3. Add financing + spread to the cost model, or re-target futures data (§7) — days.
4. Run the paired alpha test vs exposure-matched buy-and-hold (§11.3) — hours.
5. Cross-market replication on SPX/DAX/RTY, same fixed rules (§5.3, §6.5) — a week.
6. Pre-register a 12-month forward paper-trading test with written pass/fail criteria
   (§5.4, §18 stage 14) — and actually wait.

If steps 1–5 hold up, the strategy earns the forward test. If the forward test holds up, it
earns small live size under the scaling rules of §18. Nothing about the current record
justifies skipping ahead.

---

# Part II — The Test Battery

Each section follows the same eight lenses: **what it measures · why it matters · how to run
it · what a good result looks like · overfitting warning signs · Python implementation ·
statistical interpretation · institutional practice**, followed by an **"Applied to
SAM-Best"** verdict.

---

## 1. Walk-Forward Optimization (WFO)

### 1.1 What it measures
Whether the *process* of selecting parameters on past data produces profits on data that
selection never saw. WFO does not validate a parameter set; it validates a **selection rule**.

### 1.2 Why it matters
An in-sample backtest answers "did this configuration work on this history?" — a question
noise answers "yes" to constantly. WFO answers "if I had been re-fitting this strategy in real
time with only the data available at each moment, what would I have earned?" That is the only
question live trading asks.

### 1.3 The window taxonomy

```
Rolling / sliding (fixed IS length, both windows march forward):
  fold 1:  [======= IS 756d =======][ OOS 126d ]
  fold 2:        [======= IS 756d =======][ OOS 126d ]
  fold 3:              [======= IS 756d =======][ OOS 126d ]

Anchored / expanding (IS start pinned, IS grows):
  fold 1:  [==== IS ====][ OOS ]
  fold 2:  [======== IS ========][ OOS ]
  fold 3:  [============ IS ============][ OOS ]
```

- **Rolling (sliding)** — fixed-length IS window. Adapts to regime change; higher variance in
  fitted parameters because each fold forgets old data. Preferred when you believe the market's
  data-generating process drifts.
- **Anchored (expanding)** — IS grows from a fixed origin. Lower parameter variance, slower
  adaptation; parameters converge as IS grows, so late folds barely re-fit. Preferred when you
  believe the edge is stationary.
- Run **both**. Agreement between them is itself a robustness datum; large disagreement means
  the edge is regime-dependent — go to §6 to find out which regime.

### 1.4 Choosing IS and OOS lengths
Rules of thumb that institutional desks actually use:

- IS must contain **enough independent bets** to estimate the objective: for a daily-signal
  strategy, ≥ 500 trading days (≥ 2 years); the study's 756d (3y) is fine.
- IS should span **at least one full regime cycle** if possible (a vol spike + a calm stretch).
- OOS per fold: long enough for ≥ 20–30 position episodes; 126d (6 months) is the conventional
  floor for daily systems. Shorter OOS → noisier per-fold verdicts; longer OOS → fewer folds.
- IS:OOS ratio between 3:1 and 6:1; re-fit cadence = OOS length (you re-fit exactly as often
  as you would live).
- Total folds ≥ 8–10 or the aggregate OOS statistics are themselves under-sampled. The study's
  9y ÷ 126d ≈ 12 usable folds — adequate, minimal.

### 1.5 Walk-forward efficiency (WFE)

```
WFE = (annualized OOS metric, stitched across folds) / (average IS metric of the chosen configs)
```

Use Sharpe, not CAGR, as the metric (CAGR ratios explode when IS CAGR is small). Interpretation
bands used at prop desks:

| WFE | Reading |
|---|---|
| ≥ 0.7 | Excellent — selection generalizes |
| 0.5 – 0.7 | Acceptable — normal overfitting haircut |
| 0.3 – 0.5 | Weak — the fit captures noise plus a little signal |
| < 0.3 | Fail — the optimizer is fitting noise |

### 1.6 Pass/fail criteria beyond WFE
- Stitched OOS Sharpe > 0 with a t-stat computed **on the stitched OOS series only** (this is
  the cleanest significance number the backtest will ever give you — selection touched IS, not
  OOS returns, within each fold).
- ≥ 60 % of folds with positive OOS return; no single fold contributing > 40 % of total OOS PnL.
- **Parameter stability across folds**: plot the chosen parameter per fold. A healthy picture
  is a bounded random walk inside the plateau (e.g., W drifting 6→10→8). A parameter that
  jumps corner-to-corner of the grid each fold is an optimizer chasing noise.
- **Stitched OOS equity curve analysis**: same drawdown/TUW/slope diagnostics as §13/§15, but
  run on the stitched curve — it is your best forecast of live behavior. A stitched curve
  whose Sharpe is fine but whose PnL all sits in two folds fails the consistency lens.

### 1.7 Overfitting warning signs
- WFE high only for one particular IS/OOS split choice (the WFO meta-parameters were tuned —
  yes, that happens; sweep IS ∈ {504, 756, 1008}, OOS ∈ {63, 126, 252} and demand stability).
- IS Sharpe rising over folds while OOS falls — classic sign of increasing overfit as the
  optimizer accumulates degrees of freedom.
- OOS performance concentrated immediately after each re-fit, decaying within the OOS window
  (alpha decay faster than re-fit cadence).

### 1.8 Python implementation

```python
import numpy as np, pandas as pd

def walk_forward(prices, param_grid, is_len=756, oos_len=126, objective=sharpe):
    """prices: daily strategy inputs; returns stitched OOS returns + per-fold picks."""
    picks, oos_chunks = [], []
    for start in range(0, len(prices) - is_len - oos_len + 1, oos_len):
        is_slice  = prices.iloc[start : start + is_len]
        oos_slice = prices.iloc[start + is_len : start + is_len + oos_len]
        scores = {p: objective(backtest(is_slice, p)) for p in param_grid}
        best   = max(scores, key=scores.get)
        picks.append((oos_slice.index[0], best, scores[best]))
        oos_chunks.append(backtest(oos_slice, best))
    oos = pd.concat(oos_chunks)
    is_avg = np.mean([s for _, _, s in picks])
    return oos, picks, sharpe(oos) / is_avg      # stitched OOS, choices, WFE
```

`vectorbt` (`vbt.Splitter` / rolling split utilities) and `backtesting.py` (manual loop) both
support this; for grid sizes beyond ~10³ configs use `optuna` inside the IS fold — but log
every trial it evaluates (§12.5).

### 1.9 Statistical interpretation
The stitched OOS series is a *conditional* out-of-sample record: conditional on the selection
rule, unconditional on the parameter. Its t-stat is honest **for that selection rule**, but the
moment you compared several selection rules (single-W refit vs ensemble vs sizing variants) and
kept the winner, you are back in multiple-testing land one level up — deflate accordingly
(§12.2). There is no escape from this ladder except data you have never touched.

### 1.10 Institutional practice
Funds run WFO not as a one-off but as the **production re-fit process itself**: the same code
that walks forward in research re-fits the live parameters on schedule, so the backtest *is*
the live system pointed at history. Divergence between the WFO harness and production code is
treated as a sev-1 bug. Desks also demand the "WFO of the WFO": show me the result grid over
IS/OOS length choices, not the one you liked.

### 1.11 Applied to SAM-Best
The study's WFO is its strongest section, and its most interesting result is the *negative*
one: re-picking the best single W each fold collapses to OOS Sharpe 0.19, WFE 0.16 — direct
evidence that the single-W optimum (W=8, Sharpe 1.02) is mostly noise, and the honest reporting
of it is a good sign. Three caveats:

1. **For the ensemble, WFO is partially tautological.** The ensemble has no fitted parameters,
   so "IS optimization" selects nothing and WFE ≈ 0.94 largely restates that the strategy's
   performance is stable across subperiods (valuable! but it is §15 stability evidence, not
   selection-process evidence).
2. **The meta-choice was not walked forward.** The decision *ensemble vs single-W vs sizing
   variants* was made on the full sample. A cleaner test: a WFO whose IS step selects among
   {ensemble, best-single-W, split-sizing} by IS Sharpe — does the process that picks the
   ensemble also pick it fold by fold, and profit?
3. **The WFO meta-parameters (756/126) were not swept.** Cheap to add; do it.

**Verdict: pass with caveats — the strongest evidence in the study, worth 8/10 in §16.**

---

## 2. Monte Carlo Analysis

### 2.1 What it measures
The **distribution** of outcomes your single historical equity curve was drawn from. One
backtest is one sample path; every risk number computed from it (maxDD especially) is a single
order statistic with enormous sampling variance.

### 2.2 Why it matters
Max drawdown from one path is close to meaningless: rerun history with the same daily-return
distribution in a different order and maxDD routinely varies by a factor of 2–3. Position
sizing, ruin risk, and the "when do I shut it off" rule must come from the distribution, not
the point estimate.

### 2.3 The method family

| Variant | What you randomize | What it preserves / destroys |
|---|---|---|
| Trade reshuffling | Order of completed trades (or daily returns), no replacement | Preserves exact return set; destroys all serial structure |
| Bootstrap (IID) | Resample returns with replacement | Same, plus varies the return set itself |
| Block / stationary bootstrap | Resample blocks of consecutive days | Preserves short-range autocorrelation & vol clustering (§10) |
| Parametric ("randomized returns") | Draw from a fitted distribution (e.g., skew-t, or GARCH-filtered residuals recolored through the GARCH) | Clean tails control; model risk |
| Random slippage | Add per-trade cost noise, e.g. slip ~ half-normal(σ = k·bar range) | Execution uncertainty (§7) |
| Random execution delay | Shift each fill 0–n bars later | Latency sensitivity (§7) |
| Signal-preserved resampling | Block-bootstrap the *underlying price series*, re-run the full strategy | The only variant that keeps the signal→position→return chain intact |

The last row matters for SAM-Best specifically: its position size is a deterministic function
of recent realized semivariance, so **exposure and volatility are mechanically coupled**.
Reshuffling the strategy's daily returns breaks that coupling and produces paths the strategy
could never generate. The gold-standard MC here is: stationary-bootstrap the NAS100 30-minute
series in multi-day blocks → recompute RS±, SAM, votes, positions → new equity curve.

### 2.4 How to run it
1. Choose the resampling unit: daily strategy returns for quick answers; underlying 30m blocks
   for the signal-preserved version.
2. Generate ≥ 5,000 paths of the same length as the sample (2,278 days).
3. On each path record: terminal wealth, CAGR, Sharpe, maxDD, TUW, and whether equity ever
   breached −25 %, −50 % ("ruin" barriers).
4. Report percentile bands and barrier probabilities.

### 2.5 What a good result looks like
- Historical maxDD sits **inside the central 80 %** of the simulated maxDD distribution. If
  your real curve's DD is at the 5th percentile (much better than simulation), your one path
  got lucky in ordering — expect worse live.
- **P(Sharpe ≤ 0) < 5 %** (the study's "P(edge < 0)").
- **P(maxDD > 50 %) ≤ 1–2 %** at deployed size; institutional desks then size so that the 95th
  percentile simulated DD equals the mandate's kill-level with margin.
- Expected maxDD for planning = the 95th percentile of simulated maxDD, **not** the historical
  one. Rule of thumb: budget 1.5–2× historical maxDD.

### 2.6 Overfitting warning signs
- Results look fine under IID reshuffle but deteriorate sharply under block bootstrap →
  the strategy's PnL depends on volatility clustering in a way the point backtest hides
  (common for vol-conditioned strategies like this one).
- The historical path is a visible outlier (top decile) of its own simulated cloud →
  the specific historical ordering — i.e., the thing you fit to — did the work.

### 2.7 Statistical interpretation, with a cross-check of the study's claim
For a quick sanity check of ruin probabilities, the diffusion approximation: for log-equity
with drift ν = μ − σ²/2 > 0, the probability of *ever* falling to fraction (1−D) of the
starting level is

```
P(hit) = (1 − D)^(2ν/σ²)
```

With the claimed CAGR 15.1 % (μ_log ≈ 0.141), vol ≈ 15 % (Sharpe 0.83 backed out), ν ≈ 0.130,
2ν/σ² ≈ 11.5: P(50 % DD ever) ≈ 0.5^11.5 ≈ 3×10⁻⁴ — the same order as the study's 0.1 %.
The claim is internally consistent **under light-tailed IID assumptions**. That is exactly the
assumption vol clustering violates; block-bootstrap P(50 % DD) will be several times higher.
Consistency ≠ correctness.

### 2.8 Python implementation

```python
from arch.bootstrap import StationaryBootstrap
import numpy as np

rets = strategy_daily_returns.values           # or underlying 30m returns for signal-preserved
bs   = StationaryBootstrap(15, rets)           # mean block ≈ 15 days; see §10.4 for selection

def path_stats(x):
    eq = np.cumprod(1 + x)
    dd = 1 - eq / np.maximum.accumulate(eq)
    return np.array([x.mean()/x.std()*np.sqrt(252), dd.max()])

sims  = np.array([path_stats(d[0][0]) for d in bs.bootstrap(5000)])
print("P(SR<=0):", (sims[:,0] <= 0).mean())
print("maxDD p50/p95:", np.percentile(sims[:,1], [50, 95]))
```

### 2.9 Institutional practice
Every serious risk team owns a path-simulation engine; allocation sizes come from simulated
95th/99th-percentile drawdowns, and the strategy's **kill criterion is pre-committed as a
simulated quantile** ("shut off if live DD exceeds the 97.5th percentile of the bootstrap
cloud") so that the shutdown decision is made before emotions exist. Trade-level MC with random
slippage/delay is standard for anything faster than daily.

### 2.10 Applied to SAM-Best
The study ran large MC suites and used them for the right decision (rejecting 2× and the
martingale — the "24–47 % ruin" finding is precisely what MC is for). Two required upgrades:
(1) rerun everything as **stationary block bootstrap** and as **signal-preserved resampling of
the underlying**, because the exposure–volatility coupling makes IID numbers flattering; (2)
publish the maxDD distribution, not just barrier probabilities — the −24.9 % historical DD is
one draw; plan capital for the 95th percentile of the cloud (expect −35 % to −45 % at 1×).

**Verdict: good discipline, wrong (or unstated) resampler — 6–7/10 pending the block rerun.**

---

## 3. Parameter Robustness

### 3.1 What it measures
How performance responds to perturbing every knob. A real edge is a **region** in parameter
space; a fitted artifact is a **point**.

### 3.2 Why it matters
Markets will not hand you your exact backtest parameters' regime again. If Sharpe collapses
when W moves from 8 to 6, the "edge" is a property of one historical alignment, not of the
market. Parameter fragility is the single most common autopsy finding on failed retail
strategies.

### 3.3 How to run it
1. **1-D sensitivity curves**: sweep each parameter alone across its plausible range; plot the
   objective (net Sharpe). Look for smooth hills, not spikes.
2. **2-D heatmaps**: for each parameter pair, a grid of net Sharpe. The classic visual: a
   broad warm plateau with cool edges = robust; an isolated bright pixel in a cold field =
   curve fit. Describe-in-text version for SAM-Best: x-axis W (1..30), y-axis rebalance
   threshold (1..30 %), cell color = Sharpe — you want a horizontal warm band across all W at
   every sensible threshold, confirming W is the insensitive direction.
3. **Plateau detection, formalized**: for each grid point θ, compute the *neighborhood
   statistic* — mean or minimum objective over all grid points within one step of θ. Select
   (or, better, average over) the θ maximizing the neighborhood statistic, never the raw max.
   A useful plateau score: `plateau(θ) = min(SR(neighbors of θ)) / SR(θ)` — ≥ 0.7 is a real
   plateau; ≤ 0.3 is a spike.
4. **Multi-dimensional**: with > 3 parameters, random-sample the hypercube (Latin hypercube /
   Sobol), fit a smooth response surface (Gaussian process or gradient-boosted trees on
   (θ → SR)), and inspect where the surface is high *and flat* (low local gradient).
5. **Fragile-parameter identification**: rank parameters by normalized sensitivity
   `|ΔSR / SR| ÷ |Δθ / range(θ)|`. Anything > 2 is fragile — either remove it, fix it to an
   a-priori value, or ensemble over it.

### 3.4 What a good result looks like
- Objective positive over ≥ 70 % of the plausible parameter box.
- Chosen configuration's neighborhood-minimum within ~30 % of its own value.
- Performance degrades **gracefully and monotonically** toward the edges — cliffs are
  memorized events.

### 3.5 Overfitting warning signs
- Best point's Sharpe ≫ neighborhood mean (spike).
- The optimum sits at a grid **edge** (the optimizer wanted to leave the box — the box was
  chosen post hoc to frame a good number).
- Different objectives (Sharpe vs Calmar vs profit factor) select wildly different corners.
- Adding a parameter "fixed" a losing period — each parameter that exists to repair a specific
  historical stretch is a memorized patch. Count parameters: SAM-Best has effectively 4
  (wMin, wMax, minBars, rebalPct) plus sizing — commendably few.

### 3.6 Python implementation

```python
import itertools, numpy as np, pandas as pd

grid = {"W": range(1, 31), "rebal": [1, 5, 10, 20, 30]}
res  = pd.DataFrame([{**dict(zip(grid, p)), "sr": sharpe(backtest(*p))}
                     for p in itertools.product(*grid.values())])
pivot = res.pivot(index="rebal", columns="W", values="sr")
# plateau score per cell: min of the 3x3 neighborhood / own value
import scipy.ndimage as ndi
neigh_min = ndi.minimum_filter(pivot.values, size=3, mode="nearest")
plateau   = neigh_min / pivot.values
```

Plot with `matplotlib`/`seaborn` heatmaps; `optuna` visualizations (`plot_contour`,
`plot_param_importances`) do the multi-dimensional version for free.

### 3.7 Statistical interpretation
A plateau is evidence the objective surface's *signal* component dominates its *noise*
component locally — noise is uncorrelated across parameter values (approximately), so it
cannot build broad hills, only spikes. Caveat: heavily overlapping configurations (W=8 vs W=9
share almost all their positions) have **correlated noise**, so a plateau across W alone is
weaker evidence than it looks — a common shock (buying the COVID dip) lights up all W
simultaneously. This is why cross-market replication (§5.3) is the true plateau test.

### 3.8 Institutional practice
Parameter averaging — trading the centroid or the equal-weight ensemble of the plateau rather
than the peak — is standard at systematic funds (it is a poor man's Bayesian posterior mean and
usually gives up ~10 % of in-sample Sharpe for far better out-of-sample retention). Desks also
mandate: no re-tuning outside scheduled re-fits, and any parameter whose live value differs
from research must page someone.

### 3.9 Applied to SAM-Best
This is the study's best-designed dimension: 30/30 positive W, an identified plateau (4–13),
and — crucially — the deployed configuration is the **ensemble across the whole family**, not
the peak. That is textbook institutional handling. Remaining holes: (a) the *other* parameters
were never swept — run the W × rebalPct heatmap, sweep minBars 10–26, and sweep the sampling
frequency of the estimator itself (RS± from 5m/15m/30m/65m bars — realized-variance estimators
are sensitive to sampling; if the edge exists only at exactly 30m, that's a red flag; expect
mild degradation at 5m from microstructure noise, none at 65m); (b) the correlated-noise caveat
above means the 30-for-30 result overstates independence — the cluster analysis already showed
corr ≈ 1.00 within the family, i.e., the study effectively confirmed its plateau is ~2–3
independent observations, not 30.

**Verdict: strongest section of the study — 9/10, finish the non-W sweeps.**

---

## 4. Cross Validation for Financial Time Series

### 4.1 Why traditional k-fold is inappropriate — the leakage mechanics
Standard k-fold assumes samples are IID. Financial observations violate this three ways, and
each violation leaks information from test to train:

1. **Serial correlation of features**: SAM_W(d) shares up to 29 days of raw data with
   SAM_W(d+1). If day d is in train and day d+1 in test, the model has effectively seen the
   test features.
2. **Overlapping labels**: if the label is a k-day forward return, train and test labels
   built from overlapping windows share outcomes.
3. **Non-stationarity**: random shuffling puts 2024 data in the train fold used to "predict"
   2017 — a time machine. Regimes make folds non-exchangeable, so k-fold's variance estimate
   of generalization error is biased optimistic.

The result: shuffled k-fold on financial data routinely certifies pure-noise strategies with
beautiful "out-of-fold" Sharpe. It is not conservative; it is broken.

### 4.2 The correct toolkit

- **Time-series split (rolling / expanding validation)**: train always precedes test.
  `sklearn.model_selection.TimeSeriesSplit` is the expanding form; a fixed `max_train_size`
  makes it rolling. This is walk-forward (§1) in ML clothing.
- **Purged k-fold** (López de Prado): folds are contiguous time blocks; training samples whose
  **label windows overlap** the test block are *purged*, and a further **embargo** (skip a
  buffer, e.g. 1–5 % of the sample, after the test block) removes leakage via serial
  correlation of features.

```
timeline:  [ train ..... |purge| TEST |embargo| ..... train ]
```

- **Combinatorial Purged CV (CPCV)**: split the sample into N contiguous groups; every
  combination of k groups serves as the test set once (C(N,k) splits), with purging/embargo at
  every boundary. Two payoffs: (i) each configuration gets **many** backtest paths instead of
  one — you get a *distribution* of OOS Sharpe; (ii) it is the engine that computes PBO
  (§12.1). Typical setting N=12–16, k=2.
- **Nested CV**: outer loop measures generalization; inner loop (inside each outer-train)
  does hyperparameter selection. Mandatory whenever you both tune and evaluate — tuning on the
  same folds you report from is self-grading homework.

### 4.3 How to run it / good results / warning signs
Run CPCV on the strategy-selection problem itself: the "model" is the choice among the 90
configs; each CPCV split picks the best config on train and scores it on test. Good result:
the IS-best config's OOS rank distribution concentrated in the top quartile; OOS Sharpe
distribution mostly > 0. Warning signs: OOS rank of the IS-best uniform or worse (that is
exactly what PBO quantifies); performance in splits containing 2020 dominating everything
(regime concentration, §6).

### 4.4 Python implementation

```python
import numpy as np
from itertools import combinations

def cpcv_splits(n_obs, n_groups=12, k_test=2, purge=30, embargo=10):
    edges  = np.linspace(0, n_obs, n_groups + 1, dtype=int)
    groups = [np.arange(edges[i], edges[i+1]) for i in range(n_groups)]
    for test_ids in combinations(range(n_groups), k_test):
        test  = np.concatenate([groups[i] for i in test_ids])
        train = np.ones(n_obs, bool)
        train[test] = False
        for i in test_ids:                       # purge + embargo around each test block
            lo, hi = edges[i], edges[i+1]
            train[max(0, lo - purge):lo] = False
            train[hi:min(n_obs, hi + embargo)] = False
        yield np.where(train)[0], test
```

(`mlfinlab` ships PurgedKFold/CPCV implementations, but see the §19 licensing note; the ~25
lines above are all you need.) Purge length for SAM-Best: ≥ 30 days — the maximum feature
lookback (wMax) — plus a few days of embargo.

### 4.5 Statistical interpretation & institutional practice
CPCV's C(N,k) paths are **not independent** (they share data), so don't t-test across them
naively; use them as a descriptive distribution and as PBO input. Institutionally, purged CV /
CPCV is the López de Prado-school standard for any ML-flavored signal research (AQR, many
pods); classic CTA shops often skip CV and rely on WFO + cross-market replication instead —
both cultures agree that plain shuffled k-fold is malpractice on financial data.

### 4.6 Applied to SAM-Best
No CV of any kind was run. The strategy has few parameters, so CV's main value here is not
tuning — it is (a) **CPCV → PBO** on the archived 90-config grid (the highest-value missing
test in the whole program, directly quantifying Gap 2), and (b) rolling-origin validation of
the *meta-choice* (§1.11 point 2). Estimated effort: a day with the code above.

**Verdict: absent — 0/10 as performed, but cheap to fix and the data to fix it already exists.**

---

## 5. Out-of-Sample Testing

### 5.1 What it measures / why it matters
The performance of the strategy on data that influenced **no decision** — not parameter
choice, not strategy-family choice, not sizing, not the decision to keep researching this idea
rather than abandon it. Every one of those decisions consumes data. OOS is the only currency
that buys belief; everything else is promissory.

### 5.2 The validation hierarchy

```
   ┌────────────────────────────────────────────────────────┐
   │ TRAIN (in-sample): fit, explore, iterate freely        │
   ├────────────────────────────────────────────────────────┤
   │ VALIDATION: model/parameter selection, WFO, CV         │
   ├────────────────────────────────────────────────────────┤
   │ TEST (lockbox): touched ONCE, at the very end          │
   ├────────────────────────────────────────────────────────┤
   │ FORWARD: paper / small-live — data that didn't exist   │
   └────────────────────────────────────────────────────────┘
```

Lockbox discipline: carve out the final 12–18 months (and ideally a random earlier year)
**before research begins**; log a hash of the untouched file; evaluate the finished strategy on
it exactly once. If it fails, the strategy dies — you do not get to "fix" it and re-test,
because the lockbox is now spent. Institutional versions automate this: researchers physically
cannot query lockbox dates.

### 5.3 Cross-market and cross-feed OOS
Data you never optimized on is OOS even if it is contemporaneous: run the **frozen** rules on
SPX, RTY, DAX, Nikkei 30m data, and on a *different vendor's* NAS100 feed (cash index vs CFD vs
NQ futures). For an economically-motivated signal like semivariance asymmetry, directionally
similar results across correlated indices are near-mandatory; a signal that only works on one
broker's CFD feed of one index is describing that feed, not markets.

### 5.4 Forward performance — the pre-registered test
Because SAM-Best has no lockbox left (Gap 1), forward testing carries the entire OOS burden.
Do it properly — write the protocol **before** it starts, commit it to this repo:

- Period: ≥ 12 months paper (or ≥ 250 trading days ≈ enough for the paired test below to have
  power against a dead edge).
- Pass criteria (example, tune to taste but *in advance*): net-of-realistic-cost Sharpe ≥ 0.3;
  paired alpha vs 0.58× buy-and-hold t ≥ 1.0; maxDD within the block-bootstrap 95th
  percentile; live fills within 5 bps RMS of modeled fills.
- Kill criteria: DD beyond the 97.5th simulated percentile, or 6 consecutive months of
  negative alpha spread.

### 5.5 Performance decay — what to expect and measure
Published/selected edges decay: the empirical literature (McLean & Pontiff 2016) finds ~50 %
post-publication decay in anomaly returns; practitioner rule of thumb is to **haircut backtest
Sharpe by 30–50 %** for planning. Measure decay explicitly: rolling OOS-to-IS Sharpe ratio
over the forward period; regression of monthly alpha on time (a significantly negative slope =
structural decay, not noise).

### 5.6 Statistical comparison of IS vs OOS
Don't eyeball it: (a) **two-sample t / Welch** on daily returns IS vs OOS (expect
insignificance — you *want* to fail to reject equality); (b) **Kolmogorov–Smirnov** on the two
return distributions (detects shape change, e.g. vanished right tail); (c) **Mann–Whitney U**
as the nonparametric location check; (d) Chow-style break test at the IS/OOS boundary on the
alpha regression. A "good result" is p > 0.10 everywhere — no detectable degradation — with the
caveat that these tests have modest power at 1–2 years of OOS, which is precisely why the pass
criteria in §5.4 are set on levels, not on IS-equality.

### 5.7 Applied to SAM-Best
Nothing untouched remains through Sep 2025; Oct 2025 → today is *almost* clean (it existed
during final selection but allegedly wasn't used — document that claim) and everything after
today is genuinely clean. Actions: (1) freeze the ruleset (the .pine in this repo is the
frozen artifact — good); (2) pre-register the §5.4 protocol; (3) run the frozen rules on ≥ 3
other index futures and a second NAS100 feed this week; (4) start the paper-trade clock.

**Verdict: the decisive missing evidence — 3/10 today (WFO's stitched OOS earns the 3), fully
recoverable in 12 months.**

---

## 6. Regime Testing

### 6.1 What it measures / why it matters
Whether the edge is a property of markets or a property of one market *mood*. A strategy whose
entire PnL comes from one regime is a bet that the regime repeats — that bet should be priced
consciously, not discovered in the post-mortem. For a long-only contrarian dip-buyer the
question is existential: it is structurally short crash-persistence (it buys into sustained
declines) and long mean-reversion.

### 6.2 How to define regimes (objectively, in code, not by eye)
- **Bull / bear / sideways**: label by 200-day MA slope and price-vs-MA, or by
  drawdown state (bear = index in >20 % drawdown), or by an HMM (2–3 states on daily
  returns — `hmmlearn`). Use rules fixed *ex ante*.
- **High / low volatility**: terciles of trailing 21-day realized vol (or VIX/VXN terciles —
  external, so no circularity with the strategy's own RS-based signal).
- **Trending / mean-reverting**: rolling Hurst exponent, variance-ratio test (Lo–MacKinlay),
  or ADX terciles.
- **Event windows**: FOMC days ±1, CPI days, elections, index rebalances; and the named
  episodes — Volmageddon (Feb 2018), Q4 2018, COVID (Feb–Apr 2020), the 2022 hiking bear,
  SVB (Mar 2023), the Aug 2024 yen-carry unwind, plus (out of sample) 2000–02 and 2008 on
  proxy data.

### 6.3 How to run it / what a good result looks like
Tag every trading day with its regime labels; report per regime: annualized return, Sharpe,
maxDD, exposure, hit rate, and **share of total PnL**. Good result: (a) no regime with
catastrophic loss; (b) PnL not > 50 % concentrated in a single regime-episode; (c) the
strategy's *behavior* matches its thesis (a contrarian should earn in high-vol recoveries and
idle in calm trends — if it earns somewhere its thesis doesn't predict, that's unexplained
fitting, not a bonus).

### 6.4 Warning signs, statistics, institutional use
Warning: edge existing only in the regime that dominates the sample (here: buy-the-dip bull).
Statistically, per-regime Sharpes have huge standard errors (each regime may be < 2 years of
data — SE(SR) ≈ 1/√years, §11.2), so treat the table as diagnostic, not confirmatory; test
formally with a regression of strategy returns on regime dummies (HAC errors) and ask whether
the *conditional alpha* differs. Institutions run exactly this as "PnL attribution by
environment" and size strategies by their worst-regime behavior, not their average.

### 6.5 Applied to SAM-Best
The sample's three bears (Q4-18, COVID, 2022) were all fast and V-shaped or
rate-driven-but-orderly — ideal contrarian terrain. Required table: the eight regime slices
above. Two hypotheses to falsify: (1) *most PnL sits in ≤ 60 trading days around the three
crash-recoveries* — if true, the effective sample is ~6 independent events, and the t-stat's
2,278-day denominator is cosmetic (§11.2 addresses via block methods); (2) *in a grinding
18-month bear (2000–02 style) the system stays near-fully long throughout* — test on NDX
2000–02 daily data with a semivariance proxy from daily OHLC (Rogers–Satchell/Parkinson-based
downside proxy) or on any 30m data you can source; if exposure stays pinned ≥ 0.8 while the
index halves, you have quantified the nightmare and can design the (pre-registered) regime
kill-switch: e.g., suspend entries when index < 200d MA **and** trailing 63d strategy DD >
15 % — then validate that overlay from scratch, because an unvalidated safety switch is just
another fitted parameter.

**Verdict: untested — 5/10 provisional (the 2022 year is genuinely in-sample evidence of
surviving one rate-driven bear; the slow-bear scenario remains uncovered).**

---

## 7. Execution Robustness

### 7.1 What it measures / why it matters
How much of the paper edge survives contact with a real broker. Gross-to-net is where most
retail strategies die, and the study's cost model (2 bps/side commission, nothing else) is the
weakest link in an otherwise careful program. For a ~0.8-Sharpe daily-rebalanced strategy the
edge per trade is small; costs are not a haircut, they are a competitor.

### 7.2 The full cost stack for this instrument — worked numbers

| Cost | CFD (as configured) | NQ / MNQ futures alternative |
|---|---|---|
| Commission | ~2 bps/side (modeled ✓) | ~$0.5–2.5/side MNQ ≈ 0.5–1 bp — cheaper |
| Spread | 1–2+ index points ≈ 0.5–1 bp/side, widens 5–20× in stress | ~0.25–0.5 pt NQ ≈ 0.1–0.2 bp |
| **Overnight financing** | **(benchmark + 2.5–3 %) × notional / 360 per night — NOT modeled** | Embedded in basis at ≈ benchmark flat; no markup |
| Weekend financing | 3× on Fridays | n/a (basis) |
| Roll | n/a | 4×/year, ~1–2 bps total if done at fair basis |

Worked drag (Gap 4): average 0.58× exposure × ~6.5 % financing ≈ **3.8 % of equity per
year**. Claimed CAGR 15.1 % → ≈ 11.3 % net of financing; Sharpe ≈ 0.83 → ≈ 0.6. Every
downstream number in this report (DSR, MinBTL, the §16 score) should be recomputed at the net
figure. On futures the drag shrinks to ≈ benchmark-embedded (already in the price series if
you backtest futures data) — **re-running the study on NQ futures 30m data is the single
highest-value execution fix available**.

### 7.3 The test battery
1. **Commission/spread sweep**: rerun at 0.5×, 1×, 2×, 3×, 5× total per-side cost. Plot Sharpe
   vs cost; report the **breakeven cost** (where Sharpe = 0). Healthy daily-frequency
   strategies break even at ≥ 4–5× realistic costs.
2. **Slippage models**: fixed bps; spread-proportional; and volatility-scaled
   (slip = k · σ_bar, k ∈ [0.1, 0.5]) — the honest one, since this strategy trades *more* when
   vol is high, exactly when slippage is worst. Randomize per-fill (half-normal) inside the
   Monte Carlo (§2.3).
3. **Latency / delayed entries & exits**: execute the daily rebalance at the close of bar
   +1, +2, +3 (i.e., 30/60/90 minutes late), and at the *next day's* first bar. A daily signal
   whose edge dies with a 30-minute delay was never a daily edge — it was a data artifact.
   Also test executing at other points in the session (noon, last bar): sensitivity to
   execution *time-of-day* reveals whether the "first-bar close" fill is load-bearing.
4. **Partial fills**: cap fill quantity at x % of intended (50/75/90 %) — mild for index
   CFDs/futures at retail size, but confirms sizing math doesn't break.
5. **Missed trades**: randomly skip 5–10 % of rebalance orders (platform outages, rejected
   orders, you were asleep). 1,000 MC paths; a robust daily system loses < 10 % of Sharpe.

### 7.4 Good result / warning signs / stats / institutional practice
Good: monotone, shallow degradation in every direction; breakeven ≥ 3× realistic costs; delay
curve flat out to a day. Warning: edge halving from one bar of delay (look-ahead leak or
microstructure artifact — investigate before anything else); PnL concentrated in high-slippage
moments. Institutionally, execution assumptions are owned by a separate TCA function — research
must use the *trading desk's* cost curves, not its own optimism, and live implementation
shortfall (paper fill vs actual fill) is tracked per order forever; the backtest's cost model
is recalibrated to realized shortfall quarterly.

### 7.5 Applied to SAM-Best
Also model the **live execution path**: on TradingView, `process_orders_on_close` fills at the
first 30m bar's close in backtest, but live alerts fire *after* that close and a webhook →
broker order lands seconds-to-minutes later — so live fills are systematically at bar+ε prices.
The +1-bar delay test bounds this. And sweep `rebalPct` (5/10/20/30 %): it trades turnover
against tracking error of the vote; verify the default 10 % isn't a fitted sweet spot (expect a
flat plateau; a spike would be a red flag per §3).

**Verdict: largest credibility gap after OOS — 4/10 until financing + delay + cost sweeps run.**

---

## 8. Stress Testing

### 8.1 What it measures / why it matters
Survival, not performance, under conditions absent from (or rare in) the sample. Expectancy is
irrelevant if a tail event ends the account first. For a system that is *by construction* at
maximum long exposure during volatility panics, stress testing is not an appendix — it is the
sizing authority.

### 8.2 The scenario battery
1. **Historical replay**: paste the worst historical sequences into the sample as if they
   happened tomorrow at today's exposure: Oct 1987 (−22 % day), 2000–02 (−78 % NDX over 2
   years — see §6.5), Oct 2008 (−10 % days back-to-back), May 2010 flash crash (−9 % in
   minutes, V-recovery), Aug 24 2015 open, Feb 2018, Mar 2020, Aug 2024. For each: strategy
   PnL, margin status, drawdown.
2. **Synthetic overnight gaps**: −5 %, −10 %, −15 % opens while at strength = 1. At 1×
   notional these map ≈ 1:1 to equity (−15 % gap ≈ −15 % equity) — survivable; at the 2× the
   study already rejected, −15 % → −30 % plus margin-call mechanics. Note futures limit-locks
   (−7/−13/−20 % cash circuit breakers; ±5 % overnight limit on NQ) actually *cap* overnight
   fill damage but can trap you unable to exit for hours.
3. **Flash crash / intraday**: since rebalances happen once daily, an intraday crash hits a
   static position — replay the 2010 path against full exposure; the loss is mark-to-market
   unless margin forces liquidation at the low (model the broker's stop-out level: at
   `margin_long=10` a 10 % adverse move on 1× notional consumes 100 % of a 10 %-margined
   posted amount — verify how much *cash buffer* the account design leaves and at what gap the
   broker force-closes; this is the real ruin mechanism, not expectancy).
4. **Liquidity shock / spread widening**: multiply slippage+spread by 10–20× on the worst 1 %
   of days (empirically accurate for CFDs in crashes); rerun.
5. **Exchange/broker outage**: force no-trading windows of 1–5 days at random and, worse, *at
   the worst* moments (start of each historical crash) while exposed.
6. **Extreme volatility**: scale the worst historical month's daily vol ×1.5–2 and re-run the
   signal→position loop (the strategy will go max-long into it; that is the point).

### 8.3 Good result / warning signs / interpretation / institutional use
Good: no scenario produces account ruin or forced liquidation at 1×; worst synthetic equity DD
stays within ~1.5× the block-bootstrap 95th percentile; the strategy's *response* (it will buy
every crash) is understood and capitalized for. Warning: any scenario where broker margin
mechanics — not strategy logic — determine the outcome; that means size, not signal, is the
binding constraint. Institutions run standardized scenario grids (2008 replay, rates ±200bp,
vol ×2) monthly, with results wired to position limits; a strategy's capital allocation is
`min(expectancy-optimal, stress-survival)` and the second term usually binds.

### 8.4 Applied to SAM-Best
Quantify one number above all: **conditional gap exposure** — the distribution of overnight
index moves *on nights the strategy holds ≥ 0.8 exposure*. Because strength rises after
bad-vol clusters, those nights are precisely the fat-tailed ones; unconditional gap statistics
flatter it. Then the sizing statement becomes concrete: at 1× with, say, a −13 % worst
conditional gap, equity survives (−13 %); the account must therefore run with enough free
margin that a −15 % gap cannot trigger a stop-out. The study's own rejection of 2× already
anticipates this conclusion.

**Verdict: partially implied by MC ruin numbers but never scenario-tested — 5/10.**

---

## 9. Noise Testing

### 9.1 What it measures / why it matters
Whether the strategy responds to *structure* or to the particular noise realization in one
vendor's price file. A real edge is a smooth functional of the data; a curve-fit is a
delta-function on it. Especially relevant here because RS± is **quadratic in returns** —
single large 30m bars carry outsized weight in the signal.

### 9.2 The battery
1. **Random price perturbation**: add ε ~ N(0, (k · bar_range)²), k ∈ {0.05, 0.1, 0.25}, to
   each close (adjust O/H/L for consistency: H := max(H, O, C), L := min(L, O, C)); regenerate
   returns; rerun 500×. Report the Sharpe distribution and the **signal flip rate** (share of
   days the ensemble vote changes by > 0.2).
2. **Indicator noise**: jitter the computation itself — random ±1 bar alignment of day
   boundaries, ±10 % perturbation of minBars, alternative return definitions (close-to-close
   vs O-C first bar).
3. **Data corruption**: inject bad ticks (a fake ±3 % 30m bar once a quarter — does one bad
   print flip SAM's sign for a month? quadratic weighting says it might), duplicated bars,
   zero-volume stubs.
4. **Missing candles**: delete random 30m bars (0.5–2 %), delete whole sessions, simulate DST
   misalignment and half-days (this interacts with `minBars=20` — sweep it).
5. **Randomized OHLC within realistic limits**: resample each bar's OHLC inside its true
   high-low range keeping close direction — the maximum-entropy version of "same day,
   different path."
6. **The free, most realistic noise test: different vendors.** Run the identical script on
   NAS100 from 2–3 brokers + NQ futures + cash NDX. Position-series correlation across feeds
   ≥ 0.9 = robust; ≤ 0.7 = the strategy trades feed idiosyncrasies. (CFD feeds differ in
   session boundaries, holiday stubs, and overnight ranges — all of which feed RS±.)

### 9.3 Good result / warnings / stats / institutions / applied
Good: median perturbed Sharpe within 15–20 % of baseline at k = 0.1; flip rate < 5 %; graceful
monotone decay in k. Warning: bimodal perturbed-Sharpe distribution (knife-edge thresholds —
here, SAM crossing 0 with 29 windows voting can cascade); a single injected bad tick moving
monthly PnL. Statistically this is a **stability-under-perturbation** (influence-function)
argument, not a hypothesis test — you are estimating the derivative of performance with
respect to data error. Institutions run it implicitly via multi-vendor data reconciliation and
explicitly for microstructure-sensitive signals. For SAM-Best, one cheap hardening if noise
tests fail: winsorize 30m returns at ±4σ before squaring, or use a robust semivariance
(median-of-means) — then re-validate the modified signal from §18 step 4 (it is a new
strategy).

**Verdict: untested — 4/10 provisional; the ensemble's vote-averaging gives some inherent
noise damping (a single window flip moves the position only 1/29), which is worth real credit.**

---

## 10. Bootstrap Methods

### 10.1 What they measure / why they matter
Sampling distributions of any statistic (Sharpe, maxDD, expectancy) without assuming
normality — essential because daily equity-strategy returns are fat-tailed, skewed, and
autocorrelated in volatility, so textbook standard errors are wrong in the direction of
overconfidence.

### 10.2 The family

| Method | Mechanics | Use when |
|---|---|---|
| IID bootstrap | Resample single days with replacement | Never for financial series except as a lower bound |
| Block bootstrap (fixed) | Resample non-overlapping blocks of length L | Simple; block-edge artifacts |
| **Moving block** | Resample overlapping blocks of length L, concatenate | Standard choice; preserves dependence up to lag ≈ L |
| **Circular block** | Moving block on the series wrapped into a circle | Fixes end-effects (last days under-sampled otherwise) |
| **Stationary (Politis–Romano)** | Random geometric block lengths, mean L | Smoother; the resampled series is stationary; default recommendation |

### 10.3 How to run / good result
Resample daily strategy returns (and, for the signal-preserved variant, underlying 30m data —
§2.3) 5,000–10,000×; compute the statistic per path; report percentile or BCa intervals.
Good result: the 95 % CI for annualized Sharpe **excludes 0**; the CI for maxDD informs sizing
(§2.5); expectancy CI excludes 0 at the trade/episode level.

### 10.4 Block length selection
Politis–White (2004) automatic selection (`arch` implements the optimal block length
estimator: `arch.bootstrap.optimal_block_length`), typically O(n^{1/3}) — for 2,278 daily
observations expect L ≈ 10–25, larger if volatility clustering is strong (for NAS100 daily
returns it is). Sensitivity-check L ∈ {5, 10, 20, 40}: conclusions shouldn't flip.

### 10.5 Python

```python
from arch.bootstrap import StationaryBootstrap, optimal_block_length
import numpy as np

L  = optimal_block_length(rets)["stationary"].iloc[0]
bs = StationaryBootstrap(L, rets)
ann_sr = lambda x: x.mean() / x.std() * np.sqrt(252)
ci = bs.conf_int(ann_sr, reps=10000, method="bca")     # BCa 95% CI for Sharpe
```

### 10.6 Interpretation / institutional practice / applied
The bootstrap CI answers "given the dependence structure I preserved, how variable is this
statistic?" — it does **not** correct for selection bias (§12 does that); a beautiful
bootstrap CI around a cherry-picked strategy is a precise measurement of a biased quantity.
Institutions use block bootstraps as the default error bars on every reported backtest metric
and as the engine inside Reality Check/SPA (§11.5). For SAM-Best: expected result at net-of-
financing returns — Sharpe CI ≈ (0.05, 1.15) wide; if the lower bound hugs zero that is not
failure, it is honesty (see §11.2: 9 years of a 0.6–0.8 Sharpe is intrinsically borderline);
the *paired* bootstrap of strategy-minus-benchmark daily spread is the CI that matters.

**Verdict: not performed (or not reported) — but everything needed is in `arch`; a day's work.**

---

## 11. Statistical Significance

### 11.1 p-values, used correctly
A p-value is P(data at least this extreme | no edge). It is **not** P(no edge | data), and it
is meaningless without the trial count behind it (§12). One pre-registered strategy with
p = 0.006 is evidence; the best of 90 tries with p = 0.006 is close to nothing — under 90
independent null trials you *expect* min-p ≈ 1/90 ≈ 0.011. Every p below should be read
alongside §12's corrections.

### 11.2 Confidence intervals and the honest width of a 9-year Sharpe
Lo (2002): SE(ŜR_annual) ≈ √((1 + SR²/2) / years). For SR = 0.83, 9.04 years:
SE ≈ √(1.344/9.04) ≈ 0.39 → **95 % CI ≈ (0.07, 1.59)**. Read that again: nine years of daily
data cannot distinguish a 0.2-Sharpe mediocrity from a 1.5-Sharpe monster. This single equation
is the strongest argument for cross-market replication and forward testing — time is the only
variable that shrinks it (√T), and NAS100 will not produce 30 more years on demand. It also
prices the buy-and-hold comparison: the 0.83 vs 0.73 gap is ≈ 0.26·SE — nothing, *unpaired*.
Paired (next subsection), the correlation between the two series shrinks the effective SE by
√(2(1−ρ)/2); at ρ ≈ 0.9 the paired test is ~3× more powerful than the unpaired glance.

### 11.3 t-tests — the right ones
- **One-sample t on daily returns** (what the study's 2.51 is): fine as a first pass; use
  **Newey–West/HAC** standard errors (daily strategy returns inherit volatility clustering;
  naive SEs are anticonservative by 10–30 %). `statsmodels`:
  `OLS(rets, ones).fit(cov_type="HAC", cov_kwds={"maxlags": 10})`.
- **Paired alpha test (the decisive one, Gap 3)**: regress strategy daily returns on
  benchmark daily returns, HAC errors; test intercept α > 0. Equivalently t-test the daily
  spread vs 0.58× buy-and-hold. This is the test that separates "timing skill" from
  "was long NAS100 while NAS100 went up."
- **Trade/episode-level t** on per-episode PnL (independent-ish units; more honest n than
  2,278 autocorrelated days — see §14.2).

### 11.4 Nonparametric tests
- **Wilcoxon signed-rank** (one-sample analogue) on daily/episode returns: robust to the fat
  tails that inflate/deflate the t.
- **Mann–Whitney U**: two independent samples — IS vs OOS returns, regime A vs regime B.
- **Kolmogorov–Smirnov**: whole-distribution equality — IS vs OOS shape drift (§5.6), real
  returns vs MC-simulated (model adequacy). All in `scipy.stats`
  (`wilcoxon`, `mannwhitneyu`, `ks_2samp`). These trade power for robustness; agreement
  between t and Wilcoxon is a small robustness datum in itself; disagreement means tails are
  driving the mean — go look at them (§13.6, §14.4).

### 11.5 White's Reality Check and Hansen's SPA
The multiple-testing tests built for exactly this situation: **is the best rule in a universe
of rules better than benchmark, accounting for having searched the universe?**

- **White's Reality Check (2000)**: H₀ = "the best strategy in the universe has no edge over
  benchmark." Compute per-strategy performance differentials vs benchmark; stationary-
  bootstrap the joint differential series (all 90 configs on identical resampled paths — this
  preserves the correlation between configs, which is what makes it valid); the test statistic
  is the max across configs; p = fraction of bootstrap worlds whose max beats the observed max.
- **Hansen's SPA (2005)**: studentized version, less distorted by the inclusion of very bad
  rules in the universe (relevant here — the momentum configs are dreadful and would blunt
  White's RC; SPA handles them).

```python
# sketch: SPA over the 90-config universe, benchmark = 0.58x buy & hold
d = config_daily_rets.sub(0.58 * bench_rets, axis=0)        # T x 90 differentials
bs = StationaryBootstrap(L, d)
t_obs = np.sqrt(len(d)) * d.mean() / d.std()
t_max = t_obs.max()
boot_max = [np.sqrt(len(s)) * ((s - d.mean()).mean(0) / d.std()).max()
            for (s,), _ in bs.bootstrap(5000)]              # recentered null
p = np.mean(np.array(boot_max) >= t_max)
```

### 11.6 False Discovery Rate
When you evaluate many configs and want to keep *several*, control FDR (expected share of
false keeps) with **Benjamini–Hochberg**: sort p-values, keep all i with p(i) ≤ q·i/N
(q = 0.05–0.10). BH assumes positive dependence — satisfied here (configs are positively
correlated). For familywise control (no false keeps at all), Romano–Wolf stepdown (bootstrap-
based, respects correlation) is the institutional choice. Harvey–Liu–Zhu's finance-specific
recommendation: demand **t ≥ 3.0**, not 2.0, for any strategy discovered by search — note
SAM-Best's 2.51 (gross; less net of financing) sits below that bar.

### 11.7 Institutional practice / applied to SAM-Best
Funds treat significance as a *hurdle stack*: HAC t on the paired spread ≥ 2–3, SPA p < 0.05
over the full searched universe, DSR > 0.95 (§12.2) — any single test passing is not enough.
Applied here, in order of information value: (1) paired alpha test vs 0.58× B&H — hours of
work, decisive either way; (2) SPA over the archived 90 configs with both benchmarks (flat and
0.58× B&H); (3) BH-FDR across the family for the claim "the whole contrarian family works";
(4) re-run all of it on net-of-financing returns. Prediction to falsify: gross paired alpha t
≈ 1.5–2.2 (suggestive, sub-threshold), net ≈ 1.0–1.7 — if it comes in higher, the strategy is
better than this report assumes; if lower, the edge is beta plus luck.

**Verdict: 5/10 — the one test run (raw t) was run honestly but answers the wrong question.**

---

## 12. Overfitting Detection

### 12.1 Probability of Backtest Overfitting (PBO)
**What**: Bailey–Borwein–López de Prado–Zhu (2014). Using CPCV (§4.2): for each of the C(N,k)
train/test splits, rank all configs on train, find the train-best config's **rank on test**,
map to a logit λ = ln(r̄/(1−r̄)) where r̄ is its relative test rank. **PBO = fraction of
splits where the train-best performs below the test median** (λ < 0).

**Interpretation**: PBO ≈ 0.5 → in-sample selection is a coin flip out-of-sample (pure
overfit); PBO < 0.1–0.2 → selection carries real signal. Also extract the **performance
degradation regression** (test SR vs train SR across splits): slope < 0 with high PBO is the
classic signature of a strategy factory fitting noise.

**Applied**: run PBO on the 90-config grid (N = 12 groups, k = 2 → 66 splits). The study's own
walk-forward already hints at the answer: refit-best collapsing OOS (WFE 0.16) *is* high-PBO
behavior for single-W selection, while the family's homogeneity (corr ≈ 1) suggests family-
level PBO will be low. Get the number.

### 12.2 Deflated Sharpe Ratio (DSR)
**What**: Bailey & López de Prado (2014). Two ingredients:
(a) the **Probabilistic Sharpe Ratio** — P(true SR > SR*) given fat tails and sample length:

```
PSR(SR*) = Φ( ( (ŜR − SR*) · √(T−1) ) / √( 1 − γ₃·ŜR + ((γ₄−1)/4)·ŜR² ) )
```

(ŜR in per-period units, γ₃ skew, γ₄ kurtosis — negative skew and excess kurtosis, both
expected for this strategy, *widen* the denominator and cut significance); and
(b) the deflation benchmark **SR\*** = the Sharpe you'd expect from the *best of N* null
trials:

```
SR* = √V[SR across trials] · ( (1−γₑ)·Φ⁻¹(1 − 1/N) + γₑ·Φ⁻¹(1 − 1/(N·e)) ),  γₑ ≈ 0.5772
```

**DSR = PSR(SR\*)**; demand ≥ 0.95. N is the number of *effectively independent* trials —
estimate via the study's own cluster analysis (with within-family correlations ≈ 1.00, the 90
configs collapse to perhaps N_eff ≈ 5–10 clusters: contrarian family, W=1, momentum family,
sizing variants, side variants).

**Applied — worked orientation**: ŜR_daily = 0.83/√252 ≈ 0.052; T = 2,278. If the cross-trial
SR dispersion (annualized) is ~0.5 (plausible given momentum configs are strongly negative)
and N_eff = 8: SR\*_ann ≈ 0.5 × [(0.4228)(1.24) + (0.5772)(1.86)] ≈ 0.80 — **essentially equal
to the observed 0.83**, i.e., DSR ≈ 0.5, coin-flip. If instead you argue N_eff = 3 (contrarian
family / momentum / W=1) and dispersion 0.3, SR\* ≈ 0.25 and DSR is comfortable. The verdict
hinges on honest trial accounting — which is precisely why institutions log every trial
(§12.5). Mitigating factor, and it is real: the deployed config is near the family **median**,
not the max — DSR's max-of-N penalty partially overstates the selection here. Compute it both
ways and report both.

### 12.3 Reality Check
§11.5 — same machinery, selection-aware p-value; listed here because RC/SPA and DSR/PBO are
complements: RC/SPA test the *best pick against a benchmark*; PBO tests the *selection
process*; DSR corrects the *headline statistic*. Institutional-grade validation reports all
three.

### 12.4 Minimum Backtest Length (MinBTL) — the flagship calculation
**What**: Bailey et al. — the shortest backtest for which the best of N null trials would
*not* be expected to reach your observed Sharpe:

```
MinBTL (years) ≈ [ (1−γₑ)·Φ⁻¹(1−1/N) + γₑ·Φ⁻¹(1−1/(N·e)) ]² / SR²_annual
```

For N = 90: Φ⁻¹(1−1/90) ≈ 2.29, Φ⁻¹(1−1/245) ≈ 2.64 → E[max Z] ≈ 0.423·2.29 + 0.577·2.64 ≈
2.49. With SR = 0.83: MinBTL ≈ (2.49/0.83)² ≈ **9.0 years — the sample is 9.04 years.** The
backtest sits *exactly at* the minimum defensible length for its own trial count, with zero
margin: had the same search been run on 7 years, a 0.83 Sharpe would be indistinguishable from
the best of 90 coin-flippers. At the net-of-financing Sharpe (~0.6), MinBTL ≈ 17 years — the
sample is **too short** for the net edge to clear its own search. This is Gap 2's arithmetic
and the single most important number a skeptic should quote back at this strategy.

### 12.5 Multiple hypothesis testing & data snooping bias — the bookkeeping
Everything you *ever* evaluated on this data counts: the 90 configs, sizing variants, the
martingale you rejected, and — uncomfortably — the other strategies in this repository
tried on correlated instruments, and every idea abandoned before this one. Snooping compounds
at the researcher level and the *community* level (semivariance signals are published;
published anomalies arrive pre-snooped — the SSRN paper's own in-sample is part of the trial
count in a strict reading). Defenses: a **research registry** (append-only log of every
config-dataset evaluation; institutions automate it in the backtest runner), pre-registration
of new tests, economic priors (a signal with a risk-premium story needs less statistical
evidence than a data-mined pattern — semivariance asymmetry has genuine literature behind it,
which is worth perhaps a one-notch downgrade of skepticism, not a pass).

### 12.6 Institutional practice / applied verdict
Serious shops gate deployment on DSR/PBO-style analyses (post-2015, López de Prado's program
is the lingua franca), enforce trial logging in the research platform, and discount any
strategy whose backtest length is near its MinBTL. SAM-Best: the raw material (90 archived
config return series) makes all of §12 a few days' work; until then the honest summary is —
**gross edge at the edge of defensibility, net edge below it, rescued only if the paired alpha
(§11.3) and cross-market replication (§5.3) come in positive.**

**Verdict: 5/10 — cluster analysis shows awareness; none of the four formal tests computed.**

---

## 13. Risk Metrics

### 13.1 What they measure / why they matter
Different projections of the same return stream onto "what can hurt me." No single number
suffices: Sharpe hides tails, Calmar hides frequency, win rate hides magnitude. Institutions
read them as a **panel** and interrogate disagreements between them.

### 13.2 The panel, with equations and reading guidance

| Metric | Definition | Good (daily index strategy, net) | What disagreement means |
|---|---|---|---|
| **Sharpe** | (R̄ − rf)/σ · √252 | ≥ 0.7 live-credible; ≥ 1 strong | High SR + ugly DD → serial correlation of losses |
| **Sortino** | (R̄ − target)/σ_downside · √252 | ≥ 1.0 | Sortino ≫ Sharpe → upside vol dominates (good skew) |
| **Calmar / MAR** | CAGR / maxDD (Calmar: 3y window; MAR: full history) | ≥ 0.5 acceptable, ≥ 1 strong | Low Calmar at high SR → one deep episode (regime risk, §6) |
| **Omega(θ)** | ∫ P(R>r)dr above θ ÷ below θ = E[(R−θ)⁺]/E[(θ−R)⁺] | > 1.2 at θ=0 daily | Full-distribution gain/loss ratio; robust to non-normality |
| **Ulcer Index** | √(mean(DD²ₜ)) | Compare vs benchmark's | Penalizes *time spent* down, not just depth |
| **Martin (UPI)** | (CAGR − rf)/UI | > benchmark's | Sharpe with drawdown-experience denominator |
| **Recovery factor** | Net profit / maxDD | ≥ 3 over ~9y | < 2 → one drawdown ate years of edge |
| **MaxDD / AvgDD / TUW** | Depth; mean depth; time under water | TUW longest spell < ~18 months | Long TUW kills discipline before math does |
| **Skew γ₃** | E[(R−μ)³]/σ³ | Know its sign; contrarian-long ⇒ expect < 0 | Negative skew + leverage = ruin chemistry |
| **Kurtosis γ₄** | E[(R−μ)⁴]/σ⁴ | Report excess; index dailies ≈ 4–10 | Feeds PSR denominator (§12.2) |
| **Tail ratio** | |q₉₅| / |q₅| of daily returns | ≥ 0.9 | ≪ 1: quiet gains, violent losses |
| **Gain-to-Pain** | Σ monthly gains / |Σ monthly losses| | ≥ 1.5 | Schwager's practitioners' Omega |

`quantstats.reports.full(returns)` produces the entire panel plus rolling charts in one call;
`empyrical-reloaded` gives the individual functions.

### 13.3 Statistical interpretation / warning signs
Every one of these is a point estimate — attach block-bootstrap CIs (§10) or report none of
them to outsiders. Overfitting signature in metric space: a strategy *selected on* Sharpe will
show optimistic Sharpe relative to its unselected siblings but unremarkable Omega/UI — metric
disagreement across the family is a selection fingerprint. Also beware denominators: maxDD-
based ratios (Calmar/MAR/Recovery) have enormous sampling variance (§2.2) — never rank
strategies by them on a single path.

### 13.4 Applied to SAM-Best
Reported: SR 0.83, CAGR 15.1 %, maxDD −24.9 % → MAR ≈ 0.61, decent gross. Not reported and
required: Sortino, skew/kurt (PSR needs them; expect γ₃ < 0 — it holds long through panics),
tail ratio, TUW (the 2022 episode likely produced a 12–20-month underwater spell — confirm;
that is the number that tests *your* discipline), Ulcer/Martin vs the 0.58× benchmark, and the
whole panel again **net of financing** (§7.2), where MAR falls to ≈ 0.45. The exposure-
adjusted lens flatters it: per unit of average exposure (0.58×), gross return-on-exposure ≈
26 %/yr against the index's ~18 % — that ratio surviving net costs is what "timing skill"
would look like in this panel.

**Verdict: 7/10 — headline metrics fine and internally consistent; tail metrics unreported.**

---

## 14. Trade Distribution Analysis

### 14.1 What it measures / why it matters
The microstructure of the edge: is it many small wins, a few huge ones, luck concentrated in
one week of 2020? Expectancy math also feeds sizing and the psychological contract — you need
to know the losing-streak distribution *before* living through it, or you will abandon a
working system at its statistically ordinary worst.

### 14.2 A necessary reframing for this strategy
SAM-Best is a **graded-exposure daily system**, not a discrete-trade system: the ensemble
drips in and out in 1/29 steps, so "trades" produced by the backtester (Add/Trim fills) are
accounting artifacts. Analyze at two levels:
1. **Daily-return level** — treat each exposed day as the unit; all §13 machinery applies.
2. **Episode level** — define an episode as a maximal contiguous spell with exposure > 0;
   compute PnL, duration, max adverse excursion (MAE) / max favorable excursion (MFE) per
   episode. Episodes are the closest thing to independent bets and the honest n for trade
   statistics (expect n ≈ 100–250 over 9 years — verify).

### 14.3 The metric battery (per episode)

- **Win rate** p and **payoff ratio** R̄w/|R̄l|; **profit factor** PF = gross wins / gross
  losses (healthy: ≥ 1.4 at this n; suspicious: ≥ 2.5 — usually a data or lookahead problem at
  daily frequency); **expectancy** E = p·R̄w − (1−p)·|R̄l| with bootstrap CI (§10.3).
- **Largest winner/loser** and **PnL concentration**: sort episodes by PnL; report the share
  of total from the top 5. **Knock-out test**: delete the top 3–5 episodes; a robust system
  stays clearly profitable. For a contrarian dip-buyer, expect concentration in the
  COVID-rebound and 2022-rally episodes — if the strategy is only those five bets, the "daily
  edge" narrative dies and it becomes a crisis-alpha bet (tradable! but sized and marketed
  differently).
- **Streaks**: longest consecutive win/loss runs vs the MC-expected distribution for the
  measured (p, n) — e.g. at p ≈ 0.5, n = 200 episodes, a 7–8 loss streak is *expected*;
  budget margin and morale for the 95th-percentile streak, not the historical one.
- **Duration & spacing**: episode length distribution and gaps between episodes; drift in
  either across the sample is regime information (§15).
- **Distribution of returns**: histogram + QQ plot of episode PnL; a contrarian long should
  show right skew at the episode level (many small scratches, occasional large rebound
  captures) even while daily returns skew left — confirming that signature confirms the
  mechanism.

### 14.4 Warning signs / stats / institutional practice / applied
Warnings: PF driven by one episode; win rate ≫ 60 % with payoff < 0.7 (picking pennies before
steamrollers — check MAE); episode count too low for any inference (< 30). Statistically,
episode-level inference dodges the daily autocorrelation problem and is where Wilcoxon (§11.4)
earns its keep. Institutions run exactly this as "PnL forensics" — attribution by trade,
concentration limits, and the knock-out test are standard due-diligence questions from every
allocator. For SAM-Best: publish the episode table; the knock-out test result is the second
number (after MinBTL) a skeptic will demand.

**Verdict: unreported — 4/10 provisional pending the episode-level rebuild.**

---

## 15. Stability Analysis

### 15.1 What / why
Whether the edge is a property of the whole sample or of a lucky sub-era. Allocators read
stability tables before Sharpe: a 0.7 that shows up every year beats a 1.0 that is one great
year plus noise, because only the former compounds trust (and only trust survives drawdowns).

### 15.2 The battery
- **Monthly return heat table** (years × months, `quantstats.plots.monthly_heatmap`): eyeball
  clustering; then quantify — % positive months (good: ≥ 55–60 %), best/worst month.
- **Annual consistency**: per-calendar-year return, Sharpe, maxDD. Pass: ≥ 6–7 of 9 years
  positive; no year contributing > 40 % of cumulative PnL; worst year explicable by regime
  (§6), not mystery.
- **Rolling 252-day Sharpe / CAGR / drawdown / expectancy / win rate**: the five ribbons.
  Read for (a) sign stability of rolling Sharpe (share of windows > 0 — good: ≥ 80 %), (b)
  trend — regress rolling Sharpe on time; a significantly negative slope is measured **alpha
  decay** (crowding, structural change) and forecasts the forward test failing.
- **CUSUM / structural-break tests** on cumulative demeaned returns (`ruptures`,
  `statsmodels`): objective detection of "the strategy changed" — institutions wire the same
  statistic to live monitoring, so building it now does double duty (§18 stage 15).

### 15.3 Warning signs / interpretation / applied
Warnings: all of 2016–2019 flat and all PnL post-2020 (the signal may be a COVID-era artifact);
rolling Sharpe oscillating with the *index's* rolling Sharpe at high correlation (you built
expensive beta); rolling expectancy declining while rolling win rate holds (payoff compression
— often the first symptom of crowding). Statistically, rolling windows are massively
overlapping — do not t-test them against each other; use them descriptively and test breaks
with CUSUM. Applied to SAM-Best: with avg exposure 0.58× and a bull-heavy sample, the null
hypothesis to attack is "rolling PnL ≈ 0.58 × index rolling PnL + noise"; the years that can
refute it are 2018 and 2022 (bears where the claimed 11-point drawdown advantage must have
been earned) — publish those two years' slices with the benchmark overlay.

**Verdict: unreported — 5/10 provisional; the WFO fold results imply *some* window-level
stability but the per-year table must be shown.**

---

# Part III — Scoring, Standards, Pipeline

## 16. Strategy Robustness Score (0–100)

### 16.1 The framework
Ten components, ten points each. Score each from the rubric; **deployment gates use the
minimum rule as well as the sum** (a 90 total with a 2 in execution robustness is not
deployable — weakest-link logic, because failure modes don't average).

| # | Component | 10 points | 6 points | 2 points |
|---|---|---|---|---|
| 1 | Walk-forward quality | WFE ≥ 0.7, stitched OOS SR t ≥ 2, ≥ 70 % folds positive, meta-params swept | WFE 0.5–0.7, OOS SR > 0, most folds positive | WFE < 0.3 or OOS ≤ 0 |
| 2 | Parameter stability | All params on plateaus, ensemble/centroid deployed, estimator-frequency swept | Main param plateaus; others unswept | Spike optimum or edge-of-grid |
| 3 | Statistical significance | Paired-alpha HAC t ≥ 3 net, SPA p < 0.05 | Paired t ≈ 2, SPA not run | Only raw t vs zero |
| 4 | Drawdown robustness | Block-bootstrap P(DD > 1.5×hist) known & sized for; P(50 %) < 1 % | IID-MC only | Single-path DD quoted |
| 5 | Out-of-sample | Untouched lockbox passed AND ≥ 6 mo forward positive | Stitched WFO-OOS only | All data consumed by selection |
| 6 | Regime robustness | Positive/flat in every regime slice incl. cross-market bears | Survived in-sample bears; slow-bear untested | Single-regime PnL |
| 7 | Execution robustness | Full cost stack modeled; breakeven ≥ 3× costs; delay-insensitive | Commissions only; sweeps pending | Edge < 2× realistic costs |
| 8 | Overfitting probability | PBO < 0.1, DSR ≥ 0.95, T ≫ MinBTL, trial registry | Informal (clustering, plateau) evidence only | No trial accounting |
| 9 | Risk-adjusted returns (net) | Net SR ≥ 1, MAR ≥ 0.8, tails reported | Net SR 0.5–0.8 | Net SR < 0.3 or unknown |
| 10 | Consistency | ≥ 80 % rolling-yr SR > 0; no yr > 40 % PnL; no decay trend | Partial/implied | Concentrated or decaying |

**Grade bands**: ≥ 80 and no component < 5 → deployable at starter size · 65–79 → paper trade
· 50–64 → keep researching · < 50 → archive it. (Bands assume *net* returns; a gross-only
scorecard is invalid.)

### 16.2 SAM-Best scorecard (on the study's claims, this report's analysis)

| Component | Score | One-line justification |
|---|---|---|
| Walk-forward | 8 | Real WFO, honest negative result on refit; meta-choice not walked forward (§1.11) |
| Parameter stability | 9 | 30/30 positive, plateau, ensemble deployed; non-W sweeps missing (§3.9) |
| Significance | 5 | Raw t = 2.51 only; paired alpha & SPA absent (§11) |
| Drawdown robustness | 6 | Big MC program, but resampler unstated/likely IID (§2.10) |
| Out-of-sample | 3 | No lockbox left; WFO-stitched OOS is all there is (§5.7) |
| Regime robustness | 5 | Three fast bears survived in-sample; slow bear & cross-market untested (§6.5) |
| Execution robustness | 4 | Financing unmodeled ≈ 3.8 %/yr; no delay/slippage sweeps (§7) |
| Overfitting probability | 5 | Clustering + plateau are real informal evidence; PBO/DSR/MinBTL all uncomputed, and MinBTL is borderline (§12) |
| Risk-adjusted (net) | 7 | Gross panel solid; net ≈ SR 0.6 / MAR 0.45 — acceptable, not strong (§13.4) |
| Consistency | 6 | WFO folds imply stability; per-year table unpublished (§15.3) |
| **Total** | **58/100** | **"Keep researching / begin paper trading" band — not deployable** |

The remediation list in §I.4 is worth roughly +15–20 points if the results land favorably
(paired alpha ≥ 2 net alone moves component 3 from 5→8 and component 9's credibility with it).

## 17. Institutional Research Standards — where this process stands

| Institutional standard | Typical requirement at a quant fund / prop desk | SAM-Best status |
|---|---|---|
| Hypothesis before data | Written economic rationale pre-registered | Partially — literature-backed signal (SSRN 2815151), but strategy form evolved by search |
| Point-in-time, survivorship-clean data | Vendor-audited, multiple feeds reconciled | Single CFD feed; no cross-feed check |
| Trial registry | Every backtest logged automatically; N known exactly | Absent; N ≈ 90+ reconstructed from comments |
| Code review & replication | Second researcher reimplements independently (different language/stack) before capital | Absent — single author, single codebase (the Pine port is a *partial* second implementation; §Appendix A found it faithful) |
| Cost model sign-off | TCA desk owns assumptions; backtest uses their curves | Self-assumed 2 bps; financing omitted |
| Multiple-testing gates | DSR/PBO/SPA reported by the platform by default | Not computed |
| Risk committee & kill criteria | Pre-committed DD limits from simulated quantiles; independent risk veto | Informal (1× cap chosen well, but no written kill rule) |
| Capacity analysis | Max AUM before edge self-erodes | Irrelevant at retail size on NAS100 — genuinely fine to skip |
| Forward test before size | 3–12 months paper/incubation, shortfall tracked | Not started |
| Post-deploy monitoring | Live-vs-backtest drift alarms (CUSUM), monthly attribution | Not designed |

Honest summary: this process is **top-decile for independent work** — the parameter-ensemble
decision, the rejection of the martingale on MC evidence, and the honest walk-forward negative
are things many professional shops get wrong — but it is missing the three pillars
institutions consider non-negotiable: *selection-aware statistics, a complete cost model, and
data that selection never touched.*

## 18. The Validation Pipeline — idea to live capital

```
 idea → data → features → IS fit → WFO → CV/CPCV → MC/bootstrap → sensitivity
  → significance (paired, SPA, DSR/PBO) → regimes → execution stress
  → LOCKBOX (once) → paper trade → small live → scale
                 ── kill at any gate; killed ideas go in the registry too ──
```

1. **Hypothesis creation** — write the economic mechanism, the sign prediction, and the
   falsifier *before* touching data. (SAM-Best's: post-bad-vol risk-premium/overreaction
   payoff in equity indices. Falsifier: no alpha vs exposure-matched B&H.)
2. **Data cleaning** — sessions, stubs, DST, bad ticks; reconcile ≥ 2 feeds; lock a lockbox
   NOW (final 12–18 months) before anyone looks at it.
3. **Feature engineering** — build RS±/SAM variants; check features for leakage (nothing in
   day *d*'s feature may use day *d*'s close-to-future data).
4. **In-sample optimization** — explore freely on train only; log every trial.
5. **Walk-forward optimization** — §1; sweep WFO meta-parameters.
6. **Cross-validation** — purged/CPCV; nested if tuning; §4.
7. **Monte Carlo testing** — signal-preserved + return-level, block resampling; §2.
8. **Bootstrap testing** — CIs on every reported metric; §10.
9. **Parameter sensitivity** — full-grid plateaus, estimator-frequency sweep; §3.
10. **Statistical significance** — paired alpha (HAC), SPA over the trial universe, FDR
    across kept variants; §11.
11. **Regime testing** — slices + cross-market pseudo-OOS + worst-case regime replay; §6.
12. **Execution stress** — full cost stack, delays, missed fills, gap/liquidity scenarios;
    §7–8. Recompute steps 5–11 *net*.
13. **Final untouched OOS** — open the lockbox, run once, decision is binding; §5.2.
14. **Paper trading** — ≥ 3–12 months against the pre-registered protocol (§5.4); track
    implementation shortfall fill-by-fill.
15. **Small live deployment** — 10–25 % of target size; live data answers what paper can't
    (fills, financing, your own behavior).
16. **Scaling rules** — pre-committed: e.g., double allocation after each clean quarter
    (positive net alpha, DD within simulated 80th percentile); halve on DD beyond the
    simulated 95th percentile; full stop beyond 97.5th or on CUSUM break (§15.2) — then
    *post-mortem before restart*, never resize on discretion mid-drawdown.

**SAM-Best's position on this pipeline**: steps 1–5 done (4–5 done well), 9 half-done; steps
6–8 and 10–12 pending with data already in hand; step 13 impossible (lockbox spent — Gap 1);
therefore steps 14–16 carry the burden. Realistic calendar: ~2–4 weeks of computation and
analysis, then 6–12 months of forward test before first live dollar.

---

# Part IV — Tooling, Checklist, Appendices

## 19. Python Libraries — the working stack

| Task | Library | Notes & caveats |
|---|---|---|
| Core wrangling | **pandas / numpy** | Everything else sits on these; use `pd.DataFrame` daily returns as the universal interchange format |
| Statistics | **scipy.stats** | t, Wilcoxon, Mann-Whitney, KS, skew/kurt |
| Econometrics | **statsmodels** | HAC/Newey–West (`cov_type="HAC"`), OLS alpha tests, diagnostics |
| Bootstrap | **arch** | `StationaryBootstrap`, `MovingBlockBootstrap`, `CircularBlockBootstrap`, `optimal_block_length`; also GARCH for parametric MC (§2.3) |
| Backtesting (vectorized, fast sweeps) | **vectorbt** | Ideal for the 90-config × MC grids; steep API; the free version suffices (Pro exists) |
| Backtesting (event-driven, readable) | **backtesting.py** | Clean for single-strategy work; limited multi-asset |
| Backtesting (event-driven, featureful) | **Backtrader** | Mature but effectively unmaintained; fine for validation replication |
| Backtesting (portfolio, PIT-data) | **zipline-reloaded** | Community fork of Quantopian's engine; heavier setup |
| Execution-grade simulation | **nautilus_trader** | Tick-level, latency & fill models — for §7 realism if you go deep |
| Metrics/tearsheets | **quantstats** | `reports.html(returns, benchmark)` = instant §13/§15 panel |
| Metrics (functions) | **empyrical-reloaded / pyfolio-reloaded** | Use the `-reloaded` forks; originals are abandoned |
| ML & CV scaffolding | **scikit-learn** | `TimeSeriesSplit`; roll your own purge/embargo/CPCV (§4.4 — 25 lines) |
| López de Prado toolset | **mlfinlab** | PurgedKFold, CPCV, DSR/PBO — **licensing caveat**: went proprietary (Hudson & Thames); pin an old open release or reimplement from the book |
| Volatility/regime | **arch** (GARCH), **hmmlearn** (HMM regimes), **ruptures** (structural breaks/CUSUM, §15.2) | |
| Hyperparameter search | **optuna** | Powerful — and therefore an overfitting accelerant; every trial it runs goes in the registry (§12.5), N includes all of them |
| Plotting | **matplotlib / seaborn / plotly** | Heatmaps (§3), fold ribbons (§15) |

Suggested build order for the SAM-Best remediation: pandas + a small NumPy backtester
(replicate the Pine logic exactly, ~100 lines — this doubles as the independent
reimplementation from §17) → arch bootstrap suite → the §4.4 CPCV snippet → statsmodels
paired-alpha → quantstats tearsheets → vectorbt only if the config grid grows.

## 20. Final Pre-Capital Checklist

### Required (all must pass — any failure blocks live capital)
- [ ] Independent reimplementation (non-Pine) reproduces the backtest within tolerance
- [ ] Full cost model: commissions + spread + **overnight financing** (or futures data); all headline stats restated **net**
- [ ] Paired alpha vs exposure-matched buy-and-hold, HAC t ≥ 2 (net)
- [ ] Block-bootstrap (not IID) Monte Carlo: P(SR ≤ 0) < 5 %, maxDD 95th percentile known and capital-planned
- [ ] Walk-forward: WFE ≥ 0.5 and stitched OOS SR > 0 (already claimed — reproduce net)
- [ ] Parameter plateaus on **all** parameters incl. estimator frequency (5m/15m/30m/65m)
- [ ] Execution delay test: edge survives +1 bar and next-day execution
- [ ] Gap stress: worst conditional overnight gap at ≥ 0.8 exposure survivable with margin buffer; broker stop-out mechanics modeled
- [ ] Pre-registered forward-test protocol committed to this repo (period, pass/kill criteria, sizes) **before** the test starts
- [ ] Written kill criteria (DD quantile + CUSUM break) and scaling schedule (§18.16)

### Strongly recommended
- [ ] SPA (Hansen) over the archived 90-config universe, both benchmarks
- [ ] PBO via CPCV < 0.2; DSR ≥ 0.90 under conservative trial counting
- [ ] Cross-market replication (SPX, RTY, DAX, Nikkei) with frozen rules — directionally positive in ≥ 3
- [ ] Cross-feed replication (second NAS100 source + NQ futures): position correlation ≥ 0.9
- [ ] Regime table (8 slices, §6.2) + slow-bear replay (2000–02 proxy)
- [ ] Episode-level trade forensics + top-5 knock-out test (§14.3)
- [ ] Per-year consistency table; rolling-Sharpe decay regression (§15)
- [ ] Cost breakeven ≥ 3× realistic total costs
- [ ] 6–12 months paper trading with fill-level shortfall tracking

### Optional
- [ ] Noise battery (§9): perturbation, bad-tick injection, missing candles — flip rate < 5 %
- [ ] rebalPct / minBars sweeps; execution time-of-day sweep
- [ ] Sortino/Omega/Ulcer/tail panel with bootstrap CIs (§13)
- [ ] HMM-based regime attribution; strategy-vs-thesis behavioral audit (§6.3)
- [ ] quantstats HTML tearsheet committed alongside this report

### Advanced quantitative tests
- [ ] Signal-preserved MC: block-bootstrap the 30m underlying, re-run signal→position→PnL (§2.3)
- [ ] Romano–Wolf stepdown across the kept family; Harvey-Liu t ≥ 3 hurdle check
- [ ] GARCH-filtered parametric MC (fit GARCH-t, simulate, re-run strategy) as a third resampling scheme
- [ ] MinBTL restated at net Sharpe; if T < MinBTL, extend history (cash NDX + RV proxy) until it isn't
- [ ] Capacity/impact model (only if size ever exceeds a few NQ contracts)
- [ ] CUSUM live-monitoring harness wired before the first live order

---

## Appendix A — Implementation audit of `SemivarianceContrarian.pine`

A validation report should audit the artifact, not just the claims. Findings on the script as
committed in this repo:

**Correctness (look-ahead / leakage):**
- Signal uses only *completed* days: history is pushed on the first bar of the next day, and
  the position decision uses that history — no same-day leakage. ✔
- First-bar return is `log(close/open)`, so the overnight gap never enters RS± — matches the
  stated estimator. Note the gap still (correctly) affects P&L. ✔
- `process_orders_on_close=true` with orders placed on the first bar of the day → backtest
  fills at that bar's close using information available at decision time. ✔ Live alerts will
  fill *after* that close — the +1-bar delay test (§7.3.3) bounds the difference.

**Behavioral notes (not bugs, but validation-relevant):**
1. **Stub-day handling**: days with `< minBars` bars are silently dropped, so a "W-day" SAM
   can span more calendar time around holidays. Consistent with the study by design — but it
   makes results sensitive to the feed's session/holiday conventions (§9.2.6).
2. **`time("D")` day boundary** follows the chart symbol's session timezone; two brokers'
   NAS100 feeds can split "days" differently (17:00 ET vs 00:00 UTC), changing RS± materially.
   Cross-feed replication is therefore not optional hygiene, it is a core robustness test.
3. **Equity-based rebalancing**: `fullQty` is recomputed daily from `strategy.equity`, so even
   a constant vote produces drift-rebalancing trades once the 10 % threshold is crossed —
   include this churn in the cost sweeps (§7.3.1).
4. **Warmup**: trading starts only after `histCap = max(wMax, wSingle)` complete days; in
   ensemble mode a large `wSingle` needlessly extends warmup. Cosmetic.
5. **Split-entry mode** adds at most one tranche per day while underwater (max 3) — this is a
   bounded averaging-down, not the removed martingale; its risk claims come from the study's
   sizing sweep and should be re-verified under block-bootstrap MC like everything else.
6. **`margin_long=10`** enables broker leverage far above the 1× the strategy intends;
   nothing in the script prevents `fullPct=200`. Consider hard-capping `fullPct` at 100 in
   code, since the study's own MC rejected 2×.

**v2 addendum.** `SemivarianceContrarianV2.pine` implements every code-level item above while
keeping v1's trading decisions as the default: hard 1× cap (item 6), warmup fix (item 4), an
optional vote-change rebalance trigger (item 3), a display-only overnight-financing model with
net-of-equity reporting (Gap 4 / §7.2), an execution-delay input for the §7.3.3 robustness
test, an optional pre-committed drawdown halt (§18.16), optional ±Nσ winsorization of 30m
returns (§9.3), and order alert messages for live automation. The behavior-changing options
(winsorization, vote-mode rebalancing, delay > 0) ship **off** by default because each creates
a new strategy that must re-enter the pipeline at §18 step 4; v1 remains the frozen artifact
matching the study.

## Appendix B — Equation quick reference

```
Realized semivariance:  RS±_d = Σ_i r²_{d,i}·1{r_{d,i} ≷ 0}
Signal:                 SAM_W(d) = Σ_{k=d−W+1..d} (RS⁺_k − RS⁻_k);  long iff SAM < 0
Ensemble position:      frac(d) = |{W ∈ [2,30]: SAM_W(d) < 0}| / 29

Sharpe SE (Lo 2002):    SE(SR_ann) ≈ √((1 + SR²/2)/years)
t-stat:                 t = SR_ann · √years
PSR:                    Φ( (ŜR−SR*)√(T−1) / √(1 − γ₃ŜR + ((γ₄−1)/4)ŜR²) )
E[max of N null SRs]:   SR* = √V[SR]·((1−γₑ)Φ⁻¹(1−1/N) + γₑΦ⁻¹(1−1/(Ne))), γₑ≈0.5772
DSR:                    PSR evaluated at SR*
MinBTL (years):         (E[max Z_N])² / SR²_ann        → N=90, SR=0.83 ⇒ ≈ 9.0 y
PBO:                    P(train-best config ranks below test median) across CPCV splits
WFE:                    stitched OOS metric / mean IS metric of chosen configs
Ruin (diffusion):       P(equity ever ≤ (1−D)·E₀) = (1−D)^(2ν/σ²), ν = μ − σ²/2
Omega(θ):               E[(R−θ)⁺] / E[(θ−R)⁺]
Ulcer Index:            √(mean over t of DD_t²);  Martin = (CAGR − rf)/UI
```

## Appendix C — Executed walk-forward, replication and paired-alpha test (2026-07-05)

The owner supplied the underlying 30-minute NAS100 feed (103,693 bars, 2016-11-15 →
2025-10-01, 2,283 sessions — matching the study's claimed sample). The harness in
`backtests/walkforward/walkforward_sam.py` independently reimplements the Pine logic
(gap-excluded 30m semivariance, first-bar-close fills, 10 % rebalance step, 2 bps/side) and
executes the §1 program. Full tables: `backtests/walkforward/RESULTS.md`; equity chart:
`backtests/walkforward/wf_equity.png`. The raw data file is deliberately **not** committed
(broker feed, public repo). Findings:

1. **Replication passes (§17 requirement satisfied).** Full-sample ensemble: Sharpe 0.86 vs
   claimed 0.83, CAGR 14.0 % vs 15.1 %, maxDD −24.6 % vs −24.9 %, t 2.58 vs 2.51, exposure
   0.58× vs 0.58×; W=8: 0.97 vs 1.02. The study's "buy & hold 0.73" matches the OOS-days
   benchmark (0.72 here), not full-sample B&H (0.90 on this feed).
2. **Walk-forward direction confirmed.** Rolling 756/126, 11 folds: refit-best-single-W
   collapses to stitched OOS Sharpe 0.34 / WFE 0.29 (study: 0.19/0.16); the fixed ensemble
   holds at OOS 0.73 / WFE 0.83, 91 % of folds positive, with maxDD −24.6 % vs B&H's −35.7 %
   on identical days (the claimed "11 pts less drawdown" reproduces exactly). Anchored
   variant agrees (A: 0.58/0.48; B: 0.73/0.70). Meta-selection (§1.11) never picks the
   ensemble in-sample — the best single W always looks better in-sample and then
   underperforms OOS: the selection trap, demonstrated live.
3. **The paired alpha test (Gap 3) fails to reject luck.** Gross spread vs 0.58×-exposure
   buy & hold: +2.5 %/yr, Newey–West t = **0.95**. Net of 6.5 % CFD financing: **−1.2 %/yr,
   t = −0.47**. On a CFD, the timing edge is fully consumed by financing; on futures/cash
   (financing ≈ 0 to embedded), the alpha is positive but statistically indistinguishable
   from zero at this sample length.
4. **Delay robustness passes (§7.3.3):** +1-bar-delayed fills leave the ensemble unchanged
   (Sharpe 0.87 vs 0.86) — live alert latency is not a threat.
5. **Scorecard update (§16.2):** component 1 stays 8 (now independently verified); component
   3 drops 5→4 (the decisive significance test came back inconclusive-to-negative);
   component 5 rises 3→4 (stitched OOS verified by second implementation); component 7
   rises 4→5 (delay test passed, financing quantified). **Total: 58 → 59/100** — the score
   barely moves; what moved is certainty. The honest product description is now sharper:
   *SAM-Best delivers index-like risk-adjusted returns at 0.58× average exposure with
   roughly one-third less drawdown — a defensive exposure-grading overlay. Its claim to
   genuine timing alpha is unproven (t ≈ 1 gross, negative net on CFDs), so it must be
   implemented on futures or cash instruments, and sized as a beta substitute, not an
   alpha engine.*

## References

- Baruník, Kočenda & Vácha — semivariance/asymmetric volatility work, SSRN 2815151 (the
  signal's source, as cited by the strategy).
- Barndorff-Nielsen, Kinnebrock & Shephard (2010) — realized semivariance.
- Bailey, Borwein, López de Prado & Zhu (2014) — *Pseudo-Mathematics and Financial
  Charlatanism*; PBO, MinBTL.
- Bailey & López de Prado (2014) — *The Deflated Sharpe Ratio*.
- López de Prado (2018) — *Advances in Financial Machine Learning* (purged CV, CPCV, DSR).
- White (2000) — *A Reality Check for Data Snooping*; Hansen (2005) — *A Test for Superior
  Predictive Ability*.
- Lo (2002) — *The Statistics of Sharpe Ratios*.
- Politis & Romano (1994) — stationary bootstrap; Politis & White (2004) — block length.
- Harvey, Liu & Zhu (2016) — *…and the Cross-Section of Expected Returns* (t ≥ 3 hurdle).
- McLean & Pontiff (2016) — post-publication anomaly decay.
- Pardo (2008) — *The Evaluation and Optimization of Trading Strategies* (walk-forward
  canon); Aronson (2006) — *Evidence-Based Technical Analysis*.

---

*Report generated for the SAM-Best strategy as committed at `SemivarianceContrarian.pine`.
All study statistics are claims from the strategy's embedded documentation; scores marked
"provisional" become firm only when the underlying tests are run and archived in this
repository.*
