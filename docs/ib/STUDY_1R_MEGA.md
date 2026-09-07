# 27,386,100 combinations, five phases, four versions

`oner_mega.py` → `oner_phase23.py` → `oner_phase45.py`. Every phase selects on the research block;
the locked block is read at Phase 4 and once only.

## The funnel

```
PHASE 1  GENERATE   253,575 rules x 6 stops x 3 flatten times x 2 directions x 3 timeframes
                                                                    27,386,100 combinations
                    enough trades in both blocks, research-profitable    5,750,599  (21.0%)

PHASE 2  GATE       no calendar condition                                4,734,944
                    win rate >= 58% with positive excess over its own
                      geometry's population base rate                      312,223
                    every subset also beats its base (coherence)            42,774

PHASE 3  TUNE       best of 18 stop x flatten geometries per rule,
                      chosen on research                                    30,026 rule/direction

PHASE 4  VALIDATE   collapse rules sharing 2+ conditions                       150
                    >=1 condition beats a random filter of the same
                      selectivity ON THE LOCKED BLOCK                           34
                    and profitable there                                        34

PHASE 5  SELECT     decorrelated below |rho| 0.25                                4
```

**Phase 4 is the one that does the work.** 150 in, 34 out. The other 116 look identical on every
conventional metric and have no condition that beats a coin of the same selectivity on data it
was not chosen on.

## The four

Every one has **3 of 3 conditions proven** — the first time that has happened on this branch.

| | rule | tf | dir | stop | trades | win % | base | excess | PF | research | **locked** | maxDD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **V1** | `ATR>1.5x mean AND BB squeeze AND close<20-bar low` | 30m | long | 3.0×ATR | 86 | **70.9** | 48.3 | **+22.6** | 2.64 | $4,160 | **$3,333** | $1,177 |
| **V2** | `EMA20>EMA50 AND bearish engulfing AND first hour` | 30m | short | 1.0×ATR | 120 | 63.3 | 43.6 | +19.7 | 1.74 | $1,892 | $805 | $456 |
| **V3** | `close>Donchian20 high AND outside bar AND first hour` | 15m | long | 4.0×ATR | 83 | 65.1 | 47.3 | +17.8 | 1.97 | $2,648 | **$2,696** | $816 |
| **V4** | `Stoch K<20 AND close<50-bar low AND lower wick>50%` | 15m | short | 3.0×ATR | 80 | 61.3 | 42.6 | +18.7 | 1.68 | $957 | $2,018 | $1,033 |

Locked p-values, each condition against a random filter keeping the same number of trades:

```
V1   ATR>1.5x mean 0.002   BB squeeze 0.008        close<20-bar low 0.029
V2   EMA20>EMA50   0.044   bearish engulfing 0.072 first hour       0.033
V3   close>Donchian20 high 0.082   outside bar 0.041   first hour   0.050
V4   Stoch K<20    0.055   close<50-bar low 0.021   lower wick>50%  0.043
```

### As a book, one contract each

```
369 trades   65.0% win at 1R   net $18,509   locked $8,852
largest pairwise correlation +0.16
book Sharpe 2.43   best single 1.62   book maxDD $1,396
```

Two longs and two shorts, on two timeframes, from four different condition families — momentum
compression, engulfing reversal, breakout continuation and oversold exhaustion. The book Sharpe
of 2.43 against a best single of 1.62 is diversification doing its job, and the +0.16 correlation
cap is why.

## What is still wrong with all four

**Trade counts are small.** 80–120 trades over three years, 27–40 a year. A full year live
produces less evidence than the locked block already holds.

**Data-snooping is unfixable on this data.** 27.4 million combinations were searched. The
deflated Sharpe against that trial count is ~0 for anything here, and no further testing on the
same three years can change it. Phase 4 is the strongest available *substitute* — it asks whether
each condition still concentrates good trades on data it was not chosen on — but it is not a
correction for 27 million trials.

**Phase 3 tuned the geometry on research.** That is a search on top of a search. Its saving grace
is that the median rule beat its base rate in 16–18 of 18 geometries, so the choice sits on a
plateau rather than a spike — but the reported stop width is still the best of 18.

**One regime.** 2022-12 → 2025-12, one instrument, a market that rose 89%. Two of the four are
short, which is better than the 12-of-14 long tilt of the previous book, but it is still one
regime.

## The honest ranking

**V1** is the strongest: highest win rate (70.9% against a 48.3% base), highest profit factor,
its weakest condition clears p = 0.029, and it holds $3,333 of $4,160 on the locked block. **V3**
is next and is the only one that earns *more* on the locked block than on research.

Trade them at one contract each. `STUDY_SIZING_PORTFOLIO.md` swept 173,340 sizing rules and none
beat one contract out of sample; §9 of the protocol says use AVA across legs if you want the
volatility adjustment, and it belongs at book level, not trade level.
