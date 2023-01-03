from unittest import skipUnless

from django.conf import settings
from django.contrib.sites.models import Site
from django.http import HttpRequest
from django.http.response import Http404, HttpResponse, HttpResponseBase
from django.test import TestCase, override_settings

import pytest

from multisite import SiteID
from multisite.hacks import use_framework_for_site_cache
from multisite.middleware import DynamicSiteMiddleware
from tests.settings import ALLOWED_HOSTS
from tests.utils import RequestFactory


@pytest.mark.django_db
@override_settings(
    SITE_ID=SiteID(default=0),
    CACHE_MULTISITE_ALIAS='multisite',
    CACHES={
        'multisite': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}
    },
    MULTISITE_FALLBACK=None,
    ALLOWED_HOSTS=ALLOWED_HOSTS
)
class CacheTest(TestCase):
    def setUp(self):
        self.host = 'example.com'
        self.request_factory = RequestFactory(host=self.host)

        Site.objects.all().delete()
        self.site = Site.objects.create(domain=self.host)

        self.request = self.request_factory.get("/")
        self.response: HttpResponseBase = HttpResponse("<html><body></body></html>")

        def get_response(request: HttpRequest) -> HttpResponseBase:
            return self.response

        self.middleware = DynamicSiteMiddleware(get_response)

    def test_site_domain_changed(self):

        # Test to ensure that the cache is cleared properly
        response = self.middleware(self.request)

        cache_key = self.middleware.get_cache_key(self.host)
        self.assertEqual(self.middleware.cache.get(cache_key), None)
        # Make the request
        request = self.factory.get('/')
        self.assertEqual(response, None)
        self.assertEqual(self.middleware.cache.get(cache_key).site_id, self.site.pk)
        # Change the domain name
        self.site.domain = 'example.org'
        self.site.save()
        self.assertEqual(self.middleware.cache.get(cache_key), None)
        # Make the request again, which will now be invalid
        request = self.factory.get('/')
        self.assertRaises(Http404, self.middleware.process_request, request)
        self.assertEqual(settings.SITE_ID, 0)


@pytest.mark.django_db
@skipUnless(
    'django.contrib.sites' in settings.INSTALLED_APPS,
    'django.contrib.sites is not in settings.INSTALLED_APPS'
)
@override_settings(SITE_ID=SiteID(),)
class SiteCacheTest(TestCase):

    def _initialize_cache(self):
        # initialize cache again so override key prefix settings are used
        from django.contrib.sites import models
        use_framework_for_site_cache()
        self.cache = models.SITE_CACHE

    def setUp(self):
        self._initialize_cache()
        Site.objects.all().delete()
        self.host = 'example.com'
        self.site = Site.objects.create(domain=self.host)
        settings.SITE_ID.set(self.site.id)

    def test_get_current(self):
        self.assertRaises(KeyError, self.cache.__getitem__, self.site.id)
        # Populate cache
        self.assertEqual(Site.objects.get_current(), self.site)
        self.assertEqual(self.cache[self.site.id], self.site)
        self.assertEqual(self.cache.get(key=self.site.id), self.site)
        self.assertEqual(self.cache.get(key=-1), None)  # Site doesn't exist
        self.assertEqual(self.cache.get(-1, 'Default'), 'Default')  # Site doesn't exist
        self.assertEqual(
            self.cache.get(key=-1, default='Non-existant'), 'Non-existant'
        )  # Site doesn't exist
        self.assertEqual(
            'Non-existant',
            self.cache.get(self.site.id, default='Non-existant', version=100)
        )  # Wrong key version 3
        # Clear cache
        self.cache.clear()
        self.assertRaises(KeyError, self.cache.__getitem__, self.site.id)
        self.assertEqual(
            self.cache.get(key=self.site.id, default='Cleared'), 'Cleared'
        )

    def test_create_site(self):
        self.assertEqual(Site.objects.get_current(), self.site)
        self.assertEqual(Site.objects.get_current().domain, self.site.domain)
        # Create new site
        site = Site.objects.create(domain='example.org')
        settings.SITE_ID.set(site.id)
        self.assertEqual(Site.objects.get_current(), site)
        self.assertEqual(Site.objects.get_current().domain, site.domain)

    def test_change_site(self):
        self.assertEqual(Site.objects.get_current(), self.site)
        self.assertEqual(Site.objects.get_current().domain, self.site.domain)
        # Change site domain
        self.site.domain = 'example.org'
        self.site.save()
        self.assertEqual(Site.objects.get_current(), self.site)
        self.assertEqual(Site.objects.get_current().domain, self.site.domain)

    def test_delete_site(self):
        self.assertEqual(Site.objects.get_current(), self.site)
        self.assertEqual(Site.objects.get_current().domain, self.site.domain)
        # Delete site
        self.site.delete()
        self.assertRaises(KeyError, self.cache.__getitem__, self.site.id)

    @override_settings(CACHE_MULTISITE_KEY_PREFIX="__test__")
    def test_multisite_key_prefix(self):
        self._initialize_cache()
        # Populate cache
        self.assertEqual(Site.objects.get_current(), self.site)
        self.assertEqual(self.cache[self.site.id], self.site)
        self.assertEqual(
            self.cache._cache._get_cache_key(self.site.id),
            'sites.{}.{}'.format(
                settings.CACHE_MULTISITE_KEY_PREFIX, self.site.id
            ),
            self.cache._cache._get_cache_key(self.site.id)
        )

    @override_settings(
        CACHE_MULTISITE_ALIAS='multisite',
        CACHES={
            'multisite': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                'KEY_PREFIX': 'looselycoupled'
            }
        },
    )
    def test_default_key_prefix(self):
        """
        If CACHE_MULTISITE_KEY_PREFIX is undefined,
        the caching system should use CACHES[current]['KEY_PREFIX'].
        """
        self._initialize_cache()
        # Populate cache
        self.assertEqual(Site.objects.get_current(), self.site)
        self.assertEqual(self.cache[self.site.id], self.site)
        self.assertEqual(
            self.cache._cache._get_cache_key(self.site.id),
            f"sites.looselycoupled.{self.site.id}"
        )

    @override_settings(
        CACHE_MULTISITE_KEY_PREFIX="virtuouslyvirtual",
        )
    def test_multisite_key_prefix_takes_priority_over_default(self):
        self._initialize_cache()
        # Populate cache
        self.assertEqual(Site.objects.get_current(), self.site)
        self.assertEqual(self.cache[self.site.id], self.site)
        self.assertEqual(
            self.cache._cache._get_cache_key(self.site.id),
            f"sites.virtuouslyvirtual.{self.site.id}"
        )
