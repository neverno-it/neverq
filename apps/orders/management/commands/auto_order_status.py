"""
Auto Order Status — management command that can be run via cron / task scheduler.

Flow after this patch:
- Auto-cancel orders stuck in PENDING for too long
- Auto-mark CONFIRMED orders as READY once auto_ready_at is reached
- DELIVERED stays manual from cashier/admin

Usage:
    python manage.py auto_order_status
    python manage.py auto_order_status --cancel-after 4
    python manage.py auto_order_status --dry-run
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.orders.models import Order, OrderStatus, OrderStatusChoices, CounterTicket


class Command(BaseCommand):
    help = 'Auto-update order statuses (cancel stale pending, mark confirmed as ready)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cancel-after', type=int, default=4,
            help='Hours after which pending orders are auto-cancelled (default: 4)'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would be changed without actually changing anything'
        )

    def handle(self, *args, **options):
        now = timezone.now()
        cancel_hours = options['cancel_after']
        dry_run = options['dry_run']

        # 1. Auto-cancel stale PENDING orders
        cutoff_cancel = now - timedelta(hours=cancel_hours)
        stale_pending = Order.objects.filter(
            order_status=OrderStatusChoices.PENDING,
            is_deleted=False,
            created_at__lt=cutoff_cancel,
        )
        cancel_count = stale_pending.count()
        if cancel_count:
            self.stdout.write(f'Found {cancel_count} pending orders older than {cancel_hours}h')
            if not dry_run:
                for order in stale_pending:
                    order.order_status = OrderStatusChoices.CANCELLED
                    order.auto_ready_at = None
                    order.save(update_fields=['order_status', 'auto_ready_at', 'updated_at'])
                    OrderStatus.objects.create(
                        order=order,
                        status=OrderStatusChoices.CANCELLED,
                        details=f'Auto-cancelled: pending for over {cancel_hours} hours.',
                        created_at=now,
                    )
                self.stdout.write(self.style.SUCCESS(f'Cancelled {cancel_count} orders.'))
            else:
                self.stdout.write(self.style.WARNING('[DRY RUN] Would cancel these orders.'))

        # 2. Auto-mark CONFIRMED orders as READY
        due_ready = Order.objects.filter(
            order_status=OrderStatusChoices.CONFIRMED,
            is_deleted=False,
            auto_ready_at__isnull=False,
            auto_ready_at__lte=now,
        )
        ready_count = due_ready.count()
        if ready_count:
            self.stdout.write(f'Found {ready_count} confirmed orders ready to move to READY')
            if not dry_run:
                for order in due_ready:
                    order.order_status = OrderStatusChoices.READY
                    order.auto_ready_at = None
                    order.save(update_fields=['order_status', 'auto_ready_at', 'updated_at'])

                    order.counter_tickets.filter(
                        status__in=[CounterTicket.STATUS_PENDING, CounterTicket.STATUS_PREPARING]
                    ).update(status=CounterTicket.STATUS_READY, updated_at=now)

                    OrderStatus.objects.create(
                        order=order,
                        status=OrderStatusChoices.READY,
                        details='Auto-marked ready after configured product preparation time.',
                        created_at=now,
                    )
                self.stdout.write(self.style.SUCCESS(f'Marked {ready_count} orders as ready.'))
            else:
                self.stdout.write(self.style.WARNING('[DRY RUN] Would mark these orders as ready.'))

        if not cancel_count and not ready_count:
            self.stdout.write('No orders to update.')