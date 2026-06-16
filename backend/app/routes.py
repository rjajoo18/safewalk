"""API route handlers."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.directions import fetch_walking_routes, route_to_geojson
from app.models import HealthResponse, ScoreRequest, ScoreResponse, RouteResult
from app.scoring import build_explanation, resolve_weights, score_route

logger = logging.getLogger(__name__)

router = APIRouter()

SIDEWALK_SERVICE_URL = (
    "https://services2.arcgis.com/zLeajbicrDRLQcny/ArcGIS/rest/services/"
    "Sidewalks_Inventory/FeatureServer/2/query"
)
MARTA_AREA_ENVELOPE = "-84.52,33.61,-84.20,33.97"
SIDEWALK_PAGE_SIZE = 2000


def sidewalk_quality(sidewalk_cov: float | None) -> str:
    if sidewalk_cov is None:
        return "partial"
    if sidewalk_cov >= 0.75:
        return "full"
    if sidewalk_cov >= 0.25:
        return "partial"
    return "none"


def sidewalk_inventory_quality(properties: dict) -> str:
    rating = str(properties.get("SWCIRating", "")).lower()
    sidewalk_type = str(properties.get("SidewalkType", "")).lower()
    condition = str(properties.get("ObservedCondition", "")).lower()

    if "no sidewalk" in rating or "no sw" in sidewalk_type or "no sw" in condition:
        return "none"
    if "excellent" in rating or "good" in rating:
        return "full"
    if "fair" in rating or "poor" in rating:
        return "partial"
    return "full"


def fetch_arc_sidewalks() -> dict:
    features = []

    try:
        with httpx.Client(timeout=12) as client:
            for offset in range(0, 20000, SIDEWALK_PAGE_SIZE):
                response = client.get(
                    SIDEWALK_SERVICE_URL,
                    params={
                        "f": "geojson",
                        "where": "1=1",
                        "outFields": "OBJECTID,SW_ID,StreetName,SidewalkType,ObservedCondition,SWCIRating",
                        "returnGeometry": "true",
                        "outSR": "4326",
                        "geometry": MARTA_AREA_ENVELOPE,
                        "geometryType": "esriGeometryEnvelope",
                        "inSR": "4326",
                        "spatialRel": "esriSpatialRelIntersects",
                        "resultRecordCount": str(SIDEWALK_PAGE_SIZE),
                        "resultOffset": str(offset),
                    },
                )
                response.raise_for_status()
                page_features = response.json().get("features", [])

                for feature in page_features:
                    if feature.get("geometry", {}).get("type") != "LineString":
                        continue
                    properties = feature.get("properties") or {}
                    properties["quality"] = sidewalk_inventory_quality(properties)
                    if properties["quality"] == "none":
                        continue
                    feature["properties"] = properties
                    features.append(feature)

                if len(page_features) < SIDEWALK_PAGE_SIZE:
                    break
    except Exception:
        logger.exception("ARC sidewalk fetch failed")
        return {"type": "FeatureCollection", "features": []}

    return {"type": "FeatureCollection", "features": features}


def score_routes(request: ScoreRequest, http_request: Request) -> ScoreResponse:
    """Core scoring logic — runs in threadpool (sync handler)."""
    settings = http_request.app.state.settings
    segment_store = http_request.app.state.segment_store

    weights = resolve_weights(request.weights, request.profile)
    profile = request.profile or "day"

    try:
        candidates = fetch_walking_routes(
            origin=request.origin,
            dest=request.dest,
            access_token=settings.mapbox_access_token,
        )
    except Exception as exc:
        logger.exception("Mapbox Directions failed")
        raise HTTPException(status_code=502, detail=f"Directions API error: {exc}") from exc

    scored: list[RouteResult] = []
    for candidate in candidates:
        segments = segment_store.snap_route(candidate.geometry, weights, profile)
        route_score = score_route(segments, weights, profile)
        geojson = route_to_geojson(segments, route_score)
        explanation = build_explanation(segments, weights, profile)

        scored.append(
            RouteResult(
                score=round(route_score, 4) if route_score != float("inf") else 9999.0,
                minutes=round(candidate.duration_seconds / 60.0, 1),
                geojson=geojson,
                explanation=explanation,
            )
        )

    scored.sort(key=lambda r: r.score)

    if not scored:
        raise HTTPException(status_code=404, detail="No routes found")

    safest = scored[0]
    alternatives = scored[1:]

    return ScoreResponse(safest=safest, alternatives=alternatives)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/api/sidewalks/")
def get_sidewalks(http_request: Request) -> dict:
    segment_store = http_request.app.state.segment_store
    gdf = segment_store.gdf

    if gdf.empty:
        return fetch_arc_sidewalks()

    sidewalks = gdf.to_crs(4326)
    features = []
    for _, row in sidewalks.iterrows():
        geometry = row.geometry
        if geometry.geom_type != "LineString":
            continue
        quality = sidewalk_quality(row.get("sidewalk_cov"))
        if quality == "none":
            continue

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "quality": quality,
                },
                "geometry": geometry.__geo_interface__,
            }
        )

    return {"type": "FeatureCollection", "features": features}


@router.post("/score", response_model=ScoreResponse)
def post_score(request: ScoreRequest, http_request: Request) -> ScoreResponse:
    return score_routes(request, http_request)
