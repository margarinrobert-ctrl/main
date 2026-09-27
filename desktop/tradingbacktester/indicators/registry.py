"""Convenience access to the populated indicator registry.

``base`` owns the registry machinery and ``library`` owns the indicators
themselves; importing *this* module gets you both, already wired together.  It
exists so that the UI, the strategy compiler and the tests never have to
remember that the registry is only populated as a side effect of importing the
library::

    from tradingbacktester.indicators.registry import compute, list_indicators

    for d in list_indicators("Oscillators"):
        print(d.key, d.name)
    rsi = compute("RSI", bars, {"period": 14})["value"]

Everything here is a thin wrapper over :data:`REGISTRY`; there is no second
source of truth.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from . import library as _library          # noqa: F401  -- import populates REGISTRY
from .base import (REGISTRY, IndicatorDef, IndicatorRegistry, ParamSpec,
                   nan_prefix, rolling_window, safe_divide)
from .library import register_all

log = logging.getLogger(__name__)

__all__ = [
    "REGISTRY", "IndicatorDef", "IndicatorRegistry", "ParamSpec",
    "register_all", "list_indicators", "get_indicator", "compute",
    "indicator_keys", "categories", "by_category", "default_params",
    "nan_prefix", "rolling_window", "safe_divide",
]

# Importing the library registers the indicators; this re-checks that the full
# required set arrived, so a broken build fails at import rather than halfway
# through a backtest.
register_all()
log.debug("indicator registry ready: %d indicators in %d categories",
          len(REGISTRY.all()), len(REGISTRY.categories()))


def list_indicators(category: str | None = None) -> list[IndicatorDef]:
    """Every registered indicator, sorted by category then display name.

    Pass ``category`` to filter -- the comparison is case-insensitive because
    the value usually comes from a combo box.
    """
    items = REGISTRY.all()
    if category is None:
        return items
    wanted = str(category).strip().lower()
    return [d for d in items if d.category.lower() == wanted]


def get_indicator(key: str) -> IndicatorDef:
    """Look up one indicator definition, raising ``IndicatorError`` if unknown."""
    return REGISTRY.get(key)


def indicator_keys() -> list[str]:
    """Sorted registry keys -- handy for tests and for serialisation checks."""
    return sorted(d.key for d in REGISTRY.all())


def categories() -> list[str]:
    """The category names, sorted, for building a grouped menu."""
    return REGISTRY.categories()


def by_category() -> dict[str, list[IndicatorDef]]:
    """Indicators grouped by category, in menu order."""
    return REGISTRY.by_category()


def default_params(key: str) -> dict[str, Any]:
    """The default parameter values of one indicator, ready to be edited."""
    return REGISTRY.get(key).default_params()


def compute(key: str, bars, params: dict[str, Any] | None = None,
            source: str | None = None) -> dict[str, np.ndarray]:
    """Run an indicator and return ``{output_name: float64 array}``.

    Parameters are validated and defaulted first, so ``compute("EMA", bars)`` is
    a complete call.  ``source`` is ignored by indicators that need the whole
    bar (ATR, VWAP, ADX and friends).
    """
    return REGISTRY.compute(key, bars, params, source)
