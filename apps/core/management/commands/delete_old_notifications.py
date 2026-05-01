from django.core.management.base import BaseCommand
from apps.core.models import Notification


class Command(BaseCommand):
    help = 'Delete all notifications older than today (runs nightly at midnight)'

    def handle(self, *args, **options):
        from django.utils import timezone
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(hours=24)
        deleted, _ = Notification.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f'Deleted {deleted} notifications older than today.')
