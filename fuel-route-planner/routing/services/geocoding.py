"""Resolve user input ("Chicago, IL", "41.88,-87.63") to coordinates.

Offline lookup against the City table is tried first so a typical request
makes zero geocoding calls. Nominatim is only a fallback for inputs that
aren't "City, ST" or coordinates (e.g. a street address).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import requests
from django.conf import settings

from routing.models import City

from .geo import in_conus, normalize_city, normalize_state

_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
_session = requests.Session()


class GeocodingError(Exception):
    pass


@dataclass
class Place:
    query: str
    label: str
    latitude: float
    longitude: float
    source: str  # "coordinates" | "city_table" | "nominatim"

    def as_dict(self):
        return {
            "query": self.query,
            "label": self.label,
            "latitude": round(self.latitude, 6),
            "longitude": round(self.longitude, 6),
            "geocoded_by": self.source,
        }


def resolve_location(text: str) -> Place:
    text = (text or "").strip()
    if not text:
        raise GeocodingError("Location is empty.")

    place = _from_coordinates(text) or _from_city_table(text) or _from_nominatim(text)
    if place is None:
        raise GeocodingError(f"Could not find a US location matching '{text}'. Try 'City, ST' or 'lat,lng'.")
    if not in_conus(place.latitude, place.longitude):
        raise GeocodingError(f"'{text}' resolves outside the contiguous United States.")
    return place


def _from_coordinates(text: str) -> Place | None:
    m = _COORD_RE.match(text)
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise GeocodingError(f"'{text}' is not a valid latitude,longitude pair.")
    return Place(text, f"{lat:.5f}, {lon:.5f}", lat, lon, "coordinates")


def _from_city_table(text: str) -> Place | None:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 2:
        return None
    # Accept "City, ST", "City, State", and "City, ST, USA".
    if parts[-1].lower() in {"usa", "us", "united states", "united states of america"}:
        parts = parts[:-1]
    if len(parts) < 2:
        return None
    # "New York" (full name) or "IL 60601" (code + ZIP).
    state = normalize_state(parts[-1]) or normalize_state(parts[-1].split()[0])
    if not state:
        return None
    city = City.objects.filter(name_key=normalize_city(parts[-2]), state=state).first()
    if city is None:
        return None
    return Place(text, f"{city.name}, {city.state}", city.latitude, city.longitude, "city_table")


def _from_nominatim(text: str) -> Place | None:
    cfg = settings.FUEL_PLANNER
    if not cfg["GEOCODER_FALLBACK_ENABLED"]:
        return None
    try:
        resp = _session.get(
            f"{cfg['GEOCODER_BASE_URL'].rstrip('/')}/search",
            params={"q": text, "format": "jsonv2", "countrycodes": "us", "limit": 1},
            headers={"User-Agent": cfg["USER_AGENT"]},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise GeocodingError(f"Geocoding service failed for '{text}': {exc}") from exc
    if not results:
        return None
    top = results[0]
    return Place(text, top.get("display_name", text), float(top["lat"]), float(top["lon"]), "nominatim")
