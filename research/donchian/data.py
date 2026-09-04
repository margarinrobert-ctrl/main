"""Canonical datasets in New York time, with the research/holdout split.

Timezone established in tzcal.py / dstcheck.py: the CSV clock runs New York +7h
in BOTH seasons (cash-open volume spike sits at CSV 16:30 year-round), so
New York = CSV - 7h exactly. Verified independently by 15m return correlation
against the RTF file, whose stamps carry explicit -04:00 offsets.
"""
import numpy as np, pandas as pd
from pathlib import Path
import re

UP = Path("/root/.claude/uploads/ca69dfa7-5044-590d-a3ff-dff1242aefa8")
CACHE = Path("/home/user/main/data/donchian")
CACHE.mkdir(parents=True, exist_ok=True)
NY_OFFSET_H = 7          # CSV clock minus New York
SPLIT_FRAC = 0.65        # first 65% of SESSIONS is research; rest is locked

SOURCES = {
    "NAS":  UP / "65eb39e6-nasdaq_20252016_15m_data.csv",
    "US30": UP / "98dd8d93-us30_20162025_15m_data1.csv",
}
RTF = UP / "60d07ff1-us30_2_year_data.rtf"


def _finish(df):
    df = df.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    df["date"] = df.ts.dt.normalize()
    df["tod"] = df.ts.dt.hour * 60 + df.ts.dt.minute       # minutes past NY midnight
    df["dow"] = df.ts.dt.dayofweek
    # session id: contiguous index over unique dates
    u = {d: i for i, d in enumerate(sorted(df.date.unique()))}
    df["sess"] = df.date.map(u).astype(np.int32)
    return df


def load(sym):
    """15m bars, ts = New York wall clock (tz-naive, DST already folded in)."""
    f = CACHE / f"{sym}_15m_NY.parquet"
    if f.exists():
        return pd.read_parquet(f)
    df = pd.read_csv(SOURCES[sym], sep="\t")
    df["ts"] = (pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S")
                - pd.Timedelta(hours=NY_OFFSET_H))
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                            "Close": "close", "TickVolume": "tickvol"})
    df = _finish(df[["ts", "open", "high", "low", "close", "tickvol"]])
    df.to_parquet(f)
    return df


def load_rtf():
    """The independent-feed US30 file (different broker, explicit NY offsets)."""
    f = CACHE / "US30RTF_15m_NY.parquet"
    if f.exists():
        return pd.read_parquet(f)
    raw = RTF.read_text(errors="ignore")
    rows = re.findall(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}),"
                      r"([\d.]+),([\d.]+),([\d.]+),([\d.]+),(\d+)", raw)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "tickvol"])
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    df["tickvol"] = df["tickvol"].astype(int)
    df["ts"] = (pd.to_datetime(df["ts"], utc=True, format="ISO8601")
                .dt.tz_convert("America/New_York").dt.tz_localize(None))
    df = _finish(df)
    df.to_parquet(f)
    return df


def split_point(df):
    """Session index at which the locked block begins. Chronological, never
    price- or performance-based, and computed on sessions so a partial day
    cannot straddle the boundary."""
    n = df.sess.max() + 1
    return int(n * SPLIT_FRAC)


def blocks(df):
    k = split_point(df)
    return df.sess.values < k, df.sess.values >= k


if __name__ == "__main__":
    for sym in ["NAS", "US30"]:
        d = load(sym)
        k = split_point(d)
        r, h = blocks(d)
        print(f"\n{sym}: {len(d):,} bars  {d.ts.min()}  ->  {d.ts.max()}")
        print(f"  sessions {d.sess.max()+1:,}   split at session {k:,}")
        print(f"  RESEARCH {r.sum():>7,} bars  {d.ts[r].min().date()} -> {d.ts[r].max().date()}")
        print(f"  LOCKED   {h.sum():>7,} bars  {d.ts[h].min().date()} -> {d.ts[h].max().date()}")
        w = d[(d.tod >= 420) & (d.tod < 660)]
        print(f"  07:00-11:00 NY window: {len(w):,} bars over {w.sess.nunique():,} sessions"
              f"  ({len(w)/max(w.sess.nunique(),1):.1f} bars/session, 16 = full)")
    rt = load_rtf()
    print(f"\nUS30RTF (independent feed): {len(rt):,} bars  {rt.ts.min()} -> {rt.ts.max()}")
