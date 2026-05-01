"""
Test: Company create persists all configuration flags.
"""
from decimal import Decimal
from django.test import TestCase

from apps.core.models import Company


def _create_full_company(**overrides):
    defaults = dict(
        name='FullCo',
        order_open_days=['Monday','Tuesday','Wednesday','Thursday','Friday'],
        cod_payment=True,
        online_payment=True,
        monthly_payment=False,
        require_customer_approval=True,
        royalty_enabled=True,
        royalty_points_per_rupee=Decimal('1.5'),
        royalty_min_redeem=50,
        royalty_max_redeem_pct=40,
        royalty_reward_mode='count',
        royalty_reward_period='weekly',
        royalty_rank1_points=300,
        royalty_rank2_points=150,
        royalty_rank3_points=50,
        kiosk_theme_color='#c62828',
        kiosk_welcome_text='Order here',
        store_status=True,
    )
    defaults.update(overrides)
    return Company.objects.create(**defaults)


class CompanyCreateConfigTest(TestCase):

    def setUp(self):
        self.co = _create_full_company()

    def test_payment_flags_persisted(self):
        co = Company.objects.get(pk=self.co.pk)
        self.assertTrue(co.cod_payment)
        self.assertTrue(co.online_payment)
        self.assertFalse(co.monthly_payment)

    def test_approval_flag_persisted(self):
        co = Company.objects.get(pk=self.co.pk)
        self.assertTrue(co.require_customer_approval)

    def test_royalty_settings_persisted(self):
        co = Company.objects.get(pk=self.co.pk)
        self.assertTrue(co.royalty_enabled)
        self.assertEqual(co.royalty_points_per_rupee, Decimal('1.5'))
        self.assertEqual(co.royalty_min_redeem, 50)
        self.assertEqual(co.royalty_max_redeem_pct, 40)

    def test_royalty_leaderboard_settings_persisted(self):
        co = Company.objects.get(pk=self.co.pk)
        self.assertEqual(co.royalty_reward_mode, 'count')
        self.assertEqual(co.royalty_reward_period, 'weekly')
        self.assertEqual(co.royalty_rank1_points, 300)
        self.assertEqual(co.royalty_rank2_points, 150)
        self.assertEqual(co.royalty_rank3_points, 50)

    def test_kiosk_theme_persisted(self):
        co = Company.objects.get(pk=self.co.pk)
        self.assertEqual(co.kiosk_theme_color, '#c62828')
        self.assertEqual(co.kiosk_welcome_text, 'Order here')

    def test_defaults_sensible(self):
        co2 = Company.objects.create(name='MinimalCo',
            order_open_days=['Monday'])
        self.assertTrue(co2.online_payment)   # default True
        self.assertFalse(co2.cod_payment)     # default False
        self.assertFalse(co2.royalty_enabled) # default False
        self.assertEqual(co2.royalty_reward_mode, 'amount')
        self.assertEqual(co2.royalty_reward_period, 'monthly')
