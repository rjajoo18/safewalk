# Safewalk Backend

FastAPI scoring service for safe-walk routing. Wraps Mapbox Directions, snaps routes to pre-baked segment scores, and returns the safest alternative.

## Quick start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
python scripts/bootstrap_scored_segments.py   # R3 sample network + factor layers
cp .env.example .env            # add MAPBOX_ACCESS_TOKEN

uvicorn app.main:app --reload --port 8000
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check → `{"status":"ok"}` |
| POST | `/score` | Score Mapbox walking route alternatives (see DESIGN.md §7b) |
| GET | `/route` | Dijkstra safe + fast routes on the scored segment network |
| GET | `/segment/{segment_id}` | Single-segment safety breakdown from parquet |

### GET /route

Query params: `origin_lat`, `origin_lng`, `dest_lat`, `dest_lng`, `profile` (`day`|`night`|`accessible`), `sidewalk_weight` (0–1), `traffic_weight` (0–1).

Returns `safe_route` (min composite risk via Dijkstra) and `fast_route` (min distance). Origin/destination snap to the nearest walkable graph node. Only pedestrian-allowed highway types are used.

### POST /score

```json
{
  "origin": [-84.347, 33.610],
  "dest": [-84.329, 33.620],
  "profile": "night"
}
```

Optional `weights` override `profile`. Response includes `safest` + `alternatives`, each with `score`, `minutes`, `geojson`, and `explanation`.

## Project layout

```
backend/
├── app/
│   ├── main.py        # FastAPI app, CORS, lifespan
│   ├── config.py      # Settings from env
│   ├── models.py      # Pydantic request/response schemas
│   ├── routes.py      # /health, /score handlers (sync for threadpool)
│   ├── scoring.py     # Weights, profiles, segment_risk, explanations
│   ├── directions.py  # Mapbox Directions wrapper
│   ├── network.py     # Walkable graph + Dijkstra routing
│   ├── segment_repository.py  # Parquet segment lookup
│   └── segments.py    # Parquet loader + route→segment snap
├── data/
│   └── scored_segments.parquet   # from prebake.py (stub generator included)
├── scripts/
│   └── generate_stub_parquet.py
├── Dockerfile
└── requirements.txt
```

## Docker

```bash
python scripts/generate_stub_parquet.py
docker build -t safewalk-api .
docker run -p 8000:8000 -e MAPBOX_ACCESS_TOKEN=pk.xxx safewalk-api
```

## Environment

| Variable | Description |
|----------|-------------|
| `MAPBOX_ACCESS_TOKEN` | Mapbox Directions API token |
| `SCORED_SEGMENTS_PATH` | Path to pre-baked parquet (default: `data/scored_segments.parquet`) |
| `CORS_ORIGINS` | Comma-separated frontend origins |

## Contracts (R2 ↔ R3/R4)

- **Parquet schema:** `segment_id`, factor columns (`sidewalk_cov`, `traffic_risk`, …), `geometry` (WGS84)
- **Factor modules:** `layers/<factor>.py` → `score(segments) -> Series` (owned by R3/R4)
- Handlers use sync `def` so CPU-bound geo work runs in FastAPI's threadpool
