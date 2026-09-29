# Designing the S3 forward test before it starts

A forward test with no pre-committed decision rule is not a test, it is watching. Two things have
to be settled in advance: how long 40 trades takes, and what 40 trades can distinguish. The second
is arithmetic and it is disappointing.

The three hypotheses the test has to tell apart, all in deflated dollars on one MNQ contract:

| | per trade |
|---|---|
| **H_locked** — the rule earns what the out-of-sample year earned | **+$22.10** |
| **H_research** — the rule earns what the longer research block earned | **+$4.44** |
| **H_null** — no edge; the rule earns what the matched control earns | **-$3.10** |

## How long

The rule fires **191 times a year = 0.76 a session**, so 40 trades is **53 sessions, about 2.5
months**. The out-of-sample year averaged 12.8 trades a month and its slowest month was 3. Budget
roughly three months, and do not stop early on a good run.

## 40 TRADES CANNOT SEPARATE THE THREE HYPOTHESES

Per-trade standard deviation on the locked block is **$160**.

| n | standard error | 95% CI half-width |
|---|---|---|
| **40** | **$25** | **±$50** |
| 80 | $18 | ±$35 |
| 150 | $13 | ±$26 |
| 300 | $9 | ±$18 |
| 600 | $7 | ±$13 |

The three hypotheses span **$25.20 end to end** — inside a single standard error at n=40. Trades
needed to show the locked expectation differs from zero at 95%: **202**. To show the research
expectation differs from zero: **5,002**.

Simulated directly, resampling 40 trades 20,000 times from each population:

| hypothesis | p05 | p25 | median | p75 | p95 | P(ends in profit) |
|---|---|---|---|---|---|---|
| H_locked ($22.10) | -759 | +190 | +872 | +1,554 | +2,575 | **81%** |
| H_research ($4.44) | -863 | -278 | +145 | +605 | +1,341 | **59%** |
| H_null (control) | -1,255 | -612 | -158 | +320 | +1,078 | **41%** |

**A DEAD RULE FINISHES 40 TRADES IN PROFIT 41% OF THE TIME, AND A RULE WITH THE FULL OOS EDGE
FINISHES IN LOSS 19% OF THE TIME.** So a profitable 40-trade run is weak evidence and a losing one
is weak evidence. Anyone who sizes up after a good 40 trades is acting on a coin flip with a lean.

## The one statistic 40 trades can move: the win rate

The average win and average loss are near-identical ($114 against -$118), so the edge IS the win
rate — and a proportion needs far fewer observations than the mean of a fat-tailed P&L.

- driftless break-even for this geometry: **51.9%**
- research block: 52.4%
- out-of-sample year: 60.3%

Observing 60.3% and asking whether it beats break-even:

| n | 95% interval | verdict |
|---|---|---|
| 40 | [44.9%, 74.3%] | contains break-even |
| 80 | [49.4%, 70.5%] | contains break-even |
| **150** | **[52.3%, 67.9%]** | **excludes break-even** |

**150 trades is where the win rate becomes decisive** — about nine months at this rate.

## The pre-committed rule, stated before the test starts

Under a dead rule (win rate at the 51.9% break-even), fewer than 16 wins in 40 happens 5% of the
time. So:

- **15 wins or fewer in 40 → STOP. Do not size it.**
- **27 wins or more in 40 → consistent with the OOS year. Extend to 150 before sizing.**
- **16 to 26 wins → UNDECIDED, and this is the likely outcome.** Keep going to 150 at minimum size.

Write this down before the first trade. Deciding the threshold after seeing the result is the same
error as selecting on the holdout, in miniature.

## What to record, and the two things that invalidate the test

Per trade: date, time (NY), side, entry, stop at entry, exit, **exit reason**, ATR at signal, P&L.
Exit reason matters most — the backtest's mix is roughly one third stopped and two thirds
trailed-or-flattened, and a live mix far from that means the port is not doing what the research
did, which is a different problem from the edge being absent.

Two things void the test:

1. **Discretionary skips.** One skipped loser flatters everything and there is no way to correct
   for it afterwards. Take every signal or stop the test.
2. **Changing any input mid-test.** If a setting changes, the trade count restarts at zero.

Blank log: `results/s310/forward_test_log.csv`.

## What this does not test

The forward window is one market and one regime, same as the backtest. It can catch a broken port,
a cost assumption that is wrong, or an edge that has already decayed. It cannot establish that the
rule generalises — only a second market can, and that still needs 1-minute US100 or US30 bars.

`research/s310/run_f1.py`.
