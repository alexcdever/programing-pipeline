"""Project-local storage layout and migration compatibility helpers."""

from __future__ import annotations

from pathlib import Path

PIPELINE_DIR_NAME = ".pipeline"
LEGACY_PIPELINE_DIR_NAME = ".workflow"
PIPELINE_DIR_NAMES = (PIPELINE_DIR_NAME, LEGACY_PIPELINE_DIR_NAME)


def active_pipeline_dir(root: Path) -> Path:
    """Choose where new artifacts go without breaking a legacy-only project."""
    canonical = root / PIPELINE_DIR_NAME
    legacy = root / LEGACY_PIPELINE_DIR_NAME
    if canonical.is_dir():
        return canonical
    if legacy.is_dir():
        return legacy
    return canonical


def metrics_dirs(root: Path) -> list[Path]:
    """Return metric directories from both layouts for migration-safe reads."""
    existing = [root / name / "metrics" for name in PIPELINE_DIR_NAMES if (root / name).is_dir()]
    return existing or [root / PIPELINE_DIR_NAME / "metrics"]


def is_metrics_path(path: str) -> bool:
    """Return whether a normalized project-relative path is pipeline metrics."""
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return any(
        normalized == f"{name}/metrics" or normalized.startswith(f"{name}/metrics/")
        for name in PIPELINE_DIR_NAMES
    )


def evidence_root(directory: Path) -> Path:
    """Find the project root for either supported evidence layout."""
    if directory.parent.name in PIPELINE_DIR_NAMES:
        return directory.parent.parent
    return directory


def layout_parts(path: Path) -> tuple[str, ...]:
    """Return the supported layout components found in a path."""
    return tuple(part for part in path.parts if part in PIPELINE_DIR_NAMES)
