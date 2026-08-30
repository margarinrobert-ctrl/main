# Edge-search ledger

The loop's memory. One row per round; the container is wiped roughly hourly and this file is why
the search does not restart from zero. Newest first.

## QUEUE

1. **The exit geometry, attacked directly** — V50 sharpened this from a general target to a
   specific one: two trades on the same signal with the same risk denominator, differing only in
   that one entered 1 ATR lower (so its stop sits 1 ATR lower and its clock starts later), diverge
   by up to **0.29 R**, and that divergence is 99.8% of PRICE's cross-family variance. Ask what the
   stop's LOCATION is worth on its own, against a random entry. *(from V50's post-mortem)*
2. **Immediacy measured GROSS**, or families sourced for genuine front-loading — two rounds have now
   failed to span positive immediacy because a ~0.04 R common-mode cost drag pushes both sides
   negative. Mirroring does not fix it. Fix the measurement before testing another gradient on it.
3. **Where the ATR stop stops being a stable denominator** — V43 found a stop censors MAE and
   stop-out share correlates +0.978 with mean MAE; V42 found a channel stop faked a result twice.
   At what width does R break down?
4. **Mean reversion at the execution layer**, not the signal layer.

## ROUNDS

| date | hypothesis | gate reached | the deciding number | decomposition | follow-up |
| --- | --- | --- | --- | --- | --- |
| 2026-08-30 | The limit entry's advantage falls as signal immediacy rises, crossing zero | **failed at gate 2** | ρ −0.193 vs required −0.50; permutation p 0.122 | delta is a residual of SELECTION −0.5492 and PRICE +0.5366, near-cancelling in 44/44 families; PRICE is ~an arithmetic identity (1.0 ATR entry ÷ 2.0 ATR risk = 0.5 R); the mechanism is **stronger in SELECTION (ρ −0.384) than in the net (−0.321)**; immediacy spanned only −0.119 to +0.034 with 2 of 44 positive | test SELECTION at fixed fill rate → queue item 1 |
| 2026-08-30 | At a FIXED fill rate, adverse selection on a resting limit grows with the signal's immediacy | **passed gates 1-5; gate 6 unavailable** | rho -0.5887 vs required -0.50, permutation p 0.0000; monotone on all 5 quintiles; within side L -0.472 / S -0.473; locked -0.312, sign held | a THIRD component: PRICE is an identity only in its MEAN — its sd 0.0674 matches SELECTION's 0.0689 and it moves the OTHER way (rho +0.4711), cancelling to a net 8.3x smaller than its parts; the chasing explanation is refuted (open gap +0.0000 ATR, rho -0.039) and **99.8% of PRICE's variance is the EXIT PATH** | attack the stop's LOCATION directly -> queue item 1 |
