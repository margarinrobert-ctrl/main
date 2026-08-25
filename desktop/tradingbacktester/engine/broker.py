"""The simulated broker: fills, barriers, positions and the account.

This module owns everything that decides **what price a position gets** and
**when it stops existing**.  The backtester owns the bar loop and the signal
logic; it asks the broker to open, manage and close positions and never touches
a fill price itself.

The rules implemented here, in the order they bite:

*Gaps.*  A bar that **opens** beyond a stop or a target fills at the open, not
at the barrier.  A backtest that fills gaps at the barrier price is inventing
liquidity that was never there, and it flatters exactly the trades that hurt
most in reality.

*Both barriers in one bar.*  Bar data cannot say which came first.
:class:`~tradingbacktester.core.types.IntrabarPriority` decides:
``PESSIMISTIC`` gives it to the stop, ``OPTIMISTIC`` to the target, and
``OHLC_PATH`` assumes ``open -> high -> low -> close`` on a bar that closed up
and ``open -> low -> high -> close`` on a bar that closed down, then takes
whichever barrier that path reaches first.  One case is *not* ambiguous and is
never handed to the priority rule: if the bar **opened** beyond one of the
barriers, that barrier was hit at the first instant of the bar and wins
regardless of the setting.

*Trailing stops.*  On every bar the **existing** stop is tested against the
bar's range first, and only then is the trail anchor moved by that bar's
extreme.  Doing it the other way round lets a bar that took you out also move
your stop -- a look-ahead bug that silently converts losers into winners.

*Limit orders* fill only when price trades through them by at least
``ExecutionSettings.limit_requires_through`` points, or at the open when the bar
gapped past them in the trader's favour.  *Stop orders* fill at the stop price,
or at the open when the bar gapped past.  Take-profit and partial targets are
limit orders and obey the through-requirement.  ``fill_limit_orders`` gates
resting limit orders placed through :meth:`SimulatedBroker.submit`; it does not
cancel a target attached to a position, because switching off limit fills should
not silently remove a strategy's protective exit.

*Costs.*  Spread and slippage are folded into the fill price by
:class:`~tradingbacktester.engine.execution.CostCalculator`; commission is cash
and is deducted at the moment of each fill.  Slippage under ``ATR_FRACTION``
uses the ATR of the bar the fill happens on -- it is a cost, it is adverse
either way, and it cannot flatter a result.  **Barrier geometry is different**:
stop and target distances are measured with the ATR of the *signal* bar, the
last bar that had closed when the order was sent.  Sizing a stop with the fill
bar's ATR would let the position's protection know the range of the bar it was
opened on, which is the single easiest way to fake an edge in a backtest.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..core.errors import OrderError
from ..core.types import (BacktestConfig, ExecutionSettings, ExitReason,
                          ExitSettings, Fill, IntrabarPriority, Order,
                          OrderStatus, OrderType, Position, RiskSettings, Side,
                          Trade)
from ..data.models import Instrument
from .execution import CostCalculator
from .risk import PositionSizer

logger = logging.getLogger(__name__)

__all__ = ["SimulatedBroker", "limit_fill_price", "stop_fill_price"]

#: Quantities below this are treated as zero.  Lot sizes go down to 0.0001 for
#: forex, so the tolerance has to be well below that while still absorbing the
#: float error of repeated partial subtractions.
_QTY_EPS = 1e-9


# --------------------------------------------------------------------------
# Order fill primitives
# --------------------------------------------------------------------------


def limit_fill_price(buying: bool, limit: float, o: float, h: float, l: float,
                     through: float = 0.0) -> tuple[float, bool] | None:
    """Where a resting limit order fills on this bar, or ``None``.

    Returns ``(price, gapped)``.  ``gapped`` is True when the bar opened beyond
    the limit -- the order was already marketable at the open, so it fills at
    the open, which is *better* than the limit price and is the one case where
    a fill legitimately improves on the order.

    ``through`` requires the bar to trade this many points past the limit before
    the order is considered filled.  A limit order that is merely *touched* is
    not necessarily filled in real life: there is a queue in front of you.
    """
    if buying:
        if o <= limit:
            return o, True
        if l <= limit - through:
            return limit, False
        return None
    if o >= limit:
        return o, True
    if h >= limit + through:
        return limit, False
    return None


def stop_fill_price(buying: bool, stop: float, o: float, h: float,
                    l: float) -> tuple[float, bool] | None:
    """Where a stop order fills on this bar, or ``None``.

    A stop becomes a market order the moment it is touched, so there is no
    through-requirement; but if the bar opened beyond the stop the fill is at
    the open, which is *worse* than the stop price.  That asymmetry -- limits
    improve on a gap, stops suffer from one -- is the whole point of modelling
    gaps at all.
    """
    if buying:
        if o >= stop:
            return o, True
        if h >= stop:
            return stop, False
        return None
    if o <= stop:
        return o, True
    if l <= stop:
        return stop, False
    return None


# --------------------------------------------------------------------------
# Internal position bookkeeping
# --------------------------------------------------------------------------


@dataclass(slots=True)
class _Slot:
    """One open position plus the engine bookkeeping that goes with it.

    :class:`~tradingbacktester.core.types.Position` is a shared value type and
    deliberately knows nothing about trade ids, margin or partial-exit ladders,
    so the extra state lives here.  ``__slots__`` because this is touched on
    every bar of every trade.
    """

    pos: Position
    trade_id: int
    """Reserved id for the *final* trade row; partials point at it via ``parent_id``."""
    is_long: bool
    sign: int
    equity_at_entry: float
    risk_per_unit: float
    """``abs(entry - initial stop)`` in price points; 0 when there is no stop."""
    margin: float
    """Cash currently pledged against this position."""
    margin_per_unit: float = 0.0
    stop_reason: ExitReason = ExitReason.STOP_LOSS
    breakeven_done: bool = False
    trail_started: bool = False
    partials: list[list[float]] = field(default_factory=list)
    """``[[target_price, fraction, done], ...]`` ordered by increasing R."""


# --------------------------------------------------------------------------
# The broker
# --------------------------------------------------------------------------


class SimulatedBroker:
    """Cash, positions, orders, fills and the intrabar barrier logic.

    The broker is driven bar by bar by :class:`~tradingbacktester.engine.backtester.Backtester`.
    It is deliberately not re-entrant and not thread-safe: one instance
    simulates exactly one run.
    """

    def __init__(self, instrument: Instrument, config: BacktestConfig,
                 atr: np.ndarray, costs: CostCalculator | None = None,
                 sizer: PositionSizer | None = None) -> None:
        self.instrument = instrument
        self.config = config
        self.risk: RiskSettings = config.risk
        self.exits: ExitSettings = config.exits
        self.execution: ExecutionSettings = config.execution
        self.costs = costs or CostCalculator(config.costs, instrument)
        self.sizer = sizer or PositionSizer(
            config.risk, instrument,
            atr_stop_multiple=(config.exits.stop_loss_value
                               if config.exits.stop_loss_enabled
                               and config.exits.stop_loss_mode == "atr"
                               else 2.0))

        self.atr = np.asarray(atr, dtype="float64")
        self.point_value = float(instrument.point_value)

        # -- account ------------------------------------------------------
        self.cash: float = float(config.starting_capital)
        self.positions: list[_Slot] = []
        self.orders: list[Order] = []
        self.fills: list[Fill] = []
        self.trades: list[Trade] = []
        self.rejected_orders: int = 0
        self.warnings: list[str] = []

        # -- hoisted settings (read on every bar of every trade) ----------
        self._priority = config.execution.intrabar_priority
        self._through = float(config.execution.limit_requires_through)
        self._max_bars = int(config.exits.max_bars_in_trade)
        self._trailing = bool(config.exits.trailing_enabled)
        self._trail_at_r = float(config.exits.trailing_activate_at_r)
        self._breakeven_r = float(config.exits.breakeven_at_r)
        self._partial_ladder = tuple(config.exits.partial_exits)
        self._use_margin = bool(config.risk.use_margin)
        self._round_qty = bool(config.risk.round_quantity)
        self._lot = float(instrument.lot_size)

        #: ATR of the bar currently being processed; see :meth:`set_bar_atr`.
        self._atr_at_close = float("nan")
        self._order_seq = 0
        self._trade_seq = 0
        self._seen_warnings: set[str] = set()

    # -- account state ---------------------------------------------------

    @property
    def has_positions(self) -> bool:
        return bool(self.positions)

    def equity(self, price: float) -> float:
        """Cash plus the mark-to-market value of every open position."""
        eq = self.cash
        pv = self.point_value
        for s in self.positions:
            p = s.pos
            eq += (price - p.entry_price) * s.sign * p.quantity * pv
        return eq

    def exposure(self) -> float:
        """Signed quantity across open positions, for the exposure ribbon."""
        total = 0.0
        for s in self.positions:
            total += s.sign * s.pos.quantity
        return total

    def used_margin(self) -> float:
        total = 0.0
        for s in self.positions:
            total += s.margin
        return total

    def maintenance_margin(self) -> float:
        """Total maintenance requirement: 50% of pledged initial margin."""
        from .risk import MAINTENANCE_MARGIN_FRACTION

        return self.used_margin() * MAINTENANCE_MARGIN_FRACTION

    def free_equity(self, price: float) -> float:
        return self.equity(price) - self.used_margin()

    def net_side(self) -> Side | None:
        """The side currently held, or ``None`` when flat.

        Positions are only ever stacked on one side; an opposite signal either
        reverses or is ignored, so this is unambiguous.
        """
        if not self.positions:
            return None
        return Side.LONG if self.positions[0].is_long else Side.SHORT

    # -- orders ----------------------------------------------------------

    def _next_order_id(self) -> int:
        self._order_seq += 1
        return self._order_seq

    def _next_trade_id(self) -> int:
        self._trade_seq += 1
        return self._trade_seq

    def submit(self, order: Order) -> Order:
        """Record a working order.  The backtester resolves it on the next bar."""
        if order.quantity < 0:
            raise OrderError("An order cannot have a negative quantity.",
                             detail=repr(order))
        if order.id <= 0:
            order.id = self._next_order_id()
        self.orders.append(order)
        return order

    def resolve_resting_order(self, order: Order, o: float, h: float,
                              l: float) -> tuple[float, bool] | None:
        """Would this resting order fill on a bar with this range?

        Implements the limit and stop rules for orders that are not attached to
        a position.  Market orders fill at the open.
        """
        if order.order_type is OrderType.MARKET:
            return o, False
        buying = order.side is Side.LONG
        if order.order_type is OrderType.LIMIT:
            if not self.execution.fill_limit_orders:
                return None
            if order.limit_price is None:
                raise OrderError("A limit order was submitted without a limit price.",
                                 detail=repr(order))
            return limit_fill_price(buying, float(order.limit_price), o, h, l,
                                    self._through)
        if order.order_type is OrderType.STOP:
            if order.stop_price is None:
                raise OrderError("A stop order was submitted without a stop price.",
                                 detail=repr(order))
            return stop_fill_price(buying, float(order.stop_price), o, h, l)
        # STOP_LIMIT: the stop must trigger first, then the limit must fill.
        if order.stop_price is None or order.limit_price is None:
            raise OrderError(
                "A stop-limit order needs both a stop price and a limit price.",
                detail=repr(order))
        if stop_fill_price(buying, float(order.stop_price), o, h, l) is None:
            return None
        if not self.execution.fill_limit_orders:
            return None
        return limit_fill_price(buying, float(order.limit_price), o, h, l,
                                self._through)

    def _record_order(self, side: Side, quantity: float, bar: int, ts: int,
                      order_type: OrderType, status: OrderStatus,
                      reason: ExitReason | None = None, tag: str = "",
                      fill_price: float | None = None,
                      limit_price: float | None = None,
                      stop_price: float | None = None,
                      reject_reason: str = "") -> Order:
        order = Order(
            id=self._next_order_id(), side=side, quantity=float(quantity),
            order_type=order_type, limit_price=limit_price, stop_price=stop_price,
            created_bar=bar, created_ts=int(ts), status=status, tag=tag,
            reason=reason, reject_reason=reject_reason,
        )
        if status is OrderStatus.FILLED:
            order.filled_bar = bar
            order.filled_ts = int(ts)
            order.fill_price = fill_price
        self.orders.append(order)
        return order

    def reject(self, side: Side, bar: int, ts: int, why: str,
               quantity: float = 0.0) -> None:
        """Log and count an entry that could not be taken."""
        self._record_order(side, quantity, bar, ts, OrderType.MARKET,
                           OrderStatus.REJECTED, reject_reason=why)
        self.rejected_orders += 1
        logger.info("Order rejected on bar %d: %s", bar, why)

    # -- opening ---------------------------------------------------------

    def open_position(self, side: Side, bar: int, ts: int, reference_price: float,
                      signal_bar: int, tag: str = "") -> _Slot | None:
        """Open a position at ``reference_price`` on ``bar``.

        ``signal_bar`` is the bar whose close produced the signal.  Everything
        that shapes the trade -- the stop, the target, the size -- is measured
        with data from that bar; only the fill price and the slippage come from
        ``bar`` itself.
        """
        atr_arr = self.atr
        n = len(atr_arr)
        atr_signal = float(atr_arr[signal_bar]) if 0 <= signal_bar < n else float("nan")
        atr_fill = float(atr_arr[bar]) if 0 <= bar < n else float("nan")

        fill, spread_pu, slip_pu = self.costs.apply_entry(reference_price, side,
                                                          atr_fill)
        stop, target = self._barrier_prices(fill, side, atr_signal)

        equity = self.equity(reference_price)
        free = equity - self.used_margin()
        qty = self.sizer.size(equity, fill, stop, atr_signal, free_equity=free)
        if qty <= 0.0:
            self.reject(side, bar, ts,
                        self.sizer.last_reason or "The position size worked out as zero.")
            return None

        margin_per_unit = (self.sizer.initial_margin_per_unit(fill)
                           if self._use_margin else 0.0)
        margin = margin_per_unit * qty
        if self._use_margin and margin > free + 1e-9:
            self.reject(
                side, bar, ts,
                f"This entry needs {margin:,.2f} of margin but only {free:,.2f} "
                f"of equity is free.", quantity=qty)
            return None

        commission = self.costs.commission(qty, fill)
        self.cash -= commission

        pv = self.point_value
        pos = Position(
            side=side, quantity=qty, entry_price=fill, entry_bar=bar, entry_ts=int(ts),
            stop_loss=stop, take_profit=target, trail_anchor=fill,
            initial_quantity=qty, initial_stop=stop, entry_commission=commission,
            entry_slippage=slip_pu * qty * pv, entry_spread_cost=spread_pu * qty * pv,
            tag=tag,
        )
        risk_pu = abs(fill - stop) if stop is not None else 0.0
        slot = _Slot(
            pos=pos, trade_id=self._next_trade_id(), is_long=side is Side.LONG,
            sign=side.sign, equity_at_entry=equity, risk_per_unit=risk_pu,
            margin=margin, margin_per_unit=margin_per_unit,
        )
        slot.partials = self._build_partials(fill, slot.sign, risk_pu, qty)
        self.positions.append(slot)

        order = self._record_order(side, qty, bar, ts, OrderType.MARKET,
                                   OrderStatus.FILLED, tag=tag, fill_price=fill)
        self.fills.append(Fill(
            order_id=order.id, bar=bar, ts=int(ts), side=side, quantity=qty,
            reference_price=float(reference_price), fill_price=fill,
            commission=commission, slippage_cost=slip_pu * qty * pv,
            spread_cost=spread_pu * qty * pv,
        ))
        return slot

    def _barrier_prices(self, fill: float, side: Side,
                        atr: float) -> tuple[float | None, float | None]:
        """Initial stop and target prices, measured from the fill price."""
        e = self.exits
        sign = side.sign
        stop: float | None = None
        target: float | None = None

        if e.stop_loss_enabled:
            d = self._distance(e.stop_loss_mode, e.stop_loss_value, fill, atr,
                               None, "stop loss")
            if d is not None and d > 0.0:
                stop = fill - sign * d
                if stop <= 0.0:
                    # A stop below zero cannot be hit; drop it and say so rather
                    # than pretending the trade is protected.
                    self._warn_once(
                        "The stop loss worked out at or below zero for at least one "
                        "trade, so that trade ran without a stop. Check the stop "
                        "settings against the instrument's price scale.")
                    stop = None

        if e.take_profit_enabled:
            risk_pu = abs(fill - stop) if stop is not None else None
            d = self._distance(e.take_profit_mode, e.take_profit_value, fill, atr,
                               risk_pu, "take profit")
            if d is not None and d > 0.0:
                target = fill + sign * d
                if target <= 0.0:
                    target = None
        return stop, target

    def _distance(self, mode: str, value: float, price: float, atr: float,
                  risk_per_unit: float | None, what: str) -> float | None:
        """Turn an exit setting into a distance in price points."""
        v = float(value)
        if v <= 0.0:
            return None
        m = (mode or "atr").lower()
        if m == "points":
            return v
        if m == "percent":
            return abs(price) * v / 100.0
        if m == "r_multiple":
            if risk_per_unit is not None and risk_per_unit > 0.0:
                return risk_per_unit * v
            self._warn_once(
                f"The {what} is set as a multiple of R, but there is no stop loss "
                f"to measure R against, so an ATR distance was used instead.")
            m = "atr"
        if m != "atr":
            self._warn_once(
                f"'{mode}' is not a {what} mode this application knows; it was "
                f"treated as an ATR multiple.")
        if atr is None or not math.isfinite(atr) or atr <= 0.0:
            self._warn_once(
                f"The ATR was not available when a trade was opened, so no {what} "
                f"could be placed on it.")
            return None
        return atr * v

    def _build_partials(self, fill: float, sign: int, risk_per_unit: float,
                        quantity: float) -> list[list[float]]:
        """The scale-out ladder for a new position, as ``[price, qty, done]`` rows."""
        ladder = self._partial_ladder
        if not ladder:
            return []
        if risk_per_unit <= 0.0:
            self._warn_once(
                "Partial exits are set as R multiples but this strategy has no stop "
                "loss, so R is undefined and no partial exits were taken.")
            return []
        rows: list[list[float]] = []
        for fraction, r_mult in sorted(ladder, key=lambda x: float(x[1])):
            frac = float(fraction)
            r = float(r_mult)
            if frac <= 0.0 or r <= 0.0:
                continue
            qty = quantity * min(frac, 1.0)
            if self._round_qty:
                qty = self.instrument.round_quantity(qty)
            if qty <= _QTY_EPS:
                self._warn_once(
                    f"A partial exit of {frac:.0%} works out smaller than the "
                    f"instrument's minimum size, so it was skipped.")
                continue
            rows.append([fill + sign * r * risk_per_unit, qty, 0.0])
        return rows

    # -- per-bar management ----------------------------------------------

    def manage_bar(self, i: int, ts: int, o: float, h: float, l: float,
                   c: float) -> None:
        """Run every open position through this bar's range.

        Called once per bar, after any fills at the open and before the bar's
        signals are evaluated.
        """
        if not self.positions:
            return
        # Iterate over a copy: closing a position mutates ``self.positions``.
        for slot in list(self.positions):
            self._manage_slot(slot, i, ts, o, h, l, c)

    def _manage_slot(self, slot: _Slot, i: int, ts: int, o: float, h: float,
                     l: float, c: float) -> None:
        p = slot.pos
        long = slot.is_long
        entry = p.entry_price

        # -- excursions ---------------------------------------------------
        if long:
            adverse = entry - l
            favourable = h - entry
        else:
            adverse = h - entry
            favourable = entry - l
        if adverse > p.mae:
            p.mae = adverse
        if favourable > p.mfe:
            p.mfe = favourable
        p.bars_held = i - p.entry_bar

        # -- where would each barrier fill on this bar? --------------------
        # Both protective exits sell a long and buy back a short, so the
        # "buying" flag is the same for both.
        buying = not long
        stop = p.stop_loss
        stop_hit = (stop_fill_price(buying, stop, o, h, l)
                    if stop is not None else None)

        fav_hit = self._favourable_hit(slot, buying, o, h, l)

        if stop_hit is not None or fav_hit is not None:
            if self._resolve_barriers(slot, i, ts, o, h, l, c, stop_hit, fav_hit):
                return

        # -- the position survived the bar; now, and only now, move the stop
        self._update_protective_stop(slot, h, l, c, favourable)

        # -- time stop -----------------------------------------------------
        if self._max_bars and (i - p.entry_bar) >= self._max_bars:
            self.close_position(slot, i, ts, c, ExitReason.TIME_STOP)

    def _favourable_hit(self, slot: _Slot, buying: bool, o: float, h: float,
                        l: float) -> tuple[float, bool, str, Any] | None:
        """The nearest profit-taking barrier this bar reaches, if any.

        Returns ``(price, gapped, kind, payload)`` where ``kind`` is ``"partial"``
        (payload is the ladder row) or ``"target"``.  The rungs are ordered by R,
        so only the first untaken one can be next -- but nothing stops a strategy
        putting its target *inside* the ladder, so the target is always compared
        against it and whichever barrier sits nearer the entry is taken first.
        """
        hit: tuple[float, bool, str, Any] | None = None
        barrier = 0.0
        for row in slot.partials:
            if row[2]:
                continue
            r = limit_fill_price(buying, row[0], o, h, l, self._through)
            if r is not None:
                hit = (r[0], r[1], "partial", row)
                barrier = row[0]
            break
        target = slot.pos.take_profit
        if target is not None:
            r = limit_fill_price(buying, target, o, h, l, self._through)
            if r is not None:
                # Profit barriers sit above a long and below a short, so "nearer
                # the entry" is the lower price for a long and the higher one for
                # a short.  ``buying`` is True exactly when the position is short.
                nearer = target > barrier if buying else target < barrier
                if hit is None or nearer:
                    hit = (r[0], r[1], "target", None)
        return hit

    def _resolve_barriers(self, slot: _Slot, i: int, ts: int, o: float, h: float,
                          l: float, c: float, stop_hit: tuple[float, bool] | None,
                          fav_hit: tuple[Any, ...] | None) -> bool:
        """Apply the barrier(s) this bar touched.  Returns True if it closed out."""
        p = slot.pos
        stop_first: bool
        if stop_hit is not None and fav_hit is not None:
            if stop_hit[1] and not fav_hit[1]:
                stop_first = True       # the bar opened through the stop: a fact
            elif fav_hit[1] and not stop_hit[1]:
                stop_first = False      # the bar opened through the target: a fact
            else:
                priority = self._priority
                if priority is IntrabarPriority.PESSIMISTIC:
                    stop_first = True
                elif priority is IntrabarPriority.OPTIMISTIC:
                    stop_first = False
                else:
                    # OHLC_PATH: an up bar visits its high first, a down bar its
                    # low first, so whichever barrier sits on that side is
                    # reached first.
                    upper_first = c >= o
                    fav_first = upper_first if slot.is_long else not upper_first
                    stop_first = not fav_first
        else:
            stop_first = stop_hit is not None

        if stop_first:
            self.close_position(slot, i, ts, stop_hit[0], slot.stop_reason)
            return True

        # Favourable barriers, nearest first.  A bar wide enough to cover two
        # scale-out rungs really did trade through both of them.
        buying = not slot.is_long
        while fav_hit is not None:
            if fav_hit[2] == "target":
                self.close_position(slot, i, ts, fav_hit[0], ExitReason.TAKE_PROFIT)
                return True
            row = fav_hit[3]
            row[2] = 1.0
            p.partials_done += 1
            self.close_position(slot, i, ts, fav_hit[0], ExitReason.PARTIAL_TARGET,
                                quantity=min(row[1], p.quantity))
            if p.quantity <= _QTY_EPS:
                return True
            fav_hit = self._favourable_hit(slot, buying, o, h, l)

        # The remainder is still open, and the bar really did trade through the
        # stop, so the remainder is out too -- whatever the priority setting
        # said about which came first.
        if stop_hit is not None:
            self.close_position(slot, i, ts, stop_hit[0], slot.stop_reason)
            return True
        return False

    def _update_protective_stop(self, slot: _Slot, h: float, l: float, c: float,
                                favourable: float) -> None:
        """Break-even and trailing updates, applied *after* this bar's stop test."""
        p = slot.pos
        long = slot.is_long
        risk = slot.risk_per_unit

        if self._breakeven_r > 0.0 and not slot.breakeven_done and risk > 0.0:
            if favourable >= self._breakeven_r * risk:
                slot.breakeven_done = True
                entry = p.entry_price
                if p.stop_loss is None or (entry > p.stop_loss if long
                                           else entry < p.stop_loss):
                    p.stop_loss = entry

        if not self._trailing:
            return
        if not slot.trail_started:
            if self._trail_at_r > 0.0:
                if risk <= 0.0 or favourable < self._trail_at_r * risk:
                    return
            slot.trail_started = True

        anchor = p.trail_anchor
        if long:
            if anchor is None or h > anchor:
                anchor = h
        else:
            if anchor is None or l < anchor:
                anchor = l
        p.trail_anchor = anchor

        dist = self._distance(self.exits.trailing_mode, self.exits.trailing_value,
                              c, self._atr_at_close, slot.risk_per_unit, "trailing stop")
        if dist is None or dist <= 0.0:
            return
        new_stop = anchor - dist if long else anchor + dist
        cur = p.stop_loss
        # A trailing stop only ever tightens.  Letting it widen would hand back
        # protection the trade has already earned.
        if cur is None or (new_stop > cur if long else new_stop < cur):
            p.stop_loss = new_stop
            slot.stop_reason = ExitReason.TRAILING_STOP

    def set_bar_atr(self, value: float) -> None:
        """Tell the broker the ATR of the bar being processed.

        The trailing stop is recomputed at the close of each bar and applies
        from the next one, so using this bar's ATR is legitimate -- the bar has
        finished.  It is passed in rather than looked up so the hot loop indexes
        the ATR array once per bar instead of once per position.
        """
        self._atr_at_close = value

    # -- closing ---------------------------------------------------------

    def close_position(self, slot: _Slot, bar: int, ts: int, reference_price: float,
                       reason: ExitReason, quantity: float | None = None) -> Trade:
        """Close all or part of a position and book the trade."""
        p = slot.pos
        qty = p.quantity if quantity is None else min(float(quantity), p.quantity)
        if qty <= _QTY_EPS:
            raise OrderError(
                "The engine tried to close a position that has no quantity left.",
                detail=f"bar={bar} reason={reason} qty={qty}")

        atr_arr = self.atr
        atr_fill = float(atr_arr[bar]) if 0 <= bar < len(atr_arr) else float("nan")
        fill, spread_pu, slip_pu = self.costs.apply_exit(reference_price, p.side,
                                                        atr_fill)
        pv = self.point_value
        gross = (fill - p.entry_price) * slot.sign * qty * pv
        commission = self.costs.commission(qty, fill)

        # Entry costs belong to the whole position; a partial takes its share.
        frac = qty / p.initial_quantity if p.initial_quantity > 0 else 1.0
        entry_commission = p.entry_commission * frac
        spread_cost = p.entry_spread_cost * frac + spread_pu * qty * pv
        slippage_cost = p.entry_slippage * frac + slip_pu * qty * pv
        net = gross - entry_commission - commission

        self.cash += gross - commission
        p.realized_pnl += net

        closing_all = qty >= p.quantity - _QTY_EPS
        if closing_all:
            trade_id = slot.trade_id
            parent_id = None
            self.positions.remove(slot)
            p.quantity = 0.0
        else:
            trade_id = self._next_trade_id()
            parent_id = slot.trade_id
            p.quantity -= qty
            if self._use_margin:
                slot.margin = slot.margin_per_unit * p.quantity

        r_multiple: float | None = None
        if slot.risk_per_unit > 0.0:
            risk_cash = slot.risk_per_unit * qty * pv
            if risk_cash > 0.0:
                r_multiple = net / risk_cash

        equity_after = self.equity(reference_price)
        eq_entry = slot.equity_at_entry
        trade = Trade(
            id=trade_id, side=p.side, quantity=qty, entry_bar=p.entry_bar,
            entry_ts=p.entry_ts, entry_price=p.entry_price, exit_bar=bar,
            exit_ts=int(ts), exit_price=fill, stop_loss=p.initial_stop,
            take_profit=p.take_profit, gross_pnl=gross, commission=entry_commission + commission,
            slippage_cost=slippage_cost, spread_cost=spread_cost, net_pnl=net,
            return_pct=(net / eq_entry * 100.0) if eq_entry > 0 else 0.0,
            bars_held=bar - p.entry_bar,
            duration_seconds=(int(ts) - p.entry_ts) / 1e9,
            exit_reason=reason, mae=max(p.mae, 0.0), mfe=max(p.mfe, 0.0),
            r_multiple=r_multiple, equity_at_entry=eq_entry,
            equity_after=equity_after, parent_id=parent_id, tag=p.tag,
        )
        self.trades.append(trade)

        order_type = {
            ExitReason.STOP_LOSS: OrderType.STOP,
            ExitReason.TRAILING_STOP: OrderType.STOP,
            ExitReason.TAKE_PROFIT: OrderType.LIMIT,
            ExitReason.PARTIAL_TARGET: OrderType.LIMIT,
        }.get(reason, OrderType.MARKET)
        exit_side = p.side.opposite
        order = self._record_order(exit_side, qty, bar, ts, order_type,
                                   OrderStatus.FILLED, reason=reason, tag=p.tag,
                                   fill_price=fill)
        self.fills.append(Fill(
            order_id=order.id, bar=bar, ts=int(ts), side=exit_side, quantity=qty,
            reference_price=float(reference_price), fill_price=fill,
            commission=commission, slippage_cost=slip_pu * qty * pv,
            spread_cost=spread_pu * qty * pv, reason=reason,
        ))
        return trade

    def flatten(self, bar: int, ts: int, price: float, reason: ExitReason) -> int:
        """Close every open position at ``price``.  Returns how many were closed."""
        if not self.positions:
            return 0
        count = 0
        for slot in list(self.positions):
            self.close_position(slot, bar, ts, price, reason)
            count += 1
        return count

    def check_margin_call(self, bar: int, ts: int, price: float) -> bool:
        """Liquidate everything if equity has fallen to the maintenance level.

        Maintenance is 50% of the initial margin pledged against open positions
        (see :mod:`tradingbacktester.engine.risk`).  Real venues publish their
        own numbers per product; this is a documented stand-in, not a claim
        about any particular broker.
        """
        if not self._use_margin or not self.positions:
            return False
        maintenance = self.maintenance_margin()
        if maintenance <= 0.0:
            return False
        if self.equity(price) > maintenance:
            return False
        n = self.flatten(bar, ts, price, ExitReason.MARGIN_CALL)
        self._warn_once(
            "Equity fell to the maintenance margin level and the account was "
            "liquidated. The results after that point are not meaningful.")
        logger.warning("Margin call on bar %d: %d position(s) liquidated", bar, n)
        return True

    # -- misc -------------------------------------------------------------

    def _warn_once(self, message: str) -> None:
        """Record a warning the first time it happens.

        A per-bar warning would produce thousands of identical lines and bury
        the one thing the user needs to read.
        """
        if message in self._seen_warnings:
            return
        self._seen_warnings.add(message)
        self.warnings.append(message)
        logger.warning("%s", message)
