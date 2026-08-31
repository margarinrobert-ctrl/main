"""Research tools: which indicators predict, and what is unusual.

Two studies that share the strategy search's simulation and its controls:
:mod:`.study` ranks features by what they predict about a style's trades, and
:mod:`.anomalies` finds unusual bars and asks whether anything follows them.
"""

from .anomalies import DETECTORS, AnomalyScan, scan
from .features import Feature, all_features, compute_matrix
from .ic import ICResult, evaluate, newey_west, redundancy_groups
from .report import format_anomalies, format_study
from .study import FeatureStudy, study_features

__all__ = [
    "AnomalyScan", "DETECTORS", "Feature", "FeatureStudy", "ICResult",
    "all_features", "compute_matrix", "evaluate", "format_anomalies",
    "format_study", "newey_west", "redundancy_groups", "scan",
    "study_features",
]

from .loop import run_loop  # noqa: E402
from .loop_report import format_loop  # noqa: E402
