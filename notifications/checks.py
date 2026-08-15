"""Deploy guardrail (F5): warn — never block — when the support/notification email
addresses are still placeholders.

An unset production env leaves SUPPORT_EMAIL at `support@example.com` and
ADMIN_NOTIFY_EMAIL empty, which means the assistant would quote a dead address and
contact-form notifications would go nowhere. These are Warnings (`W`), so `manage.py
check` still passes; they simply make the missing configuration impossible to miss.
The setting *names* are reported, never their values.
"""
from django.conf import settings
from django.core.checks import Warning, register

SUPPORT_EMAIL_ID = "glitchy.support.W001"
NOTIFY_EMAIL_ID = "glitchy.support.W002"


@register()
def support_email_configuration(app_configs, **kwargs):
    from greatkart.support_email import is_placeholder_email

    issues = []
    if is_placeholder_email(getattr(settings, "SUPPORT_EMAIL", "")):
        issues.append(Warning(
            "SUPPORT_EMAIL is not configured (placeholder example.com address).",
            hint="Set SUPPORT_EMAIL in the server environment. Until then the "
                 "assistant routes shoppers to the /contact/ form and no support "
                 "address is shown to customers.",
            id=SUPPORT_EMAIL_ID,
        ))
    notify = (getattr(settings, "ADMIN_NOTIFY_EMAIL", "") or "").strip()
    support = (getattr(settings, "SUPPORT_EMAIL", "") or "").strip()
    # Contact-form notifications fall back to SUPPORT_EMAIL when ADMIN_NOTIFY_EMAIL
    # is empty; warn only when BOTH would leave the alert without a real inbox.
    if not notify and is_placeholder_email(support):
        issues.append(Warning(
            "Contact-form notifications have no real recipient "
            "(ADMIN_NOTIFY_EMAIL empty and SUPPORT_EMAIL is a placeholder).",
            hint="Set ADMIN_NOTIFY_EMAIL (or a real SUPPORT_EMAIL) so submitted "
                 "contact requests reach a monitored inbox.",
            id=NOTIFY_EMAIL_ID,
        ))
    return issues
