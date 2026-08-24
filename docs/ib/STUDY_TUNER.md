# The tuning harness — indicators, session, entry, target and stop, at interactive speed

Asked for: the fastest possible loop for tuning indicator settings, trading time, entry, take
profit and stop exit.

The bottleneck was never raw simulation speed — `test_suite.sim_core` is already numba and runs a
30-minute backtest in 1.4 ms. The bottleneck was that **every knob re-ran the whole price walk**,
that a fresh process paid 4.5 s to re-read the 1-minute CSV before showing anything, and that an
indicator PERIOD was not a knob at all: `close>EMA10` is a string in a fixed pool, so asking "what
about EMA 60" meant editing a module.

## 1. The observation the speed comes from

In `sim_core`, a trade's outcome depends **only on the bar it was signalled from and the
geometry**. Nothing about a trade depends on which other trades were taken — the sole coupling
between trades is the no-overlap rule, and that needs the exit *bar*, not the price path.

So the walk can be done once per geometry for **every bar as a hypothetical entry**, and cached:

```
exits[geometry, signal_bar] -> (exit bar, exit reason, gross P&L)
```

After that a rule is a bitmask, and evaluating it is a gather plus a sequential no-overlap scan
over the bars it fired on. No price data is touched. Changing the stop, the target, the flatten
time, the max hold, the entry mechanic or the cost model becomes an array index.

Costs are deliberately kept **out** of the cached number: `raw` is the gross dollar move before
commission, spread and stop slippage, and all three are affine, so any cost assumption is applied
at read time for free. That makes cost sensitivity — the test most likely to kill a scalping
result — the cheapest test in the system rather than the one you skip.

## 2. Measured

`research/tuner_bench.py`. Grid: 5 stops x 5 targets x 2 flatten times x 3 max-holds = 150
geometries.

| | 30-minute bars | 5-minute bars |
| --- | --- | --- |
| cold start, fresh process | 4.42 s -> **0.00 s** | 4.56 s -> **0.01 s** |
| 150 geometries, one rule | 0.20 s -> **0.0001 s** | 1.01 s -> **0.0001 s** |
| per geometry | 1.30 ms -> **0.4 us** | 6.76 ms -> **0.6 us** |
| a new rule (indicators + triggers) | **2.8 ms** | **10.8 ms** |
| 100 rules x the grid | 19.6 s -> **0.31 s** | 101.3 s -> **1.55 s** |
| a 2,000-draw matched control | — | **6–8 ms** |

The tensor costs 0.5 s to build on 5-minute bars and pays for itself after **69 configurations**,
after which every later rule reuses it. The per-geometry figure is the one that matters for
tuning: **3,000x** on 30-minute bars, **11,000x** on 5-minute.

The last row is the important one. A matched control at 6–8 ms can run as a **research gate** on
every configuration instead of as a final check on the survivor — which is what `CLAUDE.md` says
should have been happening, and was not, the two times it cost the most.

## 3. Correctness

Speed is worthless if it measures something else, so the tensor is asserted against the existing
engine rather than argued for. `research/tuner_test.py`:

* **192 rule x geometry x side combinations, 695,527 trades on 30m and 3,950,770 on 5m: exact
  match with `test_suite.sim_core`** — same trade count, same entry bar, same exit bar, same P&L
  to 1e-9. Including the engine's pessimism, that a bar holding both the stop and the target books
  the stop.
* **Costs applied at read time equal costs charged inside the walk**, at 0.5x, 1x, 2x and 3x.
* **Indicator causality**: every indicator is recomputed on a 70% truncation of the series and
  must be unchanged before the cut. This is the check that catches a centred window, a
  whole-sample normalisation or a shift in the wrong direction.
* **Independent agreement**: the tuner re-derives `STUDY_LIMIT_ENTRY`'s finding — on unsignalled
  entries a market order loses (−$1.9 long, −$8.6 short per trade) and a resting limit 0.75xATR in
  your favour earns (+$24.0 long, +$16.7 short) — using a completely separate code path from the
  module that first measured it. Two implementations agreeing on a non-obvious sign pattern, on
  both sides, is worth more than either one's internal consistency.

The ATR the stop is sized in is `bos_choch.atr`, not the rule-side `indpool.atr`. They agree
everywhere except the first n bars, which `bos_choch` marks NaN as a warm-up guard — and that
guard is what stops the earliest trades being sized off an ATR built from two bars.

## 4. What is deliberately slow

Two things were made harder, not easier, because this repository has already paid for both
mistakes.

**The locked block is not visible from a sweep.** `sweep()` returns research-block statistics
only; the locked columns are carried under a leading underscore so they cannot be sorted on,
printed or eyeballed by accident, and sorting by one raises. `reveal(df, k)` is the only way to
see them, it prints the multiplicity you paid to get there, and it labels any configuration that
is *better* on locked than on research as **"GREW ON LOCKED — wrong shape"**. From `CLAUDE.md`:
"Any criterion that touches the locked block puts the holdout inside the selection. This has
happened twice here and both times the result looked better than it was."

**The configuration count is printed before the numbers.** A grid this cheap makes multiplicity
the binding constraint immediately: 480 configurations means 24 expected to reach p<0.05 by
chance, and the header says so before the table does.

Neither guardrail can be turned off by a flag. That is the point — the thing that got faster
should be the search, not the standard of evidence.

## 5. Using it

```
python research/tune.py "close>ema200 and close<ema20 and rsi14<40"
python research/tune.py "close>ema{n} and rsi{p}<40" --set n=50,100,200 --set p=7,14,21 \
        --stop 1,1.5,2,2.5 --target 0.5,1,1.5,2 --flat 0,11:30 --hold 0,6 \
        --win 09:30-11:00 --entry market,limit:0.75 --cost 1,2 --reveal 3
python research/tune.py -i          # interactive; bars, indicators and tensors stay warm
python research/tune.py --catalogue # 42 indicators and how to write each one
```

The rule language takes any indicator at any period — `ema200`, `rsi14`, `stretch10`,
`emadist50` — or call form for several arguments: `macd(12,26,9)`, `supertrend(10,3)`,
`cross(9,21)`. `and` / `or` / `not` and chained comparisons (`35<rsi14<65`) work; they are
rewritten on the parse **tree**, not textually, because `c>ema200 & rsi14<40` parses as
`c > (ema200 & rsi14) < 40` and would silently mean something else.

`{name}` placeholders become sweep axes. Geometry axes are free; rule axes cost one vectorised
indicator pass per distinct value. So widen the geometry first and the rule last.

## Files

| | |
| --- | --- |
| `research/fastbars.py` | disk-cached bar arrays keyed on the source file's mtime and size; 4.5 s -> 0.1 s cold start |
| `research/indpool.py` | 42 indicators with the period as an argument, memoised, built on `indicators.py` and `trendind.py` |
| `research/tuner.py` | the exit tensor, the rule language, `run`, `sweep`, `reveal` |
| `research/tune.py` | command line and interactive prompt |
| `research/tuner_test.py` | trade-for-trade equality with `sim_core`, cost equivalence, causality, cross-check |
| `research/tuner_bench.py` | the timings in §2 |

Measured on MNQ, 2022-12-27 -> 2025-12-11, one contract, $1.00 commission per round turn, one tick
spread plus one tick slippage each side, one extra tick on stops. Research tooling for education
and analysis, not financial advice.
