from __future__ import annotations

import os
import tempfile

from django.contrib.sites.models import Site
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.test import TestCase, override_settings

import pytest

from multisite.hosts import ALLOWED_HOSTS, AllowedHosts, IterableLazyObject
from multisite.middleware import CookieDomainMiddleware

from .utils import RequestFactory


@pytest.mark.django_db
@override_settings(
    MULTISITE_COOKIE_DOMAIN_DEPTH=0,
    MULTISITE_PUBLIC_SUFFIX_LIST_CACHE=None,
    ALLOWED_HOSTS=ALLOWED_HOSTS,
    MULTISITE_EXTRA_HOSTS=['.extrahost.com'],
    MIDDLEWARE=['multisite.middleware.CookieDomainMiddleware', ]
)
class TestCookieDomainMiddleware(TestCase):

    def setUp(self):

        self.host = 'example.com'
        self.request_factory = RequestFactory(host=self.host)

        Site.objects.all().delete()
        # create sites so we populate ALLOWED_HOSTS
        Site.objects.create(domain='example.com')
        Site.objects.create(domain='test.example.com')
        Site.objects.create(domain='app.test1.example.com')
        Site.objects.create(domain='app.test2.example.com')
        Site.objects.create(domain='new.app.test3.example.com')

        self.request = self.request_factory.get("/")

        def get_response(request: HttpRequest) -> HttpResponseBase:
            response: HttpResponseBase = HttpResponse("<html><body></body></html>")
            return response

        self.middleware = CookieDomainMiddleware(get_response)

    def get_response(self, path, host, **kwargs):
        request_factory = RequestFactory(host=host)
        request = request_factory.get(path)
        cookies = kwargs.get('cookies', None)

        def _get_response(request: HttpRequest) -> HttpResponseBase:
            response: HttpResponseBase = HttpResponse("<html><body></body></html>")
            return response

        response = CookieDomainMiddleware(_get_response)(request)

        for cookie in cookies:
            response.set_cookie(**cookie)

        return response

    def test_init(self):
        self.assertEqual(CookieDomainMiddleware().depth, 0)
        self.assertEqual(
            CookieDomainMiddleware().psl_cache,
            os.path.join(tempfile.gettempdir(), 'multisite_tld.dat'))

        with override_settings(MULTISITE_COOKIE_DOMAIN_DEPTH=1,
                               MULTISITE_PUBLIC_SUFFIX_LIST_CACHE='/var/psl'):
            middleware = CookieDomainMiddleware()
            self.assertEqual(middleware.depth, 1)
            self.assertEqual(middleware.psl_cache, '/var/psl')

        with override_settings(MULTISITE_COOKIE_DOMAIN_DEPTH=-1):
            self.assertRaises(ValueError, CookieDomainMiddleware)

        with override_settings(MULTISITE_COOKIE_DOMAIN_DEPTH='invalid'):
            self.assertRaises(ValueError, CookieDomainMiddleware)

    def test_no_matched_cookies(self):
        # No cookies
        response = self.middleware(self.request)
        self.assertEqual(
            CookieDomainMiddleware().match_cookies(self.request, response), []
        )
        cookies = self.middleware(self.request).cookies
        self.assertEqual(list(cookies.values()), [])

        # Add some cookies with their domains already set
        response.set_cookie(key='a', value='a', domain='.example.org')
        response.set_cookie(key='b', value='b', domain='.example.co.uk')
        self.assertEqual(
            CookieDomainMiddleware().match_cookies(self.request, response),
            []
        )
        cookies = self.middleware(self.request).cookies

        self.assertCountEqual(
            list(cookies.values()), [cookies['a'], cookies['b']]
        )
        self.assertEqual(cookies['a']['domain'], '.example.org')
        self.assertEqual(cookies['b']['domain'], '.example.co.uk')

    def test_matched_cookies(self):
        request = self.request_factory.get('/')
        response = HttpResponse()
        response.set_cookie(key='a', value='a', domain=None)
        self.assertEqual(
            CookieDomainMiddleware().match_cookies(request, response),
            [response.cookies['a']]
        )
        # No new cookies should be introduced
        cookies = self.middleware(self.request).cookies
        self.assertEqual(list(cookies.values()), [cookies['a']])

    def test_ip_address(self):
        allowed = [host for host in ALLOWED_HOSTS] + ['192.0.43.10']
        # IP addresses should not be mutated
        with override_settings(ALLOWED_HOSTS=allowed):
            cookies = self.get_response(
                '/', host='192.0.43.10', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
        self.assertEqual(cookies['a']['domain'], '')

    def test_localpath(self):
        allowed = [host for host in ALLOWED_HOSTS] + ['localhost', 'localhost.localdomain']
        with override_settings(ALLOWED_HOSTS=allowed):
            # Local domains should not be mutated
            cookies = self.get_response(
                '/', host='localhost', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            self.assertEqual(cookies['a']['domain'], '')
            # Even local subdomains
            cookies = self.get_response(
                '/', host='localhost.localdomain', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
        self.assertEqual(cookies['a']['domain'], '')

    def test_simple_tld(self):
        allowed = [host for host in ALLOWED_HOSTS] + ['ai', 'www.ai']
        with override_settings(ALLOWED_HOSTS=allowed):
            # Top-level domains shouldn't get mutated
            cookies = self.get_response(
                '/', host='ai', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            self.assertEqual(cookies['a']['domain'], '')
            # Domains inside a TLD are OK
            cookies = self.get_response(
                '/', host='www.ai', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
        self.assertEqual(cookies['a']['domain'], '.www.ai')

    def test_effective_tld(self):
        allowed = [host for host in ALLOWED_HOSTS] + ['com.ai', 'nic.com.ai']
        with override_settings(ALLOWED_HOSTS=allowed):
            # Effective top-level domains with a webserver shouldn't get mutated
            cookies = self.get_response(
                '/', host='com.ai', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            self.assertEqual(cookies['a']['domain'], '')
            # Domains within an effective TLD are OK
            cookies = self.get_response(
                '/', host='nic.com.ai', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
        self.assertEqual(cookies['a']['domain'], '.nic.com.ai')

    def test_subdomain_depth(self):
        allowed = [host for host in ALLOWED_HOSTS] + ['com']
        with override_settings(
                MULTISITE_COOKIE_DOMAIN_DEPTH=1, ALLOWED_HOSTS=allowed
        ):
            # At depth 1:
            # Top-level domains are ignored
            cookies = self.get_response(
                '/', host='com', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            self.assertEqual(cookies['a']['domain'], '')
            # As are domains within a TLD
            cookies = self.get_response(
                '/', host='example.com', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            self.assertEqual(cookies['a']['domain'], '')
            # But subdomains will get matched
            cookies = self.get_response(
                '/', host='test.example.com', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            self.assertEqual(cookies['a']['domain'], '.test.example.com')
            # And sub-subdomains will get matched to 1 level deep
            cookies['a']['domain'] = ''
            cookies = self.get_response(
                '/', host='app.test1.example.com', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            self.assertEqual(cookies['a']['domain'], '.test1.example.com')

    def test_subdomain_depth_2(self):
        with override_settings(MULTISITE_COOKIE_DOMAIN_DEPTH=2):
            # At MULTISITE_COOKIE_DOMAIN_DEPTH 2, subdomains are matched to
            # 2 levels deep
            cookies = self.get_response(
                '/', host='app.test2.example.com', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            self.assertEqual(cookies['a']['domain'], '.app.test2.example.com')
            cookies['a']['domain'] = ''
            cookies = self.get_response(
                '/', host='new.app.test3.example.com', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            self.assertEqual(cookies['a']['domain'], '.app.test3.example.com')

    def test_wildcard_subdomains(self):

        allowed = [host for host in ALLOWED_HOSTS] + ['.test.example.com']
        with override_settings(
                MULTISITE_COOKIE_DOMAIN_DEPTH=2, ALLOWED_HOSTS=allowed
        ):
            # At MULTISITE_COOKIE_DOMAIN_DEPTH 2, subdomains are matched to
            # 2 levels deep against the wildcard
            cookies = self.get_response(
                '/', host='foo.test.example.com', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            print(cookies)
            self.assertEqual(cookies['a']['domain'], '.foo.test.example.com')
            cookies['a']['domain'] = ''
            cookies = self.get_response(
                '/', host='foo.bar.test.example.com', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            self.assertEqual(cookies['a']['domain'], '.bar.test.example.com')

    def test_multisite_extra_hosts(self):
        # MULTISITE_EXTRA_HOSTS is set to ['.extrahost.com'] but
        # ALLOWED_HOSTS seems to be generated in override_settings before
        # the extra hosts is added, so we need to recalculate it here.
        allowed = IterableLazyObject(lambda: AllowedHosts())
        with override_settings(ALLOWED_HOSTS=allowed):
            cookies = self.get_response(
                '/', host='test.extrahost.com', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            self.assertEqual(cookies['a']['domain'], '.extrahost.com')
            cookies['a']['domain'] = ''
            cookies = self.get_response(
                '/', host='foo.extrahost.com', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            self.assertEqual(cookies['a']['domain'], '.extrahost.com')
            cookies['a']['domain'] = ''
            cookies = self.get_response(
                '/', host='foo.bar.extrahost.com', cookies=[dict(key='a', value='a', domain=None)]
            ).cookies
            self.assertEqual(cookies['a']['domain'], '.extrahost.com')
