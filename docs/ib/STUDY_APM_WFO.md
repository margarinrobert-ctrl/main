# Walk-forward optimisation of the Saty-phase configuration as given

`research/apm/apm_wfo.py`, output `results/apm/wfo.txt`. Engine: `research/apm/apm_core.py`, the
NinjaScript port already validated in `docs/ib/STUDY_APM_VWAP.md`.

## 1. The configuration, and how each number was mapped

Ten of the twelve map cleanly onto the engine. Two do not, and are flagged rather than guessed.

| given | meaning | engine |
|---|---|---|
| 21 | pivot EMA length | `ema = 21` |
| 21 | ATR length | `atr = 21` (the port's default is 14) |
| 4 | smoothing of the raw phase | `osc = 4` (default 3) |
| 100 / −100 | the extended zones | `dist = 3.0` — the engine's threshold is `100 × dist / 3`, so **dist 3.0 IS the ±100 band**; same number, different unit |
| 09:30-10:30 | entry window | `ent0 = 570`, `ent1 = 630` |
| **11** | — | **NOT MAPPED** |
| **0** | — | **NOT MAPPED** |
| Opposing ±100 | exit at the opposite extreme | `opp_exit_on = True` |
| **61.8** | the golden-ratio zone | **NOT AN AXIS**: the port gates on the extended band only, so 61.8 is drawn and never traded on |
| 09:30-16:00 | cash session | the `USIndex` profile, cash close 960 |
| 2.5 | VWAP band, in ATR | `vwap = 2.5` |

`11` and `0` sit between the entry window and the exit rule. In the source NinjaScript the fields in
that position are a cap and an offset, and the port implements neither — it holds one position at a
time and does not re-enter inside a session, which is a cap of 1. **They are the only two numbers
below that are assumed rather than read; say what they are and I will re-run.**

## 2. The configuration as given, on the branch's own block split

Percent of entry price per trade, after each feed's costs.

| market | block | n | %/trade | total | PF | win |
|---|---|---|---|---|---|---|
| NQ 10m | research | 66 | +0.1394 | +9.20% | 1.64 | 56.1% |
| NQ 10m | locked | 34 | **+0.3805** | +12.94% | 7.19 | 70.6% |
| US100 15m | research | 126 | +0.1913 | +24.11% | 2.02 | 61.1% |
| US100 15m | validation | 49 | +0.2933 | +14.37% | 1.90 | 59.2% |
| US100 15m | test | 47 | +0.2469 | +11.60% | 2.53 | 57.4% |
| US30 15m | research | 102 | **−0.0263** | −2.68% | 0.88 | 50.0% |
| US30 15m | validation | 47 | +0.0151 | +0.71% | 1.05 | 38.3% |
| US30 15m | test | 38 | **−0.0981** | −3.73% | 0.61 | 36.8% |

**It is a two-market configuration.** US100 is positive and consistent on all three blocks; NQ is
positive on both with the locked block reading better than research (n=34, so read it as a small
sample rather than a strengthening edge); **US30 is negative on two of three blocks and never
clears PF 1.05**. That matches `STUDY_APM_VWAP`, where US30 was null over nine years.

## 3. The walk-forward

All six parameters re-chosen inside every training window from a **2,304-cell grid centred on the
given values** (so the given cell is inside the search), then read on the window the optimiser has
never seen. Both a rolling and an expanding training window. Objective: total percent on the
training span, with a 20-trade floor.

| market | mode | re-chosen | given | WFE | folds positive |
|---|---|---|---|---|---|
| NQ | rolling 12m | +0.0684 | **+0.3123** | 0.22 | 5/7 vs **7/7** |
| NQ | expanding | +0.0592 | **+0.3123** | 0.19 | 5/7 vs **7/7** |
| US100 | rolling 24m | +0.0006 | **+0.2702** | 0.00 | 7/13 vs **11/13** |
| US100 | expanding | +0.0698 | **+0.2702** | 0.26 | 9/13 vs **11/13** |
| US30 | rolling 24m | −0.0241 | −0.0195 | n/a | 6/13 vs 3/13 |
| US30 | expanding | −0.0657 | −0.0195 | n/a | 3/13 vs 3/13 |

**Mean walk-forward efficiency 0.17** over the four cells where the ratio is defined — and the
re-optimiser **loses in 6 of 6 cells**, on fold-consistency as well as on the stitched result. WFE
is reported as n/a on US30 because the baseline there is negative: dividing by a negative baseline
produces a number with the wrong sign and no meaning.

**And the optimiser never settles.** Its per-fold choices agree with its own first fold's choice
only **38–52% of the time** averaged over the six axes, and it keeps the given value rarely — on
NQ rolling: `ema` 1/7, `vwap` 0/7, `osc` 1/7, `dist` 2/7, `ent1` 2/7, `atr` 5/7. A parameter whose
optimum moves every fold is a parameter with no information in it.

Sixth time on this branch that a re-optimiser has lost to the author's constants
(`STUDY_IBS_SESSION`, `STUDY_APM_VWAP`, `STUDY_TRENDDAY_EMA`, `STUDY_V60`, `STUDY_V63`).

## 4. What this does and does not say

It does **not** say the configuration is good — that question is answered by §2 and by
`STUDY_APM_VWAP`'s controls, where the rule's DIRECTION call beats a coin flip (NQ p 0.05/0.001,
US100 0.012/0.034) while its ENTRY loses to a random bar in the same window on every block of every
feed, because the fill has already chased a median 3.97 ATR of a 4.99 ATR day.

It says the twelve numbers are **not worth optimising**. Leave them where they are. The honest
uses of a grid here are the two this branch already ran: the marginal average per axis, and a
neighbourhood check that the shipped cell is not a spike.

Sample size remains the binding limit: **34 locked trades on NQ, 47 on US100's test block**. Nothing
here is ready to size on without a forward test of 40+ trades.
