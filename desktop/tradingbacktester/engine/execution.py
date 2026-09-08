"""Transaction costs: spread, slippage and commission.

The engine keeps *cost* logic separate from *fill* logic on purpose.  The broker
decides **which price** a bar can transact at; this module decides **what that
price becomes** once the market's frictions are paid.  Both halves have to be
right, and mixing them together is how a backtest quietly starts paying the
mid-price.

Three rules hold everywhere in this file:

1. Every cost is adverse.  There is no combination of settings that pays the
   account for transacting: buys fill higher than the reference price and sells
   fill lower, always.
2. Spread and slippage are expressed **per unit of price** (price points), never
   in cash.  The broker multiplies by quantity and ``point_value`` when it books
   the trade, because only the broker knows how big the position is.
3. Commission is in cash, charged **per side**, with ``min_commission`` acting as
   a floor on each side the way a real broker's ticket charge does.

Fill prices are deliberately *not* snapped back to the instrument's tick grid.
Rounding a cost-adjusted price to the nearest tick would move the fill in the
trader's favour half the time, which would make the measured cost differ from
the configured cost; a reviewer checking "slippage of 0.5 points cost me exactly
0.5 points per unit" must get exactly that.
"""

from __future__ import annotations

import logging
import math

from ..core.errors import OrderError
from ..core.types import CommissionMode, CostModel, Side, SlippageMode, SpreadMode
from ..data.models import Instrument

logger = logging.getLogger(__name__)

__all__ = ["CostCalculator"]


class CostCalculator:
    """Applies a :class:`~tradingbacktester.core.types.CostModel` to a fill.

    Parameters
    ----------
    costs:
        The configured cost model.  Validated on construction, so a nonsensical
        model fails at the start of a run rather than on the first trade.
    instrument:
        Supplies ``point_value`` (used by percent-of-notional commission) and
        ``tick_size`` (used only for the sanity floor on fill prices).
    """

    __slots__ = ("costs", "instrument", "_point_value", "_entry_spread",
                 "_exit_spread", "_slip_mode", "_slip_value", "_comm_mode",
                 "_comm_value", "_min_comm", "_tick")

    def __init__(self, costs: CostModel, instrument: Instrument) -> None:
        costs.validate()
        self.costs = costs
        self.instrument = instrument
        self._point_value = float(instrument.point_value)
        self._tick = float(instrument.tick_size)

        # Half-spread on each side, or the whole spread once on entry.  Resolved
        # here so the per-fill path is two attribute reads and an add.
        spread = float(costs.spread_points)
        if costs.spread_mode is SpreadMode.HALF_EACH_SIDE:
            self._entry_spread = spread * 0.5
            self._exit_spread = spread * 0.5
        elif costs.spread_mode is SpreadMode.FULL_ON_ENTRY:
            self._entry_spread = spread
            self._exit_spread = 0.0
        else:
            self._entry_spread = 0.0
            self._exit_spread = 0.0

        self._slip_mode = costs.slippage_mode
        self._slip_value = float(costs.slippage_value)
        self._comm_mode = costs.commission_mode
        self._comm_value = float(costs.commission_value)
        self._min_comm = float(costs.min_commission)

    # -- public API ------------------------------------------------------

    def apply_entry(self, price: float, side: Side,
                    atr: float = float("nan")) -> tuple[float, float, float]:
        """Cost-adjust the price a position is *opened* at.

        Returns ``(fill_price, spread_cost_per_unit, slippage_per_unit)`` where
        the two cost figures are positive magnitudes in price points and
        ``fill_price`` already includes both.
        """
        return self._apply(price, side is Side.LONG, self._entry_spread, atr)

    def apply_exit(self, price: float, side: Side,
                   atr: float = float("nan")) -> tuple[float, float, float]:
        """Cost-adjust the price a position is *closed* at.

        ``side`` is the side of the **position**, not of the closing order: a
        long position is closed by selling, so the fill is pushed down.
        """
        return self._apply(price, side is not Side.LONG, self._exit_spread, atr)

    def commission(self, quantity: float, price: float) -> float:
        """Cash commission for one side of a trade of ``quantity`` at ``price``.

        ``min_commission`` is a per-side floor, matching how brokers charge a
        minimum ticket.  A zero-quantity fill is free, so a rejected or
        zero-sized order never manufactures a charge.
        """
        qty = abs(float(quantity))
        if qty <= 0.0:
            return 0.0
        mode = self._comm_mode
        if mode is CommissionMode.PER_UNIT:
            c = self._comm_value * qty
        elif mode is CommissionMode.PER_TRADE:
            c = self._comm_value
        else:  # PERCENT_NOTIONAL
            notional = abs(float(price)) * qty * self._point_value
            c = notional * self._comm_value / 100.0
        if not math.isfinite(c):
            raise OrderError(
                "The commission model produced a value that is not a number.",
                detail=f"mode={mode} value={self._comm_value} qty={qty} price={price}",
            )
        return c if c > self._min_comm else self._min_comm

    def round_turn_cost(self, quantity: float, price: float,
                        atr: float = float("nan")) -> float:
        """Total cash cost of opening *and* closing ``quantity`` at ``price``.

        Used by the UI and by tests as a sanity figure ("what does one trade cost
        me before the market moves at all?").  It assumes both sides transact at
        the same reference price, which is exactly the question being asked.
        """
        qty = abs(float(quantity))
        if qty <= 0.0:
            return 0.0
        _, sp_in, sl_in = self.apply_entry(price, Side.LONG, atr)
        _, sp_out, sl_out = self.apply_exit(price, Side.LONG, atr)
        points = sp_in + sl_in + sp_out + sl_out
        return points * qty * self._point_value + 2.0 * self.commission(qty, price)

    # -- internals -------------------------------------------------------

    def _slippage(self, price: float, atr: float) -> float:
        """Slippage in price points for one fill.

        ``ATR_FRACTION`` is read from the ATR of the bar the fill happens on:
        slippage scales with how fast the market is moving *while* the order is
        being worked.  A missing ATR (warm-up, or an instrument with no range)
        contributes nothing rather than a NaN that would poison the fill price.
        """
        mode = self._slip_mode
        if mode is SlippageMode.NONE:
            return 0.0
        if mode is SlippageMode.FIXED_POINTS:
            return self._slip_value
        if mode is SlippageMode.PERCENT:
            return abs(price) * self._slip_value / 100.0
        # ATR_FRACTION
        if atr is None or not math.isfinite(atr) or atr <= 0.0:
            return 0.0
        return atr * self._slip_value

    def _apply(self, price: float, buying: bool, spread_half: float,
               atr: float) -> tuple[float, float, float]:
        p = float(price)
        if not math.isfinite(p):
            raise OrderError(
                "An order was priced from a bar that has no valid price.",
                detail=f"price={price!r}",
            )
        slip = self._slippage(p, atr)
        total = spread_half + slip
        fill = p + total if buying else p - total
        if fill <= 0.0:
            # A sell whose costs exceed the price means the cost model is not
            # describing this instrument at all -- refusing is more useful than
            # simulating a trade at a negative price.
            raise OrderError(
                "The trading costs are larger than the price itself, so no fill "
                "price can be worked out. Check the spread and slippage settings "
                "against the instrument's price scale.",
                detail=(f"price={p} spread={spread_half} slippage={slip} "
                        f"tick={self._tick}"),
            )
        return fill, spread_half, slip
