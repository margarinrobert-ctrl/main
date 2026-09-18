# 9.3 million strategies on a fresh instrument, and nothing that transfers

An independent discovery cycle on US100, sharing no selection history with anything else on this
branch. `research/us100_search.py`.

**Design.** The split is chronological and deliberately backwards from convenience: research is
**2016-11 → 2021-12** (59,454 30-minute bars nothing here has ever touched, spanning the 2018
selloff, COVID and the 2022 bear market) and the holdout is **2022-01 →** (44,239 bars). Every
previous search on this branch selected on NQ 2022–2025, so this cycle cannot inherit any of it.
Anything surviving is then checked on **NQ**, a third test on a different instrument again.

**Scale.** 191 conditions → 1,161,471 rules (1–3 conditions) × 8 variants (2 directions × 4
geometries) = **9,291,768 strategies**. Bonferroni for a single claim: **p < 5.4×10⁻⁹**.

## A mistake, and what fixing it was worth

The first run did not exclude calendar conditions, which CLAUDE.md bans outright — *"weekday and
month conditions partition the sample five or twelve ways and hand the search a free lottery."*
The damage was immediately visible: **"Fri" appeared 878 times in the top 10,000** by research,
and the sixth-best rule overall — `outside bar AND last hour AND Fri` — made **+$90.0/trade on
research and lost $110.9 on the holdout**.

Excluding the seven calendar conditions and re-running:

| research top-N | median holdout $/trade, **with** calendar | **without** |
| ---: | ---: | ---: |
| 100 | **−1.5** | **+28.3** |
| 1,000 | +12.9 | +27.1 |
| 10,000 | +15.0 | +17.4 |
| research/holdout correlation | 0.3357 | **0.3574** |

An independent replication of the repo's own finding, on a different instrument.

## The multiple-comparisons tax, measured

Calendar-free, 9.29M strategies, ranked on research only:

| research top-N | median research $/t | **median holdout $/t** | share holdout > 0 |
| ---: | ---: | ---: | ---: |
| **10** | 90.9 | **11.5** | 60.0% |
| 100 | 71.0 | 28.3 | 64.0% |
| 1,000 | 52.3 | 27.1 | 66.7% |
| 10,000 | 36.6 | 17.4 | 66.7% |
| 100,000 | 20.3 | 12.6 | 68.5% |

**The very top of the research ranking is the most overfit.** The top 10 decays from $90.9 to
$11.5 while the top 100–1,000 hold up at $27–28. Only 23.5% of all strategies are profitable on
research, so this search space is not drift-dominated the way the long-only NQ book sweep was.

The useful number is the **research/holdout correlation of 0.357** across 6.9M strategies: on this
data a backtest carries real but modest information about out-of-sample performance.

## What the search actually found

The dominant motif in the top 10,000 is unmistakable — **long, into a new low**:

| condition | appearances in top 10,000 |
| --- | ---: |
| `close < prior day low` | 1,511 |
| `midday` | 1,197 |
| `ATR > 1.8× mean` | 762 |
| `close < 100-bar low` | 535 |
| `close < 75-bar low` | 365 |

83% of the top 10,000 are long. Buying new lows in elevated volatility is **mean reversion /
failed breakdown** — structurally the same mechanism as the shipped V1 leg
(`ATR>1.2× mean AND BB width<0.7× mean AND close<5-bar low`), rediscovered independently on a
different instrument across a different era out of 9.3 million candidates.

On US100's own holdout the family does hold: median **+$20.1/trade, 60% profitable**.

## And it does not transfer

226 rules from that family, taken unchanged to NQ:

| | |
| --- | ---: |
| mean excess over base rate on NQ | **−3.9 points** |
| share with positive excess | **16%** |

The best of them individually: `close<session VWAP AND close<prior day low AND 20-bar momentum>0`
wins 48.5% against a 54.1% base — **5.6 points below random**. Not one of the top rules clears its
base rate on NQ by a meaningful margin.

Worth noting too: within US100 itself the "buy a new low" family (median $20.1, 60% profitable) is
no better than everything else in the top 2,000 (median $15.4, **68%** profitable). It dominates
the ranking without dominating the results.

## The asymmetry that matters

| direction | result |
| --- | --- |
| discovered on **NQ**, validated on **US100** | **2 of 5 survive** — V1 at p 0.0001, V2L at p 0.0050, excess essentially unchanged (`STUDY_US100.md`) |
| discovered on **US100** (9.3M search), validated on **NQ** | **nothing transfers** — mean excess −3.9, 16% positive |

The difference is not the instrument. The NQ-discovered legs passed matched controls, FDR
correction, threshold-neighbourhood checks and a held-out block before anyone looked at US100. The
US100 candidates are the top of a raw research ranking over 9.3 million, which is precisely the
object the whole apparatus exists to distrust.

**A 9.3-million-strategy search on six unseen years of a fresh instrument produced no edge that
survives a change of market.** That is the result, and it is consistent with every large search on
this branch: 5.7M trend-pullback combinations returned 0 survivors, 76,546 RSI configurations
returned 1, and 100,000 book assignments failed to beat the configuration already shipped.
