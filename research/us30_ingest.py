"""Ingest the US30 15-minute export (an RTF wrapping a CSV) into the canonical bar format.

The source is a Rich Text file whose body is `time,open,high,low,close,Volume` rows stamped in New
York wall clock WITH the UTC offset (`2024-08-19T09:30:00-04:00`), one header line per export chunk
(ten of them, pasted together). This strips the RTF control words, drops the repeated headers,
de-duplicates, sorts, and writes `data/US30_15m.csv` as `timestamp,open,high,low,close,volume` in
UTC ISO-8601 -- the format every study here reads.

    python3 research/us30_ingest.py --in <export.rtf> --out data/US30_15m.csv

Data files are git-ignored (see data/README.md); the study header records this command.
"""
from __future__ import annotations

import argparse
import re

import pandas as pd

ROW = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2},")


def parse_rtf(path: str) -> pd.DataFrame:
    src = open(path, encoding="latin-1").read()
    rows = []
    for chunk in src.split("\\par"):
        line = chunk.replace("\r", "").replace("\n", "")
        line = re.sub(r"\\[a-z]+-?\d*\s?", "", line)          # RTF control words
        line = line.replace("{", "").replace("}", "").strip()
        if ROW.match(line):
            rows.append(line.split(","))
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["timestamp"] = pd.to_datetime(df["time"], utc=True)
    df = (df.dropna(subset=["open", "high", "low", "close"])
            .drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True))
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def audit(df: pd.DataFrame) -> None:
    bad = int(((df.high < df[["open", "close"]].max(axis=1)) |
               (df.low > df[["open", "close"]].min(axis=1))).sum())
    gap = df.timestamp.diff().dt.total_seconds().div(60)
    ny = df.timestamp.dt.tz_convert("America/New_York")
    print(f"  bars {len(df):,}   {ny.min()} -> {ny.max()}")
    print(f"  impossible OHLC rows: {bad}")
    print(f"  bar spacing: {gap.value_counts().head(4).to_dict()}")
    starts = ny.shift(1)[gap > 60].dt.strftime("%a %H:%M").value_counts().head(6).to_dict()
    print(f"  gaps > 60 min begin after (NY): {starts}  -- 16:45 is the daily 17:00 break")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="out", default="data/US30_15m.csv")
    a = ap.parse_args()
    d = parse_rtf(a.src)
    audit(d)
    d = d.assign(timestamp=d.timestamp.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    d.to_csv(a.out, index=False)
    print(f"  wrote {a.out}")
