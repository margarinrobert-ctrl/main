# V40 — feature engineering and an independence matrix on a Donchian 40/25 morning long

**Brief, fixed and not searched:** Donchian 40 entry / 25 exit, MA(200) as support/resistance, long
only, entries 07:00–11:00 New York with a hard flatten at 11:00, and added filters that must be
*independent of one another*. The ATR stop was handed back and swept.

## 1. The base loses at every stop

NQ 30m research block, ten stop multiples:

```
stop xATR   n     PF   $/trade   Sharpe   ret/DD
     1.00  187  0.857    -5.67    -0.48    -0.39
     1.50  176  0.866    -6.21    -0.45    -0.49
     2.00  170  0.903    -4.77    -0.31    -0.49
     2.50  167  0.832    -9.17    -0.56    -0.74
     3.50  164  0.753   -15.73    -0.84    -0.91
```

Every one negative, curve flat-to-falling; 15m is worse still (PF 0.76–0.82 across the same range).
**No stop rescues this.** 2.00N is the least bad and became the default. The filters below had to
close a gap of 0.10–0.25 profit factor before being worth anything at all.

## 2. The window — and the branch's own rule is backwards here

| window | research PF | LOCKED PF | locked $/trade |
| --- | ---: | ---: | ---: |
| **07:00–11:00** (the brief) | 0.903 | 0.957 | −2.63 |
| 07:30–11:00 | 0.914 | 1.057 | +3.25 |
| 08:30–11:00 | 0.850 | 1.067 | +3.54 |
| **09:30–11:00** | **0.713** | **0.699** | **−16.42** |
| 09:30–12:00 | 0.959 | 0.879 | −7.52 |
| 09:30–16:00 | 1.208 | 1.152 | +11.60 |
| **all hours, no flatten** | **1.366** | **1.140** | **+16.61** |

`STUDY_TREND_PULLBACK` and `STUDY_INTRADAY_SESSION` both record 07:00–09:00 as the worst part of
the day and a 09:30 start as what rescues an intraday window. **On this geometry that is exactly
backwards: 09:30–11:00 is the worst of the seven rows.**

The mechanism is the *flatten*, not the start. A 40-bar entry channel with a 25-bar exit needs room
to run; a four-hour box truncates precisely the trades the channel exit exists to hold, and a
09:30 start shortens the box further. This is the same finding as *"a fixed-time flatten costs
about half the per-trade edge when there is no entry window"* (`STUDY_V16`), and it is why the
session-preference rule does not transfer between strategies — which is itself a recorded lesson
here, now confirmed in the other direction.

## 3. Independence, measured where it matters

Seventeen features in eight declared concept families — TREND, CHOP, VOLLEVEL, VOLCHG, LOCATION,
PARTIC, SHAPE, CLOCK. Two rules govern the selection, in this order:

1. **At most one per family**, declared by hand *before* any correlation is computed.
   `STUDY_TURTLE_FEATURES` records five of six "independent" picks all turning out to be volatility
   level, which a |ρ| ceiling had passed. Family first, correlation second.
2. **|ρ| ≤ 0.35 against everything already picked, computed on the SIGNAL BARS ONLY.** A filter
   only ever acts on breakout bars inside the window. `STUDY_V21_ADX_CHOP` measured this directly:
   68.3% of the bars CHOP keeps already pass ADX, so on breakout bars they are largely one filter.

### Two exact duplicates in my own pool, found by the matrix rather than by reading

| pair | ρ | why |
| --- | ---: | --- |
| `chop14_inv` == `range_eff14` | **1.0000** | CHOP is `100·log10(ΣTR/range)/log10(14)`, a monotone transform of `range/ΣTR` |
| `close_pos` == `upwick_share` | **1.0000** | on an up bar, upper-wick share is close position minus one |

Fourth time this branch has caught its own pool duplicating. Collapsing is **conservative** — it
lowers the effective test count — so nothing published needs revising. But a drop-one test on a
stack containing such a pair would report a filter contributing nothing when it was never a second
filter.

## 4. One filter of seventeen earns its place

Each feature cut at two research-derived quantiles, scored against a **random filter of the same
selectivity**:

| feature | family | keep | PF | $/trade | control $/t | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| **dist_ma200_atr** | LOCATION | 0.50 | **1.171** | +7.92 | −5.85 | **0.017** |
| dist_ma200_atr | LOCATION | 0.65 | 1.081 | +3.60 | −6.39 | 0.022 |
| ma200_slope_atr | LOCATION | 0.65 | 1.070 | +3.02 | −6.39 | 0.035 |
| adx14 | TREND | 0.50 | 1.057 | +2.52 | −5.85 | 0.090 |
| chop / range efficiency | CHOP | 0.65 | 1.002 | +0.08 | −6.39 | 0.092 |
| body_share | SHAPE | 0.65 | 0.995 | −0.24 | −6.39 | 0.110 |
| *…28 more* | | | | | | > 0.10 |

**3 of 34 cells clear p ≤ 0.05 against 1.7 expected by chance — and all three are the same family.**
That is one finding, not three.

**What the feature is matters.** Not "close above the MA200" — that is the base condition and is
worth nothing alone. It is **how far above, in ATR units, keeping the top half of breakout bars**.
Same lesson as `STUDY_KAMA_ENTRY`: *a moving average is priced by its distance, not by the average.*

The greedy selector filled all six remaining families, and four of its picks had control p > 0.7.
A filter that loses to a random one of the same selectivity does not earn a place just because its
family is unrepresented, so the stack admits only what clears p ≤ 0.10 — which is one thing.

## 5. The stack, with the locked block read once

| NQ 30m, 2.0N | research | **LOCKED** |
| --- | --- | --- |
| base (Donchian 40/25 + MA200 support) | n 170, PF 0.903, −$4.77 | n 88, PF 0.957, −$2.63 |
| **+ MA200 distance, top half** | n 82, PF **1.171**, +$7.92 | n 46, PF **1.208**, **+$11.24** |

It converts a losing base into a winning one on both blocks. Then the caveats, all of which matter
more than the headline:

- **Not significant.** Day-block bootstrap P(mean ≤ 0) = **0.300** on both blocks, on 46 locked
  trades.
- **The realised locked drawdown of $1,556 EXCEEDS the Monte Carlo p99 of $1,457.** The realised
  path was unlucky, not lucky. Size above what you see.
- **Locked slightly better than research** (1.208 vs 1.171) — mildly the wrong shape, though inside
  noise at this n.

## 6. Two markets that had no part in any of it

| | base research / LOCKED | + MA200 distance |
| --- | --- | --- |
| **US100** | 0.899 / 1.055 | **1.001 / 1.328** |
| **US30** | 0.970 / 0.708 | 0.950 / **0.757** |

Helps on US100, does not rescue US30 — whose locked block is badly negative in this window with or
without it (−$70.74 and −$55.97 a trade). One of two.

## Verdict

The brief is buildable and the MA200 does carry something, read as a distance rather than a
threshold. But **the 11:00 flatten costs more than the filters recover**: the same rule with the
session turned off reads PF 1.366 research / 1.140 locked, against 0.903 / 0.957 inside the box.
The single largest improvement available to this script is the input that switches the session off.

Shipped as `pine/v40/V40_DONCHIAN_MORNING_strategy.pine`, defaults exactly as briefed, with the
non-surviving candidates present as default-off toggles carrying their control p in the tooltips.

## Files

| file | what it does |
| --- | --- |
| `research/v40/v40feat.py` | 17 features in 8 declared families, signal-bar correlation, the two-stage independent selector |
| `research/v40/run_v40.py` | the stop sweep, the window table, the matrix, the control-gated filter table, the stack, cross-market, Monte Carlo |
| `research/v38/v38grid.py` | `_walk_flat` / `tensor_stop` — the exit walk with a hard flatten that fills at the NEXT open, matching what a script gets |
| `docs/ib/v40_output.txt` | raw output |
