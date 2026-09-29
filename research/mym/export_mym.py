"""Turn the Databento MYM trades zip into ONE small bar file that keeps the aggressor side.

Run this on the machine that holds the zip (it never leaves it):

    pip install zstandard numpy pandas          # Python < 3.14 only needs zstandard
    python export_mym.py --zip ~/Downloads/GLBX-20260927-EBYLQK3EEU.zip
    python export_mym.py --zip ... --tf 30      # 30-second bars instead of 1-minute

Output: mym_<tf>s.csv.gz next to this script, one row per bar that traded:

    time_ny     bar OPEN time, New York local, naive (DST handled per trade, not per file)
    open high low close          whole index points (MYM tick = 1.0 pt = $0.50)
    volume      contracts
    buy_vol     contracts where the BUYER was the aggressor  (Databento side 'B')
    sell_vol    contracts where the SELLER was the aggressor (Databento side 'A')
    trades      number of prints
    iid         Databento instrument id of the contract traded (front month by that day's volume)
    roll        1 on the first bar of a new contract: the price JUMPS there, never read a return
                across it

buy_vol - sell_vol is TRUE aggressor delta. Every CVD study on this branch had to sign whole bars
by their own direction because no feed carried it; this one does, which is the main reason tick
data is worth more than the bars already on disk.

It also prints a sha256 of the output, so the uploaded copy can be registered in
research/datasets.py and proved identical later.
"""
import argparse
import gzip
import hashlib
import os
import struct
import zipfile

import numpy as np
import pandas as pd

try:                                                    # Python 3.14+ has zstd built in
    from compression import zstd as _zstd

    def _unzstd(b):
        return _zstd.decompress(b)
except ImportError:
    import zstandard as _zs

    def _unzstd(b):
        return _zs.ZstdDecompressor().decompressobj().decompress(b)

NS = 1_000_000_000
# Databento TradeMsg, 48 bytes (same layout as the uploaded mym_data.py)
DT = np.dtype([("len", "u1"), ("rtype", "u1"), ("pub", "<u2"), ("iid", "<u4"), ("ts", "<u8"),
               ("px", "<i8"), ("sz", "<u4"), ("act", "S1"), ("side", "S1"), ("flags", "u1"),
               ("depth", "u1"), ("tsr", "<u8"), ("dlt", "<i4"), ("seq", "<u4")])


def records(raw):
    if raw[:3] != b"DBN":
        raise ValueError("not a DBN file")
    mlen = struct.unpack("<I", raw[4:8])[0]
    body = raw[8 + mlen:]
    body = body[: len(body) - len(body) % DT.itemsize]
    return np.frombuffer(body, dtype=DT)


def ny_ns(ts_utc):
    """UTC epoch ns -> New York local epoch ns, per trade (a day file can straddle a DST switch)."""
    t = pd.to_datetime(ts_utc.astype(np.int64), unit="ns", utc=True).tz_convert("America/New_York")
    return t.tz_localize(None).asi8


def day_bars(raw, tf):
    a = records(raw)
    a = a[(a["rtype"] == 0) & (a["px"] > 5000 * NS)]     # trades, outrights only (no spreads)
    if len(a) == 0:
        return None
    ids, inv = np.unique(a["iid"], return_inverse=True)
    lead = ids[np.argmax(np.bincount(inv, weights=a["sz"]))]
    a = a[a["iid"] == lead]
    a = a[np.argsort(a["ts"], kind="stable")]
    loc = ny_ns(a["ts"])
    px = (a["px"] // NS).astype(np.int64)
    sz = a["sz"].astype(np.int64)
    buy = np.where(a["side"] == b"B", sz, 0)
    sell = np.where(a["side"] == b"A", sz, 0)
    key = loc // (tf * NS)
    st = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
    en = np.r_[st[1:], len(key)] - 1
    return pd.DataFrame({
        "t": key[st] * tf, "open": px[st], "high": np.maximum.reduceat(px, st),
        "low": np.minimum.reduceat(px, st), "close": px[en], "volume": np.add.reduceat(sz, st),
        "buy_vol": np.add.reduceat(buy, st), "sell_vol": np.add.reduceat(sell, st),
        "trades": np.diff(np.r_[st, len(key)]), "iid": lead})


def export(zip_path, tf, out):
    frames = []
    with zipfile.ZipFile(zip_path) as z:
        names = sorted(n for n in z.namelist() if n.endswith(".dbn.zst"))
        print(f"{len(names)} day files", flush=True)
        for i, n in enumerate(names):
            f = day_bars(_unzstd(z.read(n)), tf)
            if f is not None:
                frames.append(f)
            if i % 100 == 0:
                print(f"  {i}/{len(names)} {n}", flush=True)
    d = pd.concat(frames, ignore_index=True)
    # two day files can hold the same bar (the session crosses midnight UTC); keep the larger print
    d = d.sort_values(["t", "volume"]).drop_duplicates("t", keep="last").reset_index(drop=True)
    d["roll"] = (d["iid"] != d["iid"].shift()).astype(int)
    d.loc[0, "roll"] = 0
    d.insert(0, "time_ny", pd.to_datetime(d.pop("t"), unit="s").dt.strftime("%Y-%m-%d %H:%M:%S"))
    with gzip.open(out, "wt", compresslevel=6) as fh:
        d.to_csv(fh, index=False)
    h = hashlib.sha256(open(out, "rb").read()).hexdigest()
    side_share = (d["buy_vol"] + d["sell_vol"]).sum() / max(d["volume"].sum(), 1)
    print(f"done: {len(d):,} bars {d['time_ny'].iloc[0]} -> {d['time_ny'].iloc[-1]}")
    print(f"      contract rolls: {int(d['roll'].sum())}   volume with an aggressor side: {side_share:.1%}")
    print(f"      {out}  {os.path.getsize(out) / 1e6:.1f} MB  sha256 {h[:16]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default=os.path.expanduser("~/Downloads/GLBX-20260927-EBYLQK3EEU.zip"))
    ap.add_argument("--tf", type=int, default=60, help="bar size in seconds (default 60)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    export(a.zip, a.tf, a.out or os.path.join(here, f"mym_{a.tf}s.csv.gz"))
