# V37 — the IFVG model as the source specifies it: three-timeframe order-flow alignment

**Verdict, first: it failed.** Not one of the 48 declared cells is profitable after costs on the
holdout, the source's own one-minute entry timeframe is negative on *every* block, and the only
family that looked alive on the training block — the 15-minute one — is **0 of 16 cells positive
out of sample**, at PF 0.768. Nothing is carried forward. Nothing ships.

## Why this is a separate study from V36

V36 tested `liquidity sweep → IFVG` and failed. The uploaded thread (`IFVG Strategy`, @zaruww,
15 pages) describes a **different model**, and the difference is the whole strategy:

| | V36 | the source |
| --- | --- | --- |
| trigger | a liquidity sweep of a session/pivot level | **order-flow alignment across M15, M5, M1** |
| entry timeframe | 5m and 15m | **M1** |
| entry | limit at the proximal IFVG boundary | **the confirming candle** after the inversion |

The FVG and IFVG definitions in the thread match V36's exactly — a bullish IFVG is a *bearish* FVG
that price has closed above, and the mirror for bearish — so that part needed no change. What
needed building was order flow.

## Making "order flow" objective without adding a parameter

The source's definition is: bullish order flow is "price respects bullish PD arrays and disrespects
bearish PD arrays", the mirror for bearish, and a range/neutral state is "a low probability
condition that you need to avoid."

Disrespecting a bearish FVG — closing through it — **is** a bullish inversion. So order flow on a
timeframe is taken here as **the polarity of the most recent inversion on that timeframe**. That
follows directly from the definition already in use for the IFVG itself, introduces no threshold,
and leaves a genuine NEUTRAL state (before any inversion) which is excluded rather than defaulted
to a side. Measured: the states run 49.6/50.3 bull/bear on M15 and 50.0/50.0 on M5, with neutral
under 0.01% — so alignment is close to a fair two-coin filter, and it keeps **28.8%** of M1
inversions, against 25% for two independent fair coins.

CISD is described in the thread and is **not** implemented, deliberately. The source uses it to
confirm the same order-flow shift the inversion already marks ("a Change in State of Delivery and
inversion confirms an order flow shift"); adding it as a second reading of one event would
double-count. Recorded as untested rather than silently dropped.

`research/v37/ofa.py`. Every FVG is knowable at the close of its third candle, every inversion at
the close of the candle that closes through it, and higher-timeframe state is mapped to 1-minute
bars **by the last completed higher bar** — a 1-minute bar never reads a forming 15-minute bar.
Un-inverted FVGs expire after 500 bars on their own timeframe, so a 1-minute gap from three days
ago cannot set today's order flow.

## The constraints in force

The user's standing constraints applied throughout: **intraday only** — entries 09:30–15:30 New
York, a hard flatten at 16:00 — and *proven* means **clears a matched control at p ≤ 0.05 AND holds
out of sample**. Costs are the real MNQ stack at ×1.44. One live order; an unfilled limit holds the
lock until it expires. Every exit resolved on the true 1-minute path, stop first when a stop and a
target sit inside the same minute.

Split 60/20/20 by trading day over 1,048,575 1-minute NQ bars, 767 days. Everything below is read
on TRAIN; the holdout was read once.

## Phase 1 — the source's model on its own timeframe (`run_v37.py`)

32 pre-declared cells: 8 geometries (market vs. limit entry × 1.0/1.5 ATR stop × 1.5R/2.0R target)
× 4 model variants (alignment on/off × confirmation entry on/off). All 32 printed.

```
share of the 32 cells profitable in dollars: 0.0%   with PF > 1.10: 0.0%
mean $/trade over all cells -4.78   best -3.68   worst -5.99
```

**Zero of 32.** The best cell in the grid loses $3.68 a trade.

### It is not an execution problem — but it is a cost problem

`CLAUDE.md` requires the zero-cost variant before blaming execution. Run again at zero cost:

```
share of the 32 cells profitable GROSS: 56.2%   mean $/trade -0.00   mean PF 1.003
the round turn is worth +4.78 $/trade here
```

**Mean gross PF 1.003.** The setup is a coin flip before costs, and the round turn is $4.78 against
a mean gross edge of zero. That is the fourth-and-fifth-time shape this branch has recorded: *"a
one-bar scalp is arithmetically dead here, and the IC says so before any rule is written"*
(`STUDY_V13_MA_REGIME`), *"the intraday scalping constraint is what fails, replicated four times
now"*.

### The source's two claims, as ablations

| claim | ON | OFF | delta |
| --- | --- | --- | --- |
| alignment across M15/M5 is required | −4.46 | −5.09 | **+0.63** |
| enter on the confirming candle, not the inversion | −4.86 | −4.69 | −0.17 |

The alignment claim has the **right sign and it replicates**: +0.63 net, +0.31 vs −0.32 gross, and
on the holdout the ordering holds in both confirm settings (align ON −1.52/−2.27, align OFF
−2.68/−3.22). It is a real, small, consistent effect — worth about **+0.6 per trade against a
$4.78 round turn**. That is the entire finding and it is not enough to trade.

The confirmation-entry claim is worth nothing, in either direction, on any block.

The train-selected cell fails its matched control at **p = 0.080**, and the 1,000-draw day-block
bootstrap puts P(mean ≤ 0) at **1.000**.

## Phase 2 — is the model dead, or is the one-minute constraint dead? (`run_tf.py`)

The same rule, unchanged, at three entry timeframes, each aligned to the two next higher ones
(1m → 15m/5m as the source specifies; 5m → 60m/15m; 15m → 240m/60m). The barrier scales with the
**entry timeframe's own ATR** — stopping a 15-minute setup at 1.5× the *one-minute* ATR is a
different strategy, not the same one on a slower chart.

```
 etf  cells   net $/t   net PF   prof%   gross $/t  gross PF  gross prof%  round turn
   1     16     -4.39    0.769    0.0%       +0.38     1.025        87.5%       +4.77
   5     16     -3.06    0.917    0.0%       +1.69     1.053        93.8%       +4.75
  15     16     +3.04    1.063   75.0%       +7.72     1.173       100.0%       +4.68
```

The round turn is the *same* $4.7 at every timeframe; only the barrier grows. Gross PF rises
monotonically 1.025 → 1.053 → 1.173, and the net sign flips at 15 minutes. On TRAIN alone this is
exactly the shape of a real edge being uncovered by a widening barrier.

It is not one. On TRAIN the best 15-minute cell scores **+13.71/trade, PF 1.276, and clears its
matched control at p = 0.005** — and then:

```
      valid   n   99   $/trade    +2.38  PF 1.029
      oos     n   92   $/trade   -29.05  PF 0.642   matched control p = 0.995
```

## The family, not the cell

A single cell at 92 holdout trades says nothing on its own, so the whole family was read on all
three blocks — the branch's own rule, *"read what the top agree on, never the best row"*:

```
 etf   block  cells   trades   $/trade      PF  profitable   PF>1
   1   train     16    73080     -4.39   0.769        0.0%      0
   1   valid     16    22439     -3.37   0.875        0.0%      0
   1     oos     16    22848     -3.26   0.852        0.0%      0
   5   train     16    14696     -3.06   0.917        0.0%      0
   5   valid     16     5048     +3.23   1.047       62.5%     10
   5     oos     16     5233     -3.32   0.925       18.8%      3
  15   train     16     5417     +3.04   1.063       75.0%     12
  15   valid     16     1888     -3.03   0.974       56.2%      9
  15     oos     16     1857    -15.92   0.768        0.0%      0
```

**15-minute cells positive on all three blocks: 0 of 16.** Every one of the sixteen is negative on
the holdout, and the family mean falls from +3.04 to −15.92. The 5-minute family is positive on
validation and negative on both blocks either side of it — the same non-signal seen twice.

## What this study is worth keeping for

1. **Order-flow alignment is a real but tiny effect.** +0.6 per trade, correct sign on both blocks
   and in both gross and net terms, at every entry timeframe. It is the only part of the thread's
   model that survives measurement at all, and it is an order of magnitude under the cost floor.
2. **The confirmation entry is worth nothing**, which matters because it is the thread's stated
   answer to "price does not always retrace."
3. **The timeframe gradient is a cost gradient, not an edge gradient.** Gross PF 1.025 → 1.173
   across 1m → 15m with the round turn flat at $4.7: the barrier grew, the edge did not. Reading
   the net numbers alone would have called 15-minute IFVG a discovery. The zero-cost variant is
   what showed it was not — the eighth time on this branch that gate has earned its keep.
4. **A 264-trade cell clearing a matched control at p = 0.005 on train can be −29/trade out of
   sample.** The control gate is necessary and it is nowhere near sufficient at that trade count.

## Files

| file | what it does |
| --- | --- |
| `research/v37/ofa.py` | order flow as inversion polarity; FVG/IFVG detection (numba, age-bounded); HTF→1m mapping; entry-timeframe-scaled ATR |
| `research/v37/run_v37.py` | the source's model on M1: 32 declared cells, ablations, zero-cost pass, matched control, 1,000-draw MC, one holdout read |
| `research/v37/run_tf.py` | the same rule at 1m/5m/15m entry, and `family()` — every cell on every block |
| `docs/ib/v37_output.txt`, `v37_tf_output.txt`, `v37_family_output.txt` | raw output |
| `research/v37/v37_train.csv`, `v37_train_gross.csv`, `v37_tf.csv`, `v37_family.csv` | the cell tables |
