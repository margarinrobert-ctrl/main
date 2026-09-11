# A second instrument, six unseen years, and a problem with our own prices

Every study on this branch ends with the same caveat — *one instrument in one regime, no second
market was reachable*. A US100 15-minute file (2016-11 → 2025-10, 206,703 bars) removes it. This
is the data audit, the cross-asset test, and the strongest out-of-sample result this repository
has produced. `research/us100.py`.

## 1. The data is clean

| check | result |
| --- | --- |
| bars | 206,703, 2016-11-14 → 2025-10-01 |
| duplicate timestamps | **0** |
| OHLC violations | **0** |
| non-positive prices | **0** |
| zero-range bars | 181 (0.09%) |
| non-15m gaps | 2,904 (1.40%), 650 over two hours — weekends and holidays |
| `Volume` | identically zero (MT-style export); `TickVolume` is the only activity proxy |

**Timezone: New York + 7, and stable across DST.** Locating the RTH-open volume jump separately
in Dec–Feb and Jun–Aug puts it at **16:30 file time in both**, so the broker follows US daylight
saving and a fixed −7h shift is correct year-round. Had it followed EU DST or none at all, every
clock condition would have been an hour wrong for part of each year.

## 2. NQ does not lead US100

`corr(NQ return at t−k, US100 return at t)` on 64,884 overlapping 15-minute bars:

| lag k | −3 | −2 | −1 | **0** | +1 | +2 | +3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| corr | 0.010 | −0.015 | 0.044 | **0.8815** | −0.022 | −0.006 | 0.018 |

A clean spike at zero with nothing beside it. **At 15-minute resolution the information transfer
is already complete inside the bar**, so the lead-lag, momentum-transfer and confirmation-lag
family in the brief has no signal to find at this sampling rate. Contemporaneous correlation is
0.8815 overall, 0.922 in RTH, 0.950 overnight.

## 3. A finding about *our* prices, not this file

On 2023-01-10 the stored NQ series reads **13,915.8**; this feed reads **11,184.6**; the actual
Nasdaq-100 closed near **11,100**. The raw `data/NQ_1m.csv` itself opens at 13,788.5 on
2022-12-26, when the index was near 11,000 — so this is in the source data, not introduced here.

The ratio between the two series declines smoothly:

| year | mean NQ − US100 | ratio |
| --- | ---: | ---: |
| 2022 | 2,748 | 1.253 |
| 2023 | 2,466 | 1.177 |
| 2024 | 1,639 | 1.087 |
| 2025 | 775 | 1.036 |

Median daily drift 2.0 points, with **one** daily jump above 50 points in three years — so it is
**not roll-gap back-adjustment**, which would be a step function at quarterly rolls.

Whatever produced it, the operational conclusion is the same:

> **The stored NQ series' historical price LEVELS are synthetic. Its RETURNS are usable; its
> levels are not.**

This bites anything scaling with price — the `Percent of price` stop option, ATR-over-price
ratios — and it bites dollar magnitudes, because a 1% move maps to more points early in the sample
than late. The research block is the **earlier** 65%, so its dollar figures are inflated relative
to the locked block's. Corrected, that would make the **grew on locked** flag five shipped legs
carry *larger*, not smaller. Win rates, R-multiples and anything measured in ATR units are
unaffected, which is most of what this branch reports.

## 4. The real out-of-sample test

Everything on this branch was selected on NQ from 2022-12-26 onward. **US100 before that date is
71,074 30-minute bars of a different instrument across six years nothing here has ever seen** —
including the 2018 selloff, the COVID crash and the 2022 bear market, none of which the NQ sample
contains. Same rules, same geometry, nothing refitted:

| leg | what it is | **unseen 2016–2022 excess** | overlap excess | n | **p** | FDR 0.10 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| **V1** | mean reversion — failed breakdown | **+9.2** | +8.4 | 419 | **0.0001** | **PASS** |
| **V2L** | counter-trend — buys in a downtrend | **+8.5** | +7.8 | 243 | **0.0050** | **PASS** |
| RW | momentum | +4.1 | +10.5 | 221 | 0.1261 | fail |
| M4 | day filter | +4.3 | +16.7 | 140 | 0.1732 | fail |
| M1 | reversal bar | +1.2 | +8.2 | 150 | 0.4152 | fail |

Excess is win rate minus that geometry's own base rate on US100, which is the comparison that
survives a change of contract; dollars do not, since US100 is not MNQ.

**Two of five survive a change of instrument and a change of era.** And they are exactly the two
**counter-trend / mean-reversion** legs — the ones whose excess is essentially *unchanged* across
the switch (+8.4 → +9.2, +7.8 → +8.5), while the three that decay hardest are the momentum, day
filter and reversal legs, M4 falling from +16.7 to +4.3 and M1 from +8.2 to +1.2.

That is coherent with everything else on this branch: **trend and momentum structures do not
persist here; mean reversion does.**

## 5. What was not done

The brief asks for a continuously-running autonomous research platform — hypothesis engine,
research database, Bayesian parameter search, regime clustering, PBO analysis. This study builds
the **data foundation** for that (audit, timezone, alignment, unseen split) and spends the
remaining effort on the single highest-value test the new data enables, rather than starting a
platform and validating nothing. The existing machinery — `tuner.py`, `alpha_factory2.py`,
`feature_eval.py`, `oner_anom.py`, `phase2.py` — already covers parameter search, feature
evaluation, matched controls, Monte Carlo and walk-forward; what it lacked was a second
instrument, which it now has via `us100.to_bars(tf)`.

The honest next step is not more searching. It is re-running the existing validated legs and the
existing condition pools against `us100.unseen_split()`, because a branch that has spent this long
worrying about overfitting now has, for the first time, a genuine hold-out to worry with.
