from django.db import models
from django.utils import timezone
from apps.core.models import Company


class POSProduct(models.Model):
    company   = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='pos_products')
    name      = models.CharField(max_length=255)
    price     = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    is_deleted= models.BooleanField(default=False)
    created_at= models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'POS Product'

    def __str__(self):
        return f"{self.name} (₹{self.price})"


class POSOrder(models.Model):
    PAYMENT_CASH = 1
    PAYMENT_CARD = 2
    PAYMENT_UPI  = 3
    PAYMENT_CHOICES = [
        (PAYMENT_CASH, 'Cash'),
        (PAYMENT_CARD, 'Card'),
        (PAYMENT_UPI,  'UPI'),
    ]

    CUSTOMER_STAFF        = 'staff'
    CUSTOMER_VISITOR      = 'visitor'
    CUSTOMER_ROOM_SERVICE = 'room_service'
    CUSTOMER_TYPE_CHOICES = [
        (CUSTOMER_STAFF,        'Staff'),
        (CUSTOMER_VISITOR,      'Visitor'),
        (CUSTOMER_ROOM_SERVICE, 'Room Service'),
    ]

    company        = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='pos_orders')
    customer_name  = models.CharField(max_length=255, default='Walk-in Customer')
    customer_email = models.CharField(max_length=255, blank=True)
    customer_phone = models.CharField(max_length=30, blank=True)
    customer_type  = models.CharField(max_length=20, choices=CUSTOMER_TYPE_CHOICES, default=CUSTOMER_VISITOR)
    order_number   = models.CharField(max_length=50, unique=True, blank=True)
    base_amount    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    card_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount   = models.DecimalField(max_digits=10, decimal_places=2)
    payment_type   = models.IntegerField(choices=PAYMENT_CHOICES, default=PAYMENT_CASH)
    is_deleted     = models.BooleanField(default=False)
    # allow null so imported historical orders keep their date;
    # new orders always get set in save()
    created_at     = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'POS Order'

    def __str__(self):
        return f"POS #{self.order_number} — {self.customer_name}"

    def save(self, *args, **kwargs):
        import uuid
        if not self.order_number:
            self.order_number = f"POS-{uuid.uuid4().hex[:8].upper()}"
        if not self.created_at:           # ← THE KEY FIX
            self.created_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def created_date(self):
        return timezone.localtime(self.created_at).date() if self.created_at else None


class POSOrderItem(models.Model):
    company      = models.ForeignKey(Company, on_delete=models.CASCADE)
    order        = models.ForeignKey(POSOrder, on_delete=models.CASCADE, related_name='items')
    product_name = models.CharField(max_length=255)
    price        = models.DecimalField(max_digits=10, decimal_places=2)
    qty          = models.IntegerField(default=1)
    amount       = models.DecimalField(max_digits=10, decimal_places=2)
    is_deleted   = models.BooleanField(default=False)
    created_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.product_name} × {self.qty}"

    def save(self, *args, **kwargs):
        if not self.created_at:
            self.created_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        return self.price * self.qty
