"""A LEAN algorithm implementing this repository's validated initial-balance geometry.

Drop in as `main.py` of a `lean init` project. NOT RUN in this repository -- see lean_export.py for
why (no Docker daemon, no dotnet). It is written to be readable against the Pine and TypeScript
versions of the same rule rather than to be clever.

The geometry is the one configuration in this project that survived its own battery: initial
balance 09:30-10:30, entry on a 50% retracement of the opening range after a break, stop at 80% of
the range, a fixed 1:2 target, both sides, flat at 11:59. On NQ 2022-25 that produced E = 0.325R at
t = 3.84, holding 0.414 research against 0.116 holdout, and surviving a 10,000-path stationary
block bootstrap at 95% CI [+0.161, +0.490].

Re-optimising it destroyed value: over identical out-of-sample bars, rolling re-optimisation earned
$14,580 against the fixed geometry's $27,253. So the parameters below are FIXED on purpose. If you
are tempted to tune them, read docs/ib/STUDY_SEARCH_CURVE.md first.
"""
from AlgorithmImports import *   # noqa: F403  (LEAN injects its namespace)


class InitialBalanceRetracement(QCAlgorithm):

    # --- fixed geometry: see the module docstring before changing any of these ---
    IB_START_MIN = 9 * 60 + 30
    IB_END_MIN = 10 * 60 + 30
    FLAT_MIN = 11 * 60 + 59
    RETRACE_PCT = 0.50
    STOP_PCT = 0.80
    TARGET_R = 2.0

    def Initialize(self):
        self.SetStartDate(2022, 12, 27)
        self.SetEndDate(2025, 12, 11)
        self.SetCash(100_000)

        future = self.AddFuture(Futures.Indices.NASDAQ100EMini, Resolution.Minute)
        future.SetFilter(0, 90)
        self.symbol = None

        self.ib_high = None
        self.ib_low = None
        self.day = None
        self.traded_today = False
        self.entry = None
        self.stop = None
        self.target = None

    def _minutes(self, t):
        return t.hour * 60 + t.minute

    def OnData(self, slice: Slice):
        for chain in slice.FutureChains.Values:
            contracts = sorted(chain.Value, key=lambda c: c.Expiry)
            if contracts:
                self.symbol = contracts[0].Symbol
        if self.symbol is None or not slice.Bars.ContainsKey(self.symbol):
            return

        bar = slice.Bars[self.symbol]
        now = self.Time
        m = self._minutes(now)

        if self.day != now.date():
            self.day = now.date()
            self.ib_high = self.ib_low = None
            self.traded_today = False

        # --- build the initial balance ---
        if self.IB_START_MIN <= m < self.IB_END_MIN:
            self.ib_high = bar.High if self.ib_high is None else max(self.ib_high, bar.High)
            self.ib_low = bar.Low if self.ib_low is None else min(self.ib_low, bar.Low)
            return

        if self.ib_high is None or self.ib_low is None:
            return

        # --- flat at 11:59, unconditionally ---
        if m >= self.FLAT_MIN:
            if self.Portfolio[self.symbol].Invested:
                self.Liquidate(self.symbol)
            return

        rng = self.ib_high - self.ib_low
        if rng <= 0 or self.traded_today:
            return

        if self.Portfolio[self.symbol].Invested:
            return

        # --- a CLOSE beyond the level arms the retracement entry; the limit does the rest ---
        if bar.Close > self.ib_high:
            side, edge = 1, self.ib_high
        elif bar.Close < self.ib_low:
            side, edge = -1, self.ib_low
        else:
            return

        entry = edge - side * rng * self.RETRACE_PCT
        stop = edge - side * rng * self.STOP_PCT
        risk = abs(entry - stop)
        if risk <= 0:
            return
        target = entry + side * risk * self.TARGET_R

        self.traded_today = True
        qty = 1 if side == 1 else -1
        ticket = self.LimitOrder(self.symbol, qty, entry)
        self.StopMarketOrder(self.symbol, -qty, stop)
        self.LimitOrder(self.symbol, -qty, target)
        self.Debug(f"{now} side={side} entry={entry:.2f} stop={stop:.2f} target={target:.2f}")
