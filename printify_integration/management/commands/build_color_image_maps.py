"""Build/refresh the persisted colour→image maps for the PDP colour-driven gallery.

Stages (strict priority, see printify_integration/variant_images.py):
  deterministic (payload with --live, else DB variant titles) → heuristics →
  OpenAI vision (ONLY with --apply --openai, only for still-unresolved colours).

Examples:
  python manage.py build_color_image_maps                     # dry-run report
  python manage.py build_color_image_maps --apply             # persist maps
  python manage.py build_color_image_maps --apply --live      # refetch Printify payloads
  python manage.py build_color_image_maps --apply --openai    # + AI last resort
  python manage.py build_color_image_maps --product-id 6 --json
"""
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from store.models import Product, ProductColorImage

from printify_integration.ai_match import classify_image_color
from printify_integration.variant_images import rebuild_color_image_map

AI_CONFIDENCE = 0.6


def _resolve_client():
    """Printify client: admin config first (encrypted token), env fallback, else None."""
    try:
        from printify_integration.models import PrintifyAccountConfig
        from printify_integration.services import client_for_config
        cfg = PrintifyAccountConfig.active()
        if cfg and cfg.get_token() and cfg.shop_id:
            return client_for_config(cfg)
    except Exception:
        pass
    try:
        from printify_integration.services import get_client
        return get_client()
    except Exception:
        return None


class Command(BaseCommand):
    help = ("Rebuild persisted colour->image maps (deterministic > heuristics > "
            "optional OpenAI). Dry-run by default; writing requires --apply.")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Persist the rebuilt maps (default: dry-run rollback)")
        parser.add_argument("--live", action="store_true",
                            help="Refetch product payloads from the Printify API "
                                 "(read-only GETs) for exact deterministic matching")
        parser.add_argument("--openai", action="store_true",
                            help="Classify still-unresolved images with OpenAI vision "
                                 "(requires --apply; persisted, never re-asked)")
        parser.add_argument("--product-id", type=int, default=None)
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--max-ai-calls", type=int, default=20,
                            help="Total OpenAI vision calls budget for this run")
        parser.add_argument("--json", action="store_true", dest="as_json",
                            help="Machine-readable safe output")

    def handle(self, *args, **opts):
        qs = (Product.objects.filter(variation__variation_category="color")
              .distinct().order_by("id"))
        if opts["product_id"]:
            qs = qs.filter(id=opts["product_id"])
        if opts["limit"]:
            qs = qs[:opts["limit"]]

        apply_changes = opts["apply"]
        # in --json mode stdout must stay pure JSON — notices go to stderr
        notify = self.stderr.write if opts["as_json"] else self.stdout.write
        ai_provider = None
        ai_budget = 0
        if opts["openai"]:
            if not apply_changes:
                notify(self.style.NOTICE(
                    "--openai ignored in dry-run: AI calls cost money and results "
                    "could not be persisted. Re-run with --apply."))
            else:
                from assistant.providers import OpenAIProvider
                ai_provider = OpenAIProvider()
                if ai_provider.available():
                    ai_budget = max(0, opts["max_ai_calls"])
                else:
                    ai_provider = None
                    notify(self.style.NOTICE(
                        "OpenAI not configured (no admin key, no AI_API_KEY) — "
                        "skipping the AI stage."))

        client = _resolve_client() if opts["live"] else None
        if opts["live"] and client is None:
            notify(self.style.NOTICE(
                "--live requested but no Printify credentials available — "
                "falling back to DB data."))

        totals = {"products": 0, "colors": 0, "resolved": 0,
                  "ai_calls": 0, "ai_filled": 0, "applied": bool(apply_changes)}
        lines = []

        for product in qs:
            payload = None
            if client is not None and product.printify_product_id:
                try:
                    payload = client.get_product(product.printify_product_id)
                except Exception as exc:
                    notify(self.style.WARNING(
                        f"{product.slug}: payload refetch failed "
                        f"({exc.__class__.__name__}) — using DB data"))
            with transaction.atomic():
                summary = rebuild_color_image_map(product, payload=payload)
                ai_calls = ai_filled = 0
                if ai_provider is not None and ai_budget > 0:
                    ai_calls, ai_filled = self._ai_fill(product, ai_provider, ai_budget)
                    ai_budget -= ai_calls
                    summary["resolved"] += ai_filled
                if not apply_changes:
                    transaction.set_rollback(True)
            totals["products"] += 1
            totals["colors"] += summary["colors"]
            totals["resolved"] += summary["resolved"]
            totals["ai_calls"] += ai_calls
            totals["ai_filled"] += ai_filled
            lines.append({"product": product.slug, **summary,
                          "ai_calls": ai_calls, "ai_filled": ai_filled})

        if opts["as_json"]:
            self.stdout.write(json.dumps({"totals": totals, "products": lines}))
            return
        for line in lines:
            self.stdout.write(
                f"{line['product']}: {line['resolved']}/{line['colors']} colours "
                f"({', '.join(f'{k}={v}' for k, v in line['sources'].items()) or 'none'}"
                f"{', ai=' + str(line['ai_filled']) if line['ai_filled'] else ''})")
        style = self.style.SUCCESS if apply_changes else self.style.NOTICE
        self.stdout.write(style(
            f"{'APPLIED' if apply_changes else 'DRY-RUN (nothing written)'} — "
            f"{totals['resolved']}/{totals['colors']} colours resolved across "
            f"{totals['products']} product(s), {totals['ai_calls']} AI call(s)."))

    def _ai_fill(self, product, provider, budget):
        """Vision-classify images no stage could place, ONLY for unresolved colours.
        Uses the public printify_src URL (local media isn't reachable by OpenAI)."""
        unresolved = list(ProductColorImage.objects.filter(product=product, image_ids="")
                          .exclude(source=ProductColorImage.SOURCE_MANUAL))
        if not unresolved:
            return 0, 0
        colors = [row.color_value for row in unresolved]
        claimed = set()
        for row in ProductColorImage.objects.filter(product=product).exclude(image_ids=""):
            claimed.update(row.image_id_list())
        candidates = [img for img in product.gallery.all()
                      if img.id not in claimed and img.printify_src]
        calls = 0
        by_color = {}
        for img in candidates:
            if calls >= budget:
                break
            calls += 1
            color = classify_image_color(img.printify_src, colors, provider=provider)
            if color in colors:
                by_color.setdefault(color, []).append(img.id)
        filled = 0
        for row in unresolved:
            ids = by_color.get(row.color_value) or []
            if not ids:
                continue
            row.image_ids = ",".join(str(i) for i in ids)
            row.primary_image_id = ids[0]
            row.source = ProductColorImage.SOURCE_OPENAI
            row.confidence = AI_CONFIDENCE
            row.detail = "openai vision classification"
            row.save()
            filled += 1
        return calls, filled
