from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"
    verbose_name = "Notifications & n8n"

    def ready(self):
        # Register the support-email configuration guardrails (F5).
        from . import checks  # noqa: F401
