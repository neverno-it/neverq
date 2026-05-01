import json
import uuid
from datetime import date
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token as get_csrf_token
from django.utils import timezone
from django.core.cache import cache
from django.core.mail import EmailMessage
from apps.core.models import Company, Building
from .models import Customer, StaffUser
from .forms import StaffLoginForm, CustomerLoginForm, CustomerRegisterForm, CustomerProfileForm, notify_customer_registration_needing_approval
from .decorators import customer_login_required, enforce_customer_active_state
from django.conf import settings
from .google_auth import (
    GoogleOAuthError,
    exchange_code_for_user_info,
    get_google_auth_url,
)
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token


# ── Staff Login / Logout ──────────────────────────────────

def staff_login(request):
    if request.user.is_authenticated:
        return _staff_redirect(request.user)

    form = StaffLoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data['email'],
            password=form.cleaned_data['password']
        )
        if user and user.is_active:
            login(request, user)
            nxt = request.GET.get('next', '')
            if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(nxt)
            return _staff_redirect(user)
        messages.error(request, 'Invalid email or password.')
    return render(request, 'auth/staff_login.html', {'form': form})


def _staff_redirect(user):
    """Per-user landing page, falling back to role default."""
    try:
        from apps.core.access import get_safe_landing_url
        return redirect(get_safe_landing_url(user))
    except (ImportError, AttributeError, ValueError, KeyError):
        # Fallback: role-based default if access config is missing or broken
        defaults = {
            StaffUser.ROLE_SUPERADMIN: 'dashboard:home',
            StaffUser.ROLE_ADMIN: 'dashboard:home',
            StaffUser.ROLE_POS: 'dashboard:cashier',
            StaffUser.ROLE_CAFEMAN: 'dashboard:kitchen',
            StaffUser.ROLE_REPORTS: 'dashboard:reports',
        }
        return redirect(defaults.get(user.role, 'dashboard:home'))


def staff_logout(request):
    logout(request)
    request.session.flush()
    return redirect('accounts:login')


# ── Customer Login / Register / Logout ───────────────────

def _normalize_customer_email(value):
    return (value or '').strip().lower()


def _find_active_customer(*, company=None, company_id=None, email=''):
    """
    Resolve a customer record for auth flows with tolerance for legacy imports
    that may have mixed-case or whitespace-padded emails.
    """
    normalized_email = _normalize_customer_email(email)
    if not normalized_email:
        return None

    filters = {'is_active': True, 'is_deleted': False}
    if company is not None:
        filters['company'] = company
    elif company_id is not None:
        filters['company_id'] = company_id

    qs = Customer.objects.filter(**filters)

    customer = qs.filter(email__iexact=normalized_email).first()
    if customer:
        return customer

    # Legacy/import fallback: some old rows may contain surrounding spaces.
    for candidate in qs.only('id', 'email', 'name', 'password_hash', 'company_id'):
        if _normalize_customer_email(candidate.email) == normalized_email:
            return candidate
    return None


def _finish_customer_session(request, customer):
    request.session.cycle_key()
    request.session['customer_id'] = customer.pk
    request.session['company_id'] = customer.company_id
    request.session.pop('pending_customer_ids', None)
    request.session.pop('pending_customer_next', None)
    request.session.pop('pending_customer_email', None)


REGISTRATION_VERIFY_TTL = 60 * 60 * 24 * 2  # 48 hours
REGISTRATION_DOB_DEFAULT_YEAR = 2000
REGISTRATION_DUMMY_PHONE = '9999999999'
REGISTRATION_DAY_OPTIONS = list(range(1, 32))
REGISTRATION_MONTH_OPTIONS = list(range(1, 13))
OTP_RESET_TTL = 10 * 60
OTP_COOLDOWN_TTL = 60
OTP_MAX_FAILED_ATTEMPTS = 5


def _registration_cache_key(token):
    return f'customer_registration_verify:{token}'


def _otp_cache_subject(email):
    return _normalize_customer_email(email)


def _otp_reset_keys(email):
    subject = _otp_cache_subject(email)
    return (
        f'neverq:otp:reset:{subject}',
        f'neverq:otp:reset:attempts:{subject}',
        f'neverq:otp:reset:cooldown:{subject}',
    )


def _otp_registration_keys(email):
    subject = _otp_cache_subject(email)
    return (
        f'neverq:otp:reg:attempts:{subject}',
        f'neverq:otp:reg:cooldown:{subject}',
    )


def _cache_increment(key, ttl):
    if cache.add(key, 1, ttl):
        return 1
    try:
        return cache.incr(key)
    except (ValueError, NotImplementedError):
        value = int(cache.get(key) or 0) + 1
        cache.set(key, value, ttl)
        return value


def _normalize_registration_phone(value):
    return (value or '').strip()


def _coerce_registration_birth_date(raw_value):
    raw = (raw_value or '').strip()
    if not raw:
        return '', ''
    try:
        return date.fromisoformat(raw).isoformat(), ''
    except ValueError:
        pass

    normalized = raw.replace('/', '-').replace('.', '-')
    parts = [part.strip() for part in normalized.split('-') if part.strip()]
    if len(parts) != 2:
        return '', 'Enter birth date as DD-MM.'

    try:
        day = int(parts[0])
        month = int(parts[1])
        parsed = date(REGISTRATION_DOB_DEFAULT_YEAR, month, day)
    except (TypeError, ValueError):
        return '', 'Enter birth date as DD-MM.'
    return parsed.isoformat(), ''


def _store_pending_registration(payload):
    token = uuid.uuid4().hex
    cache.set(_registration_cache_key(token), payload, REGISTRATION_VERIFY_TTL)
    return token


def _pop_pending_registration(token):
    if not token:
        return None
    key = _registration_cache_key(token)
    payload = cache.get(key)
    if payload:
        cache.delete(key)
    return payload


def _peek_pending_registration(token):
    if not token:
        return None
    return cache.get(_registration_cache_key(token))


def _customer_exists_for_company_email(company_id, email):
    email = _normalize_customer_email(email)
    if not company_id or not email:
        return False
    qs = Customer.objects.filter(company_id=company_id, is_deleted=False)
    if qs.filter(email__iexact=email).exists():
        return True
    return any(_normalize_customer_email(value) == email for value in qs.values_list('email', flat=True))


def _send_customer_verification_email(request, *, recipient_email, customer_name, verify_token):
    verify_url = request.build_absolute_uri(reverse('accounts:customer_verify_registration')) + f'?token={verify_token}'
    from_email = (getattr(settings, 'DEFAULT_FROM_EMAIL', '') or getattr(settings, 'EMAIL_HOST_USER', '') or 'noreplay@neverno.in')
    subject = f"Verify your {getattr(settings, 'NEVERQ', {}).get('APP_NAME', 'NeverQ')} account"
    body = (
        f"Hello {customer_name or 'Customer'},\n\n"
        "Please verify your email address to finish creating your customer account.\n\n"
        f"Verification link: {verify_url}\n\n"
        "This link will expire in 48 hours. If you did not request this registration, you can ignore this email.\n"
    )
    mail = EmailMessage(subject=subject, body=body, from_email=from_email, to=[recipient_email])
    mail.send(fail_silently=False)


def _send_customer_reset_otp_email(*, recipient_email, customer_name, otp):
    from_email = (getattr(settings, 'DEFAULT_FROM_EMAIL', '') or getattr(settings, 'EMAIL_HOST_USER', '') or 'noreplay@neverno.in')
    subject = f"Your {getattr(settings, 'NEVERQ', {}).get('APP_NAME', 'NeverQ')} password reset OTP"
    body = (
        f"Hello {customer_name or 'Customer'},\n\n"
        f"Your OTP for password reset is: {otp}\n\n"
        "If you did not request this, please ignore this email."
    )
    mail = EmailMessage(subject=subject, body=body, from_email=from_email, to=[recipient_email])
    mail.send(fail_silently=False)


def _create_customer_from_pending_payload(payload, *, email_verified=True):
    customer = Customer(
        company_id=payload['company_id'],
        building_id=payload.get('building_id') or None,
        name=payload.get('name', ''),
        phone=payload.get('phone', ''),
        email=_normalize_customer_email(payload.get('email', '')),
        date_of_birth=(date.fromisoformat(payload['date_of_birth']) if payload.get('date_of_birth') else None),
        address='',
        password_hash=payload['password_hash'],
        is_email_verified=bool(email_verified),
        is_approved=bool(payload.get('is_approved', True)),
        is_active=True,
        is_deleted=False,
    )
    customer.save()
    notify_customer_registration_needing_approval(customer)
    return customer


def customer_login(request):
    if request.session.get('customer_id'):
        return redirect('orders:menu')

    form = CustomerLoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = _normalize_customer_email(form.cleaned_data['email'])
        password = form.cleaned_data['password']

        base_qs = Customer.objects.filter(
            is_deleted=False,
        ).select_related('company', 'building').only(
            'id',
            'email',
            'name',
            'password_hash',
            'company_id',
            'building_id',
            'company__name',
            'building__name',
        )

        candidates = list(base_qs.filter(email__iexact=email))

        if not candidates:
            candidates = [
                c for c in base_qs
                if _normalize_customer_email(c.email) == email
            ]

        matched = [customer for customer in candidates if customer.check_password(password)]
        for customer in matched:
            enforce_customer_active_state(customer)

        approved_matched = [
            customer for customer in matched
            if customer.is_active and customer.is_approved and customer.is_email_verified
        ]

        if len(approved_matched) == 1:
            customer = approved_matched[0]
            _finish_customer_session(request, customer)
            messages.success(request, f'Welcome back, {customer.name}!')
            _next = request.GET.get('next', '')
            if _next and url_has_allowed_host_and_scheme(_next, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(_next)
            return redirect('orders:menu')

        if len(approved_matched) > 1:
            request.session['pending_customer_ids'] = [c.pk for c in approved_matched]
            _pending_next = request.GET.get('next', '')
            if _pending_next and url_has_allowed_host_and_scheme(_pending_next, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                request.session['pending_customer_next'] = _pending_next
            else:
                request.session['pending_customer_next'] = 'orders:menu'
            request.session['pending_customer_email'] = email
            return redirect('accounts:customer_select_account')

        if matched:
            # Distinguish between unverified and unapproved for a clear error message.
            unverified = [c for c in matched if c.is_approved and not c.is_email_verified]
            if unverified:
                messages.error(request, 'Please verify your email before signing in. Check your inbox for the verification link.')
            elif any(not c.is_active for c in matched):
                messages.error(request, 'Your account is inactive. Please contact admin.')
            else:
                messages.error(request, 'Your account is pending approval.')
        else:
            messages.error(request, 'Incorrect email or password.')

    return render(request, 'auth/customer_login.html', {'form': form, 'next': request.GET.get('next', '')})


def customer_select_account(request):
    pending_ids = request.session.get('pending_customer_ids') or []
    if not pending_ids:
        return redirect('accounts:customer_login')
    candidates = list(Customer.objects.filter(pk__in=pending_ids, is_deleted=False, is_active=True).select_related('company', 'building').order_by('company__name', 'building__name', 'name'))
    if len(candidates) <= 1:
        if candidates:
            _finish_customer_session(request, candidates[0])
            messages.success(request, f'Welcome back, {candidates[0].name}!')
            return redirect(request.session.get('pending_customer_next', 'orders:menu'))
        return redirect('accounts:customer_login')
    if request.method == 'POST':
        selected_id = request.POST.get('customer_id')
        chosen = next((c for c in candidates if str(c.pk) == str(selected_id)), None)
        if chosen is None:
            messages.error(request, 'Please select a valid company account.')
        else:
            _finish_customer_session(request, chosen)
            messages.success(request, f'Welcome back, {chosen.name}!')
            return redirect(request.session.get('pending_customer_next', 'orders:menu'))
    return render(request, 'auth/customer_select_account.html', {'candidates': candidates, 'email': request.session.get('pending_customer_email','')})

def google_login_redirect(request):
    state = uuid.uuid4().hex
    request.session['google_oauth_state'] = state
    redirect_uri = request.build_absolute_uri(reverse('accounts:google_callback'))
    request.session['google_oauth_redirect_uri'] = redirect_uri

    try:
        auth_url = get_google_auth_url(state, redirect_uri)
    except GoogleOAuthError as exc:
        messages.error(request, f'Google sign-in is not available right now: {exc}')
        return redirect('accounts:customer_login')

    return redirect(auth_url)


def google_callback(request):
    expected_state = request.session.get('google_oauth_state')
    received_state = request.GET.get('state', '')
    redirect_uri = request.session.get('google_oauth_redirect_uri') or request.build_absolute_uri(
        reverse('accounts:google_callback')
    )

    request.session.pop('google_oauth_state', None)
    request.session.pop('google_oauth_redirect_uri', None)

    if not expected_state or expected_state != received_state:
        messages.error(request, 'Google sign-in failed. Invalid state.')
        return redirect('accounts:customer_login')

    code = request.GET.get('code', '')
    if not code:
        messages.error(request, 'Google sign-in was cancelled or no authorization code was returned.')
        return redirect('accounts:customer_login')

    try:
        user_info = exchange_code_for_user_info(code, redirect_uri)
    except GoogleOAuthError as exc:
        messages.error(request, f'Google sign-in failed: {exc}')
        return redirect('accounts:customer_login')

    email = _normalize_customer_email(user_info.get('email'))
    name = (user_info.get('name') or '').strip()

    request.session['google_email'] = email
    request.session['google_name'] = name

    base_qs = Customer.objects.filter(
        is_deleted=False,
    ).select_related('company', 'building').only(
        'id',
        'email',
        'name',
        'company_id',
        'building_id',
        'company__name',
        'building__name',
        'is_active',
        'is_approved',
    )

    candidates = list(base_qs.filter(email__iexact=email))
    if not candidates:
        candidates = [
            c for c in base_qs
            if _normalize_customer_email(c.email) == email
        ]

    if not candidates:
        messages.info(request, 'No account found for this Google email. Please register first.')
        return redirect('accounts:customer_register')

    for c in candidates:
        enforce_customer_active_state(c)

    # Phase 4: Google proves email ownership — auto-mark unverified accounts as verified.
    for c in candidates:
        if c.is_active and c.is_approved and not c.is_email_verified:
            c.is_email_verified = True
            c.save(update_fields=['is_email_verified'])

    approved_active = [c for c in candidates if c.is_active and c.is_approved and c.is_email_verified]
    if not approved_active:
        if any(not c.is_active for c in candidates):
            messages.error(request, 'Your account is inactive. Please contact admin.')
        else:
            messages.error(request, 'Your account is pending approval. Please contact admin.')
        return redirect('accounts:customer_login')

    if len(approved_active) == 1:
        customer = approved_active[0]
        _finish_customer_session(request, customer)
        messages.success(request, f'Welcome back, {customer.name}!')
        return redirect('orders:menu')

    request.session['pending_customer_ids'] = [c.pk for c in approved_active]
    request.session['pending_customer_next'] = 'orders:menu'
    request.session['pending_customer_email'] = email
    messages.info(request, 'Select the company account you want to use.')
    return redirect('accounts:customer_select_account')


def _allowed_google_app_client_ids():
    ids = set()
    if settings.GOOGLE_CLIENT_ID:
        ids.add(settings.GOOGLE_CLIENT_ID.strip())
    for value in getattr(settings, 'GOOGLE_APP_ALLOWED_CLIENT_IDS', []):
        value = (value or '').strip()
        if value:
            ids.add(value)
    return ids


def _verify_google_app_id_token(raw_id_token):
    """
    Verify a Google ID token for native-app login.
    Audience is validated against configured allowed client IDs.
    """
    allowed_client_ids = _allowed_google_app_client_ids()
    if not allowed_client_ids:
        raise ValueError('Google app client IDs are not configured.')

    token_data = google_id_token.verify_oauth2_token(
        raw_id_token,
        GoogleRequest(),
        audience=None,  # manual audience validation below
    )

    issuer = (token_data.get('iss') or '').strip()
    audience = (token_data.get('aud') or '').strip()
    email = _normalize_customer_email(token_data.get('email', ''))
    email_verified = bool(token_data.get('email_verified'))

    if issuer not in {'accounts.google.com', 'https://accounts.google.com'}:
        raise ValueError('Invalid token issuer.')
    if audience not in allowed_client_ids:
        raise ValueError('Token audience is not allowed.')
    if not email:
        raise ValueError('Google token did not include an email.')
    if not email_verified:
        raise ValueError('Google email is not verified.')

    return {
        'email': email,
        'name': (token_data.get('name') or '').strip(),
    }


def _build_google_app_login_response(request, *, status, message, next_url):
    # Force-save session so we can return the concrete session key to Flutter.
    request.session.save()
    csrf_token = get_csrf_token(request)
    host = request.get_host().split(':', 1)[0]
    return JsonResponse({
        'ok': True,
        'status': status,
        'message': message,
        'next_url': next_url,
        'cookies': {
            'session': {
                'name': settings.SESSION_COOKIE_NAME,
                'value': request.session.session_key or '',
                'domain': host,
                'path': '/',
                'secure': bool(settings.SESSION_COOKIE_SECURE or request.is_secure()),
            },
            'csrf': {
                'name': settings.CSRF_COOKIE_NAME,
                'value': csrf_token,
                'domain': host,
                'path': '/',
                'secure': bool(settings.CSRF_COOKIE_SECURE or request.is_secure()),
            },
        },
    })


def _try_auto_create_google_customer(*, email, name):
    if not getattr(settings, 'GOOGLE_APP_AUTO_CREATE_CUSTOMER', True):
        return None

    default_company_id = getattr(settings, 'GOOGLE_APP_DEFAULT_COMPANY_ID', None)
    company = None
    if default_company_id:
        company = Company.objects.filter(
            pk=default_company_id,
            is_deleted=False,
            is_active=True,
        ).first()
    if company is None:
        live_companies = list(Company.objects.filter(is_deleted=False, is_active=True).order_by('id')[:2])
        if len(live_companies) == 1:
            company = live_companies[0]

    if company is None:
        return None

    customer = Customer(
        company=company,
        name=name or (email.split('@')[0] if email else 'Customer'),
        phone=REGISTRATION_DUMMY_PHONE,
        email=email,
        address='',
        is_email_verified=True,
        is_approved=True,
        is_active=True,
        is_deleted=False,
    )
    customer.set_password(uuid.uuid4().hex)
    customer.save()
    return customer


@csrf_exempt
@require_POST
def google_app_login(request):
    """
    Native app Google sign-in endpoint.
    Accepts Google ID token from Flutter, verifies with Google,
    and initializes the same customer session used by web flows.
    """
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON payload.'}, status=400)

    raw_id_token = (payload.get('id_token') or '').strip()
    if not raw_id_token:
        return JsonResponse({'ok': False, 'error': 'Missing id_token.'}, status=400)

    try:
        user_info = _verify_google_app_id_token(raw_id_token)
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': f'Google token verification failed: {exc}'}, status=400)

    email = user_info['email']
    name = user_info['name']

    request.session['google_email'] = email
    request.session['google_name'] = name

    base_qs = Customer.objects.filter(
        is_deleted=False,
    ).select_related('company', 'building').only(
        'id',
        'email',
        'name',
        'company_id',
        'building_id',
        'company__name',
        'building__name',
        'is_active',
        'is_approved',
        'is_email_verified',
    )

    candidates = list(base_qs.filter(email__iexact=email))
    if not candidates:
        candidates = [c for c in base_qs if _normalize_customer_email(c.email) == email]

    if not candidates:
        created = _try_auto_create_google_customer(email=email, name=name)
        if created:
            candidates = [created]
        else:
            return _build_google_app_login_response(
                request,
                status='register_required',
                message='No account found. Continue registration to complete onboarding.',
                next_url=reverse('accounts:customer_register'),
            )

    for customer in candidates:
        enforce_customer_active_state(customer)

    for customer in candidates:
        if customer.is_active and customer.is_approved and not customer.is_email_verified:
            customer.is_email_verified = True
            customer.save(update_fields=['is_email_verified'])

    approved_active = [c for c in candidates if c.is_active and c.is_approved and c.is_email_verified]

    if not approved_active:
        if any(not c.is_active for c in candidates):
            return JsonResponse({'ok': False, 'error': 'Your account is inactive. Please contact admin.'}, status=403)
        return JsonResponse({'ok': False, 'error': 'Your account is pending approval. Please contact admin.'}, status=403)

    request.session.cycle_key()
    if len(approved_active) == 1:
        customer = approved_active[0]
        _finish_customer_session(request, customer)
        return _build_google_app_login_response(
            request,
            status='logged_in',
            message=f'Welcome back, {customer.name}!',
            next_url=reverse('orders:menu'),
        )

    request.session['pending_customer_ids'] = [c.pk for c in approved_active]
    request.session['pending_customer_next'] = 'orders:menu'
    request.session['pending_customer_email'] = email
    return _build_google_app_login_response(
        request,
        status='select_account',
        message='Select the company account you want to use.',
        next_url=reverse('accounts:customer_select_account'),
    )

def customer_register(request):
    from apps.core.registration_security import (
        is_rate_limited, record_registration, get_client_ip,
        make_form_token, validate_form_token,
    )
    ip = get_client_ip(request)

    if is_rate_limited(ip):
        messages.error(request, 'Too many registrations from your network. Please try again later.')
        return redirect('accounts:customer_login')

    birth_day_month_error = ''
    birth_day_month_value = ''
    birth_day_value = ''
    birth_month_value = ''
    if request.method == 'POST':
        if request.POST.get('website_url', '').strip():
            messages.success(request, 'Account created! Please log in.')
            return redirect('accounts:customer_login')

        token = request.POST.get('_form_token', '')
        birth_day_value = (request.POST.get('birth_day') or '').strip()
        birth_month_value = (request.POST.get('birth_month') or '').strip()
        birth_day_month_value = (request.POST.get('birth_day_month') or '').strip()
        post_data = request.POST.copy()
        post_data['phone'] = _normalize_registration_phone(post_data.get('phone'))
        if not post_data.get('date_of_birth'):
            combined_birth_day_month = birth_day_month_value
            if birth_day_value and birth_month_value:
                combined_birth_day_month = f'{birth_day_value}-{birth_month_value}'
            coerced_birth_date, birth_day_month_error = _coerce_registration_birth_date(combined_birth_day_month)
            if coerced_birth_date:
                post_data['date_of_birth'] = coerced_birth_date
        if not validate_form_token(token, min_seconds=3):
            messages.error(request, 'Form submission too fast or invalid. Please try again.')
            token = make_form_token()
            form = CustomerRegisterForm(post_data)
            return render(request, 'auth/customer_register.html', {
                'form': form,
                'form_token': token,
                'today': timezone.localdate().isoformat(),
                'birth_day_month_value': birth_day_month_value,
                'birth_day_value': birth_day_value,
                'birth_month_value': birth_month_value,
                'birth_day_month_error': birth_day_month_error,
                'birth_day_options': REGISTRATION_DAY_OPTIONS,
                'birth_month_options': REGISTRATION_MONTH_OPTIONS,
                'dummy_phone': REGISTRATION_DUMMY_PHONE,
            })

        form = CustomerRegisterForm(post_data)
        if form.is_valid():
            google_email = _normalize_customer_email(request.session.get('google_email', ''))
            submitted_email = _normalize_customer_email(form.cleaned_data.get('email'))
            is_google_verified_signup = bool(google_email and google_email == submitted_email)

            if is_google_verified_signup:
                # Phase 4: Google proves email → auto-approve + auto-login immediately.
                customer = form.save(email_verified=True)
                # Force approval regardless of company setting — Google email is trusted proof.
                if not customer.is_approved:
                    customer.is_approved = True
                    customer.save(update_fields=['is_approved'])
                record_registration(ip)
                request.session.pop('google_email', None)
                request.session.pop('google_name', None)
                _finish_customer_session(request, customer)
                messages.success(request, f'Welcome, {customer.name}! Your account is ready.')
                return redirect('orders:menu')

            # Phase 4: OTP-based verification instead of email link.
            import random as _random
            otp = _random.randint(100000, 999999)
            pending_payload = form.build_pending_payload()
            # Embed OTP in the cached payload
            pending_payload['registration_otp'] = otp
            # Force is_approved True — OTP proves email ownership, no admin wait
            pending_payload['is_approved'] = True
            verify_token = _store_pending_registration(pending_payload)

            try:
                _send_customer_registration_otp_email(
                    request,
                    recipient_email=pending_payload['email'],
                    customer_name=pending_payload['name'],
                    otp=otp,
                )
            except Exception:
                cache.delete(_registration_cache_key(verify_token))
                messages.error(request, 'We could not send the OTP email right now. Please try again shortly.')
                token = make_form_token()
                return render(request, 'auth/customer_register.html', {
                    'form': form,
                    'form_token': token,
                    'today': timezone.localdate().isoformat(),
                    'birth_day_month_value': birth_day_month_value,
                    'birth_day_value': birth_day_value,
                    'birth_month_value': birth_month_value,
                    'birth_day_month_error': birth_day_month_error,
                    'birth_day_options': REGISTRATION_DAY_OPTIONS,
                    'birth_month_options': REGISTRATION_MONTH_OPTIONS,
                    'dummy_phone': REGISTRATION_DUMMY_PHONE,
                })

            record_registration(ip)
            request.session.pop('google_email', None)
            request.session.pop('google_name', None)
            # Store token in session so OTP page can retrieve the payload
            request.session['registration_otp_token'] = verify_token
            _, cooldown_key = _otp_registration_keys(pending_payload['email'])
            cache.set(cooldown_key, '1', OTP_COOLDOWN_TTL)
            messages.info(request, f'We sent a 6-digit OTP to {pending_payload["email"]}. Enter it below to activate your account.')
            return redirect('accounts:customer_otp_verify')
    else:
        initial = {}
        google_email = (request.session.get('google_email') or '').strip()
        google_name = (request.session.get('google_name') or '').strip()
        if google_email:
            initial['email'] = google_email
        if google_name:
            initial['name'] = google_name
        initial['phone'] = REGISTRATION_DUMMY_PHONE
        form = CustomerRegisterForm(initial=initial)

    token = make_form_token()
    return render(request, 'auth/customer_register.html', {
        'form': form,
        'form_token': token,
        'today': timezone.localdate().isoformat(),
        'birth_day_month_value': birth_day_month_value,
        'birth_day_value': birth_day_value,
        'birth_month_value': birth_month_value,
        'birth_day_month_error': birth_day_month_error,
        'birth_day_options': REGISTRATION_DAY_OPTIONS,
        'birth_month_options': REGISTRATION_MONTH_OPTIONS,
        'dummy_phone': REGISTRATION_DUMMY_PHONE,
    })


def _send_customer_registration_otp_email(request, *, recipient_email, customer_name, otp):
    """Send registration OTP (6-digit) to the customer's email."""
    from_email = (
        getattr(settings, 'DEFAULT_FROM_EMAIL', '')
        or getattr(settings, 'EMAIL_HOST_USER', '')
        or 'noreplay@neverno.in'
    )
    app_name = getattr(settings, 'NEVERQ', {}).get('APP_NAME', 'NeverQ')
    subject = f'Your {app_name} registration OTP'
    greeting = customer_name or "Customer"
    body = (
        f"Hello {greeting},\n\n"
        f"Your OTP to verify your registration is: {otp}\n\n"
        "Enter this code on the verification page to activate your account.\n"
        "The code expires in 48 hours.\n\n"
        "If you did not request this, please ignore this email."
    )
    mail = EmailMessage(subject=subject, body=body, from_email=from_email, to=[recipient_email])
    mail.send(fail_silently=False)


def customer_otp_verify(request):
    """
    Phase 4 — OTP verification for email registrations.
    Token stored in session; OTP entered on this page.
    On success: creates customer (is_approved=True, is_email_verified=True) and auto-logs in.
    """
    token = (request.session.get('registration_otp_token') or '').strip()
    if not token:
        messages.error(request, 'OTP session expired or invalid. Please register again.')
        return redirect('accounts:customer_register')

    payload = _peek_pending_registration(token)
    if not payload:
        request.session.pop('registration_otp_token', None)
        messages.error(request, 'Your OTP has expired. Please register again.')
        return redirect('accounts:customer_register')

    if request.method == 'POST':
        action = request.POST.get('action', '')
        email = payload.get('email', '')
        attempts_key, cooldown_key = _otp_registration_keys(email)

        # ── Resend OTP ──────────────────────────────────────────
        if action == 'resend':
            if cache.get(cooldown_key):
                messages.warning(request, 'Please wait a minute before requesting another OTP.')
                return redirect('accounts:customer_otp_verify')
            import random as _random
            new_otp = _random.randint(100000, 999999)
            payload['registration_otp'] = new_otp
            # Refresh the cache entry
            cache.set(_registration_cache_key(token), payload, REGISTRATION_VERIFY_TTL)
            cache.delete(attempts_key)
            cache.set(cooldown_key, '1', OTP_COOLDOWN_TTL)
            try:
                _send_customer_registration_otp_email(
                    request,
                    recipient_email=payload['email'],
                    customer_name=payload['name'],
                    otp=new_otp,
                )
                messages.info(request, 'A new OTP has been sent to your email.')
            except Exception:
                messages.error(request, 'Could not resend OTP. Please try again.')
            return redirect('accounts:customer_otp_verify')

        # ── Verify OTP ──────────────────────────────────────────
        entered_otp = (request.POST.get('otp') or '').strip()
        stored_otp  = str(payload.get('registration_otp', ''))

        if not entered_otp:
            messages.error(request, 'Please enter the OTP.')
            return render(request, 'auth/customer_otp_verify.html', {'email': payload.get('email', '')})

        if entered_otp != stored_otp:
            attempts = _cache_increment(attempts_key, REGISTRATION_VERIFY_TTL)
            if attempts >= OTP_MAX_FAILED_ATTEMPTS:
                payload['registration_otp'] = ''
                cache.set(_registration_cache_key(token), payload, REGISTRATION_VERIFY_TTL)
                cache.delete(attempts_key)
                messages.error(request, 'Too many incorrect OTP attempts. Please request a new OTP.')
                return render(request, 'auth/customer_otp_verify.html', {'email': payload.get('email', '')})
            messages.error(request, 'Incorrect OTP. Please try again.')
            return render(request, 'auth/customer_otp_verify.html', {'email': payload.get('email', '')})

        # OTP correct — consume the token
        payload = _pop_pending_registration(token)
        request.session.pop('registration_otp_token', None)
        cache.delete_many([attempts_key, cooldown_key])

        if not payload:
            messages.error(request, 'OTP expired during verification. Please register again.')
            return redirect('accounts:customer_register')

        # Check duplicate (race condition guard)
        if _customer_exists_for_company_email(payload.get('company_id'), payload.get('email')):
            messages.info(request, 'This account already exists. Please sign in.')
            return redirect('accounts:customer_login')

        # Create customer — email verified, auto-approved
        customer = _create_customer_from_pending_payload(payload, email_verified=True)

        # Auto-login immediately — no extra steps
        _finish_customer_session(request, customer)
        messages.success(request, f'Welcome, {customer.name}! Your account is active.')
        return redirect('orders:menu')

    # GET — show OTP form
    return render(request, 'auth/customer_otp_verify.html', {
        'email': payload.get('email', ''),
    })


def customer_verify_registration(request):
    token = (request.GET.get('token') or '').strip()
    payload = _peek_pending_registration(token)
    if not payload:
        messages.error(request, 'This verification link is invalid, expired, or has already been used.')
        return redirect('accounts:customer_register')

    if _customer_exists_for_company_email(payload.get('company_id'), payload.get('email')):
        cache.delete(_registration_cache_key(token))
        messages.info(request, 'This account has already been registered for the selected company. Please sign in.')
        return redirect('accounts:customer_login')

    payload = _pop_pending_registration(token)
    if not payload:
        messages.error(request, 'This verification link is invalid, expired, or has already been used.')
        return redirect('accounts:customer_register')

    customer = _create_customer_from_pending_payload(payload, email_verified=True)
    if customer.is_approved:
        messages.success(request, 'Your email has been verified. You can now sign in.')
    else:
        messages.success(request, 'Your email has been verified. Your account is pending approval and will be usable once approved.')
    return redirect('accounts:customer_login')

def customer_logout(request):
    request.session.flush()
    return redirect('accounts:customer_login')


# ── Customer Profile ──────────────────────────────────────

@customer_login_required
def customer_profile(request):
    customer = request.current_customer
    form = CustomerProfileForm(
        request.POST or None, instance=customer, company=customer.company
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Profile updated.')
        return redirect('accounts:profile')
    return render(request, 'auth/customer_profile.html', {
        'form': form, 'customer': customer
    })


@customer_login_required
def customer_wallet(request):
    customer = request.current_customer
    return render(request, 'auth/customer_wallet.html', {
        'customer': customer,
        'page_title': 'My Wallet',
    })


# ── Forgot Password (Customer) ───────────────────────────

def customer_forgot_password(request):
    """
    Generate a reset token and show reset form.
    In production this should email/SMS the OTP.
    In DEBUG, OTP is shown inline for testing.
    """
    if request.method == 'POST':
        email = _normalize_customer_email(request.POST.get('email', ''))
        company = request.POST.get('company', '')
        otp_val = request.POST.get('otp', '')
        new_pw = request.POST.get('new_password', '')

        if otp_val and new_pw:
            customer = _find_active_customer(company_id=company, email=email)
            if customer:
                otp_key, attempts_key, cooldown_key = _otp_reset_keys(customer.email)
                cached_otp = cache.get(otp_key)
                attempts = int(cache.get(attempts_key) or 0)
                if attempts >= OTP_MAX_FAILED_ATTEMPTS or not cached_otp:
                    cache.delete_many([otp_key, attempts_key])
                    messages.error(request, 'OTP expired or locked. Please request a new OTP.')
                    return render(request, 'auth/customer_forgot_password.html', {
                        'step': 1,
                        'companies': Company.objects.filter(is_active=True, is_deleted=False),
                    })
                if str(cached_otp) == str(otp_val):
                    customer.set_password(new_pw)
                    customer.otp = 0
                    customer.save()
                    cache.delete_many([otp_key, attempts_key, cooldown_key])
                    messages.success(request, 'Password reset! Please log in.')
                    return redirect('accounts:customer_login')
                else:
                    attempts = _cache_increment(attempts_key, OTP_RESET_TTL)
                    if attempts >= OTP_MAX_FAILED_ATTEMPTS:
                        cache.delete_many([otp_key, attempts_key])
                        messages.error(request, 'Too many incorrect OTP attempts. Please request a new OTP.')
                    else:
                        messages.error(request, 'Invalid OTP.')
            else:
                messages.error(request, 'Account not found.')

            return render(request, 'auth/customer_forgot_password.html', {
                'step': 2,
                'email': email,
                'company_id': company,
                'companies': Company.objects.filter(is_active=True, is_deleted=False),
            })

        elif email and company:
            import random

            customer = _find_active_customer(company_id=company, email=email)
            if customer:
                otp_key, attempts_key, cooldown_key = _otp_reset_keys(customer.email)
                if cache.get(cooldown_key):
                    messages.warning(request, 'Please wait a minute before requesting another OTP.')
                    return render(request, 'auth/customer_forgot_password.html', {
                        'step': 2,
                        'email': email,
                        'company_id': company,
                        'companies': Company.objects.filter(is_active=True, is_deleted=False),
                    })
                otp = random.randint(100000, 999999)
                cache.set(otp_key, str(otp), OTP_RESET_TTL)
                cache.delete(attempts_key)
                cache.set(cooldown_key, '1', OTP_COOLDOWN_TTL)
                customer.otp = 0
                customer.save(update_fields=['otp'])

                if settings.DEBUG:
                    messages.info(request, f'DEBUG OTP: {otp}')
                else:
                    try:
                        _send_customer_reset_otp_email(
                            recipient_email=customer.email,
                            customer_name=customer.name,
                            otp=otp,
                        )
                        messages.success(
                            request,
                            'An OTP has been sent to your registered email address.'
                        )
                    except Exception:
                        messages.error(request, 'We could not send the OTP right now. Please try again shortly.')
                        cache.delete_many([otp_key, attempts_key, cooldown_key])
                        return render(request, 'auth/customer_forgot_password.html', {
                            'step': 1,
                            'companies': Company.objects.filter(is_active=True, is_deleted=False),
                        })

                return render(request, 'auth/customer_forgot_password.html', {
                    'step': 2,
                    'email': email,
                    'company_id': company,
                    'companies': Company.objects.filter(is_active=True, is_deleted=False),
                })
            else:
                messages.error(request, 'No account found.')

    return render(request, 'auth/customer_forgot_password.html', {
        'step': 1,
        'companies': Company.objects.filter(is_active=True, is_deleted=False),
    })


# ── Change Password (Customer, logged in) ────────────────

@customer_login_required
def customer_change_password(request):
    customer = request.current_customer
    if request.method == 'POST':
        old_pw = request.POST.get('old_password', '')
        new_pw = request.POST.get('new_password', '')
        confirm = request.POST.get('confirm_password', '')
        if not customer.check_password(old_pw):
            messages.error(request, 'Current password is incorrect.')
        elif new_pw != confirm:
            messages.error(request, 'New passwords do not match.')
        elif len(new_pw) < 6:
            messages.error(request, 'Password must be at least 6 characters.')
        else:
            customer.set_password(new_pw)
            customer.save()
            messages.success(request, 'Password changed.')
            return redirect('accounts:profile')
    return render(request, 'auth/customer_change_password.html', {
        'customer': customer, 'page_title': 'Change Password',
    })


# ── AJAX ─────────────────────────────────────────────────

def get_buildings(request):
    company_id = request.GET.get('company_id')
    data = []
    if company_id:
        buildings = Building.objects.filter(
            company_id=company_id, is_active=True, is_deleted=False
        ).values('id', 'name')
        data = list(buildings)
    return JsonResponse({'buildings': data})


# ── Customer Notifications ────────────────────────────────

def _create_customer_notification(customer, *, notif_type, title, message='', link=''):
    """Safely create a notification for a customer. Never raises."""
    try:
        from apps.core.models import Notification
        Notification.objects.create(
            company=customer.company,
            customer=customer,
            notif_type=notif_type,
            title=title,
            message=message,
            link=link,
        )
    except Exception:
        pass


@customer_login_required
def customer_notifications(request):
    """Customer notification panel — returns last 30 notifications."""
    from apps.core.models import Notification
    customer = request.current_customer
    notifications = Notification.objects.filter(
        customer=customer,
    ).order_by('-created_at')[:30]
    unread_count = Notification.objects.filter(customer=customer, is_read=False).count()
    from django.http import JsonResponse as _JsonResponse
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        data = []
        for n in notifications:
            data.append({
                'id': n.pk,
                'title': n.title,
                'message': n.message,
                'link': n.link or '',
                'is_read': n.is_read,
                'notif_type': n.notif_type,
                'created_at': timezone.localtime(n.created_at).strftime('%d %b %Y, %I:%M %p'),
                'image': n.image.url if n.image else '',
            })
        return _JsonResponse({'notifications': data, 'unread_count': unread_count})
    return render(request, 'auth/customer_notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
        'customer': customer,
        'page_title': 'Notifications',
    })


@customer_login_required
def customer_notifications_mark_read(request):
    """Mark all or a specific notification as read."""
    from apps.core.models import Notification
    from django.http import JsonResponse as _JsonResponse
    from django.views.decorators.http import require_POST as _rp
    customer = request.current_customer
    notif_id = request.POST.get('notif_id', '').strip()
    if notif_id:
        Notification.objects.filter(pk=notif_id, customer=customer).update(is_read=True)
    else:
        Notification.objects.filter(customer=customer, is_read=False).update(is_read=True)
    unread_count = Notification.objects.filter(customer=customer, is_read=False).count()
    return _JsonResponse({'success': True, 'unread_count': unread_count})


@customer_login_required
def customer_notifications_poll(request):
    """Lightweight poll — returns only unread count and latest 5 unread."""
    from apps.core.models import Notification
    from django.http import JsonResponse as _JsonResponse
    customer = request.current_customer
    unread = Notification.objects.filter(
        customer=customer, is_read=False
    ).order_by('-created_at')[:5]
    unread_count = Notification.objects.filter(customer=customer, is_read=False).count()
    data = []
    for n in unread:
        data.append({
            'id': n.pk,
            'title': n.title,
            'message': n.message,
            'link': n.link or '',
            'notif_type': n.notif_type,
            'created_at': n.created_at.strftime('%d %b, %I:%M %p'),
        })
    return _JsonResponse({'unread_count': unread_count, 'notifications': data})
