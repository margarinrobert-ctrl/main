# Validating the v6 spec at MNQ scale, and failing to improve it

Prompted by a live TradingView run on `MNQ1!`, 30m, Dec-2022..Dec-2025, which returned **183
trades, +$9,379.50, PF 1.58, 38.80% win, 2.59% max drawdown** — and, with TradingView's extra
script-execution modes enabled, **248 trades, −$16,246.50, PF 0.559, 31.05% win**.

## 1. The execution-mode collapse is a specification change, not fragility

The rule is `close > lastPH`: a break **confirmed at the bar's close**. TradingView's "On order
fill", "On history bar tick" and "On realtime bar tick" re-execute the script *during* the bar, so
`close` becomes the running price. Every intrabar poke through a pivot that reverses before the
close then fires a BOS, increments the run counter, and takes a trade.

| BOS definition | trades | net | PF | win % | maxDD |
| --- | --- | --- | --- | --- | --- |
| reported, "On bar close" only | 183 | +$9,380 | 1.58 | 38.80% | $2,626 |
| reported, all four ticked | 248 | −$16,247 | 0.56 | 31.05% | $16,614 |
| engine, close beyond the pivot | 147 | +$6,619 | 1.49 | 38.78% | $2,110 |
| engine, intrabar touch (repainted) | 153 | +$2,650 | 1.20 | 39.22% | $2,080 |

The ablation reproduces the direction — intrabar pivot detection alone costs 29 PF points — but
not the full collapse, because tick-level recalculation repaints the run counter, the EMA/ATR
filters and the position guards at the same time. **Only "On bar close" is compatible with this
rule.** The other modes are not a more realistic simulation; they are a different strategy.

The reported 183 trades at 38.80% win against the engine's 182 at 37.91% also closes the
Pine-versus-engine question: with the v6 gate the two agree on structure. The remaining P&L
difference is data (back-adjusted continuous contract, slightly different window).

## 2. Baseline — v6 spec, MNQ, $0.50/order

|  | trades | net | PF | win % | maxDD | Sharpe |
| --- | --- | --- | --- | --- | --- | --- |
| full sample | 147 | $7,060 | 1.53 | 40.1% | $2,074 | 2.28 |
| research block (first 65%) | 91 | $2,387 | 1.34 | 41.8% | $1,245 | 1.64 |
| **LOCKED block (final 35%)** | 56 | **$4,674** | **1.75** | 37.5% | $2,074 | **3.07** |

Out-of-sample is *better* than in-sample. That is unusual in this repository and is the single
strongest thing that can be said for this rule.

## 3. Six pre-specified improvements. None survives.

Every candidate was named before it was run and all are reported.

| variant | research Sharpe | LOCKED Sharpe |
| --- | --- | --- |
| no entries after 14:00 | **1.90** (best) | 3.21 |
| breakeven stop at +1.5R | 1.82 | 2.46 |
| baseline | 1.64 | 3.07 |
| breakeven stop at +1.0R | 1.32 | 2.67 |
| confirm buffer 0.10 ATR | 1.23 | 3.23 |
| confirm buffer 0.25 ATR | 1.16 | 2.87 |
| no entries before 11:00 | **0.63** (worst) | **3.70** (best) |

**Spearman rho = −0.429 (p = 0.34).** The research ranking carries no information about the locked
ranking — it is mildly *inverted*. The variant that looked *worst* in research is the *best* out of
sample. Selecting on the research block is not merely useless here; acting on it would have picked
the wrong rule.

No variant beats the baseline on **both** blocks. Every one of them is noise around it.

### A correction, because the first run of this table was wrong

The breakeven rows originally read 1.17 / 1.37, and were reported as the one consistent finding —
"a breakeven stop hurts". That was an artefact of the test harness, not a property of the strategy.
The implementation armed breakeven from bar *i*'s high and then tested bar *i*'s low against the
new stop, inside the same bar. That assumes the high came before the low, an intrabar ordering
nobody knows, and it scratches trades on the very bar they reach the target. Breakeven is now armed
for bar *i+1* and the resting stop is checked first.

Corrected, breakeven at +1.0R is fourth of seven on both blocks — mildly below baseline, and
indistinguishable from the rest of the noise. The claim that it "hurts" does not survive its own
bug fix. Note the direction of the error: the harness was biased *against* the variant being
tested, which is the direction that produces false negatives rather than false discoveries, but it
is a bug either way.

## 4. Monte Carlo — stationary block bootstrap, 5,000 paths, daily P&L blocks

| | p5 | p25 | median | p75 | p95 |
| --- | --- | --- | --- | --- | --- |
| net $ | 1,232 | 4,542 | **6,969** | 9,578 | 13,214 |
| max drawdown $ | 1,337 | 1,759 | **2,180** | 2,779 | 3,922 |
| Sharpe | 0.45 | 1.55 | **2.28** | 3.00 | 3.98 |

**P(net < 0) over a resampled three-year run = 2.3%.** P(drawdown exceeding twice the realised
$2,074) = 3.4%. The realised path is close to the median rather than a lucky tail.

## 5. Walk-forward with re-selection — it costs money

Six expanding folds, re-picking the best variant on each in-sample block:

| fold | picked | OOS | fixed baseline |
| --- | --- | --- | --- |
| 1 | breakeven at +1.0R | $613 | $1,236 |
| 2 | confirm buffer 0.25 | $702 | $763 |
| 3 | confirm buffer 0.25 | −$803 | $457 |
| 4 | confirm buffer 0.25 | −$955 | −$38 |
| 5 | no entries after 14:00 | $1,757 | $2,786 |
| 6 | no entries after 14:00 | $3,071 | $3,038 |
| **stitched** | | **$4,386** | **$8,242** |

Re-selection is worth **−$3,857**. It loses on four folds of six and never meaningfully wins.

## Conclusion

The honest answer to "improve it to the maximum profitability" is that **it cannot be improved by
searching, and this run measures the cost of trying**: −$3,857 in walk-forward, a rank correlation
of −0.179 across variants. That is the sixth independent reproduction in this project of the same
result — search width is monotonically harmful on this instrument and period.

What *is* worth taking is not an improvement but two corrections, both free:

1. **Use the v6 entry gate** (in session, next bar in session, not the session's first bar).
   Worth 35 fewer, better trades.
2. **Set commission to $0.50/order on MNQ.** At $2.00 the fee is ~10× the real cost and eats
   roughly 5% of gross profit.

And one thing not to do: leave TradingView's extra script-execution modes on. That alone turned
PF 1.58 into PF 0.559.

Reproduce with `python research/mnq_validate.py`.
