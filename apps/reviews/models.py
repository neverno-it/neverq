from django.db import models
from django.utils import timezone
from apps.accounts.models import Customer
from apps.orders.models import Order


class Review(models.Model):
    """Customer review / rating (mirrors tbl_review)."""
    customer   = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='reviews')
    order      = models.OneToOneField(Order, on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='review')
    rating     = models.DecimalField(max_digits=2, decimal_places=1, default=5.0)
    details    = models.TextField(blank=True)
    is_active  = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    # FIX #5: allow importer to set historical dates
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Review by {self.customer.name} — {self.rating}★"

    def save(self, *args, **kwargs):
        if not self.created_at:
            self.created_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def stars_range(self):
        return range(1, 6)

    @property
    def rating_int(self):
        return int(self.rating)
