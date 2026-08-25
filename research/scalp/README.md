# Intraday scalp lab — US30, US100, NQ

Converting the multi-day Turtle breakout (`docs/ib/STUDY_TURTLE.md`) into an intraday scalp, on
three instruments, with US30 entering the branch for the first time.

```bash
python3 -c "import sys;sys.path.insert(0,'research');from scalp import xmarket;xmarket.report()"
```

## Why US30 matters

Every prior study here ended with the same limitation: NQ and US100 track the **same** underlying
index, and `STUDY_TREND_LONG.md` measured what that costs — 68% of signals fire on the identical
bar, so one cannot replicate the other. US30 is the Dow: a different index, different composition.

Measured 15-minute return correlation over the common span:

| | US30/US100 | US30/NQ | **NQ/US100** |
| --- | ---: | ---: | ---: |
| whole sample | 0.758 | 0.679 | **0.874** |

US30 is materially more independent than the pair this branch already had. **No lead-lag at any
offset** — every cross-correlation peaks at k=0, so there is nothing tradable between them.

## Data

| feed | bars | span | source resolution |
| --- | ---: | --- | --- |
| US30 | 2,880,287 (1m) / 581,195 (5m) | 2016-10-26 → 2025-07-15 | **1-minute** |
| US100 | 206,703 | 2016-11-14 → 2025-10-01 | 15-minute |
| NQ | 1,048,575 (1m) | 2022-12-26 → 2025-12-11 | 1-minute |

US30's 1-minute file removes the constraint that blocked `STUDY_US100_EDGELAB.md`: at a scalping
stop on 15-minute bars, 47% of trades touched both barriers inside one candle and the result was
set by the tie-break rule rather than by the market.

**Clocks are measured per feed, never inherited.** `feeds.derive_offset` locates the 09:30 New
York activity step separately in winter and summer and refuses a constant shift if they disagree.
US30 and US100 both resolve to New York + 7, consistent across seasons — but that was verified for
US30 independently rather than assumed from US100.

`Volume` is identically zero in both MT-style exports; `TickVolume` is a broker tick **count**, not
exchange volume, and is labelled `tick_` wherever it is used.

## The two statistics, which disagree in sign here

| | what it is | what it answers |
| --- | --- | --- |
| `expR` | trade-weighted mean R | **the economics** — every signal is taken |
| `day_R` | mean of per-day means | the correct unit of **inference** — trades cluster several to a session |

`day_R` weights a one-trade day equally with a twelve-trade day. On this data several entry
families have **positive day-level excess at p 0.000 and negative per-trade expectancy**. Both are
reported everywhere; a rule is only interesting when both are positive.
