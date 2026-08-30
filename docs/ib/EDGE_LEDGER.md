# Edge-search ledger

The loop's memory. One row per round; the container is wiped roughly hourly and this file is why
the search does not restart from zero. Newest first.

## QUEUE

1. **SELECTION at a fixed fill rate** — for constant fill, does the market-price value of the
   filled subset fall as signal immediacy rises? Sweep expiry to hold fill constant; build the
   ladder to span positive immediacy. *(from V49's post-mortem)*
2. **The exit geometry attacked directly** — measure what the exits are worth against a random
   entry, before another trigger is added.
3. **Where the ATR stop stops being a stable denominator** — at what width does R break down?
4. **Mean reversion at the execution layer**, not the signal layer.

## ROUNDS

| date | hypothesis | gate reached | the deciding number | decomposition | follow-up |
| --- | --- | --- | --- | --- | --- |
| 2026-08-30 | The limit entry's advantage falls as signal immediacy rises, crossing zero | **failed at gate 2** | ρ −0.193 vs required −0.50; permutation p 0.122 | delta is a residual of SELECTION −0.5492 and PRICE +0.5366, near-cancelling in 44/44 families; PRICE is ~an arithmetic identity (1.0 ATR entry ÷ 2.0 ATR risk = 0.5 R); the mechanism is **stronger in SELECTION (ρ −0.384) than in the net (−0.321)**; immediacy spanned only −0.119 to +0.034 with 2 of 44 positive | test SELECTION at fixed fill rate → queue item 1 |
