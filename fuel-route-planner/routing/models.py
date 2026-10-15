from django.db import models


class City(models.Model):
    """US city centroid, used for offline geocoding of stations and user input."""

    name = models.CharField(max_length=128)
    name_key = models.CharField(max_length=128, db_index=True)
    state = models.CharField(max_length=2, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["name_key", "state"], name="unique_city_per_state"),
        ]
        verbose_name_plural = "cities"

    def __str__(self):
        return f"{self.name}, {self.state}"


class FuelStation(models.Model):
    """A truck stop from the provided fuel price file."""

    opis_id = models.IntegerField(db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=128)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.IntegerField(null=True, blank=True)
    retail_price = models.DecimalField(max_digits=8, decimal_places=5)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    geocode_source = models.CharField(max_length=32, blank=True)

    class Meta:
        indexes = [models.Index(fields=["latitude", "longitude"], name="station_lat_lon_idx")]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) ${self.retail_price}"
