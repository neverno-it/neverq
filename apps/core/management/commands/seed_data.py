"""
Management command: seed_data
Creates a small but realistic NeverQ demo dataset.

Usage:
    python manage.py seed_data
    python manage.py seed_data --flush
"""

from datetime import date, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Seed NeverQ with demo data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Clear supported demo data before re-seeding',
        )

    def handle(self, *args, **options):
        if options['flush']:
            self.stdout.write(self.style.WARNING('Flushing existing data...'))
            self._flush()

        self.stdout.write('Seeding NeverQ demo data...\n')
        refs = self._seed_core()
        self._seed_staff(refs)
        self._seed_menu(refs)
        self._seed_configs(refs)
        self._seed_customers(refs)
        self._seed_coupons(refs)
        self._seed_pages()
        self.stdout.write(self.style.SUCCESS('\nSeed complete! Visit http://127.0.0.1:8000/'))
        self.stdout.write(self.style.SUCCESS('   Admin URL: http://127.0.0.1:8000/auth/login/'))
        self.stdout.write(self.style.SUCCESS('   Admin: admin@neverq.co.in / admin123'))
        self.stdout.write(self.style.SUCCESS('   Customer: customer@linde.com / customer123'))

    def _ok(self, message):
        self.stdout.write(self.style.SUCCESS(f'  [OK] {message}'))

    def _flush(self):
        from apps.accounts.models import Customer, StaffAccess, StaffUser, WalletTransaction, WebCookie
        from apps.core.models import (
            Building,
            City,
            Company,
            Coupon,
            DisplayBoardConfig,
            KioskConfig,
            Location,
            Notification,
            State,
            StaticPage,
            WebViewConfig,
        )
        from apps.menu.models import (
            Advertise,
            Cafe,
            Category,
            Counter,
            FoodType,
            MediaAsset,
            Offer,
            OfferUsage,
            Offering,
            Product,
            ProductCompanyPrice,
            ProductCounter,
            Schedule,
            StockLedger,
        )
        from apps.orders.models import CompanySettlement, CounterTicket, Order, OrderItem, OrderStatus
        from apps.pos.models import POSOrder, POSOrderItem, POSProduct

        models_in_delete_order = [
            Notification,
            OrderStatus,
            CounterTicket,
            OrderItem,
            Order,
            CompanySettlement,
            POSOrderItem,
            POSOrder,
            POSProduct,
            StockLedger,
            ProductCompanyPrice,
            OfferUsage,
            Offer,
            ProductCounter,
            Counter,
            Product,
            Offering,
            Schedule,
            Category,
            Advertise,
            MediaAsset,
            Cafe,
            FoodType,
            WalletTransaction,
            StaffAccess,
            WebCookie,
            Customer,
            StaffUser,
            DisplayBoardConfig,
            WebViewConfig,
            KioskConfig,
            Coupon,
            StaticPage,
            Building,
            City,
            Company,
            Location,
            State,
        ]
        for model in models_in_delete_order:
            model.objects.all().delete()
        self._ok('Existing demo data cleared')

    def _seed_core(self):
        from apps.core.models import Building, City, Company, Location, State

        west_bengal, _ = State.objects.get_or_create(name='WEST BENGAL')
        telangana, _ = State.objects.get_or_create(name='TELANGANA')
        kolkata, _ = City.objects.get_or_create(name='Kolkata', defaults={'state': west_bengal})
        hyderabad, _ = City.objects.get_or_create(name='Hyderabad', defaults={'state': telangana})
        salt_lake, _ = Location.objects.get_or_create(name='Salt Lake')
        hitec, _ = Location.objects.get_or_create(name='HITEC City')

        linde, _ = Company.objects.get_or_create(
            name='Linde India - Kolkata',
            defaults={
                'company_address': '56 Jatin Das Road, Kolkata',
                'company_gst': '19AACCB8581A1ZQ',
                'phone': '9179957983',
                'bill_company': 2,
                'company_meal_amount': Decimal('40.00'),
                'store_status': True,
                'online_payment': True,
                'cod_payment': True,
                'monthly_payment': True,
                'royalty_enabled': True,
                'royalty_points_per_rupee': Decimal('1.00'),
                'royalty_min_redeem': 50,
                'royalty_max_redeem_pct': 50,
                'require_customer_approval': False,
            },
        )
        shyam, _ = Company.objects.get_or_create(
            name='Shyam Metalics',
            defaults={
                'company_address': 'Taratala HO, Kolkata',
                'phone': '8820814091',
                'bill_company': 2,
                'store_status': True,
                'online_payment': True,
                'cod_payment': True,
                'monthly_payment': False,
            },
        )

        canteen, _ = Building.objects.get_or_create(
            company=linde,
            name='Canteen',
            defaults={'state': west_bengal, 'city': kolkata, 'location': salt_lake},
        )
        tower_c, _ = Building.objects.get_or_create(
            company=linde,
            name='Tower C',
            defaults={'state': west_bengal, 'city': kolkata, 'location': salt_lake},
        )
        taratala, _ = Building.objects.get_or_create(
            company=shyam,
            name='Taratala HO',
            defaults={'state': west_bengal, 'city': kolkata, 'location': salt_lake},
        )
        Building.objects.get_or_create(
            company=shyam,
            name='Hyderabad Unit',
            defaults={'state': telangana, 'city': hyderabad, 'location': hitec},
        )

        self._ok('Companies, buildings, states, cities, and locations seeded')
        return {
            'linde': linde,
            'shyam': shyam,
            'canteen': canteen,
            'tower_c': tower_c,
            'taratala': taratala,
        }

    def _seed_staff(self, refs):
        from apps.accounts.models import StaffAccess, StaffUser
        from apps.core.access import get_default_keys

        linde = refs['linde']
        staff_rows = [
            {
                'email': 'admin@neverq.co.in',
                'name': 'Super Admin',
                'role': StaffUser.ROLE_SUPERADMIN,
                'company': None,
                'is_staff': True,
                'is_superuser': True,
            },
            {
                'email': 'manager@linde.com',
                'name': 'Linde Manager',
                'role': StaffUser.ROLE_ADMIN,
                'company': linde,
                'is_staff': True,
                'is_superuser': False,
            },
            {
                'email': 'pos@linde.com',
                'name': 'Linde POS',
                'role': StaffUser.ROLE_POS,
                'company': linde,
                'is_staff': False,
                'is_superuser': False,
            },
            {
                'email': 'chef@linde.com',
                'name': 'Linde Kitchen',
                'role': StaffUser.ROLE_CAFEMAN,
                'company': linde,
                'is_staff': False,
                'is_superuser': False,
            },
            {
                'email': 'reports@linde.com',
                'name': 'Linde Reports',
                'role': StaffUser.ROLE_REPORTS,
                'company': linde,
                'is_staff': False,
                'is_superuser': False,
            },
        ]

        for data in staff_rows:
            email = data.pop('email')
            user, created = StaffUser.objects.get_or_create(email=email, defaults=data)
            if not created:
                for field, value in data.items():
                    setattr(user, field, value)
            user.set_password('admin123')
            user.save()
            access, _ = StaffAccess.objects.get_or_create(user=user)
            if user.role != StaffUser.ROLE_SUPERADMIN and not access.visible_keys:
                access.visible_keys = sorted(get_default_keys(user.role))
                access.save(update_fields=['visible_keys'])

        self._ok('Staff users seeded')

    def _seed_menu(self, refs):
        from apps.core.models import Company
        from apps.menu.models import Cafe, Category, Counter, FoodType, Offer, Offering, Product
        from apps.pos.models import POSProduct

        linde = refs['linde']
        shyam = refs['shyam']
        canteen = refs['canteen']
        taratala = refs['taratala']

        veg, _ = FoodType.objects.get_or_create(name='Veg', defaults={'is_active': True})
        nonveg, _ = FoodType.objects.get_or_create(name='Non-Veg', defaults={'is_active': True})

        mains, _ = Category.objects.get_or_create(
            slug='mains',
            defaults={'name': 'Mains', 'is_active': True, 'position_order': 1},
        )
        snacks, _ = Category.objects.get_or_create(
            slug='snacks',
            defaults={'name': 'Snacks', 'is_active': True, 'position_order': 2},
        )
        combos, _ = Category.objects.get_or_create(
            slug='combos',
            defaults={'name': 'Combos', 'is_active': True, 'position_order': 3},
        )
        for category in (mains, snacks, combos):
            category.companies.add(linde, shyam)

        lunch, _ = Offering.objects.get_or_create(
            company=linde,
            slug='lunch-service',
            defaults={
                'name': 'Lunch Service',
                'available_from': time(12, 0),
                'available_to': time(15, 0),
                'open_days': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
                'position_order': 1,
                'is_active': True,
            },
        )
        snacks_slot, _ = Offering.objects.get_or_create(
            company=linde,
            slug='evening-snacks',
            defaults={
                'name': 'Evening Snacks',
                'available_from': time(16, 0),
                'available_to': time(19, 0),
                'open_days': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
                'position_order': 2,
                'is_active': True,
            },
        )

        main_cafe, _ = Cafe.objects.get_or_create(
            company=linde,
            name='CafeP43',
            defaults={'building': canteen, 'is_active': True},
        )
        shyam_cafe, _ = Cafe.objects.get_or_create(
            company=shyam,
            name='Cafe Aboli',
            defaults={'building': taratala, 'is_active': True},
        )
        hot_counter, _ = Counter.objects.get_or_create(
            company=linde,
            name='Hot Counter',
            defaults={'cafe': main_cafe, 'position_order': 1, 'is_active': True},
        )
        beverage_counter, _ = Counter.objects.get_or_create(
            company=linde,
            name='Beverage Counter',
            defaults={'cafe': main_cafe, 'position_order': 2, 'is_active': True},
        )

        products = [
            {
                'slug': 'veg-thali',
                'name': 'Veg Thali',
                'category': mains,
                'offering': lunch,
                'price': Decimal('95.00'),
                'calories': 620,
                'description': 'Rice, dal, sabzi, roti, and salad.',
                'featured_in_web': True,
                'food_type': veg,
                'counter': hot_counter,
            },
            {
                'slug': 'chicken-meal',
                'name': 'Chicken Meal',
                'category': mains,
                'offering': lunch,
                'price': Decimal('145.00'),
                'calories': 780,
                'description': 'Chicken curry with rice and roti.',
                'featured_in_kiosk_extra': True,
                'food_type': nonveg,
                'counter': hot_counter,
            },
            {
                'slug': 'paneer-combo',
                'name': 'Paneer Combo',
                'category': combos,
                'offering': lunch,
                'price': Decimal('125.00'),
                'calories': 700,
                'description': 'Paneer curry combo meal.',
                'food_type': veg,
                'counter': hot_counter,
            },
            {
                'slug': 'fish-rice-bowl',
                'name': 'Fish Rice Bowl',
                'category': combos,
                'offering': lunch,
                'price': Decimal('155.00'),
                'calories': 760,
                'description': 'Bengali-style fish and rice bowl.',
                'food_type': nonveg,
                'counter': hot_counter,
            },
            {
                'slug': 'samosa-plate',
                'name': 'Samosa Plate',
                'category': snacks,
                'offering': snacks_slot,
                'price': Decimal('35.00'),
                'calories': 260,
                'description': 'Two samosas with chutney.',
                'food_type': veg,
                'counter': beverage_counter,
            },
            {
                'slug': 'cold-coffee',
                'name': 'Cold Coffee',
                'category': snacks,
                'offering': snacks_slot,
                'price': Decimal('55.00'),
                'calories': 190,
                'description': 'Chilled coffee drink.',
                'food_type': veg,
                'counter': beverage_counter,
            },
        ]

        created_products = {}
        for data in products:
            food_type = data.pop('food_type')
            counter = data.pop('counter')
            slug = data['slug']
            product, _ = Product.objects.get_or_create(
                company=linde,
                slug=slug,
                defaults={
                    **data,
                    'is_active': True,
                    'is_kiosk_active': True,
                    'min_qty': 1,
                    'max_qty': 10,
                    'web_qty': -1,
                    'rating': Decimal('4.5'),
                },
            )
            changed = False
            for field, value in data.items():
                if getattr(product, field) != value:
                    setattr(product, field, value)
                    changed = True
            if not product.is_active:
                product.is_active = True
                changed = True
            if not product.is_kiosk_active:
                product.is_kiosk_active = True
                changed = True
            if changed:
                product.save()
            product.food_type.add(food_type)
            product.counters.add(counter)
            created_products[slug] = product

        Offer.objects.update_or_create(
            company=linde,
            title='Lunch Combo Saver',
            defaults={
                'product': created_products['paneer-combo'],
                'offer_type': Offer.TYPE_PERCENT,
                'value': Decimal('15.00'),
                'max_discount': Decimal('40.00'),
                'start_datetime': timezone.now() - timedelta(days=1),
                'end_datetime': timezone.now() + timedelta(days=30),
                'is_popup_enabled': True,
                'is_active': True,
            },
        )
        Offer.objects.update_or_create(
            company=linde,
            title='Flat 30 Above 200',
            defaults={
                'offer_type': Offer.TYPE_FLAT,
                'value': Decimal('30.00'),
                'min_order_value': Decimal('200.00'),
                'start_datetime': timezone.now() - timedelta(days=1),
                'end_datetime': timezone.now() + timedelta(days=30),
                'is_popup_enabled': False,
                'is_active': True,
            },
        )

        for name, price in [
            ('Tea', Decimal('10.00')),
            ('Coffee', Decimal('15.00')),
            ('Samosa', Decimal('15.00')),
            ('Chicken Puff', Decimal('25.00')),
        ]:
            POSProduct.objects.get_or_create(
                company=linde,
                name=name,
                defaults={'price': price, 'is_active': True},
            )

        self._ok('Categories, offerings, cafes, counters, products, offers, and POS items seeded')

    def _seed_configs(self, refs):
        from apps.core.models import DisplayBoardConfig, KioskConfig, WebViewConfig

        linde = refs['linde']
        canteen = refs['canteen']
        KioskConfig.objects.get_or_create(
            company=linde,
            name='Main Entrance Kiosk',
            defaults={'building': canteen, 'show_offerings': True, 'show_categories': True, 'is_active': True},
        )
        WebViewConfig.objects.get_or_create(
            company=linde,
            name='Customer Web View',
            defaults={'building': canteen, 'show_offerings': True, 'show_categories': True, 'is_active': True},
        )
        DisplayBoardConfig.objects.get_or_create(
            company=linde,
            name='Main Display Board',
            defaults={'building': canteen, 'is_active': True},
        )
        self._ok('Kiosk, web, and display-board configs seeded')

    def _seed_customers(self, refs):
        from apps.accounts.models import Customer

        linde = refs['linde']
        canteen = refs['canteen']
        tower_c = refs['tower_c']
        shyam = refs['shyam']
        taratala = refs['taratala']

        customers = [
            {
                'company': linde,
                'building': canteen,
                'name': 'Demo Customer',
                'phone': '9000000001',
                'email': 'customer@linde.com',
                'address': '56 Jatin Das Road, Kolkata',
                'date_of_birth': date(1991, 1, 1),
                'is_active': True,
                'is_approved': True,
                'is_email_verified': True,
                'monthly_payment': True,
                'meal_benefit': Customer.MEAL_BENEFIT_SUBSIDY,
            },
            {
                'company': linde,
                'building': tower_c,
                'name': 'Rahul Sharma',
                'phone': '9000000002',
                'email': 'rahul@linde.com',
                'address': 'Tower C, Kolkata',
                'date_of_birth': date(1990, 5, 12),
                'is_active': True,
                'is_approved': True,
                'is_email_verified': True,
                'meal_benefit': Customer.MEAL_BENEFIT_NONE,
            },
            {
                'company': shyam,
                'building': taratala,
                'name': 'Priya Roy',
                'phone': '9000000003',
                'email': 'priya@shyam.com',
                'address': 'Taratala, Kolkata',
                'date_of_birth': date(1992, 8, 20),
                'is_active': True,
                'is_approved': True,
                'is_email_verified': True,
                'meal_benefit': Customer.MEAL_BENEFIT_NONE,
            },
        ]

        for data in customers:
            email = data['email']
            customer, created = Customer.objects.get_or_create(
                company=data['company'],
                email=email,
                defaults=data,
            )
            if not created:
                for field, value in data.items():
                    setattr(customer, field, value)
            customer.set_password('customer123')
            customer.save()

        self._ok('Customers seeded')

    def _seed_coupons(self, refs):
        from apps.core.models import Coupon

        linde = refs['linde']
        coupons = [
            {
                'code': 'WELCOME10',
                'company': None,
                'discount_type': Coupon.DISCOUNT_TYPE_PERCENT,
                'discount_value': Decimal('10.00'),
                'min_order': Decimal('100.00'),
                'max_discount': Decimal('50.00'),
                'description': '10 percent off your first order.',
            },
            {
                'code': 'LINDE30',
                'company': linde,
                'discount_type': Coupon.DISCOUNT_TYPE_FLAT,
                'discount_value': Decimal('30.00'),
                'min_order': Decimal('200.00'),
                'max_discount': Decimal('0.00'),
                'description': 'Flat 30 off on orders above 200.',
            },
        ]
        for data in coupons:
            Coupon.objects.update_or_create(
                code=data['code'],
                defaults={
                    **data,
                    'valid_from': timezone.now() - timedelta(days=1),
                    'valid_to': timezone.now() + timedelta(days=30),
                    'is_active': True,
                },
            )
        self._ok('Coupons seeded')

    def _seed_pages(self):
        from apps.core.models import StaticPage

        pages = [
            (
                'about-us',
                'About Us',
                '<h3>About NeverQ</h3><p>NeverQ helps offices and campuses run cafeteria ordering without queues.</p>',
            ),
            (
                'terms-and-conditions',
                'Terms & Conditions',
                '<p>Orders are subject to availability and kitchen timing.</p>',
            ),
            (
                'privacy-policy',
                'Privacy Policy',
                '<p>NeverQ stores only the information needed to process cafeteria orders.</p>',
            ),
            (
                'refund-policy',
                'Refund Policy',
                '<p>Refunds are processed for cancelled or failed orders.</p>',
            ),
            (
                'contact-us',
                'Contact Us',
                '<p>Email: support@neverq.in</p><p>Phone: +91 33 4000 0000</p>',
            ),
        ]
        for slug, title, content in pages:
            StaticPage.objects.update_or_create(
                slug=slug,
                defaults={'title': title, 'content': content, 'is_active': True},
            )
        self._ok('Static pages seeded')
