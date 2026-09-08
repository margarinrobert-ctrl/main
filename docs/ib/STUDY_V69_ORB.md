# Loadish Starboard multi-session ORB — the Pine's report is gross, and the session choice is the strategy

`research/v69/`. Multi-session opening-range breakout, transliterated from the supplied Pine and run
on the uploaded 15-minute Nasdaq file, 2016-11 → 2025-10.

## Four things established before any optimisation

**1. The uploaded file is already in the registry.** sha256 prefix `c449dddfbc06a943`, 11,971,933
bytes, 206,703 rows — byte-identical to `US100_LONG_15m`, which `research/v13/*`, `v14/*`, `v15/*`,
`STUDY_V38`, `STUDY_V41` and `STUDY_V60` have all read. **There is no unread block on it.** Every
out-of-sample figure below is a second read and is descriptive.

**2. The clock is New York + 7, not New York.** Re-derived rather than trusted: mean bar range peaks
at minute-of-day 990 = 16:30 file time = 09:30 New York. The session resolution confirms it — Asia's
range candle lands at file minute 120/180 and London's at 600/660 (two values each, because JST and
London shift against NY's DST), while **NY lands at 990 every single day**. Reading the stamps as
New York would put the NY range candle at 02:30.

**3. The VIX filter cannot be reproduced and it ships ON.** `useVixFilter` defaults true at a 17.00
ceiling, gating every session at the range close. `data/VIX_daily.csv` ends 2021-12-31 while this
feed runs to 2025-10, and CLAUDE.md records the VIX cannot be joined to any futures feed here. Every
number below describes the rule **minus its shipped volatility gate**. That is a real gap.

**4. It is US100, a CFD, not MNQ.** Scored in percent of entry price; MNQ's 1.72-point all-in round
turn charged in points.

## The arithmetic, before the backtest

`riskReward` ships at **0.8**, so the target is *closer* than the stop and the driftless break-even
win rate is 1/(1+0.8) = **55.6%**. That is the number to beat before any data is read.

## The shipped configuration

| | n | win% | need | PF | %/trade | total | maxDD |
|---|---|---|---|---|---|---|---|
| **GROSS (as the Pine reports it)** | 6,163 | 55.2% | 55.6% | **1.064** | +0.0084 | **+51.60** | 16.91 |
| **NET (MNQ 1.72 pt round turn)** | 6,163 | 54.1% | 55.6% | **0.938** | −0.0086 | **−53.16** | 74.35 |

**The Pine sets `commission_value = 0` and `slippage = 0`, so its own Strategy Tester report is
gross.** Charged real costs it loses over nine years, and the win rate lands 1.5 points below what
its own geometry demands. Exits: 47.5% target, 35.2% stop, 17.3% session flat.

The cost stress makes the dependency exact:

| cost (pts) | shipped research / locked |
|---|---|
| **0.00 (the Pine's setting)** | **+17.12 / +34.48** |
| 0.86 | −23.89 / +23.11 |
| **1.72 (real MNQ)** | **−64.90 / +11.74** |
| 3.44 | −146.93 / −10.99 |

**Everything the script appears to earn is the zero-cost setting.**

## Only New York works, and the reason is arithmetic

| session | n | win% | PF | median range | risk % of price |
|---|---|---|---|---|---|
| Asia | 2,044 | 52.8% | **0.784** | 12.8 pts | 0.189% |
| London | 2,047 | 53.3% | **0.804** | 17.7 pts | 0.243% |
| **New York** | 2,072 | 56.0% | **1.052** | 50.7 pts | 0.617% |

Asia and London ranges are 3–4× narrower, so the same fixed 1.72-point cost is ~6% of an Asia stop
against ~1.8% of an NY stop. This is `STUDY_TURTLE_15M`'s lesson — **a cost is a fraction of risk,
not a number of points** — and the script's own Range Percentile comment anticipates the shape of it
without drawing the conclusion.

## Optuna — the session choice is 100% of the objective

1,200 TPE trials over the script's own inputs, research block only (first 65% of session instances),
every trial's locked result logged and never selected on.

**fANOVA: `s_ny` 0.729, `s_london` 0.147, `s_asia` 0.124.** R:R, both range filters, the percentile
filter, the two conviction tests and the entire weekday grid are collectively irrelevant.

| sessions traded | research %/trade | locked %/trade |
|---|---|---|
| **NY only** | **+0.0836** | **+0.0368** |
| Asia + NY | +0.0475 | +0.0163 |
| London + NY | +0.0378 | +0.0117 |
| all three (shipped) | +0.0256 | +0.0045 |

Monotone on both blocks. The R:R marginal agrees with the arithmetic: 0.3–0.8 gives +0.002 research
and **−0.004 locked**, while 2.5–5.0 gives +0.068 / +0.028.

**And the population still says do not select.** 96.8% of trials are research-profitable, and
although `corr(research, locked)` is +0.489 — the highest seen on this branch — the **top 1% by
research transfers to +0.0228 against the whole population's +0.0274**. Worse than the average
trial, for the third study running.

**The weekday grid is a lottery.** Best setting per day, by research: Mon `Short` +0.100, Tue
`Short` +0.069, Wed `Long` +0.081, Thu `Off` +0.107, Fri `Both` +0.071 — five different answers
with sample sizes from 45 to 991. The shipped `Mon = Long` buys 12 points over nine years on 6,163
trades. CLAUDE.md bans calendar conditions from search for exactly this reason.

## The control — and a control bug worth more than the result

Every configuration was scored against a **random entry bar inside the same session**, same side
mix, same opposite-ORB-edge stop, same R:R.

**The first version of that control earned +0.14 to +0.17% per trade and beat every rule at
p 1.000.** That is implausible, and the cause was `STUDY_V10`'s artifact: a random bar can sit
*beyond* the opposite ORB edge, so for a long entered below `ol` the "stop" is a resting order on the
**profitable** side, which fires on the next bar and books a guaranteed win. **A stop on the wrong
side of the market is not a stop.** Guarded, the control becomes sane — and the answer inverts:

| configuration | block | rule | control | excess | p |
|---|---|---|---|---|---|
| shipped | research | −0.0163 | −0.0184 | +0.0021 | **0.385** |
| shipped | LOCKED | +0.0054 | −0.0112 | +0.0167 | 0.005 |
| NY only, RR 0.8 | research | −0.0138 | −0.0100 | −0.0038 | **0.650** |
| NY only, RR 0.8 | LOCKED | +0.0590 | +0.0005 | +0.0584 | 0.000 |
| NY only, RR 3.0 | research | −0.0038 | −0.0055 | +0.0017 | **0.435** |
| NY only, RR 3.0 | LOCKED | +0.0717 | +0.0086 | +0.0631 | 0.005 |

**Every configuration fails on research and clears on locked.** A rule chosen on research should
look better *there*; this branch has recorded that shape as a defect fourteen times now.

## The rest of the battery

**Monte Carlo** (NY only, RR 3.0). Research: mean −0.0038, 95% CI [−0.044, +0.038], **P(mean≤0)
0.59** — indistinguishable from nothing. Locked: mean +0.0717, CI [+0.019, +0.127], P(mean≤0) 0.0030.
Permutation puts the realised drawdown at percentile 0.26 / 0.40 with **p99 at 2.00× / 1.98×
realised** — the sizing number.

**Deflation.** The research-block Sharpe is **negative** (−0.0049) against an expected best-of-noise
of 0.138 over 1,146 counted looks. There is nothing to deflate; the candidate fails before the
correction is applied.

**vectorbt failed transcription — 1,574 trades against 2,072, ratio 0.760.** Fifth failure on this
branch, and structural rather than tuning: this strategy's stop is an **absolute per-session level**
(the opposite ORB edge) while vectorbt 1.1.0 accepts only a **fraction of price** resolved against
the bar close, and it has no session concept, so the "flat at session end" exit — **17% of trades** —
has no expression at all. An engine that cannot represent a third of the exit logic is not an
independent check of it. **No P&L gap was read.**

## Verdict

The strategy as shipped is **net-negative over nine years** on the index it targets, and its
apparent profitability in the Pine's own tester is the zero-cost setting. The one real finding is
structural and worth keeping: **two of its three sessions are unprofitable for an arithmetic reason**
— their ranges are too narrow for a fixed cost — and the optimiser independently identifies the
session choice as the entire objective.

But **NY-only does not survive its own null on the block allowed to choose it** (p 0.435), its
research bootstrap sits at P(mean≤0) 0.59, and it clears only on a block that has been read many
times before. So the honest recommendation is not "trade NY only". It is: **the session split is
real, the edge is not demonstrated**, and the two changes that are defensible on arithmetic alone
are to drop Asia and London, and to stop reading a zero-cost backtest.
