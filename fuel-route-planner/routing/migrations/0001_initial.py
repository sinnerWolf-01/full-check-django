from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="City",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                ("name_key", models.CharField(db_index=True, max_length=128)),
                ("state", models.CharField(db_index=True, max_length=2)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
            ],
            options={
                "verbose_name_plural": "cities",
                "constraints": [
                    models.UniqueConstraint(fields=("name_key", "state"), name="unique_city_per_state"),
                ],
            },
        ),
        migrations.CreateModel(
            name="FuelStation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("opis_id", models.IntegerField(db_index=True)),
                ("name", models.CharField(max_length=255)),
                ("address", models.CharField(blank=True, max_length=255)),
                ("city", models.CharField(max_length=128)),
                ("state", models.CharField(db_index=True, max_length=2)),
                ("rack_id", models.IntegerField(blank=True, null=True)),
                ("retail_price", models.DecimalField(decimal_places=5, max_digits=8)),
                ("latitude", models.FloatField(blank=True, null=True)),
                ("longitude", models.FloatField(blank=True, null=True)),
                ("geocode_source", models.CharField(blank=True, max_length=32)),
            ],
            options={
                "indexes": [models.Index(fields=["latitude", "longitude"], name="station_lat_lon_idx")],
            },
        ),
    ]
