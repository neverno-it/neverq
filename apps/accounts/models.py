import os
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.auth.hashers import make_password, check_password as django_check_password
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from apps.core.models import Company, Building


class StaffUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError('Email is required')
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        extra.setdefault('role', StaffUser.ROLE_SUPERADMIN)
        return self.create_user(email, password, **extra)


class StaffUser(AbstractBaseUser, PermissionsMixin):
    ROLE_SUPERADMIN = 'superadmin'
    ROLE_ADMIN      = 'admin'
    ROLE_CAFEMAN    = 'cafeman'
    ROLE_POS        = 'pos'
    ROLE_REPORTS    = 'reports'

    ROLE_CHOICES = [
        (ROLE_SUPERADMIN, 'Super Admin'),
        (ROLE_ADMIN,      'Operation Manager'),
        (ROLE_CAFEMAN,    'Chef / Cafe Manager'),
        (ROLE_POS,        'Cashier / POS'),
        (ROLE_REPORTS,    'Reports Viewer'),
    ]

    email       = models.EmailField(unique=True)
    name        = models.CharField(max_length=255)
    phone       = models.CharField(max_length=20, blank=True)
    role        = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ADMIN)
    company     = models.ForeignKey(Company, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='staff')
    site_access = models.ManyToManyField(
        Company,
        blank=True,
        related_name='site_staff',
        help_text='Sites this staff member can control. Granular permissions decide what they can do inside those sites.',
    )
    avatar      = models.ImageField(upload_to='staff/avatars/', blank=True, null=True)
    is_staff    = models.BooleanField(default=False)
    is_active   = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['name']
    objects = StaffUserManager()

    class Meta:
        verbose_name = 'Staff User'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"

    @property
    def is_superadmin(self):
        return self.role == self.ROLE_SUPERADMIN

    @property
    def is_company_admin(self):
        return self.role in (self.ROLE_ADMIN, self.ROLE_SUPERADMIN)


class Customer(models.Model):
    """End-user who places food orders."""
    company  = models.ForeignKey(Company,  on_delete=models.CASCADE, related_name='customers')
    building = models.ForeignKey(Building, on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name='customers')
    name              = models.CharField(max_length=250)
    phone             = models.CharField(max_length=30)
    email             = models.EmailField()
    password_hash     = models.TextField()
    avatar            = models.CharField(max_length=255, blank=True)
    verification_key  = models.CharField(max_length=250, blank=True)
    is_email_verified = models.BooleanField(default=False)
    otp               = models.IntegerField(default=0)
    token             = models.CharField(max_length=100, blank=True)
    token_expires     = models.BooleanField(default=False)
    address           = models.TextField(blank=True)
    date_of_birth     = models.DateField(null=True, blank=True)
    cod_payment       = models.BooleanField(default=False)
    monthly_payment   = models.BooleanField(default=False)
    subsidy_eligible  = models.BooleanField(
        default=False,
        help_text='Legacy flag. Use meal_benefit for new logic.'
    )
    MEAL_BENEFIT_NONE       = 'none'
    MEAL_BENEFIT_SUBSIDY    = 'subsidy'
    MEAL_BENEFIT_COMPANY_PAY = 'company_pay'
    MEAL_BENEFIT_CHOICES = [
        (MEAL_BENEFIT_NONE,        'No benefit'),
        (MEAL_BENEFIT_SUBSIDY,     'Subsidized meals per day'),
        (MEAL_BENEFIT_COMPANY_PAY, 'Company-paid meals per day'),
    ]
    meal_benefit      = models.CharField(
        max_length=20,
        choices=MEAL_BENEFIT_CHOICES,
        default=MEAL_BENEFIT_NONE,
        help_text='Per-customer meal benefit mode for the company-defined daily limit.'
    )
    subsidy_amount_override = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Optional per-customer subsidy override. Leave blank to use company subsidy amount.'
    )
    is_active          = models.BooleanField(default=True)
    is_approved        = models.BooleanField(
        default=True,
        help_text='Set False to require admin approval before customer can order. '
                  'New registrations can be auto-set to False via company settings.'
    )
    is_deleted        = models.BooleanField(default=False)
    created_at        = models.DateTimeField(null=True, blank=True)
    # ── Wallet & Royalty Points ────────────────────────
    wallet_balance    = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Topup balance in ₹ (separate from royalty points)'
    )
    royalty_points    = models.IntegerField(
        default=0,
        help_text='Accumulated royalty points. 1 point = 1 rupee when redeemed via wallet.'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Customer'

    def __str__(self):
        return f"{self.name} — {self.email}"

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def save(self, *args, **kwargs):
        if not self.created_at:
            self.created_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def has_legacy_md5_password(self):
        value = (self.password_hash or '').strip()
        return len(value) == 32 and all(ch in '0123456789abcdefABCDEF' for ch in value)

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password, upgrade=True):
        """
        Checks raw_password against the stored hash.

        Supports two formats:
          1. Django PBKDF2 hashes (current standard)
          2. Legacy plain MD5 hashes (32-char hex) from the old system

        SECURITY NOTE: The MD5 path is a migration bridge only. Every successful
        legacy login automatically upgrades the hash to PBKDF2 (upgrade=True).
        To find accounts still on MD5, query:
            Customer.objects.filter(password_hash__regex=r'^[0-9a-f]{32}$')
        Once all legacy passwords are upgraded, remove the MD5 branch entirely.
        """
        import hashlib
        stored = (self.password_hash or '').strip()
        if not stored:
            return False
        try:
            if django_check_password(raw_password, stored):
                return True
        except (ValueError, TypeError):
            pass
        legacy_hash = hashlib.md5(raw_password.encode()).hexdigest()
        if self.has_legacy_md5_password and stored.lower() == legacy_hash.lower():
            if upgrade:
                self.password_hash = make_password(raw_password)
                self.save(update_fields=['password_hash'])
            return True
        return False


    def last_order_at(self):
        return self.orders.filter(is_deleted=False).exclude(created_at__isnull=True).order_by('-created_at').values_list('created_at', flat=True).first()

    def auto_inactive_reference_at(self):
        return self.last_order_at() or self.created_at

    def deactivate_if_stale(self, *, cutoff=None, save=True):
        from datetime import timedelta
        cutoff = cutoff or (timezone.now() - timedelta(days=60))
        ref_at = self.auto_inactive_reference_at()
        should_deactivate = bool(ref_at and ref_at < cutoff)
        if should_deactivate and self.is_active:
            self.is_active = False
            if save and self.pk:
                self.save(update_fields=['is_active'])
        return should_deactivate

    # ── FIX: All subsidy methods were previously defined OUTSIDE the class ───

    @property
    def company_subsidy_amount(self):
        try:
            return max(Decimal('0.00'), Decimal(str(self.company.company_meal_amount or 0)))
        except (InvalidOperation, TypeError, ValueError, AttributeError):
            return Decimal('0.00')

    @property
    def effective_subsidy_amount(self):
        """Return the subsidy amount that applies for this customer."""
        if self.meal_benefit != self.MEAL_BENEFIT_SUBSIDY:
            return Decimal('0.00')
        if self.subsidy_amount_override is not None:
            try:
                return max(Decimal('0.00'), Decimal(str(self.subsidy_amount_override)))
            except Exception:
                return Decimal('0.00')
        return self.company_subsidy_amount

    @property
    def subsidy_source_label(self):
        if self.meal_benefit == self.MEAL_BENEFIT_COMPANY_PAY:
            return f'Company-paid meals {self.company_pay_meals_per_day}/day'
        if self.meal_benefit != self.MEAL_BENEFIT_SUBSIDY:
            return 'Off'
        if self.subsidy_amount_override is not None:
            return f'Custom ₹{self.effective_subsidy_amount:.2f}, {self.subsidy_meals_per_day}/day'
        return f'Company ₹{self.effective_subsidy_amount:.2f}, {self.subsidy_meals_per_day}/day'

    @property
    def company_pay_meals_per_day(self):
        try:
            return max(1, int(getattr(self.company, 'company_pay_meals_per_day', 1) or 1))
        except (TypeError, ValueError, AttributeError):
            return 1

    @property
    def subsidy_meals_per_day(self):
        try:
            return max(1, int(getattr(self.company, 'subsidy_meals_per_day', 1) or 1))
        except (TypeError, ValueError, AttributeError):
            return 1

    def benefit_limit_for_date(self, target_date=None):
        if self.meal_benefit == self.MEAL_BENEFIT_COMPANY_PAY:
            if self.company.bill_company != 2:
                return 0
            return self.company_pay_meals_per_day
        if self.meal_benefit == self.MEAL_BENEFIT_SUBSIDY:
            if self.company.bill_company != 2:
                return 0
            return self.subsidy_meals_per_day
        return 0

    def benefit_used_count_on(self, target_date=None):
        """Return how many company-covered orders this customer used on target_date."""
        from apps.orders.models import Order, OrderStatusChoices
        target_date = target_date or timezone.localdate()
        return Order.objects.filter(
            customer=self,
            is_deleted=False,
            created_at__date=target_date,
            bill_to_company__gt=0,
        ).exclude(order_status=OrderStatusChoices.CANCELLED).count()

    def benefit_remaining_on(self, target_date=None):
        limit = self.benefit_limit_for_date(target_date)
        if limit <= 0:
            return 0
        return max(0, limit - self.benefit_used_count_on(target_date))

    def benefit_used_on(self, target_date=None):
        """Return True if the customer has exhausted their daily benefit."""
        return self.benefit_remaining_on(target_date) <= 0

    def company_cover_for_amount(self, gross_total, target_date=None):
        """
        How much the company will cover for this order.
        - company_pay  → full amount while company-paid meals remain today
        - subsidy      → up to effective_subsidy_amount while subsidy remains today
        - none / bill_company != 2 → 0
        """
        try:
            gross = max(Decimal('0.00'), Decimal(str(gross_total or 0)))
        except (InvalidOperation, TypeError, ValueError):
            gross = Decimal('0.00')
        if gross <= 0:
            return Decimal('0.00')
        if self.meal_benefit == self.MEAL_BENEFIT_COMPANY_PAY:
            if self.company.bill_company != 2:
                return Decimal('0.00')
            if self.benefit_remaining_on(target_date) <= 0:
                return Decimal('0.00')
            return gross
        if self.meal_benefit == self.MEAL_BENEFIT_SUBSIDY:
            if self.company.bill_company != 2:
                return Decimal('0.00')
            if self.benefit_remaining_on(target_date) <= 0:
                return Decimal('0.00')
            return min(gross, self.effective_subsidy_amount)
        return Decimal('0.00')

    # ─────────────────────────────────────────────────────────────────────────


class WebCookie(models.Model):
    """Cart session tracker."""
    DELIVERY_CHOICES = [
        ('1', 'Home Delivery'),
        ('2', 'Office Cafeteria'),
        ('3', 'Pickup'),
    ]
    cookie_id     = models.CharField(max_length=255, db_index=True)
    customer      = models.ForeignKey(Customer, on_delete=models.SET_NULL,
                                      null=True, blank=True)
    delivery_type = models.CharField(max_length=50, blank=True)
    delivery_date = models.CharField(max_length=100, blank=True)
    created_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Cookie {self.cookie_id[:12]}…"


class StaffAccess(models.Model):
    """Per-user dashboard access config. Superadmin sets this for each staff user."""
    user = models.OneToOneField(StaffUser, on_delete=models.CASCADE, related_name='access_config')
    landing_page = models.CharField(
        max_length=60, blank=True, default='',
        help_text='URL name for landing page e.g. dashboard:home'
    )
    visible_keys = models.JSONField(
        default=list, blank=True,
        help_text='List of menu keys this user can see/access'
    )

    class Meta:
        verbose_name = 'Staff Access Config'
        verbose_name_plural = 'Staff Access Configs'

    def __str__(self):
        return f'{self.user.name} — {len(self.visible_keys or [])} items'


class WalletTransaction(models.Model):
    """Tracks every debit/credit on a customer's wallet balance and royalty points."""
    TYPE_TOPUP          = 'topup'
    TYPE_ORDER_DEBIT    = 'order_debit'
    TYPE_ROYALTY_EARNED = 'royalty_earned'
    TYPE_ROYALTY_REDEEM = 'royalty_redeem'
    TYPE_REFUND         = 'refund'
    TYPE_ADJUSTMENT     = 'adjustment'
    PAYMENT_CASH        = 'cash'
    PAYMENT_UPI         = 'upi'
    PAYMENT_CARD        = 'card'
    PAYMENT_ONLINE      = 'online'
    PAYMENT_CHOICES = [
        (PAYMENT_CASH,   'Cash'),
        (PAYMENT_UPI,    'UPI'),
        (PAYMENT_CARD,   'Card'),
        (PAYMENT_ONLINE, 'Online'),
    ]
    TYPE_CHOICES = [
        (TYPE_TOPUP,          'Wallet Top-up'),
        (TYPE_ORDER_DEBIT,    'Order Payment'),
        (TYPE_ROYALTY_EARNED, 'Royalty Points Earned'),
        (TYPE_ROYALTY_REDEEM, 'Royalty Points Redeemed'),
        (TYPE_REFUND,         'Refund'),
        (TYPE_ADJUSTMENT,     'Manual Adjustment'),
    ]

    customer       = models.ForeignKey(Customer, on_delete=models.CASCADE,
                                       related_name='wallet_transactions')
    txn_type       = models.CharField(max_length=30, choices=TYPE_CHOICES)
    # wallet_delta: +ve = credit, -ve = debit (in ₹)
    wallet_delta   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # points_delta: +ve = earn, -ve = redeem
    points_delta   = models.IntegerField(default=0)
    balance_after  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    points_after   = models.IntegerField(default=0)
    order_ref      = models.CharField(max_length=50, blank=True, help_text='Order number if related to an order')
    payment_mode   = models.CharField(max_length=20, choices=PAYMENT_CHOICES, blank=True, default='')
    card_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gross_amount   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    note           = models.CharField(max_length=255, blank=True)
    created_by     = models.CharField(max_length=100, blank=True, help_text='Staff email or "system"')
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Wallet Transaction'

    def __str__(self):
        return f"{self.customer.name} | {self.get_txn_type_display()} | ₹{self.wallet_delta:+.2f} pts:{self.points_delta:+d}"


# ─── GRANULAR PERMISSION SYSTEM ──────────────────────────────────────────────

class StaffModulePermission(models.Model):
    """
    Granular per-staff per-module permission.
    One row per staff member per module.
    No row = module completely hidden from this staff member.
    """
    LEVEL_VIEW      = 'view'
    LEVEL_PART_EDIT = 'part_edit'
    LEVEL_FULL_EDIT = 'full_edit'
    LEVEL_CHOICES = [
        (LEVEL_VIEW,      'View Only'),
        (LEVEL_PART_EDIT, 'Part Edit'),
        (LEVEL_FULL_EDIT, 'Full Edit (Pending Approval)'),
    ]
    staff_user      = models.ForeignKey(
        'StaffUser', on_delete=models.CASCADE,
        related_name='module_permissions'
    )
    module_key      = models.CharField(max_length=80)
    level           = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    allowed_actions = models.JSONField(
        default=list, blank=True,
        help_text='Specific action keys (only used when level=part_edit)'
    )
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together     = [('staff_user', 'module_key')]
        verbose_name        = 'Staff Module Permission'
        verbose_name_plural = 'Staff Module Permissions'
        ordering            = ['staff_user__name', 'module_key']

    def __str__(self):
        return f'{self.staff_user.name} | {self.module_key} | {self.level}'


class PendingChange(models.Model):
    """
    A change submitted by a full_edit staff member.
    Goes live only after superadmin approval.
    """
    STATUS_PENDING  = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING,  'Pending Review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]
    staff_user   = models.ForeignKey(
        'StaffUser', on_delete=models.CASCADE,
        related_name='pending_changes'
    )
    module_key   = models.CharField(max_length=80)
    object_id    = models.PositiveIntegerField()
    object_label = models.CharField(max_length=255)
    field_diffs  = models.JSONField(
        help_text='{"field_key": {"label": "...", "before": ..., "after": ...}}'
    )
    status       = models.CharField(
        max_length=20, choices=STATUS_CHOICES,
        default=STATUS_PENDING, db_index=True
    )
    reviewed_by  = models.ForeignKey(
        'StaffUser', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_changes'
    )
    review_note  = models.CharField(max_length=500, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    reviewed_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Pending Change'
        verbose_name_plural = 'Pending Changes'

    def __str__(self):
        return f'{self.staff_user.name} | {self.module_key} | {self.object_label} | {self.status}'
