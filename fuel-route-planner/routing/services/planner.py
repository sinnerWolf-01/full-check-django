"""Orchestrates one route request: geocode -> route (1 API call) -> stations -> optimise."""
from __future__ import annotations

import hashlib
import logging
import time
import uuid

import numpy as np
from django.conf import settings
from django.core.cache import cache

from .geo import downsample_indices, resample_polyline
from .geocoding import resolve_location
from .optimizer import Candidate, InfeasibleRouteError, plan_fuel_stops
from .osrm import fetch_route
from .station_index import get_station_index

logger = logging.getLogger("routing")

PLAN_KEY = "fuelplan:plan:{}"
ROUTE_KEY = "fuelplan:route:{}"


class PlanningError(Exception):
    """Route exists but can't be fuelled with the given constraints."""


def _route_cache_key(start, finish) -> str:
    raw = f"{start[0]:.5f},{start[1]:.5f};{finish[0]:.5f},{finish[1]:.5f}"
    return ROUTE_KEY.format(hashlib.sha1(raw.encode()).hexdigest())


def build_plan(start_text: str, finish_text: str, max_detour_miles: float | None = None) -> dict:
    cfg = settings.FUEL_PLANNER
    t0 = time.perf_counter()
    max_range = cfg["MAX_RANGE_MILES"]
    mpg = cfg["MILES_PER_GALLON"]
    detour = cfg["DEFAULT_MAX_DETOUR_MILES"] if max_detour_miles is None else max_detour_miles

    start = resolve_location(start_text)
    finish = resolve_location(finish_text)
    start_ll = (start.latitude, start.longitude)
    finish_ll = (finish.latitude, finish.longitude)

    # --- Routing: exactly one external call, cached for repeat requests. ---
    route_key = _route_cache_key(start_ll, finish_ll)
    route = cache.get(route_key)
    routing_calls = 0
    if route is None:
        route = fetch_route(
            start_ll, finish_ll,
            base_url=cfg["ROUTING_BASE_URL"],
            timeout=cfg["ROUTING_TIMEOUT_SECONDS"],
            user_agent=cfg["USER_AGENT"],
        )
        routing_calls = 1
        cache.set(route_key, route, cfg["PLAN_CACHE_SECONDS"])
    t_route = time.perf_counter()

    # --- Candidate stations along the route. ---
    s_lat, s_lon, marks = resample_polyline(route.lats, route.lons, cfg["ROUTE_SAMPLE_SPACING_MILES"])
    # Scale geometry miles to the road distance reported by the router so
    # mile markers and fuel use agree with the official route length.
    if marks[-1] > 0:
        marks = marks * (route.distance_miles / marks[-1])
    total_miles = float(route.distance_miles)

    along = get_station_index().stations_along_route(s_lat, s_lon, marks, detour)
    candidates = [Candidate(mile=rs.mile, price=rs.station.price, payload=rs) for rs in along]

    try:
        plan = plan_fuel_stops(candidates, total_miles, max_range_miles=max_range, mpg=mpg)
    except InfeasibleRouteError as exc:
        raise PlanningError(str(exc)) from exc
    t_plan = time.perf_counter()

    stops = []
    for i, stop in enumerate(plan.stops, start=1):
        rs = stop.candidate.payload
        st = rs.station
        stops.append({
            "stop_number": i,
            "station_id": st.id,
            "opis_id": st.opis_id,
            "name": st.name,
            "address": st.address,
            "city": st.city,
            "state": st.state,
            "latitude": st.latitude,
            "longitude": st.longitude,
            "price_per_gallon": round(st.price, 3),
            "mile_marker": round(rs.mile, 1),
            "distance_from_route_miles": round(rs.detour_miles, 1),
            "fuel_on_arrival_miles": round(stop.fuel_on_arrival_miles, 1),
            "gallons": round(stop.gallons, 2),
            "cost": round(stop.cost, 2),
        })

    keep = downsample_indices(len(route.lats), cfg["MAX_RESPONSE_GEOMETRY_POINTS"])
    line = np.column_stack((route.lons[keep], route.lats[keep])).round(5).tolist()

    plan_id = uuid.uuid4().hex
    result = {
        "plan_id": plan_id,
        "start": start.as_dict(),
        "finish": finish.as_dict(),
        "summary": {
            "total_distance_miles": round(total_miles, 1),
            "estimated_drive_time_hours": round(route.duration_seconds / 3600, 2),
            "total_fuel_cost_usd": round(plan.total_cost, 2),
            "total_gallons_purchased": round(plan.total_gallons_purchased, 2),
            "total_gallons_used": round(total_miles / mpg, 2),
            "number_of_fuel_stops": len(stops),
            "vehicle_range_miles": max_range,
            "miles_per_gallon": mpg,
            "assumptions": [
                "Vehicle starts the trip with a full tank (500 miles of range).",
                "Fuel cost counts only fuel purchased at the recommended stops.",
                f"Stations are matched to the route within {detour:g} miles (stations are geocoded to their city).",
            ],
        },
        "fuel_stops": stops,
        "route": {
            "type": "Feature",
            "properties": {"name": f"{start.label} to {finish.label}"},
            "geometry": {"type": "LineString", "coordinates": line},
        },
        "map_url": None,  # filled in by the view (needs the request host)
        "meta": {
            "routing_api_calls": routing_calls,
            "candidate_stations_on_route": len(candidates),
            "timings_ms": {
                "routing": round((t_route - t0) * 1000, 1),
                "planning": round((t_plan - t_route) * 1000, 1),
                "total": round((time.perf_counter() - t0) * 1000, 1),
            },
        },
    }
    cache.set(PLAN_KEY.format(plan_id), result, cfg["PLAN_CACHE_SECONDS"])
    logger.info(
        "Planned %s -> %s: %.0f mi, %d stops, $%.2f, %d routing call(s), %.0f ms",
        start.label, finish.label, total_miles, len(stops), plan.total_cost,
        routing_calls, result["meta"]["timings_ms"]["total"],
    )
    return result


def get_cached_plan(plan_id: str) -> dict | None:
    return cache.get(PLAN_KEY.format(plan_id))
