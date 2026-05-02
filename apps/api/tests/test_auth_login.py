from django.test import TestCase
from rest_framework.test import APIClient
from unittest.mock import patch

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

    @patch("apps.api.views.auth._verify_google_app_id_token")
    def test_google_login_returns_customer_jwt(self, verify_google):
        customer = make_customer(make_company("GoogleCo"), "google@example.com", "unused", name="Google User")
        verify_google.return_value = {"email": customer.email, "name": customer.name}

        response = self.client.post(
            "/api/v1/auth/google/",
            {"id_token": "google-id-token"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["auth_status"], "logged_in")
        self.assertEqual(response.data["user_type"], "customer")
        self.assertEqual(response.data["company_id"], customer.company_id)
        self.assertTrue(response.data["access"])
