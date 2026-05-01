"""
Management command: award_royalty_leaderboard

Usage:
    python manage.py award_royalty_leaderboard
    python manage.py award_royalty_leaderboard --period 2025-01
    python manage.py award_royalty_leaderboard --company 3
    python manage.py award_royalty_leaderboard --dry-run
"""
from django.core.management.base import BaseCommand
from apps.core.models import Company
from apps.core.royalty_service import award_leaderboard_bonuses


class Command(BaseCommand):
    help = 'Award leaderboard bonus royalty points to top customers per period.'

    def add_arguments(self, parser):
        parser.add_argument('--period', type=str, default=None,
            help='Period key e.g. 2025-01 (monthly), 2025-W03 (weekly), 2025-01-15 (daily)')
        parser.add_argument('--company', type=int, default=None,
            help='Only process this company ID')
        parser.add_argument('--dry-run', action='store_true',
            help='Show what would be awarded without writing')

    def handle(self, *args, **options):
        dry = options['dry_run']
        companies = Company.objects.filter(is_active=True, is_deleted=False, royalty_enabled=True)
        if options['company']:
            companies = companies.filter(pk=options['company'])

        for co in companies:
            results = award_leaderboard_bonuses(co, options['period'], dry_run=dry)
            if not results:
                self.stdout.write(f'{co.name}: no eligible customers or royalty disabled.')
                continue
            for r in results:
                flag = '[DRY RUN] ' if dry else ''
                self.stdout.write(
                    f"{flag}{co.name} | Period={options['period'] or 'current'} "
                    f"| Rank #{r['rank']} → {r['customer'].name} "
                    f"({r['points']} pts) [{r['status']}]"
                )
