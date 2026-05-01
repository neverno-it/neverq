"""
Run:  python manage.py diagnose_offers
Prints a complete offer health report — every offer, its status,
and a live simulation showing exactly what each customer would pay.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Diagnose offer configuration and simulate cart discounts for real customers'

    def handle(self, *args, **options):
        from apps.menu.models import Offer, OfferUsage
        from apps.core.models import Company
        from apps.accounts.models import Customer
        from apps.menu.views import _resolve_customer_cafe

        W = self.style.WARNING
        E = self.style.ERROR
        S = self.style.SUCCESS
        N = self.style.NOTICE

        self.stdout.write('\n' + '='*65)
        self.stdout.write(N('  NEVERQ OFFER DIAGNOSTIC REPORT'))
        self.stdout.write('='*65 + '\n')

        # ── 1. All offers ─────────────────────────────────────────
        self.stdout.write(N('ALL OFFERS IN DATABASE'))
        self.stdout.write('-'*65)
        all_offers = Offer.objects.select_related('company','cafe','product').order_by('-created_at')
        if not all_offers.exists():
            self.stdout.write(E('  !! NO OFFERS FOUND IN DATABASE !!'))
        for o in all_offers:
            live   = o.is_live
            status = S('✓ LIVE') if live else E('✗ NOT LIVE')
            scope  = S('All customers (no cafe)') if not o.cafe_id else W(f'Cafe-scoped → {o.cafe}')
            self.stdout.write(f'\n  [{o.pk}] "{o.title}"  ({o.offer_type})')
            self.stdout.write(f'    Company   : {o.company.name}')
            self.stdout.write(f'    is_live   : {status}')
            self.stdout.write(f'    is_active : {o.is_active}  |  is_deleted: {o.is_deleted}')
            self.stdout.write(f'    Value     : {o.value}  |  Min Order: {o.min_order_value}  |  Max Disc: {o.max_discount}')
            self.stdout.write(f'    Scope     : {scope}')
            self.stdout.write(f'    Schedule  : {o.start_datetime or "—"} → {o.end_datetime or "no expiry"}')
            if not o.is_active:
                self.stdout.write(E('    !! FIX: is_active is False — activate it in the dashboard'))
            if o.is_deleted:
                self.stdout.write(E('    !! FIX: is_deleted is True — create a new offer'))

        # ── 2. OfferUsage ─────────────────────────────────────────
        self.stdout.write('\n' + '-'*65)
        self.stdout.write(N('OFFER USAGE RECORDS'))
        self.stdout.write('-'*65)
        usages = OfferUsage.objects.select_related('offer','customer').order_by('-used_at')[:10]
        if not usages:
            self.stdout.write(S('  No OfferUsage records.'))
        for u in usages:
            self.stdout.write(f'  [{u.offer_id}] "{u.offer.title}" — {u.customer.email} — {u.used_at:%Y-%m-%d %H:%M}')

        # ── 3. Per-customer simulation ────────────────────────────
        self.stdout.write('\n' + '-'*65)
        self.stdout.write(N('LIVE SIMULATION — recent web customers'))
        self.stdout.write('-'*65)

        from apps.menu.models import Product
        from apps.menu.views import _build_cart_summary
        from decimal import Decimal

        customers = Customer.objects.filter(
            is_active=True, is_deleted=False
        ).exclude(email__contains='kiosk').select_related('company','building').order_by('-created_at')[:5]

        for cust in customers:
            co = cust.company
            resolved_cafe = _resolve_customer_cafe(cust, co)
            self.stdout.write(f'\n  Customer : {cust.name} ({cust.email})')
            self.stdout.write(f'  Building : {cust.building or "none"}')
            self.stdout.write(f'  Resolved cafe: {resolved_cafe or "none (no building or no cafe in building)"}')

            prods = list(Product.objects.filter(
                company=co, is_active=True, is_deleted=False
            ).order_by('-price')[:2])
            if not prods:
                self.stdout.write(W('  No products for this company — skipping'))
                continue

            cart = {str(p.pk): {'qty':1,'price':str(p.price),'name':p.name} for p in prods}
            cart_total = sum(p.price for p in prods)
            self.stdout.write(f'  Cart     : {[(p.name, "₹"+str(p.price)) for p in prods]}  total=₹{cart_total}')

            try:
                summary = _build_cart_summary(cust, cart)
                discount = summary['offer_discount']
                my_pay   = summary['my_pay']
                offer    = summary.get('cart_level_offer')
                if discount > 0:
                    self.stdout.write(S(f'  Result   : ✓ Discount=₹{discount}  You pay=₹{my_pay}  (offer: "{offer.title if offer else "product-level"}")'))
                else:
                    self.stdout.write(W(f'  Result   : No discount applied.  You pay=₹{my_pay}'))
                    # Explain why
                    live_flat = Offer.objects.filter(company=co, is_active=True, is_deleted=False, offer_type__in=['flat','cart'])
                    for o in live_flat:
                        if not o.is_live:
                            self.stdout.write(E(f'    → "{o.title}" not live (check start/end dates)'))
                        elif o.cafe_id and (not resolved_cafe or o.cafe_id != resolved_cafe.pk):
                            self.stdout.write(W(f'    → "{o.title}" scoped to {o.cafe} but customer resolves to {resolved_cafe}'))
                        elif o.min_order_value and cart_total < o.min_order_value:
                            self.stdout.write(W(f'    → "{o.title}" needs ₹{o.min_order_value} min (cart only ₹{cart_total})'))
                        else:
                            self.stdout.write(W(f'    → "{o.title}" exists but not applying — check offer config'))
            except Exception as ex:
                self.stdout.write(E(f'  Error: {ex}'))

        self.stdout.write('\n' + '='*65 + '\n')
