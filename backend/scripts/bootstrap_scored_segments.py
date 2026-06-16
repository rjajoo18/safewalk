#!/usr/bin/env python3
"""
Build backend/data/scored_segments.parquet from R3 sample network + factor layers.

Preferred path after pulling origin:
  1. R3 ships data/sample_network.parquet (real OSM, 226 segments)
  2. This script runs R3 layers (sidewalk, traffic, crossing) + R4 overlays
  3. Backend loads the enriched parquet for /route and /segment

Usage:
    cd backend
    python scripts/bootstrap_scored_segments.py
    python scripts/bootstrap_scored_segments.py --source ../data/sample_network.parquet
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import geopandas as gpd

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(REPO_ROOT))

from app.data_paths import SAMPLE_NETWORK, DEFAULT_SCORED  # noqa: E402
from layers import canopy, crash, exposure, flooding, hazards, slope  # noqa: E402
from layers import crossing, sidewalk, traffic  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("bootstrap")


def _apply_layer(name: str, gdf: gpd.GeoDataFrame, fn, column: str) -> None:
    try:
        result = fn(gdf)
        gdf[column] = result.values if hasattr(result, "values") else result
        logger.info("  %s OK", name)
    except Exception as exc:
        logger.warning("  %s skipped (%s) — using 0.0", name, exc)
        gdf[column] = 0.0


def bootstrap(source: Path, output: Path) -> gpd.GeoDataFrame:
    logger.info("Loading network from %s", source)
    gdf = gpd.read_parquet(source)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)

    logger.info("R3 layers:")
    logger.info("  sidewalk …")
    gdf["sidewalk_cov"] = sidewalk.score(gdf).values

    logger.info("  traffic …")
    gdf["traffic_risk"] = traffic.score(gdf).values

    logger.info("  crossing …")
    crossing_cols = crossing.enrich(gdf)
    for col in crossing_cols.columns:
        gdf[col] = crossing_cols[col].values

    logger.info("R4 layers:")
    _apply_layer("crash", gdf, crash.score, "crash_norm")
    _apply_layer("hazards", gdf, hazards.score, "hazard_norm")
    _apply_layer("canopy", gdf, canopy.score, "canopy_pct")
    _apply_layer("exposure", gdf, exposure.score, "exposure_norm")
    _apply_layer("flooding", gdf, flooding.score, "flooding")

    logger.info("  slope …")
    try:
        slope_risk, barrier = slope.score(gdf)
        gdf["slope_risk"] = slope_risk.values
        if "barrier" in gdf.columns:
            gdf["barrier"] = gdf["barrier"].fillna(False) | barrier.values
        else:
            gdf["barrier"] = barrier.values
        logger.info("  slope OK")
    except Exception as exc:
        logger.warning("  slope skipped (%s) — using defaults", exc)
        gdf["slope_risk"] = 0.0
        if "barrier" not in gdf.columns:
            gdf["barrier"] = False

    if "segment_id" in gdf.columns:
        gdf = gdf.set_index("segment_id", drop=False)

    return gdf


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap scored_segments.parquet")
    parser.add_argument("--source", default=str(SAMPLE_NETWORK), help="R3 network parquet")
    parser.add_argument("--out", default=str(DEFAULT_SCORED), help="Output parquet path")
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.out)

    if not source.exists():
        logger.error("Source not found: %s", source)
        logger.info("Pull latest origin or run scripts/build_sample_network.py from repo root.")
        sys.exit(1)

    enriched = bootstrap(source, output)
    output.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_parquet(output)
    logger.info("Wrote %d segments to %s", len(enriched), output)


if __name__ == "__main__":
    main()
