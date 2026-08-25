"""Instruments and bar series.

:class:`BarSeries` is the single in-memory representation of market data used by
every other layer.  It stores columns as contiguous ``float64``/``int64`` NumPy
arrays rather than a DataFrame so the engine can index them in a tight loop
without paying pandas' per-access overhead, and so indicator code can be written
as plain vectorised NumPy.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Iterator

import numpy as np

from ..core.errors import DataError, InsufficientDataError
from ..core.timeframe import Timeframe, TimeframeUnit, infer_timeframe
from ..core.types import AssetClass

# Default per-asset-class characteristics used when a user creates an
# instrument without filling everything in.
_ASSET_DEFAULTS: dict[AssetClass, dict[str, Any]] = {
    AssetClass.FOREX: dict(tick_size=0.00001, point_value=100000.0, lot_size=0.01,
                           price_decimals=5, currency="USD"),
    AssetClass.CRYPTO: dict(tick_size=0.01, point_value=1.0, lot_size=0.0001,
                            price_decimals=2, currency="USD"),
    AssetClass.EQUITY: dict(tick_size=0.01, point_value=1.0, lot_size=1.0,
                            price_decimals=2, currency="USD"),
    AssetClass.FUTURES: dict(tick_size=0.25, point_value=20.0, lot_size=1.0,
                             price_decimals=2, currency="USD"),
    AssetClass.INDEX_CFD: dict(tick_size=0.1, point_value=1.0, lot_size=0.1,
                               price_decimals=2, currency="USD"),
    AssetClass.OTHER: dict(tick_size=0.01, point_value=1.0, lot_size=1.0,
                           price_decimals=2, currency="USD"),
}


@dataclass
class Instrument:
    """A tradeable symbol and the contract details the engine needs.

    ``point_value`` is the cash change in the account per 1.0 of price movement
    per unit held.  For a share it is 1.0; for an NQ future it is 20.0; for a
    1-lot of EURUSD quoted in USD it is 100000.0.
    """

    symbol: str
    name: str = ""
    asset_class: AssetClass = AssetClass.OTHER
    tick_size: float = 0.01
    point_value: float = 1.0
    lot_size: float = 1.0
    """Smallest tradeable increment of quantity."""
    price_decimals: int = 2
    currency: str = "USD"
    exchange: str = ""
    timezone: str = "UTC"
    """Timezone the instrument's session times are expressed in."""
    margin_per_unit: float = 0.0
    default_commission: float = 0.0
    default_spread_points: float = 0.0
    notes: str = ""

    def __post_init__(self) -> None:
        if not str(self.symbol).strip():
            raise DataError("An instrument needs a symbol.")
        self.symbol = str(self.symbol).strip().upper()
        if not self.name:
            self.name = self.symbol
        if self.tick_size <= 0:
            raise DataError(f"Tick size for {self.symbol} must be greater than zero.")
        if self.point_value <= 0:
            raise DataError(f"Point value for {self.symbol} must be greater than zero.")
        if self.lot_size <= 0:
            raise DataError(f"Lot size for {self.symbol} must be greater than zero.")

    @classmethod
    def with_defaults(cls, symbol: str, asset_class: AssetClass = AssetClass.OTHER,
                      **overrides: Any) -> "Instrument":
        """Build an instrument using the conventional values for its asset class."""
        base = dict(_ASSET_DEFAULTS[asset_class])
        base.update(overrides)
        return cls(symbol=symbol, asset_class=asset_class, **base)

    def round_price(self, price: float) -> float:
        """Snap a price to the instrument's tick grid."""
        if self.tick_size <= 0:
            return float(price)
        return float(round(price / self.tick_size) * self.tick_size)

    def round_quantity(self, qty: float) -> float:
        """Round a quantity *down* to a whole number of lots."""
        if self.lot_size <= 0:
            return float(qty)
        lots = np.floor(abs(qty) / self.lot_size + 1e-9)
        return float(np.sign(qty) * lots * self.lot_size)

    def format_price(self, price: float) -> str:
        if price is None or (isinstance(price, float) and np.isnan(price)):
            return "-"
        return f"{price:,.{self.price_decimals}f}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["asset_class"] = self.asset_class.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Instrument":
        d = dict(d)
        d["asset_class"] = AssetClass(d.get("asset_class", "other"))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class BarSeries:
    """OHLCV bars for one instrument at one timeframe.

    All arrays are the same length and share the same index.  ``ts`` holds UTC
    timestamps in nanoseconds since the epoch, sorted strictly ascending, and it
    marks the bar's **opening** time.
    """

    ts: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    instrument: Instrument
    timeframe: Timeframe
    source: str = ""
    """Where the bars came from -- a file path, a provider name, or 'synthetic'."""
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.ts = np.ascontiguousarray(self.ts, dtype="int64")
        for name in ("open", "high", "low", "close", "volume"):
            setattr(self, name, np.ascontiguousarray(getattr(self, name), dtype="float64"))
        n = len(self.ts)
        for name in ("open", "high", "low", "close", "volume"):
            if len(getattr(self, name)) != n:
                raise DataError(
                    "The OHLCV columns of this dataset have different lengths.",
                    detail=f"ts={n} {name}={len(getattr(self, name))}",
                )

    # -- basics ----------------------------------------------------------

    def __len__(self) -> int:
        return len(self.ts)

    def __iter__(self) -> Iterator[tuple[int, float, float, float, float, float]]:
        for i in range(len(self.ts)):
            yield (int(self.ts[i]), float(self.open[i]), float(self.high[i]),
                   float(self.low[i]), float(self.close[i]), float(self.volume[i]))

    @property
    def is_empty(self) -> bool:
        return len(self.ts) == 0

    @property
    def start_ts(self) -> int:
        if self.is_empty:
            raise InsufficientDataError("This dataset has no bars.")
        return int(self.ts[0])

    @property
    def end_ts(self) -> int:
        if self.is_empty:
            raise InsufficientDataError("This dataset has no bars.")
        return int(self.ts[-1])

    @property
    def hlc3(self) -> np.ndarray:
        """Typical price -- the source CCI and several other indicators use."""
        return (self.high + self.low + self.close) / 3.0

    @property
    def hl2(self) -> np.ndarray:
        return (self.high + self.low) / 2.0

    @property
    def ohlc4(self) -> np.ndarray:
        return (self.open + self.high + self.low + self.close) / 4.0

    def source_array(self, field_name: str) -> np.ndarray:
        """Resolve a price-source name such as ``"close"`` or ``"hlc3"``."""
        f = str(field_name).lower()
        direct = {"open": self.open, "high": self.high, "low": self.low,
                  "close": self.close, "volume": self.volume,
                  "hlc3": self.hlc3, "hl2": self.hl2, "ohlc4": self.ohlc4}
        if f in direct:
            return direct[f]
        raise DataError(f"'{field_name}' is not a price source this application knows.")

    # -- slicing ---------------------------------------------------------

    def slice(self, start: int = 0, stop: int | None = None) -> "BarSeries":
        """A new series over the half-open bar index range ``[start, stop)``."""
        stop = len(self) if stop is None else stop
        return BarSeries(
            ts=self.ts[start:stop], open=self.open[start:stop], high=self.high[start:stop],
            low=self.low[start:stop], close=self.close[start:stop],
            volume=self.volume[start:stop], instrument=self.instrument,
            timeframe=self.timeframe, source=self.source, meta=dict(self.meta),
        )

    def slice_time(self, start_ts: int | None, end_ts: int | None) -> "BarSeries":
        """A new series restricted to a UTC nanosecond time range, both bounds inclusive."""
        lo = 0 if start_ts is None else int(np.searchsorted(self.ts, start_ts, side="left"))
        hi = len(self) if end_ts is None else int(np.searchsorted(self.ts, end_ts, side="right"))
        if hi <= lo:
            raise InsufficientDataError(
                "The selected date range contains no bars.",
                detail=f"start_ts={start_ts} end_ts={end_ts} bars={len(self)}",
            )
        return self.slice(lo, hi)

    def index_at_or_after(self, ts: int) -> int:
        return int(np.searchsorted(self.ts, ts, side="left"))

    # -- construction ----------------------------------------------------

    @classmethod
    def from_arrays(cls, ts, open_, high, low, close, volume,
                    instrument: Instrument, timeframe: Timeframe | None = None,
                    source: str = "") -> "BarSeries":
        ts = np.ascontiguousarray(ts, dtype="int64")
        tf = timeframe or (infer_timeframe(ts) if len(ts) >= 2
                           else Timeframe(1, TimeframeUnit.DAY))
        return cls(ts=ts, open=open_, high=high, low=low, close=close, volume=volume,
                   instrument=instrument, timeframe=tf, source=source)

    def to_dataframe(self):
        """A pandas DataFrame with a tz-aware UTC DatetimeIndex.  For export only."""
        import pandas as pd

        return pd.DataFrame(
            {"open": self.open, "high": self.high, "low": self.low,
             "close": self.close, "volume": self.volume},
            index=pd.DatetimeIndex(pd.to_datetime(self.ts, utc=True), name="datetime"),
        )

    def describe(self) -> str:
        if self.is_empty:
            return f"{self.instrument.symbol} {self.timeframe.label}: empty"
        import pandas as pd

        a = pd.Timestamp(self.start_ts, tz="UTC")
        b = pd.Timestamp(self.end_ts, tz="UTC")
        return (f"{self.instrument.symbol} {self.timeframe.label}: {len(self):,} bars, "
                f"{a:%Y-%m-%d %H:%M} to {b:%Y-%m-%d %H:%M} UTC")
