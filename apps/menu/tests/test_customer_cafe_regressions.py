import inspect

from django.test import SimpleTestCase

import apps.menu.views as mv


class CustomerCafeRegressionTest(SimpleTestCase):
    def test_customer_menu_uses_selected_cafe_for_display_prices(self):
        src = inspect.getsource(mv.customer_menu)
        self.assertIn('_selected_cafe = _resolve_customer_cafe(customer, company, request=request)', src)
        self.assertIn('cafe=_selected_cafe', src)

    def test_product_and_cart_views_pass_request_into_cafe_aware_summary(self):
        for fn in (mv.category_detail, mv.offering_detail, mv.product_detail, mv.cart_view):
            src = inspect.getsource(fn)
            self.assertIn('request=request', src, msg=f'{fn.__name__} must keep selected cafe from session')
