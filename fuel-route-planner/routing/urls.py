from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("route/", views.RoutePlanView.as_view(), name="route-plan"),
    path("route/map/", views.RouteMapDirectView.as_view(), name="route-map-direct"),
    path("route/<str:plan_id>/map/", views.RouteMapView.as_view(), name="route-map"),
]
