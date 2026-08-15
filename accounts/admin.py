import secrets

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from greatkart.pii import mask_email
from .models import Account, StaffInvite
from .roles import (ROLE_CHOICES, ROLE_DESCRIPTIONS, ROLE_SUPERADMIN, apply_role,
                    is_superadmin, role_label, superadmin_count)

#: how long an invitation link stays usable
INVITE_TTL_HOURS = 72

#: flags that change what a person can DO — superadmin-only, always
PRIVILEGE_FIELDS = ("is_admin", "is_staff", "is_superadmin")


class AccountAdmin(UserAdmin):
    # Masked email in the list (data minimisation); full email still searchable + on detail.
    list_display = ('masked_email', 'first_name', 'last_name', 'username',
                    'role_badge', 'last_login', 'date_joined', 'is_active')
    list_display_links = ('first_name', 'last_name')
    search_fields = ('email', 'first_name', 'last_name', 'username')
    readonly_fields = ('last_login', 'date_joined')
    ordering = ('-date_joined',)

    filter_horizontal = ()
    list_filter = ()
    fieldsets = ()
    change_list_template = "admin/accounts/account/change_list.html"

    @admin.display(description=_("Email"))
    def masked_email(self, obj):
        return mask_email(obj.email)

    @admin.display(description=_("Role"))
    def role_badge(self, obj):
        if obj.is_superadmin:
            colour, label = "#7c3aed", _("Superadmin")
        elif obj.is_staff:
            colour, label = "#2563eb", _("Staff")
        else:
            colour, label = "#94a3b8", _("Customer")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
            'font-size:11px;">{}</span>', colour, label)

    # ---- privilege escalation guards ---------------------------------------- #
    # Before this, any is_admin staffer could open their own record and tick
    # is_superadmin. The switches are now invisible AND unwritable for non-superadmins,
    # and the last superadmin can neither be demoted nor deleted.
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not is_superadmin(request.user):
            for field in PRIVILEGE_FIELDS:
                form.base_fields.pop(field, None)
        return form

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not is_superadmin(request.user):
            ro.extend(f for f in PRIVILEGE_FIELDS if f not in ro)
        return ro

    def save_model(self, request, obj, form, change):
        if not is_superadmin(request.user) and obj.pk:
            # defence in depth: ignore forged POSTs for the privilege flags
            current = Account.objects.filter(pk=obj.pk).first()
            if current is not None:
                for field in PRIVILEGE_FIELDS:
                    setattr(obj, field, getattr(current, field))
        if change and obj.pk:
            previous = Account.objects.filter(pk=obj.pk).first()
            demoting = previous is not None and previous.is_superadmin and not obj.is_superadmin
            deactivating = previous is not None and previous.is_active and not obj.is_active
            unstaffing = previous is not None and previous.is_staff and not obj.is_staff
            if ((demoting or deactivating or unstaffing)
                    and superadmin_count(exclude_pk=obj.pk) == 0):
                obj.is_superadmin = previous.is_superadmin
                obj.is_active = previous.is_active
                obj.is_staff = previous.is_staff
                self.message_user(
                    request,
                    _("This is the last superadmin — keep at least one so you are "
                      "never locked out of the admin."), level=messages.WARNING)
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_superadmin and superadmin_count(exclude_pk=obj.pk) == 0:
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        """Bulk delete must respect the same lock-out guard as a single delete —
        otherwise 'select all → delete' wipes every superadmin at once."""
        protected = [u.pk for u in queryset.filter(is_superadmin=True)]
        if protected and superadmin_count(exclude_pk=None) - len(protected) <= 0:
            keep = protected[0]
            queryset = queryset.exclude(pk=keep)
            self.message_user(
                request,
                _("Kept one superadmin so the admin cannot be locked out."),
                level=messages.WARNING)
        super().delete_queryset(request, queryset)

    def user_change_password(self, request, id, form_url=""):
        """Setting another admin's password is a takeover primitive — superadmin only.

        UserAdmin exposes /<id>/password/ regardless of which fields we hide, so
        without this a plain staffer could set a superadmin's password and sign in
        as them."""
        from django.http import HttpResponseForbidden
        if not is_superadmin(request.user) and str(request.user.pk) != str(id):
            return HttpResponseForbidden("Superadmin only.")
        return super().user_change_password(request, id, form_url)

    # ---- invite flow --------------------------------------------------------- #
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        # same flag name the other control centers use for their superadmin-only CTAs
        extra_context["gl_is_superadmin"] = is_superadmin(request.user)
        return super().changelist_view(request, extra_context)

    def get_urls(self):
        from django.urls import path
        return [
            path("invite/", self.admin_site.admin_view(self.invite_view),
                 name="accounts_account_invite"),
        ] + super().get_urls()

    def invite_view(self, request):
        from django.http import HttpResponseForbidden
        from django.shortcuts import redirect, render

        if not is_superadmin(request.user):
            return HttpResponseForbidden("Superadmin only.")

        context = dict(
            self.admin_site.each_context(request),
            title=_("Invite admin user"),
            roles=[(value, label, ROLE_DESCRIPTIONS.get(value, ""))
                   for value, label in ROLE_CHOICES],
            ttl_hours=INVITE_TTL_HOURS,
            invite_link="", invited_email="", error="",
        )

        if request.method != "POST":
            return render(request, "admin/accounts/account/invite.html", context)

        email = (request.POST.get("email") or "").strip().lower()
        first_name = (request.POST.get("first_name") or "").strip()[:50]
        last_name = (request.POST.get("last_name") or "").strip()[:50]
        role = (request.POST.get("role") or "").strip()
        confirm_superadmin = bool(request.POST.get("confirm_superadmin"))

        if not email or "@" not in email:
            context["error"] = _("Enter a valid email address.")
            return render(request, "admin/accounts/account/invite.html", context)
        if role not in dict(ROLE_CHOICES):
            context["error"] = _("Choose a role.")
            return render(request, "admin/accounts/account/invite.html", context)
        existing = Account.objects.filter(email__iexact=email).first()
        if existing is not None:
            # A pending invite that was never accepted should not block re-inviting:
            # expire the old link and reuse the dormant account instead of dead-ending.
            reusable = (not existing.is_active and not existing.has_usable_password()
                        and not existing.last_login)
            if not reusable:
                context["error"] = _("An account with this email already exists.")
                return render(request, "admin/accounts/account/invite.html", context)
            StaffInvite.objects.filter(account=existing, accepted=False).update(
                expires_at=timezone.now())
            existing.delete()

        username = (email.split("@")[0] or "admin")[:40]
        base, suffix = username, 1
        while Account.objects.filter(username=username).exists():
            suffix += 1
            username = f"{base}{suffix}"[:50]

        user = Account(email=email, username=username,
                       first_name=first_name or username, last_name=last_name)
        # No password is ever generated on our side — the invitee sets their own.
        user.set_unusable_password()
        user.is_active = False
        user.save()
        apply_role(user, role, grant_superadmin=(role == ROLE_SUPERADMIN
                                                 and confirm_superadmin))

        invite = StaffInvite.objects.create(
            account=user, email=email, role=role,
            token=secrets.token_urlsafe(32)[:64],
            created_by=str(request.user)[:150],
            expires_at=timezone.now() + timezone.timedelta(hours=INVITE_TTL_HOURS),
            granted_superadmin=user.is_superadmin,
        )

        from django.urls import reverse
        path = reverse("staff_invite_accept", args=[invite.token])
        context["invite_link"] = request.build_absolute_uri(path)
        context["invited_email"] = email
        context["invited_role"] = role_label(role)

        # The link is deliberately NOT dispatched through the outbox: OutboundEvent
        # payloads are readable in the notifications admin, and this token activates
        # an admin account. The superadmin copies it from here and shares it over a
        # channel they trust.
        context["email_sent"] = False

        self.message_user(request, _("Invitation created for %(email)s.")
                          % {"email": email})
        return render(request, "admin/accounts/account/invite.html", context)


@admin.register(StaffInvite)
class StaffInviteAdmin(admin.ModelAdmin):
    """Audit trail only — invites are created from the Invite page and consumed by
    the invitee; nothing here is editable."""

    list_display = ("email", "role", "created_by", "created_at", "expires_at",
                    "status_badge", "granted_superadmin")
    list_filter = ("role", "accepted", "granted_superadmin")
    search_fields = ("email", "created_by")
    # NEVER expose `token`: it is a single-use credential that activates an admin
    # account. The audit trail shows who/when/what, not the secret itself.
    readonly_fields = [f.name for f in StaffInvite._meta.fields if f.name != "token"]
    exclude = ("token",)
    actions = ["revoke_invites"]

    def has_module_permission(self, request):
        return is_superadmin(request.user)

    def has_view_permission(self, request, obj=None):
        return is_superadmin(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description=_("Revoke selected invitations"))
    def revoke_invites(self, request, queryset):
        """Expire the link now. The pending account is removed too when it was
        never activated, so the same email can be invited again."""
        from django.utils import timezone as tz
        removed = 0
        for invite in queryset.filter(accepted=False):
            invite.expires_at = tz.now()
            invite.save(update_fields=["expires_at"])
            account = invite.account
            if account and not account.is_active and not account.has_usable_password():
                account.delete()
                removed += 1
        self.message_user(request, _("Revoked. %(n)d pending account(s) removed.")
                          % {"n": removed})

    @admin.display(description=_("Status"))
    def status_badge(self, obj):
        if obj.accepted:
            colour, label = "#16a34a", _("Accepted")
        elif obj.is_expired:
            colour, label = "#dc2626", _("Expired")
        else:
            colour, label = "#d97706", _("Pending")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
            'font-size:11px;">{}</span>', colour, label)


admin.site.register(Account, AccountAdmin)
