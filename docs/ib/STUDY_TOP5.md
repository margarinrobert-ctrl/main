# The five most profitable strategies on this branch, under one battery

`research/top5/` — `t5_adapt.py` (one trade table shape for eight strategies), `t5_rank.py`
(the ranking), `t5_control.py` (each strategy's own matched control), `t5_battery.py` (the four
tests). Output: `results/top5/ranking.txt`, `results/top5/battery.txt`,
`results/top5/all_blocks.csv`.

---

## 1. The unit, and why it is not points

Eight strategies here were each built with their own engine, feed loader, cost model and block
split. Ranking them against each other means putting them in the same unit, and points are not
that unit: a point of NQ is not a point of US30, and a strategy trading a 47,000 index looks
larger than one trading a 16,000 index for no reason of edge. Everything below is in **percent of
entry price for one unit**, after that feed's own cost model.

Two summaries per feed and block: `pct/trade` (what one unit earns per trade as a fraction of the
price it bought) and `%/yr` (the sum over the block divided by the block's length in years — the
number a trader means by "most profitable").

**Ranking is done on the RESEARCH block only.** Every one of these strategies has already had its
reserved block read once by the study that built it. Ranking on the whole sample would put those
reads inside the selection and the out-of-sample table that follows would mean nothing. Feeds are
equal-weighted, because US100 carries nine years and NQ carries two and summing across them ranks
the feed rather than the strategy.

## 2. The ranking

| # | strategy | feeds | research trades | %/yr | pct/trade | PF | Sharpe | trades/yr |
|---|---|---|---|---|---|---|---|---|
| 1 | **IBS_SESSION** | 3 | 420 | **+9.91** | +0.2716 | 1.48 | +0.93 | 36 |
| 2 | **V56_CVD** | 1 | 157 | **+7.94** | +0.1203 | 1.73 | +1.38 | 66 |
| 3 | **FTM_ORB** | 1 | 195 | **+6.38** | +0.0647 | 1.37 | +1.31 | 99 |
| 4 | **APM_VWAP** | 3 | 394 | **+2.44** | +0.0682 | 1.31 | +0.55 | 32 |
| 5 | **TFI** | 3 | 842 | **+2.43** | +0.0407 | 1.23 | +0.61 | 57 |
| 6 | TRENDDAY | 3 | 153 | +1.02 | +0.0757 | 2.46 | +0.70 | 13 |
| 7 | VWAP_DRIFT | 4 | 2,899 | +0.85 | +0.0033 | 1.05 | +0.18 | 177 |
| 8 | CMMA | 2 | 2,106 | +0.63 | +0.0025 | 1.11 | +0.38 | 252 |

Note the two axes trade off exactly as they should: TRENDDAY has the best profit factor in the
table (2.46) and the worst annual return of the five, because it takes 13 trades a year. FTM has
the third-lowest per-trade result and ranks third on the year because it takes 99.

**The adapters reproduce their own studies.** V56 research +0.3509 R / control p 0.000 and locked
+0.3176 / p 0.005 come back to four decimals; TFI NQ research p 0.013 and locked p 0.327; APM NQ
research p 0.053; FTM's excess over a random quarter-hour entry, +0.10 R at p 0.005 over all 342
trades. Nothing was re-selected.

One accounting correction was needed to make the comparison fair: **`ftm_sim` books commission in
DOLLARS and only slippage in points**, so its `pts` column is gross of the $2.50 round turn. The
adapter puts it back (1.25 points at $2 a point), which moves FTM's research figure from +7.00 to
+6.38 %/yr.

---

## 3. In sample / out of sample

Full tables in `results/top5/battery.txt` §A. The summary that matters is the SHAPE — a rule
chosen on research should look better there, and a block that reads better out of sample is a
regime, not a result.

| strategy | feeds where OOS > IS | verdict |
|---|---|---|
| IBS_SESSION | 2 of 3 (US100 +0.371→+0.412, US30 +0.121→+0.147) | **wrong shape** |
| V56_CVD | 1 of 1 (+0.1203→+0.1371) | **wrong shape** |
| FTM_ORB | 0 of 1 (+0.0647→+0.0456) | right shape |
| APM_VWAP | **3 of 3** (NQ +0.121→+0.273, US100 +0.118→+0.179, US30 −0.034→+0.041) | **wrong shape** |
| TFI | 1 of 3 | right shape on balance |

**THREE OF THE FIVE GROW OUT OF SAMPLE, and APM grows on every feed including one where its
research block LOSES money.** This branch has now recorded that shape seven times. It is not a
sign the strategies are better than they look; it is a sign the later block is a friendlier
regime than the earlier one, and the later block is where all five were read.

## 4. Monte Carlo

Two of them, because they answer different questions. A **day-block bootstrap** resamples whole
sessions with their trades attached and prices the EDGE; a **permutation** reorders the realised
trades and prices the PATH. Permuting cannot change the endpoint, so it says nothing about the
edge, and the bootstrap says nothing about the drawdown a different ordering would have produced.

**The bootstrap fails out of sample almost everywhere.** Counting reserved blocks with
P(mean ≤ 0) ≤ 0.05: IBS 1 of 7, V56 0 of 1 (0.081), FTM 0 of 1 (0.112), APM 2 of 5, TFI 1 of 7.
Every one of these strategies has a positive out-of-sample mean and none of them has an
out-of-sample mean that separates from zero on more than a minority of its blocks. That is the
whole finding of this study restated in one line: **profitable and distinguishable from zero are
different questions, and these five answer the first.**

**The permutation is the usable output.** MC p99 drawdown against the realised drawdown, in
percent of price:

| cell | realised | MC median | MC p99 | percentile of the realised |
|---|---|---|---|---|
| V56 NQ locked | 7.83 | 4.98 | 9.36 | 0.94 — path was **unlucky** |
| TFI US100 research | 10.30 | 5.75 | 11.20 | 0.98 — unlucky |
| FTM NQ research | 5.73 | 3.98 | 7.81 | 0.90 — unlucky |
| IBS US100 research | 8.42 | 14.14 | 27.16 | 0.01 — **lucky, size for 27%** |
| TFI NQ locked | 2.55 | 3.66 | 6.70 | 0.09 — lucky |

Where the percentile is low the realised path was smoother than a reshuffle of its own trades and
**the drawdown to size for is 2–3x what the backtest shows**. IBS's US100 research block is the
extreme: 8.4% realised against a p99 of 27.2%.

## 5. Robustness

**C1 — parameter neighbourhood.** Each declared parameter moved one rung at a time, everything
else at its shipped value, read on both blocks. Share of perturbed out-of-sample cells that are
profitable: V56 **100%**, FTM **100%**, APM 93%, IBS 90%, TFI 73%.

This is the one test all five pass, and it is the one that proves the least. `STUDY_V60` measured
a one-rung box that was 100.0% profitable on research and 26.6% on the locked block; a plateau
filters out artefacts of the SEARCH and cannot see a REGIME. Two of the five have their shipped
value beaten on both blocks by a neighbour (APM at `ema` 16 and `osc` 4; V56 at `ent` 15 out of
sample), which is what a flat surface looks like, not evidence the shipped cell is wrong.

**C2 — cost stress.** Out-of-sample pct per trade at 0x / 1x / 1.5x / 2x / 4x the assumed cost.
All five survive 2x on the feeds where they are profitable at all; only TFI fails the gate, and
it fails it on US30 and US30_ISO where it is already negative at 1x. This is a real departure from
the branch's earlier candidates, **every one of which died at 1.5x the assumed spread**
(`STUDY_HYPO`): these five hold wider barriers for longer, so a fixed round turn is a smaller
fraction of the trade. It removes execution cost as the binding objection and leaves the
statistical one.

**C3 — six chronological folds.** Minimum share of folds positive across feeds: IBS 50%, V56
100%, FTM 67%, APM 50%, TFI 33%. The failures are all on US30 or US30_ISO.

## 6. Live-trading readiness

Nine pre-declared gates, each one a thing that has caught a strategy on this branch before.

| gate | IBS | V56 | FTM | APM | TFI |
|---|---|---|---|---|---|
| matched control p ≤ 0.05 on ≥ half the reserved blocks | 3/7 ✗ | 1/1 ✓ | 0/1 ✗ | 1/5 ✗ | 1/7 ✗ |
| bootstrap P(mean ≤ 0) ≤ 0.05 on ≥ half of them | 1/7 ✗ | 0/1 ✗ | 0/1 ✗ | 2/5 ✗ | 1/7 ✗ |
| ≥ 100 out-of-sample trades | 385 ✓ | 87 ✗ | 147 ✓ | 285 ✓ | 702 ✓ |
| does not grow out of sample on a majority of feeds | ✗ | ✗ | ✓ | ✗ | ✓ |
| survives 2x the assumed cost on every feed | ✓ | ✓ | ✓ | ✓ | ✗ |
| profitable out of sample on ≥ 2 independent feeds | 4/4 ✓ | 1/1 ✗ | 1/1 ✗ | 3/3 ✓ | 2/4 ✓ |
| parameter neighbourhood ≥ 70% profitable | 90% ✓ | 100% ✓ | 100% ✓ | 93% ✓ | 73% ✓ |
| realised drawdown not at the top of its permutation | ✓ | ✓ | ✓ | ✓ | ✓ |
| majority of the six folds positive on every feed | ✗ | ✓ | ✓ | ✗ | ✗ |
| **total** | **5/9** | **5/9** | **6/9** | **5/9** | **5/9** |

**NO STRATEGY WITH MORE THAN ONE RESERVED BLOCK CLEARS ITS OWN MATCHED CONTROL ON A MAJORITY OF
THEM.** V56 is the only one to pass the gate and it has exactly one block to pass it on. IBS is the
best of the multi-block cases at 3 of 7.

**And FTM's published control result does not survive being restricted to the reserved block.**
`STUDY_FTM_ORB_BACKTEST` reports excess +0.1013 R over a random quarter-hour entry at p 0.004,
which reproduces here exactly — over ALL 342 trades (rule +0.162 R, control +0.061, p 0.005). Run
on the 147 locked-block trades alone it is **p 0.152** (rule +0.119, control +0.053). The pass was
carried by the block the strategy was built on. A control computed over the whole sample is a
research-block statistic wearing a holdout's clothes; it is the same error class as ranking a
feature over both blocks (`STUDY_FEATURES`), reached from a different direction, and it applies to
any figure on this branch quoted over "all trades".

The four control p-values that do clear on a reserved block are worth naming, because they are the
whole of the positive evidence here: **V56 NQ locked p 0.005**, **IBS US100 validation p 0.001**,
**IBS US30 validation p 0.031** and **IBS US30_ISO 2026 p 0.028**, plus **APM US100 validation
p 0.030**. Everything else in the table is between 0.09 and 0.99.

## 7. The funded evaluation

60 trading days, +8% target, −6% static maximum drawdown, a 3% daily loss limit, sampled from the
reserved block's own daily returns over EVERY session zero-filled — sampling only the days that
traded would give a strategy taking 36 trades a year the activity of one taking 250. Sizing is
notional leverage, swept, because there is no risk-per-trade unit common to a session fade, a
channel breakout and an opening-range stop.

At **2x notional**, P(pass) / P(bust) / **P(neither)** on the strongest reserved block of each:

| strategy | block | pass | bust | neither |
|---|---|---|---|---|
| IBS_SESSION | US100 validation | 78.5% | 13.4% | 8.1% |
| V56_CVD | NQ locked | 33.8% | 9.2% | **57.0%** |
| FTM_ORB | NQ locked | 23.8% | 7.8% | **68.4%** |
| APM_VWAP | NQ locked | 12.8% | 0.0% | **87.1%** |
| TFI | US100 validation | 25.2% | 5.1% | **69.7%** |

**P(neither) dominates at survivable sizing on four of the five**, which is `STUDY_V15`'s finding
reproduced on a different set of strategies: sized to survive, they grind. Raising leverage to 8x
buys pass rate and bust rate together (V56 66% / 30%, TFI US30 33% / 45%) and never buys a better
ratio. Print P(neither) beside P(pass) or the table lies.

## 8. What this says

1. **The ranking by profit and the ranking by evidence are different orderings.** IBS is first on
   the year at +9.91%/yr and grows out of sample on two of three feeds with 1 of 7 bootstrap
   passes. FTM passes the most gates and is one market, one block, and fails its own control there.
2. **A plateau is the only thing all five have.** 73–100% of perturbed cells profitable, and not
   one of them clears a control on a majority of blocks. The neighbourhood test cannot see a
   regime, which is exactly what the shape column says these five are sitting in.
3. **Cost is no longer the binding objection.** The five survive 2x. The binding objection is that
   an out-of-sample mean of +0.05 to +0.32 percent of price per trade, on 87 to 702 trades, is not
   separable from a matched null.
4. **Nothing here is ready to trade unsupervised.** Two come closest and for opposite reasons.
   V56's CVD exhausted-sellers gate clears its control on the one block it was not built on
   (p 0.005) — and that is n=87, one market, a CVD that is a proxy because no feed here carries
   aggressor delta, and it grew out of sample. IBS clears three separate reserved blocks
   (p 0.001 / 0.031 / 0.028) and fails four, on two indices over an overlapping calendar, with the
   worst shape in the table. Each is a footing; neither is a result.

## 9. What would move it

More reserved blocks, not more strategies. Every gate that failed here failed for want of an
independent block to clear: V56 and FTM have one each, and IBS's three passes are three blocks of
two indices over an overlapping calendar. A second instrument with a genuinely disjoint era — the
`EURUSD` era, or a real futures feed covering 2016–2022 for NQ — is worth more than any further
search.
