"""Dukascopy tick ingest, spread measurement, and a cross-check against an existing feed.

WHY TICKS. The cost model everywhere else in this repository is a CONSTANT: one tick of slippage
plus commission, $2.44 round turn on MNQ. That is fine for a strategy holding 5.8 hours with a 16x
cost cushion (STUDY_APM_VALIDATION section 4). It is not fine for the scalps: SAM's edge is a
fraction of a tick against a 6-tick round turn, and STUDY_LIMIT_ENTRY found the ENTRY MECHANIC to
be the largest lever on the branch. Both of those are decided by the spread at the minute the order
goes in, and nothing here has ever measured that spread -- it has been assumed.

Dukascopy publishes BID AND ASK on every tick, free, from 2013. That is the missing measurement.

WHAT THE METADATA SAYS (read out of the installed package, not from the web):

    usatechidxusd  "US 100 Tech Index"   ticks from 2013-01-01,  daily candles from 1990-11-07
    usa30idxusd    "US 30 Index"         ticks from 2013-01-01,  daily candles from 2013-09-30
    usa500idxusd   "US 500 Index"        ticks from 2013-01-01

So the tick history is ~13 years, against the 3 years of NQ 1-minute and the 9 years of 15-minute
broker data already here; and the Nasdaq DAILY series reaches back to 1990, which is the only free
thing on offer that contains 2000-2002 and 2008 -- the regimes CLAUDE.md says this sample lacks.

WHAT THIS IS NOT. Dukascopy is a retail broker's CFD feed, not CME. Its spread is that broker's
spread, its volume is a tick count, and its prices are not NQ futures prices. Treat a spread
measured here as an ORDER OF MAGNITUDE for the futures spread, never as the futures spread itself
-- `crosscheck()` exists to say how far apart the two feeds actually are before anything is
concluded from one.
"""
from __future__ import annotations

import os
import subprocess
import sys

import numpy as np
import pandas as pd

NY = "America/New_York"
INSTRUMENTS = {
    "NASDAQ": "usatechidxusd",
    "US30": "usa30idxusd",
    "SP500": "usa500idxusd",
}


def fetch(instrument: str, start: str, end: str, timeframe: str = "tick",
          out_dir: str = "data/dukascopy", price: str = "bid", min_rows: int = 100) -> str:
    """Shell out to the dukascopy-node CLI. Requires network access to datafeed.dukascopy.com.

    Returns the path of the CSV the CLI wrote. `timeframe` is 'tick', 'm1', 'm15', 'd1', ...
    NOTE: at tick resolution the CLI emits timestamp,askPrice,bidPrice,askVolume,bidVolume."""
    os.makedirs(out_dir, exist_ok=True)
    cmd = ["npx", "--yes", "dukascopy-node", "-i", instrument, "-from", start, "-to", end,
           "-t", timeframe, "-f", "csv", "-dir", out_dir, "-p", price, "-v", "true"]
    before = {f: os.path.getmtime(os.path.join(out_dir, f))
              for f in os.listdir(out_dir) if f.endswith(".csv")}
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"dukascopy-node failed ({r.returncode}).\n{r.stderr[-2000:]}")
    made = sorted((os.path.join(out_dir, f) for f in os.listdir(out_dir)
                   if f.endswith(".csv") and (f not in before
                                              or os.path.getmtime(os.path.join(out_dir, f))
                                              > before[f])), key=os.path.getmtime)
    if not made:
        raise RuntimeError("dukascopy-node reported success but wrote no csv")
    path = made[-1]

    # MEASURED FAILURE MODE, do not remove. With datafeed.dukascopy.com unreachable the CLI prints
    # "File saved (0 Bytes)", writes an empty file and EXITS 0. A blocked or throttled download is
    # therefore indistinguishable from a successful one by return code alone, and a silently empty
    # -- or silently partial -- file is the worst possible input to a cost study. So the output is
    # validated here rather than trusted.
    size = os.path.getsize(path)
    if size == 0:
        raise RuntimeError(
            f"dukascopy-node exited 0 but wrote an EMPTY file ({path}). The download did not "
            f"happen -- usually datafeed.dukascopy.com is unreachable (proxy/egress policy, or "
            f"offline). Check connectivity before trusting any file from this directory.")
    n = sum(1 for _ in open(path)) - 1
    if n < min_rows:
        raise RuntimeError(
            f"{path} holds only {n} rows for {start}..{end} at '{timeframe}'. Expected at least "
            f"{min_rows}. Treat as a PARTIAL download, not as a quiet market.")
    return path


def load_ticks(path: str) -> pd.DataFrame:
    """Tick CSV -> UTC-indexed bid/ask frame with the spread already computed."""
    df = pd.read_csv(path)
    cols = {c.lower().replace("_", ""): c for c in df.columns}
    tcol = next(cols[k] for k in cols if "time" in k or k == "t")
    ts = df[tcol]
    # pandas 3 gives object/string columns a StringDtype that np.issubdtype cannot interpret,
    # so the numeric test goes through the pandas API rather than numpy's.
    ts = (pd.to_datetime(ts, unit="ms", utc=True) if pd.api.types.is_numeric_dtype(ts)
          else pd.to_datetime(ts, utc=True))
    bid = df[cols.get("bidprice", cols.get("bid"))].astype(float)
    ask = df[cols.get("askprice", cols.get("ask"))].astype(float)
    out = pd.DataFrame(dict(ts=ts, bid=bid, ask=ask))
    for k, name in (("bidvolume", "bid_vol"), ("askvolume", "ask_vol")):
        if k in cols:
            out[name] = df[cols[k]].astype(float)
    out = out.sort_values("ts").reset_index(drop=True)
    out["mid"] = (out["bid"] + out["ask"]) / 2.0
    out["spread"] = out["ask"] - out["bid"]
    idx = pd.DatetimeIndex(out["ts"]).tz_convert(NY)
    out["mod"] = idx.hour * 60 + idx.minute
    out["ymd"] = idx.year * 10000 + idx.month * 100 + idx.day
    return out


def spread_profile(ticks: pd.DataFrame, point_value: float = 2.0,
                   contracts: float = 1.0) -> pd.DataFrame:
    """Spread by minute of the New York day, in points and in dollars of round-turn cost.

    A round turn crosses the spread twice, so the dollar column is 2 x spread x point value. This
    is the number that belongs in a cost-sensitivity curve in place of a constant."""
    # NB: always index the `mod` column with brackets. `df.mod` is DataFrame.mod (modulo), so
    # `df.mod == 600` resolves to a bound method and compares False without raising.
    g = ticks.groupby("mod")["spread"]
    out = pd.DataFrame(dict(
        ticks=g.size(), mean_pts=g.mean(), median_pts=g.median(),
        p90_pts=g.quantile(0.90), p99_pts=g.quantile(0.99)))
    out["rt_cost_median"] = 2.0 * out["median_pts"] * point_value * contracts
    out["rt_cost_p90"] = 2.0 * out["p90_pts"] * point_value * contracts
    return out.reset_index()


def window_cost(ticks: pd.DataFrame, windows: dict, point_value: float = 2.0) -> pd.DataFrame:
    """Median and 90th-percentile round-turn spread cost inside each named minute window."""
    rows = []
    for name, (lo, hi) in windows.items():
        m = (ticks["mod"] >= lo) & (ticks["mod"] < hi)
        if not m.any():
            continue
        s = ticks.loc[m, "spread"]
        rows.append(dict(window=name, minutes=f"{lo//60:02d}:{lo%60:02d}-{hi//60:02d}:{hi%60:02d}",
                         ticks=int(m.sum()), median_pts=float(s.median()),
                         p90_pts=float(s.quantile(0.90)),
                         rt_median=2.0 * float(s.median()) * point_value,
                         rt_p90=2.0 * float(s.quantile(0.90)) * point_value))
    return pd.DataFrame(rows)


def to_bars(ticks: pd.DataFrame, tf_min: int = 15, price: str = "mid") -> pd.DataFrame:
    """Aggregate ticks into exact UTC-aligned bars, the way apm_sim expects them."""
    px = ticks[price].to_numpy(float)
    step = tf_min * 60_000_000_000
    key = ticks["ts"].to_numpy("datetime64[ns]").astype(np.int64) // step
    starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    ends = np.r_[starts[1:], len(key)]
    return pd.DataFrame(dict(
        timestamp=pd.to_datetime(key[starts] * step, utc=True),
        open=px[starts], high=np.maximum.reduceat(px, starts),
        low=np.minimum.reduceat(px, starts), close=px[ends - 1],
        volume=(np.add.reduceat(ticks["bid_vol"].to_numpy(float), starts)
                if "bid_vol" in ticks else (ends - starts).astype(float))))


def crosscheck(bars: pd.DataFrame, other_csv: str) -> dict:
    """How close is this feed to one already in the repository?

    Levels are expected to differ (different broker, different adjustment), so the comparison is on
    RETURNS -- the same test that pinned the broker timezone in apm_data.py. Anything below ~0.99
    means the two feeds are not the same instrument on the same clock, and the tick data should not
    be used to draw conclusions about the other one."""
    a = bars.set_index(pd.DatetimeIndex(bars["timestamp"]))["close"].pct_change()
    o = pd.read_csv(other_csv)
    b = pd.Series(o["close"].to_numpy(float),
                  index=pd.DatetimeIndex(pd.to_datetime(o["timestamp"], utc=True))).pct_change()
    j = pd.concat([a.rename("dk"), b.rename("ref")], axis=1, join="inner").dropna()
    if len(j) < 100:
        return dict(n=len(j), corr=np.nan, note="insufficient overlap")
    monthly = j.groupby(lambda x: x.strftime("%Y-%m")).apply(
        lambda g: g["dk"].corr(g["ref"]) if len(g) > 50 else np.nan).dropna()
    return dict(n=len(j), corr=float(j["dk"].corr(j["ref"])),
                worst_month=float(monthly.min()) if len(monthly) else np.nan,
                months_below_0_9=int((monthly < 0.9).sum()),
                level_gap_median=float((a.index.size and 0) or 0))


# --------------------------------------------------------------------------- self-test

def synth_ticks(n_days: int = 3, seed: int = 7, spread_rth: float = 0.5,
                spread_off: float = 2.5) -> pd.DataFrame:
    """Ticks with a KNOWN spread regime, so the measurement code can be checked against truth.

    The spread is `spread_rth` inside 09:30-16:00 New York and `spread_off` outside it -- the real
    shape, exaggerated. If `spread_profile` cannot recover those two numbers the code is wrong."""
    rng = np.random.default_rng(seed)
    rows = []
    px = 15000.0
    for d in range(n_days):
        day = pd.Timestamp("2024-03-04", tz="UTC") + pd.Timedelta(days=d)
        for minute in range(0, 1440):
            t = day + pd.Timedelta(minutes=minute)
            mod = int(t.tz_convert(NY).hour) * 60 + int(t.tz_convert(NY).minute)
            rth = 570 <= mod < 960
            k = rng.integers(3, 12) if rth else rng.integers(1, 4)
            sp = spread_rth if rth else spread_off
            for j in range(k):
                px += rng.normal(0, 1.5)
                rows.append((t + pd.Timedelta(seconds=int(60 * j / k)),
                             px - sp / 2, px + sp / 2, 1.0, 1.0))
    df = pd.DataFrame(rows, columns=["ts", "bid", "ask", "bid_vol", "ask_vol"])
    df["mid"] = (df.bid + df.ask) / 2
    df["spread"] = df.ask - df.bid
    idx = pd.DatetimeIndex(df["ts"]).tz_convert(NY)
    df["mod"] = idx.hour * 60 + idx.minute
    df["ymd"] = idx.year * 10000 + idx.month * 100 + idx.day
    return df


def selftest() -> int:
    fails = []

    def chk(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
        if not cond:
            fails.append(name)

    print("\n1. tick CSV round-trip through load_ticks()")
    t = synth_ticks(3)
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"), "_dk_selftest.csv")
    out = t[["ts", "ask", "bid", "ask_vol", "bid_vol"]].rename(
        columns={"ts": "timestamp", "ask": "askPrice", "bid": "bidPrice",
                 "ask_vol": "askVolume", "bid_vol": "bidVolume"})
    out.to_csv(tmp, index=False)
    ld = load_ticks(tmp)
    chk("row count preserved", len(ld) == len(t), f"{len(ld):,} ticks")
    chk("bid/ask not transposed", bool((ld["ask"] >= ld["bid"]).all()))
    chk("mid and spread derived correctly",
        np.allclose(ld["mid"], (ld["bid"] + ld["ask"]) / 2) and
        np.allclose(ld["spread"], ld["ask"] - ld["bid"]))

    print("\n2. spread_profile() recovers the known regime (truth: 0.5 RTH / 2.5 off-hours)")
    prof = spread_profile(ld, point_value=2.0)
    rth = prof[(prof["mod"] >= 570) & (prof["mod"] < 960)]["median_pts"].median()
    off = prof[(prof["mod"] < 570) | (prof["mod"] >= 960)]["median_pts"].median()
    chk("RTH spread recovered", abs(rth - 0.5) < 1e-6, f"measured {rth:.3f}")
    chk("off-hours spread recovered", abs(off - 2.5) < 1e-6, f"measured {off:.3f}")
    chk("round-turn cost is 2 x spread x point value",
        abs(float(prof[prof["mod"] == 600]["rt_cost_median"].iloc[0]) - 2 * 0.5 * 2.0) < 1e-9)

    print("\n3. window_cost() on the windows the strategies actually trade")
    wc = window_cost(ld, {"APM entries": (570, 660), "overnight": (0, 240)}, point_value=2.0)
    a = wc[wc["window"] == "APM entries"]["rt_median"].iloc[0]
    b = wc[wc["window"] == "overnight"]["rt_median"].iloc[0]
    chk("RTH window cheaper than overnight", a < b, f"${a:.2f} vs ${b:.2f} round turn")

    print("\n4. to_bars() builds exact UTC-aligned bars")
    bars = to_bars(ld, 15, "mid")
    step = 15 * 60_000_000_000
    tsi = bars["timestamp"].to_numpy("datetime64[ns]").astype(np.int64)
    chk("every bar on a 15-minute UTC boundary", bool(np.all(tsi % step == 0)), f"{len(bars)} bars")
    chk("timestamps strictly increasing", bool(np.all(np.diff(tsi) > 0)))
    chk("high >= max(open, close)",
        bool((bars["high"] >= np.maximum(bars["open"], bars["close"]) - 1e-9).all()))
    chk("low <= min(open, close)",
        bool((bars["low"] <= np.minimum(bars["open"], bars["close"]) + 1e-9).all()))
    chk("OHLC bracket every constituent tick", bool((bars["high"] >= bars["low"]).all()))

    print("\n5. crosscheck() detects a matching and a non-matching feed")
    ref = bars.copy()
    ref["close"] = ref["close"] * 1.05 + 100.0          # same returns, different level
    rp = os.path.join(os.environ.get("TMPDIR", "/tmp"), "_dk_ref.csv")
    ref[["timestamp", "close"]].assign(
        timestamp=ref["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")).to_csv(rp, index=False)
    cc = crosscheck(bars, rp)
    chk("a level-shifted copy still matches on returns", cc["corr"] > 0.999,
        f"corr {cc['corr']:.5f} over {cc['n']} bars")
    ref2 = bars.copy()
    ref2["close"] = np.random.default_rng(1).normal(15000, 50, len(ref2))
    rp2 = os.path.join(os.environ.get("TMPDIR", "/tmp"), "_dk_ref2.csv")
    ref2[["timestamp", "close"]].assign(
        timestamp=ref2["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")).to_csv(rp2, index=False)
    cc2 = crosscheck(bars, rp2)
    chk("an unrelated series does NOT match", abs(cc2["corr"]) < 0.2, f"corr {cc2['corr']:.4f}")

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    print(__doc__)
