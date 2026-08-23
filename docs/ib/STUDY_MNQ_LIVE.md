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

---

# The take-profit — the first change in this work that survives a holdout

Prompted by a request to target 65% win at 1:1 RR. That target is unreachable, and the reason it
is unreachable pointed at something that works.

## The barrier bound, and the anomaly it exposes

For a price path with no drift the probability of touching +R before −R is exactly
`R_down / (R_up + R_down)`. It is a property of the barriers, not of the signal. Measuring this
rule's actual win rate against that bound, with the stop fixed at 2 × ATR and the CHoCH exit off:

| RR | driftless bound | observed | excess |
| --- | --- | --- | --- |
| 0.5:1 | 66.7% | 70.9% | +4.2 |
| 0.75:1 | 57.1% | 61.3% | +4.2 |
| 1:1 | 50.0% | 56.0% | +6.0 |
| 1.5:1 | 40.0% | 49.0% | +9.0 |
| **2:1** | **33.3%** | **44.0%** | **+10.7** |
| 3:1 | 25.0% | 33.6% | +8.6 |

Positive at every ratio — the signal carries real directional information — and the excess **peaks
at 2:1**. That is a mechanism, not a fitted parameter: the bound is fixed by geometry, so the
excess cannot be tuned into existence.

On the original question: 65% at 1:1 is not available. 1:1 pays **56.0%**. Above 65% is reachable
only at 0.5:1 (70.9%), which nets $2,287 against the baseline's $7,060 — a high win rate bought by
giving away the payoff.

## It survives every test that killed the other six

| | research net | research PF | LOCKED net | LOCKED PF |
| --- | --- | --- | --- | --- |
| baseline (CHoCH exit) | $2,387 | 1.34 | $4,674 | 1.75 |
| take-profit 1.5R | $609 | 1.06 | $7,273 | 2.08 |
| **take-profit 2.0R** | **$2,747** | 1.25 | **$8,932** | **2.23** |
| take-profit 3.0R | $4,019 | 1.36 | $8,180 | 1.97 |

All four beat the baseline out of sample, so it is not a knife-edge. Walk-forward over six
expanding folds picked "TP 2R, no CHoCH" in **all six**, stitching to **$11,481** against the fixed
baseline's $8,242 — the first time in this project that re-selection has *added* value rather than
destroyed it (it cost −$3,857 on the earlier variant set).

The take-profit and the CHoCH exit **conflict**: running both gives $8,405 stitched OOS versus
$11,481 for the target alone. A CHoCH cuts winners before they reach the target.

## Full comparison

| | trades | net | PF | win % | maxDD | Sharpe | Calmar |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline (CHoCH) | 147 | $7,060 | 1.53 | 40.1% | **$2,074** | 2.28 | 3.40 |
| TP 2R, no CHoCH | 141 | **$11,679** | **1.64** | **44.0%** | $2,865 | **2.93** | **4.08** |

Longs 79 trades, $7,990, PF 1.95, 48.1% win. Shorts 62 trades, $3,689, PF 1.38, 38.7% win — the
long advantage is most likely the 2022-25 bull regime rather than skill, and shorts staying above
PF 1.3 through it is the more reassuring half.

Monte Carlo, 5,000 block-bootstrap paths: median net $11,427 (p5 $2,685, p95 $21,685), median
drawdown $2,400 (p95 $4,532), **P(net < 0) = 1.5%** against the baseline's 1.8%.

## What holds this back from being called established

- **The paired same-session difference against the baseline is t = +1.22.** Favourable on every
  summary statistic; not significant. This is the number that matters and it does not clear a bar.
- Max drawdown **rises** $2,074 → $2,865. Calmar improves anyway, but anyone who chose this rule
  for its shallow drawdown is trading some of that away.
- 49 locked trades. Walk-forward folds 3 and 4 were negative (−$177, −$1,516).
- Roughly ten exit variants were examined in total, so some multiple-testing haircut applies —
  smaller than the usual one here because the whole family moved together and the barrier-bound
  mechanism was predicted before the P&L was looked at.

## Two hypotheses tested and rejected in the same pass

**Entering at or near the 200 EMA.** The opposite of the current filter, and the data is emphatic:

| distance from EMA at signal | trades | net | PF | win % | $/trade |
| --- | --- | --- | --- | --- | --- |
| 0.0-0.5 ATR | 15 | −$1,607 | 0.27 | 20.0% | −$107 |
| 0.5-1.0 ATR | 10 | −$524 | 0.55 | 40.0% | −$52 |
| 1.0-1.5 ATR | 11 | $1,036 | 1.92 | 45.5% | +$94 |
| 1.5-2.5 ATR | 34 | $3,666 | 2.18 | 35.3% | +$108 |
| ≥ 2.5 ATR | 107 | $2,919 | 1.32 | 42.1% | +$27 |

Near-EMA only: 25 trades, **−$2,131**, PF 0.36. A break that occurs while price sits on the 200 EMA
is a break inside chop — there is no established trend for it to continue.

**65% win at 1:1.** Not reachable; see the barrier bound above.

Reproduce with `python research/mnq_deep.py`.
