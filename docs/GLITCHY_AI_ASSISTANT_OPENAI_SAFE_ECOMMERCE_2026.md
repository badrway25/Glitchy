# Glitchy Assistant — Premium UX, OpenAI Admin Config & Safe Ecommerce AI (2026)

**Branch:** `feat/glitchy-ai-assistant-openai-safe-ecommerce` (from
`release/staging-printify-fashion-store @ 6256c4a`). **Migration:** `assistant/0002`
(AssistantConfig) — additive, deploy needs `migrate`. No real OpenAI calls in tests.

## 1. Audit — what already existed (a lot)
The `assistant` app was already a serious, SAFE implementation: KnowledgeEntry curated FAQ
(i18n), retrieval grounding on knowledge + PUBLIC products, `OpenAIProvider` (chat
completions via `requests`, env `AI_API_KEY` only), guardrail decline for out-of-scope,
conversation storage, rate limiting, hashed IPs, and a security test suite (owner-scoped
order context, user A cannot read user B, XSS, prompt-reveal refused, provider-failure →
curated fallback). The gaps: env-only plaintext key (no admin config), the "two close
buttons" (the draggable FAB shows a big X while the panel is open, next to the header
close), the panel opening OFF-VIEWPORT when the FAB had been dragged to the top (anchored
`bottom:72px` above the FAB), no product cards in the JSON, no online/limited status, and
no explicit hard-block list for SQL/users/secrets/billing questions.

## 2. UI fixes
- **Single close**: `.ai-assistant.is-open .ai-fab` is now hidden (only the header close
  remains; the FAB returns on close). Esc already closed — kept.
- **Always in viewport**: `clampPanel()` on open — flips the panel BELOW the FAB
  (`.ai-panel--below`) when there is no room above; if still out, resets the FAB to its
  default corner and clears the saved position. Saved positions outside the viewport are
  also clamped on load. QA: FAB parked at the very top → panel opens fully visible (flipped).
- **Status chip**: header sub shows "AI assistant · online" (provider ready) or "Limited
  mode — curated store answers" (no key/config) from the suggestions endpoint's new
  `ai_ready` flag.
- Mobile 390: bottom-sheet behaviour kept, 0 overflow.

## 3. Encrypted OpenAI admin (AssistantConfig — assistant/0002)
Same control-center pattern as payments/Google: **write-only** `Set / replace OpenAI API
key` (PasswordInput), encrypted via `payments.secrets` (`PAYMENT_CONFIG_KEY`, historical
name), masked `•••• last4 · fp:…`, superadmin-only key field, warning card when the
encryption key is missing, **read-only Test connection** (GET /v1/models; maps 401 invalid /
429 quota-billing / timeout / model-not-in-list; never prints the key), plus behaviour
knobs: model, temperature, max input chars, max output tokens, per-session rate limit,
system-prompt extra (appended, never overrides safety). The provider resolves **DB-first,
env fallback** — existing deployments unchanged until configured; disabled config serves no
key.

## 4. Safety hardening
`sensitive_block()` runs BEFORE retrieval/LLM on every message: raw SQL/database/table
requests, all-users/other-customer/user-emails, secrets/keys/passwords/tokens/credentials/
admin/webhooks, internal billing/margins/Printify costs/provider config, prompt-injection
markers ("ignore the rules", "system prompt", jailbreak) → immediate elegant refusal
("I can't access sensitive account, database or admin data…"), provider `guardrail`, no
context ever built. The model NEVER queries the DB: the only data paths are the existing
whitelist retrievals (public products, curated knowledge, owner-scoped order summary) — no
tool executes model-chosen queries. Existing protections (owner-scoping, XSS-safe
textContent rendering, hashed IPs, input cap, decline-when-ungrounded) all retained and
still test-covered.

## 5. Product cards
`_public_product_cards()` — name, price, url, image ONLY (no costs, no stock, no provider
ids) — attached to grounded answers AND to curated-fallback answers, so Limited mode also
shows cards. The widget renders them as premium tappable cards (DOM building, textContent,
lazy images). QA: 3 cards per matching answer.

## 6. Tests (11 new + full existing security suite)
Key encrypted/masked/decryptable, form refuses key without PAYMENT_CONFIG_KEY (key never in
the error), provider DB-first + disabled-config fallback, test-connection 200/401/timeout
mapped with no key echo, admin HTML has masked display + test button and never the key,
sensitive matrix (11 blocked phrasings IT/EN incl. SQL, user emails, stripe key, internal
billing, injection / 5 legitimate questions pass), chat endpoint refuses elegantly with
provider=guardrail, product cards public-fields-only, `ai_ready` flag. Full suite green.

## 7. QA (browser, OpenAI blocked → fallback paths; fake key only)
Single close (FAB hidden, header close visible), clamp at top (flipped, fully visible),
sensitive question blocked in-chat, product cards rendered, shipping/payment answers,
online status chip, admin masked config, mobile 390. 8 screenshots in
`docs/qa/glitchy_ai_assistant_openai_safe_ecommerce/`.

## 8. Deploy notes
`git pull` → **`migrate`** (assistant/0002) → `compilemessages -l it -l fr` →
`collectstatic` → restart. Then in **admin → Assistant AI settings**: paste the OpenAI key
(needs `PAYMENT_CONFIG_KEY` on the server — same one already used for payments/Google),
pick the model, enable, Test connection. Until then the assistant runs in Limited mode
(curated answers + product cards) — fully functional, zero OpenAI cost.
