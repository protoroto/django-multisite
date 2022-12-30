from __future__ import annotations

from django.contrib.sites.models import Site
from django.http import HttpResponse
from django.urls import path

urlpatterns = [
    path('domain/', lambda request, *args, **kwargs: HttpResponse(str(Site.objects.get_current())))
]
