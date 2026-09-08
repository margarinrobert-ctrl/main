"""Position sizing and margin arithmetic.

One class, :class:`PositionSizer`, answers a single question: *given the account
and the trade I am about to take, how many units may I buy or sell?*  It never
raises for an ordinary "you cannot afford this" answer -- it returns ``0.0`` and
leaves a plain-language explanation in :attr:`PositionSizer.last_reason`, which
the broker copies into the rejected-order log.  Sizing is on the hot path of
every entry, so an exception per skipped trade would be both slow and wrong: not
being able to afford a trade is a normal outcome, not a failure.

Margin
------
Margin is modelled **only when** ``RiskSettings.use_margin`` is set.  With it
off, the engine does not constrain size by available cash at all, which is what
makes a 1-contract futures backtest on a $100,000 account behave the way a
futures trader expects rather than refusing every trade because the notional
exceeds the balance.  With it on:

* initial margin per unit is ``margin_per_unit`` when that is positive (the
  futures convention: a fixed dollar amount per contract), otherwise
  ``margin_percent`` of the notional (the equities/forex convention);
* maintenance margin is :data:`MAINTENANCE_MARGIN_FRACTION` (50%) of initial
  margin.  Real venues set this per product; 50% is a documented, conservative
  stand-in and the only number this application invents.
"""

from __future__ import annotations

import logging
import math

from ..core.types import RiskSettings, SizingMode
from ..data.models import Instrument

logger = logging.getLogger(__name__)

__all__ = ["PositionSizer", "MAINTENANCE_MARGIN_FRACTION",
           "DEFAULT_ATR_STOP_MULTIPLE"]

#: Maintenance margin as a fraction of initial margin.  See the module docstring.
MAINTENANCE_MARGIN_FRACTION = 0.5

#: Stop distance assumed by ``RISK_PERCENT`` sizing when the strategy defines no
#: stop: this many ATRs.  Sizing by risk needs *some* risk to divide by.
DEFAULT_ATR_STOP_MULTIPLE = 2.0


class PositionSizer:
    """Turns an account state and a candidate trade into a quantity."""

    __slots__ = ("risk", "instrument", "atr_stop_multiple", "last_reason",
                 "_point_value", "_lot")

    def __init__(self, risk: RiskSettings, instrument: Instrument,
                 atr_stop_multiple: float = DEFAULT_ATR_STOP_MULTIPLE) -> None:
        risk.validate()
        self.risk = risk
        self.instrument = instrument
        #: Fallback stop width, in ATRs, for ``RISK_PERCENT`` sizing.  The
        #: backtester passes the strategy's own ATR stop multiple when it has
        #: one, so the fallback matches the geometry the trade would have used.
        self.atr_stop_multiple = float(atr_stop_multiple)
        #: Why the last call returned what it did.  Empty when nothing notable
        #: happened; always populated when the answer was ``0.0``.
        self.last_reason: str = ""
        self._point_value = float(instrument.point_value)
        self._lot = float(instrument.lot_size)

    # -- sizing ----------------------------------------------------------

    def size(self, equity: float, price: float, stop_price: float | None = None,
             atr: float = float("nan"), free_equity: float | None = None) -> float:
        """Units to trade, or ``0.0`` with :attr:`last_reason` set.

        Parameters
        ----------
        equity:
            Account equity at the moment of the fill (cash plus open P&L).
        price:
            The fill price of the entry.
        stop_price:
            The initial stop, if the strategy has one.  Only ``RISK_PERCENT``
            uses it.
        atr:
            ATR of the **signal** bar.  Using the fill bar's ATR would size the
            position from the range of a bar that had not finished when the
            order was sent.
        free_equity:
            Equity not already pledged as margin against open positions.
            Defaults to ``equity``.
        """
        self.last_reason = ""
        eq = float(equity)
        px = float(price)
        if not math.isfinite(eq) or eq <= 0.0:
            self.last_reason = ("Account equity is zero or negative, so no new "
                                "position can be opened.")
            return 0.0
        if not math.isfinite(px) or px <= 0.0:
            self.last_reason = "The entry price is not a usable number."
            return 0.0

        risk = self.risk
        pv = self._point_value
        mode = risk.sizing_mode

        if mode is SizingMode.FIXED_UNITS:
            qty = float(risk.fixed_units)
        elif mode is SizingMode.FIXED_CASH:
            denom = px * pv
            if denom <= 0.0:
                self.last_reason = "The instrument's point value is zero."
                return 0.0
            qty = float(risk.fixed_cash) / denom
        elif mode is SizingMode.PERCENT_EQUITY:
            denom = px * pv
            if denom <= 0.0:
                self.last_reason = "The instrument's point value is zero."
                return 0.0
            qty = eq * (float(risk.percent_equity) / 100.0) / denom
        elif mode is SizingMode.RISK_PERCENT:
            qty = self._size_by_risk(eq, px, stop_price, atr, pv)
        else:  # VOLATILITY_TARGET
            qty = self._size_by_volatility(eq, atr, pv)

        if qty <= 0.0 or not math.isfinite(qty):
            if not self.last_reason:
                self.last_reason = ("The sizing rule worked out a position of "
                                    "zero units.")
            return 0.0

        capped = self._apply_caps(qty, px, eq if free_equity is None
                                  else float(free_equity))
        if capped <= 0.0:
            return 0.0
        return capped

    def _size_by_risk(self, equity: float, price: float, stop_price: float | None,
                      atr: float, pv: float) -> float:
        """``RISK_PERCENT``: risk a fixed slice of equity between entry and stop."""
        risk_cash = equity * (float(self.risk.risk_percent) / 100.0)
        distance = 0.0
        if stop_price is not None and math.isfinite(stop_price):
            distance = abs(price - float(stop_price))
        if distance <= 0.0:
            # No stop to measure risk against.  Fall back to an ATR-width stop so
            # the trade is still sized by risk rather than silently skipped, and
            # say so -- the difference matters when reading the trade log.
            if atr is None or not math.isfinite(atr) or atr <= 0.0:
                self.last_reason = (
                    "Sizing by risk needs a stop distance, but this strategy has "
                    "no stop loss and the ATR is not available yet, so the trade "
                    "was skipped.")
                return 0.0
            distance = atr * self.atr_stop_multiple
            self.last_reason = (
                f"This strategy has no stop loss, so the risk-based size used an "
                f"assumed stop {self.atr_stop_multiple:g} x ATR "
                f"({distance:.6g} points) away.")
        denom = distance * pv
        if denom <= 0.0:
            self.last_reason = "The stop distance works out as zero."
            return 0.0
        return risk_cash / denom

    def _size_by_volatility(self, equity: float, atr: float, pv: float) -> float:
        """``VOLATILITY_TARGET``: make one ATR of movement worth a fixed slice of equity.

        ``qty * atr * point_value ~= equity * volatility_target_percent / 100``,
        so a quiet market gets a bigger position than a violent one and the
        expected per-bar swing of the account stays roughly constant.
        """
        if atr is None or not math.isfinite(atr) or atr <= 0.0:
            self.last_reason = ("Sizing by volatility target needs an ATR, which "
                                "is not available yet.")
            return 0.0
        target_cash = equity * (float(self.risk.volatility_target_percent) / 100.0)
        denom = atr * pv
        if denom <= 0.0:
            self.last_reason = "The instrument's point value is zero."
            return 0.0
        return target_cash / denom

    def _apply_caps(self, qty: float, price: float, free_equity: float) -> float:
        """Apply the unit cap, the margin cap and lot rounding, in that order."""
        risk = self.risk
        capped_by = ""

        max_units = float(risk.max_position_units)
        if max_units > 0.0 and qty > max_units:
            qty = max_units
            capped_by = f"capped at the maximum position size of {max_units:g} units"

        if risk.use_margin:
            per_unit = self.initial_margin_per_unit(price)
            if per_unit > 0.0:
                affordable = max(free_equity, 0.0) / per_unit
                if affordable <= 0.0:
                    self.last_reason = (
                        f"There is no free equity left to margin a new position "
                        f"(margin needed is {per_unit:,.2f} per unit).")
                    return 0.0
                if qty > affordable:
                    qty = affordable
                    capped_by = (f"limited by available margin to {qty:.6g} units "
                                 f"({per_unit:,.2f} per unit)")

        if risk.round_quantity:
            rounded = self.instrument.round_quantity(qty)
        else:
            rounded = qty
        if rounded <= 0.0:
            self.last_reason = (
                f"The calculated size of {qty:.6g} units is smaller than the "
                f"instrument's minimum tradeable size of {self._lot:g}.")
            return 0.0
        if capped_by and not self.last_reason:
            self.last_reason = f"Position {capped_by}."
        return rounded

    # -- margin ----------------------------------------------------------

    def initial_margin_per_unit(self, price: float) -> float:
        """Cash pledged per unit held.  Zero when margin is not being modelled."""
        risk = self.risk
        if not risk.use_margin:
            return 0.0
        if risk.margin_per_unit > 0.0:
            return float(risk.margin_per_unit)
        if self.instrument.margin_per_unit > 0.0:
            return float(self.instrument.margin_per_unit)
        return abs(float(price)) * self._point_value * (
            float(risk.margin_percent) / 100.0)

    def initial_margin(self, quantity: float, price: float) -> float:
        """Cash pledged for a position of ``quantity`` opened at ``price``."""
        return abs(float(quantity)) * self.initial_margin_per_unit(price)

    def maintenance_margin(self, quantity: float, price: float) -> float:
        """Equity below which the position is liquidated.  50% of initial margin."""
        return self.initial_margin(quantity, price) * MAINTENANCE_MARGIN_FRACTION
