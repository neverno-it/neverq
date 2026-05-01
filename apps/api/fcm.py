"""
Firebase Cloud Messaging helpers.
Sends push notifications to registered devices.
Initializes firebase-admin lazily so the server starts even without credentials.
"""
import logging

logger = logging.getLogger(__name__)

_initialized = False


def _init_firebase():
    global _initialized
    if _initialized:
        return True
    try:
        import firebase_admin
        from firebase_admin import credentials
        from django.conf import settings
        import os

        cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
        if not cred_path or not os.path.exists(cred_path):
            logger.warning('FIREBASE_CREDENTIALS_PATH not set or file missing — FCM disabled.')
            return False

        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)

        _initialized = True
        return True
    except Exception as exc:
        logger.warning('Firebase init failed: %s', exc)
        return False


def send_push(tokens, title, body, data=None):
    if not tokens:
        return
    if not _init_firebase():
        return
    try:
        from firebase_admin import messaging
        message = messaging.MulticastMessage(
            tokens=list(tokens),
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            android=messaging.AndroidConfig(priority='high'),
        )
        response = messaging.send_each_for_multicast(message)
        if response.failure_count:
            logger.warning('%d FCM messages failed.', response.failure_count)
    except Exception as exc:
        logger.error('FCM send error: %s', exc)


def notify_kitchen_new_order(order):
    from .models import FCMDevice
    from apps.accounts.models import StaffUser
    kitchen_roles = [StaffUser.ROLE_CAFEMAN, StaffUser.ROLE_ADMIN, StaffUser.ROLE_SUPERADMIN]
    staff_ids = StaffUser.objects.filter(
        company=order.company, role__in=kitchen_roles, is_active=True
    ).values_list('id', flat=True)

    tokens = list(
        FCMDevice.objects.filter(
            staff_user_id__in=staff_ids, is_active=True
        ).values_list('token', flat=True)
    )
    send_push(
        tokens,
        title='New Order',
        body=f'Order #{order.order_number} received — ₹{order.total_amount}',
        data={'order_id': str(order.id), 'type': 'new_order'},
    )


def notify_customer_order_ready(order):
    from .models import FCMDevice
    tokens = list(
        FCMDevice.objects.filter(
            customer=order.customer, is_active=True
        ).values_list('token', flat=True)
    )
    send_push(
        tokens,
        title='Your order is ready!',
        body=f'Order #{order.order_number} is ready for pickup.',
        data={'order_id': str(order.id), 'type': 'order_ready'},
    )


def notify_customer_order_status(order):
    from .models import FCMDevice
    tokens = list(
        FCMDevice.objects.filter(
            customer=order.customer, is_active=True
        ).values_list('token', flat=True)
    )
    send_push(
        tokens,
        title='Order Update',
        body=f'Order #{order.order_number}: {order.status_label}',
        data={'order_id': str(order.id), 'type': 'order_status', 'status': str(order.order_status)},
    )
