# US30 07:00-11:00 New York: the arithmetic before the rule

Asked to improve a 07:00-11:00 US30 scalp. This branch has attacked that exact cell four times
already (`STUDY_DL50`, `STUDY_MR30`, `STUDY_VP_DONCHIAN_US30`, `STUDY_SCALP_REQUIREMENTS`), so
rather than a fifth search the question was put arithmetically first: **what does a scalp need
here, and what does the window actually deliver.** `research/us30scalp/`.

## 0. The data decides more than the rule does

`python research/datasets.py`: **`US30_1m` is MISSING.** The finest US30 series on disk is
`US30_LONG_15m` (193,942 bars, sha256 24dcf2e1c7ba398f, verified identical to the studied copy), so
**a 07:00-11:00 session is SIXTEEN BARS**. Everything below inherits that — the true 1-minute exit
path cannot be walked (`STUDY_ATME_LIVE` cut a result fivefold on exactly that), and any barrier
pair tight enough to sit inside one bar is decided by the tie-break rather than by the market.

Blocks: A = US30L before 2023-01-01, B = the rest, C = `US30_ISO_15m` after 2025-07-16 — a
DIFFERENT PROVIDER over a span no search here has touched. A and B are heavily spent (six studies)
so a p-value there is descriptive; C is the only genuinely unread one.

## 1. What the geometry costs

Median in-window ATR(14) is **31.17 points** on a 26,542 index; the round turn is 2.29 points =
0.0086% of price.

| stop | risk (pts) | cost / risk | break-even win | driftless | cost costs |
|---|---|---|---|---|---|
| 0.5N | 15.6 | **14.69%** | 57.35% | 50% | 7.35 pts |
| 0.75N | 23.4 | 9.80% | 54.90% | 50% | 4.90 |
| 1.0N | 31.2 | 7.35% | 53.67% | 50% | 3.67 |
| 1.5N | 46.8 | 4.90% | 52.45% | 50% | 2.45 |
| 2.0N | 62.3 | 3.67% | 51.84% | 50% | 1.84 |
| 2.5N | 77.9 | 2.94% | 51.47% | 50% | 1.47 |
| 3.0N | 93.5 | 2.45% | 51.22% | 50% | 1.22 |

Against what the population delivers (resolved win rate, every in-window bar, research block):

    0.5N   break-even 57.35%   actual 43.21%   short by 14.1 points
    1.0N              53.67%          47.68%           6.0
    1.5N              52.45%          48.26%           4.2
    2.0N              51.84%          49.03%           2.8
    3.0N              51.22%          49.20%           2.0

**The shortfall narrows monotonically as the barriers widen and never closes.** That is the
frontier: the tighter the scalp, the further from break-even it starts, and the mechanism is
measured rather than asserted.

## 2. At scalp geometry the verdict is not knowable on this data

**14.0% of 0.5N/0.5N trades touch both barriers inside one 15-minute bar.** Resolved stop-first —
this branch's convention — and target-first, on the identical population:

| geometry | ambiguous | stop-first | target-first | **spread** | stop-first PF | target-first PF |
|---|---|---|---|---|---|---|
| 0.5N/0.5N | 14.03% | -4.764 | +0.510 | **5.274 pts** | 0.604 | **1.056** |
| 0.75N/0.75N | 6.83% | -3.731 | -0.194 | 3.537 | 0.766 | 0.986 |
| 1.0N/1.0N | 4.19% | -3.224 | -0.746 | 2.478 | 0.838 | 0.960 |
| 1.5N/1.5N | 1.69% | -2.968 | -1.673 | 1.295 | 0.888 | 0.935 |
| 2.0N/2.0N | 0.69% | -2.751 | -2.188 | 0.564 | 0.914 | 0.931 |

**The convention flips the sign at scalp geometry** — PF 0.604 against 1.056 — and is worth 5.27
points a trade, which is larger than any edge on offer anywhere in this study.
`STUDY_VOLBO_BREAKOUT` settled the same question by dropping to 1-minute bars and finding the
ambiguous share was exactly 0.000; here that is impossible because `US30_1m` is absent. **So a
sub-1N barrier result on US30 is a statement about the tie-break, not about the market**, and no
amount of filtering changes which of the two numbers is true.

## 3. No declared trigger beats the population it sits in

Seven declared triggers (Donchian 20 and 10 both sides, the `STUDY_MR30` displacement fade at two
settings, EMA 13>48) x three measurable geometries, research block only, each against a matched
random entry drawn from the same eligible in-window bars, 400 draws, sorted so the position lock
rejects the same share:

**0 of 21 cells clear p <= 0.05 where 1.1 are expected by chance, and every one of the 21 is
unprofitable.** Best in the table is `donch20 long 1.5N/1.5N` at **-0.983 pts, p 0.155** — it beats
a control that loses 2.83, which is `STUDY_IB_US30_OPTUNA`'s sentence again: *a rule that beats a
losing null is still a losing rule*.

The sides split as drift predicts and not as a signal would: longs beat their controls in 8 of 9
long cells, shorts lose to theirs in every short cell. And always-in long in the window is negative
at all three geometries (-3.22 / -2.97 / -2.75 pts), so there is no drift to harvest here either at
a symmetric barrier pair.

## 4. What the window DOES support is not a scalp

175-cell declared geometry sweep (5 stops x 5 targets including NO TARGET x 4 hold caps x flatten
on/off) on the Donchian 20 long, research only, read by MARGINAL AVERAGE:

| axis | best setting | marginal pts | worst setting | marginal pts |
|---|---|---|---|---|
| target | **NO TARGET** | **+1.707** | 1.5N | -1.291 |
| stop | 1.5N | +0.831 | 3.0N | -0.942 |
| flatten | **OFF** | +0.147 | ON | -0.740 |
| hold cap | 16 bars | -0.137 | none | -0.616 |

No target is the only positive setting on its axis — the **25th** time on this branch — and the
flatten is negative, the **16th**. The marginal consensus is **1.5N stop, no target, 16-bar cap, no
flatten**, and it reads research **+4.05 pts / PF 1.110 / 32.4% win / median hold 105 MINUTES**.

**That is not a scalp.** It is a morning-entered swing trade with no target that runs into the
afternoon, and it is what the window supports precisely because widening the barriers is the only
thing that moved the arithmetic in §1.

One read, and it inverts:

| feed | block | n | pts | PF | control p | always-in |
|---|---|---|---|---|---|---|
| US30L | A research | 1043 | +4.047 | 1.110 | 0.168 | -0.026 |
| US30L | B holdout | 484 | **-5.494** | 0.886 | 0.853 | +1.854 |
| US30I | **C forward** (different provider) | 230 | -0.516 | 0.992 | 0.568 | -1.883 |

It clears no control on any block, and on the holdout **always-in beats it** (+1.854 against
-5.494). Cost is not the objection for this cell — at ZERO cost it still reads PF 1.181 on research
and the whole cost ladder (0x through 2x) stays positive there — so what fails is the transfer, not
the friction.

## 5. The one component that helped on both blocks is the window itself

Donchian 20 long at 1.5N/1.5N, window and flatten separated, because `STUDY_V61_SESSION` showed
they are different questions:

| configuration | research | holdout |
|---|---|---|
| all hours, no flatten | -0.232 (PF 0.991) | -2.814 (PF 0.903) |
| **07-11 window, no flatten** | **+0.707 (PF 1.025)** | **-0.704 (PF 0.980)** |
| 07-11 window + flat 11:00 | -0.983 (0.959) | -0.234 (0.992) |
| all hours + flat 11:00 | -2.151 (0.907) | -3.665 (0.850) |

**Restricting to 07:00-11:00 improves the rule on BOTH blocks** (+0.94 pts research, +2.11 pts
holdout) — the window is worth keeping. The FLATTEN is mixed (-1.69 research, +0.47 holdout), which
is a weaker version of the branch's standing finding rather than a contradiction of it.

Hour by hour inside the window, population long at 1.5N/1.5N: on research **10:00-11:00 is the only
positive hour** (+0.046 pts, PF 1.002) and 07:00-08:00 the worst (-3.062), reproducing
`STUDY_TREND_PULLBACK` exactly — and on the holdout it INVERTS, 10:00-11:00 going to -2.422 while
09:00-09:30 becomes the best. Sixth time a session preference has failed to transfer here.

## Verdict

The 07:00-11:00 US30 window is not what is wrong; **the scalp geometry is**, and on 15-minute bars
it is not even measurable.

- **A scalp needs a win rate this population does not have.** At 0.5N the break-even is 57.35% and
  the population delivers 43.21% — 14 points short, on a cost that is 14.7% of the risk. Widening
  closes the gap monotonically to ~2 points at 3.0N and never past it.
- **Below 1N the tie-break decides the answer**, and the two conventions disagree in sign
  (PF 0.604 vs 1.056, a 5.27-point spread). `US30_1m` would settle it; it is absent.
- **Nothing in the declared pool beats a matched random entry** — 0 of 21, every cell losing.
- **What the window supports is a 105-minute no-target trade**, and even that inverts out of sample
  and clears no control on three blocks including a different provider.
- **Keep the window, drop the scalp.** 07:00-11:00 improved the base on both blocks; the barriers,
  the target and the flatten are what took it apart.

What would move it, in order: **1-minute US30 bars** (settles §2 and unlocks the true exit path),
then a cheaper round turn — at 0.5N the fee is 14.7% of risk, so the 2.29-point assumption is
carrying the whole scalp verdict and no feed here can check it.
