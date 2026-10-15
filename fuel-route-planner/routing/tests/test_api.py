from decimal import Decimal
from unittest import mock

import numpy as np
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings

from routing.models import City, FuelStation
from routing.services.osrm import Route
from routing.services.station_index import reset_station_index

TEST_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def straight_route(*_args, **_kwargs):
    """A fake ~1,000 mile east-west route along 36N (no network)."""
    lons = np.linspace(-110.0, -92.0, 400)
    return Route(distance_miles=1000.0, duration_seconds=15 * 3600, lats=np.full(400, 36.0), lons=lons)


@override_settings(CACHES=TEST_CACHE)
class RouteApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        City.objects.create(name="Flagstaff", name_key="flagstaff", state="AZ", latitude=36.0, longitude=-110.0)
        City.objects.create(name="Little Rock", name_key="little rock", state="AR", latitude=36.0, longitude=-92.0)
        for i, (lon, price) in enumerate([(-106.0, "3.90"), (-104.0, "3.20"), (-99.0, "3.60"), (-96.0, "3.10")]):
            FuelStation.objects.create(
                opis_id=i, name=f"Stop {i}", address="I-40", city=f"Town{i}", state="NM",
                retail_price=Decimal(price), latitude=36.02, longitude=lon, geocode_source="city",
            )

    def setUp(self):
        cache.clear()
        reset_station_index()

    @mock.patch("routing.services.planner.fetch_route", side_effect=straight_route)
    def test_route_plan_returns_stops_cost_and_map(self, fetch):
        resp = self.client.get("/api/route/", {"start": "Flagstaff, AZ", "finish": "Little Rock, AR"})
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(data["meta"]["routing_api_calls"], 1)
        self.assertGreater(data["summary"]["total_fuel_cost_usd"], 0)
        self.assertGreaterEqual(data["summary"]["number_of_fuel_stops"], 1)
        self.assertEqual(data["route"]["geometry"]["type"], "LineString")
        self.assertIn(f"/api/route/{data['plan_id']}/map/", data["map_url"])
        # Gallons purchased = (1000 - 500 starting range) / 10 mpg.
        self.assertAlmostEqual(data["summary"]["total_gallons_purchased"], 50.0, places=1)

        map_resp = self.client.get(f"/api/route/{data['plan_id']}/map/")
        self.assertEqual(map_resp.status_code, 200)
        self.assertContains(map_resp, "leaflet")

    @mock.patch("routing.services.planner.fetch_route", side_effect=straight_route)
    def test_repeat_request_uses_cached_route(self, fetch):
        params = {"start": "Flagstaff, AZ", "finish": "Little Rock, AR"}
        self.client.get("/api/route/", params)
        resp = self.client.get("/api/route/", params)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(resp.json()["meta"]["routing_api_calls"], 0)

    @mock.patch("routing.services.planner.fetch_route", side_effect=straight_route)
    def test_post_json_and_coordinates(self, fetch):
        resp = self.client.post(
            "/api/route/", {"start": "36.0,-110.0", "finish": "36.0,-92.0"}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_missing_params(self):
        self.assertEqual(self.client.get("/api/route/").status_code, 400)

    def test_outside_usa_rejected(self):
        resp = self.client.get("/api/route/", {"start": "51.5,-0.12", "finish": "Little Rock, AR"})
        self.assertEqual(resp.status_code, 400)

    def test_unknown_city_rejected_without_fallback(self):
        with self.settings(FUEL_PLANNER={**settings.FUEL_PLANNER, "GEOCODER_FALLBACK_ENABLED": False}):
            resp = self.client.get("/api/route/", {"start": "Nowhereville, TX", "finish": "Little Rock, AR"})
        self.assertEqual(resp.status_code, 400)
