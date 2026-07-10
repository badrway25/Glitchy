# Admin Colour-Image Mapping Control (2026)

**Branch:** `fix/glitchy-add-to-cart-modal-variant-thumbnail-flow`. **One additive migration** (`store/0016`): `ProductColorImageMapRun` (safe run history). No new dependencies.

## 1. Why an admin UI

The colour→image mapping was operable only via SSH (`manage.py build_color_image_maps …`). Since API keys and configs are already managed from the admin, mapping operations now live there too: **Admin → Printify control → Variant image mapping** (`/admin/store/productcolorimagemaprun/mapping/`). No shell needed for ordinary operations.

## 2. One engine, two entry points

`printify_integration/map_runner.py::run_color_image_mapping(...)` is the single engine; the management command is now a thin CLI wrapper over it and the admin pages call it directly — behaviour can never drift. Every execution records a **`ProductColorImageMapRun`** row: who/when/mode/source/status, aggregate counters (scanned/changed/resolved/unresolved/manual-preserved/AI calls), duration and a safe per-row summary. **Never stored:** tokens, keys, prompts, raw provider payloads.

## 3. Dry-run vs Apply vs OpenAI

- **Dry run (default)** — everything computed inside a transaction rolled back at the end; the history row is written *outside* it. Shows exactly what would change; writes nothing.
- **Apply** — superadmin-only, POST + explicit checkbox “I understand this will update variant image mappings.” on the results page (the confirm page IS the dry-run preview). Live payload refetch (read-only Printify GETs through the encrypted admin config) is the recommended source; missing credentials degrade to DB data with a visible warning.
- **OpenAI enrichment** — separate opt-in with a cost warning (“This may use OpenAI credits.”), mandatory call budget (default 20, max 200), runs **only on Apply** and **only for still-unresolved colours**; uses the existing encrypted AssistantConfig (env fallback); if no key is configured the dashboard shows an elegant notice pointing to the Assistant settings instead of failing. Results are persisted (`source=openai`) so images are never re-classified. Failures degrade cleanly: rows stay unresolved.
- **Manual pins** are untouchable by every path (rebuild, AI, admin) and surfaced with their own badge + a “Manual pins preserved” counter.

## 4. UI

Dashboard: premium header, stat cards (resolved/unresolved/manual pins/last-run figures), the run form (scope: all / only-unresolved / Printify-only / single product; source live/db; OpenAI block), recent-runs table. Results page: status badges (“Dry run — nothing was written”), warnings panel, per-row table (product, colour, primary thumbnail, source badge deterministic-green / heuristic-amber / openai-violet / manual-teal / unresolved-slate, confidence, image count, detail, links to product admin + PDP), Apply card with confirm checkbox, technical JSON only inside a collapsed *Diagnostics* section.

Product changelist actions: **Dry-run colour-image mapping**, **Apply colour-image mapping** (existing action, kept), **OpenAI enrich unresolved mappings** (superadmin-only) — each links to its run results. The Product change form keeps the read-only colour-image inline (colour, source, confidence, images, detail, built time).

## 5. Permissions & security

Dashboard/dry-run: any active staff admin (`admin_view`). Apply + OpenAI: `_is_superadmin` (custom `is_superadmin` OR `is_superuser`) — enforced server-side on the POST endpoints (403), not just hidden in the UI. All POSTs are CSRF-protected; runs are synchronous with a `product_cap` (500) + AI budget bound instead of background jobs (no queue exists in this project — same operating model as every other control-center action). Run rows are read-only in the admin. Tests assert no `sk-`/token/key material ever reaches HTML or the stored summary.

## 6. Recommended workflow

1. **Dry run** (live source) → 2. review the results table (unresolved? wrong sources?) → 3. **Apply** deterministic/live → 4. review remaining unresolved colours → 5. optional **OpenAI enrichment** with a small budget → 6. QA the PDP (colour switch shows the right mockup).

## 7. Tests & QA

`printify_integration/test_map_runner.py` (10: dry-run rollback + history, apply, only-unresolved scope, cap warning, manual preservation, AI gating/budget, no-secret summary, partial status) and `store/test_mapping_admin.py` (12: permissions staff/superadmin, preview→result flow, confirm gating, scope filters, changelist actions, no-secret HTML). Browser QA in `docs/qa/glitchy_admin_color_image_mapping/`: dashboard, dry-run results (run #1, live refetch worked), confirm checkbox, applied run #2, product inline, OpenAI cost-warning card, PDP after admin apply.

## 8. Deploy notes

Included in this branch's deploy (see the add-to-cart doc): `migrate` (store 0016) + `compilemessages` + `collectstatic` + restart. First use: open *Variant image mapping*, run a dry-run, review, apply. CLI (`build_color_image_maps`) keeps working unchanged for automation, now writing the same run history (`created_by="cli"`).
