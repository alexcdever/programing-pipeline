"""Project-local storage layout and migration compatibility helpers."""

from __future__ import annotations

from pathlib import Path

PIPELINE_DIR_NAME = ".pipeline"
LEGACY_PIPELINE_DIR_NAME = ".workflow"
PIPELINE_DIR_NAMES = (PIPELINE_DIR_NAME,)


class LegacyPipelineLayoutError(ValueError):
    """Raised when a project has not migrated its legacy evidence directory."""


def migrate_layout(root: Path) -> tuple[int, str]:
    """Move a legacy .workflow tree to .pipeline without overwriting files."""
    import hashlib
    import os

    legacy = root / LEGACY_PIPELINE_DIR_NAME
    canonical = root / PIPELINE_DIR_NAME
    if not legacy.exists():
        return 0, "absent"
    if canonical.exists():
        raise LegacyPipelineLayoutError("both .workflow and .pipeline exist; reconcile before migration")

    def manifest(directory: Path) -> dict[str, tuple[int, str]]:
        return {
            path.relative_to(directory).as_posix(): (
                path.stat().st_size,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in directory.rglob("*")
            if path.is_file()
        }

    before = manifest(legacy)
    os.rename(legacy, canonical)
    if before != manifest(canonical):
        raise LegacyPipelineLayoutError("migration changed file contents")
    return len(before), "migrated"


def active_pipeline_dir(root: Path) -> Path:
    """Return the canonical directory; legacy projects must migrate first."""
    return root / PIPELINE_DIR_NAME


def metrics_dirs(root: Path) -> list[Path]:
    """Return only the canonical metrics directory."""
    return [root / PIPELINE_DIR_NAME / "metrics"]


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
    """Find the project root for the canonical evidence layout."""
    if directory.parent.name == PIPELINE_DIR_NAME:
        return directory.parent.parent
    return directory


def layout_parts(path: Path) -> tuple[str, ...]:
    """Return the supported layout components found in a path."""
    return tuple(part for part in path.parts if part in PIPELINE_DIR_NAMES)
