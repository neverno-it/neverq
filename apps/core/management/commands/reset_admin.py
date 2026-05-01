"""
Management command: reset_admin
Sets working Django passwords on all imported staff users.

Usage:
    python manage.py reset_admin
    python manage.py reset_admin --password MyPass99
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Reset all staff user passwords after SQL import'

    def add_arguments(self, parser):
        parser.add_argument(
            '--password', type=str, default='admin123',
            help='New password for all staff users (default: admin123)',
        )

    def handle(self, *args, **options):
        from apps.accounts.models import StaffUser
        password = options['password']
        staff    = StaffUser.objects.all()

        if not staff.exists():
            self.stdout.write(self.style.ERROR(
                'No staff users found. Run import_sql_data first.'
            ))
            return

        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Resetting Staff Passwords ===\n'))

        for user in staff:
            user.set_password(password)
            user.save()
            self.stdout.write(
                f'  ✓  {user.email:<42} [{user.get_role_display()}]'
            )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done — {staff.count()} users updated. Password: {password}'
        ))
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=== Staff Login URLs ==='))
        self.stdout.write('')
        self.stdout.write('  Dashboard / Chef / Cashier:')
        self.stdout.write('    http://127.0.0.1:8000/auth/login/')
        self.stdout.write('')
        self.stdout.write('  Customer portal:')
        self.stdout.write('    http://127.0.0.1:8000/auth/customer/login/')
        self.stdout.write('')

        ROLE_LABELS = {
            'superadmin': '👑 Super Admin',
            'admin':      '🏢 Company Admin',
            'cafeman':    '👨‍🍳 Chef',
            'pos':        '💳 Cashier/POS',
        }
        for role_key, role_label in ROLE_LABELS.items():
            users = StaffUser.objects.filter(role=role_key)
            if users.exists():
                self.stdout.write(f'  {role_label}')
                for u in users:
                    co = f'  [{u.company.name}]' if u.company else ''
                    self.stdout.write(f'    {u.email}{co}')
                self.stdout.write('')
