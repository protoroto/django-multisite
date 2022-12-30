from unittest import skipUnless

from django.conf import settings
from django.contrib.sites.models import Site
from django.test import TestCase, override_settings

import pytest

from multisite import SiteID


@pytest.mark.django_db
@skipUnless(
    'django.contrib.sites' in settings.INSTALLED_APPS,
    'django.contrib.sites is not in settings.INSTALLED_APPS'
)
@override_settings(SITE_ID=SiteID(), CACHE_SITES_KEY_PREFIX='__test__')
class TestContribSite(TestCase):
    def setUp(self):
        Site.objects.all().delete()
        self.site = Site.objects.create(domain='example.com')
        settings.SITE_ID.set(self.site.id)

    def test_get_current_site(self):
        current_site = Site.objects.get_current()
        self.assertEqual(current_site, self.site)
        self.assertEqual(current_site.id, settings.SITE_ID)
