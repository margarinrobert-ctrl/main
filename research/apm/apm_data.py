"""Ingest for the broker 15-minute exports, and the decision-bar builder they feed.

THE TIMEZONE IS MEASURED, NOT ASSUMED. The two MetaTrader exports carry a naive `DateTime` in an
unstated broker clock. Guessing it wrong shifts every session boundary in the strategy, so it was
pinned two independent ways and both agree on EET/EEST (`Europe/Athens`):

  1. The US30 export overlaps a separate, explicitly New York-stamped US30 file by 21,094 bars.
     Under Europe/Athens the 15-minute RETURN correlation between the two feeds is 0.9955 overall
     with no calendar month below 0.969. The fixed-offset alternatives UTC+2 and UTC+3 each break
     down at a DST transition (7 and 6 months below 0.9 respectively), which is what identifies the
     clock as DST-aware rather than fixed.
  2. Independently, under the same assumption the busiest 15-minute slot of the day in BOTH files
     is exactly 09:30 New York -- the cash open -- decaying monotonically through 09:45, 10:00 and
     10:15. That signature lands on the right minute only if the conversion is right.

WHAT THESE FILES ARE NOT. They are broker index CFD feeds, not CME futures:

  * `Volume` is identically zero; `TickVolume` is the only activity measure, so the strategy's
    volume-weighted VWAP is a TICK-weighted VWAP here. That is a real difference from the source.
  * Monday-Friday only. There is no Sunday 18:00 New York open, so the electronic-session roll at
    18:00 begins a session that, on a Friday, has no bars until Monday.
  * 15-minute bars, so the strategy's 10-minute decision bar cannot be reconstructed. Everything
    downstream runs on a 15-MINUTE decision bar. Every session boundary the source uses (09:30,
    11:00, 16:00, 18:00) is divisible by 15, so the source's own alignment validation passes -- but
    this is a timeframe transplant and not a reproduction of the 10-minute result.
"""
from __future__ import annotations

import io
import os
import re

import numpy as np
import pandas as pd

NY = "America/New_York"
BROKER_TZ = "Europe/Athens"      # EET/EEST, established above


def read_mt_export(path: str, tz: str = BROKER_TZ) -> pd.DataFrame:
    """A tab-separated MetaTrader export -> UTC-indexed OHLCV, volume taken from TickVolume."""
    df = pd.read_csv(path, sep="\t")
    df.columns = [c.strip() for c in df.columns]
    dt = pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S")
    ts = dt.dt.tz_localize(tz, ambiguous=True, nonexistent="shift_forward").dt.tz_convert("UTC")
    vol = df["TickVolume"] if (df["Volume"] == 0).all() else df["Volume"]
    out = pd.DataFrame(dict(timestamp=ts, open=df["Open"].astype(float),
                            high=df["High"].astype(float), low=df["Low"].astype(float),
                            close=df["Close"].astype(float), volume=vol.astype(float)))
    return out.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def read_rtf_export(path: str) -> pd.DataFrame:
    """The RTF wrapper around a `time,open,high,low,close,Volume` csv with explicit UTC offsets."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    body = raw[raw.index("time,open"):]
    lines = [re.sub(r"\\'[0-9a-f]{2}", "", l).strip() for l in body.split("\\par")]
    rows = [l for l in lines if re.match(r"^\d{4}-\d{2}-\d{2}T", l)]
    df = pd.read_csv(io.StringIO("timestamp,open,high,low,close,volume\n" + "\n".join(rows)))
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def write_canonical(df: pd.DataFrame, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    out = df.copy()
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out.to_csv(path, index=False)
    return path


def bars_from_csv(path: str, tf: int) -> dict:
    """Load a canonical UTC csv whose bar interval is already `tf` minutes, as decision bars.

    The source's completeness rule is applied at the level this data supports: a bucket is a bar,
    and the per-session bar count is checked by the simulator's own window tracker. Bars whose
    timestamp is not on a `tf`-minute UTC boundary are dropped and counted, because a decision bar
    that is not aligned is not the bar the strategy is defined on."""
    df = pd.read_csv(path)
    ts = pd.to_datetime(df["timestamp"], utc=True)
    ts_i = ts.to_numpy("datetime64[ns]").astype(np.int64)
    step = tf * 60_000_000_000
    ok = (ts_i % step) == 0
    ts_i = ts_i[ok]
    idx = pd.DatetimeIndex(pd.to_datetime(ts_i, utc=True)).tz_convert(NY)
    nxt = pd.DatetimeIndex(pd.to_datetime(ts_i + 86_400_000_000_000, utc=True)).tz_convert(NY)
    return dict(
        ts=ts_i,
        o=df["open"].to_numpy(float)[ok], h=df["high"].to_numpy(float)[ok],
        l=df["low"].to_numpy(float)[ok], c=df["close"].to_numpy(float)[ok],
        v=df["volume"].to_numpy(float)[ok],
        mod=(idx.hour * 60 + idx.minute).to_numpy(np.int64),
        ymd=(idx.year * 10000 + idx.month * 100 + idx.day).to_numpy(np.int64),
        ymd_next=(nxt.year * 10000 + nxt.month * 100 + nxt.day).to_numpy(np.int64),
        n=int(ok.sum()), dropped=int((~ok).sum()), n_partial=0)


# Provenance. The raw exports were supplied for this study and are not in the repository (bar
# files are git-ignored: data/README.md). md5 of the sources, so a re-supplied file can be checked
# to be the same one every number in docs/ib/STUDY_APM_VALIDATION.md was computed from:
#   3509e63590be2a6b85c6ede714638d42  nasdaq_20252016_15m_data.csv   206,703 bars
#   4e5dcd8ecab2d4531059b144ce007f55  us30_20162025_15m_data1.csv    193,942 bars
#   e21672416f4224b5333f46d1bfba5166  us30_2_year_data.rtf            48,937 bars (NY-stamped)
# and of the canonical files this module writes from them:
#   ad2f242824e3a90d835383dbafb394cd  data/NASDAQ_15m.csv
#   9d37dd4771465140eff5fe3a00dd9a51  data/US30_15m.csv
#   879e13271b7337011556a955b1c9ef55  data/US30_ref_15m.csv
UPLOADS = os.environ.get("APM_UPLOADS", "/root/.claude/uploads/205de83b-ac14-560d-a641-4b02a6c9d794")
SOURCES = {
    "NASDAQ_15m": (f"{UPLOADS}/d08cdaaf-nasdaq_20252016_15m_data.csv", "mt"),
    "US30_15m": (f"{UPLOADS}/c25aa4bf-us30_20162025_15m_data1.csv", "mt"),
    "US30_ref_15m": (f"{UPLOADS}/3692ea1e-us30_2_year_data.rtf", "rtf"),
}


def ingest_all(outdir: str = "data") -> dict:
    made = {}
    for name, (src, kind) in SOURCES.items():
        if not os.path.exists(src):
            continue
        df = read_mt_export(src) if kind == "mt" else read_rtf_export(src)
        made[name] = write_canonical(df, os.path.join(outdir, f"{name}.csv"))
    return made


if __name__ == "__main__":
    for name, path in ingest_all().items():
        d = pd.read_csv(path)
        print(f"{name:14s} -> {path}  {len(d):,} bars  {d.timestamp.iloc[0]} -> {d.timestamp.iloc[-1]}")
