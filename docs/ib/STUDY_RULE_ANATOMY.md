# Every timing rule is a weighted average of price changes — and eight of ours are duplicates

Source: Valeriy Zakamulin, *Trend-Following* series (Alpha Architect), Parts 1–8, plus *Pitfalls
When Assessing Market-Timing Strategies*, *Daily vs. Monthly Trend-Following Rules*, *Time Series
Momentum: Theory and Evidence*, *Optimal Trend Following with Transaction Costs*, and
*Trend-Following Rules in Two-State Regime-Switching Models*.

Thirteen articles arrived at once. Rather than skim all of them, this study takes the one claim
that is **sharp, falsifiable, and consequential here** — Part 4's anatomy result — tests it to
machine precision, and then applies it to this repository's own condition pool. The rest of the
series is summarised at the end, because most of it corroborates findings this branch already has.

## The claim

Part 4 argues that **every** moving-average timing rule computes a weighted moving average of
price *changes*, and that rules differ only in that weighting function π. From that, three exact
equivalences follow:

1. **SMA change of direction ≡ Momentum(n)**
2. **LMA(n−1) change of direction ≡ Price − SMA(n)**
3. **EMA change of direction ≡ Price − EMA(n)**

Identity 3 is easy to see once written down: with `EMA_t = αP_t + (1−α)EMA_{t−1}`,

```
EMA_t − EMA_{t−1} = α (P_t − EMA_{t−1})
P_t − EMA_t       = (1−α)(P_t − EMA_{t−1})
```

Both are **positive multiples of the same quantity**, so as *rules* — which read only the sign —
they are identical on every bar, at every α, forever.

## Tested

30-minute MNQ closes, 35,471 usable bars, sign agreement bar by bar:

| n | identity | bars | **disagreements** |
| ---: | --- | ---: | ---: |
| 10–100 | SMA(n) change of direction == Momentum(n) | 35,471 | **0** |
| 10–100 | LMA(n−1) change of direction == Price − SMA(n) | 35,471 | **0** |
| 10–100 | EMA(n) change of direction == Price − EMA(n) | 35,471 | **0** |

All three exact, at every window tested. The second needed the article's own **n−1** convention;
at LMA(n) it lands at 96.98–99.74%, which is close enough to be mistaken for "approximately true"
and is in fact an off-by-one. Getting that right is the difference between a demonstrated identity
and a hand-wave.

## What it costs this repository

If two rules are the same rule, a condition pool containing both is counting a hypothesis it does
not have. Audited:

| pool | conditions | **identical pairs** | >99% agreement |
| --- | ---: | ---: | ---: |
| `factory` (`alpha_factory2`) | 115 | **8** | 0 |
| `ladder` (`alpha_ladder`) | 198 | **14** | 14 |

The `factory` duplicates, in full:

| | |
| --- | --- |
| `close>EMA20` | `EMA20 rising` |
| `close>EMA50` | `EMA50 rising` |
| `close>EMA200` | `EMA200 rising` |
| `close>Donchian20 high` | `close>20-bar high` |
| `close<Donchian20 low` | `close<20-bar low` |
| `Stoch K<20` | `Williams%R<-80` |
| `Stoch K>80` | `Williams%R>-20` |
| `ROC20>0` | `20-bar momentum>0` |

**The first three are Identity 3, found sitting in our own pool as six separate conditions.** The
Stochastic/Williams pairs are the other well-known algebraic identity (both rescale
`(close − low_n)/(high_n − low_n)`). The Donchian and ROC pairs are naming duplicates.

A duplicate pair costs twice:

* it makes a **two**-condition rule look like a three-condition rule, and a drop-one test on it
  will report a condition contributing nothing — which reads as "this condition is useless" when
  the truth is it was never a second condition;
* it inflates the configuration count. 115 nominal → **107 effective**, 7.0%; for a 3-condition
  search the count is overstated by **24.1%** (ladder: 198 → 184, 24.6%).

**The direction of that error is conservative.** An overstated configuration count only makes a
Bonferroni threshold *stricter*, so no published p-value here is too generous because of it. It is
still wrong, and worth knowing before quoting "N configurations searched" as a diversity claim.

**No shipped strategy is affected.** All nine — V1–V4, V2L, M1–M4 — were checked pair by pair
against the duplicate list and none contains a redundant pair.

## Following on from `STUDY_MA_LAG.md`

Part 2 showed MA *type* is nearly a non-decision at matched lag (89.5–97.3% trigger overlap).
Part 4 extends it: rule *type* collapses too. Between them, two axes that look like independent
degrees of freedom — which MA, which rule — are substantially one axis, and the thing that
actually varies is the **change-weighting function**, i.e. roughly the lag.

## The rest of the series, briefly

Read but not separately tested; most corroborates what this branch already found the hard way.

| source | claim | our position |
| --- | --- | --- |
| *Pitfalls When Assessing Market-Timing Strategies* | Prices rise over the long run, so **any** rule generating buy signals often enough looks profitable; the monthly market return was positive 62% of the time. | This is the matched-control / base-rate principle, independently arrived at. CLAUDE.md: "A win rate means nothing without its base rate." |
| Part 6, *Testing Profitability* | The **choice of split point** can decide whether trend-following appears to work; an out-of-sample test made MOM(2) look highly profitable and it would have lost money. | Same reason the split here is fixed at 65% and stated up front rather than chosen. |
| Part 7, *Trading the S&P 500* | Short selling does not pay; over short-to-medium horizons trend-following is **more likely to underperform** than outperform; lower mean returns, but a lower probability of loss over two years. | Matches `STUDY_TREND_BRIEF.md` and `STUDY_TREND_PULLBACK_2.md`, both negative. |
| Part 8, *Various Markets* | Trend rules significantly beat buy-and-hold in the **small-cap index only**. | Consistent with one-instrument results here being weak. |
| *Daily vs. Monthly Rules* | **No evidence** trend-following performs better on daily than monthly data. | Consistent with the timeframe axis being weak here. |

## What is not established

None of this makes any trend rule work. The identities are algebra and hold regardless of data;
the pool audit is a fact about our own code. The one number that could move a future result — the
24% multiplicity overstatement — moves it in the conservative direction, so nothing already
published needs revising.
