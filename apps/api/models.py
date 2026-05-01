from django.db import models
from apps.core.models import Company


class FCMDevice(models.Model):
    PLATFORM_ANDROID = 'android'
    PLATFORM_IOS = 'ios'
    PLATFORM_CHOICES = [
        (PLATFORM_ANDROID, 'Android'),
        (PLATFORM_IOS, 'iOS'),
    ]

    staff_user = models.ForeignKey(
        'accounts.StaffUser', null=True, blank=True,
        on_delete=models.CASCADE, related_name='fcm_devices'
    )
    customer = models.ForeignKey(
        'accounts.Customer', null=True, blank=True,
        on_delete=models.CASCADE, related_name='fcm_devices'
    )
    token = models.TextField(unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, default=PLATFORM_ANDROID)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'FCM Device'
        ordering = ['-updated_at']

    def __str__(self):
        if self.staff_user_id:
            return f'Staff: {self.staff_user.email}'
        if self.customer_id:
            return f'Customer: {self.customer.email}'
        return 'Unknown'


class Cart(models.Model):
    customer = models.OneToOneField(
        'accounts.Customer', on_delete=models.CASCADE, related_name='api_cart'
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='api_carts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cart'

    def __str__(self):
        return f'Cart — {self.customer.name}'

    @property
    def item_count(self):
        return self.items.filter(is_deleted=False).count()

    def clear(self):
        self.items.all().delete()


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('menu.Product', on_delete=models.CASCADE)
    qty = models.PositiveIntegerField(default=1)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('cart', 'product')]
        ordering = ['created_at']

    def __str__(self):
        return f'{self.product.name} × {self.qty}'

    @property
    def line_total(self):
        return self.product.price * self.qty
