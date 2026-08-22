# Study comparison

Extracted mechanically from each study's own tables — the walk-forward line is the only
comparable number, since it is the sole out-of-sample record every configuration produces.

| study | session | fill | cost (ticks) | alpha budget | best OOS strategy | OOS trades | net (ticks) | OOS Sharpe | t (HAC) | best gates | cleared all |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Systematic scalping study — NQ | 09:30–16:00 America/New_York | — | 3.80 | 0.00 ticks | vol-breakout | 1203 | 3.33 | 0.51 | 0.70 | vol-breakout 5/10 | 0 |
| Systematic scalping study — NQ (realistic fills) | 09:30–16:00 America/New_York | `realistic` | 3.80 | 0.00 ticks | ou-reversion | 581 | 6.60 | 0.54 | 0.69 | ou-reversion 6/10 | 0 |
| Systematic scalping study — NQ (passive fills) | 09:30–16:00 America/New_York | `passive` | 3.80 | 0.00 ticks | vol-breakout | 1494 | 3.89 | 0.83 | 1.16 | vol-breakout 6/10 | 0 |
| Systematic scalping study — NQ (open hour, realistic fills) | 09:30–10:30 America/New_York | `realistic` | 3.80 | 0.00 ticks | orb | 106 | 19.00 | 1.59 | 1.92 | orb 6/10 | 0 |
| Systematic scalping study — NQ (open hour, passive fills) | 09:30–10:30 America/New_York | `passive` | 3.80 | 0.00 ticks | orb | 105 | 18.50 | 1.51 | 1.94 | orb 7/10 | 0 |

**No configuration produced a strategy clearing every gate.** Changing execution, session and timeframe moved the numbers without changing the conclusion.

