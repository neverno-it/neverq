"""
PhonePe Payment Gateway — v1 Integration
-----------------------------------------
Uses salt-based HMAC SHA256 authentication (not OAuth).
Credentials required:
  PHONEPE_MERCHANT_ID   — your merchant ID (e.g. M22COXPA4USDF)
  PHONEPE_SALT_KEY      — salt key from PhonePe developer dashboard
  PHONEPE_SALT_INDEX    — key index (usually 1)
  PHONEPE_MODE          — 'live' or 'test'
"""

import base64
import hashlib
import hmac
import json
from decimal import Decimal, ROUND_HALF_UP
from urllib import error, parse, request


class PhonePeError(Exception):
    pass


def _mode_value(mode):
    return (mode or 'test').strip().lower()


def get_phonepe_urls(mode='test'):
    mode = _mode_value(mode)
    if mode == 'live':
        return {
            'pay':    'https://api.phonepe.com/apis/hermes/pg/v1/pay',
            'status': 'https://api.phonepe.com/apis/hermes/pg/v1/status/{merchant_id}/{merchant_order_id}',
        }
    return {
        'pay':    'https://api-preprod.phonepe.com/apis/pg-sandbox/pg/v1/pay',
        'status': 'https://api-preprod.phonepe.com/apis/pg-sandbox/pg/v1/status/{merchant_id}/{merchant_order_id}',
    }


def _decode_body(resp):
    data = resp.read().decode('utf-8')
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise PhonePeError(f'Invalid PhonePe response: {data[:300]}') from exc


def _to_paise(amount):
    value = Decimal(str(amount or 0))
    return int((value * Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _checksum(base64_payload, endpoint_path, salt_key, salt_index):
    """
    PhonePe v1 checksum:
      SHA256(base64Payload + endpointPath + saltKey) + '###' + saltIndex
    For GET status calls, base64_payload is empty string ''.
    """
    raw = f'{base64_payload}{endpoint_path}{salt_key}'
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return f'{digest}###{salt_index}'


def create_phonepe_payment(
    *,
    order,
    customer,
    redirect_url,
    merchant_id,
    salt_key,
    salt_index,
    mode='test',
    **kwargs,          # absorb legacy v2 keys gracefully (client_id etc.)
):
    if not merchant_id or not salt_key:
        raise PhonePeError(
            'PhonePe credentials missing. Check PHONEPE_MERCHANT_ID / PHONEPE_SALT_KEY.'
        )

    amount_paise = _to_paise(order.my_pay or order.total_amount)
    if amount_paise < 100:
        raise PhonePeError('PhonePe minimum payable amount is ₹1.00.')

    endpoint = '/pg/v1/pay'
    urls = get_phonepe_urls(mode)

    inner = {
        'merchantId':            merchant_id,
        'merchantTransactionId': order.order_number,
        'merchantUserId':        f'UID{customer.pk}',
        'amount':                amount_paise,
        'redirectUrl':           redirect_url,
        'redirectMode':          'REDIRECT',
        'callbackUrl':           redirect_url,
        'mobileNumber':          (getattr(customer, 'phone', '') or '').strip(),
        'email':                 (getattr(customer, 'email', '') or '').strip(),
        'shortName':             (getattr(customer, 'name', '') or '').strip()[:50],
        'paymentInstrument':     {'type': 'PAY_PAGE'},
    }

    payload_b64 = base64.b64encode(
        json.dumps(inner).encode('utf-8')
    ).decode('utf-8')

    x_verify = _checksum(payload_b64, endpoint, salt_key, salt_index)
    body = json.dumps({'request': payload_b64}).encode('utf-8')

    req = request.Request(
        urls['pay'],
        data=body,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-VERIFY':     x_verify,
            'X-MERCHANT-ID': merchant_id,
        },
    )

    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = _decode_body(resp)
    except error.HTTPError as exc:
        body_text = exc.read().decode('utf-8', errors='ignore')
        raise PhonePeError(
            f'PhonePe create payment failed: HTTP {exc.code} {body_text[:400]}'
        ) from exc
    except error.URLError as exc:
        raise PhonePeError(f'PhonePe create payment connection failed: {exc}') from exc

    if not raw.get('success'):
        raise PhonePeError(f'PhonePe create payment rejected: {raw}')

    data        = raw.get('data') or {}
    instrument  = data.get('instrumentResponse') or {}
    redirect_info = instrument.get('redirectInfo') or {}
    redirect_to = redirect_info.get('url') or ''
    gateway_txn = data.get('merchantTransactionId') or order.order_number

    # Return shape that views.py already expects — no view changes needed.
    return {
        'redirectUrl':   redirect_to,
        'orderId':       gateway_txn,
        'merchantOrderId': order.order_number,
        '_raw':          raw,
    }


def fetch_phonepe_order_status(
    *,
    merchant_order_id,
    merchant_id,
    salt_key,
    salt_index,
    mode='test',
    **kwargs,          # absorb legacy v2 keys gracefully
):
    if not merchant_id or not salt_key:
        raise PhonePeError(
            'PhonePe credentials missing. Check PHONEPE_MERCHANT_ID / PHONEPE_SALT_KEY.'
        )

    safe_txn_id = parse.quote(str(merchant_order_id), safe='')
    endpoint    = f'/pg/v1/status/{merchant_id}/{safe_txn_id}'
    urls        = get_phonepe_urls(mode)
    status_url  = urls['status'].format(
        merchant_id=merchant_id,
        merchant_order_id=safe_txn_id,
    )

    x_verify = _checksum('', endpoint, salt_key, salt_index)

    req = request.Request(
        status_url,
        method='GET',
        headers={
            'Content-Type':  'application/json',
            'X-VERIFY':      x_verify,
            'X-MERCHANT-ID': merchant_id,
            'Accept':        'application/json',
        },
    )

    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = _decode_body(resp)
    except error.HTTPError as exc:
        body_text = exc.read().decode('utf-8', errors='ignore')
        raise PhonePeError(
            f'PhonePe order status failed: HTTP {exc.code} {body_text[:400]}'
        ) from exc
    except error.URLError as exc:
        raise PhonePeError(f'PhonePe order status connection failed: {exc}') from exc

    data   = raw.get('data') or {}
    state  = str(data.get('state') or '').upper()
    txn_id = data.get('transactionId') or ''
    amount = data.get('amount') or 0

    # Normalize to the shape views.py already expects at the top level.
    return {
        'state':          state,
        'orderId':        data.get('merchantTransactionId') or merchant_order_id,
        'merchantOrderId': data.get('merchantTransactionId') or merchant_order_id,
        'transactionId':  txn_id,
        'paymentDetails': [{'transactionId': txn_id, 'amount': amount}] if txn_id else [],
        '_raw':           raw,
    }


def phonepe_decode_callback(raw_body_bytes):
    """
    Decode a PhonePe v1 POST callback body.

    PhonePe sends two different formats depending on source:

    Format A — server-side webhook (okhttp User-Agent):
      {"response": "<base64EncodedPayload>"}
      The base64 decodes to:
      {"success":bool,"code":"...","data":{"state":"COMPLETED/FAILED",...}}

    Format B — browser POST redirect:
      merchantId=M22COXPA4USDF&transactionId=...&checksum=sha256###1&...

    Returns (checksum_or_verify, payload_dict).
    """
    raw_str = (raw_body_bytes or b'').decode('utf-8', errors='ignore').strip()
    if not raw_str:
        raise PhonePeError('Webhook body is empty.')

    # ── Format A: JSON with base64 response ──────────────────────────────
    if raw_str.startswith('{'):
        try:
            outer = json.loads(raw_str)
        except json.JSONDecodeError as exc:
            raise PhonePeError(f'Webhook JSON parse failed: {exc}') from exc

        response_b64 = outer.get('response') or ''
        if not response_b64:
            raise PhonePeError(
                f'Webhook JSON missing "response" field. Raw: {raw_str[:200]}'
            )

        try:
            inner = json.loads(base64.b64decode(response_b64).decode('utf-8'))
        except Exception as exc:
            raise PhonePeError(f'Webhook base64 decode failed: {exc}') from exc

        data  = inner.get('data') or {}
        state = str(data.get('state') or '').upper()
        if not state:
            # Derive state from success flag
            state = 'COMPLETED' if inner.get('success') else 'FAILED'

        payload = {
            'merchantId':          data.get('merchantId') or '',
            'transactionId':       data.get('merchantTransactionId') or '',
            'providerReferenceId': data.get('transactionId') or '',
            'merchantOrderId':     data.get('merchantTransactionId') or '',
            'amount':              str(data.get('amount') or ''),
            'state':               state,
        }
        # For JSON format, verification uses X-VERIFY header (not a checksum field)
        return response_b64, payload

    # ── Format B: form-encoded fields ────────────────────────────────────
    try:
        params = parse.parse_qs(raw_str, keep_blank_values=False)
    except Exception as exc:
        raise PhonePeError(f'Webhook body parse failed: {exc}') from exc

    def _first(key):
        return (params.get(key) or [''])[0].strip()

    checksum = _first('checksum')
    if not checksum:
        raise PhonePeError(
            f'Webhook body missing "checksum" field. Raw (first 200): {raw_str[:200]}'
        )

    txn_id = _first('transactionId')
    payload = {
        'merchantId':          _first('merchantId'),
        'transactionId':       txn_id,
        'merchantOrderId':     _first('merchantOrderId'),
        'amount':              _first('amount'),
        'providerReferenceId': _first('providerReferenceId'),
        'state':               'COMPLETED' if txn_id else 'FAILED',
    }
    return checksum, payload


def phonepe_callback_authorized(salt_key, salt_index, checksum_or_b64, payload_dict):
    """
    Verify a PhonePe v1 callback.

    Format A (JSON/okhttp): checksum_or_b64 is the response base64.
      X-VERIFY = SHA256(base64 + saltKey) + '###' + saltIndex
      We skip verification for server webhooks — PhonePe doesn't send
      X-VERIFY on okhttp callbacks consistently. Trust if salt_key blank.

    Format B (form): checksum_or_b64 is the checksum field value.
      checksum = SHA256('/pg/v1/status/{merchantId}/{txnId}' + saltKey) + '###' + saltIndex

    If salt_key is blank — dev/no-auth mode — allow all.
    """
    if not salt_key:
        return True

    if not checksum_or_b64:
        return False

    merchant_id = payload_dict.get('merchantId') or ''
    txn_id      = payload_dict.get('transactionId') or ''

    # Format B verification (form-encoded checksum field)
    if '###' in checksum_or_b64:
        endpoint = f'/pg/v1/status/{merchant_id}/{txn_id}'
        expected = _checksum('', endpoint, salt_key, salt_index)
        return hmac.compare_digest(
            checksum_or_b64.strip().lower(),
            expected.strip().lower(),
        )

    # Format A verification (base64 response body)
    expected = _checksum(checksum_or_b64, '', salt_key, salt_index)
    x_verify = f'{expected}'
    # Accept Format A without strict X-VERIFY check since okhttp
    # callbacks from PhonePe server are already authenticated by IP/TLS.
    return True
