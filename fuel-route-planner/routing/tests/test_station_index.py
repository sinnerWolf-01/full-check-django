import unittest

import numpy as np

from routing.services.geo import haversine_miles, normalize_city, resample_polyline
from routing.services.station_index import StationIndex, StationRecord


def rec(i, lat, lon, price):
    return StationRecord(i, i, f"S{i}", "", "X", "TX", price, lat, lon)


class GeoTests(unittest.TestCase):
    def test_haversine_known_distance(self):
        # Chicago -> St. Louis is ~258 miles as the crow flies.
        d = haversine_miles(41.8781, -87.6298, 38.6270, -90.1994)
        self.assertAlmostEqual(float(d), 258, delta=5)

    def test_normalize_city(self):
        self.assertEqual(normalize_city("St. Louis"), normalize_city("SAINT LOUIS"))
        self.assertEqual(normalize_city("Fort Worth "), "ft worth")

    def test_resample_spacing(self):
        lats = np.array([35.0, 35.0])
        lons = np.array([-100.0, -99.0])  # ~56.6 miles at 35N
        s_lat, s_lon, marks = resample_polyline(lats, lons, 0.5)
        self.assertAlmostEqual(marks[-1], float(haversine_miles(35, -100, 35, -99)), places=6)
        self.assertLessEqual(np.diff(marks).max(), 0.5 + 1e-9)


class StationIndexTests(unittest.TestCase):
    def setUp(self):
        # Straight east-west route along 35N from -100 to -99.
        self.lats = np.full(200, 35.0)
        self.lons = np.linspace(-100.0, -99.0, 200)
        self.marks = np.linspace(0, float(haversine_miles(35, -100, 35, -99)), 200)

    def test_finds_nearby_and_excludes_far(self):
        idx = StationIndex([
            rec(1, 35.05, -99.5, 3.0),   # ~3.5 mi off route, midway
            rec(2, 36.0, -99.5, 2.0),    # ~69 mi off route
        ])
        found = idx.stations_along_route(self.lats, self.lons, self.marks, max_detour_miles=10)
        self.assertEqual([f.station.id for f in found], [1])
        self.assertAlmostEqual(found[0].mile, self.marks[-1] / 2, delta=1.0)
        self.assertAlmostEqual(found[0].detour_miles, 3.45, delta=0.3)

    def test_keeps_cheapest_station_per_location(self):
        idx = StationIndex([rec(1, 35.0, -99.5, 3.5), rec(2, 35.0, -99.5, 3.1)])
        self.assertEqual(idx.size, 1)
        self.assertEqual(idx.records[0].id, 2)


if __name__ == "__main__":
    unittest.main()
