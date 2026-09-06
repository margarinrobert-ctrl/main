# STUDY: feature engineering on gold — Donchian breakout × CVD

**What this is.** 60 causal CVD-family features on a Donchian breakout in XAUUSD, screened against
same-selectivity random filters, with the four divergence patterns tested separately, a truncation
audit, a sign-structure test, a pivot-only ablation and a coin-flip control.

**Verdict: null, with one named near-replication.** 13 of 229 screened cells clear p ≤ 0.05 against
11.5 expected by chance; one survives BH. The family's own directional prediction is **inverted** —
on a long-only base the *bearish* patterns beat the *bullish* ones by 11×. The one BH survivor is
`exhausted sellers, k=3 pivots, 20-bar window` at 60m, which is exactly the pattern
`STUDY_V54_CVD_KAMA`/`STUDY_V55` shipped on NQ, and it is positive on all three gold blocks.

**Two genuinely new positives worth keeping**, both about the *measurement* rather than the edge:
CVD is the first feature family on this branch to **pass the base-rate check** — it is not the
breakout restated — and the **pivot-only ablation** shows the CVD comparison is not pure decoration.

**Code.** `research/xaucvd/xcvd.py` (bars + CVD from sub-bars, 60 features, truncation audit),
`run_xcvd.py` (base, base rates, screen, patterns), `run_xcvd2.py` (audit, sign structure,
neighbourhood, one locked read, resolution), `run_xcvd3.py` (the ablation). Output
`results/xaucvd/`.

## What is different about CVD on gold, and it degrades the object twice

CVD needs bars **finer than the chart**. `STUDY_V54` built it from 1-minute bars under a 30-minute
chart — 30 sub-bars a bar — and recorded that NQ was the only feed with 1-minute data. Gold's finest
feed here is **15-minute**, so the delta must be built from 15m sub-bars under a coarser chart:

| chart | sub-bars per bar | events (V54 geometry, A/B/C) |
| --- | --- | --- |
| 60m | **4** — a coarse delta, four signs a bar | 844 / 566 / 319 |
| 240m | **16** — closest here to V54's 30 | 195 / 142 / 62 |

Both are run. Two caveats stay attached to every number:

1. It is a **proxy** — the same one TradingView uses, each sub-bar's whole volume signed by that
   sub-bar's own direction. It is not aggressor-side order flow; no feed here has that.
2. **Gold's volume is tick volume, not contracts.** So this proxy signs *tick counts*. On NQ it
   signed contract volume. A null here is therefore weaker evidence against CVD than a null on NQ.

## Step 0 — the base, before anything is added to it

Against a random entry with the same exits, 300 draws:

| tf | geometry | A_primary | B_meta | C_locked |
| --- | --- | --- | --- | --- |
| 60 | V54 20/20 2.0N | +0.0226, p **0.077** | −0.0035, p 0.593 | +0.0849, p **0.000** |
| 60 | V38 70/30 2.5N | +0.0364, p 0.157 | −0.0611, p 0.920 | +0.0972, p 0.060 |
| 240 | V54 20/20 2.0N | +0.0001, p 0.500 | +0.0602, p 0.183 | +0.6844, p **0.000** |
| 240 | V38 70/30 2.5N | +0.1265, p 0.193 | −0.0421, p 0.610 | +0.7839, p 0.007 |

This reproduces `STUDY_XAU_TWO_LAYER` exactly: the gold Donchian breakout beats a coin flip in the
block where gold rose 167.8% and essentially nowhere else. **So the question a feature has to answer
is not "does it improve gold Donchian" — it is "does it clear a same-selectivity random filter on
the blocks where the base has no edge".** A filter that only works on block C is the drift again.

## Step 1 — the base-rate check, and CVD is the first family to pass it

Four indicator families have died on this branch by *being the breakout restated*: RSI(14) ≥ 55 on
**94.7%** of breakout bars, Aroon osc ≥ 0 on **100.0%**, MACD > 0 on **99.8–100.0%**, MFI(9) ≥ 50 on
**91.7%**. Two lines, before any P&L.

Of 120 CVD feature × timeframe cells, **2 pass more than 95% of signal bars** (and one of those is
`ctx.excess`, which is the breakout distance by construction), and 8 have lift within 3% of 1.00.
The rest genuinely bind:

| feature | passes on signal bars | on all bars | lift |
| --- | --- | --- | --- |
| `eff.px_per_delta20` | 89.5% | 50.9% | 1.76 |
| `cvd.z10` | 85.2% | 50.8% | 1.68 |
| `flow.sub_up` | 81.5% | 61.1% | 1.33 |
| `conf.both55` (price *and* CVD at a 55-bar high) | 7.8% | 3.4% | 2.29 |
| `div.exhausted_buyers_k5_w10` | 4.5% | 9.2% | **0.49** |

**CVD is a genuinely different reading of a breakout bar, not the trigger wearing another name.**
That is the first time a proposed family has cleared this check here, and it is why the rest of the
study was worth running.

## Step 2 — the screen: 13 hits against 11.5 expected

Every feature cut at its research-block median (binaries at True), scored on blocks A+B against a
random filter keeping the same *number* of the same events, 600 draws:

**229 scorable cells. 13 at p ≤ 0.05 against 11.5 expected by chance. 1 survives BH at q = 0.10.**

By family — and this is the shape of the answer:

| family | cells | mean edge | hits at p ≤ 0.05 | best p |
| --- | --- | --- | --- | --- |
| **div** (the four patterns) | 134 | **+0.0394** | **11** | 0.000 |
| eff (price per unit delta) | 16 | −0.0130 | 1 | 0.025 |
| ctx | 16 | −0.0147 | 1 | 0.020 |
| flow (the bar's own delta) | 16 | −0.0315 | 0 | 0.175 |
| cvd (slope, z-score, rank) | 32 | −0.0368 | 0 | 0.063 |
| conf (CVD confirming the break) | 15 | −0.0756 | 0 | 0.140 |

**Every continuous CVD reading has a negative mean edge.** Slope, z-score, rank, the bar's own
signed delta, the sub-bar imbalance, price-per-unit-delta, and CVD-confirming-the-break all
subtract. Whatever is there is in the discrete pivot patterns and nowhere else.

## Step 3 — the sign structure, and it is inverted

The four patterns make a **directional** prediction. On a long-only base the two bullish readings
should lead. `STUDY_V54` measured exactly that on NQ: the bullish patterns worked, and **absorbed
buying — the most bearish of the four — was the only negative row on both blocks**, which is the
sign a long-only system predicts.

On gold, pooled over both timeframes, three pivot widths and three windows:

| polarity | pattern | cells | mean edge | % positive | mean block-C edge |
| --- | --- | --- | --- | --- | --- |
| BEARISH | **absorbed_buying** | 18 | **+0.1145** | 94.4% | −0.060 |
| BEARISH | exhausted_buyers | 17 | +0.1008 | 88.2% | +0.115 |
| BULLISH | exhausted_sellers | 18 | +0.0639 | 94.4% | −0.223 |
| BULLISH | absorbed_selling | 18 | −0.0450 | 27.8% | +0.017 |

**Bearish mean +0.108, bullish mean +0.009 — 11×, on a long-only base.** The best pattern of the
four is the one NQ found worst. A condition that works whichever way its own directional test points
is not that directional test. This is the same class of evidence that killed the levered-ETF primary
in `STUDY_LEV_ETF_REBALANCE`, where the mechanism's own conditioning variable predicted the opposite
of the mechanism.

## Step 4 — leakage, and the neighbourhood

**Truncation audit: 0 mismatches over 1,500 value comparisons on 25 probe bars, at both
timeframes.** This is the test that caught the divergence fill-forward leak in
`STUDY_DIVERGENCE_CONFIRM` (+37 full against +999 truncated), so it was the first thing run.

The neighbourhood does not discriminate. `exhausted_sellers` at 60m is positive in 100% of its 9
k × w cells and falls as the window widens — the shape `STUDY_V55` found on NQ. But
`absorbed_buying` at 240m is positive in 89% and rises coherently with pivot width. **Two patterns
of opposite polarity both show coherent surfaces**, so coherence is not separating them here.

## Step 5 — the decisive ablation: strip the CVD out

Every pattern is "a confirmed swing point occurred in the last *w* bars **and** the CVD comparison
at that pivot pointed a particular way". Four arms, pooled over k, w and timeframe:

| arm | keeps | research edge | % positive | block-C edge |
| --- | --- | --- | --- | --- |
| absorbed_buying (as specified) | 32% | **+0.1224** | 88.9% | −0.039 |
| exhausted_sellers (as specified) | 31% | +0.0660 | 82.9% | −0.079 |
| any of the four patterns | 68% | +0.0642 | 88.6% | −0.132 |
| **any pivot only, no CVD** | 92% | **+0.0167** | 80.0% | +0.015 |
| **pivot low only, no CVD** | 87% | **+0.0027** | 58.3% | −0.027 |

Matched head-to-head at the same (k, w, timeframe, block): exhausted_sellers beats pivot-only in
67% of cells (+0.008 mean), absorbed_buying in 87% (+0.118). **So the CVD comparison is not pure
decoration — it does add over pivot recency alone.** That is the second real positive here.

But the coin-flip control — the pivot flag with the same *fraction* of pivots kept at random, 300
draws — only clears in one corner:

| tf | k | w | block | real edge | coin p50 | p |
| --- | --- | --- | --- | --- | --- | --- |
| 60 | 2 | 20 | A_primary | +0.0799 | −0.0051 | **0.013** |
| 60 | 2 | 20 | B_meta | +0.0866 | −0.0153 | **0.050** |
| 60 | 2 | 20 | C_locked | +0.1621 | −0.0023 | 0.090 |
| 60 | 3 | 20 | A_primary | +0.0146 | −0.0178 | 0.267 |
| 240 | 2 | 20 | A_primary | +0.0250 | −0.0262 | 0.387 |
| 240 | 3 | 20 | B_meta | +0.1075 | +0.0125 | 0.303 |

**And every arm's pooled block-C edge is negative** except pivot-only. The research-block ranking
does not carry.

## The one thing that survives, and exactly how far

`div.exhausted_sellers_k2_w20` at 60m — the BH survivor, and the same pattern V54/V55 shipped on NQ:

| block | n | kept | base | filtered | edge | p vs a random filter |
| --- | --- | --- | --- | --- | --- | --- |
| A_primary | 844 | 318 | +0.0292 | +0.1092 | +0.0799 | **0.020** |
| B_meta | 566 | 211 | +0.0213 | +0.1078 | +0.0866 | 0.060 |
| C_locked | 319 | 116 | +0.1786 | +0.3407 | +0.1621 | 0.065 |

Block C: PF 1.642 → **2.197**, kept 36% against the 38% the research threshold was set for, so the
selectivity transfers. Positive on all three blocks, clears the coin flip on two of three.

**What that is and is not.** It is a near-replication, on an independent market and a different
timeframe, of the one CVD pattern this branch already ships. It is **not** a result: it is one cell
of 229 screened; its own family's ranking is polarity-inverted, with the most *bearish* pattern
scoring best on a long-only base; block C is a **second** read of gold's locked block (the first was
`STUDY_XAU_TWO_LAYER`, 690 counted trials), so its p 0.065 is descriptive; and it sits on a base
that is itself null on A and B and drift on C.

## CORRECTION — the screen was a subset, the script is a veto, and the shapes differ

The parity harness caught an error in my own screen. `run_xcvd.py` scored every feature as a
**subset**: run the base ungated, then split its realised trades by the feature. A script cannot do
that. It is a **veto** — the gate decides which bars may *open* a trade, so refusing one breakout
releases the one-position lock and lets a *later* one be taken that the ungated run never saw.
CLAUDE.md carries this rule from `STUDY_AUCTION`: *a conditional split of realised trades is not a
filter test — filter the triggers and re-simulate.*

| block | base n | base %/ev | subset n | subset %/ev | **veto n** | **veto %/ev** | lock-freed | their %/ev |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 844 | +0.0292 | 318 | +0.1092 | **400** | **+0.0563** | 82 | **−0.1485** |
| B | 566 | +0.0213 | 211 | +0.1078 | **265** | **+0.1018** | 56 | +0.0621 |
| C | 319 | +0.1786 | 116 | +0.3407 | **150** | **+0.2233** | 34 | **−0.1772** |

The lock-freed trades are bad on two blocks of three, which is what pulls the veto edge (+0.056 on
block A) well below the post-hoc split (+0.109). Same split the VP/TPO handoff measured from the
other side (32 lock-freed trades reading PF 0.92).

**Scored properly — against a random gate passing the same fraction of bars (32.3%), re-simulated
end to end, 400 draws — the veto is a better-shaped result than the subset was:**

| block | gated n | %/event | control p50 | excess | p | PF (vs ungated) |
| --- | --- | --- | --- | --- | --- | --- |
| A_primary | 400 | +0.0563 | +0.0053 | +0.0510 | **0.003** | 1.193 (1.101) |
| B_meta | 265 | +0.1018 | +0.0398 | +0.0620 | **0.003** | 1.411 (1.076) |
| C_locked | 150 | +0.2233 | +0.1765 | +0.0468 | 0.110 | 1.776 (1.642) |

It clears **both** research blocks at p 0.003 and **decays** on the locked one — the right shape,
where the subset framing had it *growing* across the split. That is a materially better result than
the one reported above, and it arrived from fixing a methodological error, not from a new search.

**But it loses total return on two blocks of three**, because it raises profit factor by removing
53% of the trades: ungated → gated total, A 24.67% → 22.54%, B 12.03% → **26.97%**, C 56.96% →
33.50%. `STUDY_V61` recorded exactly this on NQ — the gate is negative in total return everywhere
because it removes 70–90% of the signals. Whether that is a cost depends on whether you size to a
ratio or to a return target.

None of this rescues the **sign-structure** finding above: the bearish patterns still beat the
bullish ones 11× on a long-only base, and that remains the strongest argument against the family.

## Parity — the shipped script diffed against the engine

`research/xaucvd/xcvd_parity.py` writes the script's own order model out and diffs it trade for
trade, run twice: once with the research's pivot definition (the transcription check) and once with
Pine's `ta.pivotlow`, which requires a *strict* extreme where the research allows a tie.

| | research pivots | Pine pivots | shared | Jaccard |
| --- | --- | --- | --- | --- |
| block A confirmed lows | 13,036 | 12,934 | 12,934 | **0.9922** |

Under both definitions: **100.00% identical exit bars, per-trade correlation 1.0000**, trade-count
ratio 1.000–1.020, and the script reads **conservative** on all three blocks (−18.4% / −0.0% /
−0.0%). A script that reads *better* than the research is reporting the order-model gap rather than
an edge — `STUDY_V56` measured the first V55 draft at +15.2% better, and that was a naked fill bar.

The script ships with `touch` **off**, because the gold table was measured with a strict
`high > channel` and the defaults must reproduce the header.

## Resolution — the one internal check available without 1-minute gold

If CVD carried information the **finer** delta should score better. It does, weakly: 240m (16
sub-bars) has mean edge +0.0142 and a div-family mean of +0.0688, against 60m (4 sub-bars) at
+0.0040 and +0.0141. But 240m produces 5 hits against 5.5 expected — exactly chance — while 60m
produces 8 against 6, and the survivor is a 60m cell. The two readings disagree, and 240m has a
third of the events, so this is suggestive at best.

## What would move it

**1-minute gold bars.** Everything above is built on a 4-to-16 sub-bar delta signing *tick counts*;
V54's NQ result used a 30-sub-bar delta signing contract volume. That is the single largest
degradation between the two studies and it is a data problem, not a modelling one. Failing that,
**a gold history with a real bear regime in a reserved block**, so a long-only base can be tested
somewhere other than the run-up it was read on.

**Do not re-run**: the continuous CVD readings (slope, z-score, rank, bar delta, sub-bar imbalance,
efficiency, CVD-confirms-the-break). All six families have a negative mean edge over 95 cells and
none produced a single hit at p ≤ 0.05 outside the pivot patterns.
