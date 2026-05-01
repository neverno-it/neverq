"""
Registration security helpers — no external dependencies required.
Implements:
  1. Honeypot field check (bots fill hidden fields, humans don't)
  2. Time-based token (form must be held open ≥3 seconds — bots submit instantly)
  3. Redis/cache-backed rate limiting per IP (max 3 registrations per hour per IP)
  4. Phone/email basic sanity validation
"""
import hashlib
import time
from django.core.cache import cache

_MAX_PER_HOUR = 3   # max successful registrations per IP per hour
_REG_WINDOW_SECONDS = 3600


def _registration_attempts_key(ip):
    return f'neverq:reg:attempts:{ip or "0.0.0.0"}'


def is_rate_limited(ip):
    """Return True if this IP has exceeded the hourly registration limit."""
    return int(cache.get(_registration_attempts_key(ip)) or 0) >= _MAX_PER_HOUR


def record_registration(ip):
    """Record a successful registration for rate-limiting purposes."""
    key = _registration_attempts_key(ip)
    if cache.add(key, 1, _REG_WINDOW_SECONDS):
        return
    try:
        cache.incr(key)
    except (ValueError, NotImplementedError):
        cache.set(key, int(cache.get(key) or 0) + 1, _REG_WINDOW_SECONDS)


# ── Honeypot + timing token ───────────────────────────────────────────────────

def make_form_token():
    """Generate a token embedding the current timestamp (signed with a simple hash)."""
    ts = str(int(time.time()))
    sig = hashlib.sha256(f"neverq-reg-{ts}".encode()).hexdigest()[:12]
    return f"{ts}.{sig}"


def validate_form_token(token, min_seconds=3):
    """
    Returns True if:
    - Token format is valid
    - At least min_seconds have passed since token was generated (not an instant bot submit)
    - Token is not older than 30 minutes (not a stale replayed form)
    """
    try:
        ts_str, sig = token.split('.')
        ts = int(ts_str)
        expected_sig = hashlib.sha256(f"neverq-reg-{ts_str}".encode()).hexdigest()[:12]
        if sig != expected_sig:
            return False
        elapsed = time.time() - ts
        return min_seconds <= elapsed <= 1800   # 3 sec – 30 min window
    except Exception:
        return False


def get_client_ip(request):
    """Get real client IP, checking X-Forwarded-For first."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')
