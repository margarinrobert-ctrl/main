# Correlation matrices over the book, and over the states it trades in

Three matrices, plus the look-ahead bug that the first run of them contained.

## 0. A one-session misalignment that manufactured a signal

The first version of this produced a **+0.79** correlation between "prior day return" and the
long leg's daily P&L on 79 observations — a p-value around 1e-17, which is not what a real
market state looks like.

`session_index` assigns a bar before 09:30 to the *previous* session. A daily bar stamped 00:00
on date D therefore carries the session id of **D−1** while actually covering session **D**.
Indexing a state by the daily bar's own session id labelled every session with the *next* day's
data. The check that caught it is one line — correlate the state against the labelled session's
own return; it came back **−0.14** where a leak would show near 1, but only after the fix. Before
the fix, the "prior day return" state *was* the traded day's return.

The rule now enforced: every state is a function of daily bars up to and including bar *i*, and it
labels the session that bar *i+1* covers.

**Survivors of Benjamini-Hochberg at q = 0.10 went from 28 of 99 to 16 of 108.** Roughly half the
apparent structure in this study was that one-day shift.

## 1. LEG × LEG — is the book one trade or three?

Daily P&L correlation, MNQ, 922 sessions.

| | BOS 30m | BOS 60m | S/D 4H→60m |
| --- | --- | --- | --- |
| **BOS 30m core** | 1.00 | 0.27 | 0.16 |
| **BOS 60m core** | 0.27 | 1.00 | **0.01** |
| **S/D 4H→60m** | 0.16 | 0.01 | 1.00 |

Variance explained PC1 44%, PC2 33%, PC3 23% → **effective number of bets = 2.90 out of 3.**
Across all nine legs studied (including the long/short decompositions and the rejected variants):
**6.45 independent bets, PC1 = 27%.**

That is the strongest structural result here. The earlier matrix over BOS variants alone concluded
"everything here is mostly ONE trade". Adding a different *strategy* rather than another parameter
setting is what fixed it.

Worth noting inside the legs: BOS 30m LONG vs SHORT correlate **−0.00**, and S/D LONG vs SHORT
**−0.01**. The two sides of one rule are already orthogonal.

## 2. STATE × LEG — what market does each leg want?

Pre-session states against the leg's P&L on days it traded. `*` survives BH at q = 0.10 across all
108 tests.

| state | BOS 30m | BOS 60m | S/D 4H→60m | S/D SHORT |
| --- | --- | --- | --- | --- |
| prior day return | **−0.23\*** | **+0.46\*** | +0.12 | +0.09 |
| 5d vol / 20d vol | **+0.25\*** | +0.21 | +0.19 | +0.19 |
| ATR / 20d mean ATR | **+0.38\*** | −0.25 | **+0.36\*** | **+0.37\*** |
| prior range / 20d | +0.17 | −0.16 | **+0.39\*** | **+0.44\*** |
| dist from 200 EMA | −0.19 | +0.16 | **−0.45\*** | **−0.59\*** |
| 20d momentum | −0.10 | **+0.38\*** | −0.20 | −0.20 |
| 2-day run | +0.08 | **+0.35\*** | +0.01 | −0.13 |

**The three legs want three different markets, and that is why they do not correlate.**

- **BOS 30m** — a *volatility-expansion, buy-the-dip* trade. Positive on vol ratios, **negative**
  on the prior day's return.
- **BOS 60m** — a *momentum-continuation* trade. Positive on the prior day's return, on 20-day
  momentum, and on a two-day run, and it is the one leg that does **not** want expanding ATR.
- **S/D 4H→60m** — a *correction* trade. Its strongest state by far is distance from the 200-day
  EMA at **−0.45** (−0.59 on the short side): it earns when price is below its own long average
  and ranges are widening.

BOS 30m and BOS 60m have **opposite signs on prior-day return** (−0.23 vs +0.46). They are not
accidentally uncorrelated at 0.27 — they are mechanically different trades that happen to share an
entry rule.

## 3. TERCILE × LEG — $/trade in the low / mid / high third

| state | BOS 30m | BOS 60m | S/D 4H→60m |
| --- | --- | --- | --- |
| 5d vol / 20d vol | −0 / 5 / **244** | 57 / 215 / 232 | 83 / −91 / 281 |
| ATR / 20d mean ATR | −8 / 86 / 171 | 163 / 234 / 108 | 24 / 100 / 156 |
| prior day return | 99 / 33 / 116 | **−185** / 290 / 401 | 73 / −29 / 272 |
| dist from 200 EMA | 196 / −5 / 73 | 95 / 385 / 227 | 233 / 127 / **−88** |
| 20d momentum | 160 / 36 / 57 | −64 / 266 / 303 | 248 / 76 / −45 |

BOS 30m earns essentially **nothing** in the two quietest thirds of the volatility ratio and $244
per trade in the noisiest. BOS 60m *loses* $185 per trade after a down day and makes $401 after an
up day.

## 4. And the filter those tables suggest does not survive

The obvious move is to stop trading BOS 30m in the quiet third. A threshold fixed on the
**research block only**, then applied to both blocks:

| leg | filter | research $/trade | LOCKED $/trade |
| --- | --- | --- | --- |
| BOS 30m | all trades | 30 | 182 |
| BOS 30m | quiet third removed | **25** | 369 |
| BOS 60m | all trades | 118 | 279 |
| BOS 60m | quiet third removed | **89** | 435 |
| S/D 4H→60m | all trades | 55 | 144 |
| S/D 4H→60m | quiet third removed | 89 | 173 |

**On the block a threshold may legitimately be chosen on, the filter makes two of the three legs
worse.** It only looks good on the block it was not allowed to see. An effect that fails in-sample
and succeeds out-of-sample is luck with a story attached, not signal — the tercile pattern is
driven by the locked block, which is to say by 2025, which is to say it is a regime observation
and not a tradeable rule.

**Nothing is adopted from this study.** The `ATR / 20d mean ATR` variant is marginally better
(research 30 → 33 on BOS 30m) but reverses on BOS 60m (118 → 94, and locked 279 → 144), so it
fails the same way.

## What this study is actually for

Not a filter. Two things:

1. **The book is close to three independent bets (2.90 of 3).** Position sizing can use that;
   three legs at rho ≈ 0.15 support meaningfully more total risk than three at rho ≈ 0.8.
2. **Each leg has a legible market signature**, and they differ. That is a reason to expect the
   diversification to persist rather than to be a sampling accident — a momentum leg and a
   mean-reversion leg do not stop being different when the sample changes.

## Reproduce

```
python3 research/corr_matrix2.py
```
