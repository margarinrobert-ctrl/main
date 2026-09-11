# EMA 13/48 × VWAP × ATR-trail, with feature engineering and deep learning — evaluation

`research/ema48/`, `results/ema48/`. Research log with the trial count: `research/ema48/research_log.md`.

*(Verdict is at the end, after the no-trail ladder — it is the section the verdict turns on.)*

## The prior this branch carries into the ask

Every component has been measured here before, on held-out data: the 13×48 cross has failed
five held-back reads (V41, V51, V52, V55, V58); a 1.5×ATR stop sits on the wrong side of its own
marginal curve on every market (V18); every trailing stop measured has lost to no trail; the
intraday constraint has cost 57–88% of the result on every family it was applied to; and deep
learning has lost to ridge on every timeframe tried (V28, V32, V48). This study measures the
combination, with controls, rather than arguing with that record.

## Setup

| | |
| --- | --- |
| Instrument | NQ 5-minute (true contract volume), 923 sessions; NQ 15m and US100 15m as cross-checks (US100's VWAP is on tick volume — a proxy) |
| Split | research first 65% of sessions / locked last 35%, cut 2024-11-27 |
| Base rule, as asked | fresh EMA13/48 cross (within 5 bars), long only while close > session VWAP and short only while below (VWAP as support/resistance, *state* reading), ATR(14) × 1.5 stop, trailing stop arming at 1.0 ATR and trailing by 1.0 ATR, no target, RTH entries 09:30–15:55, flatten 15:55, one position |
| Also swept | the cross as a *state* (EMA13 > EMA48), the VWAP as a *touch* (bounce off it), trail off, flatten off |
| Order model | the scalp89 kernel: fill next open, bracket live from the fill bar, Pine's intrabar path, position lock. Costs 0.86 pts a side, 0.25 slippage, $2/pt |

## The declared grid — 24 cells, read by marginal average

cross {fresh, state} × VWAP {off, state, touch} × trail {on, off} × flatten {on, off}, NQ 5m research.
**29.2% of cells net-profitable, median −0.0429 % of price per trade.**

| Axis | Setting | Mean %/trade | Mean PF |
| --- | --- | ---: | ---: |
| trail | **on** | **−0.0666** | **0.201** |
| trail | off | +0.0706 | 1.309 |
| flatten | on (intraday) | −0.0376 | 0.567 |
| flatten | off (hold overnight) | +0.0416 | 0.942 |
| VWAP | off | −0.0003 | 0.756 |
| VWAP | **state** | **+0.0286** | 0.873 |
| VWAP | touch | −0.0222 | 0.635 |
| cross | fresh | −0.0080 | 0.708 |
| cross | state | +0.0121 | 0.801 |

**The trail is the whole story.** Every one of the twelve trail-on cells is PF 0.15–0.23; every
trail-off cell is 0.83–2.43. The VWAP *state* gate is the one component with a positive marginal
(+0.03) and the *touch* reading is the worst. The only cells above PF 1.3 are all *no trail, no
flatten* — 99–224 trades at **1–3% win rates**, i.e. a handful of multi-day longs in a market that
rose 89%. That is not intraday and it is drift, the same artifact this branch has caught three
times this week.

## The ask as stated, and its ablations (research)

| Variant | n | %/trade | PF | Win | Exits |
| --- | ---: | ---: | ---: | ---: | --- |
| **as asked** | 873 | **−0.0659** | **0.208** | 29.0% | trail 59% · stop 38% · flat 3% |
| − no trail | 759 | +0.0027 | **1.020** | 29.8% | stop 65% · flat 35% |
| − no VWAP gate | 857 | −0.0654 | 0.208 | | |
| − no flatten | 873 | −0.0682 | 0.199 | | |
| − no trail, no flatten | 110 | +0.1584 | 1.718 | **0.9%** | stop 99% — one winning multi-day trade |
| longs only | 482 | −0.0574 | 0.293 | | |
| shorts only | 470 | −0.0748 | 0.126 | | |
| VWAP touch | 439 | −0.0716 | 0.154 | | |
| **zero cost** | 871 | −0.0538 | **0.277** | | not a cost problem |

The same arithmetic that broke the scalping system: a trail that arms at 1.0 ATR sits inside a
1.5 ATR stop, so 59% of trades exit on a small trail gain and 38% on the full stop. The stop
ladder 1.0 → 3.0 ATR runs −0.057 → −0.067 (all negative, flat); the trail ladder improves
monotonically as it *widens* (arm 0.5 / off 0.5: PF **0.03**; arm 2.0 / off 2.0: 0.77) and never
reaches no-trail. **Random-entry control, as asked: p 0.937, and the control's 5–95% band is
[−0.0664, −0.0563] — entirely negative.** The geometry loses on any entry; the rule is slightly
*worse* than random within it. No trail: p 0.163.

**Cross-feed:** as asked, PF 0.16–0.22 on NQ 15m and US100 15m on both blocks. No trail: NQ 15m
research 0.965 / locked **1.222** (n 225), US100 0.974 / 0.921. One positive cell of eight.

## Features

37 causal features in 8 declared families (cross geometry, VWAP, volatility, trend quality,
location, participation, clock, momentum), every one built from rolling / ewm / shift only.
**Truncation audit on 30 probe bars: 0 leaking columns.** 36 survive a 98% coverage floor.

## Deep learning on the as-asked base — the ladder it has to beat

Label = the R each base trade earned, read at the signal bar. 860 research trades, 430 locked.
Six sequential folds, **purged on trade lifetime and embargoed one session**. Every model beside
its **shuffled-label twin**. Base research: mean R **−0.367**, win 29.0%, PF 0.194, p90 +0.322.

| Model | Objective | OOF IC | AUC | keep-30% R | PF | p90 | twin keep-30% R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ridge | R | +0.043 | 0.556 | −0.374 | 0.249 | 0.413 | −0.302 |
| LightGBM | R | −0.002 | 0.513 | −0.386 | 0.201 | 0.345 | −0.371 |
| XGBoost | R | −0.012 | 0.523 | −0.348 | 0.251 | 0.401 | −0.375 |
| MLP 2×64 | R | +0.009 | 0.499 | −0.406 | 0.183 | 0.337 | −0.324 |
| **MLP 4×128** | R | **−0.038** | **0.470** | −0.410 | 0.204 | 0.357 | −0.349 |
| **logistic** | win/lose | **+0.141** | **0.625** | **−0.303** | 0.303 | 0.432 | −0.347 |
| LightGBM | win/lose | +0.103 | 0.616 | −0.314 | 0.296 | 0.425 | −0.369 |
| XGBoost | win/lose | +0.117 | 0.623 | −0.311 | 0.304 | 0.464 | −0.370 |
| MLP 2×64 | win/lose | +0.098 | 0.583 | −0.316 | 0.282 | 0.407 | −0.350 |
| MLP 4×128 | win/lose | +0.088 | 0.590 | −0.356 | 0.227 | 0.351 | −0.403 |

Three things, all already on this branch's record and reproduced:

1. **Capacity is monotonically harmful.** On the R objective the deepest net has the *worst* IC
   (−0.038, AUC 0.47 — below chance); on win/lose the MLPs sit under the linear model.
2. **The linear baseline wins the whole ladder.** Logistic regression has the best IC and AUC of
   all ten cells. No deep net beats it.
3. **The twin catches the regression side.** Against a same-selectivity random filter at keep-30%,
   ridge's *shuffled* twin scores p 0.026 while ridge itself scores p 0.562; MLP 2×64's twin p 0.080
   against its own p 0.872. When the noise floor outscores the model, the model has nothing. The
   classification side is the reverse — the real models beat their twins consistently (logistic
   p 0.032 vs twin 0.246; XGBoost 0.048 vs 0.516), so the win/lose classifiers carry a little real
   information.

**And that information cannot make the strategy profitable.** The best cell in the ladder keeps
30% of trades and earns **−0.30 R per trade at PF 0.30**. The base is PF 0.19; the best subset a
classifier can find inside it is PF 0.30. **The one locked read** (logistic, chosen on research
IC before the read): IC **+0.148**, AUC **0.660** — the classifier generalises — and keep-30%
reads **R −0.297, PF 0.315, win 40.3%** against a locked base of −0.353 / 0.195 / 27.9%, at
p 0.098 against a random filter. A win-rate optimiser, as V28 said: win rate 28% → 40%,
expectancy still deeply negative.

What ridge reads (top |coefficient|): distance of the close from EMA13 (−), distance from the
VWAP (+), RSI14 (−), the ATR 5/50 ratio (+), distance below the 20-bar high (−). Interpretable,
small, and not enough.

## Deep learning on the no-trail base — the fair test

The trail makes the as-asked base PF 0.19, and no filter can select a profitable subset of that.
So the same ladder was run on the base with the trail off — fresh cross, VWAP state, 1.5 ATR
stop, 15:55 flatten, nothing else changed — which is PF **1.052** on research (mean R +0.037, win
29.8%, **p90 +2.837**): break-even with a fat right tail. 748 research trades, 374 locked.

| Model | Objective | OOF IC | keep-30% R | PF | p90 | vs random filter | twin keep-30% R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ridge | R | +0.065 | +0.129 | 1.180 | 2.92 | p 0.298 | +0.146 |
| LightGBM | R | +0.054 | +0.131 | 1.184 | 2.59 | 0.292 | −0.247 |
| XGBoost | R | +0.072 | **+0.250** | 1.363 | 3.35 | **0.050** | +0.005 |
| MLP 2×64 | R | +0.087 | +0.156 | 1.235 | 2.96 | 0.222 | +0.078 |
| MLP 4×128 | R | +0.117 | +0.150 | 1.223 | 2.85 | 0.234 | +0.118 |
| **logistic** | win/lose | **+0.156** | +0.124 | 1.201 | 2.11 | 0.316 | +0.062 |
| LightGBM | win/lose | +0.149 | **+0.280** | **1.475** | 2.30 | **0.034** | +0.005 |
| XGBoost | win/lose | +0.130 | +0.157 | 1.254 | 2.30 | 0.216 | +0.056 |
| MLP 2×64 | win/lose | +0.103 | +0.078 | 1.116 | 2.72 | 0.420 | −0.137 |
| MLP 4×128 | win/lose | +0.109 | +0.254 | 1.384 | 3.42 | **0.050** | −0.056 |

Random filter at keep-30%: median +0.054, 5–95% **[−0.147, +0.246]** — a wide band, because the
base's return is in its tail and a random 30% either catches the tail trades or does not. On
research, **5 of 20 cells clear p ≤ 0.05 against 1 expected** (at keep-50%: MLP 4×128 win p 0.010,
XGBoost win 0.030; at keep-30%: LightGBM win 0.034, XGBoost R 0.050, MLP 4×128 win 0.050), and the
twins mostly do not. That is above chance, and it is the research block.

**The one locked read.** The rule fixed before the read — best research OOF IC — chose
**logistic win/lose (IC +0.156)**. On locked:

| | n | R | PF | p90 | vs random filter |
| --- | ---: | ---: | ---: | ---: | ---: |
| locked base, unfiltered | 374 | **+0.113** | **1.164** | +2.395 | — |
| logistic keep-50% | 187 | −0.092 | 0.859 | +1.830 | p 0.958 |
| logistic keep-30% | 112 | **−0.078** | **0.870** | +1.847 | p 0.844 |

The classifier still *ranks* on locked (IC +0.141, AUC 0.567) — and **the trades it ranks highest
lose money**. It keeps the high-win-probability trades and discards the low-probability ones, and
on a strategy whose return lives in a 2.4-R tail those are the same trades: p90 falls 2.40 → 1.85.
This is `STUDY_V28_ML_CAPACITY`'s mechanism reproduced line for line — *train on win/lose and you
get a win-rate optimiser; a trend system earns in the tail; read p90 of R, not AUC.* The cells
that cleared p ≤ 0.05 on research (LightGBM win, MLP 4×128 win, XGBoost R) were not read on locked,
because the rule was fixed to IC before any block was opened and one read is one read. They stay
as research-block observations: five passes in twenty, above chance, on the block that chose them.

Note also the base's own shape: locked PF 1.164 against research 1.052 — better out of sample
than in, which on this branch has been the defect every time it appeared.

What ridge reads on the no-trail base: RSI14 (**−0.78**, by far the largest), EMA13 slope (+0.51),
20-bar range position (+0.49), the 13/48 spread (+0.25). A momentum-*negative* reading at the
signal bar — the tenth route to mean reversion on this branch.

## Verdict

**No profitable intraday strategy was found, and the components the ask specified are the ones
that prevent it.**

1. **The trailing stop is destructive by arithmetic**, not by tuning: PF 0.201 across every
   trail-on cell of a 24-cell grid, a random-entry control band entirely below zero, and a trail
   ladder that improves monotonically as the trail *widens* and never reaches no-trail. The same
   mechanism that broke the previous strategy, on a different base.
2. **The 1.5 ATR stop is on the flat part of a negative curve** (1.0 → 3.0 ATR: −0.057 → −0.067
   with the trail on). V18's finding stands.
3. **Without the trail the intraday base is break-even** (PF 1.02–1.05), fails a random entry
   (p 0.163) and is positive on one cross-feed cell of eight. The VWAP *state* gate is the one
   component with a positive marginal (+0.03 %/trade); the *touch* reading is the worst.
4. **Feature engineering was clean** (37 causal features, 0 leaks) and **deep learning did what it
   has done on this branch every time**: on the as-asked base, capacity is monotonically harmful
   and logistic regression beats every net; on the no-trail base, five of twenty research cells
   beat a random filter and the pre-declared locked read inverts, turning a PF 1.164 base into a
   PF 0.87 subset by discarding the tail.
5. **The only cells above PF 1.3 anywhere are no-trail, no-flatten** — multi-day longs at 1–3%
   win rates in a market that rose 89%. Drift, not a strategy, and not intraday.

What would change it: a base that earns before a filter is applied, and an ML objective that is
the R itself with the tail preserved (the regression models here did not lose the tail — XGBoost R
kept p90 at 3.35 — but none of them was the pre-declared pick and none clears its twin cleanly).
Not another feature, and not a deeper net.
