# Why M4 makes money, and what it is not

M4 — `body<30% AND first hour AND ATR>1.8× mean`, 30-minute bars, long, 4.0×ATR stop, 1.0R
target, flat at 16:00 — was the only one of three strategies that made money in a TradingView
Deep Backtest (`STUDY_PINE_CONFIG.md`). It also carries the highest 1R win rate this branch has
produced. This is what that win rate is made of.

`research/m4_anatomy.py` runs the whole battery. `research/ib_features.py` runs the feature work.

## The answer, before the evidence

**M4 is not a 1R barrier strategy. It is a day filter attached to a long held to the close.**
Its barriers are close to decorative, its entry bar carries no information, and what it actually
does is identify sessions that drift up. It beats a minute-of-day-matched control doing that
(research p = 0.001), so the day filter is real — but almost none of the machinery it is dressed
in contributes.

## 1. Where the money comes from

| exit | n | share | net $ | per trade | of net |
| --- | ---: | ---: | ---: | ---: | ---: |
| target | 15 | 17% | +4,889 | 326 | 54% |
| stop | 6 | 7% | −2,298 | −383 | −26% |
| **time** | **67** | **76%** | **+6,414** | **96** | **71%** |

Median hold 11 bars — 5.5 hours. Three quarters of trades never touch a barrier.

## 2. The barriers are inert

Same entries, stop widened to infinity:

| stop | n | win % | net $ | $/trade | stop/target/time |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1.0× ATR | 90 | 64.4 | 2,931 | 32.6 | 31/58/1 |
| 2.0× ATR | 88 | 69.3 | 5,200 | 59.1 | 21/45/22 |
| 3.0× ATR | 88 | 72.7 | 8,654 | 98.3 | 8/28/52 |
| **4.0× ATR (shipped)** | 88 | **73.9** | **9,005** | **102.3** | 6/15/67 |
| 10.0× ATR | 88 | 72.7 | 9,030 | 102.6 | 0/0/88 |
| **no barrier at all** | 88 | 72.7 | **9,030** | **102.6** | 0/0/88 |

Removing the barriers entirely is worth **more** than the shipped geometry. A barrier edge decays
when you widen the stop; this converges to buy-and-hold-to-flatten and stays there. The stop only
ever truncates the thing that pays.

## 3. The entry bar carries no information

On the **same days** M4 traded, entering long at a *random* first-hour bar instead:

| | win % | $/trade | net $ |
| --- | ---: | ---: | ---: |
| M4 actual | 73.9 | 102.3 | 9,005 |
| same days, random bar | 72.2 | 104.9 | 9,229 |
| p (M4 ≥ day control) | 0.187 | | 0.556 |

Indistinguishable. Whatever `body<30%` is doing, it is flagging a **day**, not an entry.

And those days move:

| | days | mean 09:30→16:00 | median | up-days |
| --- | ---: | ---: | ---: | ---: |
| M4 days | 88 | **+$96.3** | +$105.2 | **65.9%** |
| all days | 764 | +$14.6 | +$38.5 | 55.2% |

## 4. The day filter is real — it beats its matched control

Random entries, same side, geometry and minute of day, 800 draws:

| block | n | win % | control | p | net $ | control $ | p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| research | 63 | 74.6 | 56.9 | **0.001** | 6,209 | 1,187 | **0.001** |
| locked | 25 | 72.0 | 56.2 | **0.030** | 2,796 | 253 | 0.085 |

The control already contains the drift, the session clock and the barrier width, so beating it at
p = 0.001 is not "the market went up". Note the locked **net** does not separate (p = 0.085) on
25 trades.

## 5. Which condition is load bearing

| variant | n | win % | net $ | research $/t | locked $/t |
| --- | ---: | ---: | ---: | ---: | ---: |
| M4 (all three) | 88 | 73.9 | 9,005 | 98.6 | 111.8 |
| drop `body<30%` | 299 | 55.9 | 4,282 | 23.5 | −10.4 |
| **drop `ATR>1.8×`** | **405** | 61.0 | **20,933** | **48.9** | **57.0** |
| drop `first hour` | 286 | 56.6 | 4,167 | 23.0 | −5.4 |
| first hour only, no rule | 774 | 54.9 | 15,011 | 19.0 | 20.2 |

`body<30%` and `first hour` are both essential. `ATR>1.8×` is not — dropping it more than doubles
total profit.

## 6. Body is a mechanism; the ATR filter is a threshold

Bands rather than cuts, on the research block, first hour held fixed:

| body band | n | research $/t | | ATR/mean band | n | research $/t |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| [0.00, 0.10) | 18 | +86 | | [1.0, 1.2) | 13 | +62 |
| [0.10, 0.20) | 22 | +90 | | [1.2, 1.4) | 35 | +73 |
| [0.20, 0.30) | 24 | +111 | | [1.4, 1.6) | 84 | +53 |
| [0.30, 0.40) | 30 | +39 | | **[1.6, 1.8)** | 91 | **+8** |
| [0.40, 0.50) | 33 | +50 | | [1.8, 2.2) | 50 | +98 |
| [0.50, 0.65) | 70 | +40 | | [2.2, ∞) | 14 | +113 |
| [0.65, 0.80) | 57 | **−34** | | | | |
| [0.80, 1.01) | 54 | **−39** | | | | |

The body relationship is **monotone and changes sign** — small bodies pay, large bodies lose.
That is what a mechanism looks like, and 0.30 sits near the natural break rather than on a spike.

The ATR relationship is **not monotone**: it has a hole at [1.6, 1.8) immediately below the
shipped cut. `ATR>1.8×` earns its research number by sitting just above a dead band. That is a
threshold, not a mechanism — exactly the failure mode CLAUDE.md warns about.

## 7. Correlations

The three conditions are effectively orthogonal, so none is a disguised copy of another:

| | body<30% | first hour | ATR>1.8× |
| --- | ---: | ---: | ---: |
| body<30% | 1.000 | −0.009 | −0.041 |
| first hour | | 1.000 | 0.241 |
| ATR>1.8× | | | 1.000 |

Fire rates: body<30% 32.8%, first hour 4.3%, ATR>1.8× 5.0%.

Against the book, daily P&L: **M4's mean |ρ| to the other eight legs is 0.080, max 0.229 (V3).**
Genuinely decorrelated — but CLAUDE.md's rule applies, a decorrelated leg still has to have an edge.

## 8. Regime

M4 does **not** need the daily uptrend. Split by daily state at the *signal* bar (`eb−1`, not
`ent_bar`): `D EMA20>EMA50` gives $79.9/trade against $244.2 when that is false; `D slope50<0`
gives $140.3 against $92.6 for `slope50>0`; `D uptrend + ADX>20` gives $102.2 against $102.4 when
absent. If anything it prefers a weaker daily trend, which fits a compression-release reading.
These are conditional splits of realised trades, so they are descriptive only — a filter claim
would have to filter the triggers and re-simulate.

## 9. Feature engineering: the Initial Balance

M4's window *is* the IB, its barriers are inert and its entry bar is noise — so the natural
feature set is the completed IB and the natural entry is 10:30, the first moment it is known.
Moving the entry there costs nothing: **$98.7/trade against $102.3, 75.0% against 73.9%.**

14 causal IB features, ranked on research. Baseline (long at 10:30 every day) is +$13.2/trade
research, +$4.5 locked. Eight pre-declared candidates, thresholds fixed on research, matched
control as the gate, Benjamini-Hochberg at FDR 0.10:

| candidate | n_r | win % | control | p_net | **locked $/t** | **locked net** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| C `ib_dir` up | 232 | 61.6 | 55.8 | **0.002 PASS** | +11.8 | +1,652 |
| G `close_pos>0.66 and range<median` | 88 | 61.4 | 55.7 | **0.013 PASS** | **−29.4** | **−1,263** |
| B `ib_close_pos>0.66` | 182 | 59.3 | 55.6 | **0.033 PASS** | **−1.5** | **−160** |
| D `ib_range_atr` < median | 236 | 57.6 | 55.7 | 0.101 fail | +29.2 | +3,743 |
| A `ib_body<0.30` | 149 | 59.7 | 55.5 | 0.305 fail | +36.7 | +2,533 |

**Three passed the research gate and FDR. Two lost money on the holdout; the third decayed from
+$42.5 to +$11.8 per trade, barely above the do-nothing baseline.** Meanwhile the two that look
best on locked both *failed* research — the wrong shape, which this branch treats as a defect
rather than a result.

**The IB feature family does not produce a durable edge.** This agrees with `STUDY_IB.md`, where
the published IB geometry was already negative, and with `STUDY_TREND_PULLBACK_2.md`, where 127
rules beat a control on research and 0 survived. Do not re-run it.

Note what this also says about M4: its own `body<30%` condition, generalised to the IB, **fails
its research control at p = 0.305**. M4's edge does not survive being restated at day scale.

## 10. What to do with M4

Three claims, at three different strengths.

**Established.** M4 is a day-selection bet, not a barrier edge. The stop and target can be
removed with no loss. The entry can be moved to 10:30 with no loss. The day filter beats a
matched control on research at p = 0.001, and on the locked block by win rate (p = 0.030) though
not by net (p = 0.085).

**Established, research-only evidence.** `body<30%` is a real monotone mechanism; `ATR>1.8×` is a
threshold sitting above a dead band. Both statements rest on the band tables in §6, computed on
research alone.

**A hypothesis, not a result.** Dropping the ATR filter gives `body<30% AND first hour`:
266 research trades at $48.9 and 139 locked at $57.0, $20,933 total, with the matched control at
research p_net 0.001 and **locked p_net 0.036 — where M4's own locked net does not separate.**
That is a better-looking strategy on every axis including trade count. **But it was identified
after reading the locked column in §5, so its locked p-value is contaminated and cannot be
counted.** It needs data this repository does not have. The research-only case for it (§6) is
sound; the holdout confirmation is not available.

## 11. Still true

M4 holds 88 trades over three years — 25 of them on the locked block. Its header already carries
the **grew on locked** warning. Everything above sharpens what M4 *is*; none of it makes the
sample bigger.
