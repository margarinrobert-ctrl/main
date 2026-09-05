"""Data, clock and costs for the US100 morning-session lab.

THE CLOCK (brief section 1 and 2). The brief says not to use a fixed UTC offset because of
daylight saving. The subtlety in THIS file is that its stamps are not UTC: they are a broker wall
clock that itself follows US daylight saving. `verify_clock()` re-measures that rather than
trusting it -- it locates the 09:30 New York volume step separately in winter and summer months
and reports the file-clock hour of each. Both land on the same hour, so the file clock and New
York shift together and a constant -7h maps one to the other all year. If a future file failed
that check the function says so and the fixed shift must not be used.

THE INSTRUMENT (brief section 1). This is US100 CFD data from an MT-style export, and it is kept
distinct from the NQ futures series in this repo. They are NOT interchangeable: the stored NQ
price levels are synthetic (see `research/us100.py`), the two have different sessions, and this
file's `Volume` column is identically zero so `TickVolume` -- a broker tick COUNT, not centralised
exchange volume -- is the only activity proxy. Every volume feature here is labelled `tick_` for
that reason.

COSTS (brief sections 37 and 38). Retail US100 CFD pricing is a broker CHOICE, not something this
file can measure: OHLC bars carry no spread. The defaults below are a mid-range retail assumption
and are stated as an assumption everywhere they are used. Results are reported in R, where the
cost is charged as a fraction of the stop distance, because that is where a scalping brief lives
or dies -- a 2-point round trip against a 10-point stop is 20% of R.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import us100

NY = "America/New_York"


# --------------------------------------------------------------------------- costs
@dataclass(frozen=True)
class Costs:
    """Round-trip cost model in INDEX POINTS. Broker-dependent; see module docstring."""
    spread_rth: float = 1.0        # points, quoted spread 09:30-16:00 New York
    spread_pre: float = 2.0        # points, 07:00-09:30 -- thinner book, wider quote
    spread_off: float = 3.0        # points, outside 07:00-16:00
    slip_entry: float = 0.25       # points, market-order entry
    slip_stop: float = 0.75        # points, stops are marketable and gap through
    slip_target: float = 0.0       # points, a resting limit does not slip
    commission: float = 0.0        # points-equivalent per round turn (0 = spread-only broker)

    def spread_at(self, mod: np.ndarray) -> np.ndarray:
        """Half-spread paid per side, by minute-of-day in New York."""
        s = np.full(len(mod), self.spread_off)
        s[(mod >= 420) & (mod < 570)] = self.spread_pre
        s[(mod >= 570) & (mod < 960)] = self.spread_rth
        return s / 2.0


PESSIMISTIC = Costs(spread_rth=1.5, spread_pre=3.0, spread_off=4.0,
                    slip_entry=0.5, slip_stop=1.5, commission=0.2)
OPTIMISTIC = Costs(spread_rth=0.6, spread_pre=1.0, spread_off=1.5,
                   slip_entry=0.1, slip_stop=0.3)


# --------------------------------------------------------------------------- clock
def verify_clock(path=None, verbose=True):
    """Check the constant -7h shift lands the RTH open at 09:xx New York in BOTH seasons.

    `us100.load` has already applied the shift, so this measures the result: where the 09:30
    activity step falls on the shifted clock, computed separately for Dec-Feb and Jun-Aug. Both
    must read 9. If the broker clock did NOT follow US daylight saving, one season would land an
    hour off and the constant shift would be wrong for half of every year.

    Returns (ok, winter_hour, summer_hour, offset).
    """
    raw = us100.load(path)
    tv = raw["v"].to_numpy(float)
    idx = raw.index
    hour = idx.hour.to_numpy()
    month = idx.month.to_numpy()
    out = {}
    for tag, sel in (("winter", np.isin(month, (12, 1, 2))), ("summer", np.isin(month, (6, 7, 8)))):
        by = np.array([tv[sel & (hour == h)].mean() if (sel & (hour == h)).any() else 0.0
                       for h in range(24)])
        step = np.argmax(np.diff(by))          # hour BEFORE the largest jump in activity
        out[tag] = int(step) + 1
    ok = out["winter"] == out["summer"]
    if verbose:
        print(f"clock check: after the -{us100.NY_OFFSET_H}h shift the RTH activity step lands at "
              f"hour {out['winter']} (Dec-Feb) and {out['summer']} (Jun-Aug)")
        ok9 = ok and out["winter"] == 9
        print(f"  -> {'CONSISTENT and at 09:xx New York' if ok9 else 'MISMATCH'}; the constant "
              f"shift is {'valid year round' if ok9 else 'NOT valid -- re-derive per season'}")
    return ok, out["winter"], out["summer"], us100.NY_OFFSET_H


def bars(tf=15, path=None):
    """Bars on the New York clock with the standard dict shape plus a DatetimeIndex."""
    d = us100.to_bars(tf, path)
    ix = pd.DatetimeIndex(d["df"].index)
    d["idx"] = ix
    d["day"] = ix.normalize().values.astype("datetime64[D]").astype(np.int64)
    return d


def audit(tf=15, path=None):
    """Brief section 1: data-quality report, printed rather than silently assumed."""
    raw = us100.load(path)
    ix = raw.index
    gaps = np.diff(ix.view(np.int64)) // 60_000_000_000
    o, h, l, c = (raw[k].to_numpy(float) for k in "ohlc")
    print(f"rows                 {len(raw):,}   {ix[0]} -> {ix[-1]}")
    print(f"duplicate stamps     {int(ix.duplicated().sum())}")
    print(f"OHLC violations      {int(((h < l) | (h < o) | (h < c) | (l > o) | (l > c)).sum())}")
    print(f"non-positive prices  {int((np.minimum.reduce([o, h, l, c]) <= 0).sum())}")
    print(f"zero-range bars      {100.0 * float((h == l).mean()):.2f}%")
    print(f"off-grid gaps        {100.0 * float((gaps != tf).mean()):.2f}%  "
          f"({int((gaps > 120).sum())} over two hours)")
    print(f"activity proxy       TickVolume (broker tick COUNT, not exchange volume); the "
          f"file's Volume column is identically zero")
    return raw
