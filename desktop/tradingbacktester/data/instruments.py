"""The instrument catalogue: contract specifications and their persistence.

Every cash figure the engine produces flows through three numbers on an
:class:`~tradingbacktester.data.models.Instrument` -- ``tick_size``,
``point_value`` and ``lot_size`` -- so the seeded defaults in this module are
worth getting exactly right.  A wrong ``point_value`` does not produce an
obviously broken backtest; it produces a plausible one with the P&L multiplied
by a constant, which is far harder to notice.

The registry is a plain JSON file the user owns.  Defaults are *seeded* on
first run and never re-imposed afterwards: if a user corrects a tick size or
adds their broker's real commission, the next release must not silently undo
it.  :meth:`InstrumentRegistry.reset_to_defaults` is the explicit way back.

Margin figures below are indicative exchange minimums (or, for spot FX and
metals, the sort of per-lot figure a 30:1 retail account is quoted).  Brokers
vary, sometimes by a factor of two, and exchanges change them without notice --
they are here so position sizing has a sane starting point, not because they
are authoritative.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator

from ..core.errors import DataError, StorageError
from ..core.types import AssetClass
from .models import Instrument

log = logging.getLogger(__name__)

#: Name of the catalogue file when the registry is pointed at a directory.
INSTRUMENTS_FILENAME = "instruments.json"

_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# The seeded catalogue
# ---------------------------------------------------------------------------
#
# Reading the table below:
#
#   tick_size    smallest price increment the exchange quotes
#   point_value  cash per 1.00 of price movement per unit held
#   lot_size     smallest tradeable quantity increment
#   tick value   = tick_size * point_value  (the number traders actually quote)
#
# Spot FX is expressed in *standard lots*: one unit of quantity is 100,000 of
# the base currency, so ``point_value`` is 100,000 and ``lot_size`` 0.01 makes
# a micro lot the smallest trade.  A 1-pip move (0.0001) on one lot is
# 0.0001 * 100000 = 10 units of the quote currency, which is the familiar
# "$10 a pip".

DEFAULT_INSTRUMENTS: tuple[Instrument, ...] = (
    # -- Spot FX -----------------------------------------------------------
    # Five-decimal pricing (fractional pips).  P&L accrues in the QUOTE
    # currency; for the three pairs quoted against USD that is already USD.
    Instrument(
        symbol="EURUSD", name="Euro / US Dollar", asset_class=AssetClass.FOREX,
        tick_size=0.00001, point_value=100000.0, lot_size=0.01, price_decimals=5,
        currency="USD", exchange="FX", timezone="America/New_York",
        margin_per_unit=3600.0, default_commission=3.5,
        default_spread_points=0.00006,
        notes="One unit is a standard lot of 100,000 EUR. A 1-pip (0.0001) move "
              "is worth 10 USD per lot. Margin shown is indicative of a 30:1 "
              "retail account; commission is a typical 3.50 USD per lot per side.",
    ),
    Instrument(
        symbol="GBPUSD", name="British Pound / US Dollar", asset_class=AssetClass.FOREX,
        tick_size=0.00001, point_value=100000.0, lot_size=0.01, price_decimals=5,
        currency="USD", exchange="FX", timezone="America/New_York",
        margin_per_unit=4300.0, default_commission=3.5,
        default_spread_points=0.00010,
        notes="One unit is a standard lot of 100,000 GBP. A 1-pip (0.0001) move "
              "is worth 10 USD per lot.",
    ),
    Instrument(
        symbol="AUDUSD", name="Australian Dollar / US Dollar", asset_class=AssetClass.FOREX,
        tick_size=0.00001, point_value=100000.0, lot_size=0.01, price_decimals=5,
        currency="USD", exchange="FX", timezone="America/New_York",
        margin_per_unit=2200.0, default_commission=3.5,
        default_spread_points=0.00008,
        notes="One unit is a standard lot of 100,000 AUD. A 1-pip (0.0001) move "
              "is worth 10 USD per lot.",
    ),
    # USDJPY is quoted to three decimals, so a "pip" is 0.01 and the tick is a
    # tenth of one.  The caveat that matters: point_value 100,000 means 100,000
    # *JPY* per 1.00 of price per lot, because the quote currency is JPY.  A
    # 1-pip (0.01) move on one lot is 1,000 JPY -- roughly 6.60 USD at 152.
    # This application does no FX conversion, so P&L for this symbol comes out
    # in JPY.  For a USD-denominated account either read the results as JPY, or
    # set point_value to 100000 / (USDJPY rate) to get an approximate USD
    # figure at a fixed exchange rate.
    Instrument(
        symbol="USDJPY", name="US Dollar / Japanese Yen", asset_class=AssetClass.FOREX,
        tick_size=0.001, point_value=100000.0, lot_size=0.01, price_decimals=3,
        currency="JPY", exchange="FX", timezone="America/New_York",
        margin_per_unit=3300.0, default_commission=3.5,
        default_spread_points=0.006,
        notes="One unit is a standard lot of 100,000 USD. Profit and loss is in "
              "JPY, not USD, because JPY is the quote currency: a 1-pip (0.01) "
              "move is 1,000 JPY per lot. No currency conversion is applied.",
    ),

    # -- Crypto ------------------------------------------------------------
    # One unit is one coin, so point_value is 1.0 and the whole contract
    # specification is just "price times quantity".  Crypto venues charge a
    # percentage of notional rather than a per-unit fee, so the per-unit
    # default commission is left at zero.
    Instrument(
        symbol="BTCUSD", name="Bitcoin / US Dollar", asset_class=AssetClass.CRYPTO,
        tick_size=0.01, point_value=1.0, lot_size=0.0001, price_decimals=2,
        currency="USD", exchange="CRYPTO", timezone="UTC",
        margin_per_unit=0.0, default_commission=0.0, default_spread_points=1.0,
        notes="One unit is one BTC and trading runs 24/7. Venue fees are a "
              "percentage of notional (typically 0.02%-0.10% per side): set the "
              "commission mode to percent of notional rather than using the "
              "per-unit default.",
    ),
    Instrument(
        symbol="ETHUSD", name="Ethereum / US Dollar", asset_class=AssetClass.CRYPTO,
        tick_size=0.01, point_value=1.0, lot_size=0.001, price_decimals=2,
        currency="USD", exchange="CRYPTO", timezone="UTC",
        margin_per_unit=0.0, default_commission=0.0, default_spread_points=0.1,
        notes="One unit is one ETH and trading runs 24/7. Venue fees are a "
              "percentage of notional; set the commission mode accordingly.",
    ),

    # -- US equities and ETFs ---------------------------------------------
    # One unit is one share, penny-quoted, so point_value is 1.0.  Regulation T
    # margin is a percentage of a price-dependent notional rather than a fixed
    # cash amount per share, so margin_per_unit stays 0.0 and the position
    # sizer falls back to its notional rules.
    Instrument(
        symbol="SPY", name="SPDR S&P 500 ETF Trust", asset_class=AssetClass.EQUITY,
        tick_size=0.01, point_value=1.0, lot_size=1.0, price_decimals=2,
        currency="USD", exchange="ARCA", timezone="America/New_York",
        margin_per_unit=0.0, default_commission=0.005, default_spread_points=0.01,
        notes="One unit is one share. Regular hours are 09:30-16:00 New York.",
    ),
    Instrument(
        symbol="QQQ", name="Invesco QQQ Trust", asset_class=AssetClass.EQUITY,
        tick_size=0.01, point_value=1.0, lot_size=1.0, price_decimals=2,
        currency="USD", exchange="NASDAQ", timezone="America/New_York",
        margin_per_unit=0.0, default_commission=0.005, default_spread_points=0.01,
        notes="One unit is one share. Regular hours are 09:30-16:00 New York.",
    ),
    Instrument(
        symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY,
        tick_size=0.01, point_value=1.0, lot_size=1.0, price_decimals=2,
        currency="USD", exchange="NASDAQ", timezone="America/New_York",
        margin_per_unit=0.0, default_commission=0.005, default_spread_points=0.01,
        notes="One unit is one share. Regular hours are 09:30-16:00 New York.",
    ),
    Instrument(
        symbol="TSLA", name="Tesla, Inc.", asset_class=AssetClass.EQUITY,
        tick_size=0.01, point_value=1.0, lot_size=1.0, price_decimals=2,
        currency="USD", exchange="NASDAQ", timezone="America/New_York",
        margin_per_unit=0.0, default_commission=0.005, default_spread_points=0.02,
        notes="One unit is one share. Regular hours are 09:30-16:00 New York.",
    ),

    # -- Futures -----------------------------------------------------------
    # CME Globex runs on Chicago time, and a bare hour/minute read off these
    # bars is Chicago time, which is why the timezone is America/Chicago even
    # for products (CL, GC) whose exchange sits in New York.
    Instrument(
        symbol="ES", name="E-mini S&P 500 Future", asset_class=AssetClass.FUTURES,
        tick_size=0.25, point_value=50.0, lot_size=1.0, price_decimals=2,
        currency="USD", exchange="CME", timezone="America/Chicago",
        margin_per_unit=13000.0, default_commission=2.25, default_spread_points=0.25,
        notes="One tick (0.25) is 12.50 USD; one point is 50 USD. Margin is an "
              "indicative exchange minimum and brokers vary.",
    ),
    Instrument(
        symbol="NQ", name="E-mini Nasdaq 100 Future", asset_class=AssetClass.FUTURES,
        tick_size=0.25, point_value=20.0, lot_size=1.0, price_decimals=2,
        currency="USD", exchange="CME", timezone="America/Chicago",
        margin_per_unit=23000.0, default_commission=2.25, default_spread_points=0.25,
        notes="One tick (0.25) is 5.00 USD; one point is 20 USD. Margin is an "
              "indicative exchange minimum and brokers vary.",
    ),
    Instrument(
        symbol="MNQ", name="Micro E-mini Nasdaq 100 Future", asset_class=AssetClass.FUTURES,
        tick_size=0.25, point_value=2.0, lot_size=1.0, price_decimals=2,
        currency="USD", exchange="CME", timezone="America/Chicago",
        margin_per_unit=2300.0, default_commission=0.52, default_spread_points=0.25,
        notes="One tenth of an NQ. One tick (0.25) is 0.50 USD; one point is "
              "2 USD. Margin is an indicative exchange minimum and brokers vary.",
    ),
    Instrument(
        symbol="CL", name="Crude Oil (WTI) Future", asset_class=AssetClass.FUTURES,
        tick_size=0.01, point_value=1000.0, lot_size=1.0, price_decimals=2,
        currency="USD", exchange="NYMEX", timezone="America/Chicago",
        margin_per_unit=6000.0, default_commission=2.25, default_spread_points=0.01,
        notes="1,000 barrels. One tick (0.01) is 10 USD; one dollar of crude is "
              "1,000 USD. Margin is indicative and moves with volatility.",
    ),
    Instrument(
        symbol="GC", name="Gold Future", asset_class=AssetClass.FUTURES,
        tick_size=0.1, point_value=100.0, lot_size=1.0, price_decimals=1,
        currency="USD", exchange="COMEX", timezone="America/Chicago",
        margin_per_unit=14000.0, default_commission=2.25, default_spread_points=0.1,
        notes="100 troy ounces. One tick (0.10) is 10 USD; one dollar of gold is "
              "100 USD. Margin is indicative and has moved a long way with the "
              "gold price.",
    ),

    # -- Spot metal --------------------------------------------------------
    # Spot gold is a CFD-style contract rather than an exchange product: one
    # unit is 100 troy ounces, matching GC, and 0.01 lots gets you down to a
    # single ounce.
    Instrument(
        symbol="XAUUSD", name="Spot Gold / US Dollar", asset_class=AssetClass.OTHER,
        tick_size=0.01, point_value=100.0, lot_size=0.01, price_decimals=2,
        currency="USD", exchange="OTC", timezone="America/New_York",
        margin_per_unit=10000.0, default_commission=0.0, default_spread_points=0.25,
        notes="One unit is 100 troy ounces, so a 1.00 move in the gold price is "
              "100 USD per lot and the minimum 0.01 lot is one ounce. Margin is "
              "indicative of a retail account and brokers vary widely.",
    ),
)


def default_instruments() -> list[Instrument]:
    """Fresh copies of :data:`DEFAULT_INSTRUMENTS`.

    Copies, because :class:`Instrument` is a mutable dataclass: handing out the
    module-level objects would let one edit in the UI rewrite the defaults for
    the rest of the process.
    """
    return [copy.deepcopy(inst) for inst in DEFAULT_INSTRUMENTS]


def default_instrument_for(symbol: str) -> Instrument | None:
    """The seeded specification for ``symbol``, or ``None`` if it is not one."""
    key = str(symbol).strip().upper()
    for inst in DEFAULT_INSTRUMENTS:
        if inst.symbol == key:
            return copy.deepcopy(inst)
    return None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class InstrumentRegistry:
    """The user's instrument catalogue, backed by one JSON file.

    Parameters
    ----------
    path:
        The catalogue file.  A directory is accepted too and is taken to mean
        ``<directory>/instruments.json``, which is what the workspace layout
        hands over.
    seed:
        Write :data:`DEFAULT_INSTRUMENTS` when the file does not exist yet.
        Turned off in tests that want an empty catalogue.
    """

    def __init__(self, path: str | Path, seed: bool = True) -> None:
        p = Path(path).expanduser()
        # A directory is the common mistake and the common convenience: the
        # caller usually has ``workspace.settings`` to hand rather than a file.
        if p.is_dir() or (not p.suffix and not p.exists()):
            p = p / INSTRUMENTS_FILENAME
        self.path: Path = p
        self._items: dict[str, Instrument] = {}
        self._seed_on_missing = bool(seed)
        self.load()

    # -- container behaviour ---------------------------------------------

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Instrument]:
        return iter(self.all())

    def __contains__(self, symbol: object) -> bool:
        return str(symbol).strip().upper() in self._items

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"<InstrumentRegistry {len(self._items)} instruments at {self.path}>"

    # -- reading -----------------------------------------------------------

    def all(self) -> list[Instrument]:
        """Every instrument, sorted by asset class then symbol for the UI."""
        order = {cls: i for i, cls in enumerate(AssetClass)}
        return sorted(self._items.values(),
                      key=lambda inst: (order.get(inst.asset_class, 99), inst.symbol))

    def symbols(self) -> list[str]:
        """Every symbol, alphabetically."""
        return sorted(self._items)

    def get(self, symbol: str) -> Instrument:
        """Look up one instrument, case-insensitively.

        Raises
        ------
        DataError
            When the symbol is not in the catalogue.  The message suggests
            near matches, because the usual cause is a typo or a vendor suffix
            such as ``EURUSD.pro``.
        """
        key = str(symbol).strip().upper()
        if key in self._items:
            return self._items[key]
        near = [s for s in self.symbols() if key and (key in s or s in key)]
        hint = f" Did you mean {', '.join(near[:5])}?" if near else ""
        raise DataError(
            f"There is no instrument called '{symbol}' in the catalogue.{hint}",
            detail=f"known={self.symbols()}",
        )

    def find(self, symbol: str) -> Instrument | None:
        """Like :meth:`get` but returns ``None`` instead of raising."""
        return self._items.get(str(symbol).strip().upper())

    def ensure(self, symbol: str,
               asset_class: AssetClass = AssetClass.OTHER,
               **overrides: Any) -> Instrument:
        """Return the instrument for ``symbol``, creating a default one if needed.

        CSV import needs this: a user drops in ``FDAX.csv`` and something has to
        stand in for it before they have had a chance to fill in a tick size.
        A newly created instrument is added to the catalogue and saved.
        """
        existing = self.find(symbol)
        if existing is not None:
            return existing
        seeded = default_instrument_for(symbol)
        inst = seeded if seeded is not None else Instrument.with_defaults(
            symbol, asset_class, **overrides)
        if seeded is not None and overrides:
            for key, value in overrides.items():
                setattr(inst, key, value)
        self.add(inst)
        return inst

    # -- writing -----------------------------------------------------------

    def add(self, inst: Instrument) -> Instrument:
        """Add a new instrument.

        Raises
        ------
        DataError
            If the symbol is already in the catalogue -- overwriting silently
            would lose whatever the user had configured for it.
        """
        if not isinstance(inst, Instrument):  # pragma: no cover - defensive
            raise DataError("Only an instrument can be added to the catalogue.")
        if inst.symbol in self._items:
            raise DataError(
                f"{inst.symbol} is already in the instrument catalogue. "
                f"Edit the existing entry instead of adding a second one.")
        self._items[inst.symbol] = inst
        self.save()
        return inst

    def update(self, inst: Instrument) -> Instrument:
        """Replace an existing instrument, matched on symbol.

        Raises
        ------
        DataError
            If the symbol is unknown; use :meth:`add` for a new instrument or
            :meth:`upsert` when either is acceptable.
        """
        if inst.symbol not in self._items:
            raise DataError(
                f"{inst.symbol} is not in the instrument catalogue, so there is "
                f"nothing to update.")
        self._items[inst.symbol] = inst
        self.save()
        return inst

    def upsert(self, inst: Instrument) -> Instrument:
        """Add or replace, whichever applies."""
        self._items[inst.symbol] = inst
        self.save()
        return inst

    def remove(self, symbol: str) -> None:
        """Delete an instrument from the catalogue."""
        key = str(symbol).strip().upper()
        if key not in self._items:
            raise DataError(
                f"There is no instrument called '{symbol}' to remove.")
        del self._items[key]
        self.save()

    def rename(self, symbol: str, new_symbol: str) -> Instrument:
        """Change an instrument's symbol, keeping every other field."""
        inst = self.get(symbol)
        new_key = str(new_symbol).strip().upper()
        if not new_key:
            raise DataError("An instrument needs a symbol.")
        if new_key != inst.symbol and new_key in self._items:
            raise DataError(f"{new_key} is already in the instrument catalogue.")
        del self._items[inst.symbol]
        inst.symbol = new_key
        self._items[new_key] = inst
        self.save()
        return inst

    def reset_to_defaults(self) -> list[Instrument]:
        """Throw the catalogue away and seed it again.  The user must ask for this."""
        self._items = {inst.symbol: inst for inst in default_instruments()}
        self.save()
        log.info("Instrument catalogue reset to %d defaults", len(self._items))
        return self.all()

    # -- persistence -------------------------------------------------------

    def load(self) -> list[Instrument]:
        """Read the catalogue from disk, seeding defaults when there is none.

        A damaged file is moved aside rather than deleted -- a user who has
        spent an afternoon entering contract specifications should be able to
        pick the pieces out of it -- and the defaults are seeded in its place
        so the application still starts.
        """
        if not self.path.exists():
            if self._seed_on_missing:
                self._items = {inst.symbol: inst for inst in default_instruments()}
                self.save()
                log.info("Seeded %d default instruments into %s",
                         len(self._items), self.path)
            else:
                self._items = {}
            return self.all()

        try:
            raw = self.path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            self._quarantine(exc)
            self._items = {inst.symbol: inst for inst in default_instruments()}
            return self.all()

        records = payload.get("instruments") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            self._quarantine(TypeError(f"expected a list, got {type(records).__name__}"))
            self._items = {inst.symbol: inst for inst in default_instruments()}
            return self.all()

        items: dict[str, Instrument] = {}
        skipped = 0
        for record in records:
            if not isinstance(record, dict):
                skipped += 1
                continue
            try:
                inst = Instrument.from_dict(record)
            except (DataError, TypeError, ValueError, KeyError) as exc:
                # One bad row must not cost the user the other ninety-nine.
                skipped += 1
                log.warning("Skipping unreadable instrument record %r: %s", record, exc)
                continue
            items[inst.symbol] = inst
        if skipped:
            log.warning("%d instrument record(s) in %s could not be read and were "
                        "ignored", skipped, self.path)
        self._items = items
        return self.all()

    def save(self) -> None:
        """Write the catalogue atomically.

        Temp file in the same directory then :func:`os.replace`, so a crash
        mid-write leaves the previous catalogue intact rather than a truncated
        one.  ``os.replace`` is atomic on Windows as well as POSIX, which
        ``Path.rename`` is not when the destination exists.
        """
        payload = {
            "schema": _SCHEMA_VERSION,
            "instruments": [inst.to_dict() for inst in self.all()],
        }
        text = json.dumps(payload, indent=2, sort_keys=False)
        _atomic_write_text(self.path, text)

    def _quarantine(self, exc: BaseException) -> None:
        """Move a damaged catalogue aside so the app can still start."""
        broken = self.path.with_suffix(self.path.suffix + ".corrupt")
        try:
            if broken.exists():
                broken.unlink()
            self.path.replace(broken)
            log.error("The instrument catalogue at %s could not be read (%s); it "
                      "has been moved to %s and the defaults restored",
                      self.path, exc, broken.name)
        except OSError as move_exc:  # pragma: no cover - unusual filesystem state
            log.error("The instrument catalogue at %s could not be read (%s) and "
                      "could not be moved aside (%s); the defaults were used",
                      self.path, exc, move_exc)


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically, raising :class:`StorageError` on failure."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                                        dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            # Never leave a stray .tmp behind for the user to wonder about.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        raise StorageError(
            f"The file {path.name} could not be saved to {path.parent}.\n\n"
            f"Check that the folder exists and that you have permission to "
            f"write to it.",
            detail=repr(exc),
        ) from exc
