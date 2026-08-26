"""Ingest, identify and audit the four uploaded bar files.

Four files arrived with no provenance beyond their names: a 2.9M-row tab-separated
`1m_data.csv` naming no instrument, a 1.4M-row semicolon-separated `XAU_5m_data.csv`, a Binance
kline export `btc_15m_data_2018_to_2025.csv`, and a CoinMarketCap daily BTC file.

Two facts have to be established from the bytes before any of it can be traded on paper, because
getting either wrong silently invalidates every session-gated result downstream:

  * **what the instrument is** -- a price series alone does not say. Identification here is by
    level and date: a series printing 18,200 in October 2016 and 44,160 in July 2025 is the Dow,
    not the Nasdaq (4,850 / 22,900) and not the S&P (2,140 / 6,260).

  * **what timezone the stamps are in** -- a broker MT4/MT5 export is stamped in *server* time,
    which is neither UTC nor exchange time and usually follows European DST, not American. The
    whole point of this study is a 07:00-11:00 New York session, so an hour of drift moves the
    window onto a different part of the day for half the year.

The timezone is not assumed. `identify_timezone` converts the naive stamps under each candidate
zone, finds the New-York minute-of-day at which each session's largest one-bar move lands, and
scores the candidate by how tightly that anchor concentrates. An index future's 09:30 cash open is
the sharpest recurring event in its day, so the right zone is the one that puts the modal anchor
there and keeps it there across DST boundaries; a wrong fixed offset smears the anchor across two
minutes-of-day, one per European summer.

Everything is written out as UTC-indexed parquet plus a precomputed New York minute-of-day, so no
downstream module ever re-derives a timezone.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

RAW = os.environ.get(
    "TURTLE_RAW",
    "/tmp/claude-0/-home-user-main/459cb878-1a2d-5b1e-ac51-ecb383975db9/scratchpad/data")
OUT = os.environ.get("TURTLE_OUT", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))

NY = "America/New_York"

# Candidate server timezones.  MT4/MT5 brokers cluster on EET/EEST (UTC+2/+3, European DST) and on
# fixed offsets; Binance is UTC by definition.  All are tried, none assumed.
CANDIDATES = [
    "UTC", "Etc/GMT-1", "Etc/GMT-2", "Etc/GMT-3", "Etc/GMT+4", "Etc/GMT+5",
    "Europe/Athens", "Europe/London", "America/New_York", "America/Chicago",
]


# --------------------------------------------------------------------------- readers

def read_1m(path: str | None = None) -> pd.DataFrame:
    """The tab-separated MT export.  Descending order, `Volume` is identically zero."""
    path = path or os.path.join(RAW, "1m_data.csv")
    df = pd.read_csv(path, sep="\t", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    ts = pd.to_datetime(df["datetime"], format="%Y.%m.%d %H:%M:%S")
    out = pd.DataFrame({
        "ts": ts,
        "open": df["open"].astype("float64"),
        "high": df["high"].astype("float64"),
        "low": df["low"].astype("float64"),
        "close": df["close"].astype("float64"),
        # `Volume` is 0 on every row of this export; TickVolume is the real activity proxy.
        "volume": df["tickvolume"].astype("float64"),
    })
    return out.sort_values("ts", kind="mergesort").reset_index(drop=True)


def read_xau(path: str | None = None) -> pd.DataFrame:
    path = path or os.path.join(RAW, "XAU_5m_data.csv")
    df = pd.read_csv(path, sep=";", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    ts = pd.to_datetime(df["date"], format="%Y.%m.%d %H:%M")
    out = pd.DataFrame({
        "ts": ts,
        "open": df["open"].astype("float64"),
        "high": df["high"].astype("float64"),
        "low": df["low"].astype("float64"),
        "close": df["close"].astype("float64"),
        "volume": df["volume"].astype("float64"),
    })
    return out.sort_values("ts", kind="mergesort").reset_index(drop=True)


def read_btc15(path: str | None = None) -> pd.DataFrame:
    path = path or os.path.join(RAW, "btc_15m_data_2018_to_2025.csv")
    df = pd.read_csv(path, dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    ts = pd.to_datetime(df["open time"].str.strip(), format="%Y-%m-%d %H:%M:%S.%f", errors="coerce")
    out = pd.DataFrame({
        "ts": ts,
        "open": pd.to_numeric(df["open"], errors="coerce"),
        "high": pd.to_numeric(df["high"], errors="coerce"),
        "low": pd.to_numeric(df["low"], errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
        "volume": pd.to_numeric(df["volume"], errors="coerce"),
    })
    # The final row of the export has no stamps at all -- drop it rather than guess.
    out = out.dropna(subset=["ts", "open", "high", "low", "close"])
    return out.sort_values("ts", kind="mergesort").reset_index(drop=True)


def read_btc_daily(path: str | None = None) -> pd.DataFrame:
    path = path or os.path.join(
        RAW, "Bitcoin_6_24_2026-8_25_2026_historical_data_coinmarketcap.csv")
    df = pd.read_csv(path, sep=";", dtype=str)
    df.columns = [c.strip().lower().lstrip("﻿") for c in df.columns]
    ts = pd.to_datetime(df["timeopen"].str.strip('"'), format="ISO8601", utc=True)
    out = pd.DataFrame({
        "ts": ts.dt.tz_localize(None),
        "open": df["open"].astype("float64"),
        "high": df["high"].astype("float64"),
        "low": df["low"].astype("float64"),
        "close": df["close"].astype("float64"),
        "volume": df["volume"].astype("float64"),
    })
    return out.sort_values("ts", kind="mergesort").reset_index(drop=True)


# --------------------------------------------------------------------------- identification

# (year, month) -> published index level, for the three US index futures a broker labels "1m_data".
# Levels are month-average closes; the test only needs to separate series that differ by 4x.
_INDEX_LEVELS = {
    "US30 (Dow Jones)":   {(2016, 10): 18_150, (2020, 3): 21_900, (2025, 7): 44_300},
    "US100 (Nasdaq 100)": {(2016, 10): 4_850, (2020, 3): 7_700, (2025, 7): 22_900},
    "US500 (S&P 500)":    {(2016, 10): 2_140, (2020, 3): 2_650, (2025, 7): 6_270},
    "DE40 (DAX)":         {(2016, 10): 10_650, (2020, 3): 9_900, (2025, 7): 24_200},
}


def identify_instrument(df: pd.DataFrame) -> list[tuple[str, float]]:
    """Rank candidate instruments by mean relative error against published index levels."""
    scored = []
    for name, anchors in _INDEX_LEVELS.items():
        errs = []
        for (y, m), level in anchors.items():
            sel = df[(df.ts.dt.year == y) & (df.ts.dt.month == m)]
            if len(sel) < 100:
                continue
            errs.append(abs(sel.close.mean() - level) / level)
        if errs:
            scored.append((name, float(np.mean(errs))))
    return sorted(scored, key=lambda t: t[1])


@dataclass
class TzScore:
    tz: str
    anchor_min: int          # modal New York minute-of-day of the daily largest move
    concentration: float     # share of sessions whose anchor lands in the modal minute +/- 2
    n_sessions: int

    def __str__(self) -> str:
        h, m = divmod(self.anchor_min, 60)
        return f"{self.tz:<20} anchor {h:02d}:{m:02d} NY   concentration {self.concentration:.3f}"


def identify_timezone(df: pd.DataFrame, candidates=CANDIDATES, tol: int = 2) -> list[TzScore]:
    """Score candidate source timezones by how tightly the daily volatility anchor concentrates.

    The largest one-bar move of a US index session lands on the 09:30 cash open far more often than
    on any other minute.  Reading the stamps under the *correct* zone therefore piles those anchors
    onto one minute-of-day; reading them under a zone whose DST rule is wrong splits the pile in
    two, one heap per summer, and the concentration drops.  The winner is the sharpest heap, and
    the heap's location is a second, independent check that it is really the cash open.
    """
    rng = (df.high - df.low).to_numpy()
    ret = np.abs(np.log(df.close.to_numpy() / np.maximum(df.open.to_numpy(), 1e-9)))
    move = np.where(np.isfinite(ret) & (ret > 0), ret, rng / np.maximum(df.close.to_numpy(), 1e-9))

    out = []
    for tz in candidates:
        try:
            ny = df.ts.dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT").dt.tz_convert(NY)
        except Exception:
            continue
        ok = ny.notna().to_numpy()
        if ok.sum() < 1000:
            continue
        nyv = ny[ok]
        mod = (nyv.dt.hour * 60 + nyv.dt.minute).to_numpy()
        # Session = New York calendar day shifted so an evening open belongs to the next day.
        day = (nyv - pd.Timedelta(hours=18)).dt.floor("D").astype("int64").to_numpy()
        mv = move[ok]

        order = np.lexsort((-mv, day))
        d_sorted = day[order]
        first = np.ones(len(d_sorted), dtype=bool)
        first[1:] = d_sorted[1:] != d_sorted[:-1]
        anchors = mod[order][first]
        if len(anchors) < 50:
            continue
        counts = np.bincount(anchors, minlength=1440)
        # Concentration in a +/-tol window, maximised over its centre.
        k = 2 * tol + 1
        window = np.convolve(counts, np.ones(k), mode="same")
        centre = int(window.argmax())
        out.append(TzScore(tz, centre, float(window[centre] / len(anchors)), len(anchors)))
    return sorted(out, key=lambda s: -s.concentration)


# --------------------------------------------------------------------------- audit

def audit(df: pd.DataFrame, name: str, expect_minutes: int) -> dict:
    ts = df.ts.to_numpy()
    d = np.diff(ts).astype("timedelta64[m]").astype(np.int64)
    step = expect_minutes
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    bad_ohlc = int(((h < np.maximum(o, c)) | (l > np.minimum(o, c)) | (h < l)).sum())

    # A gap is "structural" if it recurs at a fixed New York minute-of-day (weekend, daily break).
    gaps = d > step
    gap_at = pd.Series(ts[:-1][gaps]).dt.hour * 60 + pd.Series(ts[:-1][gaps]).dt.minute
    modal = gap_at.value_counts().head(3).to_dict() if gaps.any() else {}

    ret = np.diff(np.log(np.maximum(c, 1e-9)))
    mad = np.median(np.abs(ret - np.median(ret))) * 1.4826
    spikes = int((np.abs(ret - np.median(ret)) > 25 * mad).sum()) if mad > 0 else -1

    return {
        "name": name, "rows": len(df),
        "start": str(df.ts.iloc[0]), "end": str(df.ts.iloc[-1]),
        "dupes": int(df.ts.duplicated().sum()),
        "monotonic": bool(df.ts.is_monotonic_increasing),
        "bad_ohlc": bad_ohlc,
        "nonpositive": int((df[["open", "high", "low", "close"]] <= 0).to_numpy().sum()),
        "gaps": int(gaps.sum()),
        "gap_modal_minutes": modal,
        "spikes_25mad": spikes,
        "median_step_min": float(np.median(d)) if len(d) else float("nan"),
    }


# --------------------------------------------------------------------------- write

def canonicalise(df: pd.DataFrame, src_tz: str) -> pd.DataFrame:
    """Naive source stamps -> UTC index + New York minute-of-day and session date."""
    utc = df.ts.dt.tz_localize(src_tz, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    keep = utc.notna().to_numpy()
    df = df.loc[keep].copy()
    utc = utc[keep]
    ny = utc.dt.tz_convert(NY)
    df["ts"] = utc.dt.tz_localize(None)
    df["ny_min"] = (ny.dt.hour * 60 + ny.dt.minute).to_numpy().astype(np.int32)
    df["ny_date"] = ny.dt.strftime("%Y-%m-%d").to_numpy()
    df["ny_dow"] = ny.dt.dayofweek.to_numpy().astype(np.int8)
    return df.drop_duplicates(subset="ts", keep="first").reset_index(drop=True)


def verify_dst(df: pd.DataFrame, tz: str, anchor: int, tol: int = 3) -> pd.DataFrame:
    """Separate the weeks where European and American DST disagree, and re-check the anchor.

    `identify_timezone` can only say which candidate is sharpest overall.  It cannot distinguish
    "EET, European DST" from "GMT+2/+3 following *American* DST", because the two agree for ~48
    weeks a year.  They disagree in the roughly three weeks between the US spring-forward and the
    EU one, and the one week between the EU fall-back and the US one -- about 4 weeks of the year,
    5% of the sample.  If the zone is right the anchor stays put in those weeks; if it is wrong the
    anchor moves exactly one hour, and only there.
    """
    ny = df.ts.dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT").dt.tz_convert(NY)
    ok = ny.notna().to_numpy()
    nyv, sub = ny[ok], df.loc[ok]
    # US offset in force vs the EU offset the candidate zone applies, per row.
    us_off = nyv.dt.strftime("%z").to_numpy()
    src_off = sub.ts.dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT").dt.strftime("%z").to_numpy()
    us_dst = us_off == "-0400"
    eu_dst = np.isin(src_off, ("+0300", "+0100", "+0200")) & (src_off != "+0200") if tz == "Europe/Athens" \
        else np.zeros(len(src_off), bool)
    if tz == "Europe/Athens":
        eu_dst = src_off == "+0300"
    elif tz == "Europe/London":
        eu_dst = src_off == "+0100"
    mismatch = us_dst != eu_dst

    rng = (sub.high - sub.low).to_numpy() / np.maximum(sub.close.to_numpy(), 1e-9)
    mod = (nyv.dt.hour * 60 + nyv.dt.minute).to_numpy()
    day = (nyv - pd.Timedelta(hours=18)).dt.floor("D").astype("int64").to_numpy()

    rows = []
    for label, sel in (("DST agree", ~mismatch), ("DST disagree", mismatch)):
        if sel.sum() < 500:
            rows.append({"weeks": label, "sessions": 0, "at_anchor": float("nan"),
                         "at_anchor_plus_1h": float("nan")})
            continue
        d, m, r = day[sel], mod[sel], rng[sel]
        order = np.lexsort((-r, d))
        ds = d[order]
        first = np.ones(len(ds), bool)
        first[1:] = ds[1:] != ds[:-1]
        a = m[order][first]
        rows.append({
            "weeks": label, "sessions": int(first.sum()),
            "at_anchor": float(np.mean(np.abs(a - anchor) <= tol)),
            "at_anchor_plus_1h": float(np.mean(np.abs(a - (anchor + 60)) <= tol)),
            "at_anchor_minus_1h": float(np.mean(np.abs(a - (anchor - 60)) <= tol)),
        })
    return pd.DataFrame(rows)


def yearly_density(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(df.ts.dt.year)
    return pd.DataFrame({
        "bars": g.size(),
        "median_vol": g.volume.median(),
        "zero_vol_share": g.volume.apply(lambda s: float((s <= 0).mean())),
        "median_range_bp": g.apply(
            lambda d: float(np.median((d.high - d.low) / d.close) * 1e4), include_groups=False),
    })


def build(name: str, df: pd.DataFrame, src_tz: str, step: int) -> pd.DataFrame:
    out = canonicalise(df, src_tz)
    path = os.path.join(OUT, f"{name}.parquet")
    out.to_parquet(path, index=False)
    print(f"  wrote {path}  {len(out):,} bars  {out.ts.iloc[0]} -> {out.ts.iloc[-1]} UTC")
    return out


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    report: list[str] = []

    print("=" * 78, "\n1m_data.csv -- identification\n", "=" * 78)
    m1 = read_1m()
    for nm, err in identify_instrument(m1):
        print(f"  {nm:<22} mean |level error| {err:7.2%}")
    print()
    for s in identify_timezone(m1)[:6]:
        print("  ", s)

    print("\n" + "=" * 78, "\nXAU_5m_data.csv -- timezone\n", "=" * 78)
    xau = read_xau()
    for s in identify_timezone(xau)[:6]:
        print("  ", s)

    print("\n" + "=" * 78, "\nbtc_15m -- timezone (expect UTC, Binance klines)\n", "=" * 78)
    btc = read_btc15()
    for s in identify_timezone(btc)[:6]:
        print("  ", s)

    print("\n" + "=" * 78, "\nDST rule check -- does the anchor move in the mismatch weeks?\n", "=" * 78)
    print("US30 @ Europe/Athens, anchor 09:30 NY")
    print(verify_dst(m1, "Europe/Athens", 9 * 60 + 30).to_string(index=False))
    print("\nXAU @ Europe/Athens, anchor 08:30 NY")
    print(verify_dst(xau, "Europe/Athens", 8 * 60 + 30).to_string(index=False))

    print("\n" + "=" * 78, "\nAudit\n", "=" * 78)
    for df, nm, step in ((m1, "1m_data", 1), (xau, "XAU_5m", 5), (btc, "BTC_15m", 15)):
        print("\n", audit(df, nm, step))
        report.append(nm)

    print("\n" + "=" * 78, "\nYearly density -- XAU (the file starts in 2004)\n", "=" * 78)
    print(yearly_density(xau).to_string())

    print("\n" + "=" * 78, "\nCanonical UTC parquet\n", "=" * 78)
    build("US30_1m", m1, "Europe/Athens", 1)
    build("XAU_5m", xau, "Europe/Athens", 5)
    build("BTC_15m", btc, "UTC", 15)
    bd = read_btc_daily()
    bd.to_parquet(os.path.join(OUT, "BTC_daily_cmc.parquet"), index=False)
    print(f"  wrote BTC_daily_cmc.parquet  {len(bd)} rows  {bd.ts.iloc[0]} -> {bd.ts.iloc[-1]}")


if __name__ == "__main__":
    main()
