import base64
import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib import error, request


class RazorpayError(Exception):
    pass


def to_paise(amount):
    try:
        value = Decimal(str(amount or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RazorpayError('Invalid Razorpay amount.') from exc
    return int((value * Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _json_headers(key_id, key_secret):
    token = base64.b64encode(f'{key_id}:{key_secret}'.encode('utf-8')).decode('ascii')
    return {
        'Authorization': f'Basic {token}',
        'Content-Type': 'application/json',
    }


def _decode_body(resp):
    raw = resp.read().decode('utf-8', errors='ignore')
    try:
        return json.loads(raw or '{}')
    except json.JSONDecodeError as exc:
        raise RazorpayError(f'Invalid Razorpay response: {raw[:300]}') from exc


def create_razorpay_order(*, order, customer, key_id, key_secret):
    if not key_id or not key_secret:
        raise RazorpayError('Razorpay credentials missing. Check RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET.')

    amount_paise = to_paise(order.my_pay or order.total_amount)
    if amount_paise < 100:
        raise RazorpayError('Razorpay minimum payable amount is Rs. 1.00.')

    payload = {
        'amount': amount_paise,
        'currency': 'INR',
        'receipt': str(order.order_number)[:40],
        'notes': {
            'neverq_order_number': str(order.order_number),
            'customer_id': str(customer.pk),
            'company_id': str(order.company_id),
        },
    }

    req = request.Request(
        'https://api.razorpay.com/v1/orders',
        data=json.dumps(payload).encode('utf-8'),
        method='POST',
        headers=_json_headers(key_id, key_secret),
    )

    try:
        with request.urlopen(req, timeout=30) as resp:
            return _decode_body(resp)
    except error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='ignore')
        raise RazorpayError(f'Razorpay order creation failed: HTTP {exc.code} {body[:400]}') from exc
    except error.URLError as exc:
        raise RazorpayError(f'Razorpay order creation connection failed: {exc}') from exc


def verify_razorpay_signature(*, order_id, payment_id, signature, key_secret):
    if not order_id or not payment_id or not signature or not key_secret:
        return False

    payload = f'{order_id}|{payment_id}'.encode('utf-8')
    expected = hmac.new(key_secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_razorpay_webhook_signature(*, body_bytes, signature_header, webhook_secret):
    """
    Verify a Razorpay webhook delivery.

    Razorpay signs the raw POST body with HMAC-SHA256 using the webhook secret
    (configured separately in the Razorpay Dashboard → Webhooks).  The resulting
    hex digest is sent in the ``X-Razorpay-Signature`` header.

    Returns True only when the signature is valid and all arguments are present.
    Returns False on any missing argument so the caller can return 400/403 safely.
    """
    if not body_bytes or not signature_header or not webhook_secret:
        return False

    expected = hmac.new(
        webhook_secret.encode('utf-8'),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
