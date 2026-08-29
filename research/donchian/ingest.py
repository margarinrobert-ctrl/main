"""Data validation + timezone calibration for the Donchian study.

The two CSVs carry naked timestamps with no timezone. The RTF carries explicit
-04:00/-05:00 New York offsets. Matching them on price identifies the CSV zone.
"""
import re, sys, numpy as np, pandas as pd
from pathlib import Path

UP = Path("/root/.claude/uploads/ca69dfa7-5044-590d-a3ff-dff1242aefa8")
NAS = UP / "65eb39e6-nasdaq_20252016_15m_data.csv"
US30 = UP / "98dd8d93-us30_20162025_15m_data1.csv"
RTF = UP / "60d07ff1-us30_2_year_data.rtf"
OUT = Path("/home/user/main/data/donchian")


def read_csv(p):
    df = pd.read_csv(p, sep="\t")
    df["DateTime"] = pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S")
    df = df.sort_values("DateTime").reset_index(drop=True)
    df = df.rename(columns={c: c.lower() for c in df.columns})
    return df.rename(columns={"datetime": "ts", "tickvolume": "tickvol"})


def read_rtf(p):
    raw = p.read_text(errors="ignore")
    rows = re.findall(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}),"
        r"([\d.]+),([\d.]+),([\d.]+),([\d.]+),(\d+)", raw)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    df["volume"] = df["volume"].astype(int)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, format="ISO8601")
    return df.sort_values("ts").reset_index(drop=True)


def audit(df, name):
    print(f"\n{'='*70}\n{name}: {len(df):,} bars  {df.ts.min()} -> {df.ts.max()}")
    d = df.ts.diff().dropna()
    print(f"  dup stamps      : {df.ts.duplicated().sum()}")
    print(f"  non-monotonic   : {(d <= pd.Timedelta(0)).sum()}")
    bad = ((df.high < df.low) | (df.high < df.open) | (df.high < df.close)
           | (df.low > df.open) | (df.low > df.close)).sum()
    print(f"  impossible OHLC : {bad}")
    print(f"  zero/neg price  : {(df[['open','high','low','close']] <= 0).sum().sum()}")
    print(f"  modal gap       : {d.mode().iloc[0]}")
    vc = d.value_counts().head(6)
    print("  gap histogram   :")
    for k, v in vc.items():
        print(f"      {str(k):>20}  {v:>8,}")
    big = d[d > pd.Timedelta(minutes=15)]
    print(f"  gaps > 15m      : {len(big):,}  (max {big.max() if len(big) else 'n/a'})")
    return df


def calibrate(csv, rtf, name):
    """Find the fixed offset that aligns CSV stamps to the RTF's UTC timeline."""
    print(f"\n{'='*70}\nTIMEZONE CALIBRATION: {name} CSV vs RTF (-04:00 tagged)")
    r = rtf.set_index("ts")
    lo, hi = rtf.ts.min(), rtf.ts.max()
    best = []
    for off in range(-12, 15):
        cs = csv.copy()
        cs["utc"] = cs.ts.dt.tz_localize("UTC") - pd.Timedelta(hours=off)
        m = cs[(cs.utc >= lo) & (cs.utc <= hi)].set_index("utc")
        j = m.join(r, how="inner", rsuffix="_r")
        if len(j) < 500:
            continue
        # price agreement: median absolute close difference
        mad = float(np.median(np.abs(j.close - j.close_r)))
        agree = float((np.abs(j.close - j.close_r) < 1.0).mean())
        best.append((off, len(j), mad, agree))
    best.sort(key=lambda x: x[2])
    print(f"  {'UTC offset':>11} {'matched':>9} {'median|dClose|':>15} {'frac<1.0':>9}")
    for off, n, mad, ag in best[:6]:
        print(f"  {off:>+11d} {n:>9,} {mad:>15.3f} {ag:>9.3f}")
    return best[0][0]


if __name__ == "__main__":
    rtf = read_rtf(RTF)
    audit(rtf.assign(ts=rtf.ts), "US30 RTF (New York tagged)")
    print(f"  RTF NY hours present: {sorted(rtf.ts.dt.tz_convert('America/New_York').dt.hour.unique())}")

    us = read_csv(US30); audit(us, "US30 CSV (naked stamps)")
    na = read_csv(NAS);  audit(na, "NASDAQ CSV (naked stamps)")
    print(f"\n  US30 CSV hours present : {sorted(us.ts.dt.hour.unique())}")
    print(f"  NAS  CSV hours present : {sorted(na.ts.dt.hour.unique())}")

    off = calibrate(us, rtf, "US30")
    print(f"\n  ==> US30 CSV stamps are UTC{off:+d}")
