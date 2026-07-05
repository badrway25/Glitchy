# Premium Order Complete, Printify Timeline & n8n Gmail Confirmation (2026)

**Branch:** `feat/glitchy-premium-order-complete-printify-email` (from
`release/staging-printify-fashion-store @ 6f66ec7`). **No migration.** No real n8n/SMTP/
Printify calls in tests; QA on local test data.

## 1. Audit — what was actually wrong
- The page's **timeline was fake**: it derived "Packed / Shipped" from `Order.status`, which
  `finalize_order_payment` sets to *Accepted* right after payment — so "Packed" showed done
  minutes after paying, with a permanent grey "Cancelled" step at the end.
- The invoice card used the **old logo** (`images/logo.png`); the official brand lives in
  `images/brand/logo-glitchy-nav(.png|-light.png)` (what the navbar uses).
- **The n8n Gmail infrastructure already existed and was already firing**: `notifications`
  has a full outbox (`OutboundEvent` with status/attempts/retries), an HMAC-signed + header-
  auth n8n dispatcher with SMTP fallback, and the previous phase already moved
  `notify_order_event(order, ORDER_PAID)` into a background thread post-finalize. What was
  missing: **idempotency** (every call created a new outbox row) and page visibility.
- Printify: push already runs in background post-finalize; `printify_order_id/status/
  last_error/tracking_*` fields already exist and the read-only sync daemon (Phase 73) keeps
  them fresh. No new sync code needed — the page just had to READ them honestly.

## 2. What this phase adds
- **`orders/timeline.py`** — `get_order_timeline(order)` / `timeline_summary(order)`:
  5 honest steps (Payment confirmed → Sent to production → In production → Shipped →
  Delivered) where each state is proven by real fields: printify_order_id gates "sent",
  Printify status gates "in production", tracking gates "shipped", carrier/status gates
  "delivered"; push errors surface as an error state with truthful copy ("Production sync
  pending — this page updates…"). Nothing is ever invented.
- **Premium page**: brand logo (theme-aware pair), "Payment confirmed · PayPal" chip,
  optional "Sandbox / test payment" chip (from the provider config environment), icon
  timeline with arrows + current-step highlight + track-parcel link, 3 info cards (email
  confirmation status from the outbox, made-to-order note, tracking note), real totals
  (shipping + discount rows added), Continue shopping / Contact support (mailto) actions,
  refined hero check (44px), dark-mode-readable Qty/Total, mobile 390 vertical timeline.
- **`GET /orders/status/`** — owner-scoped (user or guest session), read-only, no PII JSON
  `{ok, payment_status, production_status, timeline[], tracking_url, updated_at}`; the page
  polls it (first at 12s, then 15s, max 10 tries, stops at shipped/delivered) under the
  "this page updates automatically" live chip.
- **Email idempotency**: `dispatch_event(..., dedupe=True)` for customer order events — one
  OutboundEvent per (order, event); reconciliation double-fires and refreshes can never send
  a second confirmation. A FAILED event may retry (test-asserted both ways).

## 3. n8n Gmail — what remains to configure (n8n side, not code)
The backend already posts the full order payload (items, totals, shipping, language,
tracking when present) to `N8N_WEBHOOK_BASE_URL/<event>` with `X-Signature` (HMAC-SHA256 of
the body via `N8N_SHARED_SECRET`) and the `N8N_HEADER_AUTH_NAME/SECRET` header. In n8n:
a webhook node for `order.paid` → verify header/signature → Gmail node using the payload
(template `glitchy_order_confirmation`) → callback to the existing delivery-status API to
mark sent/failed. Server env needed: `N8N_ENABLED=1`, `N8N_WEBHOOK_BASE_URL`,
`N8N_SHARED_SECRET`, `N8N_HEADER_AUTH_SECRET`. Until then the SMTP fallback covers delivery.

## 4. Tests (11 new) + QA
Timeline matrix (payment-only→sync_pending, sent, in-production, shipped-requires-tracking,
delivered, error state), status endpoint owner-scoping + PII-free JSON + foreign-session 404,
page guards (new logo present, `images/logo.png` gone, "Packed" gone, honest copy, polling
wired, shipping row), email dedup ×3 → 1 row + failed-retry allowed. Full suite green.
QA: sync-pending and shipped scenarios (real DB rows, both states honest), status API,
mobile 390, dark-mode Qty/Total contrast, live-chip; 7 screenshots in
`docs/qa/premium_order_complete_printify_email/`. (Admin email-status screenshot: the
OutboundEvent admin already lists status/attempts — unchanged by this phase.)

## 5. Deploy notes
No migration, no packages. `git pull` → `compilemessages -l it -l fr` → `collectstatic` →
restart. To activate the n8n Gmail path in production: set the four N8N_* env vars and build
the `order.paid` workflow (§3); nothing else to deploy. The timeline enriches itself as the
Printify sync daemon updates status/tracking.
