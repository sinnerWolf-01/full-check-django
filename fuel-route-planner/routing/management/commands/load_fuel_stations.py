"""Load the fuel price CSV and geocode every station once, up front.

Geocoding happens here (offline, against a US cities dataset) so that API
requests never geocode stations at runtime.

    python manage.py load_fuel_stations
    python manage.py load_fuel_stations --csv path/to/fuel.csv --nominatim-fallback
"""
import csv
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from routing.models import City, FuelStation
from routing.services.geo import normalize_city, normalize_state
from routing.services.station_index import reset_station_index

DEFAULT_CSV = "data/fuel-prices-for-be-assessment.csv"
DEFAULT_CITIES = "data/us_cities.csv"
CITIES_URLS = [
    "https://raw.githubusercontent.com/kelvins/US-Cities-Database/main/csv/us_cities.csv",
    "https://raw.githubusercontent.com/kelvins/US-Cities-Database/master/csv/us_cities.csv",
]


def _pick(header: list[str], *candidates: str) -> str:
    lookup = {h.strip().lower(): h for h in header}
    for c in candidates:
        if c.lower() in lookup:
            return lookup[c.lower()]
    raise CommandError(f"CSV is missing a column like {candidates[0]!r}. Found: {header}")


class Command(BaseCommand):
    help = "Import fuel stations from the price CSV and geocode them to city coordinates."

    def add_arguments(self, parser):
        parser.add_argument("--csv", default=DEFAULT_CSV, help=f"Fuel price CSV (default: {DEFAULT_CSV})")
        parser.add_argument("--cities", default=DEFAULT_CITIES,
                            help=f"US cities CSV; downloaded automatically if missing (default: {DEFAULT_CITIES})")
        parser.add_argument("--nominatim-fallback", action="store_true",
                            help="Geocode cities missing from the dataset via Nominatim (1 request/second).")

    def handle(self, *args, **opts):
        base = Path(settings.BASE_DIR)
        csv_path = (base / opts["csv"]) if not Path(opts["csv"]).is_absolute() else Path(opts["csv"])
        cities_path = (base / opts["cities"]) if not Path(opts["cities"]).is_absolute() else Path(opts["cities"])
        if not csv_path.exists():
            raise CommandError(f"Fuel price CSV not found at {csv_path}")

        self.allow_online = opts["nominatim_fallback"]
        self._load_cities(cities_path)
        coords = {(c.name_key, c.state): (c.latitude, c.longitude) for c in City.objects.all()}

        rows = self._read_fuel_csv(csv_path)
        # One entry per normalised city ("ALBANY" and "Albany" are the same place).
        missing_map = {}
        for r in rows:
            k = (r["city_key"], r["state"])
            if k not in coords:
                missing_map.setdefault(k, r["city"])
        missing = sorted((k[0], k[1], city) for k, city in missing_map.items())

        if missing and opts["nominatim_fallback"]:
            coords.update(self._nominatim(missing))

        stations, located = [], 0
        for r in rows:
            ll = coords.get((r["city_key"], r["state"]))
            if ll:
                located += 1
            stations.append(FuelStation(
                opis_id=r["opis_id"], name=r["name"], address=r["address"], city=r["city"],
                state=r["state"], rack_id=r["rack_id"], retail_price=r["price"],
                latitude=ll[0] if ll else None, longitude=ll[1] if ll else None,
                geocode_source="city" if ll else "",
            ))

        with transaction.atomic():
            FuelStation.objects.all().delete()
            FuelStation.objects.bulk_create(stations, batch_size=2000)
        reset_station_index()

        unlocated = len(rows) - located
        self.stdout.write(self.style.SUCCESS(
            f"Imported {len(rows)} stations; {located} geocoded, {unlocated} without coordinates."
        ))
        if unlocated:
            sample = ", ".join(f"{city}, {st}" for _, st, city in missing[:10])
            self.stdout.write(f"Unmatched cities include: {sample}. "
                              f"Re-run with --nominatim-fallback to geocode them online.")

    # ------------------------------------------------------------------ cities
    def _download_cities(self, path: Path) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        for url in CITIES_URLS:
            self.stdout.write(f"Downloading US cities dataset from {url} ...")
            try:
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
            except requests.RequestException as exc:
                self.stdout.write(f"  failed: {exc}")
                continue
            path.write_bytes(resp.content)
            return True
        return False

    def _load_cities(self, path: Path):
        if City.objects.exists() and not path.exists():
            return
        if not path.exists():
            if not self._download_cities(path):
                if self.allow_online:
                    self.stdout.write(self.style.WARNING(
                        "Cities dataset unavailable; all station cities will be geocoded via Nominatim."))
                    return
                raise CommandError(
                    f"Could not download the cities dataset. Either download {CITIES_URLS[0]} "
                    f"manually to {path}, or re-run with --nominatim-fallback."
                )

        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            h = reader.fieldnames or []
            c_city = _pick(h, "CITY", "city", "name", "city_ascii")
            c_state = _pick(h, "STATE_CODE", "state_id", "state", "state_code")
            c_lat = _pick(h, "LATITUDE", "lat", "latitude")
            c_lon = _pick(h, "LONGITUDE", "lng", "lon", "longitude")
            seen, cities = set(), []
            for row in reader:
                state = normalize_state(row[c_state] or "")
                name = (row[c_city] or "").strip()
                if not state or not name:
                    continue
                key = (normalize_city(name), state)
                if key in seen:
                    continue
                try:
                    lat, lon = float(row[c_lat]), float(row[c_lon])
                except (TypeError, ValueError):
                    continue
                seen.add(key)
                cities.append(City(name=name, name_key=key[0], state=state, latitude=lat, longitude=lon))

        with transaction.atomic():
            City.objects.all().delete()
            City.objects.bulk_create(cities, batch_size=5000)
        self.stdout.write(f"Loaded {len(cities)} US cities.")

    # -------------------------------------------------------------- fuel csv
    def _read_fuel_csv(self, path: Path) -> list[dict]:
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            h = reader.fieldnames or []
            c_id = _pick(h, "OPIS Truckstop ID", "opis_id", "id")
            c_name = _pick(h, "Truckstop Name", "name")
            c_addr = _pick(h, "Address", "address")
            c_city = _pick(h, "City", "city")
            c_state = _pick(h, "State", "state")
            c_rack = _pick(h, "Rack ID", "rack_id")
            c_price = _pick(h, "Retail Price", "price", "retail_price")
            rows, skipped = [], 0
            for row in reader:
                state = normalize_state(row[c_state] or "")
                try:
                    price = Decimal(str(row[c_price]).strip())
                    opis_id = int(str(row[c_id]).strip())
                except (InvalidOperation, ValueError):
                    skipped += 1
                    continue
                if not state or price <= 0:
                    skipped += 1
                    continue
                city = (row[c_city] or "").strip()
                rack = str(row[c_rack] or "").strip()
                rows.append({
                    "opis_id": opis_id,
                    "name": (row[c_name] or "").strip(),
                    "address": (row[c_addr] or "").strip(),
                    "city": city,
                    "city_key": normalize_city(city),
                    "state": state,
                    "rack_id": int(rack) if rack.isdigit() else None,
                    "price": price,
                })
        if skipped:
            self.stdout.write(f"Skipped {skipped} rows (non-US state, bad price or ID).")
        return rows

    # -------------------------------------------------------------- nominatim
    def _nominatim(self, missing):
        cfg = settings.FUEL_PLANNER
        found = {}
        self.stdout.write(f"Geocoding {len(missing)} cities via Nominatim (~{len(missing)}s) ...")
        session = requests.Session()
        for n, (key, state, city) in enumerate(missing, start=1):
            if n % 100 == 0:
                self.stdout.write(f"  {n}/{len(missing)} ({len(found)} found)")
            try:
                resp = session.get(
                    f"{cfg['GEOCODER_BASE_URL'].rstrip('/')}/search",
                    params={"city": city, "state": state, "country": "USA", "format": "jsonv2", "limit": 1},
                    headers={"User-Agent": cfg["USER_AGENT"]}, timeout=10,
                )
                results = resp.json() if resp.ok else []
            except (requests.RequestException, ValueError):
                results = []
            if results:
                lat, lon = float(results[0]["lat"]), float(results[0]["lon"])
                found[(key, state)] = (lat, lon)
                City.objects.get_or_create(name_key=key, state=state,
                                           defaults={"name": city.title(), "latitude": lat, "longitude": lon})
            time.sleep(1.0)  # Nominatim usage policy
        self.stdout.write(f"Nominatim resolved {len(found)} of {len(missing)} cities.")
        return found
