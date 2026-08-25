# All nine shipped legs on BTC — and the first instrument whose cost is *known*

`research/edgelab/crypto.py`, `research/btc_legs.py`, `research/run_btc_legs.py`.

## The feed

Binance BTCUSDT klines, 15-minute, **295,882 bars, 2017-12-31 → 2026-06-15** New York. A **sixth
distinct export format** and the first raw exchange dump here. Note the file *name* says 2018–2025;
the data runs eighteen months further.

Quality is high — 0 OHLC violations, 0 non-positive prices, 0.005% zero-range — with three defects
found and handled rather than assumed: **the final row is malformed** (both timestamps empty, OHLCV
present), 2 timestamps are duplicated, and 14 bars carry zero volume, zero trades and zero range
together, which is an exchange outage rather than a quiet market.

Because the source is 15-minute, **all nine legs are testable** — the three 15m rules natively and
the six 30m rules on a resample. EURUSD could only test six.

## The clock: the first feed here where a constant shift is wrong

Every other file on this branch is a broker export whose server follows US daylight saving, which is
why a fixed −7h was right year round for US100, US30, XAUUSD and EURUSD. `derive_offset` was built
to *refuse* a constant shift when the seasons disagree. This is the first feed to trip that guard,
correctly. Measured against US30, whose own clock is independently verified:

| shift | winter (DJF) | summer (JJA) |
| ---: | ---: | ---: |
| −3h | +0.0142 | −0.0021 |
| **−4h** | +0.0176 | **+0.1625** |
| **−5h** | **+0.1289** | +0.0073 |
| −6h | +0.0059 | +0.0042 |

They disagree by exactly one hour — the daylight-saving signature. A true **UTC → America/New_York
conversion** scores each season's own best and **+0.1337 pooled**, against +0.0908 for the best
single constant shift. The loader converts; the autumn fall-back hour's duplicate local timestamps
are dropped.

Two independent checks agree: mean |return| and trade count both peak at raw hour 14, and
13:00–16:00 UTC brackets the US equity open.

## Two structural facts that cut against the rules before a single trade is simulated

**It is 24/7.** Weekday bar counts run 42,184 to 42,370 — flat. Six of the nine legs carry a clock
condition and all nine carry a flatten time, written against a market that closes. On BTC they
select an arbitrary slice of a continuous tape.

**It carries real taker-side flow.** `Taker buy base asset volume / Volume` is an *actual* order-flow
imbalance rather than the proxy `features3.py` had to construct — the BTC analogue of EURUSD's
spread column. It centres at 0.4965 mean / 0.4967 median, so any signal lives in its deviations, not
its level. Unused here; noted as available.

## The result

Binance spot taker fee **0.10% per side**, plus 1bp assumed half-spread — round turn **0.202%**.
Scored in R against a minute-of-day matched control, BH at q=0.10 across all nine.

| leg | tf | side | stop | n | win | E[R] | control | excess | p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| V1 | 30 | long | 3.0 | 345 | 46.38% | −0.0664 | −0.1524 | +0.0861 | 0.010 |
| M1 | 30 | long | 1.0 | 188 | 37.77% | −0.3269 | −0.4899 | +0.1630 | 0.000 |
| V4 | 15 | short | 3.0 | 216 | 38.43% | −0.1303 | −0.2462 | +0.1159 | 0.020 |
| M2 | 30 | short | 1.0 | 359 | 40.95% | −0.3911 | −0.4553 | +0.0641 | 0.117 |
| M4 | 30 | long | 4.0 | 39 | 58.97% | −0.0380 | −0.1145 | +0.0766 | 0.233 |
| V3 | 15 | long | 4.0 | 417 | 39.57% | −0.1479 | −0.1465 | −0.0014 | 0.493 |
| V2 | 30 | short | 1.0 | 543 | 37.20% | −0.4593 | −0.4554 | −0.0038 | 0.513 |
| V2L | 30 | long | 2.5 | 475 | 40.84% | −0.1840 | −0.1768 | −0.0072 | 0.590 |
| M3 | 15 | short | 2.0 | 621 | 40.42% | −0.3273 | −0.3077 | −0.0196 | 0.693 |

Three pass BH — **and every single leg is negative in absolute terms.** The "excess" is a comparison
between two losing propositions.

## Read the zero-cost variant, and read it the other way round

| | with fees | at zero cost |
| --- | --- | --- |
| passing BH at 0.10 | V1, M1, V4 | **none** |

This branch runs the zero-cost variant to check whether a failure is a cost problem. Here the
*opposite* happened: the legs look **more** significant with costs than without, which is a warning
sign, not a result. The mechanism is the one `CLAUDE.md` already documents — a minute-of-day matched
control is **not volatility-matched**, and a fixed percentage cost is a smaller fraction of a wider
barrier. Measured directly:

| leg | ATR/price at trigger | at the control's bars | ratio | cost in R | control's cost in R |
| --- | ---: | ---: | ---: | ---: | ---: |
| **V1** | 0.00650 | 0.00643 | **1.01** | 0.1129 | 0.1140 |
| M1 | 0.00773 | 0.00643 | **1.20** | 0.2845 | 0.3424 |
| V4 | 0.00640 | 0.00448 | **1.43** | 0.1146 | 0.1635 |
| M4 | 0.01157 | 0.00670 | **1.73** | 0.0475 | 0.0820 |

**M1's and V4's passes are largely cost artifacts.** M1's control pays 0.058 R more in fees against
a +0.163 excess; V4's pays 0.049 R more against +0.116. Both evaporate at zero cost (p 0.205 and
0.305). **V1 is the exception**: ratio 1.01, cost differential 0.001 R — its excess is not a
volatility artifact, and it is the only leg still positive at zero cost (+0.0530 E[R], +0.0654
excess, p 0.020).

## The verdict

**BTC does not confirm any of the nine.** V1 is again the best-behaved — the only leg positive at
zero cost, the only one whose excess survives the volatility diagnostic — but at nine tests BH needs
p ≤ 0.011 and V1's zero-cost p is 0.020. Consistent with V1, not a confirmation of it. Its three
confirmations remain NQ, US100 and EURUSD.

**What BTC does settle is the cost question, and it settles it for real.** Five studies here end at
"bid/ask is unavailable, so every cost number is an assumption, and every candidate dies at 1.5× the
assumption." **BTC's cost is not an assumption.** Binance's 0.10%/side taker fee is published and
exact; only the 1bp spread is assumed, and it is 5% of the total. So this is the first instrument
where the error bar does not swallow the answer — and the answer is that the cost kills the
geometry:

| leg's stop | cost in R | break-even at 1:1 | actual win rate |
| --- | ---: | ---: | ---: |
| 1.0×ATR (M1, M2, V2) | 0.28–0.33 | **64.2–66.5%** | 37.2–41.0% |
| 2.0–2.5×ATR (M3, V2L) | 0.11–0.23 | 55.7–61.4% | 40.4–40.8% |
| 3.0–4.0×ATR (V1, V3, V4, M4) | 0.05–0.12 | **52.4–56.0%** | 39.6–59.0% |

Only M4 clears its own break-even, on 39 trades. The pattern is the same one this branch has now
seen five times: **whatever survives sits at the wide-stop end**, and a 1×ATR barrier on a 0.2%
round turn is arithmetically dead before any signal is applied.
