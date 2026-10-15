"""In-memory spatial index of fuel stations (no Django imports in the core class).

All stations are loaded once per process into numpy arrays and a KD-tree over
unit-sphere coordinates, so per-request work is a few vectorised queries.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from .geo import chord_to_miles, miles_to_chord, to_unit_xyz


@dataclass(frozen=True)
class StationRecord:
    id: int
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    price: float
    latitude: float
    longitude: float


@dataclass(frozen=True)
class RouteStation:
    station: StationRecord
    mile: float           # position of the nearest route point, miles from start
    detour_miles: float   # straight-line distance from the route


class StationIndex:
    def __init__(self, records: list[StationRecord]):
        # Several stations often share a city (and therefore coordinates). Only
        # the cheapest one at a location can ever be part of an optimal plan.
        best: dict[tuple[float, float], StationRecord] = {}
        for r in records:
            key = (round(r.latitude, 5), round(r.longitude, 5))
            if key not in best or r.price < best[key].price:
                best[key] = r
        self.records = list(best.values())
        self.size = len(self.records)
        if self.size:
            self.lat = np.array([r.latitude for r in self.records])
            self.lon = np.array([r.longitude for r in self.records])
        else:
            self.lat = np.empty(0)
            self.lon = np.empty(0)

    def stations_along_route(
        self,
        route_lat: np.ndarray,
        route_lon: np.ndarray,
        route_marks: np.ndarray,
        max_detour_miles: float,
    ) -> list[RouteStation]:
        """Stations within `max_detour_miles` of a densely sampled route."""
        if not self.size or len(route_lat) == 0:
            return []

        # Cheap bounding-box prefilter (degrees; ~69 miles per degree latitude).
        pad_lat = max_detour_miles / 69.0 + 0.05
        cos_mid = max(np.cos(np.radians(float(np.mean(route_lat)))), 0.2)
        pad_lon = max_detour_miles / (69.0 * cos_mid) + 0.05
        mask = (
            (self.lat >= route_lat.min() - pad_lat) & (self.lat <= route_lat.max() + pad_lat)
            & (self.lon >= route_lon.min() - pad_lon) & (self.lon <= route_lon.max() + pad_lon)
        )
        idx = np.nonzero(mask)[0]
        if idx.size == 0:
            return []

        route_tree = cKDTree(to_unit_xyz(route_lat, route_lon))
        dist, nearest = route_tree.query(
            to_unit_xyz(self.lat[idx], self.lon[idx]),
            k=1,
            distance_upper_bound=float(miles_to_chord(max_detour_miles)),
        )
        hit = np.isfinite(dist)
        result = [
            RouteStation(
                station=self.records[i],
                mile=float(route_marks[n]),
                detour_miles=float(chord_to_miles(d)),
            )
            for i, d, n in zip(idx[hit], dist[hit], nearest[hit])
        ]
        result.sort(key=lambda rs: rs.mile)
        return result


_index: StationIndex | None = None
_lock = threading.Lock()


def get_station_index() -> StationIndex:
    """Process-wide index, loaded lazily from the database on first use."""
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                _index = _load_from_db()
    return _index


def reset_station_index():
    global _index
    with _lock:
        _index = None


def _load_from_db() -> StationIndex:
    from routing.models import FuelStation  # local import keeps this module Django-free

    rows = FuelStation.objects.filter(latitude__isnull=False, longitude__isnull=False).values_list(
        "id", "opis_id", "name", "address", "city", "state", "retail_price", "latitude", "longitude"
    )
    records = [
        StationRecord(
            id=r[0], opis_id=r[1], name=r[2], address=r[3], city=r[4], state=r[5],
            price=float(r[6]), latitude=r[7], longitude=r[8],
        )
        for r in rows
    ]
    return StationIndex(records)
