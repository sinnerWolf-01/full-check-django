`fuel-prices-for-be-assessment.csv` is the provided fuel price file (8,151 rows).
The importer keeps the 7,531 US stations and skips the 620 Canadian ones.

`us_cities.csv` is downloaded here automatically by `python manage.py load_fuel_stations`
(source: https://github.com/kelvins/US-Cities-Database) and is git-ignored.
