"""Historical BTC bars from a public exchange API, in this repository's canonical bar format.

Written because `data/README.md` insists every bar file be reproducible from a recorded command
rather than dragged in by hand. The output columns, ordering and timezone are exactly what
`scripts/quant-ingest.ts` emits for NQ, so a BTC file drops into the same loaders.

Three sources, because they fail in different ways and none is good at everything:

* `vision`   -- data.binance.vision monthly ZIPs. The only practical way to get MINUTE bars back
                to 2017: one HTTP request per month instead of ~4,000 paged REST calls. Use this
                for anything below an hour.
* `binance`  -- the /api/v3/klines REST endpoint, 1,000 bars per call. Fine for daily or hourly,
                and the only one of the three that can top up a file to the current bar cheaply.
* `coinbase` -- BTC-USD on a US venue, 300 candles per call. Slower and shorter, but it is a
                different price series, which is what you want when the question is whether a
                result is an artefact of one exchange's tape.

Binance quotes BTC in USDT, Coinbase in USD. They are not the same instrument and the basis is
small but real; do not splice them into one file.

NO THIRD-PARTY IMPORTS. stdlib urllib honours HTTPS_PROXY, so this runs unchanged inside the
sandbox once the destination host is allowed by the egress policy.

    python3 research/fetch_btc.py --tf 1d --start 2017-08-17 --out data/BTCUSDT_1d.csv
    python3 research/fetch_btc.py --tf 1m --start 2023-01-01 --source vision --out data/BTCUSDT_1m.csv
    python3 research/fetch_btc.py --tf 1h --start 2024-01-01 --source coinbase --out data/BTCUSD_1h.csv

A run that ends in `EGRESS BLOCKED` is not a bug in this file: the host is not on this
environment's network allow-list. See the note at the bottom of the module.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "Mozilla/5.0 (compatible; quant-research/1.0)"}

# Seconds per bar. Binance and Coinbase spell these differently; one table, two renderings.
TF_SEC = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
          "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "12h": 43200,
          "1d": 86400, "1w": 604800}
# Coinbase only serves these six granularities.
CB_GRAN = {60, 300, 900, 3600, 21600, 86400}

HEADER = ["timestamp", "open", "high", "low", "close", "volume"]


class Blocked(RuntimeError):
    """The proxy refused the CONNECT, so the request never reached the exchange."""


def _get(url: str, tries: int = 4) -> bytes:
    """One GET with backoff. A proxy 403/407 is a policy denial and is never retried."""
    delay = 2.0
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 407) and attempt == 0:
                raise Blocked(f"{url} -> HTTP {e.code}") from e
            if e.code == 404:
                raise                      # a missing month is expected; the caller decides
            if e.code in (418, 429):       # Binance rate limit: it tells you how long to wait
                time.sleep(float(e.headers.get("Retry-After", delay)))
            elif attempt == tries - 1:
                raise
            else:
                time.sleep(delay)
        except urllib.error.URLError as e:
            msg = str(e.reason)
            if "CONNECT" in msg or "403" in msg or "407" in msg:
                raise Blocked(f"{url} -> {msg}") from e
            if attempt == tries - 1:
                raise
            time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"unreachable: {url}")


def _ms(d: datetime) -> int:
    return int(d.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _parse_day(s: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise SystemExit(f"cannot parse date {s!r}; use YYYY-MM-DD")


def _row(open_ms: int, o, h, l, c, v):
    ts = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc)
    return (open_ms, ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            float(o), float(h), float(l), float(c), float(v))


# --------------------------------------------------------------------------- sources

def from_binance(symbol, tf, start, end, log):
    """Paged klines. Binance returns bars with openTime >= startTime, up to `limit` of them."""
    url = "https://api.binance.com/api/v3/klines"
    step_ms = TF_SEC[tf] * 1000
    cur, end_ms, out = _ms(start), _ms(end), []
    while cur < end_ms:
        q = f"{url}?symbol={symbol}&interval={tf}&startTime={cur}&endTime={end_ms}&limit=1000"
        k = json.loads(_get(q))
        if not k:
            break
        out.extend(_row(int(b[0]), b[1], b[2], b[3], b[4], b[5]) for b in k)
        nxt = int(k[-1][0]) + step_ms
        if nxt <= cur:                     # no forward progress: stop rather than spin
            break
        cur = nxt
        log(f"  binance {len(out):>9,} bars, through {out[-1][1]}")
        if len(k) < 1000:
            break
        time.sleep(0.12)                   # well inside the 1,200 weight/minute budget
    return out


def from_vision(symbol, tf, start, end, log):
    """Monthly ZIPs of the same klines. One request per month; the current month is absent."""
    base = "https://data.binance.vision/data/spot/monthly/klines"
    out, miss = [], 0
    m = start.replace(day=1)
    while m <= end:
        name = f"{symbol}-{tf}-{m:%Y-%m}"
        try:
            blob = _get(f"{base}/{symbol}/{tf}/{name}.zip")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            miss += 1                      # before listing, or the not-yet-published month
            log(f"  vision {name}: not published")
            m = (m + timedelta(days=32)).replace(day=1)
            continue
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            with z.open(z.namelist()[0]) as fh:
                for r in csv.reader(io.TextIOWrapper(fh, "utf-8")):
                    if not r or not r[0].lstrip("-").isdigit():
                        continue           # some months carry a header row, most do not
                    t = int(r[0])
                    if len(r[0]) > 13:     # 2025 files switched openTime to MICROseconds
                        t //= 1000
                    out.append(_row(t, r[1], r[2], r[3], r[4], r[5]))
        log(f"  vision {name}: {len(out):>9,} bars")
        m = (m + timedelta(days=32)).replace(day=1)
    if miss and not out:
        raise RuntimeError("every month 404'd -- check the symbol and timeframe spelling")
    return out


def from_coinbase(symbol, tf, start, end, log):
    """Coinbase Exchange candles: 300 per call, [time, low, high, open, close, volume], newest first."""
    gran = TF_SEC[tf]
    if gran not in CB_GRAN:
        raise SystemExit(f"coinbase serves only {sorted(CB_GRAN)} second candles, not {gran}")
    url = f"https://api.exchange.coinbase.com/products/{symbol}/candles"
    span, cur, out = gran * 300, start, []
    while cur < end:
        stop = min(cur + timedelta(seconds=span), end)
        c = json.loads(_get(f"{url}?granularity={gran}"
                            f"&start={cur:%Y-%m-%dT%H:%M:%S}&end={stop:%Y-%m-%dT%H:%M:%S}"))
        out.extend(_row(int(b[0]) * 1000, b[3], b[2], b[1], b[4], b[5])
                   for b in sorted(c, key=lambda x: x[0]))
        cur = stop
        log(f"  coinbase {len(out):>9,} bars, through {out[-1][1] if out else '-'}")
        time.sleep(0.12)                   # 10 req/s public limit, shared across the IP
    return out


SOURCES = {"binance": from_binance, "vision": from_vision, "coinbase": from_coinbase}
DEFAULT_SYMBOL = {"binance": "BTCUSDT", "vision": "BTCUSDT", "coinbase": "BTC-USD"}


# --------------------------------------------------------------------------- output

def write(rows, path, start, end):
    """Sort, de-duplicate on open time, clip to the window, and report what the file contains."""
    seen, keep = set(), []
    lo, hi = _ms(start), _ms(end)
    for r in sorted(rows, key=lambda r: r[0]):
        if r[0] in seen or not (lo <= r[0] < hi):
            continue
        seen.add(r[0])
        keep.append(r)
    if not keep:
        raise SystemExit("no bars in the requested window -- nothing written")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        for r in keep:
            w.writerow([r[1], f"{r[2]:.8g}", f"{r[3]:.8g}", f"{r[4]:.8g}",
                        f"{r[5]:.8g}", f"{r[6]:.8g}"])
    os.replace(tmp, path)                  # atomic, so a killed run leaves no half file
    return keep


def audit(rows, tf):
    """The cheap sanity checks data/README.md applies to any new bar file."""
    step = TF_SEC[tf]
    gaps = sum(1 for a, b in zip(rows, rows[1:]) if (b[0] - a[0]) // 1000 != step)
    bad = sum(1 for r in rows if not (r[3] >= max(r[2], r[5]) and r[4] <= min(r[2], r[5])))
    return gaps, bad


def main(argv=None):
    p = argparse.ArgumentParser(description="Historical BTC bars -> canonical CSV.")
    p.add_argument("--source", default="binance", choices=sorted(SOURCES))
    p.add_argument("--symbol", default=None, help="default: BTCUSDT, or BTC-USD on coinbase")
    p.add_argument("--tf", default="1d", help=f"one of {' '.join(TF_SEC)}")
    p.add_argument("--start", default="2017-08-17", help="UTC, inclusive (Binance BTCUSDT day 1)")
    p.add_argument("--end", default=None, help="UTC, exclusive; default now")
    p.add_argument("--out", default=None, help="default data/<SYMBOL>_<tf>.csv")
    p.add_argument("-q", "--quiet", action="store_true")
    a = p.parse_args(argv)

    if a.tf not in TF_SEC:
        raise SystemExit(f"unknown timeframe {a.tf!r}; one of {' '.join(TF_SEC)}")
    symbol = a.symbol or DEFAULT_SYMBOL[a.source]
    start = _parse_day(a.start)
    end = _parse_day(a.end) if a.end else datetime.now(timezone.utc)
    out = a.out or f"data/{symbol.replace('-', '')}_{a.tf}.csv"
    log = (lambda *_: None) if a.quiet else (lambda m: print(m, file=sys.stderr, flush=True))

    log(f"{a.source}: {symbol} {a.tf} {start:%Y-%m-%d} -> {end:%Y-%m-%d}")
    t0 = time.time()
    try:
        rows = SOURCES[a.source](symbol, a.tf, start, end, log)
    except Blocked as e:
        print(f"\nEGRESS BLOCKED: {e}\n\n"
              "The proxy refused the connection, so the request never reached the exchange.\n"
              "The host is not on this environment's network allow-list. Either widen the\n"
              "policy (https://code.claude.com/docs/en/claude-code-on-the-web) or run this\n"
              "script on a machine with open egress and commit the CSV.", file=sys.stderr)
        return 2

    kept = write(rows, out, start, end)
    gaps, bad = audit(kept, a.tf)
    log(f"\n{out}")
    log(f"  {len(kept):,} bars  {kept[0][1]} -> {kept[-1][1]}  in {time.time() - t0:.1f}s")
    log(f"  {gaps:,} gaps (missing bars / venue downtime), {bad} OHLC violations")
    if bad:
        log("  OHLC violations are a red flag: a real tape has none. Inspect before using.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
