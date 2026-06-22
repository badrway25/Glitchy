"""Report the readiness of every external integration WITHOUT printing any secret.

Each line is a safe status only: OK / MISSING / PLACEHOLDER / DISABLED / TEST_MODE /
NEEDS_ACTION. With --staging, the command exits non-zero if a staging-critical item is
not ready (used as a gate before deploy). Never prints tokens, keys or webhook secrets.

    python manage.py integration_status            # human-readable report
    python manage.py integration_status --staging  # gate: non-zero exit if not ready
"""
from django.conf import settings
from django.core.management.base import BaseCommand

PLACEHOLDER_TOKENS = ("change-me", "your-", "your_", "xxx", "replace", "generate_",
                      "placeholder", "from_the_", "provider_app_password")


def _is_placeholder(v):
    v = (v or "").strip().lower()
    return any(t in v for t in PLACEHOLDER_TOKENS)


def _present(name, default=""):
    return bool(str(getattr(settings, name, default) or "").strip())


class Command(BaseCommand):
    help = "Safe integration readiness report (no secret values printed)."

    def add_arguments(self, parser):
        parser.add_argument("--staging", action="store_true",
                            help="Exit non-zero if a staging-critical item is not ready.")
        parser.add_argument("--json", action="store_true",
                            help="Emit the report as JSON (statuses only, no values).")

    def handle(self, *args, **options):
        S = settings
        checks = []   # (group, item, status, staging_critical)

        def add(group, item, status, critical=False):
            checks.append((group, item, status, critical))

        def kv(name, *, critical=False, placeholder_ok=False):
            v = str(getattr(S, name, "") or "").strip()
            if not v:
                return "MISSING"
            if not placeholder_ok and _is_placeholder(v):
                return "PLACEHOLDER"
            return "OK"

        # --- OpenAI ---
        if getattr(S, "AI_ASSISTANT_ENABLED", False):
            st = kv("AI_API_KEY", critical=True)
            add("OpenAI", "AI_API_KEY", st, True)
            rotated = getattr(S, "OPENAI_KEY_ROTATED", False) or \
                str(getattr(S, "OPENAI_KEY_ROTATED", "")).lower() == "true"
            add("OpenAI", "OPENAI_KEY_ROTATED",
                "OK" if rotated else "NEEDS_ACTION (rotate the exposed key)", True)
        else:
            add("OpenAI", "assistant", "DISABLED")

        # --- Stripe ---
        add("Stripe", "STRIPE_SECRET_KEY", kv("STRIPE_SECRET_KEY", critical=True), True)
        add("Stripe", "STRIPE_PUBLIC_KEY", kv("STRIPE_PUBLIC_KEY", critical=True), True)
        add("Stripe", "STRIPE_WEBHOOK_SECRET", kv("STRIPE_WEBHOOK_SECRET", critical=True), True)
        sk = str(getattr(S, "STRIPE_SECRET_KEY", "") or "")
        add("Stripe", "mode", "TEST_MODE" if sk.startswith("sk_test") else
            ("LIVE" if sk.startswith("sk_live") else "UNKNOWN"))

        # --- PayPal ---
        if getattr(S, "PAYPAL_ENABLED", False):
            ok = _present("PAYPAL_CLIENT_ID") and _present("PAYPAL_SECRET")
            add("PayPal", "server verification", "OK" if ok else "NEEDS_ACTION (client id + secret)")
        else:
            add("PayPal", "status", "DISABLED (safe — fails closed)")

        # --- Printify ---
        add("Printify", "PRINTIFY_API_TOKEN", kv("PRINTIFY_API_TOKEN", critical=True), True)
        add("Printify", "PRINTIFY_SHOP_ID", kv("PRINTIFY_SHOP_ID", critical=True), True)
        if _present("PRINTIFY_API_TOKEN"):
            rotated = bool(getattr(S, "PRINTIFY_KEY_ROTATED", False))
            add("Printify", "PRINTIFY_KEY_ROTATED",
                "OK" if rotated else "NEEDS_ACTION (rotate the exposed token)", True)
        add("Printify", "SHIPPING_USE_PRINTIFY",
            "ON" if getattr(S, "SHIPPING_USE_PRINTIFY", False) else "OFF (fallback rates)")
        add("Printify", "PRINTIFY_PUSH_ENABLED",
            "ENABLED" if getattr(S, "PRINTIFY_PUSH_ENABLED", False) else "DISABLED (dry-run)")

        # --- n8n ---
        if getattr(S, "N8N_ENABLED", False):
            add("n8n", "N8N_WEBHOOK_BASE_URL", kv("N8N_WEBHOOK_BASE_URL"))
            add("n8n", "N8N_HEADER_AUTH_SECRET", kv("N8N_HEADER_AUTH_SECRET"))
        else:
            add("n8n", "status", "DISABLED (SMTP fallback in use)")

        # --- SMTP / email ---
        add("Email", "EMAIL_HOST_USER", kv("EMAIL_HOST_USER"))
        add("Email", "EMAIL_HOST_PASSWORD", kv("EMAIL_HOST_PASSWORD"))
        add("Email", "SMTP fallback", "ON" if getattr(S, "EMAIL_SMTP_FALLBACK", True) else "OFF")

        # --- Database ---
        eng = S.DATABASES["default"]["ENGINE"]
        add("Database", "engine", "Postgres" if "postgresql" in eng else
            ("SQLite (dev only)" if "sqlite" in eng else eng))

        # --- Security ---
        add("Security", "DEBUG", "OFF (prod)" if not S.DEBUG else "ON (dev only)", critical=False)
        add("Security", "ALLOWED_HOSTS", "OK" if S.ALLOWED_HOSTS and S.ALLOWED_HOSTS != ["*"] else "REVIEW")
        add("Security", "CSRF_TRUSTED_ORIGINS",
            "OK" if getattr(S, "CSRF_TRUSTED_ORIGINS", []) else "EMPTY (set for prod domain)")
        add("Security", "SITE_URL", kv("SITE_URL"))

        # --- Render ---
        if options["json"]:
            import json
            payload = [{"group": g, "item": i, "status": s, "critical": c}
                       for g, i, s, c in checks]
            self.stdout.write(json.dumps(payload, indent=2))
            return
        if not options["staging"]:
            cur = None
            for group, item, status, _c in checks:
                if group != cur:
                    self.stdout.write(self.style.MIGRATE_HEADING(f"\n{group}"))
                    cur = group
                self.stdout.write(f"  {item:<24} {status}")
            self.stdout.write("")
            return

        # --staging gate
        not_ready = [(g, i, s) for g, i, s, c in checks if c and not s.startswith(("OK", "TEST_MODE", "LIVE"))]
        for g, i, s in not_ready:
            self.stdout.write(self.style.ERROR(f"NOT READY: {g} / {i} -> {s}"))
        if not_ready:
            self.stderr.write(self.style.ERROR(f"\n{len(not_ready)} staging-critical item(s) not ready."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("All staging-critical integrations are ready."))
