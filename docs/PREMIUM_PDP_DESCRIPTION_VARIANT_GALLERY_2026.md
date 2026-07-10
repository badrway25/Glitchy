# Premium PDP Descriptions + Colour-Driven Variant Gallery (2026)

**Branch:** `feat/glitchy-premium-printify-description-variant-gallery` (from `release/staging-printify-fashion-store @ 1598da2`). **One migration** (`store/0015`): `ProductColorImage` model + `Product.printify_description_raw`. No new dependencies.

## 1. What shipped

Two premium upgrades to the Printify product detail page:

1. **Structured premium description** — the long Printify wall of text is re-organized at render time into **Overview** (short intro, clamped at 4 lines with a localized *Read more*), **Highlights** (check-list of feature bullets), **Care instructions** and **More details** (collapsed native `<details>` sections). Nothing is rewritten or invented: every rendered line is verbatim text from the existing sanitized description (or its cached IT/FR translation).
2. **Colour-driven gallery** — selecting a colour instantly crossfades the main image to that colour's primary mockup and narrows the thumbnail rail to that colour's images. Powered by a **persisted** mapping table, never by request-time inference.

## 2. Colour → image mapping (`store.ProductColorImage`)

One row per (product, colour): ordered `image_ids`, `primary_image`, **`source`** (`deterministic` / `heuristic` / `openai` / `manual`), `confidence`, `detail` (short provenance note), `built_at`.

Builder: `printify_integration/variant_images.py::rebuild_color_image_map(product, payload=None)` — strict priority, later stages never override earlier ones:

1. **Deterministic / payload** — at sync time (`services._upsert_product` calls the builder with the Printify product dict) `options`+`variants` give the exact variant-id set per colour, intersected with each image's persisted `ProductImage.printify_variant_ids`. Confidence 1.0.
2. **Deterministic / colour-row variant ids** — without a payload, the reliable DB pairing is the **colour** Variation row's `printify_variant_id` (written at creation from a variant of that colour, never rewritten). Verified on real data (White→38191, Dark Heather→63300 match the two mockup groups exactly).
3. **Heuristics** (`source=heuristic`, lower confidence): single-colour product; colour name embedded in mockup URL/filename; **variant-title majority vote** — deliberately weak because size-row `printify_title` is last-write-wins on re-sync (real data shows the "L" row carrying `White / L` with a Dark-Heather variant id); the vote **aborts entirely** if any image group receives votes for two colours; single-remaining-colour elimination.
4. **OpenAI vision** — see §3. Only fills rows every other stage left empty.

Unresolved colours keep an **empty row** (admin badge "Unresolved"); the storefront falls back to the default gallery for them — no wrong image is ever preferred over no image. `manual` rows are never overwritten by rebuilds; `openai` rows are only replaced when a deterministic result becomes available.

## 3. OpenAI usage (classification only, offline only)

- **Where:** `printify_integration/ai_match.py::classify_image_color(image_url, colours)` called **only** by `manage.py build_color_image_maps --apply --openai`. Never in the request path; never at sync time; the PDP only reads DB rows.
- **What:** vision *classification* — the model must answer with one colour from the product's own list (or UNKNOWN); any other output is discarded. No image generation, no free text persisted.
- **How:** raw `requests` POST to Chat Completions (same pattern as the assistant — no `openai` package), key resolved DB-first (encrypted `AssistantConfig`, `PAYMENT_CONFIG_KEY` secretbox) with `AI_API_KEY` env fallback, `temperature 0`, `max_tokens 12`, `detail:"low"`, one retry, status-codes-only logging (never the key/body). Uses the public `printify_src` mockup URL.
- **Caching / spend control:** results are persisted on `ProductColorImage` (`source=openai`, confidence 0.6) so an image is classified at most once; `--max-ai-calls` budget (default 20/run); `--openai` without `--apply` is ignored (dry-run rolls back, paying for unpersistable calls would be waste).
- **Failure:** missing key / HTTP error / odd answer → `None` → row stays unresolved → elegant deterministic fallback in the UI.

## 4. Sync + raw description

`_upsert_product` now also persists **`printify_description_raw`** (original uncleaned Printify text, capped 8 kB — admin reference only, shown collapsed & read-only in the Product form) and rebuilds the colour map from the payload inside a guarded `try/except` (a mapping failure can never abort a sync; logged as class name only).

## 5. Description structuring

`store/description_display.py::structure_description(text)` — pure, deterministic, language-agnostic parser of the sanitized plain text: recognizes `• ` / `- ` / `.: ` bullets, short heading lines ("Product features", "Care instructions", "Caractéristiques", …) and routes bullets by a small EN/IT/FR keyword map (care vs highlights). Unstructured text ⇒ whole text as Overview with the classic rendering. `store/views.py::product_detail` passes `description_sections`, plus `pdp_gallery` (gallery annotated with per-image colours) and `pdp_color_map` (JSON via `json_script`).

## 6. Frontend

- `templates/store/product_detail.html`: description block rebuilt (overview clamp + highlights + `<details>` sections); thumbs now carry `data-image-id`/`data-colors`, render up to 24 with `loading="lazy"`; `{{ pdp_color_map|json_script:"pdpColorImages" }}` ships the map safely (escaped, no `|safe`). Dead `main_src` `{% with %}` block removed.
- `greatkart/static/js/pdp-premium.js` (new, loaded in `base.html`): observes colour clicks (no coupling with theme.js handler order), preloads then crossfades `#pdpMainImg` (160 ms opacity, no flicker), filters thumbs, syncs the lightbox and active thumb, restores state on back-navigation; unknown colour or empty map ⇒ no-op with full gallery. Also drives the overview *Read more/Show less* toggle.
- `premium.css`: `.pdp-desc-premium`, `.pdp-highlights` (FA5 `fa-check`), `.pdp-details` (uppercase summary + rotating chevron), `.pdp-overview.is-clamped` 4-line clamp, `.pdp-img-swap` fade, `.pdp-thumb-hidden`. Tokens only (`var(--border)` shorthand rule respected) — light/dark follow the theme.
- i18n: 5 strings (*Read more, Show less, Highlights, Care instructions, More details*) translated in `locale/it` + `locale/fr` (fuzzy-matched wrong entries from msgmerge fixed by hand).

## 7. Admin & operations

- **Colour-image maps** changelist (Unfold sidebar → Printify control): provenance badge (green deterministic / amber heuristic / violet openai / slate manual / slate "Unresolved" when empty), image count, primary thumbnail, searchable, filter by source. Editing a row and setting `source=manual` pins it against rebuilds.
- Product admin: read-only **Colour-image map inline**, collapsed **Printify raw description** panel, bulk action **"Rebuild colour-image maps"** (deterministic+heuristics, no network).
- Command: `manage.py build_color_image_maps [--apply] [--live] [--openai] [--product-id N] [--limit N] [--max-ai-calls N] [--json]` — dry-run by default (transaction rollback), `--live` re-fetches payloads through the admin-config client (env fallback) for exact matching, `--json` safe machine output.

## 8. Tests (+72, suite green)

- `printify_integration/test_variant_image_map.py` (26) — every stage, precedence, idempotence, real-data scrambled-title scenarios (colour-row vids win; title vote aborts on contradiction).
- `printify_integration/test_build_color_maps_command.py` (16) — dry-run writes nothing, `--openai` gating/budget/missing-key degradation, `--live` refetch, hallucinated colours discarded, `classify_image_color` fail-safe.
- `printify_integration/tests.py` (+3) — sync builds the map from payload, raw+clean description persisted, resync heals poisoned rows.
- `store/test_description_display.py` (13) — parser forms/keywords EN-IT-FR, "no content invented" token-subset property.
- `store/test_pdp_premium.py` (11) — json_script map, thumb attrs, sections markup, read-more threshold, XSS escape, graceful no-map page.
- `store/test_color_map_admin.py` (3) — changelist badges, bulk rebuild action, raw-description panel.
- Full suite: `env/Scripts/python.exe manage.py test` → **935 tests OK** (was 863).

## 9. QA (real browser, real synced data)

Screenshots in `docs/qa/pdp_premium_gallery/`: default PDP (premium sections visible), Dark Heather selected (main image + all thumbs coherent dark), description expanded with Care open, mobile 375 px (no horizontal overflow), Italian locale (translated sections: "Cura del capo", "Leggi di più"), admin changelist. Verified live on product 6 (26 imgs, 2 mockup colour groups resolved deterministically from DB) and product 7 (single-colour set; unmapped colours fall back cleanly). Zero console errors. Known QA limit: the automation Chrome never paints the site's dark theme (pre-existing, whole-page); dark tokens for the new sections were verified via computed styles.

## 10. Adversarial review (multi-agent) — findings fixed

A 63-agent review (5 lenses × adversarial 2-skeptic verification, several findings reproduced with executed probes) confirmed and led to these fixes: `color_value` normalized on save + case-insensitive rebuild matching (a manual "Black" pin was previously deleted by the cleanup); shared images scoped to the colours their variant ids actually contain; payload matching merged with colour-row ids (variant-id drift no longer blanks correct rows); title-vote consistency checked against ALL colours' votes; `image_id_list` uses `isdecimal` (the repo's known `isdigit` crash gotcha); filename ambiguity guard checks every match; the AI stage excludes `manual` rows; `--json` stdout stays pure JSON (notices→stderr); the crossfade CSS preserves the hover-zoom `transform` transition; a swap generation-counter prevents slow preloads reverting newer colour picks; care keywords match at word starts only ("iron" no longer catches "environmentally"); unknown heading labels are kept in *More details* instead of vanishing; the 6-bullet highlights cap was removed (content was silently dropped); the admin rebuild action logs failures. Each fix is pinned by a regression test.

## 11. Deploy notes

`git pull` → `migrate` (store 0015) → `compilemessages -l it -l fr` → `collectstatic --noinput` → restart. Then one-off backfill: `manage.py build_color_image_maps --apply --live` (uses the encrypted admin token; read-only GETs). Optional for stubborn products: add `--openai` (requires assistant key; ~1 cheap vision call per unresolved image, persisted). Future syncs keep maps fresh automatically.
