# Is `ATR falling AND close<5-bar low AND Tue` fit for live trading?

Ten tests, run on the exact script. Reproduce with `python3 research/test_suite.py` after pointing
it at this rule, plus `research/oner_pick.py` for the search-width figures.

## Scorecard

| # | Test | Result | |
|---|---|---|---|
| 1 | Out-of-sample | research $2,257 / 63.3% win → locked $2,182 / 70.4% win | **PASS** |
| 2 | Walk-forward | 7 of 7 folds positive; 6 of 6 periods; 13 of 13 rolling windows | **PASS** |
| 3 | Monte Carlo & bootstrap | P(net<0) = 0.0%; 95% CI on net [$2,051, $6,794] | **PASS** |
| 4 | Statistical significance | per-trade t = 3.49, p = 0.0008; win-rate null +20.1 pts, p = 0.0033 | **PASS** |
| 5 | Data-snooping | deflated Sharpe 0.000 against 4,057,200 trials; SPA p = 0.368 | **FAIL** |
| 6 | Cost & slippage | profitable at 4× modelled cost and +4 ticks per fill | **PASS** |
| 7 | Execution realism | true 1-minute path +1%; entry timing spread **42%**; refill −10% | **WARN** |
| 8 | Regime consistency | positive above and below EMA200, in all three volatility terciles, 6 of 6 sixths | **PASS** |
| 9 | Sample adequacy | **87 trades, 24 a year, 27 in the holdout** | **FAIL** |
| 10 | Is Tuesday real? | see below | **FAIL** |

Eight of ten pass, including every test people usually stop at. The two that fail are the two
that decide it.

## Test 10 is the answer

The same rule, one weekday at a time:

| day filter | trades | win % | net | research | locked | PF |
|---|---|---|---|---|---|---|
| Mon | 77 | 49.4 | $124 | $731 | −$606 | 1.03 |
| **Tue** | **87** | **65.5** | **$4,439** | $2,257 | $2,182 | **2.60** |
| Wed | 84 | 47.6 | $1,010 | $357 | $653 | 1.22 |
| Thu | 76 | 40.8 | $1,235 | $215 | $1,020 | 1.35 |
| Fri | 47 | 44.7 | $473 | −$1,370 | $1,843 | 1.13 |
| **no day filter** | **390** | **49.2** | **$6,044** | $2,103 | $3,941 | 1.31 |

**Deleting the Tuesday condition earns more money — $6,044 against $4,439 — on four and a half
times the trades.** Tuesday is not selecting good trades; it is discarding 303 of them, most of
which were profitable in aggregate. The suite's drop-one test found the same thing independently:
removing `Tue` is worth **+$1,605**, while removing `close<5-bar low` costs $6,652 and removing
`ATR falling` costs $727. Two conditions are load-bearing. The third is a filter fitted to which
weekday happened to be luckiest.

And the excess collapses with it:

```
with Tue      87 trades   65.5% win   base 45.4%   excess +20.1   p 0.0033
without Tue  390 trades   49.2% win   base 45.2%   excess  +4.0   p 0.0498
```

## Test 5 is why that matters more than it looks

Inside L4's own geometry bucket — short, 2.5×ATR, flat 16:00, 60-minute bars — there are 170,460
strategies with enough trades to score:

```
research win >= 55.0%    954 (0.56%)   ->  235 held on locked  (25%)
research win >= 58.0%    366 (0.21%)   ->   67 held            (18%)
research win >= 60.0%    139 (0.08%)   ->   33 held            (24%)
research win >= 63.3%     10 (0.01%)   ->    1 held            (10%)
```

L4 scored 63.3% on research. It is **one of ten** that got that far, and **the one** that held.
That is not nothing — but "the single survivor of a ten-way extreme cut, taken from 170,460
candidates in one bucket of 4,057,200" describes a lottery winner as accurately as it describes
an edge, and 12.5% of the rule space contains a weekday condition, so 31,650 rules had the chance
to find a lucky day.

## Test 9, quietly

87 trades. **24 a year.** 27 of them in the holdout. At that rate a full year of live trading
produces less evidence than the holdout already contains, and you would not know whether it was
working until 2028.

## Verdict

**No. Do not trade this script as written.**

The Tuesday filter is a fitted artifact, and it is the source of everything that looks impressive
— the 65.5% win rate, the 2.60 profit factor, the $420 drawdown. Remove it and the rule is honest
but ordinary.

What survives is the two-condition version: **`ATR falling AND close<5-bar low`, short, 2.5×ATR,
1R, flat 16:00, 60-minute bars.** 390 trades, 49.2% against a 45.2% base, +4.0 points of excess,
PF 1.31, $6,044 net with $3,941 of it on the locked block. That is a real but marginal signal at
p = 0.0498 — a p-value with no multiple-testing correction on it, which after 4 million trials is
worth nothing on its own. It has a defensible sample and no fitted weekday.

If any version of this goes near a live account, it is that one, at minimum size, as a test of
whether the effect exists at all.

## What would change the answer

The 2018–2021 period, which this repository's data does not reach and a TradingView chart does.
Run the two-condition version there. If a short 1R rule that fires 107 times a year still clears
its base rate through 2018's Q4, the 2020 crash and the 2022 bear, that is evidence no amount of
in-sample testing can produce.
