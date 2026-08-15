"""Named admin roles.

This project's Account model predates `PermissionsMixin`: there are no Django
groups, and `has_perm()` collapses to the single `is_admin` flag. Rather than
retrofit the whole permission system mid-phase, roles are expressed with the
flags that already exist, with one hard rule — **superadmin is never granted
implicitly**. Picking the "Superadmin" role in the invite form still requires an
explicit confirmation checkbox, so nobody is promoted by a dropdown default.
"""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

ROLE_TESTER = "tester"
ROLE_MANAGER = "manager"
ROLE_SUPPORT = "support"
ROLE_SUPERADMIN = "superadmin"

ROLE_CHOICES = [
    (ROLE_TESTER, _("Staff tester")),
    (ROLE_SUPPORT, _("Support agent")),
    (ROLE_MANAGER, _("Store manager")),
    (ROLE_SUPERADMIN, _("Superadmin")),
]

ROLE_DESCRIPTIONS = {
    ROLE_TESTER: _("Can sign in to the admin and look around."),
    ROLE_SUPPORT: _("Handles contact requests, orders and returns."),
    ROLE_MANAGER: _("Runs the catalogue, pricing and merchandising."),
    ROLE_SUPERADMIN: _("Full control, including credentials and other admins."),
}


def role_label(role) -> str:
    return dict(ROLE_CHOICES).get(role, role or "")


def apply_role(user, role, *, grant_superadmin: bool = False, save: bool = True):
    """Set the flags for a role. Superadmin requires `grant_superadmin=True`."""
    user.is_staff = True
    user.is_admin = True
    user.is_superadmin = bool(role == ROLE_SUPERADMIN and grant_superadmin)
    if save and user.pk:
        user.save(update_fields=["is_staff", "is_admin", "is_superadmin"])
    return user


def is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superadmin", False)
                or getattr(user, "is_superuser", False))


def superadmin_count(exclude_pk=None) -> int:
    from .models import Account
    qs = Account.objects.filter(is_superadmin=True, is_active=True)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.count()
