from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.orders.models import Order, OrderStatusChoices


@receiver(post_save, sender=Order)
def order_status_changed(sender, instance, created, **kwargs):
    if created:
        return
    update_fields = kwargs.get('update_fields') or []
    if 'order_status' not in (update_fields or []):
        return
    from apps.api.fcm import notify_customer_order_ready, notify_customer_order_status
    if instance.order_status == OrderStatusChoices.READY:
        notify_customer_order_ready(instance)
    elif instance.order_status in (
        OrderStatusChoices.CONFIRMED,
        OrderStatusChoices.PREPARING,
        OrderStatusChoices.DELIVERED,
    ):
        notify_customer_order_status(instance)
