import ast
import inspect

from django.test import SimpleTestCase

import apps.orders.views as ov


class OrdersHardeningRegressionTest(SimpleTestCase):
    def _module_tree(self):
        return ast.parse(inspect.getsource(ov))

    def _function(self, name):
        for node in self._module_tree().body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail(f'Function {name} not found')

    def test_cancel_order_requires_customer_login(self):
        fn = self._function('cancel_order')
        decorators = [getattr(d, 'id', None) for d in fn.decorator_list]
        self.assertIn('customer_login_required', decorators)

    def test_set_web_cafe_has_single_auth_and_post_decorator(self):
        fn = self._function('set_web_cafe')
        decorators = [getattr(d, 'id', None) for d in fn.decorator_list]
        self.assertEqual(decorators.count('customer_login_required'), 1)
        self.assertEqual(decorators.count('require_POST'), 1)

    def test_apply_coupon_recomputes_summary_with_request(self):
        src = inspect.getsource(ov.apply_coupon)
        self.assertIn("_build_cart_summary(customer, request.session.get('cart', {}), request=request)", src)

    def test_display_board_payload_never_falls_through_to_all_companies(self):
        src = inspect.getsource(ov._display_board_payload)
        self.assertIn('qs = qs.none()', src)
        self.assertIn('requires_company_selection', src)
