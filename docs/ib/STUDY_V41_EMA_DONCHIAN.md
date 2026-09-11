# V41 — EMA 13/48 cross as first signal, Donchian as confirmation

**103,680 nominal cells, 62,208 effective, three markets, and the answer is: the EMA cross beats
its own no-EMA twin in exactly 3 of 6 cross-market cells, where chance is 3.0.**

## The structure, and two things counted honestly

The brief asks for a **sequence** — the EMA cross fires, then a Donchian breakout confirms it —
which is a different rule from "EMA state AND breakout". Both are in the grid as an axis, and the
grid carries its own ablation: `mode = cross, win = 0` degenerates to *Donchian alone*, so every
treated cell has a matched control built in.

| | |
| --- | --- |
| nominal cells | 103,680 |
| **effective distinct configurations** | **62,208** |
| built-in Donchian-alone control cells | 10,368 |

The gap is an **inert axis**: under `mode = state` there is no recency requirement to widen, so the
five window rungs are one cell. A multiplicity correction computed against 103,680 would be
correcting for tests that were never run.

ATR here is **Wilder's RMA(20)**, matching the source script and the Turtle definition — a
deliberate departure from this branch's usual `ema(TR, n)`.

## 1. Grid shape, before any ranking

```
research PF > 1.00: 72.5%    > 1.20: 34.1%    > 1.50: 11.2%
median research PF 1.110     max 3.751
research-to-locked PF correlation: Pearson -0.391   Spearman -0.388
top-100 mean research PF 2.781  ->  mean LOCKED PF 0.733
```

The correlation is not merely absent, it is **strongly negative**. Ranking on research
anti-predicts the holdout, and the top 100 goes from PF 2.78 to a loss.

Timeframe shows it cleanly: 60m is the **best** research marginal (PF 1.374, +$37.76) and the
**worst** locked one (0.876, −$26.59), while 15m and 30m are the reverse. The top 100 is **84%
60m** — the ranking concentrated on precisely the timeframe that fails.

## 2. The signal-level correlation: the EMA is largely inside the breakout

| condition | % of all bars | % of **breakout** bars | lift |
| --- | ---: | ---: | ---: |
| EMA13 > EMA48 (state) | 36.9% | **82.6%** | 2.24 |
| cross within 5 bars | 4.6% | 16.8% | 3.64 |
| cross within 10 bars | 8.3% | 25.1% | 3.03 |
| cross within 40 bars | 26.8% | 52.6% | 1.96 |

(NQ 15m research; 30m and 60m within a point.)

**A breakout already passes the EMA state filter 82.6% of the time.** As a confirmation it removes
a sixth of the signals and cannot add much — the same mechanism `STUDY_V16_MOMENTUM` measured for
RSI on breakouts (94.7% pass rate). The *cross-within-5-bars* form is genuinely selective (16.8%),
which is why it is the only form the top of the grid selects.

## 3. The ablation, matched pairwise

Every `(tf, don_e, don_x, stop, tp, gate)` geometry against its own Donchian-alone twin — 51,216
matched pairs, nothing but the EMA condition differing:

| | EMA helps on research | EMA helps on **locked** |
| --- | ---: | ---: |
| all pairs | 42.0% (−$2.66/trade) | **50.0% (+$0.67/trade)** |
| mode `cross` | 36.5% (−3.99) | 54.7% (+2.98) |
| mode `state` | 63.5% (+2.57) | **31.2% (−8.16)** |

**50.0% is exactly chance.** And the two modes invert in *opposite directions* between blocks —
`state` helps on research and hurts on locked, `cross` does the reverse. That is the signature of
noise, not of two competing mechanisms.

Cost of the confirmation: it halves the trade count (198 vs 395).

## 4. The three candidates, locked read once

| | research | **NQ LOCKED** |
| --- | --- | --- |
| TOP (60m, 21/48, cross win 5, Don 30/10, 2.5N, ADX≥20) | PF 3.363, +$144.09, n 33 | **PF 0.647**, −$47.37, n 21 |
| CONSENSUS (top-100 mode; win 10) | PF 3.189, +$140.60, n 37 | **PF 0.957**, −$6.23, n 27 |
| **THE BRIEF** (13/48 fixed; 60m, win 40, Don 55/20, 1.5N, CHOP≤45) | PF 2.444, +$122.01, n 67 | **PF 0.691**, −$44.96, n 42 |

All three fail. Deflated Sharpe fails at **N = 1** for all three, so multiplicity is not even the
binding problem.

## 5. Robustness

**Perturbation** — the TOP cell's neighbours score 1.531–1.971 against its own 3.363. It is a
spike, not a ridge.

**Walk-forward, 6 folds:** 5/6, 4/6, 5/6 positive — which looks fine and is not. **Fold 5 is
catastrophic in all three** (PF 0.205, 0.174, 0.101) and folds 5–6 are the recent block. A
"5 of 6" whose one failure is the most recent fold is a decay curve, not a robustness result.

**Bootstrap on locked:** P(mean ≤ 0) = 0.762, 0.557, 0.824.

**Cost stress:** essentially flat (locked PF 0.647 → 0.600 at 3× the round turn). Not a cost
problem — the trades are few and large.

## 6. Cross-market — and the control that decides it

US30 and US100 had no part in the search (re-uploaded and verified byte-identical to the registry:
US30_LONG `24dcf2e1c7ba398f`, US100_LONG `c449dddfbc06a943`).

| market | candidate | n | PF | vs **its own no-EMA twin** | matched control p |
| --- | --- | ---: | ---: | ---: | ---: |
| US30 | TOP | 130 | 1.027 | **−$52.43** (twin 1.154) | 0.606 |
| US30 | CONSENSUS | 169 | 1.058 | **−$39.13** (twin 1.154) | 0.561 |
| US30 | BRIEF | 311 | 1.249 | **−$11.37** (twin 1.280) | 0.324 |
| US100 | TOP | 142 | 1.526 | +$25.30 (twin 1.175) | 0.070 |
| US100 | CONSENSUS | 179 | 1.666 | +$36.30 (twin 1.175) | **0.035** |
| US100 | BRIEF | 322 | 1.532 | +$16.41 (twin 1.334) | **0.045** |

**The EMA beats its own twin in 3 of 6 cells — chance is exactly 3.0 — and the mean contribution is
−$4.15/trade.** The split is perfectly by market: it *hurts* in all three US30 cells and *helps* in
all three US100 cells. A filter whose sign is decided by which index you run it on is a
market-specific artifact, not a mechanism.

Two cells clear the matched control (both US100, p 0.035 and 0.045) — but the top cells' daily
returns correlate at **median ρ 0.820, with #1 and #4 at ρ 1.00 (identical trades)**, so those two
are close to one test, not two.

## 7. vectorbt as a second engine

Signal sets agree everywhere (trade-count ratio 0.92–1.00, one cell exact at 130/130). P&L does
not:

| | my engine | vectorbt | ratio |
| --- | ---: | ---: | ---: |
| US30 TOP | +$13.23/trade | **+$303.50** | **22.9×** |
| US30 CONSENSUS | +$26.52 | +$301.26 | 11.4× |
| US100 TOP | +$39.59 | +$118.59 | 3.0× |
| US100 BRIEF | +$44.15 | +$109.32 | 2.5× |

The entire gap is one convention: when the ATR stop and the 10-bar channel exit fall inside the
same bar, mine takes the stop. **At 60 minutes with a 2.5N stop and a 10-bar exit channel that
collision is common, and it is worth up to 23× the reported edge.** V38 measured the same effect at
2.1× on 30-minute bars; the coarser the bar and the tighter the exit channel, the more of the
"result" is the tie-break rule. Read the convention before the P&L.

## Verdict

The structure the brief asks for is buildable and was built. It does not work:

1. **The EMA cross is worth nothing on average** — 50.0% of 51,216 matched pairs on the holdout,
   3 of 6 cross-market cells, mean −$4.15/trade, and a sign that flips by market.
2. **It is largely redundant with the trigger** — 82.6% of breakout bars already pass EMA13>EMA48.
3. **The grid anti-predicts** — research→locked ρ = −0.391, top-100 PF 2.781 → 0.733.
4. **What survives is what always survives here**: no take profit (70% of the top 100 against a 33%
   population share), and a regime gate.

## Files

| file | what it does |
| --- | --- |
| `research/v41/v41seq.py` | the sequenced entry, the grid, the inert-axis and control-cell flags |
| `research/v41/run_v41.py` | the sweep, grid shape, marginals, pairwise ablation, top-100 consensus |
| `research/v41/run_v41b.py` | signal-level correlation, three selections, the locked read, strategy-return correlation |
| `research/v41/run_v41c.py` | perturbation, walk-forward, bootstrap, cost stress, cross-market, DSR curve |
| `research/v41/run_v41d.py` | the matched and ablation controls on the fresh markets, and vectorbt |
| `docs/ib/v41_*.txt` | raw output |
