# STUDY: the Donchian breakout on XAUUSD, built as a two-layer mechanism-first strategy

**What this is.** The best-performing Donchian family on this branch, applied to gold under the
mechanism-first architecture: a primary that emits events from a named market mechanism, a meta
layer that only ever *scores* those events, features confined to the meta layer, and two gates so
that neither features nor sizing can be credited with an edge the primary does not have. Optuna
searches the primary; fracdiff and a hidden Markov model enter as meta features and never as
signals.

**Verdict: nothing ships.** Gate 1 fails on both blocks that are allowed to judge it, and Gate 2
fails on all 18 cells. The one place the primary looks good is the block where gold rose 167.8%,
and the drift control says that is what it is.

**Code.** `research/xau/xau_core.py` (data admission, blocks, costs, the primary walker),
`run_phase0_gate1.py` (Phase 0 + Optuna + Gate 1), `run_frozen.py` (five frozen geometries),
`run_drift_control.py` (the matched random-entry null), `xau_meta.py` (fracdiff, causal HMM, 28
features, truncation audit), `run_meta_gate2.py` (meta models, Gate 2, the single locked read),
`run_deflate_fix.py`. Output under `results/xau/`.

## The data, and why the blocks are cut where they are

`data/XAU_ISO_15m.csv`, the registry's `XAU_ISO_15m`: 494,235 rows, 2004-06-11 → 2026-01-30, both
matching the recorded values exactly (the registry sha256 is of the .7z **archive**, so rows and
span are this feed's identity). The clock was **re-derived rather than inherited** — mean |15m
return| peaks at file 15:30 in both summer and winter, which is 08:30 New York after a −7h shift,
gold's own anchor and not an equity open. DST-stable. **Pre-2010 is excluded** per the registry's
defect note: 2004 runs 11.24% zero-range bars at a median 9 ticks of volume, against ≤0.23% and
468+ from 2010. 371,586 bars survive.

| block | span | bars | gold | role |
| --- | --- | --- | --- | --- |
| A_primary | 2010-01-01 → 2017-12-31 | 5.24 yr | 1093 → 1302, **+19.1%** | the primary is fitted here and nowhere else |
| B_meta | 2018-01-01 → 2022-12-31 | 3.36 yr | 1310 → 1824, **+39.3%** | the meta layer trains here |
| C_locked | 2023-01-01 → end | 2.00 yr | 1826 → 4890, **+167.8%** | read once, at the end |

Three blocks rather than two, because the architecture requires the primary to be fitted on data
the meta layer does not see. Costs are 0.30 USD/oz round turn plus 0.05/side slippage, and every
headline is re-run at 0×/0.5×/2×/3×.

## Phase 0 — the mechanism, written before any code

| question | answer |
| --- | --- |
| Who is the counterparty? | Leveraged retail XAUUSD holders at CFD and spot-FX brokers, and the brokers' risk desks. Gold is the most heavily retail-traded CFD instrument; account leverage runs 50–500× and protective stops rest immediately beyond recent swing extremes — where a Donchian channel sits. |
| Why do they trade anyway? | They do not choose to. The stop is a **resting order** placed earlier, and the margin agreement lets the broker liquidate without consent once maintenance is breached. |
| Why can't they stop? | The order is already in the book and the liquidation is contractual. At the moment the level breaks, the flow is price-insensitive and one-directional. |
| What do we provide? | Liquidity into forced flow, and patience — we hold what the liquidated account could not. |
| What would end it? | Retail leverage caps, brokers internalising rather than hedging out, or enough competing capital. Gold's retail base has grown. |

Family: **constrained flow** — sharp, capacity-limited, decaying.

**The red flag was declared up front and it is the correct reading of the result.** This mechanism
is attached to a strategy family that *already existed* on this branch, not derived independently
and then implemented. The skill names "a mechanism story attached after the pattern was found" as a
red flag, and this is one. Worse, the primary is *fitted*: six axes chosen by Optuna. It therefore
carries the full deflation burden and gets no benefit of the doubt from the story. Gate 1 does not
care where a primary came from, which is exactly why it runs before any feature is written.

## Phase 1 + Gate 1 — the fitted primary fails outside its own block

600 Optuna TPE trials on **block A only**, objective the t-statistic of per-event % return with a
floor of 200 events — the same statistic Gate 1 measures, so the search is not optimising one thing
and being judged on another. Blocks B and C are never evaluated inside the search.

Chosen: `ent 103 / exN 78 / stop 2.694N / no target / hold 101 bars / SHORT only`.

| block | n | net %/event | p | verdict |
| --- | --- | --- | --- | --- |
| A (in-sample) | 965 | +0.03784 | 0.071 | in-sample |
| **B_meta** | 620 | **−0.00404** | 1.000 | **FAIL** |
| **C_locked** | 375 | **−0.06174** | 1.000 | **FAIL** |

The search picked the short side on a 2010–2017 gold bear market and it inverted the moment gold
turned. Only 55.5% of the block-A trial population is positive at a median t of 0.278 — the
optimiser was working a surface with nothing in it.

## The fairer test — five geometries frozen on other markets

Better than an Optuna fit: geometries taken verbatim from this branch's own notes, with **zero**
gold-specific parameters, so every gold block is out of sample and the deflation burden belongs to
the original studies. Five geometries × three sides × three blocks = 45 declared cells.

| block | net-positive | p ≤ 0.10 | **gross**-positive | mean net |
| --- | --- | --- | --- | --- |
| A_primary | 4/15 | **0/15** | 14/15 | −0.00949 |
| B_meta | 4/15 | **0/15** | 12/15 | −0.00982 |
| C_locked | 8/15 | 4/15 | 10/15 | +0.01522 |

**Gross-positive 14 of 15 and net-positive 4 of 15 on block A is gold's cost floor doing the work** —
CLAUDE.md's standing finding restated on a sixth family. And every one of the four cells that
clears on block C is **long-only**, in the block where gold rose 167.8%:

| geometry | side | block | n | net | gross | p |
| --- | --- | --- | --- | --- | --- | --- |
| V38 70/30 2.5N | long | C_locked | 289 | **+0.1356** | +0.1515 | 0.019 |
| V24 30/20 2.0N | long | C_locked | 562 | +0.0981 | +0.1146 | 0.017 |
| V61i 20/20 2.0N | long | C_locked | 676 | +0.0788 | +0.0954 | 0.037 |
| V61h 15/30 3.0N 6ATR | long | C_locked | 1,476 | +0.0181 | +0.0348 | 0.088 |

Pooled by side over all blocks: long **+0.0197** (67% of cells positive), short **−0.0240** (13%),
both +0.0002 (27%).

## The drift control — the four passes are the drift, and they are the wrong shape

`STUDY_TURTLE` already recorded that a channel breakout with a trailing exit is a **drift
harvester**: its random-entry control earned +0.586 R/trade where the index rose 247.6% and −0.005
where it rose 49.6%. So each passing cell was scored against the drift it is harvesting — same side,
same exit machine, same trade count, entered at **random bars**, 400 draws.

| cell | block | n | rule %/ev | random p50 | p |
| --- | --- | --- | --- | --- | --- |
| V38 70/30 long | C_locked | 289 | +0.1356 | +0.0367 | **0.000** |
| V24 30/20 long | C_locked | 562 | +0.0981 | +0.0288 | **0.000** |
| V61i 20/20 long | C_locked | 676 | +0.0788 | +0.0314 | **0.000** |

The breakout does beat a coin flip in the bull market — and it does so on **0 of 4 cells on block A
and 1 of 4 on block B**. A conditional edge that exists only in the block that was opened last, and
is absent in the two blocks that were permitted to judge it, is the wrong shape: this branch has now
recorded that pattern eleven times, and it has never once survived a further read.

## Phases 3–4 — the meta layer, built anyway, and Gate 2

**Gate 1 had already failed. The architecture's instruction at that point is to stop.** The meta
layer was built because it was asked for, and because a completed Gate 2 over a failed Gate 1 is
worth recording — but nothing below rescues the primary, and the two-gate structure exists precisely
to make that claim impossible to smuggle in.

Primary for the meta layer: **V38 Donchian 70/30, 2.5N stop, no target, long, 30-minute bars** —
chosen on **block A** (the only long cell there that is not negative, +0.00061), which keeps block B
clean for the meta layer. 743 / 483 / 289 events on A / B / C.

**Fracdiff.** López de Prado's fixed-width FFD on log price: `w_k = −w_{k−1}(d−k+1)/k`, truncated at
|w| < 1e-4, so bar *t* uses a fixed number of prior bars and nothing after it. `d` chosen by ADF
**on block A only**, smallest on a declared 11-rung ladder clearing the 5% MacKinnon value:

| d | 0.0 | 0.3 | 0.5 | 0.6 | **0.7** | 0.8 | 1.0 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ADF t | −1.91 | −2.42 | −2.54 | −2.81 | **−3.00** | −3.98 | −16.89 |
| window | 1 | 388 | 200 | 140 | **97** | 64 | 2 |

**d = 0.7, a 97-bar fixed window.** Chosen on block A and frozen; choosing it on the block the meta
layer trains on would be selection.

**HMM.** Hand-rolled Baum-Welch (`research/v27/v27hmm.py`), fitted on **block A only**, read
**FILTERED** everywhere — `P(s_t | data up to t)`, the forward pass alone. `posterior_smoothed` and
Viterbi read the future; `STUDY_V27` measured what that costs (locked PF 1.351 smoothed against
0.973 causal on **nearly identical trade counts**, so the leak is invisible in the count and shows
only in which bars got labelled). The fitted structure is sensible and gold-like:

| state | mean 30m log-return ×100 | mean rv48 | self-transition |
| --- | --- | --- | --- |
| bear | −0.00328 | 0.2369 | 0.928 |
| side | −0.00080 | 0.0865 | 0.963 |
| bull | +0.00189 | 0.1398 | 0.943 |

The filtered and smoothed labellings agree on **96.4%** of bars — close enough that the difference
would be easy to dismiss, and `STUDY_V27` is the reason it is not.

28 features in all: fracdiff level and z-score, three HMM posteriors and their bull−bear edge,
volatility level/rank/ratio, realised-vol ratio, EMA distance and slope, RSI, two ROCs, breakout
excess and channel width, close position, body, CHOP, ADX, DI difference, volume ratio, and the
clock. **Truncation audit: 0 mismatches over 1,680 value comparisons on 60 probe bars.**

**The models are at the noise floor and the shuffled twins say so.** Purged, embargoed 5-fold inside
block B, each model run beside a shuffled-label twin:

| model | OOF AUC | twin AUC | OOF IC | twin IC |
| --- | --- | --- | --- | --- |
| logistic | 0.4871 | 0.4681 | −0.1076 | −0.1115 |
| random forest | 0.5097 | 0.4987 | −0.0797 | −0.0945 |
| LightGBM | 0.4780 | 0.5019 | −0.0934 | −0.0506 |

Two AUCs are **below** chance, every IC is **negative**, and the twins are indistinguishable from
the real models. There is no information in 28 features about which of this primary's events pays.

**Gate 2: 0 of 18 declared cells clear.** Keep-fractions declared in advance at 80/70/60/50/40/30%,
uplift measured on **unsized** per-event returns with a paired stationary bootstrap; sizing reported
and never credited.

| model | best cell | uplift | 95% CI | p | vs a random filter of the same size |
| --- | --- | --- | --- | --- | --- |
| logistic | 70% | +0.00002 | [−0.0443, +0.0446] | 0.505 | p 0.505 |
| **random forest** | **60%** | **+0.02695** | [−0.0284, +0.0825] | 0.160 | **p 0.182** |
| LightGBM | 30% | +0.00947 | [−0.0918, +0.1233] | 0.403 | p 0.407 |

Every confidence interval contains zero. The best cell in the table (rf@70%, p 0.122) scores
**p 0.198** against a random filter keeping the same fraction — restrictiveness alone would have
produced it. The logistic model's uplift falls **monotonically** as it filters harder
(−0.0096 → +0.0000 → −0.0095 → −0.0617 → −0.0539 → −0.0622): the more of its opinion you act on, the
worse you do.

## Block C — one read, everything frozen first

Declared before opening: the block-B cell with the lowest bootstrap p — **rf at keep 70%** — refitted
once on all of block B, thresholded at block B's own score distribution.

| arm | n | net %/event | hit | p vs 0 |
| --- | --- | --- | --- | --- |
| primary, unfiltered | 289 | +0.13560 | 36.3% | 0.019 |
| primary + meta filter | 209 | +0.13983 | 34.9% | 0.030 |
| **uplift** | | **+0.00423** | | random filter of the same size p **0.443** |

The meta layer contributes **three per cent of one basis point per event**, and a random filter of
the same size does as well 44% of the time. It is worth nothing, on the block where the primary
looks best.

**One thing did work, and it is worth recording.** The block-C kept fraction is **72.3%** against
the 70% the threshold was set for — the score *is* calibrated across the split. `STUDY_AUTOBNN`
recorded the opposite failure (a research threshold that kept 105 of 105 locked events because
every posterior mean sat above the cut, making the threshold meaningless out of sample). Purged
embargoed CV on a properly frozen feature transform produces a score that transfers its
distribution. It just has nothing in it.

## Phase 5 — deflation, and a correction to my own first number

Trials counted: 600 Optuna + 45 frozen cells + 12 drift-control cells + 11 fracdiff rungs + 1 HMM
state count + 3 meta models + 18 thresholds = **690**.

**`run_meta_gate2.py` printed a deflated Sharpe of 0.9919 and that number is wrong.** It fed
`deflated_sharpe` the variance of the 18 Gate-2 *uplifts* as `var_trials`. The DSR's null is the
distribution of the Sharpe ratios *the search produced*, and 18 near-zero uplifts have a variance
three orders of magnitude too small — the expected max under the null came out at 0.0008.
Recomputed from the actual trial-Sharpe pool (639 scored trials; per-event Sharpe mean −0.017,
sd 0.060, max +0.134), `run_deflate_fix.py`:

| arm | ρ = 0.0 (N 690) | ρ = 0.5 (N 346) | ρ = 0.8 (N 139) |
| --- | --- | --- | --- |
| E[max SR \| null] | 0.1897 | 0.1772 | 0.1594 |
| block-C primary unfiltered (SR 0.133) | **DSR 0.168** | 0.226 | 0.326 |
| block-C primary + meta (SR 0.138) | **DSR 0.228** | 0.286 | 0.379 |

(The Optuna objective was a t-statistic, converted to a per-event Sharpe with the primary's own
block-A event count of 965 as the representative *n*; each trial had its own count above the
200-event floor, so this is a proxy — what the DSR consumes is the *spread* of the pool, which is
insensitive to it.)

**At every assumed correlation the expected best-of-690-worthless-trials exceeds the realised
block-C Sharpe.** PSR against zero, ignoring multiplicity entirely, is 0.976 — which is exactly why
the DSR is reported as a *curve over assumed N* and the PSR is not reported alone.

This is the same error class recorded on the VP/TPO study, reached from the other side: there the
trial variance was estimated from annualised figures and the DSR came out too *harsh* (0.571 against
a corrected 0.912); here it was estimated from uplifts and came out far too *generous*. **State what
`var_trials` is measured over, every time.**

**White's reality check** across all 18 candidates, discards kept: best rf@70% at mean +0.000347,
null max p95 +0.000691, **reality-check p 0.276 — FAIL**. A set of worthless candidates searched
this hard produces a winner this good more than a quarter of the time.

## What this establishes

1. **Gold's cost floor is the binding constraint on this family, not the signal.** Gross-positive
   14/15 on block A against net-positive 4/15. The 0.30 USD/oz round turn is an *assumption* — no
   feed here carries bid/ask — and CLAUDE.md's standing note applies: on gold the difference between
   0.30 and 0.13 is the difference between −0.08 R and break-even.
2. **The Optuna primary picked a side, not an edge.** Six axes on a 2010–2017 bear market produced
   short-only, and it inverted on both later blocks. Freezing geometries from other markets is
   strictly better than fitting them here.
3. **The one thing that works on gold is being long in a bull market, and the drift control prices
   it.** The breakout beats a random entry at p 0.000 on block C and on 0/4 and 1/4 cells of the two
   blocks that were allowed to judge. A result present only where it was looked at last is not
   adoptable.
4. **The meta layer is null and its own diagnostics said so before Gate 2 ran.** AUC at or below
   chance, negative ICs, twins matching. A meta layer cannot manufacture selection information that
   is not in the events.
5. **The architecture worked exactly as designed.** Gate 1 delivered the verdict for the cost of one
   module and three scripts, before any feature was written; Gate 2 then confirmed it on unsized
   returns, so no sizing rule could be mistaken for the finding. Second consecutive primary killed
   at Gate 1 (`STUDY_LEV_ETF_REBALANCE` was the first).

## What would reopen it

A **measured** gold spread — bid/ask is unavailable in every feed on this branch, and on gold the
assumption decides the answer. Failing that, a gold history containing a genuine bear regime in a
*reserved* block, so that a long-biased breakout can be tested somewhere other than the run-up it
was read on. Neither more parameters nor more features is on the list.
