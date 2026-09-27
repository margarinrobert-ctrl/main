"""Exit settings as sweepable dimensions of an optimisation.

A strategy's parameters feed its indicators and rules. Its stop, target,
breakeven, trail, time stop and ATR period live in ``ExitSettings`` and used to
be fixed through a sweep -- so "what stop suits this entry?" could only be
answered by hand. Here each of them gets a name, ``exits.<field>``, that the
optimiser, the holdout, walk-forward and the Bayesian sampler accept exactly
like a parameter. The engine lifts the ``exits.`` names out of the overrides
and applies them to the exit settings of the run.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from ..core.errors import ParameterError
from ..indicators.base import ParamSpec

__all__ = ["PREFIX", "SWEEPABLE", "split_overrides", "apply_exit_overrides",
           "exit_parameters", "is_exit_name", "exit_param_spec"]

PREFIX = "exits."

#: field -> (kind, minimum, maximum), the same bounds the Risk panel's exit
#: form enforces, so a value the optimiser ranks is always one Apply can set.
#: A stop, target or trail of 0 is not a tight exit, it is NO exit -- the
#: engine reads 0 as "off" -- so those start just above it, where the form
#: does; switching an exit off is a different strategy, not a sweep value.
SWEEPABLE: dict[str, tuple[str, float, float | None]] = {
    "stop_loss_value": ("float", 0.0001, 1e6),
    "take_profit_value": ("float", 0.0001, 1e6),
    "breakeven_at_r": ("float", 0.0, 1e6),
    "breakeven_offset": ("float", 0.0, 1e6),
    "trailing_value": ("float", 0.0001, 1e6),
    "trailing_activate_at_r": ("float", 0.0, 1e6),
    "atr_period": ("int", 1.0, 500.0),
    "max_bars_in_trade": ("int", 0.0, 1_000_000.0),
}

_UNITS = {"atr": "x ATR", "points": "points", "percent": "%", "r": "R",
          "r_multiple": "R"}


def is_exit_name(name: str) -> bool:
    return str(name).startswith(PREFIX)


def split_overrides(overrides: dict[str, Any] | None
                    ) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(strategy parameters, exit fields)`` from one overrides mapping."""
    params: dict[str, Any] = {}
    exits: dict[str, Any] = {}
    for key, value in dict(overrides or {}).items():
        if is_exit_name(key):
            exits[key[len(PREFIX):]] = value
        else:
            params[key] = value
    return params, exits


def apply_exit_overrides(settings: Any, values: dict[str, Any]) -> Any:
    """A copy of ``settings`` with the swept exit fields set.

    Raises :class:`ParameterError` naming an unknown field or a value below
    what the field allows, rather than running a combination that means
    nothing.
    """
    if not values:
        return settings
    changes: dict[str, Any] = {}
    for field, raw in values.items():
        if field not in SWEEPABLE:
            raise ParameterError(
                f"'{PREFIX}{field}' is not an exit setting that can be swept. "
                f"These can: {', '.join(PREFIX + f for f in SWEEPABLE)}.")
        kind, minimum, maximum = SWEEPABLE[field]
        try:
            value: Any = int(round(float(raw))) if kind == "int" else float(raw)
        except (TypeError, ValueError) as exc:
            raise ParameterError(
                f"'{PREFIX}{field}' must be a number, not '{raw}'.") from exc
        if value < minimum:
            off = (" A value of 0 switches that exit off, which is a different "
                   "strategy; untick it in the exit settings instead."
                   if value <= 0 < minimum else "")
            raise ParameterError(
                f"'{PREFIX}{field}' must be at least {minimum:g}; the sweep "
                f"asked for {value:g}.{off}")
        if maximum is not None and value > maximum:
            raise ParameterError(
                f"'{PREFIX}{field}' must be at most {maximum:g}; the sweep "
                f"asked for {value:g}.")
        changes[field] = value
    return dataclasses.replace(settings, **changes)


def exit_parameters(exits: Any) -> list[ParamSpec]:
    """The exit settings this strategy actually uses, as sweepable rows.

    Only settings that are switched on are offered: sweeping the take profit
    of a strategy with no take profit would run the same backtest N times.
    The default is the current value; the bounds are wide enough to sweep
    from a quarter of it to four times it.
    """
    rows: list[ParamSpec] = []

    def add(field: str, label: str, value: float) -> None:
        kind, minimum, maximum = SWEEPABLE[field]
        value = float(value)
        if kind == "int":
            hi = max(int(value) * 4, int(value) + 20)
            if maximum is not None:
                hi = min(hi, int(maximum))
            rows.append(ParamSpec(PREFIX + field, label, "int", int(value),
                                  int(minimum), hi, 1,
                                  help=f"Exit setting '{field}', swept."))
        else:
            hi = max(value * 4, 1.0)
            if maximum is not None:
                hi = min(hi, float(maximum))
            step = 0.25 if hi <= 10 else 1.0 if hi <= 400 else 5.0
            rows.append(ParamSpec(PREFIX + field, label, "float", value,
                                  float(minimum), hi, step,
                                  help=f"Exit setting '{field}', swept."))

    uses_atr = False
    if exits.stop_loss_enabled:
        unit = _UNITS.get(exits.stop_loss_mode, exits.stop_loss_mode)
        add("stop_loss_value", f"Stop loss ({unit})", exits.stop_loss_value)
        uses_atr |= exits.stop_loss_mode == "atr"
    if exits.take_profit_enabled:
        unit = _UNITS.get(exits.take_profit_mode, exits.take_profit_mode)
        add("take_profit_value", f"Take profit ({unit})", exits.take_profit_value)
        uses_atr |= exits.take_profit_mode == "atr"
    if float(exits.breakeven_at_r) > 0:
        unit = _UNITS.get(getattr(exits, "breakeven_mode", "r"), "R")
        add("breakeven_at_r", f"Breakeven at ({unit})", exits.breakeven_at_r)
        add("breakeven_offset", "Breakeven secures (points)",
            getattr(exits, "breakeven_offset", 0.0))
        uses_atr |= getattr(exits, "breakeven_mode", "r") == "atr"
    if exits.trailing_enabled:
        unit = _UNITS.get(exits.trailing_mode, exits.trailing_mode)
        add("trailing_value", f"Trailing stop ({unit})", exits.trailing_value)
        uses_atr |= exits.trailing_mode == "atr"
        if float(exits.trailing_activate_at_r) > 0:
            unit = _UNITS.get(getattr(exits, "trailing_activate_mode", "r"), "R")
            add("trailing_activate_at_r", f"Trail starts at ({unit})",
                exits.trailing_activate_at_r)
    if exits.max_bars_in_trade:
        add("max_bars_in_trade", "Time stop (bars)", exits.max_bars_in_trade)
    if uses_atr:
        add("atr_period", "ATR period (for the exits)", exits.atr_period)
    return rows


def exit_param_spec(name: str) -> ParamSpec:
    """The definition a swept ``exits.<field>`` value is checked against."""
    field = name[len(PREFIX):] if is_exit_name(name) else name
    if field not in SWEEPABLE:
        raise ParameterError(
            f"'{name}' is not an exit setting that can be swept. These can: "
            f"{', '.join(PREFIX + f for f in SWEEPABLE)}.")
    kind, minimum, maximum = SWEEPABLE[field]
    return ParamSpec(PREFIX + field, field.replace("_", " "), kind,
                     int(minimum) if kind == "int" else minimum, minimum, maximum, 1)
