# The ten-indicator stack, measured

MACD as the signal, RSI for overbought/oversold, Bollinger for volatility, the 9/21/50/200 EMA
ladder, VWAP for intraday breakouts, ADX for trend strength, and the 21 SMA as the bull/bear line.
Each tested in the role it was given.

Setup: MNQ 15-minute, 09:30–16:00 NY, long and short, 2.0×ATR stop, 1R target, 24-bar max hold,
real fees ($1.44 round turn) plus spread and slippage. `research/user_stack.py`.

## 1. The base rate is not 50%, and it is not symmetric

Taking **every bar** on the research block:

| | trades | win % | $/trade |
| --- | ---: | ---: | ---: |
| long | 1,844 | **51.3%** | +$1.92 |
| short | 1,844 | **47.1%** | −$10.75 |

That 4.2-point gap is the sample's drift, and it is the number every condition has to be scored
against. A short setup winning 48% has beaten nothing. This is also why the short column below is
reported but not pursued: **several short conditions beat their matched control while still losing
money**, because the control they beat loses more.

## 2. What each indicator actually did

58 conditions, each against a matched control (same side, geometry and minute-of-day). 2.9 were
expected to reach p<0.05 by chance; **14 did**.

### Moved the odds

| condition | dir | n | win % | base | lift | $/trade | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ADX>20 and +DI>−DI | long | 844 | 55.2 | 51.3 | **+3.9** | **+$11.39** | 0.000 |
| Bollinger width > 1.5% (expansion) | long | 268 | 54.5 | 51.3 | +3.2 | **+$12.35** | 0.002 |
| 0.5 ATR above VWAP (breakout) | long | 903 | 54.2 | 51.3 | +2.9 | +$8.07 | 0.005 |
| above session VWAP | long | 1,187 | 53.4 | 51.3 | +2.1 | +$6.91 | 0.004 |
| close > 9 EMA | long | 1,279 | 52.5 | 51.3 | +1.2 | +$6.02 | 0.016 |
| ADX > 25 | long | 1,174 | 52.7 | 51.3 | +1.4 | +$5.70 | 0.028 |
| **close > 21 SMA** (your trend line) | long | 1,154 | 52.9 | 51.3 | +1.6 | +$5.51 | 0.040 |

### Did not

| condition | dir | lift | $/trade | p |
| --- | --- | ---: | ---: | ---: |
| **MACD histogram > 0** — the designated signal | long | +1.3 | +$3.92 | **0.199** |
| MACD strongly positive | long | +1.2 | +$3.92 | 0.472 |
| **9/21 cross up** — the designated entry | long | +0.7 | +$5.53 | 0.429 |
| close > 21 EMA | long | +1.4 | +$4.76 | 0.083 |
| 21 EMA pullback above the 200 | long | +1.8 | +$2.77 | 0.550 |
| within 0.5 ATR of the 50 EMA | long | +0.2 | +$1.98 | 0.667 |
| close > 200 EMA | long | +1.3 | +$4.12 | 0.146 |

### Actively wrong

**RSI < 30, bought as "oversold", is the worst long condition in the scan**: 50.3% against a 51.3%
base, **−$8.13/trade**, p 0.999. Fading it — shorting oversold — beats its control at p 0.002 and
*still loses money* (−$0.66/trade), because the short base is −$10.75.

## 3. The headline

**The things carrying this stack are trend STRENGTH (ADX with directional agreement), volatility
EXPANSION, and position relative to VWAP. The moving-average ladder and MACD are close to inert.**

Every one of the seven survivors is a long-side statement about being in a trending, expanding,
above-VWAP market. They are near-duplicates, so this is roughly **one finding, not fourteen**, and
the multiplicity correction should be read that way.

The 21 SMA bias does work — +1.6 points of win rate, +$5.51/trade at p 0.040 — but it is the
weakest of the survivors, and it says nothing the 9 EMA and VWAP conditions do not say more
strongly.

## 4. The combination, and why it is not a green light

41 mechanism combinations × geometry = **1,476 configurations** (73.8 expected to clear p<0.05 by
chance). Best on research, then the locked block read once:

| rule | research | locked | flag |
| --- | ---: | ---: | --- |
| ADX>20 & +DI>−DI & BBW>1.5 & close>21SMA | 88 trades, $62.1/tr, 60.2% | 58 trades, **$99.1/tr**, 58.6% | **GREW ON LOCKED** |
| BBW>1.5 & close>200EMA & close>9EMA | 88 trades, $61.7/tr | 53 trades, **$101.9/tr** | **GREW ON LOCKED** |

All four revealed configurations beat their control on the holdout at p≈0. **That is the wrong
shape and it is treated here as a defect, not a result** — an edge decays out of sample, it does
not double.

Diagnosis, from `always` and each mechanism measured on both blocks separately:

| | research $/tr | locked $/tr |
| --- | ---: | ---: |
| always (every bar, long) | 6.9 | **2.8** |
| trend strength | 18.5 | **35.2** |
| VWAP breakout | 14.0 | **23.3** |
| 21 SMA bias | 11.0 | **27.7** |
| 9 EMA | 11.8 | **24.6** |
| vol expansion | 41.2 | **20.0** |

The unconditional baseline got **worse** on the locked block while five of six trend conditions got
**better**. So this is not "the holdout was an easy long" — it is that **trend-conditioning paid
roughly twice as much in the later period**. The rule is a regime amplifier, and the holdout
happened to be a more trend-persistent regime.

Two further reasons not to project these numbers forward:

* **The matched control does not match volatility state.** It matches side, geometry and
  minute-of-day. A rule that only fires when Bollinger width exceeds 1.5% is being compared against
  entries that were mostly not in expansion, which inflates the excess. Against volatility
  expansion *alone*, the winner adds $21/trade on research but $79 on locked — inconsistent, which
  is the same regime story again.
* **88 and 58 trades.** At those counts, $62 and $99 per trade are noisy numbers.

## 5. What would actually raise the probabilities

1. **Drop MACD and the 9/21 cross from the entry decision.** Neither is doing work here. Keeping
   them costs nothing but it buys nothing, and it makes the stack look better-supported than it is.
2. **Stop buying RSI<30.** It is the single most damaging condition tested.
3. **Keep ADX+DI, volatility expansion, and VWAP position.** They are the stack's real content.
4. **Treat the combination as regime-conditional.** It needs a second instrument or more history
   before the locked figure means anything, because right now the honest reading is that it
   measured a regime.

Measured on MNQ, 2022-12-27 → 2025-12-11, one contract, itemised fees, bar-dependent slippage.
Research tooling for education and analysis, not financial advice.
