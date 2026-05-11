import uuid
from decimal import Decimal
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.core.models import Company
from apps.accounts.models import Customer
from apps.menu.models import Product, Cafe, Counter


class OrderStatusChoices(models.IntegerChoices):
    PENDING   = 1, 'Pending'
    CONFIRMED = 2, 'Confirmed'
    PREPARING = 3, 'Preparing'
    READY     = 4, 'Ready for Pickup'
    DELIVERED = 5, 'Delivered'
    CANCELLED = 6, 'Cancelled'


class PaymentModeChoices(models.TextChoices):
    CASH    = 'cash',    'Cash on Delivery'
    ONLINE  = 'online',  'Online Payment'
    MONTHLY = 'monthly', 'Monthly Billing'
    COMPANY = 'company', 'Bill to Company'
    WALLET  = 'wallet',  'Wallet'
    INTERNAL = 'internal', 'Internal Consumption'


ORDER_TYPE_WEB = 0
ORDER_TYPE_KIOSK = 1
ORDER_TYPE_OFFICE_CAFE = 2
ORDER_TYPE_WALLET_RECHARGE = 3

ORDER_TYPE_CHOICES = [
    (ORDER_TYPE_WEB, 'Home / Office Delivery'),
    (ORDER_TYPE_KIOSK, 'Pickup from Counter'),
    (ORDER_TYPE_OFFICE_CAFE, 'Office Cafeteria'),
    (ORDER_TYPE_WALLET_RECHARGE, 'Wallet Recharge'),
]


class Order(models.Model):
    SOURCE_CUSTOMER = 'customer'
    SOURCE_NEVERNO_EMPLOYEE = 'neverno_employee'
    SOURCE_CHOICES = [
        (SOURCE_CUSTOMER, 'Customer'),
        (SOURCE_NEVERNO_EMPLOYEE, 'Neverno Employee'),
    ]
    NEVERNO_FOOD_MODE_PAID = 'paid'
    NEVERNO_FOOD_MODE_INTERNAL = 'internal'
    NEVERNO_FOOD_MODE_CHOICES = [
        (NEVERNO_FOOD_MODE_PAID, 'Paid'),
        (NEVERNO_FOOD_MODE_INTERNAL, 'Internal Consumption'),
    ]

    company  = models.ForeignKey(Company,  on_delete=models.CASCADE,  related_name='orders')
    # FIX: PROTECT prevents accidental history loss when customer deleted
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT,  related_name='orders')
    customer_name_snapshot = models.CharField(max_length=255, blank=True, default='')
    customer_phone_snapshot = models.CharField(max_length=40, blank=True, default='')
    cafe     = models.ForeignKey(Cafe, on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name='orders')

    coupon_id       = models.IntegerField(default=0)
    coupon_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    offer_discount   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    wallet_used      = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    points_redeemed  = models.IntegerField(default=0)
    subtotal         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_cost   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bill_to_company = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    my_pay          = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    internal_consumption_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    order_number   = models.CharField(max_length=50, unique=True, blank=True)
    payment_mode   = models.CharField(max_length=20, choices=PaymentModeChoices.choices,
                                      default=PaymentModeChoices.ONLINE)
    payment_status = models.CharField(max_length=50, default='pending')
    transaction_id = models.CharField(max_length=255, blank=True)

    order_type   = models.IntegerField(choices=ORDER_TYPE_CHOICES, default=0)
    order_status = models.IntegerField(choices=OrderStatusChoices.choices,
                                       default=OrderStatusChoices.PENDING)
    order_source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default=SOURCE_CUSTOMER, db_index=True)
    neverno_food_mode = models.CharField(max_length=20, choices=NEVERNO_FOOD_MODE_CHOICES, blank=True, default='')
    neverno_employee_id = models.CharField(max_length=64, blank=True, db_index=True)
    neverno_employee_name = models.CharField(max_length=255, blank=True)
    neverno_site_id = models.CharField(max_length=64, blank=True)
    neverno_site_name = models.CharField(max_length=255, blank=True)

    review_given      = models.BooleanField(default=False)
    session_foodtype  = models.CharField(max_length=255, blank=True)
    session_item_date = models.CharField(max_length=255, blank=True)

    created_at     = models.DateTimeField(null=True, blank=True)
    updated_at     = models.DateTimeField(auto_now=True)
    scheduled_date = models.DateTimeField(null=True, blank=True)
    auto_ready_at  = models.DateTimeField(null=True, blank=True)
    is_deleted     = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.order_number} - {self.display_customer_name}"

    def _fallback_order_prefix(self):
        default_prefix = 'KIO' if self.order_type == ORDER_TYPE_KIOSK else (
            'WAL' if self.order_type == ORDER_TYPE_WALLET_RECHARGE else 'WEB'
        )
        company = getattr(self, 'company', None)
        if company is not None:
            if default_prefix == 'KIO':
                raw = getattr(company, 'kiosk_order_prefix', '') or ''
            elif default_prefix == 'WEB':
                raw = getattr(company, 'web_order_prefix', '') or ''
            else:
                raw = ''
            prefix = raw.strip().upper() or default_prefix
        else:
            prefix = default_prefix
        return prefix

    def _generate_fallback_order_number(self):
        prefix = self._fallback_order_prefix()
        today = timezone.localdate().strftime('%y%m%d')
        base = f"{prefix}-{today}-"
        last = (self.__class__.objects.filter(order_number__startswith=base)
                .order_by('-order_number')
                .values_list('order_number', flat=True)
                .first())
        seq = 1
        if last:
            try:
                seq = int(str(last).rsplit('-', 1)[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        candidate = f"{base}{seq:04d}"
        while self.__class__.objects.filter(order_number=candidate).exists():
            seq += 1
            candidate = f"{base}{seq:04d}"
        return candidate

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self._generate_fallback_order_number()
        if not self.created_at:
            self.created_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def status_label(self):
        return OrderStatusChoices(self.order_status).label

    @property
    def display_customer_name(self):
        snapshot_name = (self.customer_name_snapshot or '').strip()
        if snapshot_name:
            return snapshot_name
        if getattr(self, 'customer', None):
            return (self.customer.name or '').strip() or 'Customer'
        return 'Customer'

    @property
    def display_customer_phone(self):
        snapshot_phone = (self.customer_phone_snapshot or '').strip()
        if snapshot_phone:
            return snapshot_phone
        if getattr(self, 'customer', None):
            return (getattr(self.customer, 'phone', '') or '').strip()
        return ''

    @property
    def is_wallet_recharge(self):
        return self.order_type == ORDER_TYPE_WALLET_RECHARGE

    @property
    def is_neverno_employee_order(self):
        return self.order_source == self.SOURCE_NEVERNO_EMPLOYEE

    @property
    def is_internal_consumption(self):
        return (self.internal_consumption_amount or Decimal('0.00')) > Decimal('0.00')

    @property
    def recharge_transaction(self):
        if not self.is_wallet_recharge or not self.order_number:
            return None
        from apps.accounts.models import WalletTransaction
        return WalletTransaction.objects.filter(
            txn_type=WalletTransaction.TYPE_TOPUP,
            order_ref=self.order_number,
        ).order_by('-created_at').first()

    @property
    def status_color(self):
        return {1:'warning',2:'info',3:'primary',4:'success',5:'success',6:'danger'}.get(
            self.order_status, 'secondary')

    @property
    def is_cancellable(self):
        return False

    def get_preparation_lead_minutes(self):
        """Legacy helper — returns the maximum prep lead across all items (no offering gate)."""
        minutes = []
        for item in self.items.select_related('product', 'product__category').all():
            if item.product_id and item.product:
                try:
                    cat_minutes = int(getattr(getattr(item.product, 'category', None), 'preparation_time_minutes', 0) or 0)
                    prod_minutes = int(item.product.preparation_time_minutes or 0)
                    minutes.append(max(0, cat_minutes or prod_minutes))
                except (TypeError, ValueError):
                    continue
        return max(minutes, default=0)

    def calculate_auto_ready_at(self, start_from=None):
        """
        Compute when this order should be auto-marked Ready.

        New logic (prep_start_time gate):
          For each item:
            offering = item.product.offering
            if offering.prep_start_time is set:
              # Build aware prep_start datetime on the same local date as base_dt
              countdown_start = max(base_dt, prep_start_aware)
            else:
              countdown_start = base_dt   # backward-compatible

            item_ready_at = countdown_start + category_preparation_time_minutes

          order auto_ready_at = max(all item_ready_at values)

        Where base_dt = max(start_from, scheduled_date).
        """
        import datetime as _dt
        start_from = start_from or timezone.now()

        # Base datetime: the moment the order was confirmed (or its scheduled_date if later)
        base_dt = start_from
        if self.scheduled_date and self.scheduled_date > start_from:
            base_dt = self.scheduled_date

        item_ready_times = []
        for item in self.items.select_related(
            'product', 'product__category', 'product__offering'
        ).all():
            if not (item.product_id and item.product):
                continue
            try:
                cat = getattr(item.product, 'category', None)
                cat_minutes = int(getattr(cat, 'preparation_time_minutes', 0) or 0)
                prod_minutes = int(item.product.preparation_time_minutes or 0)
                lead_minutes = max(0, cat_minutes or prod_minutes)
            except (TypeError, ValueError):
                continue

            if lead_minutes <= 0:
                continue

            # Determine countdown start: honour offering prep gate if configured
            offering = getattr(item.product, 'offering', None)
            if offering is not None and offering.prep_start_time is not None:
                # Convert base_dt to local date, combine with prep_start_time to get
                # a timezone-aware datetime in the project's local timezone.
                local_base = timezone.localtime(base_dt)
                ref_date = local_base.date()
                prep_naive = _dt.datetime.combine(ref_date, offering.prep_start_time)
                prep_start_aware = timezone.make_aware(prep_naive)
                countdown_start = max(base_dt, prep_start_aware)
            else:
                # No gate configured — keep existing behaviour
                countdown_start = base_dt

            item_ready_times.append(countdown_start + timedelta(minutes=lead_minutes))

        if not item_ready_times:
            return None
        return max(item_ready_times)

    @property
    def remaining_items(self):
        return self.items.filter(picked_up_at__isnull=True, is_deleted=False)

    @property
    def remaining_items_count(self):
        return self.remaining_items.count()

    @property
    def picked_items_count(self):
        return self.items.filter(picked_up_at__isnull=False, is_deleted=False).count()

    @property
    def all_items_picked_up(self):
        return self.items.filter(is_deleted=False, picked_up_at__isnull=True).count() == 0


class OrderItem(models.Model):
    company        = models.ForeignKey(Company, on_delete=models.CASCADE)
    order          = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product        = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    counter        = models.ForeignKey(Counter, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_items')
    row_id         = models.CharField(max_length=255, blank=True)
    price          = models.DecimalField(max_digits=10, decimal_places=2)  # effective unit price after offer
    unit_price     = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # original catalog price
    item_offer_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # saving on this line
    qty            = models.IntegerField(default=1)
    image_snapshot = models.CharField(max_length=255, blank=True)
    pickup_code    = models.CharField(max_length=24, blank=True, db_index=True)
    pickup_token   = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)
    picked_up_at   = models.DateTimeField(null=True, blank=True)
    is_deleted     = models.BooleanField(default=False)
    created_at     = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.product.name if self.product else 'Item'} × {self.qty}"

    def save(self, *args, **kwargs):
        if not self.pickup_code:
            self.pickup_code = f"PK{uuid.uuid4().hex[:8].upper()}"
        if not self.created_at:
            self.created_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        return self.price * self.qty

    @property
    def is_picked_up(self):
        return bool(self.picked_up_at)

    @property
    def pickup_payload(self):
        return self.pickup_code

    @property
    def pickup_qr_data_uri(self):
        try:
            import base64
            from io import BytesIO
            import qrcode
            qr = qrcode.QRCode(box_size=4, border=1)
            qr.add_data(self.pickup_payload)
            qr.make(fit=True)
            img = qr.make_image(fill_color='black', back_color='white')
            buf = BytesIO()
            img.save(buf, format='PNG')
            return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
        except Exception:
            return ''


class OrderStatus(models.Model):
    order      = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    status     = models.IntegerField(choices=OrderStatusChoices.choices)
    details    = models.TextField(blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Order #{self.order.order_number} → {self.get_status_display()}"

class CompanySettlement(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='settlements'
    )
    payment_date = models.DateField()
    amount_received = models.DecimalField(max_digits=10, decimal_places=2)
    reference_no = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='company_settlement_entries'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-payment_date', '-created_at']
        verbose_name = 'Company Settlement'
        verbose_name_plural = 'Company Settlements'

    def __str__(self):
        return f"{self.company.name} - ₹{self.amount_received} on {self.payment_date}"


class CounterTicket(models.Model):
    """
    Groups OrderItems belonging to the same counter for multi-counter fulfilment.
    One ticket is created per (order, counter) pair on order confirmation.
    """
    STATUS_PENDING   = 'pending'
    STATUS_PREPARING = 'preparing'
    STATUS_READY     = 'ready'
    STATUS_COLLECTED = 'collected'
    STATUS_CHOICES   = [
        (STATUS_PENDING,   'Pending'),
        (STATUS_PREPARING, 'Preparing'),
        (STATUS_READY,     'Ready'),
        (STATUS_COLLECTED, 'Collected'),
    ]

    order    = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='counter_tickets')
    counter  = models.ForeignKey(
        'menu.Counter', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='tickets'
    )
    company  = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='counter_tickets')
    ticket_number = models.CharField(max_length=30, blank=True)
    scan_code = models.CharField(max_length=40, blank=True, db_index=True)
    status   = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    collected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        cname = self.counter.name if self.counter else 'Unassigned'
        return f'Ticket {self.ticket_number} — {cname}'

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            import uuid
            self.ticket_number = f'TKT-{uuid.uuid4().hex[:6].upper()}'
        if not self.scan_code:
            import uuid
            self.scan_code = f'CT{uuid.uuid4().hex[:10].upper()}'
        if not self.created_at:
            from django.utils import timezone
            self.created_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def items(self):
        """
        Returns items for this counter ticket.

        WARNING — N+1 risk: every access hits the DB.
        When rendering multiple tickets in a view, prefetch with:
            tickets = CounterTicket.objects.filter(...).prefetch_related(
                Prefetch('order__items', queryset=OrderItem.objects.filter(is_deleted=False))
            )
        Then use ticket.items_cached (see below) instead of ticket.items.
        """
        return self.order.items.filter(counter=self.counter, is_deleted=False)

    def get_items_cached(self, prefetched_items=None):
        """
        Use this in list views where you have prefetched order__items.
        Pass in the prefetched queryset result to avoid repeated DB hits.
        """
        if prefetched_items is not None:
            return [i for i in prefetched_items if i.counter_id == self.counter_id and not i.is_deleted]
        return list(self.items)

    @property
    def remaining_items(self):
        return self.items.filter(picked_up_at__isnull=True)

    @property
    def total_amount(self):
        total = Decimal('0.00')
        for item in self.items:
            total += (item.price or Decimal('0.00')) * (item.qty or 0)
        return total

    @property
    def is_collected(self):
        return self.status == self.STATUS_COLLECTED or self.remaining_items.count() == 0

    @property
    def pickup_payload(self):
        return self.scan_code or self.ticket_number

    @property
    def pickup_qr_data_uri(self):
        try:
            import base64
            from io import BytesIO
            import qrcode
            qr = qrcode.QRCode(box_size=4, border=1)
            qr.add_data(self.pickup_payload)
            qr.make(fit=True)
            img = qr.make_image(fill_color='black', back_color='white')
            buf = BytesIO()
            img.save(buf, format='PNG')
            return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
        except Exception:
            return ''

    def kot_data(self):
        """Return dict suitable for printKOT()."""
        co = self.company
        return {
            'order_number': self.order.order_number,
            'ticket_number': self.ticket_number,
            'scan_code': self.scan_code,
            'counter_name': self.counter.name if self.counter else 'Counter',
            'cafe_name': self.counter.cafe.name if (self.counter and self.counter.cafe) else '',
            'company_name': co.name if co else '',
            'company_phone': co.phone if co else '',
            'company_gst': co.company_gst if co else '',
            'company_fssai': co.fssai_number if co else '',
            'printer_label': self.counter.effective_printer_label if self.counter else '',
            'printer_route_key': self.counter.printer_route_key if self.counter else 'default',
            'customer_name': self.order.display_customer_name,
            'customer_phone': self.order.display_customer_phone,
            'payment_mode': self.order.get_payment_mode_display(),
            'items': [
                {
                    'name': (i.product.name if i.product else 'Item'),
                    'qty': i.qty,
                    'price': str(i.price),
                    'lt': str(i.line_total),
                }
                for i in self.items
            ],
            'total': str(sum(i.price * i.qty for i in self.items)),
            'created_at': self.created_at.strftime('%d-%m-%Y %H:%M') if self.created_at else '',
        }
