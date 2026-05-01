from django.test import TestCase

from apps.accounts.models import StaffUser
from apps.core.models import Company
from apps.menu.models import Category, Product
from apps.menu.views import _build_product_bulk_preview, _parse_calories_value, _resolve_product_for_import


def _company(name='Bulk Upload Co'):
    return Company.objects.create(
        name=name,
        store_status=True,
        cod_payment=True,
        online_payment=True,
    )


def _superadmin():
    return StaffUser.objects.create(
        email='bulk-upload-super@example.com',
        role=StaffUser.ROLE_SUPERADMIN,
        is_active=True,
        is_staff=True,
    )


class BulkUploadDuplicateSlugTest(TestCase):
    def setUp(self):
        self.company = _company()
        self.category = Category.objects.create(
            name='Sandwich',
            slug='sandwich',
            is_active=True,
            is_deleted=False,
        )
        self.category.companies.add(self.company)
        self.user = _superadmin()

    def _payload(self, rows):
        return {
            'mode': 'xlsx',
            'sheets': {
                'products': rows,
                'countermapping': [],
            },
        }

    def _options(self, replace=True):
        return {
            'replace_product_data': replace,
            'replace_counter_mappings': False,
            'auto_create_categories': True,
            'auto_create_offerings': True,
        }

    def test_resolves_existing_product_by_slug_even_when_name_punctuation_differs(self):
        existing = Product.objects.create(
            company=self.company,
            category=self.category,
            name='Grilled Sandwich Vegetable',
            slug='grilled-sandwich-vegetable',
            price='70.00',
            is_active=True,
            is_deleted=False,
        )
        row = {
            'product_name': 'Grilled Sandwich-Vegetable',
            'category': self.category.name,
            'base_price': '80.00',
        }

        self.assertEqual(_resolve_product_for_import(self.company, row), existing)

        summary = _build_product_bulk_preview(
            self.user,
            self._payload([row]),
            self.company,
            self._options(replace=True),
        )

        self.assertEqual(summary['preview_products_ready'], 1)
        self.assertEqual(summary['preview_products'][0]['action'], 'Update')
        self.assertEqual(summary['preview_products'][0]['errors'], [])

    def test_existing_slug_is_blocked_when_replace_data_is_off(self):
        Product.objects.create(
            company=self.company,
            category=self.category,
            name='Grilled Sandwich Vegetable',
            slug='grilled-sandwich-vegetable',
            price='70.00',
            is_active=True,
            is_deleted=False,
        )
        row = {
            'product_name': 'Grilled Sandwich-Vegetable',
            'category': self.category.name,
            'base_price': '80.00',
        }

        summary = _build_product_bulk_preview(
            self.user,
            self._payload([row]),
            self.company,
            self._options(replace=False),
        )

        self.assertEqual(summary['preview_products_blocked'], 1)
        self.assertIn('Product already exists', summary['preview_products'][0]['errors'][0])

    def test_workbook_duplicate_slug_is_caught_in_preview(self):
        rows = [
            {'product_name': 'Butter Toast (2 Pcs)', 'category': self.category.name, 'base_price': '50.00'},
            {'product_name': 'Butter Toast 2 Pcs', 'category': self.category.name, 'base_price': '50.00'},
        ]

        summary = _build_product_bulk_preview(
            self.user,
            self._payload(rows),
            self.company,
            self._options(replace=True),
        )

        self.assertEqual(summary['preview_products_ready'], 1)
        self.assertEqual(summary['preview_products_blocked'], 1)
        self.assertIn('same slug', summary['preview_products'][1]['errors'][0])

    def test_product_form_stock_headers_preserve_zero_web_qty(self):
        row = {
            'product_name': 'Zero Stock Sandwich',
            'category': self.category.name,
            'base_price': '50.00',
            'Web Stock (WEB_QTY)': 0,
            'POS Stock (POS_QTY)': 0,
            'Min Qty per Order': 1,
            'Max Qty per Order': 10,
            'Prep Time (Minutes)': 5,
            'Calories (Kcal)': 120,
        }
        from apps.menu.views import _normalize_bulk_header, _parse_int
        normalized = {_normalize_bulk_header(key): value for key, value in row.items()}

        self.assertEqual(normalized['web_qty'], 0)
        self.assertEqual(normalized['pos_qty'], 0)
        self.assertEqual(normalized['min_qty'], 1)
        self.assertEqual(normalized['max_qty'], 10)
        self.assertEqual(normalized['preparation_time_minutes'], 5)
        self.assertEqual(normalized['calories'], 120)
        self.assertEqual(_parse_int(normalized.get('web_qty'), -1), 0)

    def test_calorie_parser_preserves_explicit_zero(self):
        self.assertEqual(_parse_calories_value(0, 'Dal Fry', ''), 0)
        self.assertEqual(_parse_calories_value('0', 'Dal Fry', ''), 0)

    def test_common_product_names_auto_estimate_when_calories_blank(self):
        for product_name in ['Butter Roti', 'Channa Masala', 'Dahi', 'Jeera Rice Basmati']:
            with self.subTest(product_name=product_name):
                self.assertIsNotNone(_parse_calories_value('', product_name, ''))
