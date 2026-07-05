# Glitchy Assistant — Runtime Activation, Multilingual Answers & Admin Copy Fix (2026)

**Branch:** `fix/glitchy-assistant-runtime-openai-language` (from
`release/staging-printify-fashion-store @ fb75313`). **No migration.** No real OpenAI calls
in tests (mocked capture of the exact prompt sent).

## 1. Root cause — "Connected" in admin, decline in the store
Two stacked causes, both fixed:
1. **The system prompt was a wall**: rule 19 ordered the model to reply with EXACTLY the
   decline sentence whenever the context didn't contain the answer — and on a fresh
   deployment the KnowledgeEntry KB can be thin, so OpenAI WAS being called and obediently
   parroted *"I don't have enough information on the site…"* for perfectly normal questions.
2. **The enabled-flag trap**: the admin Test connection validated the key without checking
   `is_enabled` (default OFF) — "Connected" while the runtime stayed in limited mode. The
   test now says it explicitly: *"OpenAI key works — but the assistant is still DISABLED:
   turn on 'Is enabled' above and save."*

## 2. Always-grounded context (`retrieval.store_facts`)
Every in-scope question now injects REAL store facts into the prompt: shipping cost/ETA for
the country mentioned in the message (same `fallback_quote` rate table the checkout charges
from — country matched in it/fr/en names), the payment methods actually available (resolver
flags — never config internals), the public return window and the support contact. Test
captures the live prompt and asserts `STORE FACTS` + `Shipping to Italy` are present.

## 3. Answer in the USER'S language
`assistant/language.py`: dependency-free detection — Arabic by Unicode range, it/fr/en by
stopword scoring, site-language fallback on ambiguity/tie. The system prompt now leads with
*"ALWAYS answer in {language}; never switch to English unless the user writes in English"*,
the softened partial-context rule speaks the same language, and the sensitive refusal is
served from a localized table (it/fr/en/ar) in the DETECTED language (French question about
"tous les utilisateurs" → French refusal — pattern list extended with the French sensitive
phrasings that previously slipped through to the generic decline).

## 4. Softer honesty rule (no more decline wall)
The prompt now instructs: answer what the context DOES cover, state honestly (in the user's
language) what cannot be confirmed, point to checkout/support for the rest — the decline
sentence is reserved for genuinely off-store topics. Plus a **smart limited-mode fallback**:
without OpenAI, core questions (shipping with real country rates, available payment methods,
return window) get useful localized it/fr/en answers built from live data instead of the
decline. QA: Belgio→Italian answer with real ETA, France→French, PayPal→English steps.

## 5. Admin loader copy ("connessione a Printify" bug)
`ops-modal.js` hard-coded Printify steps for every `.gl-action` test button. New op types:
`aitest` ("Testing OpenAI connection… / Connecting to OpenAI / Validating key (read-only)")
and `gkeytest` ("Testing Google connection…") — wired via `data-gl-op` on the assistant AND
Google admin test forms (the Google test had the same Printify copy bug; fixed in passing).
QA screenshot shows the OpenAI loader with zero Printify strings.

## 6. Staff-only safe diagnostics
For staff users the chat JSON gains `debug: {assistant_mode online|limited, provider_used,
openai_called, config_enabled, language}` — no key, no prompt, no PII; customers never see
it (test-asserted both ways).

## 7. Tests (12 new; assistant suite green)
Language detection it/fr/en/ar + ambiguity fallback, French refusal in French, prompt carries
the language instruction, store_facts real shipping + no secrets, test-connection DISABLED
warning, **OpenAI-called-at-runtime with language+facts asserted on the captured prompt**,
staff-only debug, loader copy guards (aitest steps, data-gl-op on both admin forms).

## 8. QA (browser; api.openai.com blocked, fake keys only)
IT/FR/EN questions answered in the right language with useful content, Italian sensitive
question refused in Italian, mobile 390 clean, admin loader shows OpenAI copy, masked key
never in HTML. 7 screenshots in `docs/qa/glitchy_assistant_runtime_openai_language/`.

## 9. Deploy notes
No migration. `git pull` → `compilemessages -l it -l fr` → `collectstatic` → restart.
**On the live admin: open Assistant AI settings and switch `Is enabled` ON** (the key you
already saved is fine — the new Test connection message will confirm). From then on the
store calls OpenAI with grounded context and answers in the shopper's language.
