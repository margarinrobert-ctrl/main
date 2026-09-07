# Volume on NQ — the one column nobody had used, and what it is actually good for

Full reports: [`STUDY_VOLUME.md`](STUDY_VOLUME.md) (5-minute) and [`STUDY_VOLUME_1m.md`](STUDY_VOLUME_1m.md)
(1-minute). Script: `scripts/quant-volume-alpha.ts`. Features: `src/lib/quant/volumeFeatures.ts`.

NQ RTH, Dec 2022 – Dec 2025. 58,609 five-minute bars and 292,908 one-minute bars, split
chronologically 70/30 into research and holdout. Edges are **drift-adjusted** and reported in ticks
against the **3.80-tick round turn**. Every event study uses a HAC lag at least as long as its
forward window.

## The short answer

**Volume predicts RANGE overwhelmingly and DIRECTION not at all.**

Twelve pre-specified volume conditions × five horizons = 60 cells per timeframe, 120 in total.
**Zero survive Benjamini-Hochberg at q ≤ 0.10 on either timeframe.** The smallest raw p-value
anywhere in the 120 cells is 0.0089; pooled BH puts its q at essentially 1.

The same volume measure, pointed at the *size* of the next move instead of its *sign*, produces
t-statistics between 11 and 80 and replicates on the holdout without a single exception.

| question | answer | evidence |
| --- | --- | --- |
| does volume predict the next 30 minutes' range? | **yes, decisively** | dry bars → 174 ticks, heavy bars → 353 ticks (t = −39.6 / +16.7), same ordering in the holdout |
| does volume predict the next 30 minutes' direction? | **no** | 0 of 120 cells survive FDR; research→holdout sign agreement 52% |
| do heavy-volume moves continue differently from light-volume ones? | **not measurably** | largest difference t = 1.51, p = 0.13 |
| is any of it worth 3.80 ticks? | **nothing that is measurable is** | best FDR-surviving edge: none exists |

## 1. The normalisation, which is the actual contribution

Intraday volume has a deep U-shaped profile, so the usual "volume > 2× the trailing 20-bar mean"
filter is substantially a clock:

| hour (ET) | mean 5m volume | share of bars flagged by a trailing-mean surge filter |
| --- | --- | --- |
| 09:30 | 11,663 | **45.0%** |
| 11:00 | 5,496 | 0.3% |
| 12:00 | 4,242 | 0.8% |
| 15:00 | 5,309 | 10.6% |

Half of all opening-hour bars are "high volume" and essentially no midday bar ever is. `rvolTod` in
`volumeFeatures.ts` fixes this by comparing each bar to the **median volume of the same
minute-of-day over the prior 20 completed sessions** — a 10:15 bar against other 10:15 bars. Only
completed prior sessions enter the reference window, which is enforced by a test.

## 2. What volume is genuinely good for: range

Forward 30-minute high-low range, in ticks, bucketed by time-of-day relative volume:

| rvol bucket | research n | fwd range | lift vs rest | t | holdout fwd range | holdout lift | holdout t |
| --- | --- | --- | --- | --- | --- | --- | --- |
| < 0.7 (dry) | 6,206 | 174.0 | −62.6 | **−39.6** | 223.9 | −125.5 | **−33.6** |
| 0.7 – 1.0 | 12,341 | 215.7 | −15.6 | −11.2 | 286.2 | −59.0 | −14.3 |
| 1.0 – 1.5 | 12,868 | 240.3 | +21.7 | +14.9 | 349.4 | +34.1 | +7.6 |
| 1.5 – 2.5 | 4,847 | 260.3 | +39.4 | +18.4 | 449.5 | +144.4 | +16.5 |
| ≥ 2.5 (heavy) | 815 | 353.1 | +129.8 | **+16.7** | 551.2 | +231.3 | **+10.9** |

Monotone, enormous, and identical in shape on the holdout and on the 1-minute series. This is not
tradeable on its own — it says nothing about which way — but it is the proof that the volume column
carries real information, which is what makes the directional null below meaningful rather than a
data-quality story. Its use is in **sizing, stop placement and horizon selection**, not entry.

## 3. What volume is not good for: direction

Twelve conditions, all written before any was measured: heavy-volume continuation, light-volume
continuation, the legacy trailing-mean surge, exhaustion fades, volume-climax-with-small-body,
close-location-weighted pressure, dry-up-then-break, rolling volume-weighted pressure, pressure
divergence at new highs, session-delta divergence, busy-session trend, quiet-session fade.

**5-minute research half: 0 of 60 cells survive BH at q ≤ 0.10.** Best q = 0.162.
**1-minute research half: 0 of 60 cells survive BH at q ≤ 0.10.** Best q = 0.299.

And the research half carries almost no information about the holdout half:

| | 5-minute | 1-minute |
| --- | --- | --- |
| sign agreement, research → holdout, across all 60 cells | **52%** | **53%** |
| correlation of the drift-adjusted edge between halves | 0.24 | 0.67 |

52% is a coin flip. The prior ORB study found a q = 0.018, t = 3.37 anomaly that failed to
replicate; this study's version of that lesson is milder only because nothing got far enough to be
disappointed by.

## 4. The interaction test, stated in advance and failed

The hypothesis the study was built around: *the same-sized move continues differently on heavy
volume than on light volume*. Both conditions require an identical body (≥ 0.5 ATR); the only
difference is the volume filter.

| horizon | heavy n | heavy drift-adj | light n | light drift-adj | difference | t | p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5 min | 1,377 | +5.28 | 1,186 | +2.25 | +3.03 | 1.05 | 0.29 |
| 15 min | 1,347 | +6.51 | 1,142 | +5.99 | +0.52 | 0.10 | 0.92 |
| 30 min | 1,274 | +11.21 | 1,066 | +6.46 | +4.76 | 0.65 | 0.51 |
| 60 min | 1,148 | +26.22 | 931 | +9.63 | +16.59 | 1.51 | 0.13 |
| 120 min | 789 | +32.74 | 699 | +13.18 | +19.56 | 1.12 | 0.26 |

The sign is the expected one at every horizon and the magnitude at an hour is large. It is also
never significant, and the *cheaper* half of the comparison — light volume — is positive too. Read
honestly: heavy-volume moves are not measurably more persistent than light-volume ones on this
sample.

One descriptive result is worth keeping: large-bodied heavy-volume bars are **38% long / 62% short**,
while large-bodied light-volume bars are **56% long**. Selling is loud and buying is quiet on NQ.
That is a real asymmetry in the data; it just does not forecast anything.

## 5. The methodological result: overlapping events are not the only clustering problem

`eventStudy` already widens its HAC lag to cover overlapping forward windows. That is not enough for
a **day-level** condition. "Today is busy and price is away from the open" fires on most bars of a
qualifying session, so 15,000 events can be 176 days wearing a disguise.

Giving every session one vote instead of every bar:

| cell | events | sessions | edge (event mean) | HAC t | edge (per session) | clustered t |
| --- | --- | --- | --- | --- | --- | --- |
| 5m `busy-session-trend` @ 60 min | 2,538 | 128 | +34.17 | 2.42 | +26.10 | 1.57 |
| 5m `heavy-close-location` @ 5 min | 1,065 | 314 | +6.91 | 2.31 | −0.65 | −0.24 |
| 1m `busy-session-trend` @ 15 min | 14,963 | 176 | +9.06 | **2.62** | **−15.76** | **−1.97** |
| 1m `busy-session-trend` @ 30 min | 14,435 | 176 | +15.43 | 2.29 | −13.05 | −1.22 |

The last two rows are the finding. On 1-minute data the busiest-looking directional signal in the
study has a bar-weighted edge of +9 ticks at t = 2.62 and a session-weighted edge of **−16 ticks** at
t = −1.97. The sign flips. The apparent edge was a handful of very busy, very trending days
contributing thousands of bars each. **Any conditional study whose condition is a property of the
day must cluster by day, or it is counting the same day thousands of times.**

## 6. A hypothesis of mine that failed

The premise of `volumeFeatures.ts` was that the time-of-day normalisation is the right one and the
trailing-mean version is a clock in disguise. On the directional tests the opposite happened: the
*naive* trailing-mean surge was the more persistent of the two.

| condition (5m) | research @ 60 min | research @ 120 min | holdout @ 60 min | holdout @ 120 min |
| --- | --- | --- | --- | --- |
| body-only, no volume filter at all | +6.58 (t 2.82) | +8.44 (t 2.38) | +3.96 (t 0.84) | +3.43 (t 0.45) |
| body-only, first 60 minutes only | +9.92 (t 1.74) | +13.88 (t 1.96) | +19.55 (t 1.83) | +10.42 (t 0.87) |
| `heavy-continuation` (time-of-day rvol) | +26.22 (t 2.16) | +32.74 (t 2.30) | +19.05 (t 0.93) | +56.57 (t 1.68) |
| `trailing-surge-continuation` (naive) | +24.33 (t 2.44) | +33.75 (t 2.59) | **+40.42 (t 2.25)** | **+64.43 (t 2.57)** |

The controls in the first two rows are not candidates and were never in the FDR family — they exist
to take a result away, not to create one. They show the trailing-mean surge is not *merely* the
opening hour: the clock alone earns roughly a third of it. So the better-motivated normalisation lost
to the cruder one, twice.

If there is a mechanism it is probably that the two measures answer different questions — `rvolTod`
measures the **level** of participation versus normal, the trailing mean measures a **change** in
participation over the last hundred minutes — and that change may matter more than level. That
sentence is a hypothesis for a pre-registered study, not a conclusion from this one; retrofitting a
story onto the row that happened to win is the exact error this protocol exists to prevent.

## 7. The one candidate, and why it is still not a finding

`trailing-surge-continuation` is the only condition in the study that kept its sign, roughly its
size, and t > 2.2 in **both** halves, on both sides:

| | research | holdout |
| --- | --- | --- |
| @ 120 min, drift-adjusted | +33.75 ticks, t = 2.59 | +64.43 ticks, t = 2.57 |
| long side | +32.84 (n = 589) | +32.1 (n = 231) |
| short side | +34.53 (n = 694) | +88.1 (n = 315) |
| session-clustered t | 3.32 | 1.33 |

Both sides positive in both halves is unusual in this repo — the ORB and IB studies both found
"edges" that were entirely long, i.e. the index. This one is not that.

It still fails, and the reasons are worth stating precisely:

1. **It did not survive FDR** (q = 0.162 across the 60 cells it was picked from). By the protocol it
   is not a discovery, and the fact that it then replicated is exactly the coin-flip outcome BH at
   q = 0.10 is designed to be honest about in the other direction.
2. **The information ratio is 0.094 per event** — +42.9 ticks of mean against a 455-tick per-event
   standard deviation over the whole sample. It is 11× the round-turn cost and 11× smaller than its
   own noise, which is why 1,831 events cannot settle it.
3. **It is concentrated in 2024–25.** Per-year session-clustered t: 2023 = 1.66, 2024 = 2.87,
   2025 = 1.42. Gate 9 (no single year dominating) is not met.
4. **It nearly vanishes on 1-minute bars**: +11.37 ticks at t = 2.00 in research, information ratio
   0.040. The same signal measured four times more often gets four times weaker per event, which is
   the timeframe arithmetic from the protocol, not an independent confirmation.
5. **It is a 2-hour hold**, which is not what any of this repo's execution machinery models, and a
   2-hour hold on NQ has a drawdown profile no event study describes.

## 8. Bottom line

The volume column is real information and this study found where it lives: **in the second moment,
not the first**. Relative volume forecasts how far price will travel with t-statistics in the tens
and holdout replication that is essentially perfect. It forecasts the *sign* of that travel in none
of the 120 cells tested, on either timeframe, under drift adjustment and false-discovery control.

That is the same conclusion the OHLC studies reached, arrived at from a genuinely different data
column, which makes it a stronger statement than any of them: **on NQ RTH at scalping horizons the
predictable quantity is volatility, and volatility is not directly tradeable through a directional
entry.** The productive uses of what is here are:

1. **Sizing and stops.** A dry-volume bar precedes a 174-tick half-hour and a heavy one precedes 353.
   A fixed stop is two different stops in those two regimes, and this measure separates them ex ante.
2. **Horizon selection.** The same measure says when a 30-minute target is plausible and when it is
   not.
3. **The next honest test**, if directional volume alpha is still the goal, is not more OHLCV
   features — it is signed order flow. Every condition here that tried to infer buying and selling
   from OHLC (`pressure-momentum`, `pressure-divergence`, `session-delta-divergence`,
   `heavy-close-location`) landed in the noise, and the close-location proxy is the weakest link:
   it cannot distinguish a bar that closed on its high because of passive accumulation from one that
   closed there on a squeeze. Real delta would.

## What was built

- `src/lib/quant/volumeFeatures.ts` — time-of-day relative volume, session pace, volume-weighted
  pressure and session delta, all causal, with the prior-sessions-only reference window enforced by
  tests (`volumeFeatures.test.ts`, 9 tests).
- `scripts/quant-volume-alpha.ts` — the end-to-end study: normalisation diagnostics, the range
  family, the 60-cell directional grid with BH, the pre-stated interaction test, the clock control,
  the long/short split, session-clustered standard errors, and the holdout. Runs on any bar file:
  `--data data/NQ_1m.csv --out docs/ib/STUDY_VOLUME_1m.md` reproduces the 1-minute pass.
