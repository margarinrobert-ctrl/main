# V56 — The parity diff says no, and two of the three causes are fixed

**The V55 script and the backtest behind it did NOT agree. Diffed on identical signals: 245 trades
against the engine's 254, one exit bar in five landing elsewhere, and — once a target was added —
the script reading 15.2% BETTER than the research. A Strategy Tester number better than the research
is the gap, not an edge. Two of the three causes were fixable and are fixed: trade count is now
99.6% and R correlation 0.9997.**

Neither ADX nor an ATR take profit earns a place. Both ship as off-by-default inputs with their
measured cost stated.

---

## The parity diff

The script's order model was rebuilt in Python and run against the research engine on the same
signals, same bars, same costs. This is the `STUDY_PINE_PARITY` procedure: a Pine port cannot be
asserted by reading it.

| model | trades | mean R | count vs engine | same exit bar | R corr | ΔR |
| --- | --- | --- | --- | --- | --- | --- |
| engine (the research) | 254 | +0.3394 | — | — | — | — |
| V55 as shipped | 245 | +0.3429 | 96.5% | 80.0% | 0.9833 | **+1.1%** |
| **this build** | 253 | +0.3284 | **99.6%** | **87.7%** | **0.9997** | −3.2% |
| *with a 4 ATR target* | | | | | | |
| engine | 315 | +0.2131 | — | — | — | — |
| V55 as shipped | 301 | +0.2456 | 95.6% | 77.6% | 0.9520 | **+15.2%** |
| **this build** | 314 | +0.2233 | **99.7%** | **93.9%** | 0.9879 | +4.8% |

### The three causes

**1. FIXED — no exit order was live during the entry bar.** `strategy.exit` was only called on a bar
where a position already existed, so the first one for a trade was placed at the *close* of the fill
bar and could not trigger until the bar after. The engine checks the barrier from the fill bar
itself. Fixed by placing a **fill-relative bracket** (`loss` / `profit` in ticks) at the *signal*
bar, which is live during the fill bar. This is the same defect `STUDY_PINE_PARITY` found on
`TURTLE_4_FINALISTS`, where it was worth 4.4–13.0% of trades averaging −33 to −118 points.

**2. FIXED — the risk was anchored to the fill bar's ATR.** The script read `atrN` at the close of
the bar on which the position first existed. It is now stored at the signal bar in `pendAtr`, which
is the only ATR knowable when the order is sent and is what the research uses.

**3. NOT FIXABLE — the working level is one bar stale.** An order placed at the close of bar *j* is
live during bar *j+1*; the engine evaluates the level at bar *j* and applies it at bar *j*. That is
a property of Pine, not a bug, and it is what the remaining 12.3% of differing exit bars is. It now
reads **conservative** (−3.2%), which is the right direction for a residual: the script scores
slightly *worse* than the research rather than better.

**The headline survives the honest model.** Under the model this script implements, the shipped rule
scores research +0.3051 PF 1.588 p 0.002 and locked +0.3125 PF 1.634 p 0.003 — against +0.3509
p 0.000 / +0.3176 p 0.005 under the engine. The result is not an artifact of the order model.

## ADX: not one of four earns a place

Under the script's own model, against a random filter of the same selectivity, 2,000 draws:

| condition | keep | research | LOCKED |
| --- | --- | --- | --- |
| CVD only (shipped) | 21.5% | +0.3051 PF 1.588 p 0.002 | +0.3125 PF 1.634 p 0.003 |
| + ADX ≥ 20 | 14.6% | +0.1900 PF 1.382 **p 0.281** | +0.2703 PF 1.585 p 0.035 |
| + ADX ≥ 25 | 9.7% | +0.1345 PF 1.284 **p 0.553** | +0.1579 PF 1.361 **p 0.275** |
| + ADX ≤ 20 | 6.9% | +0.3166 PF 1.587 **p 0.100** | +0.4015 PF 1.799 p 0.013 |

The conventional floors **lower** the edge and fail research. The inverted reading, ADX ≤ 20, scores
best — and it is **model-dependent**: p 0.100 under the script's order model against p 0.027 under
the engine's. A result that changes side of 0.05 depending on which order convention is used is not
a result. It also keeps 6.9% of signals, which is n = 39 on the locked block.

This is consistent with what the branch has measured twice before: `STUDY_TURTLE_FEATURES` found
winning breakout trades sit at *lower* ADX (21.3 against 23.6), and V52 found the Turtle's own
`ADX < 22` gate beaten by a random filter on a held-back market.

## The ATR target: clears its control and still loses to no target

| target | research R | locked R | research p | locked p | target hit | research trades |
| --- | --- | --- | --- | --- | --- | --- |
| **none** | **+0.3051** | **+0.3125** | 0.002 | 0.003 | — | 166 |
| 2 ATR (1R) | +0.0797 | +0.0652 | 0.048 | **0.127** | 49.1% | 273 |
| 3 ATR (1.5R) | +0.1669 | +0.2178 | 0.001 | 0.003 | 40.0% | 230 |
| 4 ATR (2R) | +0.1949 | +0.2268 | 0.004 | 0.002 | 31.4% | 210 |
| 6 ATR (3R) | +0.1783 | +0.3305 | **0.056** | 0.000 | 17.4% | 184 |

3, 4 and 6 ATR all clear their controls on both blocks — **and every one earns less per trade than
no target, and less in total.** Research: 166 × 0.3051 = **50.6 R** with no target against
210 × 0.1949 = **40.9 R** at 4 ATR. Locked: 88 × 0.3125 = **27.5 R** against 105 × 0.2268 = **23.8 R**.

The mechanism is visible in the trade count: a target closes positions sooner, which frees the
position lock and admits more trades at a lower edge. The p-values improve because the *control*
degrades with a target too — which is exactly why the control column is the one to read, and why
the target is offered rather than refused.

**Eleventh time no-target has beaten every target tested on this branch.**

## Caveats

n = 88 on the locked block. One market — CVD needs 1-minute bars and NQ is the only feed here that
has them. The CVD is a proxy. The ADX and target rows are 8 and 8 uncorrected tests respectively.
The parity residual is measured, not eliminated.

## Files

`research/v56/v56core.py` (the dual order-model walker, Wilder ADX) · `run_v56.py` (the parity diff
and the feature controls) · `results/v56/v56_features.csv` ·
`pine/v56/V56_CVD_ADX_TP_strategy.pine`.
