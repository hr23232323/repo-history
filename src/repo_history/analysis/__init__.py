"""Pluggable repo-history analysis.

The framework (context loading, the analyzer registry, the result contract) is
fixed; analysis *methods* are swappable plugins. Importing this package registers
the built-in methods.
"""

from __future__ import annotations

from .base import (
    AnalysisContext,
    AnalysisResult,
    Analyzer,
    CommitStats,
    Episode,
    available,
    get_analyzer,
    load_context,
    register,
    run_analysis,
)

# Importing the module triggers registration of the built-in method(s).
from . import mechanical  # noqa: E402,F401  (import for side effect: registration)

__all__ = [
    "AnalysisContext",
    "AnalysisResult",
    "Analyzer",
    "CommitStats",
    "Episode",
    "available",
    "get_analyzer",
    "load_context",
    "register",
    "run_analysis",
]
