"""Variant thumbnail resolver — the single backend authority for line images.

Every surface that renders a cart/order line thumbnail (cart, checkout review,
payments page, order complete, account order detail, admin, add-to-cart modal
JSON) resolves the image through here instead of reaching for the live
`Product.images` hero. Priority:

1. snapshot saved on the line (`selected_image` FK) — survives catalogue edits;
   validated to still belong to the line's product (a foreign/poisoned snapshot
   is ignored, never rendered);
2. `ProductColorImage` mapping for the selected colour (primary image, else the
   first listed image that still exists);
3. product main image, else first gallery image (`display_url` handles the
   local-file-or-printify_src fallback);
4. '' — the template renders the static placeholder.

Colour lookup is normalized (lowercase + EN/IT/FR synonym map) so an Italian or
French variation value still reaches the English mapping rows. We never guess:
an unknown or unmapped colour simply falls through to the product fallback.
"""
from __future__ import annotations

# IT/FR (and common EN spelling variants) -> the canonical colour key used by
# ProductColorImage rows (Printify colours are English)
_COLOR_SYNONYMS = {
    "nero": "black", "noir": "black",
    "bianco": "white", "blanc": "white",
    "blu": "blue", "bleu": "blue",
    "rosso": "red", "rouge": "red",
    "verde": "green", "vert": "green",
    "grigio": "grey", "gris": "grey", "gray": "grey",
    "giallo": "yellow", "jaune": "yellow",
    "rosa": "pink", "rose": "pink",
    "viola": "purple", "violet": "purple",
    "arancione": "orange", "marrone": "brown", "marron": "brown",
    "beige": "beige", "azzurro": "light blue",
}


def normalize_color(value):
    """Lowercased, trimmed colour key; IT/FR synonyms mapped to the EN canonical."""
    low = (str(value) if value is not None else "").strip().lower()
    return _COLOR_SYNONYMS.get(low, low)


def _raw_color_from(selected_options, variations):
    if selected_options:
        for key, value in selected_options.items():
            if str(key).strip().lower() in ("color", "colour"):
                return (str(value) if value is not None else "").strip().lower()
    for v in variations or []:
        if getattr(v, "variation_category", "") == "color":
            return (getattr(v, "variation_value", "") or "").strip().lower()
    return ""


def resolve_variant_image(product, selected_options=None, variations=None):
    """ProductImage for the selected colour, or None when no reliable mapping
    exists. Never returns an image belonging to a different product."""
    raw = _raw_color_from(selected_options, variations)
    if not product or not raw:
        return None
    # mapping rows store the RAW lowercased variation value ('blu'), so try that
    # first; the synonym-normalized key ('blue') is the cross-language fallback
    candidates = [raw]
    normalized = normalize_color(raw)
    if normalized != raw:
        candidates.append(normalized)
    row = None
    try:
        for color in candidates:
            row = product.color_image_maps.filter(color_value=color).first()
            if row is not None:
                break
    except Exception:
        return None
    if row is None:
        return None
    candidates = []
    if row.primary_image_id:
        candidates.append(row.primary_image_id)
    candidates.extend(i for i in row.image_id_list() if i not in candidates)
    for image_id in candidates:
        img = product.gallery.filter(id=image_id).first()   # product-scoped: a
        if img is not None:                                  # foreign id is skipped
            return img
    return None


def product_fallback_image_url(product):
    """Best product-level image URL: main upload, else first gallery image."""
    if product is None:
        return ""
    if getattr(product, "images", None):
        try:
            return product.images.url
        except Exception:
            pass
    try:
        for img in product.gallery.all():
            url = img.display_url()
            if url:
                return url
    except Exception:
        pass
    return ""


def _line_image_url(line):
    """Shared resolution for CartItem/OrderProduct (both expose product,
    variations M2M and a nullable selected_image FK)."""
    snapshot = getattr(line, "selected_image", None)
    if snapshot is not None and snapshot.product_id == line.product_id:
        url = snapshot.display_url()
        if url:
            return url
    img = resolve_variant_image(line.product, variations=line.variations.all())
    if img is not None:
        url = img.display_url()
        if url:
            return url
    return product_fallback_image_url(line.product)


def resolve_cart_item_image(cart_item):
    return _line_image_url(cart_item)


def resolve_order_item_image(order_item):
    return _line_image_url(order_item)
