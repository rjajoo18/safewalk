"""
Build ``data/sample_network.parquet`` — a small GeoParquet of segmentized OSM
walk edges around the corridor's primary destination.

This is TASKS.md line 8 ("Publish a small **sample network** GeoParquet ... so
R4 can develop overlays and R2 can stub /score against it"). No factor columns —
just ``segment_id``, geometry in WGS84, OSM tag columns, and ``length_m``.

Slice strategy: 500 m buffer around ``corridor.primary_destination``; if the
filtered total is under 1 km, grow to 750 m then 1000 m. Hard-fail beyond that.

Reads:  ``corridor.json``, ``data/osm/<corridor.name>.json`` (cached Overpass)
Writes: ``data/sample_network.parquet``, ``data/sample_network.meta.json``
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import geopandas as gpd  # noqa: E402

from network.build import (  # noqa: E402
    explode_tags,
    filter_walk_eligible,
    segmentize_edges,
    slice_around,
    ways_to_gdf,
)
from network.overpass import load_cached_osm, parse_elements  # noqa: E402

CORRIDOR_PATH = REPO / "corridor.json"
OUT_PARQUET = REPO / "data" / "sample_network.parquet"
OUT_SIDECAR = REPO / "data" / "sample_network.meta.json"

MIN_LENGTH_M = 1000.0
RADIUS_LADDER_M = [500.0, 750.0, 1000.0]


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _assert_parquet_roundtrip(written: Path, expected_rows: int) -> None:
    g = gpd.read_parquet(written)
    assert g.crs is not None and g.crs.to_epsg() == 4326, f"CRS not 4326: {g.crs}"
    assert len(g) == expected_rows, f"row count drift: {len(g)} vs {expected_rows}"
    assert g.geometry.is_valid.all(), "invalid geometry in parquet"
    assert g.geometry.geom_type.eq("LineString").all(), "non-LineString geom in parquet"
    assert not g.geometry.is_empty.any(), "empty geometry in parquet"
    assert g.index.is_unique, "segment_id index not unique"
    assert g.index.name == "segment_id", f"index name: {g.index.name}"


def main() -> int:
    corridor = json.loads(CORRIDOR_PATH.read_text())
    name = corridor["name"]
    lonlat = tuple(corridor["primary_destination"]["lonlat"])

    cache_path = REPO / "data" / "osm" / f"{name}.json"
    print(f"loading OSM cache: {cache_path}")
    data = load_cached_osm(name)
    nodes, ways = parse_elements(data)
    print(f"  parsed nodes={len(nodes):,}  ways={len(ways):,}")

    print("building walk-eligible GeoDataFrame ...")
    gdf = ways_to_gdf(ways, nodes)
    gdf = filter_walk_eligible(gdf)
    print(f"  walk-eligible ways: {len(gdf):,}")

    print("segmentizing edges (~25 m) ...")
    seg = segmentize_edges(gdf, target_m=25.0, min_tail_m=3.0)
    print(f"  segments: {len(seg):,}  total_length_km={seg.length_m.sum() / 1000:.2f}")

    seg = explode_tags(seg)

    sliced = None
    radius_used = None
    for r in RADIUS_LADDER_M:
        cand, _ = slice_around(seg, lonlat, radius_m=r)
        total = float(cand.length_m.sum()) if len(cand) else 0.0
        print(f"  radius {r:>5.0f} m: rows={len(cand):,}  length_m={total:.1f}")
        if total >= MIN_LENGTH_M:
            sliced, radius_used = cand, r
            break
    if sliced is None:
        print(
            f"FAIL: even at {RADIUS_LADDER_M[-1]:.0f} m the slice is under "
            f"{MIN_LENGTH_M:.0f} m. Investigate before shipping.",
            file=sys.stderr,
        )
        return 1

    print(f"slice locked: radius={radius_used:.0f} m  rows={len(sliced):,}  "
          f"length_km={sliced.length_m.sum() / 1000:.3f}")

    # In-script assertions (pre-write).
    assert sliced.length_m.sum() >= MIN_LENGTH_M
    assert sliced.length_m.between(0.5, 30.0).mean() > 0.98, (
        "segment length distribution off — likely a segmentization bug"
    )
    motorway = {"motorway", "trunk", "motorway_link", "trunk_link"}
    assert not sliced["highway"].isin(motorway).any(), "walk-eligibility filter let motorway through"
    assert sliced.index.is_unique, "segment_id not unique in slice"

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        sliced.to_parquet(tmp_path)
        _assert_parquet_roundtrip(tmp_path, expected_rows=len(sliced))
        tmp_path.replace(OUT_PARQUET)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    head_ids = sorted(sliced["segment_id"].tolist())[:5]
    sidecar = {
        "row_count": int(len(sliced)),
        "total_length_m": float(sliced.length_m.sum()),
        "radius_m_used": float(radius_used),
        "anchor_lonlat": list(lonlat),
        "corridor_name": name,
        "osm_cache_sha256": _sha256_of(cache_path),
        "crs": "EPSG:4326",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "head_segment_ids": head_ids,
        "schema_columns": sorted(sliced.columns.tolist()),
    }
    OUT_SIDECAR.write_text(json.dumps(sidecar, indent=2) + "\n")
    print(f"wrote {OUT_PARQUET} ({len(sliced):,} rows)")
    print(f"wrote {OUT_SIDECAR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
