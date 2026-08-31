"""Capital, position sizing, costs, protective exits and session filtering.

Everything here maps onto :class:`~tradingbacktester.core.types.BacktestConfig`.
The panel is the single place a run's economics are set, so a saved backtest can
be reproduced exactly by restoring this panel's values.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...core.types import (BacktestConfig, CommissionMode, CostModel,
                           ExecutionSettings, ExitSettings, IntrabarPriority,
                           RiskSettings, SessionSettings, SignalExecution,
                           SizingMode, SlippageMode, SpreadMode)
from ..theme import PALETTE, Fonts
from .common import CollapsibleCard, FieldSpec, FormPanel

_TIMEZONES = ("America/New_York", "America/Chicago", "America/Los_Angeles",
              "Europe/London", "Europe/Berlin", "Europe/Zurich", "Asia/Tokyo",
              "Asia/Hong_Kong", "Asia/Singapore", "Australia/Sydney", "UTC")


class RiskPanel(QWidget):
    """The economics of a run: capital, size, costs, exits and session."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # -- capital and sizing ------------------------------------------
        self.capital_card = CollapsibleCard("Capital and Sizing", expanded=True)
        self.capital_form = FormPanel([
            FieldSpec("starting_capital", "Starting capital", "float", 100_000.0,
                      1.0, 1e12, 1000.0, 2, "",
                      tooltip="Account balance the simulation starts with"),
            FieldSpec("sizing_mode", "Position sizing", "choice",
                      SizingMode.FIXED_UNITS.value,
                      choices=[("Fixed units", SizingMode.FIXED_UNITS.value),
                               ("Fixed cash", SizingMode.FIXED_CASH.value),
                               ("Percent of equity", SizingMode.PERCENT_EQUITY.value),
                               ("Risk percent", SizingMode.RISK_PERCENT.value),
                               ("Volatility target", SizingMode.VOLATILITY_TARGET.value)],
                      tooltip="How the quantity for each new position is chosen"),
            FieldSpec("fixed_units", "Units per trade", "float", 1.0, 0.0001, 1e9,
                      1.0, 4,
                      tooltip="Contracts, shares or lots per position"),
            FieldSpec("fixed_cash", "Cash per trade", "float", 10_000.0, 1.0, 1e12,
                      500.0, 2),
            FieldSpec("percent_equity", "Percent of equity", "float", 10.0, 0.01,
                      500.0, 1.0, 2, " %"),
            FieldSpec("risk_percent", "Risk per trade", "float", 1.0, 0.01, 100.0,
                      0.25, 2, " %",
                      tooltip="Percentage of equity lost if the initial stop is hit"),
            FieldSpec("volatility_target_percent", "Volatility target", "float", 1.0,
                      0.01, 100.0, 0.1, 2, " %",
                      tooltip="Target per-bar position volatility as a percent of equity"),
            FieldSpec("max_position_units", "Max units", "float", 0.0, 0.0, 1e9,
                      1.0, 4, tooltip="Hard cap per position; 0 means no cap"),
            FieldSpec("max_concurrent_positions", "Max open positions", "int", 1, 1, 100),
            FieldSpec("allow_long", "Allow long trades", "bool", True),
            FieldSpec("allow_short", "Allow short trades", "bool", True),
            FieldSpec("use_margin", "Use margin", "bool", False,
                      tooltip="Reject entries whose initial margin exceeds free equity"),
            FieldSpec("margin_percent", "Initial margin", "float", 100.0, 0.1, 100.0,
                      5.0, 2, " %", enabled_by="use_margin"),
            FieldSpec("margin_per_unit", "Margin per unit", "float", 0.0, 0.0, 1e9,
                      100.0, 2, tooltip="Futures initial margin per contract; "
                                        "takes priority over the percentage when above zero",
                      enabled_by="use_margin"),
            FieldSpec("max_daily_loss", "Max daily loss", "float", 0.0, 0.0, 1e12,
                      100.0, 2, tooltip="Stop trading for the rest of the session day "
                                        "once this loss is reached; 0 disables it"),
            FieldSpec("max_daily_loss_is_percent", "Daily loss is a percent", "bool", False),
        ], label_width=118)
        self.capital_form.changed.connect(self._on_changed)
        self.capital_card.add(self.capital_form)
        lay.addWidget(self.capital_card)

        # -- costs --------------------------------------------------------
        self.cost_card = CollapsibleCard("Trading Costs", expanded=True)
        self.cost_form = FormPanel([
            FieldSpec("commission_mode", "Commission", "choice",
                      CommissionMode.PER_UNIT.value,
                      choices=[("Per unit", CommissionMode.PER_UNIT.value),
                               ("Per trade", CommissionMode.PER_TRADE.value),
                               ("Percent of notional", CommissionMode.PERCENT_NOTIONAL.value)]),
            FieldSpec("commission_value", "Commission value", "float", 0.0, 0.0,
                      1e6, 0.1, 4,
                      tooltip="Charged on each side of the trade"),
            FieldSpec("min_commission", "Minimum commission", "float", 0.0, 0.0,
                      1e6, 0.5, 2),
            FieldSpec("spread_mode", "Spread model", "choice",
                      SpreadMode.NONE.value,
                      choices=[("None", SpreadMode.NONE.value),
                               ("Half each side", SpreadMode.HALF_EACH_SIDE.value),
                               ("Full on entry", SpreadMode.FULL_ON_ENTRY.value)]),
            FieldSpec("spread_points", "Spread (points)", "float", 0.0, 0.0, 1e6,
                      0.25, 5,
                      tooltip="Bid/ask spread in price points, not ticks"),
            FieldSpec("slippage_mode", "Slippage model", "choice",
                      SlippageMode.NONE.value,
                      choices=[("None", SlippageMode.NONE.value),
                               ("Fixed points", SlippageMode.FIXED_POINTS.value),
                               ("Percent of price", SlippageMode.PERCENT.value),
                               ("Fraction of ATR", SlippageMode.ATR_FRACTION.value)]),
            FieldSpec("slippage_value", "Slippage value", "float", 0.0, 0.0, 1e6,
                      0.25, 5,
                      tooltip="Always applied against the trade's direction"),
        ], label_width=118)
        self.cost_form.changed.connect(self._on_changed)
        self.cost_card.add(self.cost_form)
        lay.addWidget(self.cost_card)

        # -- exits --------------------------------------------------------
        self.exit_card = CollapsibleCard("Stops and Targets", expanded=True)
        modes = [("ATR multiple", "atr"), ("Percent of price", "percent"),
                 ("Price points", "points")]
        self.exit_form = FormPanel([
            FieldSpec("stop_loss_enabled", "Use stop loss", "bool", False),
            FieldSpec("stop_loss_mode", "Stop mode", "choice", "atr", choices=modes,
                      enabled_by="stop_loss_enabled"),
            FieldSpec("stop_loss_value", "Stop value", "float", 1.5, 0.0001, 1e6,
                      0.1, 4, enabled_by="stop_loss_enabled"),
            FieldSpec("take_profit_enabled", "Use take profit", "bool", False),
            FieldSpec("take_profit_mode", "Target mode", "choice", "atr",
                      choices=modes + [("R multiple", "r_multiple")],
                      enabled_by="take_profit_enabled"),
            FieldSpec("take_profit_value", "Target value", "float", 3.0, 0.0001,
                      1e6, 0.1, 4, enabled_by="take_profit_enabled"),
            FieldSpec("trailing_enabled", "Use trailing stop", "bool", False),
            FieldSpec("trailing_mode", "Trail mode", "choice", "atr", choices=modes,
                      enabled_by="trailing_enabled"),
            FieldSpec("trailing_value", "Trail value", "float", 2.0, 0.0001, 1e6,
                      0.1, 4, enabled_by="trailing_enabled"),
            FieldSpec("trailing_activate_at_r", "Trail starts at", "float", 0.0,
                      0.0, 100.0, 0.25, 2, " R", enabled_by="trailing_enabled",
                      tooltip="Only start trailing once the trade is this many R "
                              "in profit; 0 trails from the entry bar"),
            FieldSpec("breakeven_at_r", "Break even at", "float", 0.0, 0.0, 100.0,
                      0.25, 2, " R",
                      tooltip="Move the stop to the entry price once the trade "
                              "reaches this many R; 0 disables it"),
            FieldSpec("atr_period", "ATR period", "int", 14, 1, 500,
                      tooltip="Period used by every ATR-based stop, target and trail"),
            FieldSpec("max_bars_in_trade", "Time stop (bars)", "int", 0, 0, 1_000_000,
                      tooltip="Close the position after this many bars; 0 disables it"),
        ], label_width=118)
        self.exit_form.changed.connect(self._on_changed)
        self.exit_card.add(self.exit_form)
        lay.addWidget(self.exit_card)

        # -- session and execution ---------------------------------------
        self.session_card = CollapsibleCard("Session and Execution", expanded=False)
        self.session_form = FormPanel([
            FieldSpec("session_enabled", "Restrict trading hours", "bool", False),
            FieldSpec("session_start", "Session start", "time", "09:30",
                      enabled_by="session_enabled"),
            FieldSpec("session_end", "Session end", "time", "16:00",
                      enabled_by="session_enabled"),
            FieldSpec("session_timezone", "Timezone", "choice", "America/New_York",
                      choices=[(tz, tz) for tz in _TIMEZONES],
                      enabled_by="session_enabled"),
            FieldSpec("flat_at_session_end", "Close positions at session end", "bool",
                      True, enabled_by="session_enabled"),
            FieldSpec("trade_monday", "Monday", "bool", True, enabled_by="session_enabled"),
            FieldSpec("trade_tuesday", "Tuesday", "bool", True, enabled_by="session_enabled"),
            FieldSpec("trade_wednesday", "Wednesday", "bool", True, enabled_by="session_enabled"),
            FieldSpec("trade_thursday", "Thursday", "bool", True, enabled_by="session_enabled"),
            FieldSpec("trade_friday", "Friday", "bool", True, enabled_by="session_enabled"),
            FieldSpec("trade_saturday", "Saturday", "bool", False, enabled_by="session_enabled"),
            FieldSpec("trade_sunday", "Sunday", "bool", False, enabled_by="session_enabled"),
            FieldSpec("signal_execution", "Order timing", "choice",
                      SignalExecution.NEXT_OPEN.value,
                      choices=[("Next bar open (realistic)", SignalExecution.NEXT_OPEN.value),
                               ("Same bar close (optimistic)", SignalExecution.THIS_CLOSE.value)],
                      tooltip="Next bar open is the only setting free of look-ahead: "
                              "a rule evaluated on a bar's close cannot transact at "
                              "that close, because the close was not known until the "
                              "bar was over."),
            FieldSpec("intrabar_priority", "If stop and target both hit", "choice",
                      IntrabarPriority.PESSIMISTIC.value,
                      choices=[("Assume the stop (pessimistic)", IntrabarPriority.PESSIMISTIC.value),
                               ("Assume the target (optimistic)", IntrabarPriority.OPTIMISTIC.value),
                               ("Infer from the bar's shape", IntrabarPriority.OHLC_PATH.value)],
                      tooltip="Bar data cannot say which barrier was reached first. "
                              "Pessimistic is the only assumption that will not "
                              "flatter the result."),
            FieldSpec("allow_reversal", "Allow direct reversals", "bool", True),
            FieldSpec("close_on_opposite_signal", "Close on opposite signal", "bool", True),
            FieldSpec("limit_requires_through", "Limit fill margin", "float", 0.0,
                      0.0, 1e6, 0.25, 4,
                      tooltip="Require price to trade this many points past a resting "
                              "limit before treating it as filled"),
            FieldSpec("risk_free_rate", "Risk-free rate", "float", 0.0, -10.0, 100.0,
                      0.25, 2, " %",
                      tooltip="Annual rate subtracted before computing Sharpe and Sortino"),
        ], label_width=140)
        self.session_form.changed.connect(self._on_changed)
        self.session_card.add(self.session_form)
        lay.addWidget(self.session_card)

        self.note = QLabel(
            "Costs and the order-timing rule change results more than most "
            "parameters. A backtest with no commission, no spread and same-bar "
            "fills is not a backtest.")
        self.note.setWordWrap(True)
        self.note.setObjectName("Hint")
        self.note.setFont(Fonts.body(8))
        lay.addWidget(self.note)

        self._sync_sizing_visibility()
        self.capital_form.changed.connect(self._sync_sizing_visibility)

    # -- behaviour -------------------------------------------------------

    def _sync_sizing_visibility(self) -> None:
        """Only the field the chosen sizing mode actually uses stays enabled."""
        mode = self.capital_form.value("sizing_mode")
        mapping = {
            SizingMode.FIXED_UNITS.value: ("fixed_units",),
            SizingMode.FIXED_CASH.value: ("fixed_cash",),
            SizingMode.PERCENT_EQUITY.value: ("percent_equity",),
            SizingMode.RISK_PERCENT.value: ("risk_percent",),
            SizingMode.VOLATILITY_TARGET.value: ("volatility_target_percent",),
        }
        all_keys = {k for keys in mapping.values() for k in keys}
        active = set(mapping.get(mode, ()))
        self.capital_form.set_enabled_keys(all_keys - active, False)
        self.capital_form.set_enabled_keys(active, True)
        self.capital_card.set_summary(
            f"{self.capital_form.value('starting_capital'):,.0f} · "
            f"{str(mode).replace('_', ' ')}")

    def _on_changed(self) -> None:
        self.changed.emit()

    # -- configuration ---------------------------------------------------

    def build_config(self, instrument: Any = None) -> BacktestConfig:
        """Assemble a :class:`BacktestConfig` from the current values."""
        c = self.capital_form.values()
        k = self.cost_form.values()
        e = self.exit_form.values()
        s = self.session_form.values()

        weekdays = tuple(i for i, key in enumerate(
            ("trade_monday", "trade_tuesday", "trade_wednesday", "trade_thursday",
             "trade_friday", "trade_saturday", "trade_sunday")) if s[key])

        risk = RiskSettings(
            starting_capital=float(c["starting_capital"]),
            sizing_mode=SizingMode(c["sizing_mode"]),
            fixed_units=float(c["fixed_units"]),
            fixed_cash=float(c["fixed_cash"]),
            percent_equity=float(c["percent_equity"]),
            risk_percent=float(c["risk_percent"]),
            volatility_target_percent=float(c["volatility_target_percent"]),
            volatility_atr_period=int(e["atr_period"]),
            max_position_units=float(c["max_position_units"]),
            max_concurrent_positions=int(c["max_concurrent_positions"]),
            max_daily_loss=float(c["max_daily_loss"]),
            max_daily_loss_is_percent=bool(c["max_daily_loss_is_percent"]),
            allow_long=bool(c["allow_long"]),
            allow_short=bool(c["allow_short"]),
            use_margin=bool(c["use_margin"]),
            margin_percent=float(c["margin_percent"]),
            margin_per_unit=float(c["margin_per_unit"]),
        )
        costs = CostModel(
            commission_mode=CommissionMode(k["commission_mode"]),
            commission_value=float(k["commission_value"]),
            min_commission=float(k["min_commission"]),
            spread_mode=SpreadMode(k["spread_mode"]),
            spread_points=float(k["spread_points"]),
            slippage_mode=SlippageMode(k["slippage_mode"]),
            slippage_value=float(k["slippage_value"]),
        )
        exits = ExitSettings(
            stop_loss_enabled=bool(e["stop_loss_enabled"]),
            stop_loss_mode=str(e["stop_loss_mode"]),
            stop_loss_value=float(e["stop_loss_value"]),
            take_profit_enabled=bool(e["take_profit_enabled"]),
            take_profit_mode=str(e["take_profit_mode"]),
            take_profit_value=float(e["take_profit_value"]),
            trailing_enabled=bool(e["trailing_enabled"]),
            trailing_mode=str(e["trailing_mode"]),
            trailing_value=float(e["trailing_value"]),
            trailing_activate_at_r=float(e["trailing_activate_at_r"]),
            breakeven_at_r=float(e["breakeven_at_r"]),
            atr_period=int(e["atr_period"]),
            max_bars_in_trade=int(e["max_bars_in_trade"]),
        )
        session = SessionSettings(
            enabled=bool(s["session_enabled"]),
            start=str(s["session_start"]),
            end=str(s["session_end"]),
            timezone=str(s["session_timezone"]),
            weekdays=weekdays or (0, 1, 2, 3, 4),
            flat_at_session_end=bool(s["flat_at_session_end"]),
        )
        execution = ExecutionSettings(
            signal_execution=SignalExecution(s["signal_execution"]),
            intrabar_priority=IntrabarPriority(s["intrabar_priority"]),
            allow_reversal=bool(s["allow_reversal"]),
            close_on_opposite_signal=bool(s["close_on_opposite_signal"]),
            limit_requires_through=float(s["limit_requires_through"]),
        )
        config = BacktestConfig(
            starting_capital=float(c["starting_capital"]),
            risk=risk, costs=costs, session=session, exits=exits,
            execution=execution,
            risk_free_rate=float(s["risk_free_rate"]) / 100.0,
        )
        config.validate()
        return config

    def apply_config(self, config: BacktestConfig) -> None:
        """Restore the panel from a config, e.g. when reopening a saved run."""
        r, k, e, s, x = (config.risk, config.costs, config.exits,
                         config.session, config.execution)
        self.capital_form.set_values({
            "starting_capital": config.starting_capital,
            "sizing_mode": r.sizing_mode.value, "fixed_units": r.fixed_units,
            "fixed_cash": r.fixed_cash, "percent_equity": r.percent_equity,
            "risk_percent": r.risk_percent,
            "volatility_target_percent": r.volatility_target_percent,
            "max_position_units": r.max_position_units,
            "max_concurrent_positions": r.max_concurrent_positions,
            "max_daily_loss": r.max_daily_loss,
            "max_daily_loss_is_percent": r.max_daily_loss_is_percent,
            "allow_long": r.allow_long, "allow_short": r.allow_short,
            "use_margin": r.use_margin, "margin_percent": r.margin_percent,
            "margin_per_unit": r.margin_per_unit,
        })
        self.cost_form.set_values({
            "commission_mode": k.commission_mode.value,
            "commission_value": k.commission_value,
            "min_commission": k.min_commission,
            "spread_mode": k.spread_mode.value, "spread_points": k.spread_points,
            "slippage_mode": k.slippage_mode.value, "slippage_value": k.slippage_value,
        })
        self.exit_form.set_values({
            "stop_loss_enabled": e.stop_loss_enabled,
            "stop_loss_mode": e.stop_loss_mode, "stop_loss_value": e.stop_loss_value,
            "take_profit_enabled": e.take_profit_enabled,
            "take_profit_mode": e.take_profit_mode,
            "take_profit_value": e.take_profit_value,
            "trailing_enabled": e.trailing_enabled, "trailing_mode": e.trailing_mode,
            "trailing_value": e.trailing_value,
            "trailing_activate_at_r": e.trailing_activate_at_r,
            "breakeven_at_r": e.breakeven_at_r, "atr_period": e.atr_period,
            "max_bars_in_trade": e.max_bars_in_trade,
        })
        weekday_values = {f"trade_{name}": (i in s.weekdays) for i, name in enumerate(
            ("monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday"))}
        self.session_form.set_values({
            "session_enabled": s.enabled, "session_start": s.start,
            "session_end": s.end, "session_timezone": s.timezone,
            "flat_at_session_end": s.flat_at_session_end,
            "signal_execution": x.signal_execution.value,
            "intrabar_priority": x.intrabar_priority.value,
            "allow_reversal": x.allow_reversal,
            "close_on_opposite_signal": x.close_on_opposite_signal,
            "limit_requires_through": x.limit_requires_through,
            "risk_free_rate": config.risk_free_rate * 100.0,
            **weekday_values,
        })
        self._sync_sizing_visibility()

    def apply_instrument_defaults(self, instrument: Any) -> None:
        """Seed commission, spread and margin from the instrument's own defaults."""
        if instrument is None:
            return
        if getattr(instrument, "default_commission", 0):
            self.cost_form.set_value("commission_value", instrument.default_commission)
            self.cost_form.set_value("commission_mode", CommissionMode.PER_UNIT.value)
        if getattr(instrument, "default_spread_points", 0):
            self.cost_form.set_value("spread_points", instrument.default_spread_points)
            self.cost_form.set_value("spread_mode", SpreadMode.HALF_EACH_SIDE.value)
        if getattr(instrument, "margin_per_unit", 0):
            self.capital_form.set_value("margin_per_unit", instrument.margin_per_unit)
        tz = getattr(instrument, "timezone", "")
        if tz and self.session_form.editor("session_timezone") is not None:
            self.session_form.set_value("session_timezone", tz)
