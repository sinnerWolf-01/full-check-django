"""Cheapest refuelling plan along a fixed route (no Django imports).

Classic "gas station problem" greedy, which is optimal when fuel can be bought
in any amount and every candidate station lies on the route:

At each station (price p), look ahead within one full tank:
  * If a cheaper station is reachable, buy only enough to get there.
  * Otherwise, if the destination is reachable on a full tank, buy just
    enough to finish.
  * Otherwise fill the tank and drive to the cheapest station in range.

The origin is treated as a station where fuel can't be bought (price = inf)
holding the starting fuel. Visiting a station without buying costs nothing,
so stops with zero gallons are dropped from the output.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

EPS = 1e-9


@dataclass(frozen=True)
class Candidate:
    mile: float          # position along the route, in miles from the start
    price: float         # USD per gallon
    payload: Any = None  # arbitrary data echoed back (station details)


@dataclass
class FuelStop:
    candidate: Candidate
    gallons: float
    cost: float
    fuel_on_arrival_miles: float


@dataclass
class FuelPlan:
    stops: list[FuelStop] = field(default_factory=list)
    total_cost: float = 0.0
    total_gallons_purchased: float = 0.0


class InfeasibleRouteError(Exception):
    def __init__(self, stuck_at_mile: float, reach_mile: float, next_station_mile: float | None):
        self.stuck_at_mile = stuck_at_mile
        self.reach_mile = reach_mile
        self.next_station_mile = next_station_mile
        gap = "no further stations" if next_station_mile is None else f"next station at mile {next_station_mile:.1f}"
        super().__init__(
            f"No fuel station within range after mile {stuck_at_mile:.1f} "
            f"(can reach mile {reach_mile:.1f}; {gap})."
        )


def plan_fuel_stops(
    candidates: list[Candidate],
    total_miles: float,
    max_range_miles: float = 500.0,
    mpg: float = 10.0,
    start_fuel_miles: float | None = None,
) -> FuelPlan:
    if max_range_miles <= 0 or mpg <= 0:
        raise ValueError("max_range_miles and mpg must be positive")
    fuel = max_range_miles if start_fuel_miles is None else min(start_fuel_miles, max_range_miles)

    # Sort by position, cheapest first at equal positions.
    stations = sorted(
        (c for c in candidates if -EPS <= c.mile <= total_miles + EPS),
        key=lambda c: (c.mile, c.price),
    )
    n = len(stations)

    plan = FuelPlan()
    pos = 0.0
    price = math.inf
    current: Candidate | None = None  # None == at the origin
    nxt = 0                            # index of first station after the current one

    def buy(gallons_in_miles: float):
        if current is None or gallons_in_miles <= EPS:
            return
        gallons = gallons_in_miles / mpg
        cost = gallons * current.price
        plan.stops.append(FuelStop(current, gallons, cost, fuel_on_arrival_miles=arrival_fuel))
        plan.total_cost += cost
        plan.total_gallons_purchased += gallons

    while True:
        arrival_fuel = fuel
        tank_limit = max_range_miles if current is not None else fuel
        reach = pos + tank_limit

        cheaper_idx = None
        cheapest_idx = None
        j = nxt
        while j < n and stations[j].mile <= reach + EPS:
            if stations[j].price < price - EPS:
                cheaper_idx = j
                break
            # "<=" prefers the farther of equally cheap stations (fewer stops).
            if cheapest_idx is None or stations[j].price <= stations[cheapest_idx].price:
                cheapest_idx = j
            j += 1

        if cheaper_idx is not None:
            target = stations[cheaper_idx]
            need = target.mile - pos
            buy(max(0.0, need - fuel))
            fuel = max(fuel, need) - need
            pos, price, current, nxt = target.mile, target.price, target, cheaper_idx + 1
            continue

        if total_miles <= reach + EPS:
            need = total_miles - pos
            buy(max(0.0, need - fuel))
            return plan

        if cheapest_idx is None:
            next_mile = stations[nxt].mile if nxt < n else None
            raise InfeasibleRouteError(pos, reach, next_mile)

        target = stations[cheapest_idx]
        buy(tank_limit - fuel)  # fill up
        fuel = tank_limit - (target.mile - pos)
        pos, price, current, nxt = target.mile, target.price, target, cheapest_idx + 1
