from django.contrib import admin

from .models import City, FuelStation


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "retail_price", "latitude", "longitude", "geocode_source")
    list_filter = ("state", "geocode_source")
    search_fields = ("name", "city", "address")


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "latitude", "longitude")
    list_filter = ("state",)
    search_fields = ("name",)
