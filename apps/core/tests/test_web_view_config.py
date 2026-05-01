from django.test import TestCase

from apps.core.models import Company, Building, WebViewConfig, resolve_web_view_config


class WebViewConfigModelTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='WebCo',
            kiosk_theme_color='#c62828',
            kiosk_welcome_text='Order with ease',
            order_open_days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],
        )
        self.building = Building.objects.create(company=self.company, name='Tower A')

    def test_effective_theme_color_uses_company_default(self):
        cfg = WebViewConfig(company=self.company, name='Default Theme')
        self.assertEqual(cfg.effective_theme_color, '#c62828')

    def test_effective_subtitle_uses_company_default(self):
        cfg = WebViewConfig(company=self.company, name='Default Subtitle')
        self.assertEqual(cfg.effective_welcome_subtitle, 'Order with ease')

    def test_slug_auto_generated(self):
        cfg = WebViewConfig.objects.create(company=self.company, name='Main Web')
        self.assertTrue(cfg.slug)
        self.assertIn('web', cfg.slug)

    def test_resolve_prefers_building_specific_config(self):
        default_cfg = WebViewConfig.objects.create(company=self.company, name='Company Default')
        building_cfg = WebViewConfig.objects.create(company=self.company, building=self.building, name='Tower A Web')
        self.assertEqual(resolve_web_view_config(self.company, building=self.building).pk, building_cfg.pk)
        self.assertEqual(resolve_web_view_config(self.company).pk, default_cfg.pk)

    def test_resolve_by_slug(self):
        cfg = WebViewConfig.objects.create(company=self.company, name='Preview Config')
        self.assertEqual(resolve_web_view_config(self.company, slug=cfg.slug).pk, cfg.pk)
