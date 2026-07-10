"""Colour → gallery-image mapping builder.

Resolves which `ProductImage` rows belong to each colour variation of a product and
persists the result as `store.ProductColorImage` rows (one per product × colour).
The PDP reads ONLY those rows — nothing here runs in the request path.

Matching priority (strict — a later stage never overrides an earlier one):

1. Deterministic / payload — when the Printify product payload is available (at sync
   time, or re-fetched by the management command), `options` + `variants` give the
   EXACT set of variant ids per colour; intersecting with each image's persisted
   `printify_variant_ids` partitions the gallery with no guesswork.
2. Deterministic / colour-row variant ids — a COLOUR Variation row's
   `printify_variant_id` is set at creation from a variant OF THAT COLOUR and never
   rewritten, so it reliably belongs to the colour's variant set (verified on real
   synced data: White→38191 / Dark Heather→63300 match the gallery groups exactly).
3. Local heuristics — colour name embedded in the mockup URL / filename; variant-
   TITLE majority voting (titles are last-write-wins on re-sync — the size row "L"
   ends up carrying the LAST colour's "White / L" while its variant id came from the
   FIRST, so titles are only a weak vote and the whole sub-stage aborts when any
   image group receives votes for two different colours); single-remaining-colour
   elimination. All clearly marked `source="heuristic"` with lower confidence.
   Nothing is invented: an ambiguous colour stays unresolved.

A colour that no stage can resolve keeps an EMPTY row (admin-visible "unresolved");
the storefront falls back to the default gallery for it. The optional OpenAI stage
(management command `build_color_image_maps --openai`) only fills those empty rows.

Precedence on rebuild: `manual` rows are never touched; `openai` rows are replaced
only when a deterministic result is now available (an upgrade), never by heuristics.
"""
from __future__ import annotations

import re

from store.models import ProductColorImage


CONF_DETERMINISTIC = 1.0
CONF_SINGLE_COLOR = 0.85
CONF_FILENAME = 0.75
CONF_TITLE_VOTE = 0.65
CONF_ELIMINATION = 0.7


def _norm(value):
    return (value or "").strip().lower()


def _split_ids(csv):
    return {s.strip() for s in (csv or "").split(",") if s.strip()}


def _color_variant_ids_from_payload(payload):
    """color(lower) -> set of variant ids (as str), from Printify options+variants.
    Includes DISABLED variants on purpose: mockups reference them too."""
    color_titles = {}
    for opt in payload.get("options") or []:
        if _norm(opt.get("type")) != "color":
            continue
        for val in opt.get("values") or []:
            vid, title = val.get("id"), (val.get("title") or "").strip()
            if vid is not None and title:
                color_titles[vid] = title
    out = {}
    for v in payload.get("variants") or []:
        variant_id = str(v.get("id") or "")
        if not variant_id:
            continue
        for oid in v.get("options") or []:
            title = color_titles.get(oid)
            if title:
                out.setdefault(_norm(title), set()).add(variant_id)
    return out


def _title_color(title, colors_lower):
    """Colour encoded in a variant title like 'Black / S' (or 'S / Black').
    Only trusted when exactly ONE '/'-separated part matches a known colour."""
    parts = [_norm(p) for p in (title or "").split("/")]
    matches = [p for p in parts if p in colors_lower]
    return matches[0] if len(matches) == 1 else None


def _color_variant_ids_from_color_rows(variations):
    """color(lower) -> {variant id} from COLOUR rows only. A colour row's
    printify_variant_id is written at creation from a variant OF THAT COLOUR and
    never rewritten — the one (id, colour) pairing in the DB that stays true."""
    out = {}
    for v in variations:
        if v.variation_category != "color":
            continue
        variant_id = (v.printify_variant_id or "").strip()
        color = _norm(v.variation_value)
        if variant_id and color:
            out.setdefault(color, set()).add(variant_id)
    return out


def _color_variant_ids_from_titles(variations, colors_lower):
    """color(lower) -> set of variant ids voted by Variation.printify_title.
    WEAK signal: titles are last-write-wins on (re)sync, so a size row's title can
    belong to a different variant than its id. Contradictory ids (claimed by two
    colours) are dropped here; the caller additionally aborts the whole vote when
    any image group receives votes for two different colours."""
    votes = {}
    for v in variations:
        variant_id = (v.printify_variant_id or "").strip()
        color = _title_color(v.printify_title, colors_lower)
        if variant_id and color:
            votes.setdefault(variant_id, set()).add(color)
    out = {}
    for variant_id, colors in votes.items():
        if len(colors) == 1:              # drop ids with conflicting titles
            out.setdefault(next(iter(colors)), set()).add(variant_id)
    return out


def _filename_color(image, colors_lower):
    """Colour name embedded in the mockup URL or local filename.
    'dark heather' matches 'dark-heather'/'dark_heather'/'darkheather'."""
    haystack = _norm(image.printify_src)
    try:
        if image.image:
            haystack += " " + _norm(image.image.name)
    except Exception:
        pass
    if not haystack:
        return None
    matches = []
    for color in colors_lower:
        pattern = re.escape(color).replace(r"\ ", r"[-_ ]?")
        if re.search(r"(?<![a-z0-9])" + pattern + r"(?![a-z0-9])", haystack):
            matches.append(color)
    # prefer the LONGEST match ('dark heather' wins over a hypothetical 'heather')
    if not matches:
        return None
    matches.sort(key=len, reverse=True)
    if not all(m in matches[0] for m in matches[1:]):
        return None  # any unrelated colour in the same filename -> ambiguous
    return matches[0]


def rebuild_color_image_map(product, payload=None):
    """(Re)build the persisted colour→image map for one product. Idempotent.

    Returns a safe summary dict: {"colors", "resolved", "sources": {source: n}}.
    Raises on unexpected errors — sync-time callers wrap this in try/except."""
    variations = list(product.variation_set.all())
    colors = [v for v in variations if v.variation_category == "color"]
    colors_lower = []
    for v in colors:
        val = _norm(v.variation_value)
        if val and val not in colors_lower:
            colors_lower.append(val)

    if not colors_lower:
        ProductColorImage.objects.filter(product=product).delete()
        return {"colors": 0, "resolved": 0, "sources": {}}

    # gallery order (is_default first, then sort_order) is the display order
    images = list(product.gallery.all())
    image_ids = {img.id: _split_ids(img.printify_variant_ids) for img in images}

    # ---- deterministic colour -> variant-id sets -------------------------------
    if payload:
        known = _color_variant_ids_from_payload(payload)
        det_detail = "payload options/variants"
        # merge colour-row ids as well: gallery variant ids freeze at first sync
        # (_sync_images early-returns) so after provider/variant-id drift only the
        # old ids still intersect the images — without this merge a re-sync would
        # blank previously-correct rows
        for c, ids in _color_variant_ids_from_color_rows(variations).items():
            known.setdefault(c, set()).update(ids)
    else:
        known = _color_variant_ids_from_color_rows(variations)
        det_detail = "colour-row variant ids"

    # ---- match images ----------------------------------------------------------
    specific = {c: [] for c in colors_lower}   # colour -> [image ids] (gallery order)
    shared_by_color = {c: [] for c in colors_lower}
    unassigned = []
    for img in images:
        ids = image_ids[img.id]
        matched = [c for c in colors_lower if known.get(c) and ids & known[c]]
        if len(matched) == 1:
            specific[matched[0]].append(img.id)
        elif len(matched) > 1:
            for c in matched:                  # shared ONLY with the colours the
                shared_by_color[c].append(img.id)   # image's variant ids contain
        else:
            unassigned.append(img.id)

    results = {}   # colour -> (image_ids list, source, confidence, detail)
    for c in colors_lower:
        if specific[c] or shared_by_color[c]:
            results[c] = (specific[c] + shared_by_color[c],
                          ProductColorImage.SOURCE_DETERMINISTIC,
                          CONF_DETERMINISTIC, det_detail)

    # ---- heuristics for colours the deterministic stages left empty -------------
    unresolved = [c for c in colors_lower if c not in results]

    # single-colour product: every image is that colour by definition
    if len(colors_lower) == 1 and unresolved and images:
        c = colors_lower[0]
        results[c] = ([img.id for img in images], ProductColorImage.SOURCE_HEURISTIC,
                      CONF_SINGLE_COLOR, "single-colour product")
        unresolved = []

    # filename / URL match
    if unresolved and unassigned:
        by_color = {}
        for img in images:
            if img.id not in unassigned:
                continue
            c = _filename_color(img, unresolved)
            if c:
                by_color.setdefault(c, []).append(img.id)
        for c, ids in by_color.items():
            results[c] = (ids, ProductColorImage.SOURCE_HEURISTIC,
                          CONF_FILENAME, "filename match")
            unresolved.remove(c)
            unassigned = [i for i in unassigned if i not in ids]

    # variant-title majority vote (weak — titles are last-write-wins on resync)
    if unresolved and unassigned:
        # consistency is checked against votes for ALL colours (not just the
        # unresolved ones): an image voted for a resolved AND an unresolved colour
        # is exactly the scrambled-titles evidence the abort exists for
        votes = _color_variant_ids_from_titles(variations, set(colors_lower))
        if votes:
            assign = {}
            consistent = True
            for img in images:
                if img.id not in unassigned:
                    continue
                matched = [c for c, vids in votes.items() if image_ids[img.id] & vids]
                if len(matched) > 1:      # one mockup voted two colours -> titles
                    consistent = False    # are scrambled; abort the whole vote
                    break
                if matched and matched[0] in unresolved:
                    assign.setdefault(matched[0], []).append(img.id)
            if consistent:
                for c, ids in assign.items():
                    results[c] = (ids, ProductColorImage.SOURCE_HEURISTIC,
                                  CONF_TITLE_VOTE, "variant-title vote")
                    unresolved.remove(c)
                    unassigned = [i for i in unassigned if i not in ids]

    # elimination: exactly one colour left and images no known colour claims
    if len(unresolved) == 1 and unassigned:
        c = unresolved[0]
        results[c] = (list(unassigned), ProductColorImage.SOURCE_HEURISTIC,
                      CONF_ELIMINATION, "elimination (last unmatched colour)")
        unresolved = []
        unassigned = []

    # ---- persist (respecting manual/openai precedence) ---------------------------
    # key existing rows by NORMALIZED colour so a legacy/mixed-case row ("Black")
    # is recognized, not shadowed-then-deleted; on duplicates keep the row whose
    # source carries the strongest precedence and drop the other
    _priority = {ProductColorImage.SOURCE_MANUAL: 3, ProductColorImage.SOURCE_OPENAI: 2}
    existing = {}
    for row in ProductColorImage.objects.filter(product=product):
        key = _norm(row.color_value)
        other = existing.get(key)
        if other is None:
            existing[key] = row
            continue
        keep, drop = ((row, other)
                      if _priority.get(row.source, 1) > _priority.get(other.source, 1)
                      else (other, row))
        drop.delete()
        existing[key] = keep
    image_by_id = {img.id: img for img in images}
    sources = {}
    resolved = 0

    for c in colors_lower:
        ids, source, confidence, detail = results.get(
            c, ([], ProductColorImage.SOURCE_DETERMINISTIC, 0.0, "unresolved"))
        row = existing.get(c)
        if row is not None:
            if row.source == ProductColorImage.SOURCE_MANUAL:
                sources["manual"] = sources.get("manual", 0) + 1
                if row.image_ids:
                    resolved += 1
                continue
            if (row.source == ProductColorImage.SOURCE_OPENAI
                    and not (ids and source == ProductColorImage.SOURCE_DETERMINISTIC)):
                sources["openai"] = sources.get("openai", 0) + 1
                if row.image_ids:
                    resolved += 1
                continue
        primary_id = next((i for i in ids if i in image_by_id), None)
        values = dict(
            image_ids=",".join(str(i) for i in ids),
            primary_image_id=primary_id,
            source=source, confidence=confidence, detail=detail[:200],
        )
        if row is None:
            ProductColorImage.objects.create(product=product, color_value=c, **values)
        else:
            for k, v in values.items():
                setattr(row, k, v)
            row.save()
        if ids:
            resolved += 1
            sources[source] = sources.get(source, 0) + 1

    # drop rows for colours that no longer exist (any source, case-insensitive)
    for row in ProductColorImage.objects.filter(product=product):
        if _norm(row.color_value) not in colors_lower:
            row.delete()

    return {"colors": len(colors_lower), "resolved": resolved, "sources": sources}
