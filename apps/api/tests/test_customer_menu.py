from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Customer
from apps.core.models import Company
from apps.menu.models import Advertise, Category, Offer, Offering, Product


class CustomerMenuApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name="MenuCo", store_status=True)
        self.customer = Customer.objects.create(
            company=self.company,
            name="Menu Customer",
            phone="9999999999",
            email="menu@example.com",
            is_active=True,
            is_approved=True,
            is_email_verified=True,
        )
        self.client.force_authenticate(user=self.customer, token={"user_type": "customer"})

    def test_menu_uses_current_category_and_product_fields(self):
        category = Category.objects.create(
            name="Breakfast",
            slug="breakfast",
            icon_type=Category.ICON_VEG,
            position_order=2,
            is_active=True,
            is_deleted=False,
        )
        category.companies.add(self.company)
        Product.objects.create(
            company=self.company,
            category=category,
            name="Idli",
            slug="idli",
            price=Decimal("40.00"),
            position_order=1,
            is_active=True,
            is_deleted=False,
            featured_in_web=True,
        )
        offering = Offering.objects.create(company=self.company, name="Breakfast Slot", slug="breakfast-slot")
        advert = Advertise.objects.create(
            company=self.company,
            name="Morning Banner",
            status=Advertise.STATUS_APPROVED,
            is_active=True,
        )
        advert.companies.add(self.company)
        Offer.objects.create(
            company=self.company,
            title="Morning Deal",
            offer_type=Offer.TYPE_PERCENT,
            value=Decimal("10.00"),
            is_active=True,
            is_deleted=False,
        )

        response = self.client.get("/api/v1/customer/menu/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["categories"][0]["sort_order"], 2)
        self.assertEqual(response.data["products"][0]["name"], "Idli")
        self.assertEqual(response.data["products"][0]["is_veg"], True)
        self.assertEqual(response.data["products"][0]["is_available"], True)
        self.assertEqual(response.data["featured_products"][0]["name"], "Idli")
        self.assertEqual(response.data["banners"][0]["name"], "Morning Banner")
        self.assertEqual(response.data["offerings"][0]["name"], offering.name)
        self.assertEqual(response.data["offers"][0]["title"], "Morning Deal")
        self.assertEqual(response.data["store_name"], self.company.name)
