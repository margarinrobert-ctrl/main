"""Historical BTC bars from a public exchange API, in this repository's canonical bar format.

Written because `data/README.md` insists every bar file be reproducible from a recorded command
rather than dragged in by hand. The output columns, ordering and timezone are exactly what
`scripts/quant-ingest.ts` emits for NQ, so a BTC file drops into the same loaders.

Three sources, because they fail in different ways and none is good at everything:

* `vision`   -- data.binance.vision archive ZIPs. The only practical way to get SUB-MINUTE or
                minute bars over years: one request per month (or per day, below a minute) instead
                of tens of thousands of paged REST calls.
* `binance`  -- the /api/v3/klines REST endpoint, 1,000 bars per call. Fine for daily or hourly,
                and the only one of the three that can top up a file to the current bar cheaply.
* `coinbase` -- BTC-USD on a US venue, 300 candles per call. Slower, shorter, and floored at one
                minute, but it is a different price series, which is what you want when the
                question is whether a result is an artefact of one exchange's tape.

SUB-MINUTE. No venue publishes a 30-second bar. Binance's finest native kline is **1 second**, and
every coarser timeframe that 1s divides is an EXACT aggregation of it -- a 30s bar is 30 of them,
first open, max high, min low, last close, summed volume, with no information lost and no
interpolation. So `--tf 30s` fetches 1s and folds. The same machinery gives 2m, 10m or 45s.

NOTHING IS STORED BUT THE OUTPUT, which is the point of the design. A year of 30s bars means
31.5M one-second source bars; held in a list to fold at the end, that is 10 GB of RAM (measured:
317 bytes per row tuple), and three years is 30 GB. So every source is a GENERATOR yielding one
archive file or one REST page at a time, `Folder` keeps exactly one open bucket, and completed
bars go straight to the CSV. Peak memory is one file's rows, peak disk is the output file, and
neither grows with the length of the pull. The bytes still have to cross the wire -- that part is
irreducible -- but they are never all resident anywhere.

NO THIRD-PARTY IMPORTS. stdlib urllib honours HTTPS_PROXY, so this runs unchanged inside the
sandbox once the destination host is allowed by the egress policy.

    python3 research/fetch_btc.py --tf 1d --start 2017-08-17 --out data/BTCUSDT_1d.csv
    python3 research/fetch_btc.py --tf 1m --start 2023-01-01 --source vision
    python3 research/fetch_btc.py --tf 30s --start 2025-01-01 --source vision   # folds 1s klines
    python3 research/fetch_btc.py --tf 30s --start 2025-01-01 --dry-run         # size it first

A run that ends in `EGRESS BLOCKED` is not a bug in this file: the host is not on this
environment's network allow-list.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "Mozilla/5.0 (compatible; quant-research/1.0)"}

# Binance's native kline intervals, seconds per bar. Anything else is folded from one of these.
# Note what is NOT here: 30s, 10s, 2m, 45s. They are all reachable by aggregation, none natively.
NATIVE = {"1s": 1, "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
          "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200,
          "1d": 86400, "3d": 259200, "1w": 604800}
UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
# Coinbase serves only these six granularities, and nothing below a minute.
CB_GRAN = {60, 300, 900, 3600, 21600, 86400}
# Rough compressed bytes per bar in a Vision ZIP, for the size estimate. Measured on 2024 files.
BYTES_PER_BAR = 11

HEADER = ["timestamp", "open", "high", "low", "close", "volume"]


class Blocked(RuntimeError):
    """The proxy refused the CONNECT, so the request never reached the exchange."""


def tf_seconds(tf: str) -> int:
    """'30s' -> 30, '1m' -> 60, '4h' -> 14400. The one place a timeframe string is interpreted."""
    m = re.fullmatch(r"(\d+)([smhdw])", tf.strip().lower())
    if not m:
        raise SystemExit(f"cannot parse timeframe {tf!r}; use forms like 30s, 1m, 15m, 4h, 1d")
    n = int(m.group(1))
    if n <= 0:
        raise SystemExit(f"timeframe {tf!r} must be positive")
    return n * UNIT[m.group(2)]


def native_for(sec: int) -> tuple[str, int]:
    """The coarsest native interval that divides `sec` evenly -- the fewest bars to fetch and fold.

    30s has no divisor above 1s, so it pulls 1s. 2m divides by 1m, not by 3m. Since 1s divides
    every whole-second timeframe, nothing expressible here is unreachable; the guard below only
    fires if NATIVE ever loses its 1s entry, and refusing beats silently approximating.
    """
    best = max((v for v in NATIVE.values() if sec % v == 0), default=0)
    if not best:
        raise SystemExit(f"{sec}s is not a whole multiple of any Binance interval "
                         f"({' '.join(NATIVE)}); pick a timeframe that is")
    return next(k for k, v in NATIVE.items() if v == best), best


class Folder:
    """Folds a stream of ascending native bars into `sec` buckets, holding exactly one of them.

    This is the whole reason a multi-GB pull fits in a few MB of memory. Bars arrive a file or a
    page at a time; each completed bucket is handed to `sink` and forgotten. Clipping to the
    window and the gap/OHLC audit happen on the way past, so no second pass over the data is ever
    needed -- there is no second pass available, because nothing is kept.

    Buckets are anchored to the UNIX epoch, which for any timeframe dividing a day also aligns
    them to midnight UTC.

    Input must be ascending and de-duplicated ACROSS files as well as within them: monthly and
    daily archives overlap, and a repeated bar would double-count its volume into the bucket. A
    row at or before the last one seen is dropped and counted in `backwards` rather than silently
    accepted; a large count there means the source is not ordered the way this assumes, which is a
    bug to investigate, not a number to ignore.
    """

    def __init__(self, sec: int, lo: int | None = None, hi: int | None = None, sink=None):
        self.sec, self.ms, self.lo, self.hi = sec, sec * 1000, lo, hi
        self.sink = sink
        self.rows = [] if sink is None else None   # collect only when no sink: used by fold()
        self._cur = None
        self._last_src = None
        self._prev_out = None
        self.backwards = self.n = self.gaps = self.bad = 0
        self.first = self.last = None

    def _emit(self, b):
        row = _row(b[0], b[1], b[2], b[3], b[4], b[5])
        if self.lo is not None and not (self.lo <= b[0] < self.hi):
            return                                  # outside the requested window
        if self._prev_out is not None and (b[0] - self._prev_out) // 1000 != self.sec:
            self.gaps += 1
        self._prev_out = b[0]
        if not (row[3] >= max(row[2], row[5]) and row[4] <= min(row[2], row[5])):
            self.bad += 1
        self.n += 1
        if self.first is None:
            self.first = row[1]
        self.last = row[1]
        if self.sink is None:
            self.rows.append(row)
        else:
            self.sink(row)

    def feed(self, rows):
        for r in rows:
            if self._last_src is not None and r[0] <= self._last_src:
                self.backwards += 1
                continue
            self._last_src = r[0]
            k = r[0] - (r[0] % self.ms)
            if self._cur is None or k != self._cur[0]:
                if self._cur is not None:
                    self._emit(self._cur)
                self._cur = [k, r[2], r[3], r[4], r[5], r[6]]   # open, high, low, close, volume
            else:
                self._cur[2] = max(self._cur[2], r[3])
                self._cur[3] = min(self._cur[3], r[4])
                self._cur[4] = r[5]
                self._cur[5] += r[6]

    def close(self):
        """Flush the final bucket. It is partial only if the window ended mid-bar."""
        if self._cur is not None:
            self._emit(self._cur)
            self._cur = None
        return self


def fold(rows, sec: int):
    """Batch convenience over `Folder`: one fold definition, exercised by both paths."""
    f = Folder(sec)
    f.feed(sorted(rows, key=lambda r: r[0]))
    return f.close().rows


def _get(url: str, tries: int = 4) -> bytes:
    """One GET with backoff. A proxy 403/407 is a policy denial and is never retried."""
    delay = 2.0
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 407) and attempt == 0:
                raise Blocked(f"{url} -> HTTP {e.code}") from e
            if e.code == 404:
                raise                      # a missing month/day is expected; the caller decides
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
    stamp = "%Y-%m-%dT%H:%M:%SZ" if open_ms % 1000 == 0 else "%Y-%m-%dT%H:%M:%S.%fZ"
    return (open_ms, ts.strftime(stamp),
            float(o), float(h), float(l), float(c), float(v))


def _klines(reader):
    """Parse Binance kline rows, from CSV or JSON: [openTime, o, h, l, c, v, ...]."""
    for r in reader:
        if not r or not str(r[0]).lstrip("-").isdigit():
            continue                       # some archive months carry a header row, most do not
        t = int(r[0])
        if len(str(r[0])) > 13:            # 2025 archive files switched openTime to MICROseconds
            t //= 1000
        yield _row(t, r[1], r[2], r[3], r[4], r[5])


# --------------------------------------------------------------------------- sources
# Each yields an iterable of rows per network round trip, and never accumulates. The caller folds
# and writes as chunks arrive, so peak memory is one chunk regardless of how long the pull runs.

def from_binance(symbol, interval, start, end, log):
    """Paged klines. Binance returns bars with openTime >= startTime, up to `limit` of them."""
    url = "https://api.binance.com/api/v3/klines"
    step_ms = NATIVE[interval] * 1000
    cur, end_ms, seen = _ms(start), _ms(end), 0
    while cur < end_ms:
        q = f"{url}?symbol={symbol}&interval={interval}&startTime={cur}&endTime={end_ms}&limit=1000"
        k = json.loads(_get(q))
        if not k:
            break
        seen += len(k)
        yield _klines(k)
        nxt = int(k[-1][0]) + step_ms
        if nxt <= cur:                     # no forward progress: stop rather than spin
            break
        cur = nxt
        log(f"  binance {seen:>12,} bars fetched, through "
            f"{datetime.fromtimestamp(int(k[-1][0]) / 1000, tz=timezone.utc):%Y-%m-%d %H:%M}")
        if len(k) < 1000:
            break
        time.sleep(0.12)                   # well inside the 1,200 weight/minute budget


def _unzip(blob):
    """Rows from an archive ZIP. Decompressed in memory and dropped as soon as they are folded."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        with z.open(z.namelist()[0]) as fh:
            yield from _klines(csv.reader(io.TextIOWrapper(fh, "utf-8")))


def from_vision(symbol, interval, start, end, log):
    """Archive ZIPs: monthly where published, falling back to daily.

    The fallback is not a nicety. Monthly files stop at the previous complete month, and the 1s
    interval is published DAILY only for much of its history -- so a 30s pull that only tried
    monthly would come back empty for the exact case it exists to serve.
    """
    base = "https://data.binance.vision/data/spot"
    got = missed = 0
    m = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while m <= end:
        nxt = (m + timedelta(days=32)).replace(day=1)
        try:
            blob = _get(f"{base}/monthly/klines/{symbol}/{interval}/"
                        f"{symbol}-{interval}-{m:%Y-%m}.zip")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            d, days = max(m, start.replace(hour=0, minute=0, second=0, microsecond=0)), 0
            while d < min(nxt, end + timedelta(days=1)):
                try:
                    yield _unzip(_get(f"{base}/daily/klines/{symbol}/{interval}/"
                                      f"{symbol}-{interval}-{d:%Y-%m-%d}.zip"))
                    days += 1
                except urllib.error.HTTPError as e2:
                    if e2.code != 404:
                        raise
                    missed += 1            # before listing, or today's not-yet-published file
                d += timedelta(days=1)
            got += bool(days)
            log(f"  vision {m:%Y-%m} daily:   {days} files")
        else:
            got += 1
            yield _unzip(blob)
            log(f"  vision {m:%Y-%m} monthly")
        m = nxt
    if not got:
        raise SystemExit(f"every archive file 404'd for {symbol} {interval} -- check the symbol "
                         f"spelling and that this interval is published for this date range")
    if missed:
        log(f"  {missed} archive file(s) absent (before listing, or not yet published)")


def check_source(source, interval, tf):
    """Refuse an impossible combination before anything is fetched, printed or estimated."""
    if source == "coinbase" and NATIVE[interval] not in CB_GRAN:
        raise SystemExit(
            f"coinbase serves only {sorted(CB_GRAN)}-second candles and nothing below a minute, "
            f"so it cannot supply {tf} (which needs {interval} bars); use --source vision")


def from_coinbase(symbol, interval, start, end, log):
    """Coinbase Exchange candles: 300 per call, [time, low, high, open, close, volume], newest first."""
    check_source("coinbase", interval, interval)
    gran = NATIVE[interval]
    url = f"https://api.exchange.coinbase.com/products/{symbol}/candles"
    span, cur, seen = gran * 300, start, 0
    while cur < end:
        stop = min(cur + timedelta(seconds=span), end)
        c = json.loads(_get(f"{url}?granularity={gran}"
                            f"&start={cur:%Y-%m-%dT%H:%M:%S}&end={stop:%Y-%m-%dT%H:%M:%S}"))
        seen += len(c)
        yield [_row(int(b[0]) * 1000, b[3], b[2], b[1], b[4], b[5])
               for b in sorted(c, key=lambda x: x[0])]
        cur = stop
        log(f"  coinbase {seen:>10,} bars fetched, through {stop:%Y-%m-%d %H:%M}")
        time.sleep(0.12)                   # 10 req/s public limit, shared across the IP


SOURCES = {"binance": from_binance, "vision": from_vision, "coinbase": from_coinbase}
DEFAULT_SYMBOL = {"binance": "BTCUSDT", "vision": "BTCUSDT", "coinbase": "BTC-USD"}


# --------------------------------------------------------------------------- output

def estimate(source, interval, sec, start, end):
    """What the pull will cost, in requests, native bars, output bars and rough download."""
    span = (end - start).total_seconds()
    native = int(span // NATIVE[interval])
    final = int(span // sec)
    if source == "binance":
        reqs = -(-native // 1000)
    elif source == "coinbase":
        reqs = -(-native // 300)
    else:
        months = (end.year - start.year) * 12 + end.month - start.month + 1
        reqs = months if NATIVE[interval] >= 60 else int(span // 86400) + 1
    return reqs, native, final, native * BYTES_PER_BAR


def audit(rows, sec):
    """Gap and OHLC-violation counts for a list of bars. `Folder` computes these as it streams;
    this is the batch equivalent, kept for tests and for checking a file someone else produced."""
    gaps = sum(1 for a, b in zip(rows, rows[1:]) if (b[0] - a[0]) // 1000 != sec)
    bad = sum(1 for r in rows if not (r[3] >= max(r[2], r[5]) and r[4] <= min(r[2], r[5])))
    return gaps, bad


def _human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f}{u}" if u == "B" else f"{n:.1f}{u}"
        n /= 1024


def main(argv=None):
    p = argparse.ArgumentParser(description="Historical BTC bars -> canonical CSV.")
    p.add_argument("--source", default="binance", choices=sorted(SOURCES))
    p.add_argument("--symbol", default=None, help="default: BTCUSDT, or BTC-USD on coinbase")
    p.add_argument("--tf", default="1d", help="30s, 1m, 5m, 4h, 1d ... folded from the finest "
                                              "native interval that divides it")
    p.add_argument("--start", default="2017-08-17", help="UTC, inclusive (Binance BTCUSDT day 1)")
    p.add_argument("--end", default=None, help="UTC, exclusive; default now")
    p.add_argument("--out", default=None, help="default data/<SYMBOL>_<tf>.csv")
    p.add_argument("--dry-run", action="store_true", help="print the cost estimate and stop")
    p.add_argument("-q", "--quiet", action="store_true")
    a = p.parse_args(argv)

    sec = tf_seconds(a.tf)
    interval, nat = native_for(sec)
    symbol = a.symbol or DEFAULT_SYMBOL[a.source]
    start = _parse_day(a.start)
    end = _parse_day(a.end) if a.end else datetime.now(timezone.utc)
    if end <= start:
        raise SystemExit(f"--end {end:%Y-%m-%d} is not after --start {start:%Y-%m-%d}")
    out = a.out or f"data/{symbol.replace('-', '')}_{a.tf}.csv"
    log = (lambda *_: None) if a.quiet else (lambda m: print(m, file=sys.stderr, flush=True))

    check_source(a.source, interval, a.tf)
    reqs, native_n, final_n, dl = estimate(a.source, interval, sec, start, end)
    log(f"{a.source}: {symbol} {a.tf} {start:%Y-%m-%d} -> {end:%Y-%m-%d}")
    if nat != sec:
        log(f"  no native {a.tf} bar; fetching {interval} and folding {sec // nat}:1")
    log(f"  ~{reqs:,} requests, ~{native_n:,} {interval} bars -> ~{final_n:,} {a.tf} bars, "
        f"~{_human(dl)} over the wire, streamed (nothing kept but the output)")
    if a.dry_run:
        return 0

    t0 = time.time()
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    tmp = f"{out}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(HEADER)
            f = Folder(sec, _ms(start), _ms(end),
                       sink=lambda r: w.writerow([r[1], f"{r[2]:.8g}", f"{r[3]:.8g}",
                                                  f"{r[4]:.8g}", f"{r[5]:.8g}", f"{r[6]:.8g}"]))
            for chunk in SOURCES[a.source](symbol, interval, start, end, log):
                f.feed(chunk)
            f.close()
    except Blocked as e:
        os.path.exists(tmp) and os.remove(tmp)
        print(f"\nEGRESS BLOCKED: {e}\n\n"
              "The proxy refused the connection, so the request never reached the exchange.\n"
              "The host is not on this environment's network allow-list. Either widen the\n"
              "policy (https://code.claude.com/docs/en/claude-code-on-the-web) or run this\n"
              "script on a machine with open egress and commit the CSV.", file=sys.stderr)
        return 2
    except BaseException:
        os.path.exists(tmp) and os.remove(tmp)   # a killed run leaves no half file behind
        raise

    if not f.n:
        os.remove(tmp)
        raise SystemExit("no bars in the requested window -- nothing written")
    os.replace(tmp, out)                   # atomic: the name appears only once it is complete
    log(f"\n{out}  ({_human(os.path.getsize(out))})")
    log(f"  {f.n:,} bars  {f.first} -> {f.last}  in {time.time() - t0:.1f}s")
    log(f"  {f.gaps:,} gaps (missing bars / venue downtime), {f.bad} OHLC violations")
    if f.backwards:
        log(f"  {f.backwards:,} rows dropped as duplicate or out-of-order "
            f"(expected where monthly and daily archives overlap)")
    if f.bad:
        log("  OHLC violations are a red flag: a real tape has none. Inspect before using.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
