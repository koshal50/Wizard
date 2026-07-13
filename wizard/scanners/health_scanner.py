"""Repository health evaluation scanner.

Checks for common indicators of a well-maintained repository.
"""

from __future__ import annotations

from pathlib import Path

from wizard.models.analysis_result import HealthCheck
from wizard.utils.constants import HEALTH_CHECKS


def scan(project_path: Path) -> list[HealthCheck]:
    """Evaluate repository health through standard checks.

    Args:
        project_path: Resolved path to the project root.

    Returns:
        List of HealthCheck results.
    """
    results: list[HealthCheck] = []

    for check_def in HEALTH_CHECKS:
        result = _run_check(project_path, check_def)
        results.append(result)

    return results


def _run_check(project_path: Path, check_def: dict) -> HealthCheck:
    """Run a single health check.

    Args:
        project_path: Project root.
        check_def: Check definition from HEALTH_CHECKS constant.

    Returns:
        HealthCheck with pass/fail status.
    """
    check_id = check_def["id"]
    check_name = check_def["name"]
    passed = False
    message = ""

    # Check for specific files
    for filename in check_def.get("files", []):
        candidate = project_path / filename
        if candidate.is_file():
            passed = True
            message = f"Found: {filename}"
            break

    # Check for specific directories (if files didn't pass)
    if not passed:
        for dirname in check_def.get("dirs", []):
            candidate = project_path / dirname
            if candidate.is_dir():
                # Verify directory is not empty
                try:
                    has_content = any(candidate.iterdir())
                    if has_content:
                        passed = True
                        message = f"Found: {dirname}/"
                        break
                    else:
                        message = f"Found {dirname}/ but it is empty"
                except PermissionError:
                    message = f"Found {dirname}/ but cannot read contents"

    if not passed and not message:
        message = "Not found"

    return HealthCheck(
        check_id=check_id,
        name=check_name,
        passed=passed,
        message=message,
    )
