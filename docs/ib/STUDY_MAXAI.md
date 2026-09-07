# MaxAI / NQ34 (Huber 2025), forward-tested on data the paper never saw

**Paper:** Michael Maximilian Huber, *"MaxAI: A Reinforcement Learning and Genetic Algorithm
Framework for Intraday Index Futures Trading"*, SSRN 5761402, October 2025. Preprint, not peer
reviewed.

**Reported:** $132,412 net over 4,014 trades, Jan 2018 – Aug 2022. PF 1.07, Sharpe 1.04, max
drawdown $41,180, $32.99/trade, 43.95% win rate, risk of ruin 0.38%. Live from Feb 2025, +36.49% by
June 2025.

**Result here:** the rule does not have an edge on Dec 2022 – Dec 2025. The reading that reproduces
the paper's own headline statistics almost exactly earns $102,571 — at a Newey-West **t of 1.34**,
inside a random-entry null, from a parameter surface that changes sign between adjacent cells, and
at **−$25.19/trade under walk-forward**. What profit exists is the NQ uptrend, and the paper's own
signal is *worse* than a randomly chosen minute of the same day.

Code: `research/cmf_maxai.py`, `research/cmf_validate.py`, `research/cmf_edge.py`,
`research/cmf_conditions.py`.

## 1. What the strategy actually is

The paper is framed as reinforcement learning tuned by a genetic algorithm. It is neither, and this
matters because it determines what there is to reproduce.

§3.7 defines the agent's action as a deterministic function of the feature:

> *State S_t: rounded CMF value. Action A_t ∈ {Buy, Sell, Neutral}: Buy if CMF ≥ 0.25; Sell if
> CMF ≤ −0.25; else Neutral.* … *the state is equal to action + 1.*

A tabular Q-learner whose action is already pinned by the feature has nothing to learn, and its
state is a relabelling of its own action. The genetic algorithm (§3.8) searches only α, γ and ε —
the three Q-learning hyper-parameters — none of which can alter a deterministic policy. Table 3
reports the GA's answer as α=0.12, γ=0.85, ε=0.08, which changes nothing about which trades are
taken.

So the traded policy is three lines:

```
CMF(20) >= +0.25  ->  long
CMF(20) <= -0.25  ->  short
otherwise         ->  flat
```

with next-bar-open fills, a $900 stop, a $1,500 target, one contract, RTH only. That is what is
reproduced below. **This is not a criticism of the result** — a simple rule that works is worth more
than a complex one — but the RL and GA machinery does no work, and describing the strategy without
them costs nothing.

## 2. Why this data is the right test

| | paper | here |
| --- | --- | --- |
| sample | Jan 2018 – Aug 2022 | **Dec 2022 – Dec 2025** |
| bars | ~4M 1-minute | 292,908 RTH 1-minute |
| sessions | ~1,160 | 765 |

**There is no overlap.** The paper's window ends 16 Aug 2022; this data starts 26 Dec 2022. Every
number below is out-of-sample for the published rule in the strictest sense available.

It is worth noting what the paper's own headline window is: §4.8 evaluates NQ34 over Jan 2018 –
Aug 2022, a span that **contains both its training year (2021) and its test year (2022)**. The
$132,412 is therefore not an out-of-sample figure; roughly 40% of it comes from data used to build
and select the configuration.

## 3. Costs

The paper quotes four different cost models: $5 per open/close and $10 per flip (§3.3), $3.25 per
step (§3.7), $5 slippage + $5 commission per trade (§4.9), and $2/side + $8.60 slippage (§4.10).
Its own realised figures — $34,530 slippage and $8,028 commission over 4,014 trades — imply
**$10.60 per round turn**. This repository's standard NQ model is 1 tick spread + 1 tick slippage
per side + $4 commission = **$19.00**. All three are reported below; nothing here depends on the
choice.

## 4. The rule as written: it loses

The paper never says a position is closed because the signal decayed, so both readings are run.

```
                                        trades        net $      PF   $/trade      win       maxDD   Sharpe
signal-following, paper cost $10.00      7,437      -53,810   0.940     -7.24    38.0%      71,995    -0.80
signal-following, realised $10.60        7,437      -58,272   0.935     -7.84    38.0%      75,434    -0.87
signal-following, repo cost $19.00       7,437     -120,743   0.871    -16.24    36.8%     125,511    -1.79
signal-following, ZERO cost (gross)      7,437       20,560   1.024     +2.76    40.5%      39,080     0.31

barriers-only, paper cost $10.00         2,871      128,410   1.075    +44.73    40.5%      30,650     0.95
barriers-only, realised $10.60           2,871      126,687   1.074    +44.13    40.5%      30,829     0.93
barriers-only, repo cost $19.00          2,871      102,571   1.060    +35.73    40.5%      33,332     0.76
barriers-only, ZERO cost (gross)         2,871      157,120   1.093    +54.73    40.5%      28,950     1.16
```

The signal-following reading loses under every cost model and in every full year (2023 −$22.16/trade,
2024 −$13.94, 2025 −$14.00; the 5-session Dec-2022 stub is the only positive), and its **gross** edge of
$2.76/trade is a quarter of the $10.60 the paper itself realised. On that reading the strategy
cannot pay for its own execution.

The barriers-only reading is profitable, and it reproduces the paper's profile closely:

| | paper (2018–22) | here (2022–25) |
| --- | --- | --- |
| profit factor | 1.07 | **1.060** |
| $/trade | $32.99 | **$35.73** |
| trades/day | 3.46 | **3.75** |
| win rate | 43.95% | 40.5% |
| max drawdown | $41,180 | $33,332 |

That correspondence, on non-overlapping data, is why the rest of this study exists. It looked like a
replication.

## 5. It is not significant, and the search was wider than the effect

```
observed edge          $35.73/trade over 2,871 trades, NW t = 1.34
block bootstrap 95% CI [-$17.49, +$87.89]   P(edge <= 0) = 9.2%

23 (CMF length, threshold) cells evaluated
  published 20/0.25 ranks 5 of 23 by $/trade
  best cell 20/0.30 at $64.18/trade, t = 1.76
  cells with a NEGATIVE edge: 5 of 23
  sd of edge ACROSS cells $36.85
```

The standard deviation of the edge **across parameter cells ($36.85) is larger than the edge itself
($35.73)**. Adjacent settings flip sign — at length 20 the sequence 0.10 → 0.40 runs +$6.29, +$12.55,
**−$2.52**, +$35.73, +$64.18, +$7.93. This is a spike surface, not a plateau, and the published cell
is neither the best nor near a stable region.

A best-of-23 search draws E[max z] ≈ 2.50 from noise alone. The published cell reaches t = 1.34. As a
single pre-specified test it does not reach 2; priced as a searched one it is not close.

### Walk-forward is the decisive number

Re-selecting the best cell on a rolling 250-session window and trading it for the next 60 —
what someone using this method in real time would actually experience:

```
8 folds: 1,004 trades, -$25,286, -$25.19/trade, t = -0.42
fixed published cell over the same span: +$35.73/trade
cells chosen: (60,0.25) x2, (60,0.20) x2, (30,0.25), (60,0.15), (30,0.20)
```

The procedure never re-picks 20/0.25 and loses money. The published cell is a survivor of hindsight,
not an output of the method.

## 6. A random-entry null does nearly as well

A $900 stop against a $1,500 target breaks even at a 37.5% win rate. The rule wins 40.5%. So the
question is whether CMF earns those three points or the barrier geometry does.

```
CMF rule                                 $35.73/trade

A. same entry bars, RANDOM side          null mean -$2.25  sd $25.03  95th +$38.75  -> CMF beats 92.0%
B. RANDOM entry bars, same side mix      null mean -$9.61  sd $35.31  95th +$50.07  -> CMF beats 90.2%
```

Both nulls put the published rule at roughly the 90th percentile — a one-sided p of about 0.09,
consistent with the bootstrap's 9.2%. Random entries into the same barriers beat CMF about one time
in ten.

## 7. The profit is not where the paper says it is

```
exit reason              n    share        net $    $/trade
$900 stop            1,475    51.4%   -1,355,525    -919.00
$1,500 target          876    30.5%    1,297,356    1481.00
16:00 session close    520    18.1%      160,740    +309.12

barrier exits only : 2,351 trades, -$58,169  (-$24.74/trade)
16:00 exits only   :   520 trades, +$160,740 (+$309.12/trade)
```

**The stop and target together lose $58,169.** Every dollar of profit comes from the 18% of positions
that hit neither barrier and were flattened at 16:00 — entered at a median of 14:31 ET, i.e. late
enough that a 45-point stop and a 75-point target are out of reach before the close. The mechanism
the paper describes (§4.12: entry on money-flow thresholds, exit at $900/$1,500) is the part that
loses money.

## 8. The late-day effect is the clock, not CMF — and two bugs that reversed it

The obvious follow-up is whether "hold into the close" is real. The first version of that test
reported lifts of +$201 and +$183 per trade at t = 5.60 and t = 7.94. Both were artifacts:

1. **A one-bar look-ahead.** The signal at bar *i* is known at bar *i*'s close, so the fill is
   `o[i+1]`. Entering at `o[i]` books part of the move that created the signal.
2. **Fake independence.** Every bar in a session shares one closing price, so hold-to-close outcomes
   inside a day are one observation, not 8,541. The unit is the session: 765 of them.

Corrected — next-bar fills, one observation per session, tested across sessions:

```
      entry     days   CMF n  CMF $/tr  no-signal $     LIFT  t(day)      long $  short $
09:30-11:00      668   8,541    131.60         8.94  -152.97   -1.37      154.45    94.35
11:00-12:30      652   6,827      1.69        20.87   -40.50   -0.47        8.83   -13.20
12:30-14:00      642   6,959    128.46        -4.92   +40.10    0.62      125.63   133.85
14:00-15:00      485   3,432     -5.38       -23.36  -102.81   -1.61       98.24  -195.42
15:00-16:00      497   3,600     27.24       -15.86   -95.29   -2.70       55.54   -23.63
```

The lift is negative in four of five windows and the **only significant result is negative**
(−$95.29, t = −2.70). Holding a CMF-signalled position into the close is worse than holding a
randomly chosen position from the same session into the close.

## 9. What the data actually says about winnable trades

Using the paper's barrier as a ruler — take a position from *every* bar, exit at the $900 stop, the
$1,500 target or 16:00 — and asking which causal conditions shift the outcome. Lift is measured
against the same barrier on all bars **within the same session**, then tested across 765 sessions,
with Benjamini-Hochberg across all 28 tests.

```
unconditional: long +$9.25/trade   short -$47.25/trade
break-even win rate 37.5%; actual long win rate 43.8%

condition                             side        n    lift $      t      q   research   holdout     net $
below the opening range               long   73,120   +567.56  23.76  0.000    +565.76   +570.56     -5.82  *
price below session VWAP              long  128,196   +368.96  24.55  0.000    +374.40   +360.78    -11.46  *
above the opening range              short   96,711   +364.68  26.49  0.000    +381.73   +339.90    -56.25  *
CMF <= -0.25 (the paper's SHORT)      long   10,355   +255.09  10.07  0.000    +285.84   +209.09     +8.53  *
inside the opening range              long   99,394   +145.54   6.73  0.000    +124.20   +177.76     +7.47  *
CMF >= +0.25 (the paper's long)       long   19,004   -141.30  -8.32  0.000    -138.33   -145.69    +58.07  *
CMF <= -0.25 (the paper's short)     short   10,355   -255.09 -10.07  0.000    -285.84   -209.09    -46.53  *
```

Three readings, in order of importance.

**The unconditional long is +$9.25 and the unconditional short is −$47.25.** The gap is the drift.
On 2023–25 NQ, *any* long-biased intraday rule shows a profit against zero, so **zero is the wrong
benchmark**. The right one is the unconditional long, and the paper's rule at +$35.73/trade has to
beat +$9.25 — which, per §5 and §6, it does not do significantly.

**The paper's signal is a day-selector, not a timing tool.** `CMF ≥ +0.25` taken long has the best
raw number in the table (+$58.07/trade) and the *worst* within-day lift (−$141.30, t = −8.32). Both
are true and they are not in conflict: the signal identifies days that are going up, and within
those days it picks worse-than-average minutes. Strip out which day you are in — which is all the
lift does — and the signal is actively harmful.

**The paper's short signal is a long signal.** `CMF ≤ −0.25` taken *short* nets −$46.53/trade; taken
*long* it nets +$8.53 with a +$255.09 within-day lift that holds at +$285.84 research / +$209.09
holdout. This is the eighth independent sighting in this project that direction cannot be a free
parameter on 2022–25 NQ.

The four largest lifts (opening range, VWAP) are mechanically guaranteed and **not tradeable**: being
below VWAP means being below the day's own average price, so buying there beats buying at a random
minute of that day by construction. Their `net` columns are negative — the days on which you are
persistently below VWAP are the down days, and you cannot know that in advance. This is why the lift
and the net disagree in sign, and why both columns have to be printed.

## 10. Conclusions

1. **The published rule does not have an edge on unseen NQ data.** Signal-following: negative under
   every cost model and every full year. Barriers-only: +$35.73/trade at t = 1.34, bootstrap CI crossing
   zero, beaten by random entries 9% of the time, −$25.19/trade under walk-forward.
2. **The reproduction matching the paper's headline statistics is a coincidence.** PF 1.060 vs 1.07
   and $35.73 vs $32.99/trade look like replication, but the standard deviation of the edge across
   23 parameter cells is $36.85 — as large as the effect. Matching one number from a distribution
   that wide is not evidence.
3. **There is no RL and no GA in the traded policy.** The action is a deterministic function of CMF;
   the GA tunes hyper-parameters that cannot change it.
4. **The paper's headline window contains its own training and test years.** The $132,412 is not an
   out-of-sample figure.
5. **The profit is in the 16:00 flat, not the barriers.** Stop and target together lose $58,169.
6. **Both defects that inflate this kind of study are cheap to make and reverse the sign.** A
   one-bar look-ahead and treating intraday bars as independent turned −$95 at t = −2.70 into +$201
   at t = 5.60 in my own first draft of §8.
7. **On 2023–25 NQ, zero is the wrong benchmark.** The unconditional intraday long earns +$9.25 per
   barrier trade. Any long-biased rule clears zero; only beating +$9.25 means anything.

## 11. What this does contribute

The barrier-as-a-ruler framing in §9 is worth keeping and is now a reusable tool: it converts "was
this a good moment to trade" into a per-bar dollar number with no strategy attached, which makes
conditions directly comparable. The correct estimator for it — within-session lift, tested across
sessions, both lift and net reported — is the one that survived the bug in §8, and both columns are
needed because they routinely disagree in sign.

## 12. Reproduce

```bash
python3 research/cmf_maxai.py       # the published rule, both readings, three cost models, by year
python3 research/cmf_validate.py    # random-entry nulls, exit decomposition, parameter surface
python3 research/cmf_edge.py        # bootstrap, search cost, walk-forward, the 16:00 lift test
python3 research/cmf_conditions.py  # the barrier as a ruler: which conditions shift the outcome
```
