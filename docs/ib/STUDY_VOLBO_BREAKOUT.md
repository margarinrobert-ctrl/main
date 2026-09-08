# The CrackingMarkets intraday volatility breakout — the day selection is real, the entry is the worst part of it

The rule, verbatim: daily ATR(5); long at `open + 0.4×ATR`, short at `open − 0.4×ATR`; stop at the
session open (so risk is exactly 0.4×ATR); one long and one short attempt per day; exit at the stop
or at the close; no target; 0.33% of the account per trade. The article reports **27%/yr, −32% max
drawdown and Sharpe 1.04** over six markets (SPY, IWM, QQQ, GLD, USO, DIA) from 2018.

## What the uploads are

All three files are **byte-identical to feeds already in the registry**: `nasdaq_20252016_15m`
(sha `c449dddfbc06a943`) is **US100_LONG_15m** — US100, not the Nasdaq future, which the registry
established by measurement — `us30_20162025_15m` is **US30_LONG_15m**, and the RTF is
**US30_ISO_15m**, a different provider. Neither long feed carries an unread block. US30_ISO
(2024-08 → 2026-08) is the closest thing to reserved and was held back until last and read once.

A six-market portfolio containing two non-equities cannot be reproduced from two correlated equity
indices, so the headline number is not the thing under test. What is testable is whether the
mechanism is present here at all.

## The finding that mattered most was a bug in my own harness

The stop sits at the session open and the entry 0.4×ATR above it, so on a 15-minute bar the entry
and the stop can fall inside one bar. This branch's convention is to resolve that as a stop and
report the share. Doing so gave **PF 0.69–0.76 and a solidly losing strategy**, with an ambiguous
share of 18–19%.

**That convention is flatly wrong on the session's first bar.** The first bar *opens at* the stop,
so its low is at or below the stop with probability 1 and the flag carries no information at all
about the post-entry path. Measured: **100.0% of first-bar entries are flagged, and they are 12.4–
12.9% of all trades.** Excluding them, the genuine ambiguous share is 6.3%.

Rather than pick a convention, it was **settled on NQ 1-minute data** — the same rule, the same
sessions, resampled to 15m so only the intrabar resolution differs:

| bars | n | first-bar entries | ambiguous | bar range / risk |
|---|---|---|---|---|
| **1 minute** | 683 | 0.000 | **0.000** | 0.187 |
| 15 minutes | 683 | 0.108 | 0.176 | 0.671 |

**At one minute the ambiguous share is exactly zero** — not one trade has the entry level and the
stop touched in the same minute, because the stop is 0.4 of a *daily* ATR away and no single minute
spans that. So the entry bar never stops out, and the 15-minute convention that reproduces the
truth is the optimistic one:

| bars | convention | win | PF | %/trade | vs the 1-minute truth |
|---|---|---|---|---|---|
| 1m | **true path** | 0.476 | **1.226** | +0.0485 | — |
| 15m | blanket pessimism | 0.398 | 0.788 | −0.0544 | **−0.1029** |
| 15m | skip the first bar | 0.449 | 1.033 | +0.0076 | −0.0408 |
| 15m | entry bar cannot stop | 0.476 | **1.226** | +0.0485 | **+0.0000** |

Trade-for-trade the optimistic reading matches at **correlation 1.0000 with 100% identical exit
reasons**, which is expected by construction once entry-bar stops are ruled out. **The convention
alone was worth 0.1029 %/trade — more than twice the entire edge — and flipped the strategy's
sign.** For this geometry a 15-minute bar is a perfectly adequate resolution; the article's
1-minute data buys nothing.

## Gate 1 — the rule as published

| feed | block | n | win | needs | PF | %/trade | Sharpe (daily, 0-filled) |
|---|---|---|---|---|---|---|---|
| US100 | research 2016–22 | 1,338 | 0.457 | 0.452 | **1.020** | +0.0055 | +0.105 |
| US100 | locked 2022–25 | 709 | 0.471 | 0.428 | **1.190** | +0.0473 | +0.898 |
| US30 | research | 1,286 | 0.450 | 0.445 | **1.023** | +0.0045 | +0.116 |
| US30 | locked | 683 | 0.439 | 0.419 | **1.084** | +0.0157 | +0.413 |
| NQ (1-minute) | 2022–25 | 683 | 0.476 | 0.425 | **1.226** | +0.0485 | — |
| **US30_ISO** | **forward, other provider** | 474 | 0.430 | 0.440 | **0.963** | −0.0071 | −0.296 |

There is no target, so the break-even is set by the realised payoff ratio (1.2–1.4) rather than by
1/(1+RR). The rule clears it by half a point on research and by four on locked.

**Cost is not the objection, which is rare here.** The round turn is **1.5–3.2% of the stop**,
because the stop is 0.4 of a daily ATR. Gross PF is 1.07–1.24 against net 1.02–1.19, and the rule
survives 2× costs on three of four blocks. Every other intraday family on this branch died on the
cost floor; this one does not.

## The breakout level is the worst part of the rule

Against a **risk-matched random entry on the same days and the same sides** — stop placed 0.4×ATR
from that entry, same close exit, so the risk distribution is matched trade for trade:

| feed | block | rule | random, same days | p | random, all days | p |
|---|---|---|---|---|---|---|
| US100 | research | +0.0055 | **+0.1557** | 1.000 | −0.0099 | 0.010 |
| US100 | locked | +0.0473 | **+0.1435** | 1.000 | −0.0099 | 0.000 |
| US30 | research | +0.0045 | **+0.1121** | 1.000 | −0.0055 | 0.020 |
| US30 | locked | +0.0157 | **+0.1058** | 1.000 | −0.0055 | 0.000 |

Read the two columns together. **Day selection is worth +0.11 to +0.17 %/trade; the timing is worth
−0.09 to −0.15.** Days on which price travels 0.4×ATR from the open are days that trend, and
entering *anywhere* on them beats entering at the level. This is `research/atme/`'s finding —
chasing a breakout is the most reliably destructive choice measured on this branch — and
`STUDY_V43`'s, that a breakout enters at the top of its own range, reached from a third direction.

That control is **not a tradeable alternative**: the day is in the sample *because* the level broke,
so a random bar can precede the break and knows something the trader does not. The feasible version
— having seen the break, enter at a random later bar — **splits and the splits disagree**:

| feed | research | locked | forward |
|---|---|---|---|
| US100 | **fail** p 0.850 | pass p 0.000 | — |
| US30 | pass p 0.010 | **fail** p 0.212 | p 0.470 |

The feed that passes on research fails on locked and vice versa. That is noise, not a mechanism.

## Always-in beats it

Buy the open, sell the close, every session, no stop, no ATR, no shorting:

| feed | block | rule %/session | always-in | rule Sharpe | always-in Sharpe |
|---|---|---|---|---|---|
| US100 | research | +0.0049 | **+0.0095** | 0.105 | **0.137** |
| US100 | locked | +0.0425 | **+0.0564** | **0.898** | 0.807 |
| US30 | research | +0.0039 | **+0.0060** | 0.116 | 0.116 |
| US30 | locked | +0.0141 | **+0.0283** | 0.413 | **0.563** |
| US30_ISO | forward | −0.0065 | **+0.0239** | −0.296 | — |

**Always-in wins on total return on all five blocks** and on Sharpe on three of five. The strategy's
defence is a smaller drawdown on two blocks of four, which is what capping risk at 0.4×ATR buys.

## The account, at the article's own sizing

| feed | block | trades/yr | CAGR | max DD | Sharpe |
|---|---|---|---|---|---|
| US100 | research | 227 | +3.14% | 8.65% | +0.550 |
| US100 | locked | 226 | +5.97% | 5.92% | +1.012 |
| US30 | research | 218 | +1.11% | 7.87% | +0.229 |
| US30 | locked | 227 | +2.81% | 5.62% | +0.500 |
| **US30_ISO** | **forward** | 226 | **−1.81%** | 7.43% | **−0.296** |
| both indices, 0.33% each | full | — | +5.64% | 11.38% | +0.626 |

Against the article's 27%/yr at Sharpe 1.04. The two legs correlate **+0.375** in daily R, so two
equity indices buy very little diversification; the article's GLD and USO are doing work that
nothing here can represent, and that is the most likely honest explanation of the gap.

## Everything else that was checked

**No block's day-block bootstrap excludes zero.** Best is US100 locked at P(mean≤0) 0.061; US100
research 0.404, US30 0.393 / 0.232, forward 0.628.

**The 0.4 multiple inverts between feeds.** On US100 the marginal rises monotonically to 0.8 (+0.0425
research, +0.0827 locked) and 0.4 is the *worst* rung; on US30 it falls off a cliff at 0.8 (−0.0284)
and 0.4 is among the best. The ATR period is close to inert (3/5/10/14/20 span 0.010 %/trade),
which matches the author's own claim — for the period, not for the multiple. `corr(research, locked)`
across the 70-cell grid is **+0.189 on US100 and −0.043 on US30**.

**The author's own named enhancement does not reproduce.** A causal ATR percentile floor, tested as
one declared condition against a same-selectivity random filter, re-simulated as a veto: **0 of 8
rungs clear** (best p 0.150), and on US100 every rung is worse than no filter.

**Concurrency is a non-issue and the reason is structural.** Two trades occur on 11.3% of sessions
but both are live at once on **0.1%** of US100 sessions and **0.0%** of US30's — because
`dn < open < up` with the stop *at* the open, so the short trigger is unreachable while a long is
open without the long having stopped first. The article's "0.66% max per market per day" is
therefore almost never realised.

**Year by year** the profile is long-volatility: US100 7/10 years positive, US30 6/10, NQ 3/3,
US30_ISO 1/3, with 2018 (+25.7 / +18.0) and 2022 (+20.7) carrying it and **2020 at −34.1 on US100**.

## Pine parity

| feed | trades | same exit bar | correlation | gap |
|---|---|---|---|---|
| US100 | 2,047 / 2,047 (1.000) | 0.9971 | 0.9977 | +1.5% |
| US30 | 1,968 / 1,969 (0.999) | 0.9990 | 0.9970 | +5.3% |

Two order-model differences are worth their own line. **The end-of-day convention is 25–84% of the
result**: `strategy.close_all()` cannot sell the close of the bar that triggers it, so the script
exits at the next bar's open, which is worth −0.0051 %/trade on US100 and **+0.0070 on US30** — a
large fraction of a small edge, with no consistent sign. And **protecting the fill bar destroys the
strategy** (+0.0149 → −0.0913 on US100), confirming the 1-minute tie-break finding from the script
side.

## Verdict

The mechanism is **real but small, and the article's own entry is the weakest part of it**. Days
that travel 0.4×ATR from the open do trend — that is worth +0.11 to +0.17 %/trade against entering
on a random day — but entering *at the level* gives back −0.09 to −0.15 of it, and what remains does
not separate from zero on any block, loses to buying the open and holding, and **is negative on the
one genuinely forward block from a different provider**.

It is not refuted as published: six markets across two asset classes from 2018 is a different test,
the diversification is doing real work there, and the sample the author trades includes GLD and USO
which are uncorrelated with anything here. But on two correlated equity indices over nine years it
delivers 1.7–4.1%/yr at Sharpe 0.3–0.7, not 27% at 1.04.

The two things worth keeping are methodological: **an intrabar convention was worth twice the entire
edge and had to be settled on finer data**, and **the level that finds the day is not the place to
enter it**.
