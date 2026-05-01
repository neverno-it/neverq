from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.conf import settings
from django.core.mail import EmailMessage
from apps.core.models import Company, StaticPage, Notification


def home(request):
    if request.user.is_authenticated:
        try:
            from apps.core.access import get_safe_landing_url
            return redirect(get_safe_landing_url(request.user))
        except Exception:
            return redirect('dashboard:home')

    if request.session.get('customer_id'):
        return redirect('orders:menu')

    # Public entry should open the customer sign-in first.
    return redirect('accounts:customer_login')


@login_required
def select_company(request):
    companies = Company.objects.filter(is_active=True, is_deleted=False)
    return render(request, 'core/select_company.html', {'companies': companies})


# ── Static Pages ──────────────────────────────────────────────

def static_page(request, slug):
    page = get_object_or_404(StaticPage, slug=slug, is_active=True)
    return render(request, 'core/static_page.html', {
        'page': page, 'page_title': page.title,
    })


def about_us(request):
    return static_page(request, 'about-us')


def terms(request):
    return static_page(request, 'terms-and-conditions')


def privacy(request):
    return static_page(request, 'privacy-policy')


def refund(request):
    return static_page(request, 'refund-policy')


def contact_us(request):
    from django.contrib import messages

    recipients = list(getattr(
        settings,
        'CONTACT_FORM_RECIPIENTS',
        ['pritam@neverno.in', 'niladri.roy@neverno.in'],
    ))

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        email = (request.POST.get('email') or '').strip()
        message = (request.POST.get('message') or '').strip()

        if not name or not email or not message:
            messages.error(request, 'Please fill in your name, email, and message.')
            return redirect('core:contact_us')

        subject = f'NeverQ Contact Us — {name}'
        body = (
            f"A new Contact Us message was submitted from NeverQ.\n\n"
            f"Name: {name}\n"
            f"Email: {email}\n\n"
            f"Message:\n{message}\n"
        )

        from_email = (
            getattr(settings, 'DEFAULT_FROM_EMAIL', None)
            or getattr(settings, 'EMAIL_HOST_USER', None)
            or 'no-reply@neverq.local'
        )
        mail = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=recipients,
            reply_to=[email],
        )

        try:
            mail.send(fail_silently=False)
        except Exception:
            messages.error(request, 'Sorry, your message could not be sent right now. Please try again shortly.')
            return redirect('core:contact_us')

        messages.success(request, 'Thank you for your message! Our team will get back to you soon.')
        return redirect('core:contact_us')

    page = StaticPage.objects.filter(slug='contact-us', is_active=True).first()
    return render(request, 'core/contact_us.html', {
        'page': page,
        'page_title': 'Contact Us',
    })


# ── Notifications AJAX ────────────────────────────────────────

def notifications_poll(request):
    """Return unread notification count + latest items for topbar bell."""
    from apps.accounts.models import StaffUser
    user = request.user
    qs = Notification.objects.none()

    if isinstance(user, StaffUser) and user.is_authenticated:
        qs = Notification.objects.filter(staff_user=user, is_read=False)[:10]
    elif request.session.get('customer_id'):
        qs = Notification.objects.filter(
            customer_id=request.session['customer_id'], is_read=False
        )[:10]

    data = {
        'count': qs.count(),
        'items': [
            {'id': n.pk, 'title': n.title, 'message': n.message[:100],
             'link': n.link, 'time': n.created_at.strftime('%d %b %H:%M')}
            for n in qs
        ]
    }
    return JsonResponse(data)


def notification_mark_read(request):
    """Mark notification(s) as read."""
    if request.method == 'POST':
        nid = request.POST.get('id')
        mark_all = request.POST.get('all') == '1'
        from apps.accounts.models import StaffUser
        user = request.user
        qs = Notification.objects.none()
        if isinstance(user, StaffUser) and user.is_authenticated:
            qs = Notification.objects.filter(staff_user=user, is_read=False)
        elif request.session.get('customer_id'):
            qs = Notification.objects.filter(
                customer_id=request.session['customer_id'], is_read=False)
        if mark_all:
            qs.update(is_read=True)
        elif nid:
            qs.filter(pk=nid).update(is_read=True)
        return JsonResponse({'success': True})
    return JsonResponse({'success': False}, status=405)
