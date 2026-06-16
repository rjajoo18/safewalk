# safewalk

Safe-walk routing + crowdsourced gap-mapping for MARTA first/last mile. See [DESIGN.md](DESIGN.md) for the engineering spec.

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
