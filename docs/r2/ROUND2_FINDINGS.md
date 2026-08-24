# Round 2 — hunting the leads from the first NQ study

Round 1 ended with nothing clearing the gates. This round followed the two leads that study
actually produced, rather than widening parameter grids until something passed.

## What changed

1. **Execution.** Round 1 charged every trade a full round turn (`taker`). Real desks rest targets
   and only take liquidity on stops. Added `realistic` and `passive` fill models — see
   [`RESEARCH_PROTOCOL.md`](../RESEARCH_PROTOCOL.md) §4b for the caveats, particularly that
   `passive` is a **ceiling**, not a forecast.
2. **A strategy matched to the one credible statistic.** Round 1's only statistically significant
   finding was VR(10) = 0.928 (z = −2.81) — mean reversion at the ~50-minute horizon. `ou-reversion`
   trades that and nothing else.
3. **Session.** Round 1's time-of-day profile showed 09:30–10:30 carries roughly twice the range of
   the midday tape. Re-ran restricted to that window.

## Result

See [`COMPARISON.md`](COMPARISON.md) for the mechanical table. Summary:

| configuration | best strategy | OOS Sharpe | t (HAC) | gates |
| --- | --- | --- | --- | --- |
| full session, taker (round 1) | vol-breakout | 0.51 | 0.70 | 5/10 |
| full session, realistic | ou-reversion | 0.54 | 0.69 | 6/10 |
| full session, passive | vol-breakout | 0.83 | 1.16 | 6/10 |
| open hour, realistic | orb | 1.59 | 1.92 | 6/10 |
| **open hour, passive** | **orb** | **1.51** | **1.94** | **7/10** |

Cheaper execution and a narrower session both moved the numbers in the expected direction, and the
best configuration now passes seven gates. **Nothing cleared all ten.**

## Why the headline result should not be believed yet

The open-hour ORB looks the strongest thing found so far: +18.5 ticks net per trade, walk-forward
efficiency 0.75, PBO 0.00, profitable in 83% of sub-periods and 100% of years, and it survives 3x
the modelled cost. Three things say hold on.

**1. It is not the strategy it claims to be.** The exit breakdown is decisive:

```
session 89 ($15,982) · stop 13 (-$8,740) · target 3 ($2,468)
```

Eighty-nine of 105 trades exit because the 10:30 session cut-off arrived — the profit target is hit
three times in the entire out-of-sample record. This is not an opening-range breakout scalp with a
target. It is "enter on the first break of the opening range, hold until 10:30", and essentially all
of the P&L comes from that holding period. The name and the rationale no longer describe the trade,
which means the economic story that justified testing it is not the story being tested.

**2. The 10:30 cut-off was chosen by looking at this data.** The window came from round 1's
time-of-day profile on the same sample. That is a legitimate research move, but it is a selection,
and it has to be paid for. The Deflated Sharpe prices it at **0.035** — far below the 0.95 gate.
The t-statistic of 1.94 also sits just under the threshold, which is what a genuinely marginal
result looks like.

**3. The sample is thin.** 105 out-of-sample trades, barely clearing the 100-trade gate, with 68% of
the P&L in a single year. A per-trade edge of 18.5 ticks over 105 trades is not a track record.

## What round 2 actually established

- **Execution cost is a real lever and a bounded one.** Moving from taker to passive fills lifted the
  best Sharpe from 0.51 to 0.83 — material, but not enough to turn a failing candidate into a
  passing one. It buys roughly one gate, not five.
- **Session selection is a bigger lever than entry logic**, exactly as the round-1 time-of-day
  profile implied. The same rules on the same data pass more gates purely from *when* they trade.
- **Micro contracts are not a cost lever** — MNQ commission is 2.40 ticks against NQ's 0.80. They cut
  dollar risk, not the per-tick hurdle. (Corrected in the protocol doc this round.)
- **The variance-ratio effect is real but too small to trade standalone.** `ou-reversion` — the
  narrowest possible expression of it — is profitable in-sample (+11.9 ticks, PF 1.13) and stays
  profitable on the untouched holdout (+6.0 ticks, PF 1.045), with a genuine parameter plateau.
  It is also insignificant in both (t = 1.59, then t = 0.40). That is the signature of a true but
  tiny effect, and it is a more useful answer than "mean reversion doesn't work".

## Honest next step

The open-hour ORB is worth one more research cycle, but the cycle has to be **a new question, not
more tuning of this one**: does an entry-on-break, hold-to-a-fixed-time rule work on data that has
never been looked at? That means a different instrument or a later sample, not another pass over
2022–2025 NQ. Tuning it further on this data would only lower the Deflated Sharpe.
