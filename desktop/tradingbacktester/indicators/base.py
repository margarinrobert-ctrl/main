"""The indicator registry.

An indicator is a pure function of a :class:`~tradingbacktester.data.models.BarSeries`
plus keyword parameters, returning one or more equal-length ``float64`` arrays
padded at the front with NaN for the warm-up period.

Adding an indicator is one decorated function; nothing else in the application
needs to change.  The UI reads :data:`REGISTRY` to build its dropdowns and
parameter editors, the strategy compiler reads it to evaluate rules, and the
chart reads ``plot_style`` to know how to draw the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import numpy as np

from ..core.errors import IndicatorError

IndicatorFunc = Callable[..., "np.ndarray | dict[str, np.ndarray]"]


@dataclass(frozen=True)
class ParamSpec:
    """One tunable parameter of an indicator or a strategy."""

    name: str
    label: str
    kind: str = "int"
    """``int``, ``float``, ``bool``, ``choice`` or ``source``."""
    default: Any = 14
    minimum: float | None = 1
    maximum: float | None = 5000
    step: float = 1
    choices: tuple[str, ...] = ()
    help: str = ""

    def coerce(self, value: Any) -> Any:
        """Validate and convert a user-supplied value, raising on nonsense."""
        try:
            if self.kind == "int":
                v: Any = int(round(float(value)))
            elif self.kind == "float":
                v = float(value)
            elif self.kind == "bool":
                if isinstance(value, str):
                    v = value.strip().lower() in ("1", "true", "yes", "on")
                else:
                    v = bool(value)
            else:
                v = str(value)
        except (TypeError, ValueError) as exc:
            raise IndicatorError(
                f"'{value}' is not a valid value for {self.label}.", detail=repr(exc)
            ) from exc
        if self.kind in ("int", "float"):
            if self.minimum is not None and v < self.minimum:
                raise IndicatorError(
                    f"{self.label} must be at least {self.minimum:g} (got {v:g})."
                )
            if self.maximum is not None and v > self.maximum:
                raise IndicatorError(
                    f"{self.label} must be at most {self.maximum:g} (got {v:g})."
                )
        if self.kind == "choice" and self.choices and v not in self.choices:
            raise IndicatorError(
                f"{self.label} must be one of {', '.join(self.choices)} (got '{v}')."
            )
        return v


@dataclass(frozen=True)
class IndicatorDef:
    """Registry entry describing one indicator."""

    key: str
    """Stable machine name, e.g. ``"EMA"``.  Saved inside strategy files."""
    name: str
    """Display name, e.g. ``"Exponential Moving Average"``."""
    category: str
    func: IndicatorFunc
    params: tuple[ParamSpec, ...] = ()
    outputs: tuple[str, ...] = ("value",)
    """Names of the arrays returned.  A single-output indicator returns a bare
    array and the registry wraps it as ``{"value": array}``."""
    overlay: bool = True
    """True if it is drawn on the price panel; False if it needs its own panel."""
    plot_style: dict[str, Any] = field(default_factory=dict)
    """Per-output drawing hints, e.g. ``{"value": {"color": "#4aa3ff"}}``."""
    default_source: str = "close"
    uses_source: bool = True
    """False for indicators that need the whole bar (ATR, ADX, VWAP, ...)."""
    scale_hint: str = "price"
    """``price``, ``percent``, ``oscillator_0_100``, ``zero_centred`` or ``volume``.
    Used to choose sensible panel bounds and guide lines."""
    description: str = ""
    min_bars: int = 1
    """Bars needed before the first non-NaN output, given default parameters."""

    def param_spec(self, name: str) -> ParamSpec:
        for p in self.params:
            if p.name == name:
                return p
        raise IndicatorError(f"{self.name} has no parameter called '{name}'.")

    def default_params(self) -> dict[str, Any]:
        return {p.name: p.default for p in self.params}

    def coerce_params(self, values: dict[str, Any] | None) -> dict[str, Any]:
        """Fill in defaults and validate every supplied parameter."""
        values = dict(values or {})
        out: dict[str, Any] = {}
        for p in self.params:
            out[p.name] = p.coerce(values.get(p.name, p.default))
        unknown = set(values) - {p.name for p in self.params} - {"source"}
        if unknown:
            raise IndicatorError(
                f"{self.name} does not take the parameter(s) {', '.join(sorted(unknown))}."
            )
        return out

    def warmup(self, params: dict[str, Any] | None = None) -> int:
        """Bars of warm-up implied by a given parameter set.

        The longest period the parameters name, or ``min_bars`` when they name
        none. ``min_bars`` is deliberately *not* applied as a floor on top:
        most declarations of it are simply the indicator's default period, so
        an SMA asked for a period of 1 would otherwise be told it needs twenty
        bars.

        The known limitation: a recursively smoothed indicator -- Wilder's RSI
        or ATR -- returns a number at ``period`` bars and is still settling for
        several times that. Both the engine and the strategy search take their
        warm-up from here, so they agree with each other, and neither waits
        that long. Widening it would change every existing strategy's results,
        so it is a decision to take deliberately rather than a bug to fix
        quietly.
        """
        params = params or self.default_params()
        periods = [int(v) for k, v in params.items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)
                   and ("period" in k or "length" in k or k in ("fast", "slow", "signal"))]
        return max(periods) if periods else self.min_bars


class IndicatorRegistry:
    """Name -> :class:`IndicatorDef` lookup with a decorator for registration."""

    def __init__(self) -> None:
        self._items: dict[str, IndicatorDef] = {}

    def register(self, key: str, name: str, category: str, *,
                 params: Iterable[ParamSpec] = (), outputs: Iterable[str] = ("value",),
                 overlay: bool = True, plot_style: dict[str, Any] | None = None,
                 default_source: str = "close", uses_source: bool = True,
                 scale_hint: str = "price", description: str = "",
                 min_bars: int = 1) -> Callable[[IndicatorFunc], IndicatorFunc]:
        """Decorator registering the wrapped function as an indicator."""

        def deco(func: IndicatorFunc) -> IndicatorFunc:
            k = key.upper()
            if k in self._items:
                raise IndicatorError(f"An indicator called '{k}' is already registered.")
            self._items[k] = IndicatorDef(
                key=k, name=name, category=category, func=func,
                params=tuple(params), outputs=tuple(outputs), overlay=overlay,
                plot_style=dict(plot_style or {}), default_source=default_source,
                uses_source=uses_source, scale_hint=scale_hint,
                description=description, min_bars=min_bars,
            )
            return func

        return deco

    def get(self, key: str) -> IndicatorDef:
        k = str(key).upper()
        if k not in self._items:
            raise IndicatorError(
                f"'{key}' is not an indicator this application knows about.",
                detail=f"Known: {', '.join(sorted(self._items))}",
            )
        return self._items[k]

    def has(self, key: str) -> bool:
        return str(key).upper() in self._items

    def all(self) -> list[IndicatorDef]:
        return sorted(self._items.values(), key=lambda d: (d.category, d.name))

    def categories(self) -> list[str]:
        return sorted({d.category for d in self._items.values()})

    def by_category(self) -> dict[str, list[IndicatorDef]]:
        out: dict[str, list[IndicatorDef]] = {}
        for d in self.all():
            out.setdefault(d.category, []).append(d)
        return out

    # -- evaluation ------------------------------------------------------

    def compute(self, key: str, bars, params: dict[str, Any] | None = None,
                source: str | None = None) -> dict[str, np.ndarray]:
        """Run an indicator and return ``{output_name: array}``.

        Every returned array is float64, the same length as ``bars`` and padded
        with NaN where the indicator is not yet defined.
        """
        d = self.get(key)
        kw = d.coerce_params(params)
        if d.uses_source:
            kw["source"] = source or d.default_source
        try:
            raw = d.func(bars, **kw)
        except IndicatorError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise IndicatorError(
                f"{d.name} could not be calculated with the parameters given.",
                detail=f"{type(exc).__name__}: {exc}",
            ) from exc

        n = len(bars)
        if isinstance(raw, dict):
            out = {k: np.ascontiguousarray(v, dtype="float64") for k, v in raw.items()}
        else:
            out = {d.outputs[0]: np.ascontiguousarray(raw, dtype="float64")}
        for name, arr in out.items():
            if arr.shape != (n,):
                raise IndicatorError(
                    f"{d.name} returned {arr.shape[0] if arr.ndim else '?'} values "
                    f"for {n} bars, which is a bug in the indicator.",
                )
        missing = set(d.outputs) - set(out)
        if missing:
            raise IndicatorError(
                f"{d.name} did not return its declared output(s): {', '.join(sorted(missing))}."
            )
        return out


#: The application-wide registry.  Importing
#: :mod:`tradingbacktester.indicators.library` populates it.
REGISTRY = IndicatorRegistry()


# -- small helpers shared by indicator implementations --------------------

def nan_prefix(n: int, count: int, arr: np.ndarray) -> np.ndarray:
    """Blank out the first ``count`` values of ``arr`` (length ``n``)."""
    out = np.asarray(arr, dtype="float64").copy()
    if count > 0:
        out[: min(count, n)] = np.nan
    return out


def rolling_window(a: np.ndarray, window: int) -> np.ndarray:
    """A read-only strided view with shape ``(len(a) - window + 1, window)``."""
    if window <= 0:
        raise IndicatorError("A rolling window must be at least 1 bar wide.")
    if len(a) < window:
        return np.empty((0, window), dtype=a.dtype)
    return np.lib.stride_tricks.sliding_window_view(a, window)


def safe_divide(num: np.ndarray, den: np.ndarray, fill: float = np.nan) -> np.ndarray:
    """Element-wise division that yields ``fill`` instead of raising on 0/0."""
    num = np.asarray(num, dtype="float64")
    den = np.asarray(den, dtype="float64")
    out = np.full(np.broadcast(num, den).shape, fill, dtype="float64")
    ok = np.isfinite(den) & (den != 0.0)
    np.divide(num, den, out=out, where=ok)
    return out
