# Real commissions, fees, slippage and entries

Asked for: real broker commissions, fees and slippage, and real entries, on all the strategies.

## 1. What was wrong

Two cost models existed, both of them one number and a flat tick.

**TypeScript** carried `commissionRoundTurn` — a single figure standing in for four separate
charges — plus `slippageTicks`, applied identically to every fill.

**Python** was worse: `PV = 2.0; TICK = 0.25; COMM = 1.0; EC = 2*TICK; SE = 1*TICK` copy-pasted as
bare constants into about twenty modules. `COMM = 1.00` is **broker commission only**. It has no
CME exchange fee and no NFA line. On MNQ the exchange fee is roughly the broker's own charge
again, so the real round turn is nearer **$1.44 than $1.00** — every result in `docs/ib/` was
measured about 44% light on fees.

The flat tick is the subtler problem. It is charged in the calm bars where it is not paid and
understated in the fast ones where it is, and a stop-loss strategy exits preferentially into fast
bars — that is *why* stops trigger. The bias is neither small nor symmetric.

## 2. What replaced it

One model, defined twice so the two engines cannot drift: `src/lib/quant/costs.ts` and
`research/costs.py`.

**Fees, itemised per side**, the way a statement itemises them:

| | MNQ | NQ |
| --- | ---: | ---: |
| broker (discount preset) | $0.35 | $0.85 |
| exchange | $0.35 | $1.18 |
| clearing | $0.00 | $0.00 |
| regulatory (NFA) | $0.02 | $0.02 |
| **round turn** | **$1.44** | **$4.10** |

Four broker presets ship — `discount`, `ibkr`, `propfirm`, `premium` — and each is a component
breakdown, not a number. The decomposition makes one thing unavoidable that a lumped commission
hid: **MNQ carries a tenth of NQ's tick value against roughly a third of its fee**, so an
identical strategy pays several times as much of its edge away on the micro. `costs.test.ts`
asserts that relationship holds whatever the numbers are replaced with.

**Slippage as a model, not a constant.** Ticks charged on a fill depend on:

* **the role of the fill** — a resting limit pays nothing; a market order pays the spread and
  slippage; a **stop pays a premium on top**, because it becomes a market order into a book that is
  moving away by construction;
* **how fast the bar was**, measured against the series' own *median* true range — median, not
  mean, because bar ranges are heavy-tailed and a mean is dragged up by exactly the fast bars the
  model is trying to charge extra for;
* **whether the fill was in session**, doubling outside it;
* capped at 3x, so one freak bar cannot set the cost of a whole study.

**Real entries.** The fill roles are now wired through both engines, so what a trade pays depends
on how it actually entered and left: `taker` (every fill crosses, the pessimistic case), `realistic`
(a target rests and pays fees only), `passive` (the entry rests too). Under `realistic` the gap
between a target exit and a stop exit is one taker side **plus the stop premium** — under the old
flat model it was one taker side, and that missing premium is the specific way a flat tick flatters
a stop system.

## 3. What it costs the strategies

### TypeScript, NQ 5-minute, 210,516 bars — `npx tsx scripts/quant-costs.ts`

Here the change is one-directional: the old model already charged 1.5 ticks per side, so the new
one is worse everywhere.

| | old $/tr | real $/tr | delta | verdict |
| --- | ---: | ---: | ---: | --- |
| orb | 41.01 | 22.34 | −18.67 | still positive |
| gap-fade | 335.81 | 316.51 | −19.31 | still positive |
| opening-range | 100.53 | 85.58 | −14.96 | still positive |
| value-area | 72.02 | 53.08 | −18.94 | still positive |
| profile-levels | 76.36 | 57.45 | −18.91 | still positive |
| **moving-average** | **12.24** | **−4.57** | −16.81 | **was profitable, now is not** |
| **tod-control** | **0.53** | **−17.86** | −18.39 | **was profitable, now is not** |
| vol-breakout, initial-balance, vwap-bands, vwap-fade, ou-reversion, sweep-reversal, trend-pullback | — | — | −10 to −17 | negative either way |

**Two crossed from profitable to unprofitable**, and one of them is the time-of-day control — which
matters, because a control that was marginally positive was making every strategy compared against
it look worse than it should.

### Python, the nine shipped MNQ strategies — `python research/real_costs.py`

Here the change is **not** one-directional, and saying otherwise would be wrong. Per round turn:

```
fees      $ 1.00 -> $ 1.44   (+0.44)  the exchange and NFA lines the old number omitted
friction   4.00t ->  3.00t   (-1.00t) on a CALM bar; up to 13.00t on a fast one out of session
calm round turn $3.00 -> $2.94
```

`sim_core` billed a flat 2 ticks per side. The new model bills half a 1-tick spread plus 1 tick of
slippage — 1.5 ticks on a median bar, which is a fairer description of a liquid micro mid-session —
and far more on a fast one. So the net direction is a property of a strategy's **exit mix**, not
something the model decides in advance.

The nine survive comfortably:

| | n | stop % | old $/tr | real $/tr | delta | real net | real locked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| M1 | 85 | 22 | 39.2 | 38.2 | −1.0 | 3,245 | 1,481 |
| M2 | 120 | 36 | 22.0 | 21.0 | −1.0 | 2,514 | 697 |
| M3 | 92 | 34 | 39.1 | 37.9 | −1.2 | 3,484 | 1,300 |
| M4 | 88 | 7 | 102.3 | 101.1 | −1.2 | 8,898 | 2,754 |
| V1 | 249 | 28 | 35.9 | 34.6 | −1.3 | 8,606 | 2,187 |
| V2 | 201 | 38 | 21.8 | 20.9 | −0.9 | 4,201 | 2,468 |
| V2L | 139 | 17 | 68.9 | 68.0 | −0.9 | 9,454 | 4,809 |
| V3 | 158 | 20 | 69.5 | 68.2 | −1.3 | 10,780 | 7,305 |
| V4 | 80 | 22 | 37.2 | 35.4 | −1.8 | 2,830 | 1,958 |

**Book $55,424 → $54,011, a 3% give-back, and none of the nine flips.** They survive because they
are low-frequency (80–250 trades over three years) against a per-trade edge of $20–100, so a ~$1
change in cost is noise to them. That is a real and reassuring result, and it is the opposite of
what happened to the high-frequency TS strategies — which is exactly the point: **cost realism
punishes turnover, not edge.**

Under every broker preset:

| broker | fees/rt | book net | vs old |
| --- | ---: | ---: | ---: |
| legacy (the old model) | $1.00 | 55,424 | — |
| ibkr | $1.24 | 54,254 | −1,170 |
| discount | $1.44 | 54,011 | −1,413 |
| propfirm | $1.74 | 53,648 | −1,776 |
| premium | $2.24 | 53,042 | −2,382 |

## 4. Two footguns found and closed

Both were introduced by the change itself and would have silently corrupted studies.

**`{ ...inst, commissionRoundTurn: 0 }` stopped working.** Isolating gross edge by zeroing the
commission is a real and reasonable thing to write, and once `fees` existed it silently did
nothing — the study would report a costed result while believing it had none. Resolved by a stated
precedence rule: **when the headline and the itemised detail disagree, the headline wins**, because
an explicit override is a statement of intent and a derived field is not. The same rule now governs
`slippageTicks` against the slippage model, and both are asserted.

**Costs stopped being a read-time lookup** — or appeared to. Bar-dependent slippage looks
incompatible with the tuner's whole premise, that every knob is an array index. It is not: friction
depends only on **the bar a fill landed on and the role it played**, and the tensor already stores
the exit bar and the exit reason. So friction is precomputed once **per bar** (two arrays, not two
per geometry), fees stay a constant applied at read time, and broker, fill model and cost multiplier
all remain free to change with no rebuild.

## 5. Verification

* **360 TypeScript tests** (22 new, all cost invariants), and the tuner's exit tensor still
  reproduces `runBacktest` **trade for trade** under the new bar-dependent model.
* **Python: exact match preserved** against `sim_core` on 695,527 trades — `research/costs.py`
  reconstructs the pre-change model precisely (`broker="legacy"`, 2 ticks/side, 1-tick stop
  premium), so the equality check is made against the cost stack that was actually in force rather
  than one remembered approximately.
* Invariants asserted rather than assumed: role ordering (maker < taker < stop), monotonicity in
  bar speed, the stretch cap, the session multiplier, that a quieter-than-median bar earns no
  discount, that a zero-cost instrument costs exactly zero, and that MNQ stays the more expensive
  contract per point traded.

## 6. What is still an assumption

The **structure** is exact. The **values** are not, and nothing here is a quote:

* exchange fees change, and differ by membership tier and by whether the trade is electronic;
* broker commissions differ by volume tier and by negotiation;
* **slippage cannot be calibrated from OHLCV at all.** Bars are not order books. The model buys
  that cost stops being independent of the conditions a strategy trades in, which is the specific
  way a flat tick lies — but its coefficients are chosen, not measured.

Take the numbers off your own statement. Every field is separately settable, `describe()` prints
the breakdown to hold next to it, and the cost multiplier sweeps the uncertainty — that sweep, not
the point estimate, is the number to trust.

## Files

| | |
| --- | --- |
| `src/lib/quant/costs.ts` | fee decomposition, broker presets, slippage model, fill roles |
| `src/lib/quant/costs.test.ts` | 22 invariant tests |
| `scripts/quant-costs.ts` | old vs real across every TS strategy |
| `research/costs.py` | the same model for the research layer, plus the exact legacy reconstruction |
| `research/real_costs.py` | old vs real across the nine shipped strategies, and by broker |

Research tooling for education and analysis, not financial advice.
