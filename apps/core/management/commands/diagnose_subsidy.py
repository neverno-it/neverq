"""
Run:  python manage.py diagnose_subsidy

Checks the full subsidy configuration for every company and customer.
Shows exactly why subsidy is or isn't applying.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Diagnose subsidy / meal benefit configuration'

    def handle(self, *args, **options):
        from apps.core.models import Company
        from apps.accounts.models import Customer
        from apps.menu.models import Product
        from apps.menu.views import _build_cart_summary
        from decimal import Decimal

        S = self.style.SUCCESS
        E = self.style.ERROR
        W = self.style.WARNING
        N = self.style.NOTICE

        self.stdout.write('\n' + '='*65)
        self.stdout.write(N('  SUBSIDY DIAGNOSTIC REPORT'))
        self.stdout.write('='*65)

        for company in Company.objects.filter(is_active=True, is_deleted=False).order_by('name'):
            self.stdout.write(f'\n{"─"*65}')
            self.stdout.write(N(f'  COMPANY: {company.name}'))
            self.stdout.write(f'{"─"*65}')

            # ── Company-level config ──────────────────────────────
            if company.bill_company != 2:
                self.stdout.write(E('  bill_company = Employee Pays (1) → subsidy DISABLED for whole company'))
                self.stdout.write(E('  FIX: Go to company settings → set "Billing" to "Bill to Company"'))
            else:
                self.stdout.write(S('  bill_company = Bill to Company (2) ✓'))

            amt = company.company_meal_amount or 0
            if amt <= 0:
                self.stdout.write(W(f'  company_meal_amount = ₹{amt}  ← set this to the subsidy amount per meal'))
            else:
                self.stdout.write(S(f'  company_meal_amount = ₹{amt} ✓'))

            # ── Free meal product restriction ──────────────────────
            free_products = list(company.free_meal_products.filter(is_deleted=False).values('pk', 'name'))
            if not free_products:
                self.stdout.write(S('  free_meal_products = (none) → ALL products in cart qualify for subsidy ✓'))
            else:
                self.stdout.write(W(f'  free_meal_products = {[p["name"] for p in free_products]}'))
                self.stdout.write(W('  → Subsidy ONLY applies to orders containing these products'))

            # ── Customers with benefits ────────────────────────────
            benefited = Customer.objects.filter(
                company=company, is_active=True, is_deleted=False
            ).exclude(meal_benefit='none').select_related('building')

            if not benefited.exists():
                self.stdout.write(W('  No customers have a meal benefit set — everyone pays full price'))
            else:
                self.stdout.write(N(f'  Customers with meal benefit: {benefited.count()}'))

            for cust in benefited:
                override = cust.subsidy_amount_override
                if cust.meal_benefit == 'subsidy':
                    effective_amt = override if override is not None else (company.company_meal_amount or 0)
                    label = f'SUBSIDY ₹{effective_amt}'
                    if override is not None:
                        label += f' (custom override — company default is ₹{company.company_meal_amount})'
                else:
                    label = 'COMPANY PAY (100% free meal)'

                self.stdout.write(f'\n    Customer: {cust.name} ({cust.email})')
                self.stdout.write(f'    Building: {cust.building or "none"}')
                self.stdout.write(f'    Benefit : {label}')

                if company.bill_company != 2:
                    self.stdout.write(E('    ✗ Will NOT apply — company bill_company != 2'))
                    continue

                # Simulate cart
                prods = list(Product.objects.filter(
                    company=company, is_active=True, is_deleted=False
                ).order_by('-price')[:2])
                if not prods:
                    self.stdout.write(W('    Cannot simulate — no products'))
                    continue

                cart = {str(p.pk): {'qty': 1, 'price': str(p.price), 'name': p.name} for p in prods}
                try:
                    summary = _build_cart_summary(cust, cart)
                    sub = summary['subsidy']
                    pay = summary['my_pay']
                    total = summary['total']
                    if sub > 0:
                        self.stdout.write(S(f'    ✓ Subsidy WORKS: cart=₹{total}  subsidy=₹{sub}  customer_pays=₹{pay}'))
                    else:
                        self.stdout.write(E(f'    ✗ Subsidy NOT applying: cart=₹{total}  subsidy=₹{sub}  customer_pays=₹{pay}'))
                        if cust.benefit_used_on():
                            self.stdout.write(E('      Reason: benefit already used today'))
                        elif not free_products:
                            self.stdout.write(E('      Reason: unknown — check meal_benefit and company_meal_amount'))
                        else:
                            eligible_pks = {p['pk'] for p in free_products}
                            cart_pks = {p.pk for p in prods}
                            if not eligible_pks & cart_pks:
                                self.stdout.write(E(f'      Reason: none of the cart products are in free_meal_products'))
                                self.stdout.write(E(f'      Cart has: {[p.name for p in prods]}'))
                                self.stdout.write(E(f'      Eligible: {[p["name"] for p in free_products]}'))
                except Exception as ex:
                    self.stdout.write(E(f'    Error simulating: {ex}'))

        self.stdout.write('\n' + '='*65 + '\n')
