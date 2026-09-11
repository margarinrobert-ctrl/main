# STUDY: Volume profile, TPO, EMA200, EMA 13/48 and ATR variables as features on the 07:00-11:00 scalp

**Ask.** Feature engineering with volume profile and TPO to forecast the ENTRY and the TAKE PROFIT of a
Donchian breakout scalp, with the EMA200 as support or resistance, the EMA 13/48 cross as momentum and
ATR(14) in several variables as the stop.

**Base.** NQ 15m, Donchian 10/10, 3.19 ATR stop, 2.3 ATR target, 230-minute hold, entries 07:00-11:00
New York, MNQ costs -- the Optuna finalist of `STUDY_BAYESOPT_SCALP.md`, research PF 1.164 / locked 1.110.
Research = the first 65% of sessions (to 2024-11-27); locked = the rest, read once.

**Code.** `research/inst/vp_tpo.py` (features + `walk_tp`, a per-bar-stop / per-bar-target walker
verified exact against the engine on 1,154 trades), `run_vp_scalp.py` (the battery), `run_vp_scalp2.py`
(ladder, co-selection, mechanism, years, bootstrap), `run_vp_scalp3.py` (drop-one), `vp_tpo_parity.py`
(the shipped Pine's profile diffed against the research feature). Outputs in `results/inst/vp_scalp*.txt`.
Ships `pine/inst/VP_TPO_SCALP_strategy.pine`.

## 1. Features: 45, all causal, audit-clean

| family | columns | source | audit |
| --- | --- | --- | --- |
| `vp.` 18 | prior-session POC / VAH / VAL / high / low distance, VA width, poor high/low, developing POC / VAH / VAL, position in prior VA, nearest HVN / LVN above and below, nearest naked POC above | `volprofile.build(window=(570, 960))` on the 1-minute file, mapped to the 15m bar that CLOSED before the 1m bar opened (`side="left"`; `side="right"` would carry the next minute's volume) | `volprofile.leakage_check` clean |
| `tpo.` 14 | prior-session POC / VAH / VAL / skew / nearest single print above; developing POC / VAH / VAL, single print above and below, IB high / low / range, above-IB | 30-minute letters from the 15m bars, 2.5-point bins, 70% value area expanded toward the larger neighbour, single print = a bin touched by exactly one letter | truncation audit 0 leaks, 27 columns x 16 probes |
| `ema.` 7 | EMA200 distance / touch / slope, EMA13>48 state, bars since cross, spread, spread slope | | clean |
| `atr.` 6 | ATR/price, ATR/ATR50, ATR/ATR250, vol percentile, bar range/ATR, TR/ATR | | clean |

Two things the audit caught before any P&L. (1) The first prior-session assignment ran only on days
that already had RTH bars, so a pre-open bar read NaN when the series was truncated at it and a value
when it was not -- 8 of 12 probes failed. The prior profile is now CARRIED bar by bar: before 16:00 a bar
reads the previous day's completed profile, from 16:00 the same day's. (2) The "session complete" test
was `last RTH bar is not the day's last bar`; on the ten early-close sessions (13:00 closes before
Thanksgiving weekend, Christmas, July 4th) the 13:00 bar IS the day's last bar, so those profiles were
never frozen and the next Monday read Wednesday's. Found by the Pine parity diff (99.4% -> 100.0%).

## 2. Base rates on the trigger's own bars

The momentum readings are the breakout restated again: `EMA13-48 spread rising` passes **87%** of the
signal bars, `EMA13 > EMA48` 74%, `EMA200 above` 77%. The profile readings mostly do NOT co-vary with
the trigger (lift 0.86-1.07 for HVN / LVN / VA width / naked POC / IB range), which is what makes them
testable filters rather than restatements -- and `close above developing VAH` / `above IB high` have lift
2.4 / 3.1 because a breakout bar is by construction near the top of the day.

## 3. Feature IC on the research trades (765), shuffled null sd 0.037

Five of 45 pass BH q 0.10 on Spearman(feature, realised R). Four are the ATR level (`atr.pct_price`
+0.27, `ratio250` +0.20, `vol_pct250` +0.18, `ratio50` +0.17) -- higher volatility, higher R, and lower
MFE **and** MAE in ATR at once, which is the ATR-denominator effect of `STUDY_V44` and not a forecast
(the same features as ENTRY conditions in §4 read +4 to +5% PF at p 0.06-0.10 for the floors and
-17 to -26% for the ceilings). The fifth is `tpo.prior_single_above_atr` at **-0.135**: the NEARER the
prior session's single print above, the better the trade. No EMA feature reaches |IC| 0.06. MFE and MAE
ICs correlate +0.67 across features -- maximising one and minimising the other is one axis (`STUDY_V44`).

## 4. Entry conditions: 43 declared, each against a random filter of the same selectivity, BH q 0.10

6 of 41 scorable clear p <= 0.05 against 2.1 expected; **1 passes BH**. By family (mean over cells):

| family | cells | mean dPF | mean p | beat control |
| --- | --- | --- | --- | --- |
| TPO | 8 | **+6.7%** | 0.26 | 25% |
| VP | 14 | +0.3% | 0.31 | 21% |
| EMA200 | 7 | -2.9% | 0.39 | 0% |
| EMA 13/48 | 6 | -5.4% | 0.70 | 17% |
| ATR | 6 | -6.9% | 0.48 | 0% |

**EMA200 as support or resistance: nothing.** Above (1.161, p 0.36), >= 1 ATR above (1.197, p 0.16),
>= 2 ATR (1.153, p 0.39), rising (1.196, p 0.20), touched within 5 bars (1.107, p 0.58), below
(1.167, p 0.24). The literal SUPPORT reading -- above and within 1 ATR -- is the worst cell in the family,
**PF 0.931**, p 0.75. Fourth time on this branch a "near the MA" reading loses to a distance floor.

**EMA 13/48 as momentum: every bullish reading LOWERS the profit factor.** State 1.105 (p 0.82), fresh
cross <= 5 bars 0.988 (p 0.82), <= 20 bars 0.996 (p 0.90), spread >= 0.5 ATR 1.082 (p 0.77), spread
rising 1.127 (p 0.86). The one reading that clears is the COUNTER-state, EMA13 < EMA48, PF 1.308 at
p 0.020 -- a breakout that fires while the fast average is still below the slow one is the early break,
which is `STUDY_TURTLE`'s "breakouts pay early in a trend" from a new direction. It fails BH and was not
read on locked; it ships as an input, default off.

**Volume profile: two developing-profile readings clear on research and fail BH.** Close above the
developing VAH (1.289, p 0.040, keeps 20%) and above the developing POC (1.248, p 0.048); "no HVN within
2 ATR above" (1.231, p 0.024, keeps 80%) is a near-unconditional filter. Prior-session levels do
nothing (VAH p 0.56, POC p 0.12, VAL p 0.14); an HVN within 1 ATR above is the worst VP cell, 0.844.

**TPO: the survivor.** `prior-session single print within 3 ATR above the close` -- research 350 trades
**PF 1.446, win 52%, +16.4%, Sharpe 2.84**, against a same-selectivity random filter's median 1.127,
**p 0.000**; its mirror reads 1.072 at p 0.91. Keeps 37% of the signal bars with lift 0.91, so it is not
the trigger restated. `close above IB high` reads 1.533 at p 0.044 on 92 trades (6%) -- too few.

## 5. Take profit: 37 rules, and no profile level beats the fixed 2.3 ATR

Fixed ladder on research: 1.0 ATR **0.944**, 1.5 0.997, 2.0 1.091, 2.3 **1.164**, 3.0 1.149, 4.0 1.019,
6.0 1.099, none 1.069 -- a hump at 2.3-3.0, the two rungs the search had already chosen. Every profile
level used as the target (prior VP VAH, nearest HVN, nearest naked POC, prior TPO VAH / POC / single
print, developing VAH / single print, IB high; each with a fixed fallback, a no-target fallback and a
4 ATR cap; plus the nearest-of-four) reads **1.03-1.14**. The IB high clears a random target drawn from
its own distance distribution (p 0.065 / 0.030 capped) -- it is a real level -- and still loses to the
fixed multiple (1.139 vs 1.164). **0 of 37 beat fixed on PF and total while clearing their null.** A
target reached 48% of the time at 2.3 ATR on a 3.19 ATR stop is the base's whole edge, and a level that
sits nearer than that gives it up.

## 6. Stop: 27 rules in three units

| rule | n | PF | %/trade | R/trade | total | DD | ret/DD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fixed 1.0 | 903 | 0.980 | -0.0017 | -0.070 | -1.5 | 6.7 | -0.2 |
| fixed 2.0 | 783 | 1.134 | +0.0150 | +0.025 | +11.7 | 5.5 | 2.1 |
| fixed 3.0 | 767 | **1.173** | **+0.0206** | **+0.029** | **+15.8** | 5.6 | **2.8** |
| fixed 3.19 (base) | 765 | 1.164 | +0.0197 | +0.026 | +15.0 | 5.5 | 2.7 |
| fixed 6.0 | 764 | 1.116 | +0.0146 | +0.005 | +11.1 | 7.0 | 1.6 |
| adaptive 4.0 calm / 2.5 hot (V22) | 770 | 1.163 | +0.0190 | +0.030 | +14.7 | 4.9 | 3.0 |
| adaptive inverted 2.0 / 3.19 | 772 | 1.143 | +0.0171 | +0.016 | +13.2 | 5.6 | 2.4 |
| 3.19 x ATR/ATR50 (wider when expanding) | 765 | 1.118 | +0.0147 | -0.003 | +11.3 | 6.7 | 1.7 |
| 3.19 / ATR/ATR50 (wider when contracting) | 779 | 1.128 | +0.0146 | +0.036 | +11.4 | 6.2 | 1.8 |
| 1.5 x signal-bar range | 784 | 1.106 | +0.0126 | +0.021 | +9.9 | 7.0 | 1.4 |
| below prior VP VAL | 770 | 1.145 | +0.0173 | +0.022 | +13.3 | 5.0 | 2.7 |
| below IB low | 767 | 1.139 | +0.0169 | +0.015 | +13.0 | 6.0 | 2.2 |
| below EMA200 | 767 | 1.175 | +0.0206 | +0.032 | +15.8 | 5.1 | 3.1 |
| below EMA48 | 780 | 1.110 | +0.0131 | -0.007 | +10.2 | 6.3 | 1.6 |

For once the three units agree: the fixed ladder peaks at **3.0 ATR** in %/trade, in R and in
return/drawdown, and 3.19 is one rung from it. A structural stop under a profile level is never better
than the fixed multiple it falls back to, because at this geometry it mostly IS the fallback (median
risk 3.19 in every structural row). "Below EMA200" ties the fixed 3.0 on research and reads 1.082 on
locked. The V22 adaptive direction (wide when calm) beats its inversion on every line, as V22 found, and
does not beat fixed.

## 7. The one locked read (152 things looked at on research: 43 + 37 + 27 + 45)

| | n | PF | win | total | Sharpe | DD | null |
| --- | --- | --- | --- | --- | --- | --- | --- |
| base | 389 | 1.110 | 48.8% | +6.0% | 0.73 | 7.8% | |
| **+ single print within 3 ATR above** | **187** | **1.382** | 50.8% | **+9.9%** | **2.02** | 4.7% | random filter median 1.109, **p 0.016** |

**+24.5% locked PF, the number `STUDY_SCALP_FILTERS` said was not a filter-sized effect.** It decays
across the split (1.446 -> 1.382), the right shape; it is positive in every calendar year (2023 PF 1.52,
2024 1.43, 2025 1.33 against the base's 1.24 / 1.14 / 1.07); more total money on half the trades. No
target rule and no stop rule earned a locked read against the base.

## 8. What it is, and what it is not

**The distance ladder is a hump, not a gradient.** Within 0.5 ATR PF 1.23 (p 0.18), 1.0 1.24, 1.5 1.27,
2.0 1.30 (p 0.010), **3.0 1.45 (p 0.000)**, 4.0 1.32 (p 0.000), 5.0 1.24, 6.0 1.26, 8.0 1.22; the mirror
falls below the base at every rung from 1.0 to 8.0. By band the 3-4 and 4-6 ATR bands are NEGATIVE in R
(-0.055, -0.082), so the 3 ATR ceiling is doing real work and it was chosen on research. Locked,
descriptive: 2.0 1.41, 3.0 1.38, 4.0 1.43, 5.0 1.31 -- the same hump.

**It is the single print, not "below yesterday's high" -- but it can only exist there.** A prior-session
single print above the close is inside yesterday's range, so the condition co-selects `close below the
prior RTH high` **100%** (the inverse of V17's gate, which on this base reads 1.144 at p 0.35 while below-
the-high reads 1.202 at p 0.16 -- neither is a filter). Drop-one:

| | research n / PF / p | locked (descriptive) n / PF / p |
| --- | --- | --- |
| below prior high AND single print <= 3 ATR above | 350 / **1.446** / 0.000 | 187 / **1.382** / 0.017 |
| below prior high AND NO single print <= 3 ATR | 230 / 1.035 / 0.71 | 94 / 0.809 / 0.97 |
| below prior high AND a single print > 3 ATR | 186 / 1.021 / 0.70 | 81 / 0.820 / 0.94 |
| below prior TPO VAH AND single print <= 3 | 235 / 1.512 / 0.000 | 116 / 1.766 / 0.000 |
| above prior TPO VAH AND single print <= 3 | 151 / 1.263 / 0.14 | 89 / 0.887 / 0.88 |

Below yesterday's high WITHOUT a near single print loses on both blocks. The last two rows are the
locked block read twice more after the declared read and are recorded, not selected on: the cell that
looks best there (below the VAH with a single print overhead, locked 1.77) is exactly the spike
`STUDY_V54` warned a post-hoc split produces.

**Mechanism.** Inside the condition the fixed-horizon MAE is **3.69 ATR against 4.44** outside with MFE
unchanged (4.11 / 4.06), the target is reached 50% against 47% and the stop 45% against 49%: the breakout
is heading into a zone yesterday's auction traversed inside one 30-minute letter -- no acceptance
overhead, nothing to sell into -- and it takes less heat on the way. It is the auction-theory reading of
a "vacuum", and it is a LEVEL feature, which is the family (`STUDY_V17`'s prior-session high, V51's
MA200 floor, V58's IB retracement) that has carried the branch's few survivors.

**Caveats that stay attached.** One survivor of 43 at BH q 0.10 (6 at p <= 0.05 against 2.1 expected)
on ONE market and ONE geometry; locked n 187; day-block bootstrap **P(mean <= 0) 0.056** with a 95% CI of
[-0.012, +0.122] %/trade, so it does not clear zero at 0.05 even though it clears its matched control
(`STUDY_V15_BOOK`'s two questions); MC p99 drawdown **13.1% against a realised 4.7% (2.8x)** -- the
sizing number; the realised path sits at the 45th percentile of its own permutation. US100 / US30 are
15-minute feeds here and cannot supply the 1-minute volume profile, so the VP half has no cross-market
read; the TPO half could be run on them and has not been.

## 9. Shipped

`pine/inst/VP_TPO_SCALP_strategy.pine`: the base with the TPO profile built from the chart's own bars
(30-minute letters, 2.5-point bins on an absolute grid, frozen at 16:00 New York or at the next RTH open
when the 16:00 bar is missing). The single-print gate is ON. EMA200 (five readings), EMA 13/48 (three),
the stop (fixed / adaptive / below EMA200 / below prior VAL) and the target (fixed / none / IB high /
prior VAH / prior single print) ship as inputs, default at the base, each tooltip carrying its research
number. `research/inst/vp_tpo_parity.py` transliterates the Pine's profile arrays bar by bar: prior
single print, POC, VAH, VAL and IB high agree with the research feature on **100.00% of 70,685 bars**,
and the gate itself on 100.000% (31,151 true bars both ways).
