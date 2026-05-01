"""
Run:  python manage.py create_flat_offer

Creates a FLAT offer for every active company:
  - No cafe restriction (applies to ALL customers site-wide)
  - No start/end date (always live)
  - ₹20 off on orders above ₹80

Edit the values below before running if you want different amounts.
"""
from django.core.management.base import BaseCommand


DISCOUNT_AMOUNT  = 20    # ₹20 off
MIN_ORDER_VALUE  = 80    # on orders above ₹80
OFFER_TITLE      = '₹20 off on orders above ₹80'


class Command(BaseCommand):
    help = 'Create a working FLAT offer with no cafe restriction'

    def handle(self, *args, **options):
        from apps.core.models import Company
        from apps.menu.models import Offer
        from decimal import Decimal

        S = self.style.SUCCESS
        E = self.style.ERROR
        N = self.style.NOTICE

        self.stdout.write(N('\nCreating FLAT offer for all active companies...\n'))

        companies = Company.objects.filter(is_active=True, is_deleted=False)
        for co in companies:
            # Check if a valid offer already exists (no cafe, active, flat)
            existing = Offer.objects.filter(
                company=co,
                offer_type='flat',
                is_active=True,
                is_deleted=False,
                cafe__isnull=True,
            ).first()

            if existing:
                self.stdout.write(f'  [{co.name}] Already has a FLAT offer: "{existing.title}" — skipping')
                continue

            offer = Offer.objects.create(
                company=co,
                title=OFFER_TITLE,
                offer_type='flat',
                value=Decimal(str(DISCOUNT_AMOUNT)),
                min_order_value=Decimal(str(MIN_ORDER_VALUE)),
                cafe=None,          # ← NO CAFE — works for ALL customers
                product=None,
                is_active=True,
                is_deleted=False,
                start_datetime=None,   # ← NO EXPIRY
                end_datetime=None,
            )
            self.stdout.write(S(f'  [{co.name}] ✓ Created offer [{offer.pk}]: "{offer.title}"'))

        self.stdout.write('\n')

        # Verify it will work
        self.stdout.write(N('Verifying offer will apply...\n'))
        from apps.accounts.models import Customer
        from apps.menu.models import Product
        from apps.menu.views import _build_cart_summary
        from decimal import Decimal

        for co in companies:
            offer = Offer.objects.filter(company=co, offer_type='flat', is_active=True, is_deleted=False, cafe__isnull=True).first()
            if not offer:
                continue

            cust = Customer.objects.filter(company=co, is_active=True, is_deleted=False).exclude(email__contains='kiosk').first()
            if not cust:
                continue

            prods = list(Product.objects.filter(company=co, is_active=True, is_deleted=False).order_by('-price')[:2])
            if not prods:
                continue

            cart = {str(p.pk): {'qty': 1, 'price': str(p.price), 'name': p.name} for p in prods}
            cart_total = sum(p.price for p in prods)

            try:
                summary = _build_cart_summary(cust, cart)
                discount = summary['offer_discount']
                my_pay   = summary['my_pay']

                if discount > 0:
                    self.stdout.write(S(
                        f'  [{co.name}] ✓ OFFER WORKS! '
                        f'Cart=₹{cart_total} → Discount=₹{discount} → You pay=₹{my_pay}'
                    ))
                elif cart_total < offer.min_order_value:
                    self.stdout.write(self.style.WARNING(
                        f'  [{co.name}] Cart ₹{cart_total} < min ₹{offer.min_order_value} — add more items to trigger'
                    ))
                else:
                    self.stdout.write(E(f'  [{co.name}] ✗ Offer not applying — cart={cart_total}, check offer config'))
            except Exception as ex:
                self.stdout.write(E(f'  [{co.name}] Error: {ex}'))

        self.stdout.write(N('\nDone. Go to your cart and refresh — the offer will apply automatically.\n'))
