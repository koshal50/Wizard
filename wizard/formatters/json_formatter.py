"""JSON output formatter.

Serializes analysis and dependency results to JSON for
machine-readable output and piping to other tools.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from wizard.formatters.console import console
from wizard.models.analysis_result import AnalysisResult
from wizard.models.dependency_result import DependencyResult


def format_as_json(result: AnalysisResult | DependencyResult) -> None:
    """Print the result as formatted JSON to stdout.

    Args:
        result: An AnalysisResult or DependencyResult.
    """
    data = _serialize(result)

    # Clean up internal attributes
    if "_project_imports" in data:
        del data["_project_imports"]

    json_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    console.print(json_str, highlight=False)


def _serialize(obj: Any) -> Any:
    """Recursively serialize dataclasses, enums, and other types to JSON-compatible dicts."""
    if is_dataclass(obj) and not isinstance(obj, type):
        result = {}
        for key, value in asdict(obj).items():
            # Skip private attributes
            if key.startswith("_"):
                continue
            result[key] = _serialize(value)
        return result
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items() if not str(k).startswith("_")}
    elif isinstance(obj, (list, tuple)):
        return [_serialize(item) for item in obj]
    elif isinstance(obj, set):
        return sorted(_serialize(item) for item in obj)
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        return str(obj)
