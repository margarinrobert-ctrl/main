# The Turtle short mirror, measured rather than assumed

`research/turtleshort/mirror.py`, `pine/turtle/TURTLE_SHORT_strategy.pine`. Every rule of the
long-only script inverted: entries break the channel **low**, exits reclaim the channel **high**,
the stop sits **above** the fill, the ladder steps **down**, "extended" means far **below** the
EMA, and a winner is a close **below** the first fill.

**Mirroring code is trivial. Mirroring evidence is not**, because every constant in the long
presets — the ADX ceiling of 22, the 3.964 and 3.193 extension caps — was fitted on long trades.
Reusing them on shorts is an unfitted guess wearing fitted numbers. So the mirror was measured.

## The result

NQ futures, 20/55 entry channels, 10/20 exit channels, 2N stop, 0.5N ladder, max 4 units,
skip-after-winner on, MNQ fees and slippage, split at the first 65% of sessions, locked read once:

| timeframe | side | block | trades | pts/trade | PF | net points |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 60m | long | research | 348 | +9.17 | 1.08 | +3,190 |
| 60m | long | LOCKED | 175 | −32.95 | 0.82 | −5,766 |
| 60m | **SHORT** | research | 337 | **−47.03** | **0.65** | −15,848 |
| 60m | **SHORT** | LOCKED | 165 | **−55.88** | **0.73** | −9,221 |
| 120m | long | research | 156 | +45.89 | 1.25 | +7,158 |
| 120m | **SHORT** | research | 145 | **−61.44** | **0.68** | −8,908 |
| 120m | **SHORT** | LOCKED | 72 | **−147.50** | **0.55** | −10,620 |
| 240m | long | research | 69 | +159.19 | 1.72 | +10,984 |
| 240m | **SHORT** | research | 74 | **−184.46** | **0.36** | −13,650 |
| 240m | **SHORT** | LOCKED | 44 | **−311.67** | **0.39** | −13,713 |

**Six short cells out of six are losses**, on both blocks and all three timeframes, profit factor
0.36 to 0.73. That is not a near miss a parameter fixes. It also agrees with
`STUDY_TURTLE_ORIGINAL.md`, where the short side of the full original system inverted from
**+0.098 R in sample to −0.403 out of sample**.

Worth noting the long side is no advertisement either: positive on research at every timeframe and
**negative on the locked block at every timeframe**. The mirror is worse, not different in kind.

## What this measurement cannot tell you, which matters more than the table

**NQ rose 89% across this sample and 81% of its bars sit in a daily uptrend.** A short book loses by
existing here. No control available on this data separates *"the mirror is broken"* from *"this
sample had nothing to short"* — a matched short control would itself be deeply negative, so the
comparison has no power in the direction that matters.

So the table establishes one thing and not another. It establishes that **the mirror is not rescued
by its own rules on a rising market** — the channel break, the ladder and the 2N stop do not find
the down-moves that did occur. It does **not** establish how the mirror behaves in a falling market,
because this sample does not contain one. That question needs history this branch does not have,
and `STUDY_TREND_PULLBACK_2.md` already flagged the same gap: one regime, 81% daily uptrend, the
short side close to untestable.

A deliberate consequence: `mirror.py` ships **no** matched control. Providing one would have looked
like rigour and measured drift.

## Two notes on the implementation

**R is not comparable across ladder depths and is not the number to read.** The denominator scales
with unit count, so a four-unit winner is divided by four times the risk of a one-unit loser — the
60m long research cell shows +9.17 points a trade against a mean R of −0.2343 for exactly that
reason. Points per trade and profit factor have no such distortion. On the short research block the
ladder reached four units on 146 of 337 trades, so the effect is not marginal.

**The exit mirrors to `math.min`, not `math.max`.** On the long side the stop is the *higher* of the
ATR stop and the channel low, because falling price reaches that first. Short, rising price reaches
the *lower* of the ATR stop and the channel high first. Getting this backwards would place a stop
the market has already passed.

The Pine defaults to **"Spec defaults (no gate)"** rather than to a preset, since the presets carry
constants that were never fitted on this side; those options are present but labelled `UNFITTED on
this side`, and the HUD's first row states the measured verdict on every chart.
