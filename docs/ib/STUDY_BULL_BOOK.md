# The most profitable bullish intraday system this data supports — and why it isn't trend-following

Asked for: the most profitable bullish **trend-following** intraday strategy the accumulated work
can produce. What follows is the most profitable bullish intraday book I can build and defend.
It is not a trend-following book, and the first section says why, because that gap is the finding.

## Trend-following was tested here, repeatedly, and it fails

| study | result |
| --- | --- |
| `STUDY_TREND_BRIEF.md` | 200 EMA + ADX + crossover does not survive. The slope condition is **redundant** — identical trade list. **ADX contributes negatively**: removing it raises Sharpe. |
| `STUDY_TREND_PULLBACK_2.md` | 5,723,136 combinations. **127 rules beat a time-matched control on research; 0 survived the holdout**, against 6.4 expected by chance. Marked do-not-re-run. |
| `STUDY_MA_LAG.md` | MA type is barely a choice — at matched lag SMA/LMA/EMA overlap **89.5–97.3%** of triggers with win rates inside one point. |
| `STUDY_RULE_ANATOMY.md` | "EMA rising" is **algebraically the same rule** as "close > EMA". The classic trend rule set is one rule wearing several names. |
| this study | `close > MA` in every flavour: **52.5–53.5% win at $8–16/trade**. |

So a textbook bullish trend rule is not a candidate. What follows is what actually pays.

## The five legs

All long, all 30-minute, one contract each, entered and exited independently.

| leg | rule | stop | flatten | what it actually is |
| --- | --- | ---: | --- | --- |
| M1 | ATR>1.2× mean AND bullish engulfing AND upper wick>60% | 1.0×ATR | 15:00 | reversal / exhaustion bar |
| M4 | body<30% AND first hour AND ATR>1.8× mean | 4.0×ATR | 16:00 | **day filter**, held to the close |
| V1 | ATR>1.2× mean AND BB width<0.7× mean AND close<5-bar low | 3.0×ATR | 15:00 | **mean reversion** — failed breakdown |
| V2L | **EMA20 < EMA50** AND bullish engulfing (body≥20%) AND 09:30–11:30 | 2.5×ATR | 15:00 | **counter-trend** — requires a downtrend |
| RW | RSI28>65 AND RSI28 rising AND lower wick>30% AND 09:30–16:00 | 4.0×ATR | none | momentum continuation |

**Two of the five are explicitly counter-trend.** V2L only fires when EMA20 is *below* EMA50 — in
a downtrend — and V1 buys a close at a 5-bar **low** after a volatility squeeze. One is a day
filter, one a reversal bar, and only RW is momentum. Calling the result "trend following" would
describe what was asked for, not what is here.

## Individually

| leg | n | win % | net $ | research $/t | locked $/t |
| --- | ---: | ---: | ---: | ---: | ---: |
| M1 | 85 | 71.8 | 3,331 | 33.1 | 50.3 |
| M4 | 88 | 73.9 | 9,005 | 98.6 | 111.8 |
| V1 | 249 | 59.8 | 8,935 | 37.7 | **31.6** |
| V2L | 139 | 67.6 | 9,575 | 54.7 | 91.9 |
| RW | 117 | 69.2 | 19,570 | 148.2 | 220.1 |
| *V3 (15m, second chart)* | *158* | *65.8* | *10,981* | *34.2* | *139.4* |

Each beat its own matched control before being included. V1 is the only leg with the right shape.

## The book

Daily-P&L correlation is the reason to combine: **mean |ρ| 0.098, max 0.438.**

| | legs | net $ | Sharpe | max DD $ | MAR |
| --- | ---: | ---: | ---: | ---: | ---: |
| best single leg (RW) | 1 | 19,570 | 2.72 | 956 | 20.5 |
| **the five 30m legs — one chart** | 5 | **50,416** | **4.79** | **1,068** | **47.2** |
| all six, adding V3 on a 15m chart | 6 | 61,398 | 4.77 | 1,319 | 46.5 |

Combining raises Sharpe from 2.82 (best leg) to 4.79 without raising drawdown proportionally.
That is the one free lunch available — and the one a correlation matrix alone will talk you into
wrongly, since **a decorrelated leg still has to have an edge** (`STUDY_SEMIVARIANCE.md`).

## Validation of the combined book

| test | result |
| --- | --- |
| bootstrap, 100,000 paths | **P(net < 0) = 0.000%**, 5th percentile net $46,998 |
| permutation drawdown | median $2,085, p95 $3,178, **realised $1,319 — luckier than median** |
| walk-forward, 6 folds, no re-fitting | **6/6 profitable**, $86–194/day |
| risk of ruin (50% of $25,000) | 0.0% at 1%/trade, 0.1% at 4% |
| Pine vs research trigger sets | 86/86, 94/94, 310/310, 172/172, 303/303 — **zero on either side** |

## The caveat that matters most

**The book earns more per day on the locked block ($118.8) than on research ($100.7).** That is
the wrong shape — an edge decays out of sample, it does not appear there — and it is inherited:
five of the six legs carry the same flag individually. Read **$100.7/day** as the forward
expectation and treat Sharpe 4.79 as the most flattering number here, not the most reliable.

The realised drawdown is also on the lucky side of its own permutation distribution ($1,319
against a median $2,085), so **$1,068 is not a drawdown to plan around**.

And every number is one instrument, one regime, 88% of it a rising market. No second market was
reachable from this environment, so the cross-market question stays unanswerable rather than
guessed at.

## Shipped

`pine/bullBook/BULL_BOOK_30m.pine` — the five 30-minute legs on one chart, with the configuration
lock, per-leg no-overlap enforced through `strategy.opentrades`, per-leg flatten times, and both
caveats above stated in the header and on an on-chart banner. V3 needs a separate 15-minute chart.
