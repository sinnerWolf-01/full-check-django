"""Small, vectorised geometry helpers (no Django imports)."""
from __future__ import annotations

import re

import numpy as np

EARTH_RADIUS_MILES = 3958.7613

# Contiguous United States (lower 48 + DC). Routes must be drivable, so
# Alaska/Hawaii endpoints are rejected.
CONUS_BOUNDS = {"min_lat": 24.3, "max_lat": 49.5, "min_lon": -125.0, "max_lon": -66.8}

US_STATES = {
    "AL": "Alabama", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida",
    "GA": "Georgia", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
STATE_NAME_TO_CODE = {name.lower(): code for code, name in US_STATES.items()}

_ABBREVIATIONS = {
    "saint": "st", "sainte": "ste", "fort": "ft", "mount": "mt", "north": "n",
    "south": "s", "east": "e", "west": "w",
}


def normalize_city(name: str) -> str:
    """Normalise a city name for matching: 'St. Louis' == 'Saint Louis' == 'ST LOUIS'."""
    cleaned = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    words = [_ABBREVIATIONS.get(w, w) for w in cleaned.split()]
    return " ".join(words)


def normalize_state(value: str) -> str | None:
    value = value.strip()
    if value.upper() in US_STATES:
        return value.upper()
    return STATE_NAME_TO_CODE.get(value.lower())


def in_conus(lat: float, lon: float) -> bool:
    b = CONUS_BOUNDS
    return b["min_lat"] <= lat <= b["max_lat"] and b["min_lon"] <= lon <= b["max_lon"]


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles; accepts scalars or numpy arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def to_unit_xyz(lat, lon) -> np.ndarray:
    """Project lat/lon (degrees) onto the unit sphere for Euclidean KD-tree queries."""
    lat = np.radians(np.asarray(lat, dtype=float))
    lon = np.radians(np.asarray(lon, dtype=float))
    cos_lat = np.cos(lat)
    return np.column_stack((cos_lat * np.cos(lon), cos_lat * np.sin(lon), np.sin(lat)))


def miles_to_chord(miles):
    """Surface distance (miles) -> straight-line chord length on the unit sphere."""
    return 2.0 * np.sin(np.asarray(miles) / (2.0 * EARTH_RADIUS_MILES))


def chord_to_miles(chord):
    return 2.0 * EARTH_RADIUS_MILES * np.arcsin(np.clip(np.asarray(chord) / 2.0, 0.0, 1.0))


def cumulative_miles(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Distance along a polyline from its first vertex, per vertex."""
    seg = haversine_miles(lats[:-1], lons[:-1], lats[1:], lons[1:])
    return np.concatenate(([0.0], np.cumsum(seg)))


def resample_polyline(lats: np.ndarray, lons: np.ndarray, spacing_miles: float):
    """Return points every `spacing_miles` along the polyline plus their mile markers.

    Linear interpolation in lat/lon is fine at sub-mile spacing.
    """
    cum = cumulative_miles(lats, lons)
    total = float(cum[-1])
    if total == 0:
        return lats[:1].copy(), lons[:1].copy(), np.array([0.0])
    # Drop zero-length segments so np.interp gets strictly increasing x.
    keep = np.concatenate(([True], np.diff(cum) > 0))
    cum, lats, lons = cum[keep], lats[keep], lons[keep]
    n = max(2, int(np.ceil(total / spacing_miles)) + 1)
    marks = np.linspace(0.0, total, n)
    return np.interp(marks, cum, lats), np.interp(marks, cum, lons), marks


def downsample_indices(n: int, max_points: int) -> np.ndarray:
    """Evenly spaced indices (always keeping first and last) for trimming geometry."""
    if n <= max_points:
        return np.arange(n)
    return np.unique(np.linspace(0, n - 1, max_points).round().astype(int))
