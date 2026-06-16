"""API route handlers."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.directions import fetch_walking_routes, route_to_geojson
from app.models import (
    FastRouteResult,
    HealthResponse,
    RouteResponse,
    RouteResult,
    RouteSegment,
    SafeRouteResult,
    ScoreRequest,
    ScoreResponse,
    SegmentDetailResponse,
)
from app.network import GraphRouter, serialize_segment
from app.scoring import (
    build_explanation,
    resolve_weights,
    resolve_weights_from_sliders,
    score_route,
)
from app.segment_repository import SegmentRepository

logger = logging.getLogger(__name__)

router = APIRouter()


# =========================================================================
# Request → (weights, step_free) translation
# =========================================================================

def _resolve_request_weights(req: ScoreRequest) -> tuple[dict[str, float], bool]:
    """Translate a ScoreRequest into (weights, step_free). Priority order:
      1. Explicit legacy `weights` dict → resolve_weights
      2. Explicit legacy `profile` string → resolve_weights;
         `profile="accessible"` becomes step_free=True (alias).
      3. Default → new slider path (theme + sliders, sliders may be None
         in which case theme defaults fill in).
    """
    if req.weights is not None:
        return resolve_weights(req.weights, None), False

    if req.profile is not None:
        return resolve_weights(None, req.profile), (req.profile == "accessible")

    weights = resolve_weights_from_sliders(
        sidewalks=req.sidewalks,
        safety=req.safety,
        comfort=req.comfort,
        theme=req.theme,
    )
    return weights, req.step_free


def _resolve_query_weights(
    sidewalks: int | None,
    safety: int | None,
    comfort: int | None,
    step_free: bool,
    theme: Literal["light", "dark"],
    profile: str | None,
    sidewalk_weight: float | None,
    traffic_weight: float | None,
) -> tuple[dict[str, float], bool]:
    """Same priority as _resolve_request_weights but for GET query params.

    Legacy `profile` or per-factor query params override the slider path
    when explicitly provided. Otherwise the slider path runs with theme +
    any provided slider values (None → theme defaults).
    """
    # Legacy explicit per-factor weights
    if sidewalk_weight is not None or traffic_weight is not None:
        from app.scoring import PROFILES
        base = dict(PROFILES.get(profile or "day", PROFILES["day"]))
        if sidewalk_weight is not None:
            base["sidewalk"] = float(sidewalk_weight)
        if traffic_weight is not None:
            base["traffic"] = float(traffic_weight)
        return resolve_weights(base, None), (profile == "accessible")

    # Legacy explicit profile
    if profile is not None:
        return resolve_weights(None, profile), (profile == "accessible")

    # Default: slider path
    return resolve_weights_from_sliders(
        sidewalks=sidewalks, safety=safety, comfort=comfort, theme=theme,
    ), step_free


# =========================================================================
# POST /score — Mapbox candidate scoring
# =========================================================================

def score_routes(request: ScoreRequest, http_request: Request) -> ScoreResponse:
    """Core scoring logic — runs in threadpool (sync handler)."""
    settings = http_request.app.state.settings
    segment_store = http_request.app.state.segment_store

    weights, step_free = _resolve_request_weights(request)

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
        segments = segment_store.snap_route(candidate.geometry, weights, step_free=step_free)
        route_score = score_route(segments, weights, step_free=step_free)
        geojson = route_to_geojson(segments, route_score)
        explanation = build_explanation(segments, weights, step_free=step_free)

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


@router.post("/score", response_model=ScoreResponse)
def post_score(request: ScoreRequest, http_request: Request) -> ScoreResponse:
    return score_routes(request, http_request)


# =========================================================================
# GET /route — Dijkstra walkable-graph routing
# =========================================================================

def _to_route_segments(segments: list[dict], include_risk: bool) -> list[RouteSegment]:
    output: list[RouteSegment] = []
    for seg in segments:
        serialized = serialize_segment(seg, risk=seg.get("risk") if include_risk else None)
        output.append(RouteSegment(**serialized))
    return output


@router.get("/route", response_model=RouteResponse)
def get_route(
    http_request: Request,
    origin_lat: float = Query(..., ge=-90, le=90),
    origin_lng: float = Query(..., ge=-180, le=180),
    dest_lat: float = Query(..., ge=-90, le=90),
    dest_lng: float = Query(..., ge=-180, le=180),
    # Preferred: 3 sliders + step-free toggle + theme
    sidewalks: int | None = Query(default=None, ge=0, le=100),
    safety:    int | None = Query(default=None, ge=0, le=100),
    comfort:   int | None = Query(default=None, ge=0, le=100),
    step_free: bool = Query(default=False),
    theme: Literal["light", "dark"] = Query(default="light"),
    # Legacy back-compat (deprecated; ignored when sliders or step_free are set)
    profile: str | None = Query(default=None, pattern="^(day|night|accessible)$"),
    sidewalk_weight: float | None = Query(default=None, ge=0, le=1),
    traffic_weight:  float | None = Query(default=None, ge=0, le=1),
) -> RouteResponse:
    graph: GraphRouter = http_request.app.state.graph_router
    if graph.walkable_gdf.empty:
        raise HTTPException(status_code=503, detail="Walkable network is not loaded")

    weights, resolved_step_free = _resolve_query_weights(
        sidewalks, safety, comfort, step_free, theme,
        profile, sidewalk_weight, traffic_weight,
    )

    try:
        safe_segments, fast_segments, mean_risk, safe_distance, fast_distance, _ = graph.route(
            origin_lon=origin_lng,
            origin_lat=origin_lat,
            dest_lon=dest_lng,
            dest_lat=dest_lat,
            weights=weights,
            step_free=resolved_step_free,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    explanation = build_explanation(safe_segments, weights, step_free=resolved_step_free)

    return RouteResponse(
        safe_route=SafeRouteResult(
            segments=_to_route_segments(safe_segments, include_risk=True),
            total_risk=round(mean_risk, 6),
            distance_m=round(safe_distance, 2),
            explanation=explanation,
        ),
        fast_route=FastRouteResult(
            segments=_to_route_segments(fast_segments, include_risk=False),
            distance_m=round(fast_distance, 2),
        ),
    )


@router.get("/segment/{segment_id}", response_model=SegmentDetailResponse)
def get_segment(segment_id: str, http_request: Request) -> SegmentDetailResponse:
    repo: SegmentRepository = http_request.app.state.segment_repository
    try:
        data = repo.get_segment(segment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}") from exc

    return SegmentDetailResponse(**data)
