"""slope.py — slope_risk and barrier factor module.

Data source: USGS 3DEP 1/3 arc-second (~10 m) bare-earth DEM
             Public AWS Open Data COG tiles (no API key, no rate limits):
             prd-tnm/StagedProducts/Elevation/13/TIFF/current/<tile>/USGS_13_<tile>.tif
             Read via rioxarray over HTTP; the corridor's 1-degree tile(s) are
             derived from the bbox at runtime.

             Why 3DEP and not OpenMeteo / Copernicus GLO-30:
               - OpenMeteo's elevation API is rate-limited (weighted per location),
                 so a full corridor took 13-45 min of 429 backoffs.
               - Copernicus GLO-30 is a DSM (surface model) — it includes buildings,
                 bridges and trees, producing impossible grades (>100%) next to
                 structures. 3DEP is bare earth, so pedestrian grades are realistic.
             US-only, which covers the Gillem corridor and its Atlanta backup.

Scoring: grade = rise / run where rise = |elevation difference| between segment
         endpoints (sampled from the DEM) and run = projected segment length in
         metres (EPSG:32616).
         slope_risk scales linearly:
           grade <= 5%    → 0.0  (comfortable walking)
           grade >= 8.33% → 1.0  (ADA running-slope limit)
         barrier = True when grade > 10% (effectively impassable for wheelchairs)

Null policy: DEM unreachable or an endpoint falls outside coverage → grade treated
             as 0.0 (slope_risk = 0.0, barrier = False). This is the orchestrator's
             documented null default for an unknown slope — not a claim that the
             segment is flat.

Returns a tuple (slope_risk: pd.Series, barrier: pd.Series[bool]) indexed by segment_id.
"""
from __future__ import annotations

import logging
import math

import geopandas as gpd
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_DEM_BASE = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current"
_BBOX_PAD_DEG = 0.005  # small pad so edge segments still sample inside the tile

# ADA-referenced grade thresholds
_GRADE_COMFORTABLE = 0.05    # 5% — no penalty
_GRADE_ADA_LIMIT = 0.0833    # 8.33% — maps to score = 1.0
_GRADE_BARRIER = 0.10        # 10% — impassable for wheelchairs


def _tiles_for_bbox(bbox: tuple[float, float, float, float]) -> list[str]:
    """3DEP tile names covering `bbox` (min_lon, min_lat, max_lon, max_lat).

    Tiles are 1x1 degree, named by their NW corner: n<north-edge>w<west-magnitude>,
    e.g. n34w085 covers lat 33-34, lon -85..-84.
    """
    minlon, minlat, maxlon, maxlat = bbox
    tiles: list[str] = []
    for north in range(math.ceil(minlat), math.ceil(maxlat) + 1):
        for wmag in range(math.ceil(-maxlon), math.ceil(-minlon) + 1):
            tiles.append(f"n{north:02d}w{wmag:03d}")
    return tiles


def _open_dem(bbox: tuple[float, float, float, float]):
    """Open and merge the 3DEP tile(s) covering `bbox`, clipped to the bbox.

    Returns a 2-D DataArray, or None if no tile could be read. A missing
    rioxarray/rasterio is a deployment error and is re-raised loudly.
    """
    try:
        import rioxarray as rxr
        from rioxarray.merge import merge_arrays
    except ImportError as exc:
        raise RuntimeError(
            "slope.py requires rioxarray + rasterio. "
            "Run `pip install rioxarray rasterio` in the prebake environment and retry."
        ) from exc

    clipped = []
    for tile in _tiles_for_bbox(bbox):
        url = f"{_DEM_BASE}/{tile}/USGS_13_{tile}.tif"
        try:
            da = rxr.open_rasterio(url, masked=True, lock=False).rio.clip_box(*bbox)
            clipped.append(da)
            logger.info("slope.py: opened 3DEP tile %s", tile)
        except Exception as exc:
            # Tile may not exist (ocean / no coverage) or not overlap the bbox.
            logger.warning("slope.py: 3DEP tile %s unavailable (%s)", tile, exc)

    if not clipped:
        return None

    dem = clipped[0] if len(clipped) == 1 else merge_arrays(clipped)
    return dem.squeeze(drop=True)


def score(segments: gpd.GeoDataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (slope_risk, barrier) both indexed by segment_id.

    slope_risk: float in [0, 1]
    barrier: bool (True = effectively impassable for wheelchairs)
    """
    zeros = pd.Series(0.0, index=segments["segment_id"], dtype=float)
    no_barrier = pd.Series(False, index=segments["segment_id"], dtype=bool)

    minx, miny, maxx, maxy = segments.to_crs(4326).total_bounds
    bbox = (minx - _BBOX_PAD_DEG, miny - _BBOX_PAD_DEG,
            maxx + _BBOX_PAD_DEG, maxy + _BBOX_PAD_DEG)

    dem = _open_dem(bbox)
    if dem is None:
        # Null policy: no DEM → unknown slope, scored as 0.0
        logger.warning("slope.py: no DEM available; slope_risk=0.0 for all segments")
        return zeros, no_barrier

    try:
        import xarray as xr

        # Sample endpoint elevations in the DEM's own CRS; run length in metres.
        pts = segments.to_crs(dem.rio.crs).geometry
        starts = pts.apply(lambda ln: ln.coords[0])
        ends = pts.apply(lambda ln: ln.coords[-1])
        sx = xr.DataArray([c[0] for c in starts], dims="seg")
        sy = xr.DataArray([c[1] for c in starts], dims="seg")
        ex = xr.DataArray([c[0] for c in ends], dims="seg")
        ey = xr.DataArray([c[1] for c in ends], dims="seg")

        z0 = dem.sel(x=sx, y=sy, method="nearest").to_numpy().astype(float)
        z1 = dem.sel(x=ex, y=ey, method="nearest").to_numpy().astype(float)
        run = segments.to_crs(32616).geometry.length.to_numpy()

        with np.errstate(divide="ignore", invalid="ignore"):
            grade = np.where(run >= 1.0, np.abs(z1 - z0) / run, 0.0)
        # Null policy: endpoints outside coverage (NaN) → grade 0.0
        grade = np.nan_to_num(grade, nan=0.0)

        span = _GRADE_ADA_LIMIT - _GRADE_COMFORTABLE
        slope_risk = pd.Series(
            np.clip((grade - _GRADE_COMFORTABLE) / span, 0.0, 1.0),
            index=segments["segment_id"], dtype=float,
        )
        barrier = pd.Series(grade > _GRADE_BARRIER, index=segments["segment_id"], dtype=bool)

        logger.info(
            "slope.py: graded %d segments (risk_mean=%.3f, barriers=%d)",
            len(grade), float(slope_risk.mean()), int(barrier.sum()),
        )
        return slope_risk, barrier

    except Exception as exc:
        logger.warning("slope.py: DEM processing failed (%s); slope_risk=0.0", exc)
        return zeros, no_barrier
