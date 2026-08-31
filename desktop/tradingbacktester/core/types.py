"""Value types shared by every layer of the application.

Nothing in here imports Qt, pandas or any engine module: these are the plain
data structures that the data layer, the strategy layer, the engine, the
analytics layer and the UI all agree on.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

import numpy as np

# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------


class Side(str, Enum):
    """Direction of a trade or order."""

    LONG = "long"
    SHORT = "short"

    @property
    def sign(self) -> int:
        """``+1`` for long, ``-1`` for short."""
        return 1 if self is Side.LONG else -1

    @property
    def opposite(self) -> "Side":
        return Side.SHORT if self is Side.LONG else Side.LONG


class OrderType(str, Enum):
    """How an order finds its price."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    """Lifecycle of an order."""

    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TimeInForce(str, Enum):
    """How long a resting order stays alive."""

    GTC = "gtc"
    """Good till cancelled."""
    DAY = "day"
    """Cancelled at the end of the session day."""
    IOC = "ioc"
    """Fill on the next bar or cancel."""


class ExitReason(str, Enum):
    """Why a position was closed.  Used to split P&L by cause."""

    SIGNAL = "signal"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"
    PARTIAL_TARGET = "partial_target"
    TIME_STOP = "time_stop"
    SESSION_END = "session_end"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MARGIN_CALL = "margin_call"
    END_OF_DATA = "end_of_data"
    REVERSAL = "reversal"
    MANUAL = "manual"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


class SignalExecution(str, Enum):
    """When a signal raised on a bar is allowed to be executed.

    ``NEXT_OPEN`` is the default and the only setting free of look-ahead: the
    rule is evaluated on the close of bar *i*, and the order fills at the open
    of bar *i+1*.

    ``THIS_CLOSE`` fills at the close of the same bar the signal fired on.  It
    is offered because some vendors report results that way, but it assumes you
    could have transacted at a price that was only known once the bar was over,
    and the UI labels it as optimistic.
    """

    NEXT_OPEN = "next_open"
    THIS_CLOSE = "this_close"


class IntrabarPriority(str, Enum):
    """Which barrier wins when a bar's range covers both stop and target.

    Bar data cannot say which came first.  ``PESSIMISTIC`` assumes the stop was
    hit, which is the only assumption that will not flatter a backtest.
    """

    PESSIMISTIC = "pessimistic"
    OPTIMISTIC = "optimistic"
    OHLC_PATH = "ohlc_path"
    """Assume open -> high -> low -> close on up bars and open -> low -> high ->
    close on down bars, resolving the order by the sign of ``close - open``."""


class SizingMode(str, Enum):
    """How the quantity for a new position is chosen."""

    FIXED_UNITS = "fixed_units"
    FIXED_CASH = "fixed_cash"
    PERCENT_EQUITY = "percent_equity"
    RISK_PERCENT = "risk_percent"
    VOLATILITY_TARGET = "volatility_target"


class CommissionMode(str, Enum):
    """How commission is charged."""

    PER_UNIT = "per_unit"
    """A cash amount per contract/share, charged on each side."""
    PER_TRADE = "per_trade"
    """A flat cash amount charged on each side."""
    PERCENT_NOTIONAL = "percent_notional"
    """A percentage of the traded notional, charged on each side."""


class SlippageMode(str, Enum):
    """How slippage is applied.  Always adverse to the trade's direction."""

    NONE = "none"
    FIXED_POINTS = "fixed_points"
    PERCENT = "percent"
    ATR_FRACTION = "atr_fraction"


class SpreadMode(str, Enum):
    """How the bid/ask spread is modelled from single-series OHLC data."""

    NONE = "none"
    HALF_EACH_SIDE = "half_each_side"
    """Buys fill at ``price + spread/2``, sells at ``price - spread/2``."""
    FULL_ON_ENTRY = "full_on_entry"
    """The whole spread is charged once, on entry."""


class AssetClass(str, Enum):
    """Broad instrument category; drives the default cost and margin model."""

    FOREX = "forex"
    CRYPTO = "crypto"
    EQUITY = "equity"
    FUTURES = "futures"
    INDEX_CFD = "index_cfd"
    OTHER = "other"


# --------------------------------------------------------------------------
# Orders, fills, positions, trades
# --------------------------------------------------------------------------


@dataclass
class Order:
    """A working or historical order."""

    id: int
    side: Side
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: TimeInForce = TimeInForce.GTC
    created_bar: int = -1
    created_ts: int = 0
    status: OrderStatus = OrderStatus.PENDING
    reduce_only: bool = False
    tag: str = ""
    reason: ExitReason | None = None
    filled_bar: int | None = None
    filled_ts: int | None = None
    fill_price: float | None = None
    reject_reason: str = ""

    def is_active(self) -> bool:
        return self.status is OrderStatus.PENDING


@dataclass
class Fill:
    """The result of an order actually transacting."""

    order_id: int
    bar: int
    ts: int
    side: Side
    quantity: float
    #: Price before costs, i.e. the raw bar price the fill was based on.
    reference_price: float
    #: Price after spread and slippage -- the price the account really paid.
    fill_price: float
    commission: float
    slippage_cost: float
    spread_cost: float
    reason: ExitReason | None = None


@dataclass
class Position:
    """An open position.  ``quantity`` is always positive; ``side`` carries the direction."""

    side: Side
    quantity: float
    entry_price: float
    entry_bar: int
    entry_ts: int
    stop_loss: float | None = None
    take_profit: float | None = None
    trail_anchor: float | None = None
    """Best price reached since entry, used to compute the trailing stop."""
    initial_quantity: float = 0.0
    initial_stop: float | None = None
    entry_commission: float = 0.0
    entry_slippage: float = 0.0
    entry_spread_cost: float = 0.0
    realized_pnl: float = 0.0
    """P&L already banked from partial exits on this position."""
    mae: float = 0.0
    """Maximum adverse excursion in price points, always >= 0."""
    mfe: float = 0.0
    """Maximum favourable excursion in price points, always >= 0."""
    bars_held: int = 0
    partials_done: int = 0
    tag: str = ""

    def unrealized(self, price: float, point_value: float) -> float:
        """Mark-to-market P&L in account currency at ``price``."""
        return (price - self.entry_price) * self.side.sign * self.quantity * point_value


@dataclass
class Trade:
    """One completed round turn.

    A partial exit produces its own :class:`Trade` row so that every row has a
    single entry price, a single exit price and a single P&L; the ``parent_id``
    field links the pieces of a scaled-out position back together.
    """

    id: int
    side: Side
    quantity: float
    entry_bar: int
    entry_ts: int
    entry_price: float
    exit_bar: int
    exit_ts: int
    exit_price: float
    stop_loss: float | None
    take_profit: float | None
    gross_pnl: float
    commission: float
    slippage_cost: float
    spread_cost: float
    net_pnl: float
    return_pct: float
    """Net P&L as a percentage of the account equity at the moment of entry."""
    bars_held: int
    duration_seconds: float
    exit_reason: ExitReason
    mae: float
    mfe: float
    r_multiple: float | None
    """Net P&L divided by the cash that was at risk at entry, or ``None`` when
    the strategy defined no initial stop."""
    equity_at_entry: float
    equity_after: float
    parent_id: int | None = None
    tag: str = ""

    @property
    def is_win(self) -> bool:
        return self.net_pnl > 0.0

    @property
    def notional(self) -> float:
        return abs(self.entry_price * self.quantity)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        d["exit_reason"] = self.exit_reason.value
        return d


# --------------------------------------------------------------------------
# Configuration blocks
# --------------------------------------------------------------------------


@dataclass
class CostModel:
    """Commission, spread and slippage.

    All three are charged in the account currency and every one of them is
    adverse: there is no configuration of this class that can pay the account
    for transacting.
    """

    commission_mode: CommissionMode = CommissionMode.PER_UNIT
    commission_value: float = 0.0
    """Meaning depends on ``commission_mode``: cash per unit, cash per trade, or
    percent of notional (``0.1`` means 0.1%)."""
    min_commission: float = 0.0
    spread_mode: SpreadMode = SpreadMode.NONE
    spread_points: float = 0.0
    """Spread expressed in price points, not ticks."""
    slippage_mode: SlippageMode = SlippageMode.NONE
    slippage_value: float = 0.0
    """Points, percent, or a fraction of ATR depending on ``slippage_mode``."""

    def validate(self) -> None:
        from .errors import RiskError

        if self.commission_value < 0:
            raise RiskError("Commission cannot be negative.")
        if self.spread_points < 0:
            raise RiskError("Spread cannot be negative.")
        if self.slippage_value < 0:
            raise RiskError("Slippage cannot be negative.")
        if self.min_commission < 0:
            raise RiskError("Minimum commission cannot be negative.")


@dataclass
class RiskSettings:
    """Everything that decides *how big* a position is and when trading stops."""

    starting_capital: float = 100_000.0
    sizing_mode: SizingMode = SizingMode.FIXED_UNITS
    fixed_units: float = 1.0
    fixed_cash: float = 10_000.0
    percent_equity: float = 10.0
    risk_percent: float = 1.0
    """Percent of equity risked between entry and the initial stop."""
    volatility_target_percent: float = 1.0
    """Target per-bar volatility of the position as a percent of equity."""
    volatility_atr_period: int = 14
    max_position_units: float = 0.0
    """Hard cap on units per position; ``0`` disables the cap."""
    max_concurrent_positions: int = 1
    max_daily_loss: float = 0.0
    """Cash loss in one session day that halts trading for that day; ``0`` disables."""
    max_daily_loss_is_percent: bool = False
    allow_long: bool = True
    allow_short: bool = True
    use_margin: bool = False
    margin_percent: float = 100.0
    """Initial margin as a percent of notional, for equities/forex."""
    margin_per_unit: float = 0.0
    """Initial margin per contract, for futures.  Takes priority when > 0."""
    round_quantity: bool = True
    """Round the computed size down to the instrument's lot size."""

    def validate(self) -> None:
        from .errors import RiskError

        if self.starting_capital <= 0:
            raise RiskError("Starting capital must be greater than zero.")
        if not self.allow_long and not self.allow_short:
            raise RiskError("At least one of long or short trading must be enabled.")
        if self.max_concurrent_positions < 1:
            raise RiskError("The maximum number of open positions must be at least 1.")
        if self.sizing_mode is SizingMode.RISK_PERCENT and self.risk_percent <= 0:
            raise RiskError("Risk per trade must be greater than zero when sizing by risk.")
        if self.sizing_mode is SizingMode.PERCENT_EQUITY and self.percent_equity <= 0:
            raise RiskError("Percent of equity must be greater than zero.")
        if self.sizing_mode is SizingMode.FIXED_UNITS and self.fixed_units <= 0:
            raise RiskError("Fixed position size must be greater than zero.")
        if self.sizing_mode is SizingMode.FIXED_CASH and self.fixed_cash <= 0:
            raise RiskError("Fixed cash per trade must be greater than zero.")
        if self.use_margin and self.margin_per_unit <= 0 and self.margin_percent <= 0:
            raise RiskError("Margin must be greater than zero when margin is enabled.")


@dataclass
class SessionSettings:
    """Time-of-day and day-of-week filters, evaluated in the instrument's timezone."""

    enabled: bool = False
    start: str = "09:30"
    end: str = "16:00"
    timezone: str = ""
    """Empty means the instrument's own timezone, which is what the line above
    promises and what the strategy compiler has always done.

    It used to default to ``"America/New_York"``, and that default was applied
    even for a CME instrument carrying ``America/Chicago`` -- so a scripted
    ``SessionSettings(enabled=True)`` on NQ filtered 09:30-16:00 New York while
    every other part of the application read those bars as Chicago. On a
    30-minute NQ series that was 71 trades against 49, and nothing said so.

    A strategy saved with an explicit zone keeps it; only the default changed."""
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    """Monday is 0.  Bars on other weekdays are not tradeable."""
    flat_at_session_end: bool = True
    """Close any open position on the last in-session bar of each day."""


@dataclass
class ExitSettings:
    """Protective exits attached to every position the strategy opens."""

    stop_loss_enabled: bool = False
    stop_loss_mode: str = "atr"
    """One of ``atr``, ``percent``, ``points`` or ``r_multiple``."""
    stop_loss_value: float = 1.5
    take_profit_enabled: bool = False
    take_profit_mode: str = "atr"
    take_profit_value: float = 3.0
    trailing_enabled: bool = False
    trailing_mode: str = "atr"
    trailing_value: float = 2.0
    trailing_activate_at_r: float = 0.0
    """Only start trailing once the trade is this many R in profit; ``0`` = immediately."""
    breakeven_at_r: float = 0.0
    """Move the stop to entry once the trade reaches this many R; ``0`` disables."""
    atr_period: int = 14
    max_bars_in_trade: int = 0
    """Time stop in bars; ``0`` disables."""
    partial_exits: tuple[tuple[float, float], ...] = ()
    """``((fraction, r_multiple), ...)`` -- e.g. ``((0.5, 1.0),)`` takes half off at 1R."""


@dataclass
class ExecutionSettings:
    """How the simulated broker turns signals into fills."""

    signal_execution: SignalExecution = SignalExecution.NEXT_OPEN
    intrabar_priority: IntrabarPriority = IntrabarPriority.PESSIMISTIC
    allow_reversal: bool = True
    """A long signal while short closes the short and opens the long on the same bar."""
    close_on_opposite_signal: bool = True
    fill_limit_orders: bool = True
    limit_requires_through: float = 0.0
    """Require price to trade this many points *past* a resting limit before it
    is treated as filled.  Guards against the classic 'touched, therefore
    filled' optimism."""


# --------------------------------------------------------------------------
# Backtest configuration
# --------------------------------------------------------------------------


@dataclass
class BacktestConfig:
    """Everything a run needs besides the bars and the strategy rules."""

    starting_capital: float = 100_000.0
    risk: RiskSettings = field(default_factory=RiskSettings)
    costs: CostModel = field(default_factory=CostModel)
    session: SessionSettings = field(default_factory=SessionSettings)
    exits: ExitSettings = field(default_factory=ExitSettings)
    execution: ExecutionSettings = field(default_factory=ExecutionSettings)
    start_ts: int | None = None
    """Inclusive UTC nanosecond bound; ``None`` means from the first bar."""
    end_ts: int | None = None
    """Inclusive UTC nanosecond bound; ``None`` means to the last bar."""
    warmup_bars: int = 0
    """Bars at the start of the data reserved for indicator warm-up.  No trade
    is taken before this many bars have elapsed."""
    annualization_factor: float | None = None
    """Periods per year used by Sharpe/Sortino.  ``None`` derives it from the
    timeframe and the observed trading calendar."""
    risk_free_rate: float = 0.0
    """Annual risk-free rate as a decimal (``0.04`` = 4%)."""

    def validate(self) -> None:
        from .errors import BacktestError

        if self.starting_capital <= 0:
            raise BacktestError("Starting capital must be greater than zero.")
        self.risk.starting_capital = self.starting_capital
        self.risk.validate()
        self.costs.validate()
        if self.start_ts is not None and self.end_ts is not None and self.start_ts > self.end_ts:
            raise BacktestError("The start date must be earlier than the end date.")
        if self.warmup_bars < 0:
            raise BacktestError("Warm-up bars cannot be negative.")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def empty_float_array(n: int) -> np.ndarray:
    """An ``n``-length float64 array filled with NaN."""
    a = np.empty(n, dtype=np.float64)
    a.fill(np.nan)
    return a
