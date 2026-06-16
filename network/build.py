"""
Walk-network assembly: turn parsed Overpass elements into a segmentized
GeoDataFrame ready for factor-module scoring.

CRS rules (per DESIGN.md §7d):
  - All length / buffer math happens in EPSG:32616 (UTM 16N).
  - Canonical store/serve geometry stays in EPSG:4326 (WGS84).
  - ``length_m`` is computed once in 32616 and carried as a column — never
    recompute it from the WGS84 geometry.
"""

from __future__ import annotations

from math import ceil

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.ops import substring

from network.overpass import is_walk_eligible

WGS84 = "EPSG:4326"
UTM16N = "EPSG:32616"

TAG_COLUMNS = [
    "highway", "sidewalk", "sidewalk:left", "sidewalk:right",
    "footway", "foot", "maxspeed", "lanes", "width", "name",
    "access", "wheelchair", "kerb", "surface", "service",
]


def ways_to_gdf(
    ways: list[dict],
    nodes_by_id: dict[int, tuple[float, float]],
) -> gpd.GeoDataFrame:
    """Assemble OSM ways into a WGS84 GeoDataFrame.

    Each row is one way. Columns: ``osm_way_id`` (int), ``tags`` (dict —
    temporary, dropped before write), ``geometry`` (LineString in WGS84).

    Ways with fewer than two resolvable nodes are skipped (defensive against
    truncated Overpass responses).
    """
    records: list[dict] = []
    geometries: list[LineString] = []
    for w in ways:
        pts = [nodes_by_id[n] for n in w.get("nodes", []) if n in nodes_by_id]
        if len(pts) < 2:
            continue
        records.append({
            "osm_way_id": int(w["id"]),
            "tags": w.get("tags") or {},
        })
        geometries.append(LineString(pts))
    gdf = gpd.GeoDataFrame(records, geometry=geometries, crs=WGS84)
    return gdf


def filter_walk_eligible(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep only walk-eligible rows per :func:`network.overpass.is_walk_eligible`."""
    mask = gdf["tags"].apply(is_walk_eligible)
    return gdf.loc[mask].reset_index(drop=True)


def segmentize_edges(
    gdf_wgs84: gpd.GeoDataFrame,
    target_m: float = 25.0,
    min_tail_m: float = 3.0,
) -> gpd.GeoDataFrame:
    """Cut each way into ~``target_m`` substrings; assign ``segment_id`` + ``length_m``.

    Math is done in EPSG:32616; the returned GeoDataFrame is back in WGS84.
    ``length_m`` is the 32616 length of each child substring.

    Tail pieces shorter than ``min_tail_m`` are merged into the previous segment
    rather than emitted, to avoid degenerate sub-meter rows.

    ``segment_id`` is ``f"{osm_way_id}-{segment_index:04d}"`` — zero-padded so
    lexical sort matches spatial order along the way.
    """
    if gdf_wgs84.empty:
        return gdf_wgs84.copy()

    proj = gdf_wgs84.to_crs(UTM16N)

    child_rows: list[dict] = []
    child_geoms: list[LineString] = []

    for row in proj.itertuples(index=False):
        geom = row.geometry
        L = float(geom.length)
        if L <= 0:
            continue

        n = max(1, ceil(L / target_m))
        cuts = [(i * target_m, min((i + 1) * target_m, L)) for i in range(n)]

        if len(cuts) >= 2 and (cuts[-1][1] - cuts[-1][0]) < min_tail_m:
            prev_a, _ = cuts[-2]
            cuts = cuts[:-2] + [(prev_a, L)]

        parent_attrs = {
            "osm_way_id": row.osm_way_id,
            "tags": row.tags,
        }
        for idx, (a, b) in enumerate(cuts):
            child = substring(geom, a, b)
            if child.is_empty or child.length <= 0:
                continue
            child_rows.append({
                **parent_attrs,
                "segment_index": idx,
                "segment_id": f"{row.osm_way_id}-{idx:04d}",
                "length_m": float(child.length),
            })
            child_geoms.append(child)

    proj_children = gpd.GeoDataFrame(child_rows, geometry=child_geoms, crs=UTM16N)
    result = proj_children.to_crs(WGS84)
    result = result.set_index("segment_id", drop=False)
    result.index.name = "segment_id"
    return result


def explode_tags(
    gdf: gpd.GeoDataFrame,
    keys: list[str] = TAG_COLUMNS,
) -> gpd.GeoDataFrame:
    """Flatten the ``tags`` dict column into typed string columns.

    OSM-tag string semantics (e.g., ``maxspeed="35 mph"``, ``lanes="2;3"``) are
    preserved as-is — numeric coercion is the factor modules' job.

    Drops the raw ``tags`` dict column before returning (pyarrow round-trips
    dict columns inconsistently across versions, and downstream consumers
    should work off explicit columns anyway).
    """
    out = gdf.copy()
    for k in keys:
        out[k] = out["tags"].apply(lambda t, k=k: t.get(k) if isinstance(t, dict) else None)
    out = out.drop(columns=["tags"])
    return out


def slice_around(
    gdf: gpd.GeoDataFrame,
    lonlat: tuple[float, float],
    radius_m: float = 500.0,
) -> tuple[gpd.GeoDataFrame, float]:
    """Keep rows whose centroid falls inside a ``radius_m`` buffer of ``lonlat``.

    Buffer + centroid distance are computed in EPSG:32616. Returns
    ``(sliced_gdf, used_radius_m)`` — the radius is echoed back so the
    caller can record which value actually shipped.
    """
    if gdf.empty:
        return gdf.copy(), radius_m

    proj = gdf.to_crs(UTM16N)
    anchor = gpd.GeoSeries([Point(lonlat)], crs=WGS84).to_crs(UTM16N).iloc[0]
    buffer = anchor.buffer(radius_m)
    centroids = proj.geometry.centroid
    mask = centroids.within(buffer)
    sliced = gdf.loc[mask.values].copy()
    return sliced, radius_m
