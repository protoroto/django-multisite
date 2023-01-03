import os

from django.template.loader import get_template
from django.test import TestCase, override_settings

TEMPLATE_SETTINGS = {'TEMPLATES': [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates')
        ],
        'OPTIONS': {
            'loaders': [
                'multisite.template.loaders.filesystem.Loader',
            ]
        },
    }
]
}


@override_settings(
    MULTISITE_DEFAULT_TEMPLATE_DIR='multisite_templates',
    **TEMPLATE_SETTINGS
)
class TemplateLoaderTests(TestCase):

    def test_get_template_multisite_default_dir(self):
        template = get_template("test.html")
        self.assertEqual(template.render(), "Test!")

    def test_domain_template(self):
        template = get_template("example.html")
        self.assertEqual(template.render(), "Test example.com template")

    def test_get_template_old_settings(self):
        # tests that we can still get to the template filesystem loader with
        # the old setting configuration
        with override_settings(
                TEMPLATES=[
                    {
                        'BACKEND': 'django.template.backends.django.DjangoTemplates',
                        'DIRS': [
                            os.path.join(
                                os.path.abspath(os.path.dirname(__file__)),
                                'templates'
                            )
                        ],
                        'OPTIONS': {
                            'loaders': [
                                'multisite.template_loader.Loader',
                            ]
                        },
                    }
                ]
        ):
            template = get_template("test.html")
            self.assertEqual(template.render(), "Test!")
