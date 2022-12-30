from __future__ import annotations

from unittest import skipUnless

from django.conf import settings
from django.contrib.sites.models import Site
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.test import RequestFactory as DjangoRequestFactory, TestCase, override_settings

import pytest

from multisite import SiteID
from multisite.hosts import ALLOWED_HOSTS
from multisite.middleware import DynamicSiteMiddleware


class RequestFactory(DjangoRequestFactory):
    def __init__(self, host):
        super().__init__()
        self.host = host

    def get(self, path, data=None, host=None, **extra):
        if host is None:
            host = self.host
        if not data:
            data = {}
        return super().get(path=path, data=data, HTTP_HOST=host, **extra)


@pytest.mark.django_db
@skipUnless(
    'django.contrib.sites' in settings.INSTALLED_APPS,
    'django.contrib.sites is not in settings.INSTALLED_APPS'
)
@override_settings(
    ALLOWED_SITES=['*'],
    ROOT_URLCONF=__name__,  # this means that urlpatterns above is used when .get() is called below.
    SITE_ID=SiteID(default=0),
    CACHE_MULTISITE_ALIAS='multisite',
    CACHES={
        'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'},
        'multisite': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}
    },
    MULTISITE_FALLBACK=None,
    ALLOWED_HOSTS=ALLOWED_HOSTS
)
class DynamicSiteMiddlewareTests(TestCase):

    def setUp(self):
        self.host = 'example.com'
        self.request_factory = RequestFactory(host=self.host)
        Site.objects.all().delete()
        self.site = Site.objects.create(domain=self.host)
        self.site2 = Site.objects.create(domain='anothersite.example')

        self.request = self.request_factory.get("/")
        self.response: HttpResponseBase = HttpResponse("<html><body></body></html>")

        def get_response(request: HttpRequest) -> HttpResponseBase:
            return self.response

        self.middleware = DynamicSiteMiddleware(get_response)

    def test_valid_domain(self):
        # Make the request
        response = self.middleware(self.request)

        self.assertEqual(response, None)
        self.assertEqual(settings.SITE_ID, self.site.pk)
        # Request again
        self.assertEqual(response, None)
        self.assertEqual(settings.SITE_ID, self.site.pk)

    # def test_encoded_response(self):
    #     self.response["Content-Encoding"] = "zabble"
    #
    #     response = self.middleware(self.request)
    #
    #     assert isinstance(response, HttpResponse)
    #     assert response.content == b"<html><body></body></html>"
    #
    # def test_text_response(self):
    #     self.response["Content-Type"] = "text/plain"
    #
    #     response = self.middleware(self.request)
    #
    #     assert isinstance(response, HttpResponse)
    #     assert response.content == b"<html><body></body></html>"
    #
    # def test_no_match(self):
    #     self.response = HttpResponse("<html><body>Woops")
    #
    #     response = self.middleware(self.request)
    #
    #     assert isinstance(response, HttpResponse)
    #     assert response.content == b"<html><body>Woops"
    #
    # def test_success(self):
    #     self.response = HttpResponse("<html><body></body></html>")
    #     self.response["Content-Length"] = len(self.response.content)
    #
    #     response = self.middleware(self.request)
    #
    #     assert isinstance(response, HttpResponse)
    #     assert response.content == (
    #         b"<html><body>"
    #         + b'<script src="/static/django-browser-reload/reload-listener.js"'
    #         + b' data-worker-script-path="/static/django-browser-reload/'
    #         + b'reload-worker.js"'
    #         + b' data-events-path="/__reload__/events/" defer></script>'
    #         + b"</body></html>"
    #     )
