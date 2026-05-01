from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Customer


class Command(BaseCommand):
    help = 'Deactivate active customers who have had no orders for the last 60 days.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show how many customers would be deactivated without saving changes.')

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        now = timezone.now()
        candidates = Customer.objects.filter(is_active=True, is_deleted=False)
        deactivated = 0

        for customer in candidates.iterator():
            if customer.deactivate_if_stale(save=not dry_run):
                deactivated += 1

        mode = 'would be deactivated' if dry_run else 'deactivated'
        self.stdout.write(self.style.SUCCESS(f'{deactivated} customer(s) {mode}. Checked at {now:%Y-%m-%d %H:%M:%S}.'))
