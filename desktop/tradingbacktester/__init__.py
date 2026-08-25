"""Trading Backtester -- a desktop backtesting platform for discretionary and
systematic traders.

The package is layered so that each part can be used without the ones above it:

``core``        value types, timeframes, the error hierarchy
``data``        loading, validating, resampling and storing market data
``indicators``  the indicator registry and library
``strategy``    the declarative strategy definition and its compiler
``engine``      order simulation, risk sizing and the backtest loop
``analytics``   performance metrics, equity curves, period returns, comparison
``optimize``    parameter sweeps
``reports``     CSV, HTML and PDF export
``storage``     the on-disk workspace
``ui``          the PySide6 desktop application

Everything below ``ui`` is importable without Qt, which is what makes the engine
scriptable and the test suite fast.
"""

from __future__ import annotations

from .config import APP_DISPLAY_NAME, APP_VERSION

__version__ = APP_VERSION
__all__ = ["APP_DISPLAY_NAME", "APP_VERSION", "__version__"]
