from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.http import HttpResponseRedirect

from apps.orders.views import (
    SESSION_KEY_PENDING_KIOSK_ONLINE_CHECKOUT,
    SESSION_KEY_PENDING_ONLINE_CHECKOUT,
    phonepe_callback,
)
from apps.orders.phonepe import PhonePeError


class PhonePeCallbackReconciliationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _build_request(self, path, session_key, snapshot):
        request = self.factory.get(path)
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session[session_key] = snapshot
        setattr(request, '_messages', FallbackStorage(request))
        return request

    @override_settings(PHONEPE_MODE='test')
    def test_web_callback_reconciles_locally_when_status_api_fails_in_test_mode(self):
        snapshot = {
            'merchant_ref': 'WEB-TEST-0001',
            'gateway_order_id': 'pp-order-1',
            'gateway_redirect_url': 'https://phonepe.test/redirect',
            'created_at': '2026-04-08T10:00:00+05:30',
        }
        request = self._build_request(
            '/orders/phonepe/callback/?merchant_order_id=WEB-TEST-0001',
            SESSION_KEY_PENDING_ONLINE_CHECKOUT,
            snapshot,
        )

        with patch('apps.orders.views.Order.objects.filter') as mock_filter, \
             patch('apps.orders.views._fetch_phonepe_order_status_with_retry', side_effect=PhonePeError('sandbox down')), \
             patch('apps.orders.views._find_existing_order_with_retry', return_value=None), \
             patch('apps.orders.views._create_new_order_from_pending_snapshot', return_value=SimpleNamespace(pk=77, order_number='WEB-TEST-0001')) as mock_create:
            mock_filter.return_value.first.return_value = None
            response = phonepe_callback(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/orders/confirmation/77/')
        mock_create.assert_called_once_with(snapshot, transaction_id='pp-order-1')
        self.assertFalse(request.session.get(SESSION_KEY_PENDING_ONLINE_CHECKOUT))
        msgs = [m.message for m in get_messages(request)]
        self.assertIn('Payment completed for order #WEB-TEST-0001.', msgs)

    @override_settings(PHONEPE_MODE='test')
    def test_kiosk_callback_reconciles_locally_when_status_api_fails_in_test_mode(self):
        snapshot = {
            'merchant_ref': 'KIO-TEST-0001',
            'company_id': 9,
            'kiosk_slug': 'front-desk',
            'gateway_order_id': 'pp-order-2',
            'gateway_redirect_url': 'https://phonepe.test/redirect',
            'created_at': '2026-04-08T10:00:00+05:30',
        }
        request = self._build_request(
            '/orders/phonepe/callback/?merchant_order_id=KIO-TEST-0001',
            SESSION_KEY_PENDING_KIOSK_ONLINE_CHECKOUT,
            snapshot,
        )

        with patch('apps.orders.views.Order.objects.filter') as mock_filter, \
             patch('apps.orders.views._fetch_phonepe_order_status_with_retry', side_effect=PhonePeError('sandbox down')), \
             patch('apps.orders.views._find_existing_order_with_retry', return_value=None), \
             patch('apps.orders.views._create_new_kiosk_order_from_pending_snapshot', return_value=SimpleNamespace(pk=88, order_number='KIO-TEST-0001')) as mock_create, \
             patch('apps.orders.views._kiosk_redirect', return_value=HttpResponseRedirect('/kiosk/confirmation/88/')) as mock_redirect:
            mock_filter.return_value.first.return_value = None
            response = phonepe_callback(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/kiosk/confirmation/88/')
        mock_create.assert_called_once_with(snapshot, transaction_id='pp-order-2')
        mock_redirect.assert_called_once_with('orders:kiosk_confirmation', 9, 'front-desk', pk=88)
        self.assertFalse(request.session.get(SESSION_KEY_PENDING_KIOSK_ONLINE_CHECKOUT))
        self.assertEqual(request.session.get('last_kiosk_online_order', {}).get('order_id'), 88)
        msgs = [m.message for m in get_messages(request)]
        self.assertIn('Payment completed for order #KIO-TEST-0001.', msgs)

    @override_settings(PHONEPE_MODE='live')
    def test_live_mode_does_not_use_local_reconciliation_fallback(self):
        snapshot = {
            'merchant_ref': 'WEB-LIVE-0001',
            'gateway_order_id': 'pp-order-live',
            'gateway_redirect_url': 'https://phonepe.live/redirect',
            'created_at': '2026-04-08T10:00:00+05:30',
        }
        request = self._build_request(
            '/orders/phonepe/callback/?merchant_order_id=WEB-LIVE-0001',
            SESSION_KEY_PENDING_ONLINE_CHECKOUT,
            snapshot,
        )

        with patch('apps.orders.views.Order.objects.filter') as mock_filter, \
             patch('apps.orders.views._fetch_phonepe_order_status_with_retry', side_effect=PhonePeError('sandbox down')), \
             patch('apps.orders.views._find_existing_order_with_retry', return_value=None), \
             patch('apps.orders.views._create_new_order_from_pending_snapshot') as mock_create:
            mock_filter.return_value.first.return_value = None
            response = phonepe_callback(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/orders/checkout/')
        mock_create.assert_not_called()
        msgs = [m.message for m in get_messages(request)]
        self.assertIn('Unable to verify PhonePe payment right now. Please check My Orders after a moment or try again.', msgs)
