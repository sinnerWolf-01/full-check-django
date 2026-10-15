# Fuel Route Planner API

A Django API that takes a start and finish location in the USA and returns:

- the driving route (GeoJSON) and an interactive map,
- the cheapest places to refuel along the way, given a 500-mile range,
- the total fuel cost at 10 miles per gallon.

Built with Django 6.1, NumPy/SciPy, and the free [OSRM](https://project-osrm.org/) routing API.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1. Put the provided price file at data/fuel-prices-for-be-assessment.csv
python manage.py migrate
python manage.py load_fuel_stations                  # imports + geocodes stations (one-time)

python manage.py runserver
```

Then open:

```
http://127.0.0.1:8000/api/route/?start=Chicago, IL&finish=Los Angeles, CA
http://127.0.0.1:8000/api/route/map/?start=New York, NY&finish=Miami, FL
```

Run the tests (no network needed; the routing call is mocked):

```bash
python manage.py test routing
```

## API

### `GET /api/route/?start=...&finish=...` (or `POST` with a JSON body)

| Parameter | Required | Example | Notes |
|---|---|---|---|
| `start` | yes | `Chicago, IL` or `41.8781,-87.6298` | "City, ST", "City, State", or "lat,lng" |
| `finish` | yes | `Denver, CO` | same formats |
| `max_detour_miles` | no | `10` | how far off the route a station may be (default 10) |

```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "finish": "Los Angeles, CA"}'
```

Response (abridged):

```json
{
  "plan_id": "4f1c…",
  "start":  {"label": "Chicago, IL", "latitude": 41.85, "longitude": -87.65, "geocoded_by": "city_table"},
  "finish": {"label": "Los Angeles, CA", "...": "..."},
  "summary": {
    "total_distance_miles": 2015.3,
    "estimated_drive_time_hours": 29.6,
    "total_fuel_cost_usd": 488.12,
    "total_gallons_purchased": 151.5,
    "number_of_fuel_stops": 4,
    "assumptions": ["Vehicle starts the trip with a full tank (500 miles of range).", "..."]
  },
  "fuel_stops": [
    {"stop_number": 1, "name": "…", "city": "…", "state": "MO", "price_per_gallon": 3.019,
     "mile_marker": 412.6, "fuel_on_arrival_miles": 87.4, "gallons": 41.3, "cost": 124.68}
  ],
  "route": {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-87.65, 41.85], "..."]}},
  "map_url": "http://127.0.0.1:8000/api/route/4f1c…/map/",
  "meta": {"routing_api_calls": 1, "candidate_stations_on_route": 312,
           "timings_ms": {"routing": 640.2, "planning": 14.8, "total": 658.1}}
}
```

- `route` is standard GeoJSON, so it can be dropped into any map tool.
- `map_url` opens an interactive Leaflet/OpenStreetMap page showing the route and numbered stops.
- `meta.routing_api_calls` shows how many routing calls the request made (1, or 0 when cached).

Errors return `{"error": "..."}` with `400` (bad input / outside the US), `422` (a stretch of
the route has no station within range), `502` (routing service failure), or `503` (no stations loaded).

### Other endpoints

- `GET /api/route/<plan_id>/map/` — map for a previously computed plan
- `GET /api/route/map/?start=...&finish=...` — compute and show the map in one step
- `GET /api/health/` — station counts

## How it works

```
start, finish ──► geocode (offline city table) ──► OSRM route (1 call, cached)
                                                       │
           stations KD-tree (built once) ◄── resample route every 0.5 mi
                                                       │
                              stations within 10 mi + mile marker
                                                       │
                              greedy cost optimiser ──► stops, cost, map
```

**One routing call per request.** Start and finish are geocoded offline against a US cities
table, so a normal request makes exactly one external call (OSRM). Identical routes are cached,
so repeats make zero. Nominatim is only used as a fallback for inputs that aren't
"City, ST" or coordinates (e.g. a street address), which keeps the worst case at three calls.

**Stations are geocoded once, up front.** The price file has addresses but no coordinates.
`load_fuel_stations` matches each station's city/state to the US cities dataset and stores
coordinates in the database. `--nominatim-fallback` geocodes any unmatched cities online
(one-time, rate-limited to 1 request/second).

**Fast spatial matching.** All stations are loaded once per process into a SciPy KD-tree.
For each request the route is resampled every half mile and stations within the detour radius
are matched to their nearest route point, which gives each station a mile marker. Several
stations in the same city share coordinates, so only the cheapest per location is kept.
Planning takes roughly 15–20 ms for a coast-to-coast route.

**Optimal fuel stops.** With fuel purchasable in any amount, this greedy strategy is optimal:

1. At each station, look ahead one full tank (500 miles).
2. If a cheaper station is in range, buy just enough to reach it.
3. Otherwise, if the destination is in range, buy just enough to finish.
4. Otherwise fill up and go to the cheapest station in range.

This was checked against an exact linear-programming solution on 3,000 random routes and
matched the optimum on every one.

## Assumptions

- The vehicle starts with a full tank; total cost covers fuel bought at the recommended stops.
- Stations are located at their city's centroid (the price file has no coordinates), so they are
  matched to the route within 10 miles. Detour distance is reported per stop but not added to
  fuel use.
- Locations must be in the contiguous United States (the route must be drivable).
- The public OSRM demo server is used for routing; set `ROUTING_BASE_URL` to use a self-hosted one.

## Project layout

```
config/                      Django settings and root URLs
routing/
  models.py                  City, FuelStation
  views.py                   API and map views
  services/
    geocoding.py             start/finish → coordinates (offline first)
    osrm.py                  single routing call
    station_index.py         KD-tree of stations, matching to the route
    optimizer.py             cheapest refuelling plan
    planner.py               orchestration, caching, response shaping
  management/commands/
    load_fuel_stations.py    CSV import + station geocoding
  templates/routing/map.html Leaflet map
  tests/                     optimiser, spatial and API tests
postman_collection.json      requests for the demo
```
