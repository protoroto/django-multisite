from __future__ import annotations

from pathlib import Path
from typing import Any

from multisite import SiteID

ALLOWED_HOSTS: list[str] = []

BASE_DIR = Path(__file__).resolve().parent

SITE_ID = SiteID(default=1)

DATABASES: dict[str, dict[str, Any]] = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'test',
    }
}

INSTALLED_APPS = [
    'django.contrib.sites',
    'multisite',
]

MIDDLEWARE: list[str] = [
    'multisite.middleware.DynamicSiteMiddleware',
]

ROOT_URLCONF = "tests.urls"

SECRET_KEY = "NOTASECRET"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates" / "django"],
        "OPTIONS": {"context_processors": []},
    },
]

USE_TZ = True

# 2. Django Contrib Settings

# django.contrib.staticfiles

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_URL = "/static/"
