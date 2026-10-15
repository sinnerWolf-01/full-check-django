"""Django settings for the fuel route planner."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# File cache works across worker processes, so a plan computed by one worker
# can be rendered as a map by another, and repeated routes skip the routing API.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": BASE_DIR / ".cache",
        "TIMEOUT": 60 * 60 * 24,
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Django defaults to "same-origin", which strips the Referer header that public
# map tile servers require. This still hides full URLs from other sites.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Fuel route planner settings -------------------------------------------
FUEL_PLANNER = {
    # Free OSRM demo server; point this at a self-hosted OSRM for production.
    "ROUTING_BASE_URL": os.environ.get("ROUTING_BASE_URL", "https://router.project-osrm.org"),
    "ROUTING_TIMEOUT_SECONDS": float(os.environ.get("ROUTING_TIMEOUT_SECONDS", "15")),
    # Nominatim is only used when a start/finish can't be resolved offline.
    "GEOCODER_BASE_URL": os.environ.get("GEOCODER_BASE_URL", "https://nominatim.openstreetmap.org"),
    "GEOCODER_FALLBACK_ENABLED": os.environ.get("GEOCODER_FALLBACK_ENABLED", "1") == "1",
    "USER_AGENT": os.environ.get("FUEL_PLANNER_USER_AGENT", "fuel-route-planner/1.0 (assessment)"),
    "MAX_RANGE_MILES": 500.0,
    "MILES_PER_GALLON": 10.0,
    # Stations are geocoded to their city, so allow some distance from the route.
    "DEFAULT_MAX_DETOUR_MILES": 10.0,
    "ROUTE_SAMPLE_SPACING_MILES": 0.5,
    "MAX_RESPONSE_GEOMETRY_POINTS": 2000,
    "PLAN_CACHE_SECONDS": 60 * 60 * 24,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"routing": {"handlers": ["console"], "level": "INFO"}},
}
