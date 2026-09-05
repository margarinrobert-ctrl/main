# V53 — The underfit version: lower-timeframe absorption, every tuned number removed

**Adding conditions buys research score that does not survive the split, and the population shows it
directly: corr(research R, locked R) falls from +0.2366 with no filter to +0.0579 with one and goes
NEGATIVE (−0.0382) with two, while mean research R rises +0.0517 → +0.0812 and mean locked R does
not move. The most underfit version — zero conditions — has the best cross-block agreement and gives
up nothing out of sample.**

And nothing clears its control on both blocks, including the bare base against a random entry
(p 0.051 research, 0.109 locked).

---

## What changed, at the user's direction

* Absorption is now **two readings** — buyer or seller — detected on a **lower timeframe than the
  chart, automatically**, so a 1-minute absorption is visible from a 15-minute chart.
* **Its two tuned numbers are gone.** The volume-spike multiple and the close-inside-the-range
  fraction were free parameters a sweep can fit. They are replaced by the two values that cannot be
  tuned: volume at or above its **own rolling mean** (a ratio of exactly 1.0) and the close on the
  wrong side of the bar's **midpoint** (exactly 0.5).
* **The EMA 100 is gone**, with the ADX gate, the session window, the flatten, the pyramid ladder,
  the near/far bands and every preset. What is left is the 200 EMA, the 13 and the 48.

**30-second absorption cannot be tested here and was not proxied.** The finest bars on this branch
are 1-minute. The Pine can still request 30s; that setting is unmeasured and is labelled so.

**Causality.** A 1-minute absorption at T+3 inside a 15-minute bar starting at T is complete at T+4,
before the trading bar closes — so reading it at the signal bar's close uses only settled data.

**Grid:** 4 timeframes × 4 entry × 4 exit × 4 stop × 5 MA200 × 3 cross × 73 absorption =
**280,320 configurations**, all resampled from the same NQ 1-minute series so the lower-timeframe
absorption and the trading bars align exactly. Research = first 65%, locked = last 35%, read once.
The grid was diffed against an independent plain-Python simulation on 10 cells — trade counts
identical, mean R to 1e-9.

## The underfitting reading

206,436 cells clear 100 research and 30 locked trades; 73.5% are profitable on research.

| active conditions | cells | research R | locked R | corr(research, locked) | median n | locked positive |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 254 | +0.0517 | +0.0780 | **+0.2366** | 727 | 86.2% |
| 1 | 18,544 | +0.0709 | +0.0895 | +0.0579 | 459 | 83.5% |
| 2 | 93,098 | +0.0812 | +0.0845 | **−0.0382** | 308 | 78.1% |
| 3 | 94,540 | +0.0755 | +0.0925 | +0.0480 | 250 | 77.6% |

This is what overfitting looks like when the whole population is visible rather than one cell.
Research score is bought and locked score is not.

**The timeframe axis says the same thing.** Research rises monotonically to 60m (+0.1965) while
locked falls to it (+0.0304). 60m is the overfit end of that axis; 30m is where the two blocks agree
most closely (+0.1192 / +0.0896) and is the base used below.

**The one reassuring result — the surviving number is inert.** Locked mean R at volume-mean windows
50 / 100 / 200 is +0.0887 / +0.0871 / +0.0904. Removing a tuned parameter is supposed to look like
this.

## The controls

Base: NQ 30m, Donchian 20 in / 20 out, 2.0N stop, one unit, long, no target, max hold 480. Each
condition against a random filter of the same selectivity (2,000 draws); the bare base against a
random entry with identical exits.

| condition | research | locked |
| --- | --- | --- |
| base (vs a random **entry**) | +0.0945 p 0.051 | +0.1280 p 0.109 |
| MA200 above | +0.1212 p 0.084 | +0.0861 p 0.979 |
| MA200 ≥ 1.5 ATR above | +0.1149 p 0.259 | +0.0380 **p 1.000** |
| EMA13 > EMA48 | +0.1027 p 0.408 | +0.1087 p 0.878 |
| EMA13×48 cross ≤ 20 bars | +0.1042 p 0.722 | +0.1661 p 0.297 |
| buyer absorption 4m | +0.1002 p 0.636 | +0.2320 **p 0.007** |
| buyer absorption 3m | +0.1035 p 0.455 | +0.1809 p 0.048 |
| buyer absorption 15m | +0.1465 p 0.485 | +0.2421 p 0.054 |
| seller absorption 15m | +0.2131 p 0.113 | +0.0333 p 0.880 |

The bare base does not clear a random entry on either block. No condition clears a random filter on
both. **The absorption readings that look strongest on locked fail on research** — a rule chosen on
research should look better there, so passing out of sample while failing in sample is a defect, not
a result. That is the fifth time on this branch.

### The lower-timeframe axis has no gradient, which is the tell

Locked mean R by the timeframe absorption is read on, against **+0.0808** for absorption off:

| LTF | buyer | seller |
| --- | --- | --- |
| 1m | +0.0967 | +0.0759 |
| 2m | +0.0951 | +0.0706 |
| 3m | +0.0734 | +0.0776 |
| 4m | +0.1132 | +0.0831 |
| 5m | +0.0819 | +0.1357 |
| 15m | +0.0833 | +0.0656 |

Scattered around the no-filter baseline with no monotone structure in either direction. A real
mechanism decays smoothly across a parameter; this does not. Compare V51, where the same proxy on
60m US100 put *requiring* seller absorption in 0.00% of the top 1000 in five of six variants, and
V52, where it cleared both US100 blocks on n = 22. Three studies, three different answers — which is
itself the answer.

## vectorbt: run, and it failed its transcription check for the third time

`sl_stop` is a fraction of price, so a per-trade ATR stop **can** be passed as an array — that part
works. The check was run on the ATR-stop-only geometry, where vectorbt should be able to reproduce
the engine exactly:

```
engine    trades   175   mean R +0.5618
vectorbt  trades     6   mean R +10.1503   count ratio 0.034
```

Five configurations were tried — full OHLC passed (the first attempt passed only `close`, which was
my own omission and is corrected above), `exits` as an all-False Series, no `exits` argument, a
scalar `sl_stop`, and `stop_entry_price="fillprice"`. Every one returned the same 6 trades. The stop
**level** is right: a 0.4% stop from 14631.25 exited at 14572.725, exactly 0.4% below. The **timing**
is not: one position opened 2023-01-31 09:00 and did not close until 2023-03-01 20:00, through a
month in which price traded well below that level, swallowing every entry signal in between. 175
entry signals produced 11 orders.

No vectorbt number is reported. Every figure in this study comes from the verified engine.

## Caveats

One market — the lower-timeframe work needs 1-minute data and only NQ has it, so US100 and US30
could not be used here. NQ's locked block scores *higher* than its research block almost everywhere,
which is the wrong direction and reflects a strong up period rather than an edge. Absorption remains
a proxy: real absorption needs bid/ask volume at price and no feed on this branch carries it. Spread
is assumed.

## Files

`research/v53/v53abs.py` (1-minute loader, parameter-free absorption, the LTF→trading-bar mapping) ·
`run_v53.py` (the 280,320-cell sweep) · `v53_verify.py` · `analyse_v53.py` (the underfitting
reading) · `run_v53b.py` (the controls) · `v53_vbt.py` (the vectorbt check) · `results/v53/` ·
`pine/v53/V53_UNDERFIT_LTF_ABSORPTION_strategy.pine`.
