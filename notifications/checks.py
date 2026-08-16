"""Deploy guardrail (F5): warn — never block — when the effective support /
notification email addresses are still placeholders.

The addresses now resolve from the admin Mail Control Center first, then the server
env. This check evaluates the RESOLVED values, so once a superadmin fills in the
config the warnings clear even if the env is still unset. These are Warnings (`W`),
so `manage.py check` still passes; the *names* are reported, never the values.
"""
from django.core.checks import Warning, register

SUPPORT_EMAIL_ID = "glitchy.support.W001"
NOTIFY_EMAIL_ID = "glitchy.support.W002"


@register()
def support_email_configuration(app_configs, **kwargs):
    from greatkart.support_email import is_placeholder_email
    from notifications.email_settings import (get_admin_notify_email,
                                             get_support_email)

    issues = []
    if is_placeholder_email(get_support_email()):
        issues.append(Warning(
            "Support email is not configured (placeholder example.com address).",
            hint="Set it in the admin Mail Control Center (Notifications → Email "
                 "configuration) or SUPPORT_EMAIL in the server env. Until then the "
                 "assistant routes shoppers to the /contact/ form and no support "
                 "address is shown to customers.",
            id=SUPPORT_EMAIL_ID,
        ))
    # Contact-form notifications fall back to the support address when no explicit
    # admin-notify address exists; warn only when the effective recipient is a
    # placeholder (neither the Mail Control Center nor the env provides a real one).
    if is_placeholder_email(get_admin_notify_email()):
        issues.append(Warning(
            "Contact-form notifications have no real recipient.",
            hint="Set the admin-notify (or support) address in the Mail Control "
                 "Center, or ADMIN_NOTIFY_EMAIL / SUPPORT_EMAIL in the env, so "
                 "submitted contact requests reach a monitored inbox.",
            id=NOTIFY_EMAIL_ID,
        ))
    return issues
