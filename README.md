# safewalk

Safe-walk routing + crowdsourced gap-mapping for MARTA first/last mile. See [DESIGN.md](DESIGN.md) for the full engineering spec.

## Backend (R2)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Real R3 network + factor layers (recommended after pulling origin)
python scripts/bootstrap_scored_segments.py

# Or stub grid for offline contract testing only
# python scripts/generate_stub_parquet.py

uvicorn app.main:app --reload --port 8000
```

Data flow: `data/sample_network.parquet` (R3) → `bootstrap_scored_segments.py` → `backend/data/scored_segments.parquet` → API.

API docs at http://localhost:8000/docs. See [backend/README.md](backend/README.md) for endpoint contracts.
