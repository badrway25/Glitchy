"""Single resolver for operational email settings — admin DB config preferred,
server env/settings as fallback.

Every place that used to read ``settings.SUPPORT_EMAIL`` / ``ADMIN_NOTIFY_EMAIL`` /
``DEFAULT_FROM_EMAIL`` or the raw ``EMAIL_HOST*`` transport now goes through here,
so the addresses and the SMTP transport can be managed from the admin Mail Control
Center. When no config row exists, or it is disabled, this returns exactly the env
values — installing the model changes nothing until a superadmin fills it in.

Nothing here ever returns a decrypted secret to a template or a log; the SMTP
password is only decrypted inside ``get_email_backend_settings`` / ``send_test_email``
at the moment of building a connection.
"""
from __future__ import annotations

from django.conf import settings


def _clean(value) -> str:
    return (value or "").strip()


def get_email_configuration():
    """The singleton EmailConfiguration, or None (missing table / DB error → env)."""
    try:
        from .models import EmailConfiguration
        return EmailConfiguration.objects.filter(
            pk=EmailConfiguration.SINGLETON_PK).first()
    except Exception:
        return None


def _active():
    """The config only when it exists AND is enabled; else None (→ env fallback)."""
    cfg = get_email_configuration()
    return cfg if (cfg and cfg.is_enabled) else None


# --- addresses -------------------------------------------------------------- #
def get_support_email() -> str:
    cfg = _active()
    if cfg and cfg.support_email:
        return _clean(cfg.support_email)
    return _clean(getattr(settings, "SUPPORT_EMAIL", ""))


def get_public_support_email() -> str:
    """Support address only when it is a REAL (non-placeholder) address, else ''.

    This is what customer-facing code shows; the empty string means 'fall back to
    the /contact/ form' (F5)."""
    from greatkart.support_email import is_placeholder_email
    email = get_support_email()
    return "" if is_placeholder_email(email) else email


def get_admin_notify_email() -> str:
    """Recipient for contact-form / internal alerts. Mirrors the old fallback:
    ADMIN_NOTIFY_EMAIL, else the support address."""
    cfg = _active()
    if cfg and cfg.admin_notify_email:
        return _clean(cfg.admin_notify_email)
    env = _clean(getattr(settings, "ADMIN_NOTIFY_EMAIL", ""))
    return env or get_support_email()


def get_default_from_email():
    """From: for outbound mail. None → let Django use its own DEFAULT_FROM_EMAIL."""
    cfg = _active()
    if cfg and cfg.default_from_email:
        return _clean(cfg.default_from_email)
    return _clean(getattr(settings, "DEFAULT_FROM_EMAIL", "")) or None


def get_reply_to_email() -> str:
    cfg = _active()
    return _clean(cfg.reply_to_email) if cfg else ""


def is_email_configured() -> bool:
    """True when a real support address AND a usable send channel are configured."""
    from greatkart.support_email import is_placeholder_email
    if is_placeholder_email(get_support_email()):
        return False
    cfg = _active()
    if cfg:
        if cfg.provider == cfg.PROVIDER_SMTP:
            return bool(_clean(cfg.smtp_host))
        if cfg.provider in (cfg.PROVIDER_N8N, cfg.PROVIDER_CONSOLE):
            return True
        return False                       # disabled
    # env: an n8n webhook or an SMTP user counts as a usable channel
    return bool(_clean(getattr(settings, "N8N_WEBHOOK_BASE_URL", ""))
                or _clean(getattr(settings, "EMAIL_HOST_USER", "")))


# --- SMTP transport --------------------------------------------------------- #
def get_email_backend_settings() -> dict:
    """kwargs for ``django.core.mail.get_connection`` — or ``{}`` to use the default
    connection (``settings.EMAIL_BACKEND``).

    Returns explicit kwargs ONLY when an enabled DB config selects SMTP (with a host)
    or the console backend. Otherwise ``{}`` so existing behaviour — and tests that
    override ``EMAIL_BACKEND`` — are preserved untouched.
    """
    cfg = _active()
    if not cfg:
        return {}
    if cfg.provider == cfg.PROVIDER_CONSOLE:
        return {"backend": "django.core.mail.backends.console.EmailBackend"}
    if cfg.provider == cfg.PROVIDER_SMTP and _clean(cfg.smtp_host):
        return {
            "backend": "django.core.mail.backends.smtp.EmailBackend",
            "host": _clean(cfg.smtp_host),
            "port": int(cfg.smtp_port or 587),
            "username": _clean(cfg.smtp_username),
            "password": cfg.get_secret("smtp_password"),
            "use_tls": bool(cfg.smtp_use_tls),
            "use_ssl": bool(cfg.smtp_use_ssl),
        }
    return {}


def get_connection(**overrides):
    """Build a mail connection from the resolved backend settings (+ any overrides)."""
    from django.core.mail import get_connection as dj_get_connection
    kwargs = get_email_backend_settings()
    kwargs.update({k: v for k, v in overrides.items() if v is not None})
    return dj_get_connection(**kwargs)


# --- n8n mail override (optional) ------------------------------------------- #
def get_n8n_mail_settings() -> dict:
    """Resolved n8n mail webhook + secret. DB override when n8n_mail_enabled, else
    the server env. The secret is decrypted here only for the outbound request."""
    cfg = _active()
    if cfg and cfg.n8n_mail_enabled and _clean(cfg.n8n_webhook_url):
        return {
            "base_url": _clean(cfg.n8n_webhook_url),
            "shared_secret": cfg.get_secret("n8n_secret"),
        }
    return {
        "base_url": _clean(getattr(settings, "N8N_WEBHOOK_BASE_URL", "")),
        "shared_secret": _clean(getattr(settings, "N8N_SHARED_SECRET", "")),
    }


# --- controlled test send --------------------------------------------------- #
def send_test_email(config, recipient, requested_by="") -> dict:
    """Send ONE test email using ``config``'s transport. Returns a safe result dict
    ``{ok, status, detail, error}`` and records it on the row.

    Superadmin gating + rate limiting are enforced by the admin view (as with the
    payment/printify control centers) — this function assumes it may act. It never
    returns or logs the SMTP password.
    """
    from django.core.mail import EmailMessage
    from django.utils import timezone

    recipient = _clean(recipient)
    result = {"ok": False, "status": "failed", "detail": "", "error": ""}
    if not recipient or "@" not in recipient:
        result["error"] = "A valid recipient address is required."
    elif config.provider == config.PROVIDER_DISABLED:
        result["error"] = "Sending is disabled in this configuration."
    elif config.provider == config.PROVIDER_N8N:
        # We do not fire a real automation from a test button; n8n delivery is
        # exercised by a genuine event. Report clearly instead of pretending.
        result["status"] = "skipped"
        result["detail"] = "n8n provider — verified by a real event, not a test send."
        result["ok"] = True
    else:
        try:
            kwargs = {}
            if config.provider == config.PROVIDER_CONSOLE:
                kwargs = {"backend": "django.core.mail.backends.console.EmailBackend"}
            elif config.provider == config.PROVIDER_SMTP and _clean(config.smtp_host):
                kwargs = {
                    "backend": "django.core.mail.backends.smtp.EmailBackend",
                    "host": _clean(config.smtp_host),
                    "port": int(config.smtp_port or 587),
                    "username": _clean(config.smtp_username),
                    "password": config.get_secret("smtp_password"),
                    "use_tls": bool(config.smtp_use_tls),
                    "use_ssl": bool(config.smtp_use_ssl),
                }
            else:
                raise ValueError("SMTP host is not set.")
            from django.core.mail import get_connection as dj_get_connection
            conn = dj_get_connection(**kwargs)
            from_email = (_clean(config.default_from_email)
                          or _clean(config.support_email) or None)
            msg = EmailMessage(
                subject="Glitchy — test email",
                body=("This is a test email from the Glitchy Mail Control Center. "
                      "If you received it, outbound email is configured correctly."),
                from_email=from_email, to=[recipient], connection=conn,
            )
            reply_to = _clean(config.reply_to_email)
            if reply_to:
                msg.reply_to = [reply_to]
            sent = msg.send(fail_silently=False)
            result["ok"] = bool(sent)
            result["status"] = "connected" if sent else "failed"
            result["detail"] = f"Sent 1 test message to {recipient}."
        except Exception as exc:            # never leak the password in the message
            result["error"] = _safe_error(str(exc))

    config.last_test_status = result["status"]
    config.last_test_at = timezone.now()
    config.last_test_detail_safe = result["detail"][:300]
    config.last_test_error_safe = result["error"][:250]
    if requested_by:
        config.updated_by = str(requested_by)[:150]
    config.save(update_fields=["last_test_status", "last_test_at",
                               "last_test_detail_safe", "last_test_error_safe",
                               "updated_by", "updated_at"])
    return result


def _safe_error(message: str) -> str:
    """Trim an exception message and strip anything that looks like a credential."""
    msg = (message or "").strip()
    for marker in ("password", "secret", "auth", "AUTH"):
        idx = msg.lower().find(marker)
        if idx != -1:
            msg = msg[:idx].rstrip() + " …"
            break
    return msg[:250]
