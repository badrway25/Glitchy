from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AccountPageSmokeTests(TestCase):
    """Regression smoke tests — would have caught the missing address templates."""

    def setUp(self):
        U = get_user_model()
        self.user = U.objects.create_user(
            first_name="Test", last_name="User", username="testuser",
            email="test@example.com", password="StrongPass!234")
        self.user.is_active = True
        self.user.save()

    def test_public_auth_pages_render(self):
        for name in ["login", "register", "forgotPassword"]:
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 200, f"{name} should render")

    def test_authenticated_account_pages_render(self):
        self.client.force_login(self.user)
        for name in ["dashboard", "my_orders", "transactions",
                     "address_list", "address_create"]:
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 200, f"{name} should render (got {resp.status_code})")

    def test_account_pages_render_in_italian(self):
        """Account pages must render without error under the /it/ prefix."""
        self.client.force_login(self.user)
        resp = self.client.get("/it/accounts/dashboard/")
        self.assertEqual(resp.status_code, 200)
