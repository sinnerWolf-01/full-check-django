import json

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import FuelStation
from .services.geocoding import GeocodingError
from .services.osrm import RoutingError
from .services.planner import PlanningError, build_plan, get_cached_plan
from .services.station_index import get_station_index


def _error(message, status, **extra):
    return JsonResponse({"error": message, **extra}, status=status)


def _read_params(request):
    if request.method == "POST" and request.body:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            raise ValueError("Request body must be valid JSON.")
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object.")
        return body
    return request.GET


def _parse_request(request):
    params = _read_params(request)
    start = str(params.get("start") or "").strip()
    finish = str(params.get("finish") or "").strip()
    if not start or not finish:
        raise ValueError("Both 'start' and 'finish' are required, e.g. start='Chicago, IL', finish='Denver, CO'.")
    detour = params.get("max_detour_miles")
    if detour not in (None, ""):
        try:
            detour = float(detour)
        except (TypeError, ValueError):
            raise ValueError("'max_detour_miles' must be a number.")
        if not 0 < detour <= 50:
            raise ValueError("'max_detour_miles' must be between 0 and 50.")
    else:
        detour = None
    return start, finish, detour


def _plan_or_error(request):
    """Returns (plan, None) or (None, JsonResponse)."""
    try:
        start, finish, detour = _parse_request(request)
    except ValueError as exc:
        return None, _error(str(exc), 400)
    if get_station_index().size == 0:
        return None, _error("No fuel stations loaded. Run: python manage.py load_fuel_stations", 503)
    try:
        return build_plan(start, finish, detour), None
    except GeocodingError as exc:
        return None, _error(str(exc), 400)
    except RoutingError as exc:
        return None, _error(str(exc), 502)
    except PlanningError as exc:
        return None, _error(str(exc), 422)


@method_decorator(csrf_exempt, name="dispatch")
class RoutePlanView(View):
    """GET /api/route/?start=...&finish=...  or  POST {"start": ..., "finish": ...}"""

    def get(self, request):
        return self._handle(request)

    def post(self, request):
        return self._handle(request)

    def _handle(self, request):
        plan, error = _plan_or_error(request)
        if error:
            return error
        plan["map_url"] = request.build_absolute_uri(reverse("route-map", args=[plan["plan_id"]]))
        return JsonResponse(plan, json_dumps_params={"indent": 2})


class RouteMapView(View):
    """GET /api/route/<plan_id>/map/ — interactive Leaflet map of a computed plan."""

    def get(self, request, plan_id):
        plan = get_cached_plan(plan_id)
        if plan is None:
            raise Http404("Plan not found or expired. Request the route again.")
        return render(request, "routing/map.html", {"plan": plan})


class RouteMapDirectView(View):
    """GET /api/route/map/?start=...&finish=... — compute and render in one step (handy in a browser)."""

    def get(self, request):
        plan, error = _plan_or_error(request)
        if error:
            return error
        return render(request, "routing/map.html", {"plan": plan})


def health(request):
    index = get_station_index()
    return JsonResponse({
        "status": "ok",
        "stations_in_database": FuelStation.objects.count(),
        "geocoded_station_locations_indexed": index.size,
    })
