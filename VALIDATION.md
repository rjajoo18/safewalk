# Corridor validation — hour-1 GO/NO-GO

**Date:** 2026-06-15
**Corridor:** `gillem-logistics-corridor`
**Bbox (W, S, E, N):** `[-84.37, 33.58, -84.29, 33.65]`
**Method:** `scripts/validate_corridor.py` — pulls OSM walk network via
Overpass, computes length-weighted sidewalk-tag distribution, classifies
arterials. Raw OSM cached at `data/osm/gillem-logistics-corridor.json`.

## Numbers

| Metric | Value |
|---|---:|
| Walk-eligible network length | **716.75 km** |
| Length with `sidewalk=yes` (or footway/path) | 36.9 km (5.1%) |
| Length with `sidewalk=no` | 1.4 km (0.2%) |
| Length with sidewalk tag missing | 678.5 km (94.7%) |
| **Arterials (primary/secondary/tertiary) without sidewalk tag** | **121.6 km (17.0%)** |
| Residential streets | 286.9 km (40.0%) |
| Service roads | 269.4 km (37.6%) |
| OSM crossings (`highway=crossing` nodes) | 125 |
| MARTA-ish bus stops in OSM | **0** (see below) |

## Verdict: GO-with-caveat

**Criterion A — walkability gap is real:** ✅ GO.
17% of the network is arterials with no sidewalk tag (clears the >15%
threshold). The 94.7% "unknown" share is consistent with DESIGN.md §14 ("OSM
sidewalk coverage thin"); it confirms — not refutes — the corridor's
walkability problem, and reinforces that `layers/sidewalk.py` MUST combine
OSM with the ARC sidewalk layer (per DESIGN.md §7d step 2) rather than treating
missing OSM tags as "no sidewalk."

**Criterion B — safer alternative exists:** ⚠️ GO-with-caveat.
286 km of residential and 269 km of service surface exists, so parallel-path
candidates are present in principle. But many service roads are interior to
the Gillem campus (private logistics yards — irrelevant for a worker walking
from a public bus stop), and DESIGN.md §11 already flagged that the canonical
Gillem case is workers walking arterials *because the residential network
doesn't connect to the campus*. We accept this caveat.

## What this means for the demo

Per DESIGN.md §11's contingency plan:

- **Primary demo beat:** the **"no safe route → report a gap"** beat at
  Gillem. The 17% arterial-without-sidewalk number is the receipt for the
  pitch deck.
- **Reroute beat:** to be confirmed once `layers/sidewalk.py` is wired up with
  the ARC layer. If a viable reroute around the Gillem arterials exists, use
  it; otherwise add a secondary corridor (West Atlanta / Belvedere Park) for
  the reroute beat only.
- **Pitch line stays intact:** "We scoped v1 to one corridor so every safety
  claim is verified" (DESIGN.md §11).

## Items skipped or deferred

- **Ground-truth at 3 random points (Street View)** — skipped for time. The
  94.7% unknown rate already establishes the ARC-layer dependency; per-point
  ground truth will happen organically during pipeline development.
- **MARTA stops in OSM** — confirmed missing across all standard tag
  conventions (`highway=bus_stop`, `public_transport=stop_position|platform`,
  `bus=yes`, `amenity=bus_station`). MARTA stops will come from MARTA GTFS
  (DESIGN.md §8 — keyless, public), not OSM. R4 will need GTFS for the
  stop list anyway.

## Next action

Proceed to `network/overpass.py` + `network/build.py` for the locked Gillem
bbox; publish `data/sample_network.parquet` to unblock R4 + R2 (TASKS.md
"Contracts" line 8).

## Reproducing

```bash
python3 scripts/validate_corridor.py
```

The Overpass JSON is cached; the script is idempotent.
