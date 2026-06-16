"""Resolve parquet paths relative to backend/ or repo root."""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent

DEFAULT_SCORED = BACKEND_ROOT / "data" / "scored_segments.parquet"
SAMPLE_NETWORK = REPO_ROOT / "data" / "sample_network.parquet"


def resolve_parquet_path(configured: str | Path) -> Path | None:
    """Return the first existing parquet path from configured + fallbacks."""
    configured_path = Path(configured)
    candidates = [
        configured_path,
        BACKEND_ROOT / configured_path,
        REPO_ROOT / configured_path,
        DEFAULT_SCORED,
        SAMPLE_NETWORK,
    ]
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved
    return None
