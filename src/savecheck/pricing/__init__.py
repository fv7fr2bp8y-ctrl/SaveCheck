"""Pure, dependency-free pricing logic.

This package computes rolling price statistics and the promotion "traffic
light" verdict. It depends only on the Python standard library so it can be
unit-tested without a database, network access, or any third-party packages.
"""

from .aggregates import PricePoint, PriceStats, compute_stats
from .alerts import AlertDecision, WatchRule, evaluate_watch
from .history import HistoryChart, HistoryPoint, build_chart
from .verdict import Verdict, VerdictConfig, VerdictResult, evaluate, evaluate_series

__all__ = [
    "PricePoint",
    "PriceStats",
    "compute_stats",
    "Verdict",
    "VerdictConfig",
    "VerdictResult",
    "evaluate",
    "evaluate_series",
    "HistoryChart",
    "HistoryPoint",
    "build_chart",
    "AlertDecision",
    "WatchRule",
    "evaluate_watch",
]
