# Market data

**Do not delete these files.** They are the historical data supplied for this
project, committed here because the working container is wiped between
sessions and anything not in git is gone. They are stored gzipped; the importer
reads `.csv.gz` directly, so nothing has to be unpacked by hand.

| File | Instrument | Timeframe | Bars | Range |
|---|---|---|---|---|
| `US30_5m.csv.gz` | US30 (Dow Jones index CFD) | 5 minutes | 581,195 | 2016-10-27 → 2025-07-15 |
| `US30_15m.csv.gz` | US30 (Dow Jones index CFD) | 15 minutes | 193,942 | 2016-10-27 → 2025-07-15 |
| `US30_30m.csv.gz` | US30 (Dow Jones index CFD) | 30 minutes | 11,445 | 2024-07-22 → 2025-07-15 |
| `BTCUSD_1d.csv.gz` | Bitcoin | 1 day | 397 | 2025-07-23 → 2026-08-24 |

## What is in them

The three US30 files are MetaTrader 5 exports: tab-separated, newest row first,
`DateTime Open High Low Close Volume TickVolume` with timestamps written
`%Y.%m.%d %H:%M:%S`. **`Volume` is zero on every row and the real figure is in
`TickVolume`** — the importer detects that and uses `TickVolume`, because
importing the zeros would silently flatten every volume-based indicator.

The instrument was identified from its own price history rather than from the
file name, which does not state it: 18,200 in October 2016, 24,811 in January
2018, 28,848 in January 2020 and 44,145 in July 2025 are the Dow Jones
Industrial Average to within a few points at every one of those dates.

`BTCUSD_1d.csv.gz` is a CoinMarketCap export: semicolon-separated, quoted, with
a UTF-8 BOM, newest row first, and five different time columns. The bar is
stamped from `timeOpen`; the generic `timestamp` column holds the *close* of
each day, and using it would shift every bar forward by 24 hours.

## Timezone

The MetaTrader timestamps carry no offset. They are read as the source
timezone chosen at import; the exporting broker's server time is usually
UTC+2/+3 (EET). Set that on import if the session times matter to your
strategy — it moves every bar, so it changes any rule with a time window in it.

## Volume

`TickVolume` counts price changes, not contracts. It is a fair proxy for
activity on a CFD, where true traded volume is not published, but it is not
comparable to exchange volume on a futures contract.
