"""
Hour-1 corridor validator for Safewalk (manual run of the corridor-validator
agent checklist — the .claude/agents/ subagent isn't loaded in this session).

Pulls OSM walk network for the Gillem bbox via Overpass, caches the raw JSON,
and reports:

  - total walk-network length (km)
  - share of length with sidewalk=no/none vs. explicit sidewalk vs. missing tag
  - count of edges by `highway` class (so we know what kind of corridor it is)
  - candidate arterial check: do Anvil Block Rd / Jonesboro Rd / Main St show
    up with the right tags?

Computes lengths with haversine — no geopandas / shapely needed (those aren't
installed on this Python). Outputs to stdout as a small report.

Per TASKS.md "Validation & de-risking" line 59 and DESIGN.md §11/§14/§17 Q2.
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import requests

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from network.overpass import WALK_ELIGIBLE, fetch_overpass  # noqa: E402

CORRIDOR_PATH = REPO / "corridor.json"
CACHE_DIR = REPO / "data" / "osm"


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    R = 6371008.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def way_length_m(way: dict, nodes: dict[int, tuple[float, float]]) -> float:
    pts = [nodes[n] for n in way["nodes"] if n in nodes]
    return sum(haversine_m(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def has_sidewalk(tags: dict) -> str:
    """Return 'yes' | 'no' | 'unknown' based on OSM sidewalk semantics."""
    sw = tags.get("sidewalk") or ""
    sw_left = tags.get("sidewalk:left") or ""
    sw_right = tags.get("sidewalk:right") or ""
    fw = tags.get("footway") or ""
    hw = tags.get("highway") or ""

    # A footway/path/pedestrian way IS itself the sidewalk equivalent.
    if hw in {"footway", "path", "pedestrian", "steps"}:
        return "yes"

    positive = {"yes", "both", "left", "right", "separate"}
    negative = {"no", "none"}

    if sw in positive or sw_left in positive or sw_right in positive:
        return "yes"
    if sw in negative and sw_left in negative and sw_right in negative:
        return "no"
    if sw in negative or sw_left in negative or sw_right in negative:
        # at least one side missing — count as no for the worst-case story
        return "no"
    return "unknown"


def main():
    corridor = json.loads(CORRIDOR_PATH.read_text())
    bbox = corridor["bbox"]
    name = corridor["name"]
    cache_path = CACHE_DIR / f"{name}.json"

    data = fetch_overpass(bbox, cache_path)
    elements = data.get("elements", [])

    nodes: dict[int, tuple[float, float]] = {}
    ways: list[dict] = []
    bus_stops: list[tuple[float, float, str]] = []
    crossings: list[dict] = []

    for el in elements:
        if el["type"] == "node":
            nodes[el["id"]] = (el["lon"], el["lat"])
            tags = el.get("tags") or {}
            if tags.get("highway") == "bus_stop" or tags.get("public_transport") == "platform":
                bus_stops.append((el["lon"], el["lat"], tags.get("name") or ""))
            if tags.get("highway") == "crossing":
                crossings.append(el)
        elif el["type"] == "way":
            ways.append(el)

    print()
    print(f"Corridor: {name}")
    print(f"Bbox    : {bbox}  (W, S, E, N)")
    print(f"Nodes   : {len(nodes):,}")
    print(f"Ways    : {len(ways):,}")
    print()

    # Walk-eligible edges only.
    walk_ways = [w for w in ways
                 if (w.get("tags") or {}).get("highway") in WALK_ELIGIBLE
                 and (w.get("tags") or {}).get("foot") != "no"
                 and (w.get("tags") or {}).get("access") not in {"no", "private"}]

    # Lengths.
    by_class_len: dict[str, float] = defaultdict(float)
    by_sidewalk_len: dict[str, float] = defaultdict(float)
    arterial_no_sidewalk_len = 0.0
    arterial_classes = {"primary", "primary_link", "secondary", "secondary_link",
                        "tertiary", "tertiary_link"}

    total_len = 0.0
    for w in walk_ways:
        L = way_length_m(w, nodes)
        if L == 0:
            continue
        total_len += L
        tags = w.get("tags") or {}
        cls = tags.get("highway") or "unknown"
        by_class_len[cls] += L
        sw = has_sidewalk(tags)
        by_sidewalk_len[sw] += L
        if cls in arterial_classes and sw in {"no", "unknown"}:
            arterial_no_sidewalk_len += L

    def km(m: float) -> str:
        return f"{m / 1000:6.2f} km"

    def pct(m: float) -> str:
        return f"{100 * m / total_len:5.1f}%" if total_len else "    n/a"

    print("Walk-eligible network")
    print(f"  total length .................... {km(total_len)}")
    print()
    print("By highway class (length)")
    for cls in sorted(by_class_len, key=lambda c: -by_class_len[c]):
        print(f"  {cls:18s} {km(by_class_len[cls])}  ({pct(by_class_len[cls])})")
    print()
    print("By sidewalk signal (length)")
    for k in ("yes", "no", "unknown"):
        print(f"  {k:10s} {km(by_sidewalk_len[k])}  ({pct(by_sidewalk_len[k])})")
    print()
    print("Arterials lacking sidewalk (the 'red route' signal)")
    print(f"  arterial + (no | unknown) sidewalk: {km(arterial_no_sidewalk_len)} "
          f"({100 * arterial_no_sidewalk_len / total_len:.1f}% of network)")
    print()
    print(f"MARTA-ish bus stops in bbox: {len(bus_stops)}")
    for lon, lat, nm in bus_stops[:10]:
        print(f"  ({lat:.4f}, {lon:.4f})  {nm[:50]}")
    if len(bus_stops) > 10:
        print(f"  ... and {len(bus_stops) - 10} more")
    print()
    print(f"OSM crossings (nodes) in bbox: {len(crossings)}")

    # Quick verdict scaffolding (the human decides; this gives the numbers).
    print()
    print("=== Verdict inputs ===")
    no_or_unknown_pct = 100 * (by_sidewalk_len["no"] + by_sidewalk_len["unknown"]) / total_len if total_len else 0
    print(f"  no-sidewalk-OR-unknown share: {no_or_unknown_pct:.1f}%")
    print(f"  arterials w/o sidewalk      : {km(arterial_no_sidewalk_len)} ({100 * arterial_no_sidewalk_len / total_len:.1f}%)")
    print(f"  bus stops to choose from    : {len(bus_stops)}")
    print()
    print("Criterion A (walkability gap real): GO if no-sidewalk-OR-unknown >15% AND")
    print("  arterials w/o sidewalk are present.")
    print("Criterion B (safer alternative exists): needs route-choice inspection — see")
    print("  raw OSM cache for residential parallels around the arterial segments.")


if __name__ == "__main__":
    main()
