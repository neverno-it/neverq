import os
import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image
from apps.core.models import Company


PORTAL_BANNER_WIDTH = 1240
PORTAL_BANNER_HEIGHT = 660
PORTAL_BANNER_RATIO = PORTAL_BANNER_WIDTH / PORTAL_BANNER_HEIGHT
PORTAL_BANNER_LABEL = f"{PORTAL_BANNER_WIDTH} × {PORTAL_BANNER_HEIGHT} px"
PORTAL_BANNER_RATIO_TOLERANCE = 0.01


def _validate_portal_banner_image(image_file, field_label='Image'):
    """Validate that uploaded banner/library images match the customer portal banner frame."""
    if not image_file:
        return

    try:
        image_file.seek(0)
    except AttributeError:
        pass

    try:
        with Image.open(image_file) as img:
            width, height = img.size
    except (OSError, Exception):  # PIL raises OSError for corrupt images; keep broad for unknown PIL errors
        raise ValidationError({
            'image': f'{field_label} could not be read. Please upload a valid JPG, PNG, or WEBP image.'
        })
    finally:
        try:
            image_file.seek(0)
        except AttributeError:
            pass

    if not width or not height:
        raise ValidationError({'image': f'{field_label} must have a valid width and height.'})

    ratio_error = abs((width / height) - PORTAL_BANNER_RATIO) / PORTAL_BANNER_RATIO
    if ratio_error > PORTAL_BANNER_RATIO_TOLERANCE:
        raise ValidationError({
            'image': (
                f'{field_label} must be close to the customer banner ratio {PORTAL_BANNER_WIDTH}:{PORTAL_BANNER_HEIGHT} '
                f'({PORTAL_BANNER_LABEL}). Your file is {width} × {height} px.'
            )
        })

    if width < PORTAL_BANNER_WIDTH or height < PORTAL_BANNER_HEIGHT:
        raise ValidationError({
            'image': (
                f'{field_label} is too small for the customer portal banner. '
                f'Upload at least {PORTAL_BANNER_LABEL}. Your file is {width} × {height} px.'
            )
        })


class FoodType(models.Model):
    name       = models.CharField(max_length=255)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


def category_image_path(instance, filename):
    return f'categories/{uuid.uuid4().hex}{os.path.splitext(filename)[1]}'


class Category(models.Model):
    ICON_NONE   = 0
    ICON_VEG    = 1
    ICON_NONVEG = 2
    TYPE_ROOT     = 1
    TYPE_CHILD    = 2
    TYPE_SUBCHILD = 3

    parent     = models.ForeignKey('self', on_delete=models.CASCADE,
                                   null=True, blank=True, related_name='children')
    sub_parent = models.ForeignKey('self', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='sub_children')
    slug           = models.SlugField(max_length=255)
    name           = models.CharField(max_length=255)
    companies      = models.ManyToManyField(Company, blank=True, related_name='categories')
    image          = models.ImageField(upload_to=category_image_path, blank=True, null=True)
    icon_type      = models.IntegerField(
        choices=[(ICON_NONE,'None'),(ICON_VEG,'Veg'),(ICON_NONVEG,'Non-Veg')], default=ICON_NONE)
    tagline        = models.TextField(blank=True)
    cat_type       = models.IntegerField(
        choices=[(TYPE_ROOT,'Root'),(TYPE_CHILD,'Child'),(TYPE_SUBCHILD,'Sub-child')], default=TYPE_ROOT)
    position_order = models.IntegerField(default=0)
    open_days      = models.JSONField(
        default=list, blank=True,
        help_text='Days this category is shown e.g. ["Mon","Tue"]. Empty = every day.'
    )
    preparation_time_minutes = models.PositiveIntegerField(
        default=0,
        help_text='Minutes after confirmation before items in this category should be marked ready. 0 = manual flow.'
    )
    is_active      = models.BooleanField(default=True)
    is_deleted     = models.BooleanField(default=False)

    class Meta:
        ordering = ['position_order', 'name']
        verbose_name_plural = 'Categories'
        constraints = [
            models.UniqueConstraint(fields=['slug'], name='uniq_category_slug'),
        ]

    def __str__(self):
        return f"{self.parent.name} → {self.name}" if self.parent else self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            n = 1
            while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_veg(self):
        return self.icon_type == self.ICON_VEG

    @property
    def is_nonveg(self):
        return self.icon_type == self.ICON_NONVEG

    def _company_status_for(self, company=None):
        if not company or not self.pk:
            return None
        status_obj_map = getattr(self, '_company_status_obj_map', None)
        if status_obj_map is not None:
            return status_obj_map.get(company.pk)
        prefetched = getattr(self, '_prefetched_objects_cache', {}).get('company_statuses')
        if prefetched is not None:
            for status in prefetched:
                if status.company_id == company.pk:
                    return status
            return None
        return self.company_statuses.filter(company=company).first()

    def is_active_for_company(self, company=None):
        if self.is_deleted:
            return False
        if company and self.pk:
            status_map = getattr(self, '_company_status_map', None)
            if status_map is not None:
                if company.pk in status_map:
                    return bool(status_map[company.pk])
                return bool(self.is_active)
            prefetched = getattr(self, '_prefetched_objects_cache', {}).get('company_statuses')
            if prefetched is not None:
                for status in prefetched:
                    if status.company_id == company.pk:
                        return bool(status.is_active)
                return bool(self.is_active)
            status = self.company_statuses.filter(company=company).first()
            if status:
                return bool(status.is_active)
        return bool(self.is_active)

    def _open_days_for_company(self, company=None):
        status = self._company_status_for(company)
        if status and getattr(status, 'use_custom_availability', False):
            return list(status.open_days or [])
        return list(self.open_days or [])

    def _schedule_rows_for_company(self, company=None):
        schedules = list(self.schedules.all()) if self.pk else []
        if not schedules:
            return []
        if company:
            company_id = company.pk
            site_schedules = [s for s in schedules if s.company_id == company_id]
            if site_schedules:
                return site_schedules
            status = self._company_status_for(company)
            if status and getattr(status, 'use_custom_availability', False):
                return []
        return [s for s in schedules if s.company_id is None]

    def is_open_on_day(self, weekday_abbr=None, company=None):
        """Return True if this category is available today (or on the given weekday abbr like 'Mon')."""
        days = self._open_days_for_company(company)
        if not days:
            return True  # no restriction
        if weekday_abbr is None:
            # weekday() returns 0=Mon … 6=Sun
            wd = timezone.localtime().weekday()
            abbrs = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
            weekday_abbr = abbrs[wd]
        return weekday_abbr in days

    def is_active_now(self, company=None):
        if not self.is_active_for_company(company):
            return False
        if not self.is_open_on_day(company=company):
            return False
        schedules = self._schedule_rows_for_company(company)
        if schedules:
            return any(s.is_active_now() for s in schedules)
        return True


class CategoryCompanyStatus(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='company_statuses')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='category_statuses')
    is_active = models.BooleanField(default=True)
    use_custom_availability = models.BooleanField(default=False)
    open_days = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['category__position_order', 'category__name', 'company__name']
        constraints = [
            models.UniqueConstraint(fields=['category', 'company'], name='uniq_category_company_status'),
        ]

    def __str__(self):
        return f'{self.category.name} / {self.company.name}: {"Active" if self.is_active else "Inactive"}'


# FIX #4: Full day names matching the SQL data
DAYS_OF_WEEK = [
    ('Monday','Monday'), ('Tuesday','Tuesday'), ('Wednesday','Wednesday'),
    ('Thursday','Thursday'), ('Friday','Friday'), ('Saturday','Saturday'),
    ('Sunday','Sunday'), ('All','All Days'),
    # short forms kept for backward compat
    ('Mon','Mon'), ('Tue','Tue'), ('Wed','Wed'),
    ('Thu','Thu'), ('Fri','Fri'), ('Sat','Sat'), ('Sun','Sun'),
]

WEEKDAY_CHOICES = [
    ('Mon', 'Monday'), ('Tue', 'Tuesday'), ('Wed', 'Wednesday'),
    ('Thu', 'Thursday'), ('Fri', 'Friday'), ('Sat', 'Saturday'), ('Sun', 'Sunday'),
]
ALL_DAYS = [d for d, _ in WEEKDAY_CHOICES]



class Schedule(models.Model):
    category    = models.ForeignKey(Category, on_delete=models.CASCADE,
                                    related_name='schedules', null=True, blank=True)
    company     = models.ForeignKey(Company, on_delete=models.CASCADE,
                                    related_name='category_schedules', null=True, blank=True)
    # Phase 2: offering link — same Schedule table, same logic, same is_active_now()
    offering    = models.ForeignKey('Offering', on_delete=models.CASCADE,
                                    related_name='schedules', null=True, blank=True)
    display_day = models.CharField(max_length=20)
    start_time  = models.TimeField()
    end_time    = models.TimeField()

    class Meta:
        ordering = ['display_day', 'start_time']

    def __str__(self):
        target = self.category or self.offering or '?'
        if self.category and self.company:
            target = f"{self.category} / {self.company}"
        return f"{target} | {self.display_day} {self.start_time}–{self.end_time}"

    def is_active_now(self):
        """Return True when the current local time falls inside this schedule row.

        Supports both same-day windows (e.g. 09:00 → 17:00) and overnight
        windows that cross midnight (e.g. Thu 21:00 → Fri 12:00, or 23:00 → 01:00).
        """
        from django.utils import timezone as _tz
        now = _tz.localtime(_tz.now())
        t = now.time()
        weekday = now.weekday()
        DAY_MAP = {
            'Monday':0,'Tuesday':1,'Wednesday':2,'Thursday':3,
            'Friday':4,'Saturday':5,'Sunday':6,
            'Mon':0,'Tue':1,'Wed':2,'Thu':3,'Fri':4,'Sat':5,'Sun':6,
        }

        # All-day schedule row: just evaluate the time window, including overnight.
        if self.display_day == 'All':
            if self.start_time <= self.end_time:
                return self.start_time <= t <= self.end_time
            return t >= self.start_time or t <= self.end_time

        day_idx = DAY_MAP.get(self.display_day, -1)
        if day_idx == -1:
            return False

        # Same-day window.
        if self.start_time <= self.end_time:
            return weekday == day_idx and self.start_time <= t <= self.end_time

        # Overnight window: active on the schedule's display_day after start_time,
        # and also active on the next day before end_time.
        next_day_idx = (day_idx + 1) % 7
        return (
            (weekday == day_idx and t >= self.start_time)
            or (weekday == next_day_idx and t <= self.end_time)
        )


class Cafe(models.Model):
    """Sub-outlet within a company — mirrors tbl_cafes."""
    company    = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cafes')
    building   = models.ForeignKey('core.Building', on_delete=models.SET_NULL, null=True, blank=True, related_name='cafes')
    name       = models.CharField(max_length=255)
    is_active  = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']

    def __str__(self):
        if self.building_id:
            return f"{self.name} ({self.company.name} / {self.building.name})"
        return f"{self.name} ({self.company.name})"


class Offering(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='offerings')
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, blank=True)
    menu_date = models.DateField(null=True, blank=True)
    available_from = models.TimeField(null=True, blank=True)
    available_to = models.TimeField(null=True, blank=True)
    start_datetime = models.DateTimeField(null=True, blank=True)
    end_datetime = models.DateTimeField(null=True, blank=True)
    position_order = models.IntegerField(default=0)
    open_days      = models.JSONField(
        default=list, blank=True,
        help_text='Days offering is available e.g. ["Mon","Tue"]. Empty = every day.'
    )
    image = models.ImageField(upload_to='offerings/', blank=True, null=True)
    prep_start_time = models.TimeField(
        null=True, blank=True,
        help_text=(
            'Kitchen prep gate: auto-ready countdown will not start before this time. '
            'Leave blank to keep existing behaviour (countdown starts from order time). '
            'Example: 11:30 means kitchen starts preparing at 11:30 AM regardless of when the order was placed.'
        )
    )
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['position_order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def is_active_now(self):
        from django.utils import timezone as tz
        now = tz.localtime()
        if not self.is_active or self.is_deleted:
            return False
        # Day-of-week check
        days = self.open_days or []
        if days:
            abbrs = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
            today_abbr = abbrs[now.weekday()]
            if today_abbr not in days:
                return False
        if self.menu_date and self.menu_date != now.date():
            return False
        if self.start_datetime and now < self.start_datetime:
            return False
        if self.end_datetime and now > self.end_datetime:
            return False
        # Phase 2: check Schedule rows first (supports multiple windows per day)
        if self.pk:
            schedules = list(self.schedules.all())
            if schedules:
                return any(s.is_active_now() for s in schedules)
        # Legacy single-window fallback (available_from / available_to)
        if self.available_from and self.available_to:
            current = now.time()
            if self.available_from <= self.available_to:
                return self.available_from <= current <= self.available_to
            return current >= self.available_from or current <= self.available_to
        return True


class Counter(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='counters')
    cafe = models.ForeignKey(Cafe, on_delete=models.CASCADE, related_name='counters', null=True, blank=True)
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=50, blank=True)
    printer_label = models.CharField(max_length=120, blank=True, help_text='Optional browser/printer label for this counter POS.')
    auto_print_on_ready = models.BooleanField(default=False)
    auto_print_on_scan = models.BooleanField(default=True)
    position_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['position_order', 'name']
        unique_together = [('company', 'name')]

    def __str__(self):
        return f"{self.name} ({self.company.name})"

    @property
    def effective_printer_label(self):
        return (self.printer_label or self.name or 'KOT Printer').strip()

    @property
    def printer_route_key(self):
        return f'counter:{self.pk}' if self.pk else 'default'


def product_image_path(instance, filename):
    return f'products/{uuid.uuid4().hex}{os.path.splitext(filename)[1]}'


class Product(models.Model):
    category     = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    offering     = models.ForeignKey('Offering', on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    sub_category = models.ForeignKey(Category, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='sub_products')
    sub_list     = models.ForeignKey(Category, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='list_products')
    company      = models.ForeignKey(Company, on_delete=models.CASCADE,
                                     related_name='products', null=True, blank=True)
    food_type    = models.ManyToManyField(FoodType, blank=True)
    counters     = models.ManyToManyField('Counter', blank=True, through='ProductCounter', related_name='products')

    menu_date       = models.DateField(null=True, blank=True)
    available_from  = models.TimeField(null=True, blank=True)
    available_to    = models.TimeField(null=True, blank=True)
    start_datetime  = models.DateTimeField(null=True, blank=True)
    end_datetime    = models.DateTimeField(null=True, blank=True)

    slug            = models.SlugField(max_length=255)
    name            = models.CharField(max_length=255)
    code            = models.CharField(max_length=100, blank=True)
    price           = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    company_price   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    room_service_extra_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='Percentage added to the visitor price for room service orders.',
    )
    packing_price   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_qty         = models.IntegerField(default=1)
    max_qty         = models.IntegerField(default=10)   # web ordering stock
    pos_qty         = models.IntegerField(default=0)    # POS terminal stock
    web_qty         = models.IntegerField(default=-1, help_text='-1 = unlimited web stock; >=0 = capped')
    preparation_time_minutes = models.PositiveIntegerField(
        default=10,
        help_text='Minutes after confirmation before this item should be marked ready.'
    )
    calories        = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Approximate calorie count (kcal) per serving. Leave blank if unknown.',
    )
    image           = models.ImageField(upload_to=product_image_path, blank=True, null=True)
    description     = models.TextField(blank=True)
    rating          = models.DecimalField(max_digits=3, decimal_places=1, default=0)
    position_order  = models.IntegerField(default=0)
    is_active             = models.BooleanField(default=True)
    featured_in_kiosk_extra = models.BooleanField(
        default=False,
        help_text='Show this product in the "Featured" section on the kiosk (max 10 shown).'
    )
    featured_in_web = models.BooleanField(
        default=False,
        help_text='Pin this product in the "Featured Products" section on the customer web portal.'
    )
    is_kiosk_active  = models.BooleanField(
        default=True,
        help_text='Controls visibility in the self-service kiosk. '
                  'Independent of the web (customer portal) active status.'
    )
    is_pos_active = models.BooleanField(
        default=True,
        help_text='Controls whether this product appears on the POS terminal. '
                  'Independent of the web and kiosk active status.'
    )
    schedule_bypass  = models.BooleanField(
        default=False,
        help_text='SUPERADMIN ONLY: When enabled, this product always appears in the menu '
                  'regardless of its parent Offering or Category schedule. '
                  "The product's own time/date settings still apply."
    )
    is_deleted      = models.BooleanField(default=False)

    class Meta:
        ordering = ['position_order', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'slug'],
                condition=models.Q(company__isnull=False),
                name='uniq_product_company_slug',
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            n = 1
            qs = Product.objects.filter(company=self.company, slug=slug).exclude(pk=self.pk)
            while qs.exists():
                slug = f'{base}-{n}'
                n += 1
                qs = Product.objects.filter(company=self.company, slug=slug).exclude(pk=self.pk)
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def effective_price(self):
        return self.price

    def is_available_now(self):
        """Product schedule overrides category/offering schedule."""
        from django.utils import timezone as tz
        if not self.is_active or self.is_deleted:
            return False
        now_tz = tz.now()
        now    = tz.localtime(now_tz)   # local-aware datetime — use for time/weekday comparisons

        has_explicit_product_schedule = bool(self.available_from or self.available_to or self.start_datetime or self.end_datetime or self.menu_date)

        if self.menu_date and self.menu_date != tz.localdate():
            return False
        if self.available_from and self.available_to:
            current = now.time()
            if self.available_from <= self.available_to:
                if not (self.available_from <= current <= self.available_to):
                    return False
            else:
                if not (current >= self.available_from or current <= self.available_to):
                    return False
        if self.start_datetime and now_tz < self.start_datetime:
            return False
        if self.end_datetime and now_tz > self.end_datetime:
            return False

        if self.category_id and self.category and not self.category.is_active_for_company(self.company):
            return False
        if self.offering_id and self.offering and (not self.offering.is_active or self.offering.is_deleted):
            return False

        if has_explicit_product_schedule:
            return True

        # schedule_bypass: superadmin flag — skip offering/category schedule checks
        if self.schedule_bypass:
            return True

        if self.category_id and self.category and not self.category.is_active_now(self.company):
            return False

        if self.offering_id and self.offering:
            return self.offering.is_active_now()
        return True

    @property
    def primary_counter(self):
        mapping = self.counter_mappings.select_related('counter').filter(is_active=True).order_by('position_order', 'id').first()
        return mapping.counter if mapping else None


def advert_image_path(instance, filename):
    return f'adverts/{uuid.uuid4().hex}{os.path.splitext(filename)[1]}'


class HolidaySchedule(models.Model):
    """
    Recurring annual holiday — e.g. Independence Day (15 Aug).
    Any Advertise linked to this schedule will automatically go live
    every year on this date, regardless of its start_date / end_date.
    """
    name        = models.CharField(max_length=255, help_text='e.g. Independence Day')
    month       = models.IntegerField(help_text='Month number 1–12')
    day         = models.IntegerField(help_text='Day number 1–31')
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True)
    created_by  = models.ForeignKey(
        'accounts.StaffUser', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_holidays'
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['month', 'day']
        verbose_name = 'Holiday Schedule'
        unique_together = [('month', 'day')]

    def __str__(self):
        return f'{self.name} ({self.day:02d}/{self.month:02d})'

    @property
    def is_today(self):
        from django.utils import timezone
        today = timezone.localdate()
        return self.is_active and today.month == self.month and today.day == self.day

    @property
    def next_occurrence(self):
        """Return the next date this holiday falls on."""
        from django.utils import timezone
        import datetime
        today = timezone.localdate()
        try:
            this_year = today.replace(month=self.month, day=self.day)
        except ValueError:
            return None
        if this_year >= today:
            return this_year
        try:
            return today.replace(year=today.year + 1, month=self.month, day=self.day)
        except ValueError:
            return None


def media_asset_path(instance, filename):
    return f'media_library/{uuid.uuid4().hex}{os.path.splitext(filename)[1]}'


class MediaAsset(models.Model):
    """Reusable image library — upload once, use across many advertisements."""
    company     = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='media_assets')
    # Extra companies this asset is shared with (optional)
    companies   = models.ManyToManyField(
        Company, blank=True, related_name='shared_assets',
        help_text='Additional sites that can use this image'
    )
    name        = models.CharField(max_length=255, help_text='Friendly label for this image')
    image       = models.ImageField(
        upload_to=media_asset_path,
        help_text=f'Upload {PORTAL_BANNER_LABEL} (or larger in the same ratio) so it fits the customer portal banner'
    )
    uploaded_by = models.ForeignKey(
        'accounts.StaffUser', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='uploaded_assets'
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Media Asset'

    def __str__(self):
        return f'{self.name} ({self.company.name})'

    def clean(self):
        super().clean()
        if self.image:
            _validate_portal_banner_image(self.image, field_label='Library image')

    def save(self, *args, **kwargs):
        # full_clean() is called by Django admin and ModelForms automatically.
        # Calling it here would break bulk_create() and M2M admin inlines.
        # Image validation lives in clean() and is enforced via forms.
        super().save(*args, **kwargs)


class Advertise(models.Model):
    STATUS_PENDING  = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES  = [
        (STATUS_PENDING,  'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    # Owning company (for scoping / permissions)
    company        = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='adverts')
    # Sites this ad runs on — if none selected, defaults to own company only
    companies      = models.ManyToManyField(
        Company, blank=True, related_name='targeted_adverts',
        help_text='Select which sites to show this banner on. Leave empty to show only on your own site.'
    )
    name           = models.CharField(max_length=255, blank=True)

    # Image: either a direct upload OR picked from the media library
    image          = models.ImageField(
        upload_to=advert_image_path, blank=True, null=True,
        help_text=f'Upload {PORTAL_BANNER_LABEL} (or larger in the same ratio) for the customer portal banner'
    )
    media_asset    = models.ForeignKey(
        MediaAsset, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='adverts',
        help_text='Pick from media library instead of uploading'
    )

    position_order = models.IntegerField(default=0)
    is_active      = models.BooleanField(default=True)

    # Date range scheduling
    start_date     = models.DateField(null=True, blank=True, help_text='Run from this date (inclusive)')
    end_date       = models.DateField(null=True, blank=True, help_text='Run until this date (inclusive)')

    # Holiday schedules — this ad also runs on these annual dates every year
    holiday_schedules = models.ManyToManyField(
        HolidaySchedule, blank=True, related_name='adverts',
        help_text='Also run this ad automatically on selected national holidays every year'
    )

    # Approval workflow
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_by     = models.ForeignKey(
        'accounts.StaffUser', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_adverts'
    )
    reviewed_by    = models.ForeignKey(
        'accounts.StaffUser', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_adverts'
    )
    review_note    = models.TextField(blank=True, help_text='Admin note on approval/rejection')
    created_at     = models.DateTimeField(null=True, blank=True)

    def clean(self):
        super().clean()
        if self.image:
            _validate_portal_banner_image(self.image, field_label='Banner image')

    def save(self, *args, **kwargs):
        if not self.created_at:
            from django.utils import timezone
            self.created_at = timezone.now()
        # full_clean() is enforced by Django admin / ModelForms — not needed here.
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['position_order', '-created_at']

    def __str__(self):
        return f"Ad #{self.pk} – {self.company.name} [{self.get_status_display()}]"

    @property
    def display_image(self):
        """Return the effective image: media_asset takes priority over direct upload."""
        if self.media_asset_id and self.media_asset.image:
            return self.media_asset.image
        return self.image

    @property
    def is_scheduled_active(self):
        """
        True only when the banner should actually be displayed today.

        Rules (in priority order):
        1. If today matches a linked holiday → True (fires every year).
        2. If start_date set and today < start_date → False (not started).
        3. If end_date set and today > end_date → False (expired).
        4. If ONLY holidays linked (no date range) and today is not one → False.
        5. Otherwise → True (no restrictions).
        """
        from django.utils import timezone
        today = timezone.localdate()

        # 1. Holiday match — always live on the exact date
        if self.pk:
            if self.holiday_schedules.filter(
                is_active=True, month=today.month, day=today.day
            ).exists():
                return True

        # 2 & 3. Normal date window
        if self.start_date and today < self.start_date:
            return False
        if self.end_date and today > self.end_date:
            return False

        # 4. Holiday-only banner — only live on linked holiday dates
        if self.pk and not self.start_date and not self.end_date:
            if self.holiday_schedules.filter(is_active=True).exists():
                return False

        return True

    @property
    def is_live(self):
        """True if approved, active flag on, and within schedule."""
        return (
            self.status == self.STATUS_APPROVED
            and self.is_active
            and self.is_scheduled_active
        )

    @property
    def next_live_date(self):
        """Next date this banner will go live (for UI display)."""
        from django.utils import timezone
        today = timezone.localdate()
        if self.start_date and self.start_date > today:
            return self.start_date
        if self.pk and not self.start_date and not self.end_date:
            soonest = None
            for h in self.holiday_schedules.filter(is_active=True):
                occ = h.next_occurrence
                if occ and occ > today:
                    if soonest is None or occ < soonest:
                        soonest = occ
            return soonest
        return None

    @property
    def schedule_label(self):
        """One of: live | scheduled | expired | inactive | pending | rejected"""
        from django.utils import timezone
        today = timezone.localdate()
        if self.status != self.STATUS_APPROVED:
            return self.status
        if not self.is_active:
            return 'inactive'
        if self.end_date and today > self.end_date:
            return 'expired'
        if self.is_scheduled_active:
            return 'live'
        return 'scheduled'

    def targets_company(self, company):
        """True if this ad should display for the given company."""
        if self.companies.filter(pk=company.pk).exists():
            return True
        # Falls back to own company if no specific targets set
        return not self.companies.exists() and self.company_id == company.pk


class ProductCounter(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='counter_mappings')
    counter = models.ForeignKey(Counter, on_delete=models.CASCADE, related_name='product_mappings')
    position_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['position_order', 'id']
        unique_together = [('product', 'counter')]

    def __str__(self):
        return f"{self.product.name} → {self.counter.name}"


class Offer(models.Model):
    TYPE_BOGO    = 'bogo'
    TYPE_FREE    = 'free'
    TYPE_PERCENT = 'percent'
    TYPE_CART    = 'cart'
    TYPE_FLAT    = 'flat'
    OFFER_TYPE_CHOICES = [
        (TYPE_BOGO,    'Buy 1 Get 1 Free'),
        (TYPE_FREE,    '100% Free Product'),
        (TYPE_PERCENT, 'Percentage Off Product'),
        (TYPE_CART,    'Cart % Discount'),
        (TYPE_FLAT,    'Flat ₹ Off (Min Order)'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='offers')
    cafe = models.ForeignKey(Cafe, on_delete=models.SET_NULL, null=True, blank=True, related_name='offers')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='offers',
                    help_text='Single product. Leave blank for multi-product or cart-level offers.')
    products = models.ManyToManyField(Product, blank=True, related_name='multi_offers',
                    help_text='Multiple products this offer applies to.')
    title = models.CharField(max_length=160)
    offer_type = models.CharField(max_length=20, choices=OFFER_TYPE_CHOICES, default=TYPE_PERCENT)
    value           = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                        help_text='PERCENT/CART: percentage (0-100). FLAT: rupee amount off.')
    min_order_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                        help_text='Minimum cart total (₹) needed to unlock this offer.')
    max_discount    = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                        help_text='Cap on discount amount (₹) for PERCENT/CART offers.')
    popup_image = models.ImageField(upload_to='offers/', null=True, blank=True)
    start_datetime = models.DateTimeField(null=True, blank=True)
    end_datetime = models.DateTimeField(null=True, blank=True)
    is_popup_enabled = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def is_live(self):
        from django.utils import timezone as tz
        now = tz.now()
        if not self.is_active or self.is_deleted:
            return False
        if self.start_datetime and now < self.start_datetime:
            return False
        if self.end_datetime and now > self.end_datetime:
            return False
        return True


class OfferUsage(models.Model):
    """Tracks one-use offer redemption per customer per day."""
    offer    = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='usages')
    customer = models.ForeignKey('accounts.Customer', on_delete=models.CASCADE, related_name='offer_usages')
    order    = models.ForeignKey('orders.Order', on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name='offer_usages')
    used_at  = models.DateTimeField(auto_now_add=True)
    used_on  = models.DateField(default=timezone.localdate, db_index=True)

    class Meta:
        unique_together = [('offer', 'customer', 'used_on')]
        ordering = ['-used_at']

    def __str__(self):
        return f'{self.customer} used "{self.offer}" on {self.used_on:%Y-%m-%d}'


class ProductCompanyPrice(models.Model):
    """Site-wise price override: same product, different price per company/building/cafe."""
    product   = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='company_prices')
    company   = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='product_prices')
    building  = models.ForeignKey('core.Building', on_delete=models.CASCADE, related_name='product_prices', null=True, blank=True)
    cafe      = models.ForeignKey('Cafe', on_delete=models.CASCADE, related_name='product_prices', null=True, blank=True)
    price     = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Site-wise Price'
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'company'],
                condition=models.Q(building__isnull=True, cafe__isnull=True),
                name='uniq_product_company_price_company_only',
            ),
            models.UniqueConstraint(
                fields=['product', 'building'],
                condition=models.Q(building__isnull=False, cafe__isnull=True),
                name='uniq_product_company_price_building',
            ),
            models.UniqueConstraint(
                fields=['product', 'cafe'],
                condition=models.Q(cafe__isnull=False),
                name='uniq_product_company_price_cafe',
            ),
        ]

    def __str__(self):
        return f'{self.product.name} @ {self.scope_label}: ₹{self.price}'

    @property
    def scope_label(self):
        if self.cafe_id:
            if self.cafe.building_id:
                return f'{self.company.name} / {self.cafe.building.name} / {self.cafe.name}'
            return f'{self.company.name} / {self.cafe.name}'
        if self.building_id:
            return f'{self.company.name} / {self.building.name}'
        return self.company.name

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.building_id and self.building.company_id != self.company_id:
            raise ValidationError('Selected building does not belong to the selected company.')
        if self.cafe_id and self.cafe.company_id != self.company_id:
            raise ValidationError('Selected cafe does not belong to the selected company.')
        if self.cafe_id and self.cafe.building_id and self.building_id and self.cafe.building_id != self.building_id:
            raise ValidationError('Selected cafe does not belong to the selected building.')
        if self.cafe_id and self.cafe.building_id and not self.building_id:
            self.building = self.cafe.building


class StockLedger(models.Model):
    """
    Unified stock deduction log for both web orders and POS orders.
    Positive qty = restock/cancel. Negative qty = deduction.
    """
    SOURCE_WEB    = 'web'
    SOURCE_POS    = 'pos'
    SOURCE_MANUAL = 'manual'
    SOURCE_CHOICES = [
        (SOURCE_WEB,    'Web Order'),
        (SOURCE_POS,    'POS Order'),
        (SOURCE_MANUAL, 'Manual Adjustment'),
    ]

    product    = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='stock_entries')
    company    = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='stock_entries')
    source     = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_WEB)
    ref_id     = models.IntegerField(default=0, help_text='Order PK or POS order PK')
    qty        = models.IntegerField(help_text='Negative = deduct, positive = restock')
    note       = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Stock Ledger Entry'

    def __str__(self):
        direction = 'OUT' if self.qty < 0 else 'IN'
        return f'{direction} {abs(self.qty)} × {self.product.name} ({self.source})'




def category_gallery_image_path(instance, filename):
    return f'category_gallery/{uuid.uuid4().hex}{os.path.splitext(filename)[1]}'


def offering_gallery_image_path(instance, filename):
    return f'offering_gallery/{uuid.uuid4().hex}{os.path.splitext(filename)[1]}'


class CategoryGallery(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='category_gallery', null=True, blank=True,
                                help_text='Leave blank for a global/shared image')
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to=category_gallery_image_path)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Category Gallery Image'
        verbose_name_plural = 'Category Image Gallery'

    def __str__(self):
        return self.name


class OfferingGallery(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='offering_gallery', null=True, blank=True,
                                help_text='Leave blank for a global/shared image')
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to=offering_gallery_image_path)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Offering Gallery Image'
        verbose_name_plural = 'Offering Image Gallery'

    def __str__(self):
        return self.name


# ── Product Gallery ──────────────────────────────────────────────────────────

def product_gallery_image_path(instance, filename):
    return f'product_gallery/{uuid.uuid4().hex}{os.path.splitext(filename)[1]}'


class ProductGallery(models.Model):
    """
    Shared image library for products — similar to MediaAsset for banners.
    Admin uploads images here; they can be picked when creating/editing products.
    """
    company    = models.ForeignKey('core.Company', on_delete=models.CASCADE,
                                   related_name='product_gallery', null=True, blank=True,
                                   help_text='Leave blank for a global/shared image')
    name       = models.CharField(max_length=255, help_text='Descriptive label for this image')
    image      = models.ImageField(upload_to=product_gallery_image_path)
    uploaded_by= models.ForeignKey('accounts.StaffUser', on_delete=models.SET_NULL,
                                   null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Product Gallery Image'
        verbose_name_plural = 'Product Gallery'

    def __str__(self):
        prefix = self.company.name + ' / ' if self.company else 'Global / '
        return prefix + self.name
