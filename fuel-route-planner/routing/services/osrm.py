"""Thin client for the OSRM routing API (one HTTP call per route)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import requests

METERS_PER_MILE = 1609.344

_session = requests.Session()


class RoutingError(Exception):
    pass


@dataclass
class Route:
    distance_miles: float
    duration_seconds: float
    lats: np.ndarray
    lons: np.ndarray


def fetch_route(
    start: tuple[float, float],
    finish: tuple[float, float],
    base_url: str,
    timeout: float,
    user_agent: str,
) -> Route:
    """Driving route between two (lat, lon) points, with full GeoJSON geometry."""
    (lat1, lon1), (lat2, lon2) = start, finish
    url = f"{base_url.rstrip('/')}/route/v1/driving/{lon1:.6f},{lat1:.6f};{lon2:.6f},{lat2:.6f}"
    params = {"overview": "full", "geometries": "geojson", "alternatives": "false", "steps": "false"}
    try:
        resp = _session.get(url, params=params, timeout=timeout, headers={"User-Agent": user_agent})
    except requests.RequestException as exc:
        raise RoutingError(f"Routing service unreachable: {exc}") from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise RoutingError(f"Routing service returned HTTP {resp.status_code} with a non-JSON body") from exc

    if resp.status_code != 200 or data.get("code") != "Ok" or not data.get("routes"):
        message = data.get("message") or data.get("code") or f"HTTP {resp.status_code}"
        raise RoutingError(f"No route found: {message}")

    route = data["routes"][0]
    coords = np.asarray(route["geometry"]["coordinates"], dtype=float)  # [[lon, lat], ...]
    return Route(
        distance_miles=route["distance"] / METERS_PER_MILE,
        duration_seconds=float(route["duration"]),
        lats=coords[:, 1],
        lons=coords[:, 0],
    )
