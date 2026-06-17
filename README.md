# safewalk

Safe-walk routing + crowdsourced gap-mapping for MARTA first/last mile. See [DESIGN.md](DESIGN.md) for the engineering spec.

## Inspiration
MARTA riders in South Atlanta often get dropped a mile or more from work. At Gillem Logistics Center, workers walk 1.5–2 miles along arterials with no sidewalk after getting off the bus. Google Maps gives you the shortest path, not the safest one.

We built Safewalk for that gap: the walk to the stop is still broken even when the bus part works.

## What it does
Safewalk routes you on the safest walk between two points (MARTA stop → job, home → store, etc.), not just the fastest. You see a red default route and a green safe route side by side, with per-segment coloring and a short explanation of why they differ.

Three sliders let you weight sidewalks, safety, and comfort. There's a wheelchair toggle that skips stairs and steep grades, and a dark mode that bumps up traffic/crash weight at night. If there's no good path, you can drop a pin to report a missing sidewalk or bad crossing — it shows up live on the map for other riders and planners.

## How we built it
- Next.js + Mapbox on the frontend. FastAPI + GeoPandas on the backend. We don't run our own routing engine — we pull walking routes from Mapbox/OSRM and score them against a pre-baked parquet file where every ~25m street segment already has sidewalk, traffic, crash, hazard, shade, heat, slope, and flood scores.

- A prebake.py pipeline pulls OSM, ARC sidewalk data, GDOT traffic counts, Atlanta crash/311 data, canopy rasters, and heat APIs offline. Gap reports go into Supabase with realtime so new pins appear without a refresh. Four of us split frontend, backend/scoring, network pipeline, and hazard layers and worked off locked API contracts so nobody blocked anyone.

## Challenges we ran into
Gillem is a real walkability failure, but a lot of the residential roads on the map are private logistics yards that don't help a worker walking in from the bus. We ended up demoing both rerouting (where a safer parallel exists) and the "no safe route → report it" flow.

## Accomplishments that we're proud of
- We shipped a working scored route on a real corridor with 30k+ segments, not a mock. The slider reroute actually changes the path on the map — that's the demo moment.

- We have a clear rule we stuck to: score the road, not the neighborhood. Crime and land-use factors are out; physical hazards at specific points are in.

- Gap reporting works end to end — tap, pin appears live, feeds the hazard layer. And we validated the corridor with numbers (17% of arterials with no sidewalk tag) instead of just asserting the problem exists.

## What we learned
- You don't need to build a routing engine to add value. Wrapping existing directions and ranking alternatives by safety was the right call for a weekend.

- Pre-baking everything into parquet saved us — request-time scoring is just a spatial snap, and the demo doesn't depend on live raster pulls or flaky Wi-Fi.

- Open data is messy. Sparse tags, biased 311 reports, point-sample traffic counts — you have to document what you don't know and design around it, or your "safe route" is just confident nonsense.

## What's next for Safewalk
- Expand the bbox to more corridors, then citywide — the pipeline already takes a bounding box, it's mostly a bake-time problem.

- SMS or low-bandwidth fallback for riders without smartphones. Multimodal walk → bus → walk with MARTA stops as endpoints.

- Get the gap heatmap in front of ARC or the city as an actual sidewalk prioritization input, and fold confirmed reports back into the scoring weights over time.

## Repo layout

```
safewalk/
├── DESIGN.md              # locked engineering spec (R1)
├── SCORING.md             # slider model + API reference (gitignored — local working doc)
├── VALIDATION.md          # corridor-validation receipts + factor spot-checks
├── corridor.json          # locked corridor bbox + primary destination
├── network/               # OSM corpus → walk network builder (R3)
├── scripts/
│   ├── prebake.py         # canonical R3+R4 orchestrator → outputs/scored_segments.parquet
│   ├── build_sample_network.py
│   ├── validate_corridor.py
│   └── spot_check.py      # factor ground-truth picker
├── backend/               # FastAPI scoring service + factor modules
├── frontend/              # Next.js routing UI (submodule)
├── data/                  # cached external data (OSM, ARC, GDOT) — partially gitignored
└── outputs/               # generated scored_segments.parquet + sidecar JSON
```

## Build the scored corridor

```bash
# install Python deps
pip install -r requirements.txt
pip install -r backend/requirements.txt

# bake the corridor (full pipeline: OSM → factor scores → parquet)
python scripts/prebake.py
# → outputs/scored_segments.parquet
# → outputs/scored_segments.meta.json   (per-column stats + canary warnings)
```

Re-run is idempotent. Sidecar warnings flag any factor module that silently fell back to zeros.

## Run the backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env                                  # add MAPBOX_ACCESS_TOKEN
uvicorn app.main:app --reload --port 8000
```

API docs at http://localhost:8000/docs. Endpoint shape + slider model live in [backend/README.md](backend/README.md) and the local `SCORING.md`.

## Run the frontend

```bash
git submodule update --init                           # if you didn't clone with --recurse-submodules
cd frontend
npm install
npm run dev
```

Frontend reads `NEXT_PUBLIC_SAFEWALK_API_URL` (default empty → mock mode).

## Demo corridor

Gillem Logistics Center, Forest Park GA. Bbox + primary destination locked in `corridor.json`. Verified demo OD pair (3 distinct route geometries across slider configs) documented in `SCORING.md`.
