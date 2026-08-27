# V20 — Donchian 30/20 with a 50-period linear regression confirmation

**No demonstrable edge.** Bootstrap p-values run 0.41 to 0.97, every market goes negative at 1.5×
the assumed spread, and the regression confirmation contributes about five thousandths of an R while
passing 89% of the breakout bars it is meant to confirm.

---

## 1. The spec, and the one place it left a choice

Donchian 30 entry / 20 exit, stop 2.0 × ATR(14), target 2R, market order, one unit, intraday, with a
50-period linear regression as entry confirmation.

"The regression is supporting / forecasting the move" has four mechanical readings. Picking whichever
backtests best is how a spec becomes an overfit, so **all four were declared before running any of
them**, all four were run, and the multiplicity is stated: 4 readings × 5 markets × 2 timeframes =
**40 research cells**, of which two pass by chance at α 0.05.

| reading | 15m pooled add | 30m pooled add | markets helped |
| --- | --- | --- | --- |
| A slope > 0 | −0.0151 | −0.0082 | 40% / 40% |
| B forecast > close | −0.0534 | +0.0023 | 20% / 60% |
| **C close > value** | **+0.0049** | **+0.0028** | 60% / 80% |
| D slope > 0 **and** close > value | −0.0046 | +0.0090 | 40% / 60% |

"Add" is the reading's EV minus the identical rule with no confirmation. The best reading adds
**+0.005 R** against a base losing 0.05–0.15 R a trade.

The rolling OLS was validated before use: on a pure line it recovers slope 0.700000 with R² = 1.0,
and on a random walk it matches `numpy.polyfit` to six decimals.

---

## 2. The most literal reading is mechanically backwards

Share of bars passing each test, US30 15m:

| reading | all bars | **breakout bars** | lift |
| --- | --- | --- | --- |
| A slope > 0 | 53.1% | 78.2% | 1.47× |
| **B forecast > close** | 50.5% | **12.1%** | **0.24×** |
| C close > value | 49.7% | 89.1% | 1.80× |
| D both | 21.8% | 67.7% | 3.11× |

**On a breakout bar the regression's one-bar-ahead forecast is below the current price 88% of the
time.** It has to be: a breakout bar has just jumped above its own recent range, so price sits far
above a line fitted to that range and one bar of extrapolation cannot catch up. Reading B — the most
natural reading of "forecasting the move" — is close to a *rejection* of breakouts, not a
confirmation of them.

And reading C, the best scorer, passes **89.1%** of breakout bars: it removes about a ninth of the
trades and adds no information. This is the same mechanism `STUDY_V16_MOMENTUM.md` measured for
momentum filters — a breakout is already a directional event, so a trend filter on top of it is
largely redundant with the trigger.

---

## 3. Reading C chosen on research, read once on locked

| market | tf | n | EV (R) | PF | MAR | Sharpe | Sortino | control p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| US30 | 15m | 366 | +0.0487 | 1.085 | 0.76 | 0.70 | 0.79 | 0.006 |
| US100 | 15m | 323 | +0.0994 | 1.192 | 2.14 | 1.42 | 1.76 | 0.033 |
| NQ | 15m | 494 | −0.0023 | 0.996 | −0.03 | −0.04 | −0.04 | 0.395 |
| US30L (8.5 yr) | 15m | 1,548 | −0.1373 | 0.794 | −0.92 | −2.21 | −2.09 | 0.968 |
| XAU (22 yr) | 15m | 3,670 | −0.0546 | 0.910 | −0.74 | −0.86 | −0.91 | 0.304 |
| US30 | 30m | 190 | +0.0174 | 1.032 | 0.13 | 0.21 | 0.20 | 0.098 |
| US100 | 30m | 176 | −0.0082 | 0.985 | −0.09 | −0.10 | −0.10 | 0.458 |
| NQ | 30m | 281 | +0.0163 | 1.030 | 0.20 | 0.19 | 0.20 | 0.364 |
| US30L | 30m | 791 | −0.0778 | 0.869 | −0.77 | −0.91 | −0.84 | 0.874 |
| XAU | 30m | 1,867 | −0.0022 | 0.996 | −0.05 | −0.02 | −0.02 | 0.236 |

The two long histories — 8.5 years of US30 and 22 years of gold — are negative or zero on both
timeframes, and US30L's control p is 0.968 and 0.874. The two cells that clear a control (US30 15m
p 0.006, US100 15m p 0.033) are two of forty; the expected number by chance is two.

**Bootstrap** P(mean daily R ≤ 0), 30m locked: 0.421, 0.551, 0.411, 0.965, 0.532. Nothing
significant. **Cost stress:** at 1.5× the assumed friction every market is negative. **Perturbation:**
regression length 20/30/50/75/100 gives pooled EV −0.029/−0.030/−0.024/−0.021/−0.019 — the 50 is
neither special nor rescuable by moving it.

---

## 4. The one change the measurements support

Holding the Donchian, the regression and the stop fixed and removing **only** the 2R target, locked
block, 30 minutes:

| market | as briefed (2R) | no target | change |
| --- | --- | --- | --- |
| US100 | −0.0082 / 0.985 | **+0.1581 / 1.285** | +0.166 R |
| XAU | −0.0022 / 0.996 | **+0.1555 / 1.256** | +0.158 R |
| NQ | +0.0163 / 1.030 | **+0.0990 / 1.179** | +0.083 R |
| US30 | +0.0174 / 1.032 | +0.0049 / 1.008 | −0.013 R |
| US30L | −0.0778 / 0.869 | −0.0923 / 0.861 | −0.015 R |

Better on three of five and by an order of magnitude more than it costs on the other two. **This is
the seventh independent time on this branch that no take profit has beaten a take profit.** The
target ships on because the brief asked for it; the input turns it off.

---

## 5. Verdict

The configuration as briefed should not be traded as it stands. The regression is redundant with the
trigger rather than complementary to it, the 2R target is the weakest component, and the geometry's
own marginal surface — measured in `STUDY_V18_COINT_EWMAC.md` across 3,125 cells — already said the
2.0N stop sits below the middle of its axis. What this branch has that does survive comparable
attack is in `STUDY_V19_DESTROY.md`: the same family on 1-hour bars, above the 200-day, with no
target.

## Files

`research/v20/v20linreg.py` (rolling OLS, validated; the four declared readings) · `v20run.py`
(40 research cells, redundancy) · `v20judge.py` (locked read, controls, perturbation, geometry,
cost stress, Monte Carlo) · `pine/turtle/V20_DONCHIAN_LINREG_strategy.pine`.
