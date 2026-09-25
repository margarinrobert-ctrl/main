# V15 — the synthesis, and the order-model error it uncovered

**The headline is a correction, not a result.** Building the parity harness for V15 showed that the
research engine's limit-entry model fills trades a script cannot fill, and that the difference is
worth roughly half of every limit-entry number on this branch. The book still ships, at half the
size it was written up as.

---

## 1. What was being built

One book combining everything on this branch that had beaten its own control:

| leg | rule | entry | exit |
| --- | --- | --- | --- |
| short (shipped) | Donchian 30 down-break, EMA13 < EMA34, ADX(14) ≥ 22, 07:00–11:00 NY | resting limit 0.75 × ATR(5) above the close, 8-bar expiry | nearer of 2.5 × ATR(20) and the 25-bar high; target 2R |
| long (off) | Donchian 30 up-break, ADX ≥ 25 **and** ER(20) ≥ 0.30 **and** CHOP(14) ≤ 55 **and** EMA13 > EMA48 **and** EMA12 > EMA100 | resting limit 0.75 × ATR(5) below | nearer of 2.0N and the 20-bar low; no target |

US30 and US100, 15-minute bars, 2024-08 → 2026-08. Points are not comparable across two
instruments, so every trade is divided by **its own stop distance** and the book is measured in R.
Train is everything before 2026-01-01; the judged block is 2026-01-01 → 2026-08-26.

---

## 2. The error

`research/v15/v15_parity.py` re-implements this script's order model bar by bar and diffs it
against `eem.run`. The diff is the point of the file, and it says two things at once:

| market / leg | engine | this script | kept |
| --- | --- | --- | --- |
| US30 short | 216 trades, +62.4R, PF 1.57 | 174 trades, +29.5R, PF 1.31 | 47% |
| US30 long | 311 trades, +58.6R, PF 1.34 | 260 trades, +13.9R, PF 1.09 | 24% |
| US100 short | 214 trades, +55.9R, PF 1.50 | 168 trades, +17.5R, PF 1.18 | 31% |
| US100 long | 276 trades, +97.0R, PF 1.73 | 246 trades, +34.0R, PF 1.25 | 35% |

**Every trade the two engines share is identical** — exit bar match 100%, P&L correlation 1.0000,
on all four legs. The exit machinery, the bracket, the fill-bar rules, the channel indexing and the
stop cap are exact. The entire gap is *which signals get filled*.

The engine scans forward from each signal in turn and fills at **that signal's** level:

```
for i in signals:                 # in order
    for k in i+1 .. i+8:          # that signal's own 8-bar window
        if bar k reaches level(i): fill
```

so a limit priced eight bars ago outranks a nearer one priced since. Reproducing that requires
eight simultaneous resting orders **and** for the far one to fill before the near one — which is
the opposite of how a resting book fills. A script has one live order.

Three implementable policies were measured against it (`arm=` in the harness):

| policy | what it does | US30 short R |
| --- | --- | --- |
| engine | oldest level wins, eight windows overlapping | +62.4 |
| `hold` | order rests untouched, new signals ignored until expiry | **+29.5** |
| `best` | re-price only if the new level is further in our favour | +21.8 |
| `replace` | re-price on every fresh signal | +14.8 |

`hold` is both the best of the three and the plain reading of the script, so it is what ships and
what every number below is computed with. Note `replace` — the intuitive "keep the order current"
choice — gives back three quarters of the leg by chasing the market.

**This correction applies to every limit-entry figure on the branch**, `STUDY_V10_LIMIT.md` and
`STUDY_V14_WINDOW_GRID.md` included. It does not touch any market-order result.

---

## 3. Selection, on train, against a matched control

The control draws random entries with the same side, geometry, order type and minute-of-day mix,
300 times per leg, and asks how often it beats the rule. It is run as the **gate**, not the final
check.

| book | train R | Sharpe | maxDD | control p | 2026 R | Sharpe | maxDD | ret/DD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **shorts, limit** | **+24.0** | **1.32** | **13.2** | **0.003** | **+23.0** | **2.50** | **9.2** | **2.50** |
| shorts, market | +5.5 | 0.20 | 26.2 | 0.330 | +22.9 | 1.82 | 13.3 | 1.72 |
| full, limit | +66.3 | 1.26 | 33.0 | 0.017 | +28.6 | 1.14 | 24.9 | 1.15 |
| full, market | +59.9 | 0.89 | 31.2 | 0.357 | +42.4 | 1.32 | 29.2 | 1.45 |

The choice was made on the train columns. **The limit is what clears the control; with market
orders neither book does** (p 0.33, p 0.36). Adding the long leg nearly triples the judged drawdown
and halves Sharpe, so it ships off.

The judged block was then read once: **81 trading days, +23.0R, Sharpe 2.50, max drawdown 9.22R**,
and against the same control **p = 0.010** — with the control's *median* outcome at **−10.9R**.
Random entries with this side, geometry and session lose money; the rule is doing the work.

---

## 4. A claim that did not survive its own correction

The pre-correction write-up said the limit beat a market order in **all eight** cells and called it
the largest single effect in the study. With the implementable order model it wins four and loses
four:

| cell | market | limit | winner |
| --- | --- | --- | --- |
| US30 short train | PF 0.84, −18.5R | PF 1.23, +15.6R | limit |
| US30 short judge | PF 1.12, +6.4R | PF 1.50, +14.0R | limit |
| US30 long train | PF 1.18, +25.0R | PF 1.29, +30.1R | limit |
| US30 long judge | PF 1.05, +3.4R | PF 0.70, −16.1R | market |
| US100 short train | PF 1.23, +24.0R | PF 1.13, +8.4R | market |
| US100 short judge | PF 1.30, +16.6R | PF 1.29, +9.1R | tie |
| US100 long train | PF 1.25, +29.4R | PF 1.14, +12.3R | market |
| US100 long judge | PF 1.27, +16.0R | PF 1.47, +21.7R | limit |

The surviving claim is narrower and better supported: the limit is not uniformly the better fill,
but it is the version that **clears a matched control**, and it does so by taking fewer and better
trades. On the judged block the two mechanics earn the same net R (+23.0 against +22.9); the limit
earns it at Sharpe 2.50 against 1.82 on **half** the drawdown.

---

## 5. Stability of the shipped book

* **Quarters**, both instruments, 2024-Q3 → 2026-Q3, in R: −0.9, +2.5, +10.4, +4.3, −0.5, +8.2,
  +19.8, +4.3, −1.1. **6 of 9 positive, worst −1.1R.** One quarter (2026-Q1, +19.8R) is 42% of the
  whole result.
* **Monte Carlo**, 20,000 shuffles of the judged daily series: realised drawdown 9.22R against a
  median of 9.4 and a p99 of **18.3**. Size for 18R, not the 9 that is visible.
* **Bootstrap** on the judged block: P(mean daily R ≤ 0) = **0.073**. Not significant at 5%. The
  book clears its control at p 0.010 and does **not** clear zero on 81 days of daily data — those
  are different questions and an eight-month holdout can answer the first but not the second.
* **Leave-out**: drop a random 10% of days, Sharpe p5 1.47, median 2.48. No single stretch carries
  it.

---

## 6. Sizing, and why this is not an evaluation strategy

Risk a fixed fraction per trade sized off the stop, never a fixed contract count. 60 trading days,
6% target, 4% trailing drawdown, 20,000 paths, resampled from the book's daily R:

| risk/trade | P(pass) | P(bust) | edge | P(neither) |
| --- | --- | --- | --- | --- |
| 0.25% | 25.5% | 12.8% | **+12.8%** | 61.7% |
| 0.50% | 49.4% | 47.9% | +1.5% | 2.7% |
| 0.75% | 45.3% | 54.7% | −9.4% | 0.0% |
| 1.00% | 42.3% | 57.7% | −15.5% | 0.0% |

Read the last column first. **At the only risk level with a real edge, the likeliest outcome by far
is that 60 days ends with neither a pass nor a bust.** This book does not clear a 6% target inside
an evaluation window at survivable risk; sized to survive, it grinds. It is an income book for a
funded account, not an evaluation strategy — the same conclusion `STUDY_V9_PROP.md` reached from
the other direction, that prop evaluations are bound by the rule set rather than by the strategy.

---

## 7. What would move this

1. **One-minute US30 and US100 bars.** The whole result rests on a limit entry, and
   `STUDY_V10_LIMIT.md` established that limit-entry questions are settled on the true 1-minute
   path or not at all. The order-model error found here is exactly the class of thing that hides at
   15-minute resolution. This is the single highest-value missing input.
2. **A longer holdout.** Eight months is why the bootstrap sits at 0.073.
3. **A third instrument.** Two markets and one of them (US100 short) does not beat its own control
   in isolation.

## Files

`research/v15/v15book.py` (features, legs, geometry) · `research/v15/v15_parity.py` (the order-model
diff and the three arming policies) · `research/v15/run_book.py` (the whole table above) ·
`pine/turtle/V15_BOOK_strategy.pine`.
