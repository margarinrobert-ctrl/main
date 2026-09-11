# V64 walk-forward on the V61 CVD rule

`research/v64/run_wfo.py`, `run_wfo2.py`, `run_wfo3.py`, `run_wfo4.py`; `results/v64/wfo*.txt`.

## Verdict

**Selecting from this family beats picking from it arbitrarily. Re-selecting every fold does not
beat never selecting at all.** Those are different claims and only the first holds in both
schemes. Over all nine test folds the shipped 15-minute preset wins both schemes (+34.27% against
a re-chosen +28.20% rolling and +24.50% expanding), and a random cell from the same grid earns
+8.28%.

The one genuinely good result: on the walk-forward's out-of-sample span **all three arms clear a
random-entry control with identical geometry at p 0.000**.

## Design

The selection is re-run **inside every training window** and only the test window is read —
`STUDY_EDGELAB` recorded that a walk-forward whose parameters were chosen on the whole training
span is contaminated, and that rolling folds inside a discovery block showed 5/6 positive and
meant nothing.

| | |
| --- | --- |
| Grid | 19,200 declared cells: timeframe (15/30/60) × entry channel (15/20/30/40/55) × exit (10/20/30/40) × stop (1.5–3.0 ATR) × target (none/3/4/6 ATR) × pivot k (2–5) × window w (5–40) |
| Held fixed | adaptive stop, prior-session-high, MA200 floor, max hold — the four axes V64's fANOVA measured at 0.003–0.012 importance |
| Folds | 9 quarterly test windows, 2023Q4 → 2025Q4; **rolling** 4 quarters train / 1 test, and **expanding** from the start |
| Selection objective | total % of entry price on the training window, ≥ 15 training trades |
| Arms | RE-CHOSEN (all axes) · RE-CHOSEN (4 axes, the rest frozen at what the optimiser agrees on) · FIXED incumbent · FIXED 15m preset · **RANDOM cell from the same grid** |

Each cell is evaluated **once** over the whole series and a fold's score is a slice of its trades
by signal bar, so 19,200 evaluations answer 2 schemes × 9 folds × 5 arms.

## All nine folds

| Arm | OOS trades | Total % | %/trade | PF | Folds + | Worst fold |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Rolling 4Q** | | | | | | |
| RE-CHOSEN (all axes) | 281 | +28.20 | 0.1004 | 1.498 | 8/9 | −3.74 |
| RE-CHOSEN (4 axes only) | 275 | +23.36 | 0.0850 | 1.415 | 7/9 | −3.74 |
| FIXED incumbent | 188 | +28.43 | **0.1512** | **1.795** | 8/9 | −0.76 |
| **FIXED 15m preset** | 460 | **+34.27** | 0.0745 | 1.465 | **9/9** | **+1.70** |
| RANDOM grid cell | 244 | +8.38 | 0.0343 | 1.246 | 6/9 | −3.65 |
| **Expanding** | | | | | | |
| RE-CHOSEN (all axes) | 331 | +24.50 | 0.0740 | 1.389 | 8/9 | −1.38 |
| RE-CHOSEN (4 axes only) | 290 | +28.39 | 0.0979 | 1.484 | 8/9 | −1.38 |
| FIXED incumbent | 188 | +28.43 | 0.1512 | 1.795 | 8/9 | −0.76 |
| **FIXED 15m preset** | 460 | **+34.27** | 0.0745 | 1.465 | **9/9** | **+1.70** |
| RANDOM grid cell | 158 | +4.42 | 0.0280 | 1.149 | 6/9 | −1.09 |

The 15m preset is the only arm with **no losing quarter** in three years of folds.

**Span-normalised walk-forward efficiency: 0.582 rolling, 0.751 expanding.** *(A raw
sum-OOS ÷ sum-IS ratio gives 0.145 and 0.094 and is mostly a span ratio — training is 4–12
quarters and testing is 1. The figures above normalise both sides to % per quarter, which is the
number that means something.)* Expanding has the higher efficiency and the lower absolute return:
a longer training window earns less per quarter in-sample, so the ratio flatters it.

## The caveat that decides the head-to-head

**The fixed arms were selected on the research block, which ends 2024-11-27.** Five of the nine
test folds are inside it *for them* — not for the re-chosen arm, which is honest in every fold.
Comparing an arm that has seen the data with one that has not is exactly the contamination this
design exists to avoid, so the head-to-head is re-read on the four quarters that postdate the cut:

| Scheme | Folds | RE-CHOSEN | FIXED | FIXED15 | RANDOM | Winner |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| rolling | 4 | +14.23 | +10.87 | **+17.07** | +2.92 | FIXED15 |
| expanding | 4 | **+19.84** | +10.87 | +17.07 | +2.60 | **RE-CHOSEN** |
| *(all nine, rolling)* | 9 | +28.20 | +28.43 | **+34.27** | +8.28 | FIXED15 |
| *(all nine, expanding)* | 9 | +24.50 | +28.43 | **+34.27** | +8.18 | FIXED15 |

**The two schemes disagree on the post-cut folds and agree over all nine.** Four folds cannot
separate them. Both are reported rather than the one that reads better — but note that the
expanding win for re-optimisation is the *first* time on this branch a re-optimiser has come out
ahead of the author's constants on any honest slice, and it rests on four quarters.

**What both schemes agree on:** RE-CHOSEN beats a RANDOM grid cell in 3/4 post-cut folds, and 8/9
and 5/9 overall.

## Parameter stability — the optimiser converges on two axes and wanders on four

| Axis | Rolling: chosen values | Modal share | Agrees with the shipped incumbent |
| --- | --- | ---: | ---: |
| entry channel | **15 × 9** | **100%** | **0/9** |
| exit channel | 30 × 8, 40 × 1 | 89% | 0/9 |
| take profit | **0.0 × 8**, 6.0 × 1 | 89% | **8/9** |
| timeframe | 15 × 5, 60 × 4 | 56% | 0/9 |
| stop | 3.0 × 4, 2.0 × 3, 2.5 × 2 | 44% | 3/9 |
| pivot k | 3 × 4, 2 × 3, 5 × 2 | 44% | 4/9 |
| window w | 40 × 4, 20 × 2, 30 × 2, 5 × 1 | 44% | 2/9 |

Two things fall out:

- **The optimiser independently rediscovers the shipped 15m preset's channels.** Entry 15 in 9 of
  9 folds and exit 30 in 8 of 9 — which is exactly `ent 15 / exit 30`, and it never once picks the
  incumbent's 20/20. Note entry 15 is the grid's *minimum*, so that axis is at the box edge again.
- **No take profit in 8 of 9 folds**, chosen freshly inside every training window. That is the
  seventeenth independent time on this branch.

On the four axes it does not settle (44–78% modal share), `STUDY_APM_WFO`'s reading applies: a
parameter whose optimum moves every fold has no information in it. **Freezing what it agrees on
and re-choosing only the four it does not** gives +23.36% rolling (worse than +28.20%) and +28.39%
expanding (better than +24.50%) — inconsistent, so the wandering axes are not cleanly the problem
either.

## The matched control on the walk-forward out-of-sample span

Random entries drawn from the bars each arm was eligible to trade, from 2023-10-01 onward, running
the **identical** stop, target, channel exit, clock and position lock — so the only difference is
which bar the trade starts on. Entry bars are oversampled 3× and then thinned by the same position
lock, so the control lands near the rule's own trade count instead of clustering (the construction
`STUDY_V59` had to fix).

| Arm | n | Observed %/trade | Total % | Control median | Control 5–95% | p |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| FIXED incumbent (30m) | 188 | **+0.1512** | +28.43 | +0.0438 | [+0.0008, +0.0872] | **0.000** |
| FIXED 15m preset | 460 | +0.0745 | +34.27 | +0.0174 | [−0.0021, +0.0371] | **0.000** |
| WFO modal cell (15/15/30/2.5/0/3/40) | 450 | +0.1112 | **+50.06** | +0.0331 | [+0.0107, +0.0604] | **0.000** |

This is the strongest evidence in the study: on a span where nothing was selected, all three beat
a geometry-matched random entry decisively. **The modal cell's +50.06% is post-hoc** — it was
picked by reading the fold-by-fold table — so its total is descriptive; its control p-value is
real but the choice is not pre-registered.

## What this changes

Nothing ships differently. The 15m preset keeps its default status and gains the best evidence it
has: 9/9 folds positive, no losing quarter, and p 0.000 against a matched random entry on the
walk-forward span. The incumbent keeps the best per-trade edge (+0.1512, PF 1.795) on 60% fewer
trades.

The honest summary of seven re-optimisation attempts on this branch is now slightly more nuanced
than "the optimiser always loses": it loses over all nine folds in both schemes, it loses on the
post-cut folds under a rolling window, and it wins on the post-cut folds under an expanding
window — on four quarters. What it never does is lose to a random member of its own family, and
what it never finds is a parameter set worth changing the defaults for.
