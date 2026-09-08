"""Indicators.

Importing this package populates :data:`REGISTRY`.  That matters because
indicators register themselves as a side effect of importing
:mod:`tradingbacktester.indicators.library`, and every other layer refers to
them by *name* -- a strategy file says ``"EMA"``, not an import path.  Without
this, ``from ..indicators.base import REGISTRY`` would hand a caller an empty
registry and every strategy would fail validation with "EMA is not an indicator
this application knows about".
"""

from __future__ import annotations

from .base import (REGISTRY, IndicatorDef, IndicatorRegistry, ParamSpec,
                   nan_prefix, rolling_window, safe_divide)
from . import library as _library  # noqa: F401  -- imported for its side effect

__all__ = ["REGISTRY", "IndicatorDef", "IndicatorRegistry", "ParamSpec",
           "nan_prefix", "rolling_window", "safe_divide"]
