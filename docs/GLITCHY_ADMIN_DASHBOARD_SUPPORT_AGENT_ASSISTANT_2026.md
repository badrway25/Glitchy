# Premium Product UI Fix, Admin Dashboard Pro & Support-Agent Assistant Memory (2026)

**Branch:** `feat/glitchy-admin-dashboard-support-agent-assistant` (from
`release/staging-printify-fashion-store @ d7f6664`). **No migration** (the conversation
models already existed). No real OpenAI calls in tests/QA.

## 1. SAVED button (product page)
`.wish-btn-pdp.is-active` painted white text on bright `var(--danger)` — the reported
unreadable state. New premium saved-state: soft danger tint background with DARK red text
(`#b91c1c`) in light theme and soft readable red (`#fca5a5`) in dark theme, plus a visible
focus ring. QA-measured: text luminance dark on light bg; the circular card wishlist buttons
are untouched.

## 2. Admin dashboard — ecommerce control center
The Phase-71 dashboard (catalog/orders/sync cards) gains a full control-center row, all from
aggregate COUNT/SUM queries (no N+1, no PII, no secrets — flags only):
- **Payments**: paid orders 24h, revenue 7d, awaiting-payment count, methods split;
- **Email outbox**: n8n enabled/SMTP fallback, sent/pending/failed 7d;
- **Assistant**: online(AI)/limited, model, messages 24h, safety blocks 24h;
- **Operational health**: Stripe / PayPal / Google Places / OpenAI / n8n configured yes-no;
- **Recent orders**: last 6 paid (number/status/printify status/total — no names/addresses);
- Quick actions extended (Payments config, Assistant settings, Email outbox).
Owner feedback applied live: status dots now breathe (`.gl-pulse` margin) and `.gl-kv` rows
have more air. Tablet 768 verified, no overflow.

## 3. Assistant — real conversation memory
The message history WAS already stored and sent to OpenAI; what was missing was
**context-aware retrieval**: a follow-up like "quanto costa?" retrieved nothing, so the
model had no grounding and answered generically. New `_followup_products(conv)` reuses the
products referenced by the previous assistant turns (from the stored `used_sources`
`product:{id}` refs) whenever the current retrieval comes up empty — QA: search → 3 product
cards → "quanto costa?" → the SAME products return with prices. Works in AI mode and in
limited mode. Session-scoped and isolated (test: client B never sees client A's context);
clear-chat already resets the conversation id.

## 4. Support-agent behaviour
System prompt upgraded: professional support-agent persona; resolve follow-ups against the
conversation; ONE clarifying question when a detail is missing; always end with a concrete
next step; practical payment-trouble playbook including "if PayPal approved but the page
failed, do NOT pay again — contact support with the order number". Quick prompts replaced
with the support set (Find a product / Delivery times & costs / Payment problem / Where is
my order? / Returns). Widget header: "Glitchy Support Assistant · Products · Delivery ·
Payments · Orders" + discreet memory note.

## 5. Memory protection
New sensitive patterns (it/fr/en): "remember/save my card", card numbers, "memorize the
password", "what did the other user ask" — refused by the guardrail BEFORE any storage,
retrieval or LLM call (QA: "ricordati la mia carta 4242" → Italian refusal). System-prompt
reveal, SQL, users/emails, secrets, internal billing all still blocked (existing tests).

## 6. Tests (7 new) + QA
Follow-up reuses previous products, session isolation, memory-exfiltration matrix, SAVED
readable-state CSS guard (both themes + focus ring), dashboard snapshots leak nothing +
flags-only ops health + staff-only. Full suite green. QA browser: SAVED readable
(rgb(185,28,28) on soft tint), dashboard 13 sections with dot spacing fix, follow-up cards,
Belgium follow-up answered in Italian with the real €11.90 / 7-15 days quote, payment
support answer, memory-block, mobile/tablet clean. 9 screenshots in
`docs/qa/glitchy_admin_dashboard_support_agent_assistant/`.

## 7. Deploy notes
No migration, no packages. `git pull` → `compilemessages -l it -l fr` → `collectstatic` →
restart. Nothing to configure: memory and the support persona activate immediately; the
dashboard reads existing data.
