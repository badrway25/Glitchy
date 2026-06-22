"""P1: PII masking helpers + admin column factories."""
from django.test import TestCase
from greatkart.pii import (mask_email, mask_phone, mask_name, mask_address,
                           mask_tracking, mask_token, mask_text)


class PiiHelperTests(TestCase):
    def test_mask_email_hides_local_and_domain(self):
        m = mask_email("john.doe@example.com")
        self.assertTrue(m.startswith("j"))
        self.assertIn("@", m)
        self.assertIn(".com", m)
        self.assertNotIn("john.doe", m)
        self.assertNotIn("example", m)

    def test_mask_email_empty_and_malformed(self):
        self.assertEqual(mask_email(""), "")
        self.assertNotIn("notanemail", mask_email("notanemail"))

    def test_mask_phone_keeps_last_four(self):
        m = mask_phone("+39 123 456 789")
        self.assertTrue(m.endswith("6789"))
        self.assertNotIn("123", m)

    def test_mask_name(self):
        self.assertEqual(mask_name("John", "Doe"), "John D.")
        self.assertEqual(mask_name("John"), "John")

    def test_mask_address_no_street(self):
        m = mask_address(city="Rome", state="RM", country="IT", postal_code="00100")
        self.assertIn("Rome", m)
        self.assertNotIn("Street", m)

    def test_mask_tracking(self):
        m = mask_tracking("TRK-DEMO-9988")
        self.assertTrue(m.startswith("TRK"))
        self.assertTrue(m.endswith("988"))
        self.assertNotIn("DEMO", m)

    def test_mask_token_and_text(self):
        self.assertTrue(mask_token("a1b2c3d4e5").startswith("a1b2"))
        self.assertNotIn("e5", mask_token("a1b2c3d4e5"))
        self.assertTrue(mask_text("x" * 100).endswith("…"))


class AdminColumnTests(TestCase):
    def test_admin_lists_do_not_render_raw_email(self):
        # OrderAdmin list_display uses masked_email, not raw email.
        from orders.admin import OrderAdmin
        self.assertIn("masked_email", OrderAdmin.list_display)
        self.assertNotIn("email", OrderAdmin.list_display)

    def test_masked_email_column_factory(self):
        from greatkart.admin_pii import masked_email_column
        col = masked_email_column("recipient_email")

        class Obj:
            recipient_email = "secret@example.com"
        # bound-method style: pass a dummy self
        out = col(None, Obj())
        self.assertNotIn("secret", out)
        self.assertIn("@", out)
