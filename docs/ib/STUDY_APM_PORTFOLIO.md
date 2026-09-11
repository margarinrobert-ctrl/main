# APM portfolio construction, and the sizing number the script displays

## 1. THERE IS NO PORTFOLIO HERE, AND THAT IS THE FINDING

Three legs exist — NQ, US100, US30 — and they are not three.

Daily P&L correlation, zero-filled over the 764 shared sessions (2022-12-27 to 2025-12-11):

| | NQ | US100 | US30 |
|---|---|---|---|
| **NQ** | 1.000 | **0.715** | 0.106 |
| **US100** | 0.715 | 1.000 | 0.152 |
| **US30** | 0.106 | 0.152 | 1.000 |

**On the 70 sessions where BOTH NQ and US100 traded the correlation is +0.950, with the same sign
94.3% of the time.** The zero-filled 0.715 understates it, because the legs often fire on different
days; when they both fire they are the same trade. That is `STUDY_US100`'s finding reproduced at
the strategy level — those two feeds are the same index at a 0.9995 daily return correlation.

One principal component explains **58.6%** of the variance of the three and two explain **90.6%**.

## 2. Every combination containing US30 is worse than the best single leg

Sharpe, research -> locked (the split is NQ's 65/35 session cut, applied to the shared index):

| book | research | locked | ret/DD research | ret/DD locked |
|---|---|---|---|---|
| NQ only | 1.115 | **1.570** | 2.311 | **3.971** |
| US100 only | **1.857** | 0.421 | 12.172 | 0.562 |
| **US30 only** | **-0.434** | **-0.535** | -0.389 | -0.445 |
| NQ + US100 (same index) | 1.582 | 1.125 | 5.124 | 1.759 |
| NQ + US30 | 0.636 | 1.029 | 1.545 | 1.196 |
| US100 + US30 | 1.219 | 0.103 | 4.543 | 0.102 |
| all three equal | 1.286 | 0.872 | 4.704 | 1.295 |
| inverse-vol (fitted on research) | 1.121 | 0.764 | 4.084 | 1.015 |

**US30 loses on both blocks**, so every book containing it is dragged down: US100 alone goes 1.857
-> 1.219 research and 0.421 -> 0.103 locked when US30 is added at equal weight. Inverse-volatility
weighting, fitted honestly on the research block only, does not rescue it (1.121 / 0.764) — it just
weights a losing leg less.

`STUDY_SEMIVARIANCE` measured this trap directly and it reproduces exactly: **a decorrelated leg
still has to have an edge.** Adding a coin-flip at |rho| 0.25 there raised net profit, cut Sharpe
3.73 -> 3.23 and more than doubled drawdown.

**Recommendation: run ONE instrument.** The two legs that make money are the same index, and the
one that is genuinely uncorrelated does not make money.

## 3. The sizing number

`contracts = floor( account x risk% / (stop distance x point value) )`. The only open question is
risk%, and it is set by the **drawdown**, not the per-trade edge — a stop is the loss on one trade
and the account has to survive a run.

Measured at the shipped 3.0N stop:

| market | n | median ATR14 | stop distance | $ per contract | longest losing run | worst 20-trade run, in stops |
|---|---|---|---|---|---|---|
| NQ | 104 | 25.57 pts | 76.70 pts | $153 | 7 | **-4.29** |
| US100 | 308 | 21.54 | 64.63 | $65 | 8 | **-2.32** |
| US30 | 267 | 39.93 | 119.80 | $120 | 10 | **-13.59** |

Translated to accounts, at 0.5% risk per trade:

| market | $50,000 account | contracts | worst measured 20-trade run |
|---|---|---|---|
| NQ | $250 budget | 1 | -$658 = **1.3%** of the account |
| US100 | $250 | 3 | -$449 = **0.9%** |
| US30 | $250 | 2 | -$3,256 = **6.5%** |

**0.5% is the defensible default; 1% is already aggressive**, because at 1% those worst runs roughly
double to 2.6% / 1.8% / 13%. The p99 Monte Carlo drawdown from `STUDY_APM_VWAP` is about **$2,400
per MNQ**, which is the number to size against rather than the realised one.

US30 is the outlier on every risk measure here — a worst run of 13.6 stops against NQ's 4.3 — **and
it is also the leg that loses on both blocks.** Those two facts belong together.

## 4. What ships in the script

- **A live stop-loss plot.** Once a position exists the level is
  `position_avg_price -/+ stopAtr x liveAtr`, exactly where the broker emulator has it. On the FILL
  BAR `position_avg_price` is still `na`, so the PLANNED level computed from the signal close is
  drawn instead — otherwise the one bar a reader most wants the stop is the one bar it is missing.
  **A defect worth recording, because it is a class and not a typo.** The first build cleared the
  planned level with `if pos == 0: plannedStop := na`, and `pos` is read at the TOP of the bar. On
  the signal bar the entry has been submitted but has not filled, so `pos` is still 0 — the guard
  wiped the level a few lines after the decision block wrote it, and the stop line could not appear
  until the FILL bar, one bar late. **A "flat" test that runs before the fill is not a flat test.**
  Fixed with a bar-scoped `justArmed` flag plus `strategy.opentrades == 0`, so the level clears only
  when genuinely flat with nothing pending. Same family as the `strategy.position_avg_price` trap:
  both are questions asked one bar before the answer exists.
- **A sizing panel** showing the stop price, the stop distance in points and dollars per contract,
  the contract count at the configured account and risk%, the dollars at risk, and what the worst
  measured 20-trade run would cost at that size as a percentage of the account. It warns when the
  account is too small for one contract.
- **`applySize` defaults OFF.** Every measured number in the header is one contract; switching it on
  makes position size vary with ATR, which changes the equity path, the drawdown and the
  compounding, and the Strategy Tester report is then not comparable to any of them.

`research/apm/run_p4.py`.
