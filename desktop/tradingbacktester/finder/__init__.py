"""Automatic strategy search, with the discipline that makes it worth running.

See :mod:`.search` for the protocol and :mod:`.control` for the reason a
backtest result on its own is not evidence.
"""

from .autosearch import (AutoSearchReport, Sweep, auto_search,
                         format_auto_search, plan)
from .candidates import Candidate, TEMPLATES, all_candidates, build_spec
from .control import ControlResult, analytic_control, sampled_control
from .outcomes import Geometry, OutcomeCache, build_outcomes, select_sequential
from .overfit import (DeflatedSharpe, PBOResult, deflated_sharpe,
                      probability_of_overfitting)
from .report import format_report
from .search import Finding, FinderReport, find_strategies
from .styles import STYLES, TradingStyle, style

__all__ = [
    "AutoSearchReport", "Sweep", "auto_search", "format_auto_search",
    "plan",
    "Candidate", "ControlResult", "DeflatedSharpe", "Finding", "FinderReport",
    "Geometry", "OutcomeCache", "PBOResult", "STYLES", "TEMPLATES",
    "TradingStyle", "all_candidates", "analytic_control", "build_outcomes",
    "build_spec", "deflated_sharpe", "find_strategies", "format_report",
    "probability_of_overfitting", "sampled_control", "select_sequential",
    "style",
]
