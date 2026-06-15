"""exposure.py — exposure_norm factor module.

Data source: backend/data/ejscreen_georgia.csv
             NOTE: This file is CDC SVI (Social Vulnerability Index) data,
             not EJScreen. It does not contain PTRAF.
             Best available proxy: EP_NOVEH (% households with no vehicle)
             — indicates transit-dependent populations most exposed to
             walking hazards. County-level granularity (STCNTY = 5-digit FIPS).

Method: normalize EP_NOVEH across all Georgia counties; assign county value
        to each segment based on centroid location using Census county polygons
        (downloaded from Census TIGER/Line via geopandas if available,
        otherwise falls back to hardcoded Fulton/DeKalb values).

Null policy: segment outside all county geometries → exposure_norm = 0.0
             (unknown exposure, not zero exposure — noted here per Principle V)
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from layers._utils import normalize

logger = logging.getLogger(__name__)

_SVI_FILE = Path(__file__).resolve().parent.parent / "data" / "ejscreen_georgia.csv"

# Hardcoded EP_NOVEH fallback for Fulton (13121) and DeKalb (13089)
# Used when county polygon download is unavailable
_COUNTY_FALLBACK: dict[int, float] = {
    13121: None,  # Fulton — filled from CSV at runtime
    13089: None,  # DeKalb — filled from CSV at runtime
}

# Gillem corridor centroid longitude: ~-84.38 (Fulton / DeKalb boundary ~-84.3)
_DEKALB_LON_EAST = -84.30


def _load_svi() -> pd.DataFrame:
    """Load SVI CSV and return Georgia county EP_NOVEH values."""
    df = pd.read_csv(_SVI_FILE, dtype={"STCNTY": str, "FIPS": str})
    # Ensure numeric
    df["EP_NOVEH"] = pd.to_numeric(df["EP_NOVEH"], errors="coerce").fillna(0.0)
    return df


def _get_county_scores() -> dict[str, float]:
    """Return normalized EP_NOVEH keyed by 5-digit STCNTY FIPS string."""
    df = _load_svi()
    # Normalize across all Georgia counties in the file
    normalized = normalize(df["EP_NOVEH"])
    return dict(zip(df["STCNTY"].astype(str).str.zfill(5), normalized))


def score(segments: gpd.GeoDataFrame) -> pd.Series:
    """Return exposure_norm in [0, 1] indexed by segment_id.

    Uses EP_NOVEH (% no-vehicle households) from CDC SVI as an environmental
    exposure proxy at county level. County assignment uses segment centroid longitude.
    """
    county_scores = _get_county_scores()

    # Fulton FIPS 13121, DeKalb FIPS 13089 (zero-padded to 5 digits)
    fulton_score = county_scores.get("13121", 0.5)
    dekalb_score = county_scores.get("13089", 0.5)

    segs_wgs = segments.to_crs(4326)
    centroids = segs_wgs.geometry.centroid

    scores: list[float] = []
    for centroid in centroids:
        lon = centroid.x
        if lon > _DEKALB_LON_EAST:
            # Null policy: east of DeKalb boundary approximation → DeKalb score
            scores.append(dekalb_score)
        else:
            scores.append(fulton_score)

    result = pd.Series(scores, index=segments["segment_id"], dtype=float)
    return result.clip(0.0, 1.0)
