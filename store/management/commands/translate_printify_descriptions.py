"""Translate (and cache) product descriptions into the site's non-English locales.

SAFETY:
- Dry-run is the DEFAULT. Real OpenAI calls + DB writes require --apply.
- When no OpenAI key is configured the command exits cleanly with "missing key"
  (no stacktrace, no API call) — it never blocks or fabricates content.
- Output is safe: counts + masked product ids only; never the API key, the prompt,
  or raw provider output.

Examples:
  manage.py translate_printify_descriptions                       # dry-run, it+fr, all
  manage.py translate_printify_descriptions --apply --language it # write IT for all
  manage.py translate_printify_descriptions --product-id 12 --apply --all-languages
  manage.py translate_printify_descriptions --json
"""
import json

from django.core.management.base import BaseCommand

from store.models import Product
from assistant import translation


class Command(BaseCommand):
    help = ("Translate product descriptions into IT/FR via OpenAI and cache them "
            "(hash-invalidated). Dry-run by default; --apply writes.")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Actually call OpenAI and write translations (default: dry-run).")
        parser.add_argument("--language", choices=list(translation.SUPPORTED_TARGET_LANGS),
                            help="Limit to one target language (it|fr).")
        parser.add_argument("--all-languages", action="store_true",
                            help="Process all supported target languages (default).")
        parser.add_argument("--product-id", type=int, default=None,
                            help="Limit to a single product id.")
        parser.add_argument("--limit", type=int, default=None,
                            help="Process at most N products.")
        parser.add_argument("--force", action="store_true",
                            help="Re-translate even if a fresh cached translation exists.")
        parser.add_argument("--json", action="store_true",
                            help="Emit a machine-readable JSON summary.")

    def handle(self, *args, **opts):
        dry_run = not opts["apply"]
        force = opts["force"]
        langs = ([opts["language"]] if opts["language"]
                 else list(translation.SUPPORTED_TARGET_LANGS))

        # Guard: applying without a usable key is a no-op (don't burn time / fail ugly).
        if not dry_run and not translation.translation_available():
            msg = "missing key: AI_API_KEY not configured — nothing translated."
            if opts["json"]:
                self.stdout.write(json.dumps({"ok": False, "reason": "missing_key",
                                              "applied": False}))
            else:
                self.stdout.write(self.style.WARNING(msg))
            return

        qs = Product.objects.exclude(description="").order_by("id")
        if opts["product_id"]:
            qs = qs.filter(id=opts["product_id"])
        if opts["limit"]:
            qs = qs[: opts["limit"]]

        stats = {"examined": 0, "translated": 0, "cached": 0, "would_translate": 0,
                 "failed": 0, "skipped": 0, "by_language": {lang: 0 for lang in langs},
                 "errors": {}}
        rows = []

        for product in qs:
            stats["examined"] += 1
            for lang in langs:
                res = translation.ensure_product_translation(
                    product, lang, force=force, apply=opts["apply"])
                action = res["action"]
                if action == "translated":
                    stats["translated"] += 1
                    stats["by_language"][lang] += 1
                elif action == "cached":
                    stats["cached"] += 1
                elif action == "would_translate":
                    stats["would_translate"] += 1
                elif action == "failed":
                    stats["failed"] += 1
                    code = res.get("error", "error")
                    stats["errors"][code] = stats["errors"].get(code, 0) + 1
                else:
                    stats["skipped"] += 1
                rows.append({"product_id": product.id, "language": lang,
                             "action": action, "status": res["status"]})

        mode = "DRY-RUN (no API calls / no writes)" if dry_run else "APPLIED"

        if opts["json"]:
            self.stdout.write(json.dumps({
                "ok": True, "mode": mode, "applied": opts["apply"],
                "languages": langs, "stats": stats, "rows": rows,
            }))
            return

        self.stdout.write(self.style.SUCCESS(
            f"[{mode}] products_examined={stats['examined']} "
            f"translated={stats['translated']} cached={stats['cached']} "
            f"would_translate={stats['would_translate']} failed={stats['failed']} "
            f"skipped={stats['skipped']}"))
        for lang in langs:
            self.stdout.write(f"  {lang}: wrote {stats['by_language'][lang]}")
        if stats["failed"]:
            self.stdout.write(self.style.WARNING(
                f"failures by code: {stats['errors']} "
                f"(existing good translations were preserved as fallback)"))
        if dry_run:
            self.stdout.write(self.style.NOTICE(
                "Dry-run only. Re-run with --apply to call OpenAI and write translations."))
