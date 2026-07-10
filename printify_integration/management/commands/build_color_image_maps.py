"""Build/refresh the persisted colour→image maps for the PDP colour-driven gallery.

Thin CLI wrapper over printify_integration/map_runner.py — the SAME runner the
admin "Variant image mapping" pages use, so CLI and admin can never drift.

Examples:
  python manage.py build_color_image_maps                     # dry-run report
  python manage.py build_color_image_maps --apply             # persist maps
  python manage.py build_color_image_maps --apply --live      # refetch Printify payloads
  python manage.py build_color_image_maps --apply --openai    # + AI last resort
  python manage.py build_color_image_maps --product-id 6 --json
"""
import json

from django.core.management.base import BaseCommand

from store.models import Product

from printify_integration.map_runner import run_color_image_mapping


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
        parser.add_argument("--only-unresolved", action="store_true",
                            help="Scope to products that still have unresolved colours")
        parser.add_argument("--json", action="store_true", dest="as_json",
                            help="Machine-readable safe output")

    def handle(self, *args, **opts):
        qs = (Product.objects.filter(variation__variation_category="color")
              .distinct().order_by("id"))
        if opts["product_id"]:
            qs = qs.filter(id=opts["product_id"])
        if opts["limit"]:
            qs = qs[:opts["limit"]]

        # in --json mode stdout must stay pure JSON — notices go to stderr
        notify = self.stderr.write if opts["as_json"] else self.stdout.write

        result = run_color_image_mapping(
            products=qs, apply=opts["apply"],
            source="live" if opts["live"] else "db",
            use_openai=opts["openai"], max_ai_calls=opts["max_ai_calls"],
            only_unresolved=opts["only_unresolved"], requested_by="cli",
        )

        for warning in result["warnings"]:
            if "OpenAI stage skipped: it requires Apply" in warning:
                notify(self.style.NOTICE(
                    "--openai ignored in dry-run: AI calls cost money and results "
                    "could not be persisted. Re-run with --apply."))
            elif "OpenAI not configured" in warning:
                notify(self.style.NOTICE(
                    "OpenAI not configured (no admin key, no AI_API_KEY) — "
                    "skipping the AI stage."))
            elif "No Printify credentials" in warning:
                notify(self.style.NOTICE(
                    "--live requested but no Printify credentials available — "
                    "falling back to DB data."))
            else:
                notify(self.style.WARNING(warning))

        totals = {
            "products": result["products_scanned"],
            "colors": result["colors_resolved"] + result["colors_unresolved"],
            "resolved": result["colors_resolved"],
            "ai_calls": result["openai_calls_used"],
            "ai_filled": sum(l["ai_filled"] for l in result["product_lines"]),
            "applied": result["apply"],
        }
        if opts["as_json"]:
            self.stdout.write(json.dumps(
                {"totals": totals, "products": result["product_lines"],
                 "run_id": result.get("run_id")}))
            return
        for line in result["product_lines"]:
            self.stdout.write(
                f"{line['product']}: {line['resolved']}/{line['colors']} colours "
                f"({', '.join(f'{k}={v}' for k, v in line['sources'].items()) or 'none'}"
                f"{', ai=' + str(line['ai_filled']) if line['ai_filled'] else ''})")
        style = self.style.SUCCESS if result["apply"] else self.style.NOTICE
        self.stdout.write(style(
            f"{'APPLIED' if result['apply'] else 'DRY-RUN (nothing written)'} — "
            f"{totals['resolved']}/{totals['colors']} colours resolved across "
            f"{totals['products']} product(s), {totals['ai_calls']} AI call(s)."))
