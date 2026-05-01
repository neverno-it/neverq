from django.db import models
from decimal import Decimal

from django.utils.text import slugify
from django.utils import timezone

ORDER_DAY_CHOICES = [
    ('Monday', 'Monday'),
    ('Tuesday', 'Tuesday'),
    ('Wednesday', 'Wednesday'),
    ('Thursday', 'Thursday'),
    ('Friday', 'Friday'),
    ('Saturday', 'Saturday'),
    ('Sunday', 'Sunday'),
]


def default_order_open_days():
    return [day for day, _ in ORDER_DAY_CHOICES]


class State(models.Model):
    name = models.CharField(max_length=100)
    class Meta:
        ordering = ['name']
        verbose_name = 'State'
    def __str__(self):
        return self.name


class City(models.Model):
    state = models.ForeignKey('State', on_delete=models.CASCADE, related_name='cities', null=True, blank=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Cities'
    def __str__(self):
        if self.state_id:
            return f"{self.name}, {self.state.name}"
        return self.name


class Location(models.Model):
    name       = models.CharField(max_length=255)
    is_active  = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    class Meta:
        ordering = ['name']
    def __str__(self):
        return self.name


class Company(models.Model):
    BILL_CHOICES = [(1,'Employee Pays'),(2,'Bill to Company')]

    name            = models.CharField(max_length=255)
    company_address = models.TextField(blank=True)
    company_gst     = models.CharField(max_length=50, blank=True)
    fssai_number    = models.CharField(max_length=50, blank=True)
    phone           = models.CharField(max_length=30, blank=True)

    order_from_time = models.TimeField(null=True, blank=True)
    order_to_time   = models.TimeField(null=True, blank=True)
    order_open_days = models.JSONField(default=default_order_open_days, blank=True)

    address         = models.CharField(max_length=100, blank=True)
    bill_company    = models.IntegerField(choices=BILL_CHOICES, default=2)

    company_meal_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        null=True, blank=True,
        help_text='Subsidy amount company covers per meal'
    )
    company_pay_meals_per_day = models.PositiveSmallIntegerField(
        default=1,
        help_text='How many fully company-paid meals each eligible customer can use per day.'
    )
    subsidy_meals_per_day = models.PositiveSmallIntegerField(
        default=1,
        help_text='How many subsidized meals each eligible customer can use per day.'
    )
    cod_payment         = models.BooleanField(default=False)
    online_payment      = models.BooleanField(default=True,  help_text='Allow online/UPI payment in web & kiosk')
    monthly_payment     = models.BooleanField(default=False, help_text='Allow monthly billing in web orders')
    pos_cash_enabled    = models.BooleanField(default=True, help_text='Allow cash payments in POS terminal')
    pos_upi_enabled     = models.BooleanField(default=True, help_text='Allow UPI payments in POS terminal')
    pos_card_enabled    = models.BooleanField(default=True, help_text='Allow card payments in POS terminal')
    pos_card_fee_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('3.50'),
        help_text='Extra percentage charged on POS card payments and wallet recharge by card.'
    )

    # Kiosk / portal theme
    logo                = models.ImageField(upload_to='company/logos/', blank=True, null=True)
    kiosk_theme_color   = models.CharField(max_length=20, default='#1e3a5f', blank=True,
                                           help_text='Primary hex colour for kiosk header')
    kiosk_logo          = models.ImageField(upload_to='company/kiosk_logos/', blank=True, null=True,
                                            help_text='Override logo shown on the kiosk screen only')
    kiosk_welcome_text  = models.CharField(max_length=160, blank=True, default='Touch to order')

    store_status        = models.BooleanField(default=True)
    store_order_enabled = models.BooleanField(default=False)
    video_link          = models.TextField(blank=True)
    free_meal_products   = models.ManyToManyField(
        'menu.Product',
        blank=True,
        related_name='free_meal_companies',
        help_text='Only these mapped products are eligible for free meal or subsidy cover for this company.'
    )

    require_customer_approval = models.BooleanField(
        default=False,
        help_text='New customer registrations need admin approval before ordering.'
    )
    royalty_enabled          = models.BooleanField(default=False)
    royalty_points_per_rupee = models.DecimalField(max_digits=5, decimal_places=2, default=1,
        help_text='Points earned per ₹1 spent on a normal order (standard earn rate)')
    royalty_min_redeem       = models.IntegerField(default=100)
    royalty_max_redeem_pct   = models.IntegerField(default=50,
        help_text='Max % of order value payable by royalty points')

    # ── Leaderboard / "top customer" bonus rewards ────────────────
    REWARD_BY_AMOUNT = 'amount'
    REWARD_BY_COUNT  = 'count'
    REWARD_MODE_CHOICES = [
        (REWARD_BY_AMOUNT, 'Highest spend amount'),
        (REWARD_BY_COUNT,  'Most number of orders'),
    ]
    PERIOD_DAILY   = 'daily'
    PERIOD_WEEKLY  = 'weekly'
    PERIOD_MONTHLY = 'monthly'
    REWARD_PERIOD_CHOICES = [
        (PERIOD_DAILY,   'Daily'),
        (PERIOD_WEEKLY,  'Weekly'),
        (PERIOD_MONTHLY, 'Monthly'),
    ]
    royalty_reward_mode    = models.CharField(max_length=10, choices=REWARD_MODE_CHOICES,
                                              default=REWARD_BY_AMOUNT)
    royalty_reward_period  = models.CharField(max_length=10, choices=REWARD_PERIOD_CHOICES,
                                              default=PERIOD_MONTHLY)
    royalty_rank1_points   = models.IntegerField(default=500, help_text='Bonus pts for #1 customer')
    royalty_rank2_points   = models.IntegerField(default=250, help_text='Bonus pts for #2 customer')
    royalty_rank3_points   = models.IntegerField(default=100, help_text='Bonus pts for #3 customer')

    # ── Order number prefixes ───────────────────────────────────────────────
    web_order_prefix = models.CharField(
        max_length=10, blank=True, default='',
        help_text='Prefix for web orders (e.g. "WEB"). Leave blank to use default "WEB".'
    )
    kiosk_order_prefix = models.CharField(
        max_length=10, blank=True, default='',
        help_text='Prefix for kiosk orders (e.g. "KIO"). Leave blank to use default "KIO".'
    )

    # ── Fulfillment mode ───────────────────────────────────────────────────────
    FULFILLMENT_PICKUP           = 'pickup'
    FULFILLMENT_PACKET_DELIVERY  = 'packet_delivery'
    FULFILLMENT_MODE_CHOICES = [
        (FULFILLMENT_PICKUP,          'Pickup (QR-based collection at counter)'),
        (FULFILLMENT_PACKET_DELIVERY, 'Packet Delivery (our staff delivers to company)'),
    ]
    fulfillment_mode = models.CharField(
        max_length=30,
        choices=FULFILLMENT_MODE_CHOICES,
        default=FULFILLMENT_PICKUP,
        help_text=(
            'Pickup: customers collect at counter using QR. '
            'Packet Delivery: our staff delivers packed food to company — no QR used.'
        ),
    )

    is_active  = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = 'Companies'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def is_packet_delivery(self):
        """True when this company uses packet-delivery mode (no QR pickup)."""
        return self.fulfillment_mode == self.FULFILLMENT_PACKET_DELIVERY

    @property
    def enabled_order_days(self):
        valid_days = [day for day, _ in ORDER_DAY_CHOICES]
        raw_days = self.order_open_days or []
        if not isinstance(raw_days, list):
            raw_days = []
        return [day for day in raw_days if day in valid_days]

    @property
    def has_order_schedule(self):
        return bool(self.order_from_time and self.order_to_time and self.order_from_time != self.order_to_time)

    @property
    def is_open_today(self):
        today_name = timezone.localtime().strftime('%A')
        return today_name in self.enabled_order_days

    def _is_within_order_window(self):
        now = timezone.localtime().time()
        if not self.has_order_schedule:
            return True
        if self.order_from_time < self.order_to_time:
            return self.order_from_time <= now <= self.order_to_time
        # overnight window
        return now >= self.order_from_time or now <= self.order_to_time

    @property
    def is_store_open(self):
        if not self.is_active or self.is_deleted:
            return False
        if not self.store_status:
            return False
        if not self.is_open_today:
            return False
        if self.has_order_schedule and not self._is_within_order_window():
            return False
        return True

    @property
    def order_days_label(self):
        days = self.enabled_order_days
        all_days = [day for day, _ in ORDER_DAY_CHOICES]
        if days == all_days:
            return 'All Days'
        if not days:
            return 'No Days Selected'
        return ', '.join(days)

    @property
    def order_window_label(self):
        if not self.has_order_schedule:
            return 'Always Open'
        from datetime import datetime
        start = datetime.combine(timezone.localdate(), self.order_from_time).strftime('%I:%M %p').lstrip('0')
        end   = datetime.combine(timezone.localdate(), self.order_to_time).strftime('%I:%M %p').lstrip('0')
        return f'{start} – {end}'

    @property
    def ordering_status_message(self):
        if not self.is_active or self.is_deleted:
            return 'Ordering is not available for this store right now.'
        if not self.store_status:
            return 'This store has been manually closed by admin.'
        if not self.is_open_today:
            return f'Ordering is closed today. Open days: {self.order_days_label}.'
        if self.has_order_schedule and not self._is_within_order_window():
            from datetime import datetime
            start = datetime.combine(timezone.localdate(), self.order_from_time).strftime('%I:%M %p').lstrip('0')
            end   = datetime.combine(timezone.localdate(), self.order_to_time).strftime('%I:%M %p').lstrip('0')
            return f'Ordering is closed right now. Orders are accepted between {start} and {end}.'
        return 'Ordering is open. You can place your order now!'


class Building(models.Model):
    company    = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='buildings')
    state      = models.ForeignKey(State, on_delete=models.SET_NULL, null=True, blank=True, related_name='buildings')
    city       = models.ForeignKey('City', on_delete=models.SET_NULL, null=True, blank=True, related_name='buildings')
    location   = models.ForeignKey(Location, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='buildings')
    name       = models.CharField(max_length=255)
    is_active  = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} – {self.company.name}"



class RoyaltyAward(models.Model):
    """Tracks bonus leaderboard awards — prevents double-awarding the same period+rank."""
    company      = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='royalty_awards')
    customer     = models.ForeignKey('accounts.Customer', on_delete=models.CASCADE,
                                     related_name='royalty_awards')
    period_key   = models.CharField(max_length=20,
        help_text='e.g. 2025-01 (monthly), 2025-W03 (weekly), 2025-01-15 (daily)')
    rank         = models.IntegerField(help_text='1=first, 2=second, 3=third')
    points       = models.IntegerField(default=0)
    awarded_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('company', 'period_key', 'rank')]
        ordering = ['-awarded_at']

    def __str__(self):
        return f'{self.company.name} | {self.period_key} | Rank {self.rank} → {self.customer.name} ({self.points} pts)'


class Coupon(models.Model):
    DISCOUNT_TYPE_FLAT    = 'flat'
    DISCOUNT_TYPE_PERCENT = 'percent'
    DISCOUNT_TYPE_CHOICES = [
        (DISCOUNT_TYPE_FLAT, 'Flat Amount'),
        (DISCOUNT_TYPE_PERCENT, 'Percentage'),
    ]

    company       = models.ForeignKey(Company, on_delete=models.CASCADE,
                                      related_name='coupons', null=True, blank=True,
                                      help_text='Leave blank for site-wide coupon')
    code          = models.CharField(max_length=50, unique=True, db_index=True)
    description   = models.TextField(blank=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES,
                                     default=DISCOUNT_TYPE_FLAT)
    discount_value= models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_order     = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                        help_text='Minimum order amount to apply')
    max_discount  = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                        help_text='Cap for percentage discount (0 = no cap)')
    usage_limit   = models.IntegerField(default=0, help_text='0 = unlimited')
    used_count    = models.IntegerField(default=0)
    valid_from    = models.DateTimeField(null=True, blank=True)
    valid_to      = models.DateTimeField(null=True, blank=True)
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} — {self.get_discount_type_display()} {self.discount_value}"

    @property
    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        return True

    def calculate_discount(self, subtotal):
        from decimal import Decimal
        if not self.is_valid:
            return Decimal('0')
        if subtotal < self.min_order:
            return Decimal('0')
        if self.discount_type == self.DISCOUNT_TYPE_FLAT:
            return min(self.discount_value, subtotal)
        else:
            disc = subtotal * self.discount_value / Decimal('100')
            if self.max_discount > 0:
                disc = min(disc, self.max_discount)
            return min(disc, subtotal)


class Notification(models.Model):
    TYPE_ORDER     = 'order'
    TYPE_SYSTEM    = 'system'
    TYPE_PROMO     = 'promo'
    TYPE_BROADCAST = 'broadcast'
    TYPE_WALLET    = 'wallet'
    TYPE_CHOICES   = [
        (TYPE_ORDER,     'Order Update'),
        (TYPE_SYSTEM,    'System'),
        (TYPE_PROMO,     'Promotion'),
        (TYPE_BROADCAST, 'Broadcast'),
        (TYPE_WALLET,    'Wallet'),
    ]

    company    = models.ForeignKey(Company, on_delete=models.CASCADE,
                                   related_name='notifications', null=True, blank=True)
    staff_user = models.ForeignKey('accounts.StaffUser', on_delete=models.CASCADE,
                                   null=True, blank=True, related_name='notifications')
    customer   = models.ForeignKey('accounts.Customer', on_delete=models.CASCADE,
                                   null=True, blank=True, related_name='notifications')

    notif_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_ORDER)
    title      = models.CharField(max_length=255)
    message    = models.TextField(blank=True)
    link       = models.CharField(max_length=500, blank=True)
    image      = models.ImageField(upload_to='notifications/', blank=True, null=True)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_notif_type_display()})"


class StaticPage(models.Model):
    slug       = models.SlugField(max_length=100, unique=True)
    title      = models.CharField(max_length=255)
    content    = models.TextField(blank=True, help_text='HTML content')
    is_active  = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title


class RoleMenuConfig(models.Model):
    """One row per role. visible_keys = list of menu keys this role can see."""
    role = models.CharField(max_length=20, unique=True)
    visible_keys = models.JSONField(default=list, help_text='List of menu key strings')
    def __str__(self):
        return f'{self.role}: {len(self.visible_keys or [])} items'


class KioskConfig(models.Model):
    """
    Per-kiosk/terminal UI configuration.
    Falls back to company-level settings when fields are blank.
    """
    company        = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='kiosk_configs')
    building       = models.ForeignKey('Building', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='kiosk_configs')
    name           = models.CharField(max_length=120, help_text='e.g. "Main Entrance Kiosk"')
    slug           = models.SlugField(max_length=120, unique=True, blank=True,
                                      help_text='Auto-set. Used in kiosk URL: /kiosk/<company_id>/?kiosk=<slug>')
    # Branding overrides (blank = use company default)
    logo           = models.ImageField(upload_to='kiosk_configs/', blank=True, null=True)
    theme_color    = models.CharField(max_length=20, blank=True,
                                      help_text='Hex colour override e.g. #c62828')
    welcome_title  = models.CharField(max_length=160, blank=True)
    welcome_subtitle = models.CharField(max_length=255, blank=True)
    hero_image     = models.ImageField(upload_to='kiosk_configs/hero/', blank=True, null=True)
    # UI feature toggles
    show_offerings = models.BooleanField(default=True)
    show_categories= models.BooleanField(default=True)
    card_style     = models.CharField(max_length=20, default='standard',
                                      choices=[('standard','Standard'),('compact','Compact'),('large','Large')],
                                      help_text='Product card display style')
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['company__name', 'name']
        verbose_name = 'Kiosk Configuration'
        verbose_name_plural = 'Kiosk Configurations'

    def __str__(self):
        return f'{self.company.name} — {self.name}'

    def save(self, *args, **kwargs):
        from django.utils.text import slugify
        if not self.slug:
            base = slugify(f'{self.company.name}-{self.name}')[:100]
            slug = base
            n = 1
            while KioskConfig.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    # ── Effective values (falls back to company) ──────────────────
    @property
    def effective_logo(self):
        return self.logo or self.company.kiosk_logo or self.company.logo

    @property
    def effective_theme_color(self):
        return self.theme_color.strip() or self.company.kiosk_theme_color or '#1e3a5f'

    @property
    def effective_welcome_title(self):
        return self.welcome_title.strip() or self.company.name

    @property
    def effective_welcome_subtitle(self):
        return self.welcome_subtitle.strip() or self.company.kiosk_welcome_text or 'Touch to order'


class WebViewConfig(models.Model):
    """
    Per-company/building web-customer UI configuration.
    Falls back to company-level settings when fields are blank.
    """
    company        = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='web_view_configs')
    building       = models.ForeignKey('Building', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='web_view_configs')
    name           = models.CharField(max_length=120, help_text='e.g. "IBM Bhubaneswar Web View"')
    slug           = models.SlugField(max_length=120, unique=True, blank=True,
                                      help_text='Auto-set. Used in web URL preview: /menu/?web=<slug>')
    logo           = models.ImageField(upload_to='web_view_configs/', blank=True, null=True)
    theme_color    = models.CharField(max_length=20, blank=True,
                                      help_text='Hex colour override e.g. #c62828')
    navbar_color   = models.CharField(max_length=20, blank=True,
                                      help_text='Top navigation bar background colour e.g. #15233b. Solid — no transparency.')
    welcome_title  = models.CharField(max_length=160, blank=True)
    welcome_subtitle = models.CharField(max_length=255, blank=True)
    hero_image     = models.ImageField(upload_to='web_view_configs/hero/', blank=True, null=True)
    show_offerings = models.BooleanField(default=True)
    show_categories = models.BooleanField(default=True)
    card_style     = models.CharField(max_length=20, default='standard',
                                      choices=[('standard','Standard'),('compact','Compact'),('large','Large')],
                                      help_text='Product card display style')
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['company__name', 'name']
        verbose_name = 'Web View Configuration'
        verbose_name_plural = 'Web View Configurations'

    def __str__(self):
        return f'{self.company.name} — {self.name}'

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(f'{self.company.name}-{self.name}-web')[:100]
            slug = base
            n = 1
            while WebViewConfig.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def effective_logo(self):
        return self.logo or self.company.logo or self.company.kiosk_logo

    @property
    def effective_theme_color(self):
        return self.theme_color.strip() or self.company.kiosk_theme_color or '#1e3a5f'

    @property
    def effective_welcome_title(self):
        return self.welcome_title.strip() or self.company.name

    @property
    def effective_welcome_subtitle(self):
        return self.welcome_subtitle.strip() or self.company.kiosk_welcome_text or 'Order online'




class DisplayBoardConfig(models.Model):
    """Per-company display-board presentation settings."""
    company        = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='display_board_configs')
    building       = models.ForeignKey('Building', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='display_board_configs')
    name           = models.CharField(max_length=120, help_text='e.g. "Main Cafeteria Display"')
    slug           = models.SlugField(max_length=120, unique=True, blank=True,
                                      help_text='Auto-set. Used in preview URL: /display-board/?board=<slug>')
    logo           = models.ImageField(upload_to='display_board_configs/', blank=True, null=True)
    footer_logo    = models.ImageField(upload_to='display_board_configs/footer/', blank=True, null=True)
    background_image = models.ImageField(upload_to='display_board_configs/background/', blank=True, null=True)
    theme_color    = models.CharField(max_length=20, blank=True, help_text='Primary accent colour e.g. #1e3a5f')
    heading_text   = models.CharField(max_length=160, blank=True)
    side_text      = models.CharField(max_length=120, blank=True, help_text='Large vertical/side text')
    waiting_text   = models.CharField(max_length=120, blank=True, help_text='Small waiting/status text')
    promo_embed_url = models.URLField(blank=True, help_text='YouTube watch/share/embed URL')
    footer_text    = models.CharField(max_length=255, blank=True)
    pending_label  = models.CharField(max_length=40, default='Pending')
    confirmed_label = models.CharField(max_length=40, default='Order Placed')
    preparing_label = models.CharField(max_length=40, default='Preparing')
    ready_label    = models.CharField(max_length=40, default='Food Ready')
    show_clock     = models.BooleanField(default=True)
    show_company_filter = models.BooleanField(default=True)
    show_status_legend = models.BooleanField(default=True)
    sound_enabled  = models.BooleanField(default=True)
    voice_enabled  = models.BooleanField(default=True)
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['company__name', 'name']
        verbose_name = 'Display Board Configuration'
        verbose_name_plural = 'Display Board Configurations'

    def __str__(self):
        return f'{self.company.name} — {self.name}'

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(f'{self.company.name}-{self.name}-board')[:100]
            slug = base
            n = 1
            while DisplayBoardConfig.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def effective_logo(self):
        return self.logo or self.company.logo or self.company.kiosk_logo

    @property
    def effective_footer_logo(self):
        return self.footer_logo or self.company.logo or self.company.kiosk_logo

    @property
    def effective_theme_color(self):
        return self.theme_color.strip() or self.company.kiosk_theme_color or '#1e3a5f'

    @property
    def effective_heading_text(self):
        return self.heading_text.strip() or 'SERVING HAPPINESS'

    @property
    def effective_side_text(self):
        return self.side_text.strip() or (self.company.name.upper() if self.company_id else 'NEVERQ')

    @property
    def effective_waiting_text(self):
        return self.waiting_text.strip() or 'Waiting for orders...'

    @property
    def effective_footer_text(self):
        return self.footer_text.strip() or 'Neverno Allied Services Pvt Ltd'

    @property
    def normalized_promo_embed_url(self):
        raw = (self.promo_embed_url or '').strip()
        if not raw:
            return ''
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(raw)
            host = (parsed.netloc or '').lower()
            path = parsed.path or ''
            if 'youtube.com' in host:
                if '/embed/' in path:
                    return raw
                video_id = parse_qs(parsed.query).get('v', [''])[0]
                if video_id:
                    return f'https://www.youtube.com/embed/{video_id}?rel=0&modestbranding=1'
            if 'youtu.be' in host:
                video_id = path.strip('/').split('/')[0]
                if video_id:
                    return f'https://www.youtube.com/embed/{video_id}?rel=0&modestbranding=1'
        except Exception:
            return raw
        return raw


def resolve_display_board_config(company, building=None, slug=''):
    """Return the active display-board config for a company/building or a slug preview."""
    if not company:
        return None

    qs = DisplayBoardConfig.objects.filter(company=company, is_active=True).select_related('company', 'building')

    slug = (slug or '').strip()
    if slug:
        return qs.filter(slug=slug).first()

    building_id = getattr(building, 'pk', None)
    if building_id:
        exact = qs.filter(building_id=building_id).order_by('-created_at', 'name').first()
        if exact:
            return exact

    return qs.filter(building__isnull=True).order_by('-created_at', 'name').first()

def resolve_web_view_config(company, building=None, slug=''):
    """Return the active web-view config for a company/building or a slug preview."""
    if not company:
        return None

    qs = WebViewConfig.objects.filter(company=company, is_active=True).select_related('company', 'building')

    slug = (slug or '').strip()
    if slug:
        return qs.filter(slug=slug).first()

    building_id = getattr(building, 'pk', None)
    if building_id:
        exact = qs.filter(building_id=building_id).order_by('-created_at', 'name').first()
        if exact:
            return exact

    return qs.filter(building__isnull=True).order_by('-created_at', 'name').first()
