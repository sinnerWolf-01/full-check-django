import unittest

from routing.services.optimizer import Candidate, InfeasibleRouteError, plan_fuel_stops


def C(mile, price, name=None):
    return Candidate(mile=mile, price=price, payload=name or f"s{mile}")


class OptimizerTests(unittest.TestCase):
    def test_short_trip_needs_no_stops(self):
        plan = plan_fuel_stops([C(100, 3.0)], total_miles=400)
        self.assertEqual(plan.stops, [])
        self.assertEqual(plan.total_cost, 0)

    def test_buys_only_what_is_needed_to_finish(self):
        # 700 miles, full tank covers 500; one station at 300.
        plan = plan_fuel_stops([C(300, 4.0)], total_miles=700)
        self.assertEqual(len(plan.stops), 1)
        # Arrive at 300 with 200 mi left; need 400 to finish -> buy 200 mi = 20 gal.
        self.assertAlmostEqual(plan.stops[0].gallons, 20.0)
        self.assertAlmostEqual(plan.total_cost, 80.0)

    def test_prefers_cheaper_station_later_in_range(self):
        stations = [C(400, 5.0, "pricey"), C(450, 3.0, "cheap")]
        plan = plan_fuel_stops(stations, total_miles=900)
        self.assertEqual([s.candidate.payload for s in plan.stops], ["cheap"])
        # Arrive at 450 with 50 mi; need 450 more -> 400 mi = 40 gal at $3.
        self.assertAlmostEqual(plan.total_cost, 120.0)

    def test_fills_up_when_next_stretch_is_expensive(self):
        # Cheap at 100, expensive at 550, finish at 1000.
        stations = [C(100, 2.0, "cheap"), C(550, 6.0, "pricey")]
        plan = plan_fuel_stops(stations, total_miles=1000)
        names = [s.candidate.payload for s in plan.stops]
        self.assertEqual(names, ["cheap", "pricey"])
        # At 100 (400 left) fill 100 mi -> 10 gal @2 = 20. At 550 arrive with 50,
        # need 450 -> buy 400 mi = 40 gal @6 = 240.
        self.assertAlmostEqual(plan.total_cost, 260.0)

    def test_multiple_stops_on_long_route(self):
        stations = [C(m, 3.0 + (m % 7) / 10) for m in range(50, 2800, 60)]
        plan = plan_fuel_stops(stations, total_miles=2800)
        self.assertGreaterEqual(len(plan.stops), 5)
        # Never run dry: arrival fuel is never negative.
        for s in plan.stops:
            self.assertGreaterEqual(s.fuel_on_arrival_miles, -1e-6)
        purchased_miles = plan.total_gallons_purchased * 10
        self.assertAlmostEqual(purchased_miles + 500, 2800, places=6)

    def test_infeasible_gap_raises(self):
        with self.assertRaises(InfeasibleRouteError):
            plan_fuel_stops([C(400, 3.0)], total_miles=1200)

    def test_custom_range_and_mpg(self):
        plan = plan_fuel_stops([C(50, 2.0)], total_miles=150, max_range_miles=100, mpg=20)
        # Arrive with 50, need 100 -> buy 50 mi = 2.5 gal @2 = 5.
        self.assertAlmostEqual(plan.total_cost, 5.0)


if __name__ == "__main__":
    unittest.main()
