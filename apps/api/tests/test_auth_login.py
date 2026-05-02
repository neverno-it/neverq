from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Customer
from apps.core.models import Company


def make_company(name):
    return Company.objects.create(name=name, store_status=True)


def make_customer(company, email, password, name="Customer"):
    customer = Customer.objects.create(
        company=company,
        name=name,
        phone="9999999999",
        email=email,
        is_active=True,
        is_approved=True,
        is_email_verified=True,
    )
    customer.set_password(password)
    customer.save()
    return customer


class LoginApiCustomerTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_duplicate_customer_email_can_login_matching_account(self):
        email = "same@example.com"
        make_customer(make_company("FirstCo"), email, "wrong-pass", name="First")
        matching = make_customer(make_company("SecondCo"), email, "correct-pass", name="Second")

        response = self.client.post(
            "/api/v1/auth/login/",
            {"email": email, "password": "correct-pass", "user_type": "customer"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user_type"], "customer")
        self.assertEqual(response.data["role"], "customer")
        self.assertEqual(response.data["company_id"], matching.company_id)
        self.assertTrue(response.data["access"])
        self.assertTrue(response.data["refresh"])

    def test_duplicate_customer_email_wrong_password_returns_401(self):
        email = "same@example.com"
        make_customer(make_company("FirstCo"), email, "first-pass", name="First")
        make_customer(make_company("SecondCo"), email, "second-pass", name="Second")

        response = self.client.post(
            "/api/v1/auth/login/",
            {"email": email, "password": "wrong-pass", "user_type": "customer"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["detail"], "Invalid email or password.")
