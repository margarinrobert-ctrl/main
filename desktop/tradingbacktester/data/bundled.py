"""Market data shipped with the application.

These are real files, not generated ones, and they are the reason the app has
something to work on the moment it opens.  Each entry names the instrument and
timeframe explicitly rather than letting them be inferred, because a file name
is not evidence: ``5m_data.csv`` says nothing about what was trading.

The files live in ``data/market`` beside the package and are gzipped; the CSV
importer reads ``.csv.gz`` directly, so there is no unpacking step.  When the
application is frozen by PyInstaller they are collected into the bundle, so
``directory()`` resolves through ``sys._MEIPASS``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from ..core.types import AssetClass


@dataclass(frozen=True)
class BundledDataset:
    """One shipped data file and everything needed to import it correctly."""

    filename: str
    symbol: str
    timeframe: str
    description: str
    timezone: str = "UTC"
    asset_class: AssetClass = AssetClass.OTHER

    @property
    def name(self) -> str:
        """The dataset name shown in the app."""
        return f"{self.symbol} {self.timeframe}"

    def path(self) -> Path:
        return directory() / self.filename

    def exists(self) -> bool:
        return self.path().is_file()


#: Everything shipped, in the order it should appear.
BUNDLED: tuple[BundledDataset, ...] = (
    BundledDataset(
        "US30_5m.csv.gz", "US30", "5m",
        "Dow Jones index CFD, 5-minute bars, October 2016 to July 2025 "
        "(581,195 bars). MetaTrader export; real volume is in TickVolume.",
        timezone="UTC", asset_class=AssetClass.INDEX_CFD),
    BundledDataset(
        "US30_15m.csv.gz", "US30", "15m",
        "Dow Jones index CFD, 15-minute bars, October 2016 to July 2025 "
        "(193,942 bars).",
        timezone="UTC", asset_class=AssetClass.INDEX_CFD),
    BundledDataset(
        "US30_30m.csv.gz", "US30", "30m",
        "Dow Jones index CFD, 30-minute bars, July 2024 to July 2025 "
        "(11,445 bars).",
        timezone="UTC", asset_class=AssetClass.INDEX_CFD),
    BundledDataset(
        "BTCUSD_1d.csv.gz", "BTCUSD", "1D",
        "Bitcoin daily bars from CoinMarketCap, July 2025 to August 2026 "
        "(397 bars). Short: enough to chart, not enough to judge a strategy.",
        timezone="UTC", asset_class=AssetClass.CRYPTO),
)


def directory() -> Path:
    """Where the shipped data files are, running from source or frozen."""
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen) / "data" / "market"
    # tradingbacktester/data/bundled.py -> desktop/data/market
    return Path(__file__).resolve().parents[2] / "data" / "market"


def available() -> list[BundledDataset]:
    """The shipped datasets whose files are actually present."""
    return [d for d in BUNDLED if d.exists()]


def find(name: str) -> BundledDataset | None:
    """Look one up by dataset name, symbol+timeframe, or file name."""
    wanted = str(name).strip().lower()
    for dataset in BUNDLED:
        if wanted in (dataset.name.lower(), dataset.filename.lower(),
                      f"{dataset.symbol}{dataset.timeframe}".lower()):
            return dataset
    return None
