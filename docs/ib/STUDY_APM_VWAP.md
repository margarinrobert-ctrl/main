# STUDY_APM_VWAP -- the ATR-phase-momentum session-VWAP strategy, tested for live trading

The strategy under test is the NinjaScript `ATR_NORMALIZED_PHASE_MOMENTUM_MULTI_SESSION_VWAP_v2`,
ported to Pine as `pine/apm/APM_SESSION_VWAP_strategy.pine`. On 10-minute decision bars the phase
oscillator is EMA3 of `100 * (close - EMA21) / (3 * ATR14)`; a cross above +100 is a long intent
and a cross below -100 a short intent; an intent is taken only when the signal bar's close sits
within 2.5 ATR14 of the session HLC3-volume VWAP and the fill (the next open) lands inside
09:30-11:00 New York; the position is held to the 16:00 cash close or an opposite cross; one
contract, no stop, no target. Threshold and denominator are one axis -- phase > 100 with a
denominator of 3 is `close - EMA21 > 3 x ATR14` -- and the grid below sweeps that distance.

Engine: `research/apm/apm_core.py`, the Pine's order model as one numba walk per configuration
(5.6 ms), reproducing the transliteration `research/apm/apm_sim.py` trade for trade (104 trades,
same counts on every path). Battery: `research/apm/apm_run.py`, outputs in `results/apm/`.

Feeds and blocks: NQ_1m built into exact UTC buckets at 5/10/15 minutes, 2022-12-26 to
2025-12-11, research = the first 65% of sessions, locked = the rest; US100 and US30 15-minute CFD
files 2016-2025 with TICK volume (research < 2022, validation 2022-23, test 2024+); XAUUSD 15m
2022-06 to 2026-08 (research < 2025) on the gold profile shifted to 08:15/09:45/13:30 so the
clocks sit on a 15-minute bar. The source's `StartTradingDate` (2020-02-03, set for its own MNQ
file) is not applied, so the CFD research blocks hold five years. Costs per side are half the
session-tier spread plus entry slippage from `research/scalp/core.COSTS`, plus commission on NQ;
NQ dollars are MNQ ($2 a point).

## 1. As specified

| feed | block | n | win | PF | pts/trade | Sharpe (all sessions) | max DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ 10m | research | 70 | 58.6% | 1.62 | +24.0 | +1.12 | 564 |
| NQ 10m | locked | 34 | 67.6% | 4.12 | +62.8 | +2.77 | 243 |
| NQ 10m | all | 104 | 61.5% | 2.12 | +36.7 ($7,633) | +1.68 | 564 ($1,128) |
| NQ 5m | research / locked | 69 / 35 | 58% / 74% | 2.06 / 2.63 | +35.0 / +72.9 | +1.62 / +1.90 | 605 / 852 |
| NQ 15m | research / locked | 67 / 41 | 69% / 56% | 2.05 / 1.13 | +34.1 / +7.0 | +1.60 / +0.21 | 520 / 1,154 |
| US100 15m | research | 176 | 57.4% | 1.53 | +10.8 | +0.80 | 638 |
| US100 15m | validation | 70 | 64.3% | 1.89 | +34.5 | +1.37 | 478 |
| US100 15m | test | 62 | 58.1% | 1.31 | +15.3 | +0.45 | 1,324 |
| US30 15m | research / validation / test | 148 / 68 / 51 | 49% / 46% / 51% | 0.88 / 1.19 / 1.06 | -7.9 / +16.4 / +4.6 | -0.22 / +0.37 / +0.13 | 2,168 / 1,957 / 1,150 |
| XAUUSD 15m | research / locked | 46 / 26 | 48% / 69% | 1.11 / 3.44 | +0.5 / +12.0 | +0.17 / +1.45 | 59 / 60 |

Exits are the cash close: 101 of 104 on NQ, 281 of 308 on US100, all 72 on gold. The opposite-cross
exit fires 2-7 times per feed and the reversal branch never fired anywhere. The short side earns
more than the long on every index feed (NQ +46 vs +30, US100 +31 vs +6 a trade). Top-5% share of
net: 48% NQ, 88% US100, 79% gold. Longest losing run 3-9.

**The shape is the wrong one on three of four feeds.** NQ locked PF 4.12 against research 1.62,
gold 3.44 against 1.11, US100 validation 1.89 against research 1.53. The constants are the source's
and were not chosen here, so this is not selection -- it is a regime: 2022-2024 flatters the rule
on every feed. NQ 15m and the US100 test block (PF 1.31, 2025 at -27.4 a trade on 29 trades) show
the decay a real edge is supposed to show.

## 2. Matched controls -- what the rule beats and what beats it

Three nulls, 2,000 draws each, matched on the block's trade count, identical exits (opposite cross
of the same oscillator, cash close), one position at a time.

| feed / block | rule | RANDOM bar, coin-flip side | SAME DAYS, same side, random bar | RULE'S bars, coin-flip side |
| --- | ---: | ---: | ---: | ---: |
| NQ 10m research | +24.0 | ctl -2.1, p **0.054** | ctl +29.0, p 0.855 | ctl -0.1, p **0.051** |
| NQ 10m locked | +62.8 | ctl -0.4, p 0.062 | ctl +72.2, p 0.851 | ctl +2.7, p **0.001** |
| NQ 15m research | +34.1 | ctl -2.2, p **0.013** | ctl +46.0, p 0.994 | ctl -1.4, p **0.007** |
| NQ 15m locked | +7.0 | ctl -0.5, p 0.407 | ctl +37.3, p 1.000 | ctl -1.6, p 0.447 |
| US100 research | +10.8 | ctl -2.3, p **0.019** | ctl +15.0, p 0.998 | ctl -2.9, p **0.012** |
| US100 validation | +34.5 | ctl +0.5, p **0.032** | ctl +47.2, p 1.000 | ctl +3.6, p **0.034** |
| US100 test | +15.3 | ctl -1.6, p 0.230 | ctl +30.5, p 0.996 | ctl -2.2, p 0.262 |
| US30 research / validation / test | -7.9 / +16.4 / +4.6 | p 0.585 / 0.283 / 0.411 | p 1.000 / 1.000 / 1.000 | p 0.490 / 0.259 / 0.410 |
| XAUUSD research / locked | +0.5 / +12.0 | p 0.270 / **0.027** | p 0.939 / 0.598 | p 0.350 / **0.020** |

Three things are in that table.

**The direction call is the asset.** Keep the rule's bars and flip a coin for the side and the
excess is +24 / +60 on NQ and +14 / +31 on US100, at p 0.05 / 0.001 and 0.012 / 0.034. Inverting
the side in §3 loses on every block of every index feed. Always-long is NEGATIVE on NQ research
and on all three US100 blocks, so this is not drift wearing a signal (the branch's usual finding).

**The entry timing is a cost, not an edge.** Given the rule's own sessions and its own side, a
random fill bar inside 09:30-10:50 earns MORE than the rule on every block of every feed
(excess -4 to -35 a trade, p 0.85-1.00). Measured directly: at its fill the rule has already
chased a median **3.97 ATR** of a day that travels **4.99 ATR** in its direction (US100: 3.96 of
4.89), and captures a median 1.20 ATR of it. The oscillator identifies the day and the side; by
the time it says so, 80% of the move is gone. `STUDY_ATME`'s "chasing a breakout is the most
destructive choice in the search", from a new indicator. **Read this control as an upper bound,
not as a tradeable alternative**: it is handed the rule's side, which the rule only learns at the
cross, so a random bar drawn before the cross is entering on information the rule did not yet
have. The realisable route to an earlier entry is a smaller distance threshold, and §4 shows that
is WORSE (2.0 ATR: +9.9 / +21.8 against 3.0 ATR: +21.3 / +39.8 on NQ) -- the confirmation is worth
more than the chase costs. The lateness is the price of the direction call, not a defect to fix.

**The VWAP filter is real on the two feeds that work.** Against a random filter keeping the same
share of intents (300 draws): NQ 10m keeps 66.7%, rule +36.7 vs random-filter median +20.7,
**p 0.007**; US100 keeps 77.8%, +17.1 vs +9.5, **p 0.010**; NQ 15m p 0.153, US30 0.133, gold
0.063. Note the mechanism (§3): the band is also the clock.

## 3. Anatomy -- one component at a time (pts/trade, research | locked; US100 research | validation | test)

| variant | NQ 10m | US100 15m |
| --- | ---: | ---: |
| as specified | +24.0 / +62.8 | +10.8 / +34.5 / +15.3 |
| VWAP filter off | +13.3 / +32.9 (n 101 / 55) | +3.6 / +26.6 / +10.1 |
| VWAP 1.5 ATR | +41.2 / +76.1 (n 27 / 12) | +23.8 / +41.3 / **-17.1** |
| VWAP 4.0 ATR | +13.7 / +38.8 | +9.8 / +30.9 / +8.7 |
| opposite-cross exit off | +24.3 / +62.8 | +10.3 / +32.9 / +18.7 |
| always long | -12.9 / +14.7 | -10.7 / -19.1 / -5.2 |
| always short | +9.0 / -18.6 | +6.7 / +15.1 / +1.1 |
| side inverted | -27.9 / -66.7 | -14.7 / -38.5 / -19.3 |
| entries to 10:30 | +33.4 / +69.7 (n 60 / 31) | +16.8 / +31.6 / +6.7 |
| entries to 12:00, 14:00, 15:50 | identical to 11:00 | +8.5 / +29.2 / +7.7 and flat after |
| distance 2.0 ATR | +7.4 / +8.6 (n 166 / 94) | -2.5 / +17.4 / +8.3 |
| distance 4.0 ATR | +15.5 / -1.4 (n 20 / 10) | +24.4 / +21.9 / +24.8 (n 57 / 26 / 18) |
| raw phase (no EMA3) | +9.3 / +43.8 | +4.9 / +5.6 / +15.9 |
| zero cost / 2x / 3x | +26.0 / +22.0 / +20.1 research | +12.7 / +8.8 / +6.8 research |

**The entry window is inert, because the VWAP band is the clock.** Widening entries to 15:50
changes nothing on NQ: 72 more intents arrive after 11:00 and every one is rejected. The share of
crosses within 2.5 ATR of VWAP is 85% in the 09:00 hour, 51% at 10:00, **3% at 11:00 and 0%
after** -- a 3-ATR excursion from the EMA21 is inside the band only while the VWAP is a few bars
old. The 09:30-11:00 window in the source is a restatement of what the filter already does.

The opposite-cross exit is inert (it fires on 2% of trades). The reset detector and the frozen
calendar are inert on these feeds. Costs are not the obstacle on NQ (PF 1.62 -> 1.44 at 4x); US30
was null before costs and dies at 2x.

## 4. The parameter grid

Six axes, 4,320 cells per timeframe: EMA {13, 21, 34} x ATR {10, 14, 20} x oscillator EMA
{1, 2, 3, 5} x distance {1.5 .. 4.0 ATR} x VWAP band {1.5, 2.0, 2.5, 3.0, off} x last entry
{10:30, 11:00, 12:00, 14:00}. NQ at 5/10/15 minutes = 12,960 cells; US100 and US30 at 15.

| | NQ (10,149 scorable) | US100 (3,927) | US30 |
| --- | --- | --- | --- |
| profitable on research | 89.1% | 67.5% | see §4b |
| profitable on the later blocks | locked 94.9% | validation 95.3%, test 81.9% | |
| corr(research mean, later mean) | Pearson **+0.524**, Spearman +0.505 | test +0.314 / +0.346; validation-test -0.033 | |
| default cell | +24.0 / +62.8 | +10.8 / +34.5 / +15.3 | -7.9 / +16.4 / +4.6 |
| one-rung box (729 cells) | 98% / 99% profitable, mean +24.9 / +46.6 | 84% / 97% / 89%, +9.3 / +23.2 / +21.3 | |
| top decile by research | +40.8 -> locked **+57.8** (95% profitable) vs population +30.5 | +24.3 -> test **+23.0** (79%) vs +15.4 | |

**This is the first grid on this branch whose research ranking transfers.** Pearson +0.524 on NQ
and +0.31 on US100 against the -0.04 to +0.2 the branch usually measures, and the research top
decile beats the population on the later block on both feeds. The marginals say why: the axes
that matter move the SAME way on every block.

- **distance**: monotone up to 3.5 ATR on both NQ blocks (+3.4 -> +23.8 research, +15.7 -> +44.8
  locked) and on US100 research (-0.5 -> +13.9); the source's 3.0 is one rung inside the optimum.
- **VWAP band**: tighter is better on every block of both feeds (NQ 1.5: +18.7 / +34.6 against
  off +10.1 / +23.7; US100 1.5 best on all three blocks) -- and 1.5 ATR fails the US100 test
  block as a single cell (§3), so read the marginal, not the cell.
- **last entry**: 10:30 best on every block of both feeds; the window is doing nothing after that.
- **oscillator EMA**: 5 > 3 > 2 > 1 on NQ both blocks; the raw phase is the worst setting.
- **EMA**: 13 best, 34 worst, on both feeds; **ATR length** is inert.
- **timeframe** (NQ): 5m +14.3 / +35.7, 10m +15.0 / +31.4, 15m +13.9 / +24.4.

Population first, as always: with 89% of the NQ grid profitable the top cell is the max of ~9,000
positive draws, and the top-10 rows are 32-40-trade cells. The top decile carrying to the locked
block is the evidence; no single cell is.

### 4b. US30 (rerun with the full history)

4,320 cells, 3,776 scorable: **58.9% profitable on research, 42.4% on validation, 19.7% on
test**; corr(research, test) **-0.339** Pearson; the research top decile (+26.1) reads validation
+12.9 and test **-50.0** (8% profitable). Every axis inverts on the test block -- distance 4.0
is the best research rung (+7.4) and the worst test rung (-40.9); the tightest VWAP band is the
best research rung (+6.1) and -19.3 on test. The one-rung box around the default is 51% / 64% /
**21%** profitable. On US30 the family is a nine-year null whose surface anti-predicts, which is
what the branch usually finds and what NQ and US100 did NOT show here. The instrument decides.

## 5. Walk-forward -- re-select the whole grid on a trailing window, read the next

Each fold picks the cell with the highest total net on the trailing window (30-trade floor)
and reads the next; the source's defaults are read on the same test windows.

| feed | folds | chosen cells, stitched OOS | defaults on the same windows | folds where the chosen cell beat the defaults |
| --- | ---: | ---: | ---: | ---: |
| NQ 10m (18m train / 6m test) | 2 | **+0.2** pts/trade on 199 | **+62.7** on 38 | 0 of 2 |
| US100 15m (24m / 12m) | 6 | **-1.7** on 591 | **+25.3** on 188 | 1 of 6 |
| US30 15m (24m / 12m) | 6 | +1.4 on 890 | +7.3 on 186 | 3 of 6 |

Walk-forward efficiency of the chosen cells runs -1.27 to +2.41 with a median near zero. The
optimiser picks fast, loose cells (distance 1.5-2.0, oscillator EMA 1, band 3.0 or off) that
trade three to five times as often, because total net on a two-year window rewards count, and
those cells earn nothing forward. **The source's constants beat every re-selected cell on the two
feeds that work.** Same finding as `STUDY_IBS_SESSION`: an author's fixed defaults are the best
cell the optimiser can find, and the way to lose the edge is to tune it.

## 6. Monte Carlo, cost stress, perturbation (NQ 10m, as specified)

| block | n | trade bootstrap P(mean<=0), 95% CI | day-block bootstrap | permutation drawdown: realised / median / p95 / **p99** |
| --- | ---: | --- | --- | --- |
| research | 70 | **0.052** [-5.1, +53.6] | 0.055 [-5.7, +53.5] | 564 (pct 0.38) / 617 / 988 / **1,205 pts = $2,410 per MNQ** |
| locked | 34 | 0.001 [+25.5, +101.6] | 0.000 | 243 (pct 0.68) / 208 / 347 / 425 |
| all | 104 | 0.001 [+12.9, +60.4] | 0.000 | 564 (pct 0.52) / 555 / 892 / 1,100 |

The research CI includes zero. The realised research path was neither lucky nor unlucky (38th
percentile). Size for the p99: about $2,400 per MNQ contract on the research block, 2.1x the
realised drawdown. Bootstrap endpoint on research: median +1,657 pts, 5th percentile -36.

Cost stress: research PF 1.68 / 1.65 / 1.62 / 1.58 / 1.55 / 1.49 / 1.44 at 0 / 0.5 / 1 / 1.5 / 2 /
3 / 4x the per-side cost. Perturbation of one axis at a time by about 20%: every cell positive on
both blocks; the weakest are EMA 25 (locked +39.1, PF 1.81), distance 3.6 (research +5.6, PF 1.11)
and VWAP 3.0 (locked +47.7). The surface is smooth, which §4 already said.

## 7. Clusters

600 NQ 10m cells with 60+ trades, 731 trading days: pairwise daily-P&L correlation median 0.446,
**47 clusters at rho >= 0.7** (largest 59 cells), **26 principal components for 90% of variance**.
The grid is genuinely diverse -- not one strategy in 4,320 hats -- which is why the marginals in
§4 are informative rather than a restatement of one rule.

## 8. Funded evaluation, MNQ on a $50,000 account

Day-block bootstrap over EVERY session (a session without a trade is a zero day; the rule trades
on 14% of sessions), 3,000 paths each, `research/vbt/prop.simulate`.

| rules | contracts | P(pass) | P(bust) | P(timeout) |
| --- | ---: | ---: | ---: | ---: |
| 6% target, 4% trailing, 2% daily, 60 sessions | 1 / 2 / 4 / 8 | 0.5% / 12.3% / 38.7% / 51.0% | 0.1% / 9.3% / 41.2% / 47.0% | 99.4% / 78.4% / 20.1% / 1.9% |
| same, 120 sessions | 1 / 2 / 4 / 8 | 6.9% / 41.8% / 48.6% / 49.5% | 0.2% / 17.6% / 49.6% / 50.5% | 92.9% / 40.6% / 1.8% / 0.0% |
| 4% target, 120 sessions | 1 / **2** / 4 | 25.5% / **61.5%** / 61.0% | 0.3% / 15.1% / 38.1% | 74.2% / 23.4% / 0.9% |
| 6% target, 250 sessions | 1 / 2 / 4 | 40.4% / 70.2% / 50.8% | 1.5% / 23.7% / 49.2% | 58.1% / 6.1% / 0.0% |

One contract almost never busts and almost never passes: 35 trades a year at +$73 is $2,600 a
year against a $3,000 target. Two contracts is the only sizing where P(pass) clears 60% on any
rule set, and it busts 15-24% of the time. From four contracts up every rule set is a coin flip.
`STUDY_MEGA_144K`'s finding again: an evaluation is a distribution problem, and a low-frequency
rule with a positive mean is a timeout problem before it is anything else.

## 9. Verdict for live trading

What passed:

1. It beats a random entry with its own exits on NQ 10m research (p 0.054), NQ 15m research
   (0.013), US100 research (0.019) and US100 validation (0.032).
2. The direction call carries information: the rule beats a coin flip on its own bars at p 0.05 /
   0.001 (NQ) and 0.012 / 0.034 (US100), and inverting the side loses everywhere.
3. It is not drift: always-long is negative on NQ research and on every US100 block.
4. The VWAP filter beats a random filter of the same selectivity on NQ 10m (p 0.007) and US100
   (p 0.010).
5. The parameter surface is smooth, the one-rung box is 98% / 99% profitable, and the research
   ranking transfers (rho +0.52 NQ, +0.31 US100) -- the first grid here that does.
6. Costs are not the issue on NQ (PF 1.44 at 4x). Drawdown is bounded and known: p99 $2,400 per MNQ.

What failed or stays attached:

1. **The research-block CI includes zero** (P(mean<=0) 0.052 on 70 trades) and the reserved NQ
   read is 34 trades. The whole NQ history is three years and one regime.
2. **The most recent block is the weakest everywhere it exists**: US100 test p 0.230 with 2025 at
   -27 a trade; NQ 15m locked PF 1.13; and the locked-beats-research shape on NQ 10m, gold and
   US100 validation says 2022-2024 flattered it.
3. **US30 is null over nine years** (PF 0.88 / 1.19 / 1.06, every control p > 0.25), so it is not
   a general index effect; gold's research block is null (+0.5 a trade).
4. **The entry is late by construction**: a random bar on the same day with the same side beats
   the rule on every block of every feed. The rule buys the last fifth of a five-ATR day. That is
   where the improvement lives, and it is a different strategy.
5. **Walk-forward re-selection loses to the defaults** (§5), so there is nothing to tune, and
   anyone who tunes it will make it worse.
6. 30-40 trades a year per market, with 48-88% of net in the top 5% of trades: six months of
   forward trading will not distinguish it from zero, and a bad quarter is expected.
7. Funded-account rules: one MNQ cannot pass, two pass 42-70% and bust 15-24%.

**Recommendation.** Not live-ready on this evidence; forward-test it. Run the shipped Pine in
paper or with one MNQ on NQ, USIndex profile, defaults untouched, for at least 40 trades (about
14 months), and judge it against the numbers above: research mean +24 a trade, 58% win, a
drawdown of up to $2,400 per contract. If traded, 1-2 MNQ per $50,000, never re-optimised, and
with the knowledge that the short side and the 09:30-10:30 fills carry the result. What would
actually move the verdict is not another parameter search but more independent history: the
direction call is worth +24 to +60 a trade, and the only evidence for it outside the author's own
2020-2026 development window is US100 2016-2021 (passes) and US30 (null).

Research tooling for education and analysis -- not financial advice.

## 10. Reverse-engineering: what the direction call is, without the indicator

`research/apm/apm_edge.py`, `results/apm/edge.txt`. The null throughout is a coin flip for the
side on the rule's own fill and exit bars, 2,000 draws -- the test that isolates the direction
call from everything else.

**It is not the opening drive.** If the mechanism were "a large move from the 09:30 open
continues to the close", a rule reading nothing but the signed distance from the 09:30 open would
reproduce it. It does not, at any threshold, on either feed:

| rule (exit 16:00) | NQ research | NQ locked | US100 research | validation | test |
| --- | ---: | ---: | ---: | ---: | ---: |
| APM as specified | +24.0 on 70, p 0.050 | +62.8 on 34, p 0.000 | +10.8 on 176, p 0.018 | +34.5, p 0.015 | +15.3, p 0.279 |
| drive >= 3.0 ATR from the 09:30 open, first hour | +5.5 on 247, p 0.194 | +9.8 on 148, p 0.234 | -1.0 on 503, p 0.407 | +7.2, p 0.203 | +10.5, p 0.135 |
| drive ladder 0.5 .. 5.0 ATR | -8.4 to +5.5, no rung below p 0.16 | | -2.1 to +3.0, no rung below p 0.14 | | |
| first 30 minutes' sign, enter 10:00 (the published intraday momentum) | +0.6 on 479, p 0.348 | -0.3, p 0.457 | +0.4 on 1,096, p 0.188 | +3.4 | +1.5 |
| first 60 minutes' sign, enter 10:30 | +10.8, p 0.009 | -2.3, p 0.503 | -2.9, p 0.651 | +14.1, p 0.009 | +13.6, p 0.044 |

93 of the APM's 104 NQ trades are also 3-ATR-drive days on the same side -- but the drive rule
takes 395 such days and earns nothing on them. The APM is selecting the quarter of big-drive
days that continue, and the drive's size is not how.

**It is the conjunction of two things, neither of which works alone.** The displacement is
measured from an EMA21 of 10-minute bars, which is a 3.5-hour average anchored in the pre-market;
it must be sustained through a 3-bar smoothing; and it is taken only while the session VWAP still
sits within 2.5 ATR of price.

| variant | NQ research | NQ locked | US100 research | validation | test |
| --- | ---: | ---: | ---: | ---: | ---: |
| both: smoothed phase AND the VWAP band (the rule) | **+24.0, p 0.050** | +62.8, p 0.000 | **+10.8, p 0.018** | +34.5, p 0.015 | +15.3, p 0.279 |
| smoothed phase, band off | +13.3 on 101, p 0.133 | +32.9, p 0.043 | +3.6 on 226, p 0.163 | +26.6, p 0.042 | +10.1, p 0.317 |
| raw phase (no EMA3), band on | +9.3 on 144, p 0.137 | +43.8, p 0.016 | +4.9 on 352, p 0.054 | +5.6, p 0.282 | +15.9, p 0.142 |
| raw phase, band off | +0.3 on 185, p 0.401 | +29.0, p 0.060 | +1.6 on 422, p 0.191 | +10.2, p 0.150 | +0.5, p 0.434 |
| 3-ATR drive from the open + the same VWAP band | +7.8 on 218, p 0.153 | +11.0, p 0.207 | +1.2 on 446, p 0.206 | +6.3, p 0.221 | +9.0, p 0.173 |

Remove either half and the research pass is gone on both feeds; remove both and it is a coin
flip (+0.3, +1.6). Bolt the VWAP band onto the plain drive and nothing happens (+7.8, +1.2). The
anchor matters: the EMA21 carries the overnight, so "3 ATR from it" is a displacement against
where the market spent the night, not against where it opened. The band matters because it is a
clock (§3): the displacement is admitted only in the hour when the session's own average price
has not yet moved away with it. The smoothing matters because the excursion must hold for three
bars rather than print once.

Stated for the library: **a sustained (3-bar) displacement of at least 3 ATR from a pre-market-
anchored average, taken in the first hour while the session VWAP is still within 2.5 ATR of
price, continues to the cash close.** Worth +24 / +63 a trade on NQ and +11 / +35 / +15 on US100
over a coin flip on the same bars; null on US30 over nine years and on gold's research block; the
plain drive, the published first-half-hour momentum and the first-hour sign are all null or
inconsistent on the same data.

## 11. Feature engineering on the rule's trades

Seventeen causal features at the signal bar in eight declared families (gap and drive
composition, timing, the rule's own magnitudes, participation, volatility, prior-day context,
trend, candle), each split at its research median, each half scored against 2,000 random subsets
of the same size, on NQ (70 research trades) and US100 (176). A feature is carried only if the
SAME half beats the random filter at p <= 0.10 on BOTH research blocks; survivors are read once
on the later blocks.

| feed | tests | at p <= 0.10 | expected by chance | the ones that passed |
| --- | ---: | ---: | ---: | --- |
| NQ research | 34 | 2 | 3.4 | drive straightness high (0.033), VWAP distance low (0.091) |
| US100 research | 34 | 5 | 3.4 | fill in the first bars (0.002), oscillator excess high (0.002), VWAP distance low (0.038), prior-day range high (0.038), daily trend against (0.068) |

**One feature agrees on both feeds and it fails the later blocks.** VWAP distance below its
median: NQ research +43.9 vs base +24.0 (p 0.091), US100 research +21.4 vs +10.8 (p 0.030); read
once, NQ locked +68.8 vs +62.8 (p 0.377), US100 validation +41.3 vs +34.5 (p 0.348), US100 test
**-15.6 vs +15.3 (p 0.872)**. It is also the rule's own admission variable restated, so a tighter
band is what it proposes, and the grid already showed that cell failing the US100 test block. The
two features that came closest on US100 -- an earlier fill and a larger oscillator excess -- are
the mechanism's own magnitudes, not new information, and they miss the NQ gate (0.111, 0.104).
Nothing from the prior day, the overnight, participation, the trend or the candle separates the
trades on either feed. 74% of the rule's signal bars are already beyond the prior session's high
or low, and the half that is not earns MORE on NQ and less on US100, so E4 does not transfer to
this base either. Feature engineering ships nothing; the rule is its own best filter.
