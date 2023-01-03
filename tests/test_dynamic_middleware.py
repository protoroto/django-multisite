from __future__ import annotations

from unittest import skipUnless

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse
from django.http.response import Http404, HttpResponseBase
from django.test import TestCase, override_settings

import pytest

from multisite import SiteID
from multisite.hosts import ALLOWED_HOSTS
from multisite.middleware import DynamicSiteMiddleware
from multisite.models import Alias

from .utils import RequestFactory


@pytest.mark.django_db
@skipUnless(
    'django.contrib.sites' in settings.INSTALLED_APPS,
    'django.contrib.sites is not in settings.INSTALLED_APPS'
)
@override_settings(
    ALLOWED_SITES=['*'],
    ROOT_URLCONF="tests.urls",
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

        self.assertEqual(response.status_code, 200)
        self.assertEqual(settings.SITE_ID, self.site.pk)
        # Request again
        self.assertEqual(response.status_code, 200)
        self.assertEqual(settings.SITE_ID, self.site.pk)

    def test_valid_domain_port(self):
        # Make the request with a specific port
        response = self.middleware(self.request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(settings.SITE_ID, self.site.pk)
        # Request again
        response = self.middleware(self.request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(settings.SITE_ID, self.site.pk)

    def test_case_sensitivity(self):
        # Make the request in all uppercase
        request_factory = RequestFactory(host=self.host.upper())
        request = request_factory.get("/")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(settings.SITE_ID, self.site.pk)

    def test_change_domain(self):
        # Make the request
        response = self.middleware(self.request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(settings.SITE_ID, self.site.pk)

        # Another request with a different site
        request_factory = RequestFactory(host=self.site2.domain)
        request2 = request_factory.get('/', host=self.site2.domain)
        response2 = self.middleware(request2)
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(settings.SITE_ID, self.site2.pk)

    def test_unknown_host(self):
        # Unknown host
        request = self.request_factory.get('/', host='unknown')

        with self.assertRaises(Http404):
            self.middleware(request)

        # The middleware resets SiteID to its default value, as given above, on error.
        self.assertEqual(settings.SITE_ID, 0)

    def test_unknown_hostport(self):
        # Unknown host:port
        request = self.request_factory.get('/', host='unknown:8000')

        with self.assertRaises(Http404):
            self.middleware(request)

        # The middleware resets SiteID to its default value, as given above, on error.
        self.assertEqual(settings.SITE_ID, 0)

    def test_invalid_host(self):
        # Invalid host
        request = self.request_factory.get('/', host='')
        with self.assertRaises(Http404):
            self.middleware(request)

    def test_invalid_hostport(self):
        # Invalid host:port
        request = self.request_factory.get('/', host=':8000')
        with self.assertRaises(Http404):
            self.middleware(request)

    def test_no_sites(self):
        # FIXME: this needs to go into its own TestCase since it requires modifying the fixture to work properly
        # Remove all Sites
        Site.objects.all().delete()
        # Make the request
        request = self.request_factory.get('/')

        with self.assertRaises(Http404):
            self.middleware(request)

        # The middleware resets SiteID to its default value, as given above, on error.
        self.assertEqual(settings.SITE_ID, 0)

    def test_redirect(self):
        host = 'example.org'
        alias = Alias.objects.create(site=self.site, domain=host)
        self.assertTrue(alias.redirect_to_canonical)
        # Make the request
        request = self.request_factory.get('/path', host=host)

        response = self.middleware(request)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], f"http://{self.host}/path")

    def test_no_redirect(self):
        host = 'example.org'
        Alias.objects.create(site=self.site, domain=host, redirect_to_canonical=False)
        # Make the request
        request = self.request_factory.get('/path', host=host)
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(settings.SITE_ID, self.site.pk)

    def test_integration(self):
        """
        Test that the middleware loads and runs properly under settings.MIDDLEWARE.
        """
        resp = self.client.get('/domain/', HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.site.domain)
        self.assertEqual(settings.SITE_ID, self.site.pk)

        resp = self.client.get('/domain/', HTTP_HOST=self.site2.domain)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.site2.domain)
        self.assertEqual(settings.SITE_ID, self.site2.pk)


@pytest.mark.django_db
@skipUnless(
    'django.contrib.sites' in settings.INSTALLED_APPS,
    'django.contrib.sites is not in settings.INSTALLED_APPS'
)
@override_settings(
    SITE_ID=SiteID(default=0),
    CACHE_MULTISITE_ALIAS='multisite',
    CACHES={
        'multisite': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}
    },    MULTISITE_FALLBACK=None,
    MULTISITE_FALLBACK_KWARGS={},
)
class DynamicSiteMiddlewareFallbackTest(TestCase):
    def setUp(self):
        self.host = 'unknown'
        self.request_factory = RequestFactory(host=self.host)
        Site.objects.all().delete()

        self.request = self.request_factory.get("/")
        self.response: HttpResponseBase = HttpResponse("<html><body></body></html>")

        def get_response(request: HttpRequest) -> HttpResponseBase:
            return self.response

        self.middleware = DynamicSiteMiddleware(get_response)

    def test_404(self):
        with self.assertRaises(Http404):
            self.middleware(self.request)
        self.assertEqual(settings.SITE_ID, 0)

    def test_testserver(self):
        host = 'testserver'
        site = Site.objects.create(domain=host)

        request = self.request_factory.get('/', host=host)
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(settings.SITE_ID, site.pk)

    def test_string_class(self):
        # Class based
        settings.MULTISITE_FALLBACK = 'django.views.generic.base.RedirectView'
        settings.MULTISITE_FALLBACK_KWARGS = {
            'url': 'http://example.com/',
            'permanent': False
        }
        response = self.middleware(self.request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], settings.MULTISITE_FALLBACK_KWARGS['url'])

    def test_class_view(self):
        from django.views.generic.base import RedirectView
        settings.MULTISITE_FALLBACK = RedirectView.as_view(
            url='http://example.com/', permanent=False
        )
        response = self.middleware(self.request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'http://example.com/')

    @override_settings(MULTISITE_FALLBACK='')
    def test_invalid(self):
        with self.assertRaises(ImproperlyConfigured):
            self.middleware(self.request)


@pytest.mark.django_db
@skipUnless(
    'django.contrib.sites' in settings.INSTALLED_APPS,
    'django.contrib.sites is not in settings.INSTALLED_APPS'
)
@override_settings(SITE_ID=0,)
class DynamicSiteMiddlewareSettingsTest(TestCase):
    def test_invalid_settings(self):
        self.assertRaises(TypeError, DynamicSiteMiddleware)
