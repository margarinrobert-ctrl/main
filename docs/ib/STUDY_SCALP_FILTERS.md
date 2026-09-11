# Can any indicator raise the 07:00–11:00 scalp's locked profit factor by 25%?

`research/inst/run_scalp_filters.py`, `results/inst/scalp_filters.txt`, `scalp_filters.parquet`.
The base is the surviving Optuna finalist under the user's constraints — NQ 15m, entries
07:00–11:00 New York, Donchian **10/10** (the search printed 7/8; its evaluator clips channel
lengths to a floor of 10, so 10/10 is what was measured and what ships), 3.19 ATR stop, 2.3 ATR
target, 230-minute hold, no filters. Reproduced here to within the rounding of the printed
parameters: research 765 trades PF 1.164 +15.0%, locked 389 PF 1.110 +6.0%.

The ask — raise the *locked* PF by at least 25% — names a holdout number, so the holdout was never
consulted to choose. Procedure: 38 declared conditions at the signal bar in eight families, drawn
from what this branch has measured as helping a scalp (`STUDY_SCALP_REQUIREMENTS`) plus the
confirmations known to be the trigger restated as base-rate controls; each scored on research
against a random filter of the same selectivity (250 draws); Benjamini-Hochberg at q = 0.10 across
the pool; survivors also required to keep ≥100 research trades and add ≥10% PF; the survivors and
their stack read **once** on locked.

## Verdict

**Not reachable.** No condition in the pool lifts the research PF by 25% (the best is +12.3%),
three of 38 clear their control at p ≤ 0.05 against 1.9 expected, one survives correction, and
that one — `ADX ≥ 20` — **lowers the locked PF by 5.7%** (1.110 → 1.047), cuts the locked total
from +6.0% to +2.1%, and is beaten by a random filter of its own selectivity on the locked block
(p 0.764). The target was +25%; the delivered change is −6%.

## The three that cleared research, and what happened to them

| condition | keeps | research PF | ΔPF | control p | BH | locked |
|---|---|---|---|---|---|---|
| `ADX ≥ 20` | 73% | 1.307 | **+12.3%** | **0.000** | pass | **1.047 (−5.7%)**, p 0.764 |
| entries from 08:30 only | 66% | 1.264 | +8.6% | 0.012 | fail | not read |
| close ≥ 1 ATR above VWAP(07:00) | 48% | 1.232 | +5.9% | 0.040 | fail | not read |

ADX inverting out of sample is this branch's oldest result on that indicator (`STUDY_V39`: "ADX
gets worse the tighter it gets and inverts"; `STUDY_V52`; `STUDY_V60`), now reproduced on a
scalping base. Its mirror, `ADX < 20`, is the worst condition in the pool (PF 0.786 on research),
which is what makes the floor look strong in-sample — it removes the trades that happen to be bad
in that block.

## What the rest of the pool says

- **The clock**: starting at 08:30 is the second-best condition (+8.6%, p 0.012) and *before
  09:30 only* is the second-worst (−17.1%, p 1.000) — the pre-open block is subtractive again, the
  fourth time here — but neither survives the correction on this base.
- **Participation**: `volume ≥ 1.5× time-of-day` is −0.4%; `≥ 2.0×` is −15.9%. What was the best
  scalp condition in `STUDY_SCALP_REQUIREMENTS` does nothing on a base that already trades a
  wide-stop 10-bar breakout.
- **Volatility**: every floor is +3.5 to +4.9% at p 0.08–0.12; every ceiling (`ATR < 1.0×`,
  `calm`) is −17 to −26% at p 0.96–0.99. Direction consistent with V63's ATR finding; magnitude
  short of the gate.
- **Location**: MA200 ≥ 2 ATR +3.2%, prior RTH high −1.7%, VWAP distance +5.9% — small.
- **Order flow**: the two bullish CVD patterns are −4.4% and −2.6% here; `CVD rising` +3.8% at
  p 0.052. The pattern that carried V54/V55 on a 30-minute Donchian does not carry a 15-minute,
  10-bar, 4-hour-capped one.
- **The confirmations are the trigger restated, again**: `RSI ≥ 55` passes 82% of the base's
  signal bars, `MACD > 0` 90%, `EMA13 > 48` 74%, `+DI > −DI` 94%, `CVD rising` 87% — and none
  helps (−5.0 to +1.1%).

## What to carry

- A +25% lift in locked PF is not a filter-sized effect on this base. The largest in-sample lift
  available from 38 declared conditions is half that, and it does not transfer.
- The base is a coin flip (49–52% wins) whose small edge is in its exit geometry; a filter can
  only remove trades from it, and the trades it removes are the ones its edge lives in.
- The Optuna study's "7/8" was a clipping artifact of the evaluator's channel floor; the shipped
  Pine is corrected to 10/10 and reproduces the measured numbers.
