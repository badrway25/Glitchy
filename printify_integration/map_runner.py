"""Shared colour-image mapping runner — ONE engine for CLI and admin.

`manage.py build_color_image_maps` and the admin "Variant image mapping" pages
both call `run_color_image_mapping`, so behaviour, guardrails and reporting can
never drift apart. The runner:

- is dry-run by default (everything computed inside a transaction that is rolled
  back unless `apply=True`);
- refetches Printify payloads only with `source="live"` (read-only GETs through
  the encrypted admin config, env fallback);
- runs the OpenAI vision stage ONLY when `use_openai=True` AND `apply=True`
  (paying for unpersistable dry-run calls would be waste), capped by
  `max_ai_calls`, and never touches `manual` rows;
- records a safe `ProductColorImageMapRun` row (aggregates + per-row summary —
  no tokens, keys, prompts or raw provider payloads, ever);
- never lets one broken product abort the run (status becomes "partial").

Synchronous by design (no queue exists in this project): the admin bounds work
with `product_cap`, scoped selections and the AI budget instead of background
jobs — the same operating model as every other control-center action here.
"""
from __future__ import annotations

import logging
import time

from django.db import transaction
from django.utils import timezone

from store.models import Product, ProductColorImage, ProductColorImageMapRun

from .ai_match import classify_image_color
from .variant_images import rebuild_color_image_map

AI_CONFIDENCE = 0.6
DEFAULT_PRODUCT_CAP = 500

logger = logging.getLogger("printify")


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


def _ai_fill(product, provider, budget):
    """Vision-classify images no stage could place, ONLY for unresolved colours.
    Manual rows are untouchable — an admin pin (even deliberately empty) wins."""
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


def _map_signature(product):
    return {row.color_value: (row.image_ids, row.source)
            for row in ProductColorImage.objects.filter(product=product)}


def _safe_rows(product):
    rows = []
    for row in ProductColorImage.objects.filter(product=product).order_by("color_value"):
        resolved = bool(row.image_ids)
        primary_url = row.primary_image.display_url() if row.primary_image else ""
        rows.append({
            "product_id": product.id,
            "product": product.product_name,
            "product_slug": product.slug,
            "color": row.color_value,
            "source": row.source if resolved or row.source ==
                      ProductColorImage.SOURCE_MANUAL else "unresolved",
            "confidence": row.confidence,
            "images": len(row.image_id_list()),
            "primary_url": primary_url,
            "detail": row.detail,
        })
    return rows


def run_color_image_mapping(*, products=None, apply=False, source="db",
                            use_openai=False, max_ai_calls=20,
                            only_unresolved=False, requested_by="",
                            product_cap=DEFAULT_PRODUCT_CAP, record_run=True):
    """Execute (or simulate) a mapping run. Returns a SAFE structured summary."""
    started = timezone.now()
    t0 = time.monotonic()
    warnings = []

    qs = products
    if qs is None:
        qs = (Product.objects.filter(variation__variation_category="color")
              .distinct().order_by("id"))
    product_list = list(qs)
    if only_unresolved:
        product_list = [p for p in product_list if
                        p.color_image_maps.filter(image_ids="")
                        .exclude(source=ProductColorImage.SOURCE_MANUAL).exists()
                        or not p.color_image_maps.exists()]
    if product_cap and len(product_list) > product_cap:
        warnings.append(f"Scope capped to {product_cap} products "
                        f"({len(product_list) - product_cap} skipped this run).")
        product_list = product_list[:product_cap]

    ai_provider = None
    ai_budget = 0
    if use_openai:
        if not apply:
            warnings.append("OpenAI stage skipped: it requires Apply "
                            "(dry-run results could not be persisted).")
        else:
            from assistant.providers import OpenAIProvider
            provider = OpenAIProvider()
            if provider.available():
                ai_provider = provider
                ai_budget = max(0, int(max_ai_calls or 0))
            else:
                warnings.append("OpenAI not configured (no Assistant key, no "
                                "AI_API_KEY) — AI stage skipped.")

    client = _resolve_client() if source == "live" else None
    if source == "live" and client is None:
        warnings.append("No Printify credentials available — live payload "
                        "refetch skipped, using DB data.")

    totals = {"products_scanned": 0, "products_changed": 0, "colors_resolved": 0,
              "colors_unresolved": 0, "manual_preserved": 0, "openai_calls_used": 0}
    rows = []
    product_lines = []
    failures = 0

    for product in product_list:
        payload = None
        if client is not None and product.printify_product_id:
            try:
                payload = client.get_product(product.printify_product_id)
            except Exception as exc:
                warnings.append(f"{product.slug}: payload refetch failed "
                                f"({exc.__class__.__name__}) — used DB data.")
        try:
            before = _map_signature(product)
            with transaction.atomic():
                summary = rebuild_color_image_map(product, payload=payload)
                ai_calls = ai_filled = 0
                if ai_provider is not None and ai_budget > 0:
                    ai_calls, ai_filled = _ai_fill(product, ai_provider, ai_budget)
                    ai_budget -= ai_calls
                    summary["resolved"] += ai_filled
                after = _map_signature(product)
                product_rows = _safe_rows(product)
                if not apply:
                    transaction.set_rollback(True)
        except Exception as exc:
            failures += 1
            logger.warning("mapping run failed for %s: %s",
                           product.slug, exc.__class__.__name__)
            warnings.append(f"{product.slug}: failed ({exc.__class__.__name__}).")
            continue

        totals["products_scanned"] += 1
        if before != after:
            totals["products_changed"] += 1
        totals["colors_resolved"] += summary["resolved"]
        totals["colors_unresolved"] += summary["colors"] - summary["resolved"]
        totals["manual_preserved"] += sum(
            1 for r in product_rows if r["source"] == ProductColorImage.SOURCE_MANUAL)
        totals["openai_calls_used"] += ai_calls
        rows.extend(product_rows)
        product_lines.append({"product": product.slug, "colors": summary["colors"],
                              "resolved": summary["resolved"],
                              "sources": summary["sources"],
                              "ai_calls": ai_calls, "ai_filled": ai_filled})

    duration_ms = int((time.monotonic() - t0) * 1000)
    status = (ProductColorImageMapRun.STATUS_FAILED if failures and
              not totals["products_scanned"] else
              ProductColorImageMapRun.STATUS_PARTIAL if failures else
              ProductColorImageMapRun.STATUS_SUCCEEDED)

    result = {
        "ok": status != ProductColorImageMapRun.STATUS_FAILED,
        "mode": "apply" if apply else "dry_run",
        "apply": bool(apply),
        "source": "live" if client is not None else "db",
        "use_openai": ai_provider is not None,
        "status": status,
        "warnings": warnings,
        "rows": rows,
        "product_lines": product_lines,
        "duration_ms": duration_ms,
        **totals,
    }

    if record_run:
        # written OUTSIDE the per-product transactions so a dry-run rollback
        # can never swallow its own history row
        run = ProductColorImageMapRun.objects.create(
            created_by=(requested_by or "")[:150],
            mode=result["mode"], source=result["source"],
            use_openai=result["use_openai"], max_ai_calls=int(max_ai_calls or 0),
            only_unresolved=bool(only_unresolved), status=status,
            products_scanned=totals["products_scanned"],
            products_changed=totals["products_changed"],
            colors_resolved=totals["colors_resolved"],
            colors_unresolved=totals["colors_unresolved"],
            manual_preserved=totals["manual_preserved"],
            openai_calls_used=totals["openai_calls_used"],
            duration_ms=duration_ms,
            safe_summary_json={"rows": rows[:400], "warnings": warnings},
            safe_error="" if status != ProductColorImageMapRun.STATUS_FAILED
                       else "all products failed",
            started_at=started, finished_at=timezone.now(),
        )
        result["run_id"] = run.pk
    return result
