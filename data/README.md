# Research data

Bar files live here and are **git-ignored** — they are large, frequently licensed, and always
reproducible from the ingest command recorded in each study's header.

## Canonical format

`timestamp,open,high,low,close,volume`, one row per bar, timestamps in **UTC ISO-8601**, sorted
ascending. Produced by the ingest script rather than written by hand:

```bash
# Source stamped in US Eastern wall clock (the usual case for CME data)
npx tsx scripts/quant-ingest.ts --in raw_1min.csv --out data/NQ_5m.csv --tf 5 --tz America/New_York

# Source already in UTC
npx tsx scripts/quant-ingest.ts --in raw_1min.csv --out data/XAUUSD_5m.csv --tf 5 --tz UTC
```

The script reads the source timestamps as **exchange wall clock** and converts to true UTC, so a file
stamped in Eastern time survives both daylight-saving transitions. Resampling buckets are anchored to
*local* midnight, so a 5-minute bar lines up with the 09:30 session open instead of straddling it. It
reports any row landing in a non-existent (spring-forward) or ambiguous (fall-back) local hour.

The source column order is free and headers are matched loosely, so `timestamp ET,open,high,low,
close,volume,Vwap_RTH,Vwap_ETH` works as-is; extra columns are ignored.

## Then run a study

```bash
npx tsx scripts/quant-research.ts --data data/NQ_5m.csv --symbol NQ --out docs/STUDY_NQ.md
```

`--symbol` selects the contract spec and cost model from `src/lib/quant/instruments.ts`
(`NQ`, `ES`, `CL`, `MCL`, `GC`, `MGC`, `XAUUSD`). Optional: `--holdout 0.3`, `--combos 400`,
`--seed 20250822`.

See [`docs/RESEARCH_PROTOCOL.md`](../docs/RESEARCH_PROTOCOL.md) for what each stage tests and how to
read the result.
