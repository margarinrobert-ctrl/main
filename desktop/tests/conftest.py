"""Shared fixtures.

Bars are built by hand rather than generated so that every expected value in a
test can be worked out on paper.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tradingbacktester.core.timeframe import Timeframe  # noqa: E402
from tradingbacktester.core.types import AssetClass  # noqa: E402
from tradingbacktester.data.models import BarSeries, Instrument  # noqa: E402

#: 2023-01-02 00:00:00 UTC, a Monday, in nanoseconds.
EPOCH_NS = 1_672_617_600_000_000_000


def make_bars(closes, highs=None, lows=None, opens=None, volumes=None,
              instrument: Instrument | None = None,
              timeframe: str = "1h", start_ts: int = EPOCH_NS) -> BarSeries:
    """Build a BarSeries from plain lists, filling anything not supplied.

    When only closes are given, each bar opens at the previous close and its
    high/low just contain the body, which keeps hand-computed expectations
    simple.
    """
    close = np.asarray(closes, dtype="float64")
    n = len(close)
    open_ = (np.asarray(opens, dtype="float64") if opens is not None
             else np.concatenate([[close[0]], close[:-1]]))
    high = (np.asarray(highs, dtype="float64") if highs is not None
            else np.maximum(open_, close))
    low = (np.asarray(lows, dtype="float64") if lows is not None
           else np.minimum(open_, close))
    volume = (np.asarray(volumes, dtype="float64") if volumes is not None
              else np.full(n, 1000.0))
    tf = Timeframe.parse(timeframe)
    step = int(tf.approx_seconds * 1_000_000_000)
    ts = start_ts + np.arange(n, dtype="int64") * step
    inst = instrument or Instrument(
        symbol="TEST", asset_class=AssetClass.OTHER, tick_size=0.01,
        point_value=1.0, lot_size=1.0, price_decimals=2, currency="USD",
        timezone="UTC")
    return BarSeries(ts=ts, open=open_, high=high, low=low, close=close,
                     volume=volume, instrument=inst, timeframe=tf,
                     source="unit-test")


@pytest.fixture
def simple_instrument() -> Instrument:
    """Point value 1.0 so cash P&L equals price movement times quantity."""
    return Instrument(symbol="TEST", tick_size=0.01, point_value=1.0,
                      lot_size=1.0, price_decimals=2, timezone="UTC")


@pytest.fixture
def futures_instrument() -> Instrument:
    """Point value 20.0, like an E-mini Nasdaq contract."""
    return Instrument(symbol="NQ", asset_class=AssetClass.FUTURES,
                      tick_size=0.25, point_value=20.0, lot_size=1.0,
                      price_decimals=2, timezone="America/Chicago")


@pytest.fixture
def rising_bars(simple_instrument) -> BarSeries:
    """100, 101, ... 149 -- a clean uptrend."""
    return make_bars(list(np.arange(100.0, 150.0)), instrument=simple_instrument)


@pytest.fixture
def flat_bars(simple_instrument) -> BarSeries:
    """Fifty identical bars.  Every ratio metric has a degenerate denominator."""
    return make_bars([100.0] * 50, instrument=simple_instrument)


@pytest.fixture
def random_bars(simple_instrument) -> BarSeries:
    """A seeded random walk with valid OHLC relationships."""
    rng = np.random.default_rng(20240101)
    n = 600
    close = 100.0 + np.cumsum(rng.normal(0.0, 1.0, n))
    open_ = np.concatenate([[100.0], close[:-1]])
    high = np.maximum(open_, close) + rng.random(n)
    low = np.minimum(open_, close) - rng.random(n)
    volume = rng.integers(500, 5000, n).astype("float64")
    return make_bars(close, high, low, open_, volume, instrument=simple_instrument)


@pytest.fixture(scope="session")
def qapp():
    """A single QApplication for every GUI test in the session."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from tradingbacktester.ui.theme import apply_theme

    apply_theme(app)
    return app
