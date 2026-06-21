"""Phase 19: order-help support handoff — ownership & privacy."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from orders.models import Order

User = get_user_model()


def _user(email):
    u = User.objects.create_user(email=email, first_name="A", last_name="B",
                                 username=email.split("@")[0], password="pw12345!")
    u.is_active = True
    u.save()
    return u


def _order(user, number):
    return Order.objects.create(user=user, first_name="A", last_name="B", phone="1",
                                email=user.email, address_line_1="x", city="c", state="s",
                                country="US", order_total=20, tax=2, ip="127.0.0.1",
                                is_ordered=True, order_number=number)


class OrderHelpTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.alice = _user("alice@example.com")
        self.bob = _user("bob@example.com")
        self.order_a = _order(self.alice, "AAA111")
        self.order_b = _order(self.bob, "BBB999")

    def test_guest_redirected_to_login(self):
        r = self.c.post(reverse("order_help", args=["AAA111"]))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.url)

    def test_owner_can_request_help(self):
        from notifications.models import SupportMessage
        self.c.force_login(self.alice)
        r = self.c.post(reverse("order_help", args=["AAA111"]),
                        {"topic": "delivery", "note": "where is it?"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(SupportMessage.objects.filter(account=self.alice,
                                                      subject__contains="AAA111").exists())

    def test_user_cannot_help_on_another_users_order(self):
        from notifications.models import SupportMessage
        self.c.force_login(self.alice)
        # Alice tries Bob's order -> 404, no support message about BBB999
        r = self.c.post(reverse("order_help", args=["BBB999"]),
                        {"topic": "delivery", "note": "snoop"})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(SupportMessage.objects.filter(subject__contains="BBB999").exists())

    def test_analytics_event_recorded(self):
        from storefront.models import AnalyticsEvent
        self.c.force_login(self.alice)
        self.c.post(reverse("order_help", args=["AAA111"]), {"topic": "return"})
        self.assertTrue(AnalyticsEvent.objects.filter(name="support_order_help").exists())
