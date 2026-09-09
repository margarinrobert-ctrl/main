# Donchian + ATR on US30, with the volume profile demoted to the meta layer

`research/vpus30/vpdon.py`, `run_d1.py` … `run_d5.py`. Feed `US30_LONG_15m` (193,942 bars,
2016–2025, sha256 24dcf2e1c7ba398f). Split at 2023-05-14, last 25% of sessions held out.
Round turn 2.29 points. Everything scored in **percent of entry price** — the stop varies with ATR,
so R is a denominator trap.

## Why the architecture changed

`STUDY_VP_US30` made the volume-profile setups the *primaries* and 0 of 10 control tests cleared.
Under mechanism-first, features may never decide direction or whether an opportunity exists. So the
profile is demoted: the primary is now a **Donchian channel break with an ATR stop** — an object
this branch has measured on US30 many times — and all 52 profile/quant features plus 14 new
channel/ATR features are confined to scoring events the primary already emitted.

## Gate 1 — the raw primary. 0 of 8

Declared grid, all counted: entry channel {20, 55} × stop {2.0, 3.0} ATR × side {long, both}.
Exit = the opposite 20-bar channel or the stop, **no target**. Entries RTH only, exits walked on the
full frame so a stop can fire overnight. Null = a **risk-matched random entry**: same count, same
side mix, re-simulated through the same walker, so only the entry bar moves.

| cell | blk | n | net % | gross % | PF | cost/risk | control | p |
|---|---|---|---|---|---|---|---|---|
| don20 2.0N long | research | 1089 | 0.0121 | 0.0205 | 1.061 | 0.026 | 0.0138 | 0.537 |
| don20 3.0N long | research | 1006 | 0.0190 | 0.0275 | 1.085 | 0.017 | 0.0102 | 0.333 |
| don55 2.0N both | research | 1587 | 0.0176 | 0.0260 | 1.084 | 0.025 | 0.0012 | 0.188 |
| don55 3.0N long | research | 788 | 0.0279 | 0.0363 | 1.130 | 0.017 | 0.0089 | 0.177 |
| **don55 3.0N both** | **research** | **1477** | **0.0209** | **0.0293** | **1.087** | **0.017** | **−0.0020** | **0.150** |
| don55 3.0N both | HOLDOUT | 529 | 0.0243 | 0.0302 | 1.124 | 0.014 | 0.0116 | 0.307 |

**All eight cells are profitable, net, on both blocks — and not one is distinguishable from a
random entry with the same geometry.** Best research p 0.150 against 0.4 expected by chance. Cost is
1.4–2.7% of the stop, so cost is not the objection; the exit geometry is the asset and the channel
break carries no measurable direction information. Eighth Donchian breakout on this branch to fail
its own risk-matched control (`STUDY_TURTLE_YOUTUBE`, `STUDY_V38`, `STUDY_V12`, …).

Under the strict reading, no primary is eligible for a meta layer. The layer was built anyway,
because a base at PF 1.09 is *not dead* (contrast `STUDY_EMA48_VWAP_DL`, where a filter was asked
to rescue PF 0.19) — a conditional edge could exist inside an unconditional zero. The primary
carried forward is `don55 3.0N both`: best control p **and** the most events, 1477 / 529.

## The base-rate check binds, and only just

66 features (22 volume-profile + 30 quant + 14 new `don.*`). Truncation audit on the new family
**0 mismatches / 168**. Share of *signal* bars above the all-RTH-bar median:

- **dropped as degenerate**: `p_neut` (0.000) and `don.age` (0.000) — a breakout bar is never in a
  neutral prior distribution and is by definition a zero-age breakout.
- most selective survivors are honest readings, not the trigger restated: `vol.rng_atr` 0.875,
  `don.w20` 0.157, `hmm.bear` 0.840 — largest lift 1.75×, against the 94.7% / 100.0% / 99.8%
  pass rates RSI, Aroon and MACD show on breakout bars.

## Screen: 8 of 128 cells, against 6.4 expected

Each surviving feature cut at its own research median, scored as a **veto** and re-simulated,
against a random gate of the same selectivity. Leaders: `p_bull` hi (PF 1.465, p 0.000),
`stack5` hi (1.434, p 0.000), `inside_va` hi (1.289, p 0.005), `stack20` hi (1.291, p 0.005).

Coherent in one respect worth recording: **the two constructions in Anderson's book that were *not*
in `STUDY_AUCTION`'s 47-condition pool — distribution SHAPE and STACKED POCs — are exactly the two
at the top of the screen.** That is the only thing here that looks like a finding, and 8 of 128 is
chance.

## Gate 2 — the ladder is the cleanest noise floor measured on this branch, and it still fails

Objective is the percent actually earned, not win/lose. Purged embargoed folds, every model beside
a shuffled-label twin.

| model | OOF IC | shuffled twin | winner |
|---|---|---|---|
| **ridge** | **+0.0755** | −0.0159 | real |
| rf | +0.0438 | −0.0358 | real |
| xgb | +0.0334 | −0.0393 | real |
| lgbm | +0.0178 | −0.0366 | real |

**Twin wins 0 of 4.** Capacity is monotonically harmful again and **ridge wins the whole ladder** —
the sixth family here where the linear model beats every booster and every net. Gate 2 (veto,
re-simulated, vs a random gate of the same size) clears in 2 of 12 cells against 0.6 expected, both
ridge: keep-70% uplift +0.0260 at p 0.012, keep-50% +0.0377 at p 0.040, monotone in selectivity.
Second null on research: kept P(mean≤0) 0.003, P(uplift≤0) 0.066.

Family ablation (drop one, refit): load-bearing are `vol`, `vp`, `tod`, `mom`; dropping `don`,
`ffd`, `hmm` or `str` **improves** the model. The 40-feature load-bearing subset scores IC 0.0890
against 0.0755 for all 62 — **feature engineering is subtractive here for the fifth time.** Note
what that says: the new channel/ATR family, the one the request was about, is the *most* harmful
thing to include.

## The one holdout read: calibrated, and predicting nothing

Ridge on the 40-feature subset, threshold fixed on research at keep-50%, opened once.

| | n | net % | PF |
|---|---|---|---|
| base | 529 | 0.0243 | 1.124 |
| kept | 268 | 0.0259 | 1.129 |

Uplift **+0.0016**. Random gate of the same size earns **more** (median 0.0286, p 0.525). Holdout
IC **−0.0032**. Kept P(mean≤0) 0.297. Total return falls **12.87% → 6.94%** because it removes half
the trades — `STUDY_V61`'s finding again.

**The threshold kept 0.507 against the 0.50 it was set for**, so the score *is* calibrated across
the split — the failure is predictability, not `STUDY_AUTOBNN`'s miscalibration.

Deflated Sharpe **0.427 at 157 counted looks**: per-trade Sharpe 0.0350 against an expected
best-of-noise of **0.0452**. The best thing the search found is *below the noise floor of its own
search*. FAIL.

## The two things worth carrying

**1. The feature ICs transfer and the strategy uplift does not, and that is a different failure from
the usual one.** Across 62 features, `corr(research IC, holdout IC)` is **+0.6407 Pearson / +0.6443
Spearman with the sign kept 71%** — far above this branch's usual −0.03 to +0.2. What halves is the
magnitude: mean |IC| **0.0707 research → 0.0386 holdout**. The features are genuinely, stably,
weakly informative; 0.04 IC over 529 events is not enough to move a P&L. So a transfer correlation
being high is not evidence a filter will work — it is evidence the *direction* survives, and the
size is a separate question that the trade table answers separately.

**2. The eight strongest features are one feature.** `d_poc`, `d_vah`, `d_val`, `dev_pos`,
`mom.d_ema78`, `mom.d_ema26`, `mom.rsi14`, `ffd.z250` have a **mean pairwise |rho| of 0.820 on the
signal bars** (d_poc vs d_vah 0.97, d_ema26 vs rsi14 **0.99**), and every one points the same way:
the further above its references price already is when the channel breaks, the better the trade.
That is `STUDY_V40`'s "a moving average is priced by its DISTANCE" reproduced on US30, with the
profile's POC and value edges as the reference instead of an MA — and it is one number wearing
eight names. **Seventh time the pool has been caught duplicating**, and three of them were exact:
`dev_pos == str.sess_pos` (rho 1.0000, `vpquant` literally reads the column) and
`don.atr_pct == don.stop_pct` (rho 1.0000, one is a constant multiple of the other).

## What ships

Two scripts, both with the numbers in their headers and **no edge claimed**:

- `pine/vpus30/US30_DONCHIAN_ATR_strategy.pine` — the bare Gate 1 primary.
- `pine/vpus30/US30_VP_DONCHIAN_ATR_strategy.pine` — the same rule with the **volume profile actually
  computed on the chart**: every completed session binned at 0.10 × its own mean ATR, each bar's
  volume spread uniformly across its `[low, high]`, the value area grown outward from the POC always
  taking the richer neighbour to 70%, the prior session's POC/VAH/VAL frozen and plotted, and the
  last 20 sessions' POCs kept for the stacked-POC counts. The four screen leaders ship as gates,
  **all default off**, each tooltip carrying its own research → holdout pair.

Two parity harnesses, because a port cannot be asserted by reading it:

- `don_parity.py` — the script's order model against the engine: trade count 0.993, side agreement
  1.0000, per-trade correlation 0.9997, script +6.1% research / +0.7% holdout. The exit bar differs
  on two trades in three by construction (the engine takes a channel break at that bar's close; a
  script fills at the next open) and the script reads slightly *better*, the non-conservative
  direction.
- `vp_parity.py` — the script's **profile** against `vpcore.sessions` over all 2,246 sessions. With
  a session-only ATR, POC/VAL/VAH are **identical 1.0000, max diff 0.0, bin count identical
  1.0000**. With a chart ATR instead, correlation is 0.99998 and **not one bin count matches**,
  because a chart ATR sees the overnight and runs **0.884×** the RTH-only one, moving every bin edge
  — median POC shift 0.036 ATR, shape agreement 96.5%, stacked-POC ≥ 1 agreement 96.5%. That
  difference is invisible in a correlation and total in the bins, which is why it is an input and
  why the session-only ATR is the default.

## Nothing here is tradeable

157 counted looks; the primary fails its own control on all eight cells; the meta layer fails the
holdout at p 0.525 with IC −0.0032 and a deflated Sharpe below its own noise floor. What would move
it is not more features — the ablation says the pool is already too large for 1,477 events — and not
more capacity, which was swept and is harmful. It is **more events**, or a primary that clears
Gate 1.
