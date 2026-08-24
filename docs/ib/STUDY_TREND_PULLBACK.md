# Follow the daily trend, buy the pullback, 07:00–11:00 — built and measured

*Built exactly as specified:* daily trend from EMA200 and EMA crossovers → intraday pullback →
resumption trigger → entries only 07:00–11:00 New York. Direction dictated by the daily trend,
never chosen by the optimiser. No mean reversion: a rule that bought a dip in a daily *downtrend*
cannot be expressed in this family.

*Measured result:* **161,280 combinations, 1,158 clear every research-block gate, 4 pass the
holdout drop-one test — and all four fail the matched control on the research block while passing
it on the holdout.** That is the wrong shape and it is not selectable. The plain version of the
idea is worse than a time-matched random long on research and better on the holdout, with the sign
flipping between blocks.

---

## 1. The one structural improvement worth keeping

Every previous search on this branch let the optimiser choose long or short. That is the most
dangerous free parameter on this sample: NQ rose 91%, so a search allowed to pick a side picks
long and gets paid for existing (`RESEARCH_PROTOCOL.md` §4c). It is why every rule has to be
scored against the base rate of its own side.

Here **the daily trend fixes the side**. The rule is not long because long worked; it is long
because the daily trend is up, and it is short when the daily trend is down. Direction stops being
fitted. That is a better place to search from and it should be kept regardless of this result.

Two honest limits of the sample, stated before the numbers:

* **81% of intraday bars sit in a daily uptrend and 7% in a daily downtrend.** The short side has
  almost no data here. Its results deserve very little weight.
* **07:00–09:30 is pre-RTH.** Volume is a fraction of the cash session and the real spread is wider
  than the cost model assumes, so pre-market figures are optimistic by an unmodelled amount.

## 2. Causality, which was the hard part

A daily bar's close is not known until the session ends. The first version keyed the daily state
on the repository's 09:30 session index and shifted it one session — which is causal but throws
away a whole day: at Tuesday 07:00 it would have shown the trend as of Monday 09:29, when a real
trader plainly knows Monday's 16:00 close.

The daily bar is now the RTH session with an explicit **known-at** timestamp, and an intraday bar
takes the most recent daily bar that has *already closed*. Tuesday 07:00 sees Monday's 16:00 close
and nothing after it. `leakage_check` rebuilds from truncated 1-minute history and confirms:
**CLEAN**.

## 3. The search

| | |
| --- | --- |
| daily trend states | 7 per side — close vs EMA200, EMA20/50, EMA50/200, the stacked triple, uptrend + ADX>20, 50-bar slope, ±DI |
| pullback conditions | 16 per side — below EMA20 / EMA50 / by 0.5 and 1 ATR, below session VWAP, at 5/10/20-bar low, RSI<35/40/45, Stoch<20/30, 2 and 3 down closes, retrace >1 ATR from the 20-bar high |
| resumption triggers | 10 per side — cross back above EMA20, close > prior high, close > 3-bar high, bullish engulfing, first up close, RSI back above 40/50, Stoch back above 20, bullish bar, close in top third |
| geometry | 6 stop widths × 4 flatten times (none, 11:00, 12:00, 16:00) |
| timeframes | 5m, 15m, 30m |
| **combinations** | **161,280** |

Gates unchanged: base-rate excess against the population mean of the rule's own side and geometry,
subset coherence on singletons and pairs, geometry tuned on research, then each condition against a
random filter of the same selectivity **on the locked block**.

    1,158  rule/geometry pairs clear every research gate
       60  after collapsing rules that share two or more conditions
        4  have 2 of 3 conditions beating a random filter on the LOCKED block, profitable and
           above base there

| | rule | trades | win % | base | locked n | locked win % | locked $ | PF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1 | D close>EMA200 + at 5-bar low + close in top third | 47 | 59.6 | 50.3 | 17 | 64.7 | 1,676 | 2.13 |
| P2 | D uptrend+ADX>20 + below VWAP + bullish engulfing | 301 | 52.5 | 50.3 | 75 | 56.0 | 4,116 | 1.24 |
| P3 | D uptrend+ADX>20 + retrace >1 ATR + top third | **654** | 53.1 | 50.3 | 151 | 52.3 | 4,716 | 1.15 |
| P4 | D uptrend+ADX>20 + Stoch K<30 + close > prior high | 154 | 52.6 | 49.3 | 29 | 62.1 | 1,277 | 1.27 |

P3 fires 654 times — more than anything else on this branch.

## 4. The matched control, which stops all of it

Random entries with the same side, geometry and minute-of-day distribution:

| | research win p | research net p | locked win p | locked net p |
| --- | --- | --- | --- | --- |
| P1 | 0.274 | 0.157 | 0.102 | **0.043** |
| P2 | 0.491 | 0.591 | **0.005** | **0.030** |
| P3 | **0.025** | 0.723 | **0.005** | **0.005** |
| P4 | 0.651 | 0.354 | **0.015** | 0.107 |

**Every one of them fails on research and passes on the holdout.** That is backwards. A rule
selected on the research block should look *better* there — the holdout is where an edge decays,
not where it appears. The same diagnostic caught a fake feature result earlier in this branch.

The plain version of the idea shows why, with no rule search at all — just *be long in the window
when the daily trend is up and ADX > 20*:

| block | rule | matched control | p |
| --- | --- | --- | --- |
| **research** | 677 trades, 50.4% win, **−$2,848** | +$3,646 | **1.000** |
| **locked** | 229 trades, 53.3% win, **+$3,885** | −$6,151 | **0.003** |

The daily-trend filter is **worse than a random long** at the same times on the research block and
**better** on the holdout. The sign flips completely. That is regime instability across 2023–24
versus 2024–25, not an edge — and no amount of pullback and resumption structure fixed it, because
all four survivors inherit it.

## 5. What is actionable anyway

**The cash-session half of your window is the better half.** Same rule, different entry windows:

| entry window | trades | research $/trade | locked n | locked $ |
| --- | --- | --- | --- | --- |
| 07:00–11:00 | 906 | $1.1 | 229 | 3,885 |
| 08:00–11:00 | 803 | $1.4 | 203 | 3,615 |
| **09:30–11:00** | 509 | **$4.2** | 132 | 3,633 |
| 07:00–09:30 | 641 | $1.9 | 154 | 1,580 |
| 09:30–16:00 | 743 | $0.9 | 180 | 750 |

09:30–11:00 gives roughly **four times the per-trade result of the full 07:00–11:00 window on
research**, on 44% fewer trades, and nearly all of the locked dollars. Every one of the four
candidates shows the same split individually — pre-RTH earns $7.2, $15.5 and $12.9 per trade
against $15.3, $20.5 and $17.0 in the cash session. And the cost model does **not** widen the
spread before 09:30, so the true pre-market gap is larger than these numbers show.

If you trade this structure, **trade 09:30–11:00, not 07:00–11:00.** That is the one recommendation
in this document I would stand behind, and it is a window choice rather than an edge claim.

## 6. Feature engineering: what was built and what needs a file

167 features now, across every family requested. Three were added in this pass:

| family | n | notes |
| --- | --- | --- |
| spread | 2 | Corwin-Schultz (2012) high-low, Roll (1984) autocovariance — **estimators, not quotes** |
| variance | 7 | Parkinson, Garman-Klass, Rogers-Satchell, realised vol, vol-of-vol, ATR expansion and compression |
| order flow | 8 | **tick-rule proxies**: delta, delta/volume, delta z-score, absorption, aggressive buy and sell, trade intensity, Kyle lambda proxy |
| market structure | 7 | swing distances, break of structure up/down, liquidity sweeps of highs and lows, swing range |
| session | 5 | NY open hour, London/NY overlap, pre-RTH, the 07:00–11:00 window, minutes from the open |
| anomalies | 4 | volume, return and ATR shock z-scores, absolute return in ATRs |

Leakage check: **CLEAN**.

**Named as proxies on purpose.** A feature called `delta` that is really a tick-rule guess from
1-minute bars will be trusted like real delta, and it should not be — the tick rule's error grows
with bar size, and a 5-minute bar is a long time to guess an aggressor side over.

**Not buildable here, and exactly what each would need:**

| | what it needs |
| --- | --- |
| options / IV / GEX / gamma regime | an NQ or SPX chain with strikes, expiries and greeks; or at minimum a VIX/VXN daily series for the IV-level features |
| cross-asset — NQ/ES correlation, DXY, bonds, VIX | ES, DX, ZN and VX bar files on the same clock in `data/`. Rolling correlation, beta and lead-lag are then one function each |
| true bid/ask spread and depth | quote data. The two spread features are bar estimators |
| true delta and absorption | trade-side data. The order-flow features are tick-rule proxies |

Drop those files into `data/` and the cross-asset family is an afternoon's work; the options family
needs a chain and is a larger job.

## Files

| | |
| --- | --- |
| `research/daily_trend.py` | daily RTH bars with known-at timestamps, 14 trend states, leakage check |
| `research/pullback.py` | the pullback and resumption pools, 07:00–11:00 window |
| `research/pullback_search.py` | the five phases with direction dictated by the daily trend |
| `research/features3.py` | spread, variance, order-flow proxy, structure, session and anomaly families; `NEEDS_DATA` registry |

Measured on MNQ, 2022-12-27 → 2025-12-11, one contract, $1.00 commission per round turn, one tick
spread plus one tick slippage each side, one extra tick on stops. **The cost model does not widen
the spread before 09:30.** Research tooling for education and analysis, not financial advice.
