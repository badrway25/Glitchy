"""Creating a second admin safely, and closing a privilege-escalation hole.

Two things are tested here:

1. **The invite flow** — a superadmin invites a colleague by email and role; the
   account is created inactive with an unusable password and a single-use, expiring
   token; the invitee sets their own password. No password is ever generated,
   displayed, emailed or logged by us.
2. **The escalation fix** — before this phase any `is_admin` staffer could open
   /admin/accounts/account/ and tick `is_superadmin` (on themselves or anyone).
   Those switches are now superadmin-only, and the last superadmin cannot be
   demoted or deleted.
"""
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Account, StaffInvite
from accounts.roles import ROLE_SUPERADMIN, ROLE_SUPPORT, apply_role

ADMIN_USERS = "/admin/accounts/account/"
INVITE_URL = "/admin/accounts/account/invite/"


def _superadmin(email="root@x.com"):
    return Account.objects.create_superuser("Root", "Admin", email, email.split("@")[0],
                                            "pw-Str0ng!123")


def _staffer(email="staff@x.com"):
    user = Account.objects.create_user("St", "Aff", email.split("@")[0], email,
                                       "pw-Str0ng!123")
    user.is_active = True
    user.is_staff = True
    user.is_admin = True
    user.is_superadmin = False
    user.save()
    return user


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class InvitePermissionTests(TestCase):
    def test_anonymous_redirected(self):
        self.assertEqual(self.client.get(INVITE_URL).status_code, 302)

    def test_plain_staff_forbidden(self):
        self.client.force_login(_staffer())
        self.assertEqual(self.client.get(INVITE_URL).status_code, 403)

    def test_superadmin_sees_form(self):
        self.client.force_login(_superadmin())
        resp = self.client.get(INVITE_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invite admin user")

    def test_plain_staff_cannot_post_an_invite(self):
        self.client.force_login(_staffer())
        resp = self.client.post(INVITE_URL, {"email": "new@x.com", "first_name": "N",
                                             "last_name": "U", "role": ROLE_SUPPORT})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(StaffInvite.objects.exists())


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class InviteCreationTests(TestCase):
    def setUp(self):
        self.root = _superadmin()
        self.client.force_login(self.root)

    def _invite(self, **extra):
        data = {"email": "tester@x.com", "first_name": "Test", "last_name": "Admin",
                "role": ROLE_SUPPORT}
        data.update(extra)
        return self.client.post(INVITE_URL, data, follow=True)

    def test_creates_inactive_account_with_unusable_password(self):
        self._invite()
        user = Account.objects.get(email="tester@x.com")
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superadmin)

    def test_records_audit_trail(self):
        self._invite()
        invite = StaffInvite.objects.get()
        self.assertEqual(invite.created_by, str(self.root))
        self.assertEqual(invite.role, ROLE_SUPPORT)
        self.assertIsNotNone(invite.expires_at)
        self.assertFalse(invite.accepted)

    def test_shows_the_link_once_to_the_superadmin(self):
        resp = self._invite()
        self.assertContains(resp, "/accounts/staff-invite/")

    def test_never_renders_a_password(self):
        resp = self._invite()
        body = resp.content.decode().lower()
        for needle in ("password:", "temporary password", "pw-str0ng"):
            self.assertNotIn(needle, body)

    def test_duplicate_email_is_refused(self):
        self._invite()
        resp = self._invite()
        self.assertContains(resp, "already")
        self.assertEqual(Account.objects.filter(email="tester@x.com").count(), 1)

    def test_superadmin_role_requires_explicit_confirmation(self):
        self._invite(email="boss@x.com", role=ROLE_SUPERADMIN)
        user = Account.objects.get(email="boss@x.com")
        self.assertFalse(user.is_superadmin)      # not granted without the checkbox

    def test_superadmin_role_granted_with_confirmation(self):
        self._invite(email="boss2@x.com", role=ROLE_SUPERADMIN, confirm_superadmin="1")
        user = Account.objects.get(email="boss2@x.com")
        self.assertTrue(user.is_superadmin)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class InviteAcceptanceTests(TestCase):
    def setUp(self):
        self.root = _superadmin()
        self.client.force_login(self.root)
        self.client.post(INVITE_URL, {"email": "tester@x.com", "first_name": "T",
                                      "last_name": "A", "role": ROLE_SUPPORT})
        self.invite = StaffInvite.objects.get()
        self.client.logout()

    def _url(self, token=None):
        return reverse("staff_invite_accept", args=[token or self.invite.token])

    def test_valid_token_shows_password_form(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "password")

    def test_setting_a_password_activates_the_account(self):
        resp = self.client.post(self._url(), {"new_password1": "Str0ng-Passw0rd!x",
                                              "new_password2": "Str0ng-Passw0rd!x"},
                                follow=True)
        self.assertEqual(resp.status_code, 200)
        user = Account.objects.get(email="tester@x.com")
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("Str0ng-Passw0rd!x"))
        self.invite.refresh_from_db()
        self.assertTrue(self.invite.accepted)

    def test_new_admin_can_log_into_admin(self):
        self.client.post(self._url(), {"new_password1": "Str0ng-Passw0rd!x",
                                       "new_password2": "Str0ng-Passw0rd!x"})
        self.assertTrue(self.client.login(email="tester@x.com",
                                          password="Str0ng-Passw0rd!x"))
        self.assertEqual(self.client.get(ADMIN_USERS).status_code, 200)

    def test_token_is_single_use(self):
        self.client.post(self._url(), {"new_password1": "Str0ng-Passw0rd!x",
                                       "new_password2": "Str0ng-Passw0rd!x"})
        resp = self.client.get(self._url(), follow=True)
        self.assertContains(resp, "no longer valid")

    def test_expired_token_refused(self):
        self.invite.expires_at = timezone.now() - timezone.timedelta(hours=1)
        self.invite.save(update_fields=["expires_at"])
        resp = self.client.get(self._url(), follow=True)
        self.assertContains(resp, "no longer valid")
        Account.objects.get(email="tester@x.com")   # account still inactive, not deleted

    def test_unknown_token_refused(self):
        resp = self.client.get(self._url("deadbeef" * 4), follow=True)
        self.assertContains(resp, "no longer valid")

    def test_mismatched_passwords_rejected(self):
        self.client.post(self._url(), {"new_password1": "Str0ng-Passw0rd!x",
                                       "new_password2": "Different!x9"})
        self.assertFalse(Account.objects.get(email="tester@x.com").is_active)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class PrivilegeEscalationTests(TestCase):
    """Regression: a plain staffer could previously tick is_superadmin on themselves."""

    def setUp(self):
        self.root = _superadmin()
        self.staffer = _staffer()

    def test_staff_cannot_see_privilege_switches(self):
        self.client.force_login(self.staffer)
        resp = self.client.get(f"{ADMIN_USERS}{self.staffer.pk}/change/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'name="is_superadmin"')
        self.assertNotContains(resp, 'name="is_staff"')

    def test_staff_post_cannot_grant_itself_superadmin(self):
        self.client.force_login(self.staffer)
        self.client.post(f"{ADMIN_USERS}{self.staffer.pk}/change/", {
            "first_name": "St", "last_name": "Aff", "username": self.staffer.username,
            "email": self.staffer.email, "phone_number": "",
            "is_superadmin": "on", "is_staff": "on", "is_admin": "on", "is_active": "on",
        })
        self.staffer.refresh_from_db()
        self.assertFalse(self.staffer.is_superadmin)

    def test_superadmin_still_sees_the_switches(self):
        self.client.force_login(self.root)
        resp = self.client.get(f"{ADMIN_USERS}{self.staffer.pk}/change/")
        self.assertContains(resp, 'name="is_superadmin"')

    def test_last_superadmin_cannot_be_demoted(self):
        self.client.force_login(self.root)
        self.client.post(f"{ADMIN_USERS}{self.root.pk}/change/", {
            "first_name": "Root", "last_name": "Admin", "username": self.root.username,
            "email": self.root.email, "phone_number": "", "is_active": "on",
            "is_staff": "on", "is_admin": "on",     # is_superadmin unticked
        })
        self.root.refresh_from_db()
        self.assertTrue(self.root.is_superadmin)

    def test_last_superadmin_cannot_be_deleted(self):
        self.client.force_login(self.root)
        self.client.post(f"{ADMIN_USERS}{self.root.pk}/delete/", {"post": "yes"})
        self.assertTrue(Account.objects.filter(pk=self.root.pk).exists())


class RoleTests(TestCase):
    def test_roles_grant_staff_but_not_superadmin_by_default(self):
        user = Account.objects.create_user("R", "T", "roled", "roled@x.com", "pw-x1!Aa")
        apply_role(user, ROLE_SUPPORT)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_admin)
        self.assertFalse(user.is_superadmin)

    def test_superadmin_role_needs_explicit_grant(self):
        user = Account.objects.create_user("R", "T", "roled2", "roled2@x.com", "pw-x1!Aa")
        apply_role(user, ROLE_SUPERADMIN)
        self.assertFalse(user.is_superadmin)
        apply_role(user, ROLE_SUPERADMIN, grant_superadmin=True)
        self.assertTrue(user.is_superadmin)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class ReviewHardeningTests(TestCase):
    """Regressions found by the adversarial review of this phase."""

    def setUp(self):
        self.root = _superadmin()
        self.staffer = _staffer()

    def test_staff_cannot_change_another_users_password(self):
        """UserAdmin exposes /<id>/password/ regardless of the fields we hide —
        setting a superadmin's password would be a full takeover."""
        self.client.force_login(self.staffer)
        resp = self.client.get(f"{ADMIN_USERS}{self.root.pk}/password/")
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post(f"{ADMIN_USERS}{self.root.pk}/password/",
                                {"password1": "Hijacked-2026!x",
                                 "password2": "Hijacked-2026!x"})
        self.assertEqual(resp.status_code, 403)
        self.root.refresh_from_db()
        self.assertFalse(self.root.check_password("Hijacked-2026!x"))

    def test_superadmin_can_still_change_passwords(self):
        self.client.force_login(self.root)
        self.assertEqual(
            self.client.get(f"{ADMIN_USERS}{self.staffer.pk}/password/").status_code, 200)

    def test_bulk_delete_cannot_wipe_every_superadmin(self):
        second = _superadmin("root2@x.com")
        self.client.force_login(self.root)
        self.client.post(ADMIN_USERS, {
            "action": "delete_selected", "post": "yes",
            "_selected_action": [str(self.root.pk), str(second.pk)],
        }, follow=True)
        self.assertGreaterEqual(
            Account.objects.filter(is_superadmin=True, is_active=True).count(), 1)

    def test_last_superadmin_cannot_be_unstaffed(self):
        self.client.force_login(self.root)
        self.client.post(f"{ADMIN_USERS}{self.root.pk}/change/", {
            "first_name": "Root", "last_name": "Admin", "username": self.root.username,
            "email": self.root.email, "phone_number": "",
            "is_active": "on", "is_superadmin": "on", "is_admin": "on",  # is_staff off
        })
        self.root.refresh_from_db()
        self.assertTrue(self.root.is_staff)

    def test_invite_token_is_never_rendered_in_the_invite_admin(self):
        self.client.force_login(self.root)
        self.client.post(INVITE_URL, {"email": "leak@x.com", "first_name": "L",
                                      "last_name": "K", "role": ROLE_SUPPORT})
        invite = StaffInvite.objects.get()
        resp = self.client.get("/admin/accounts/staffinvite/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, invite.token)
        detail = self.client.get(f"/admin/accounts/staffinvite/{invite.pk}/change/",
                                 follow=True)
        self.assertNotContains(detail, invite.token)

    def test_invite_admin_is_superadmin_only(self):
        self.client.force_login(self.staffer)
        resp = self.client.get("/admin/accounts/staffinvite/")
        self.assertIn(resp.status_code, (302, 403))

    def test_invite_token_is_not_stored_in_the_outbox(self):
        """OutboundEvent payloads are readable in the notifications admin."""
        from notifications.models import OutboundEvent
        self.client.force_login(self.root)
        self.client.post(INVITE_URL, {"email": "nooutbox@x.com", "first_name": "N",
                                      "last_name": "O", "role": ROLE_SUPPORT})
        token = StaffInvite.objects.get().token
        for event in OutboundEvent.objects.all():
            self.assertNotIn(token, str(event.payload))

    def test_revoking_an_invite_frees_the_email(self):
        self.client.force_login(self.root)
        self.client.post(INVITE_URL, {"email": "again@x.com", "first_name": "A",
                                      "last_name": "G", "role": ROLE_SUPPORT})
        invite = StaffInvite.objects.get()
        self.client.post("/admin/accounts/staffinvite/", {
            "action": "revoke_invites", "_selected_action": [str(invite.pk)],
        }, follow=True)
        self.assertFalse(Account.objects.filter(email="again@x.com").exists())
        resp = self.client.post(INVITE_URL, {"email": "again@x.com", "first_name": "A",
                                             "last_name": "G", "role": ROLE_SUPPORT},
                                follow=True)
        self.assertContains(resp, "/accounts/staff-invite/")
