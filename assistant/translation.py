"""Faithful, cached translation of product descriptions.

Reuses the assistant's OpenAI transport (`assistant.providers.OpenAIProvider`). This
module is the ONLY place product descriptions are translated, and it is invoked
OFFLINE by the `translate_printify_descriptions` management command — never in the
request/response path. Output is guaranteed plain text (re-sanitized, no HTML), never
contains internal IDs/costs, and the API key is never logged or returned.
"""
import logging

from django.conf import settings

from printify_integration.text import clean_printify_description
from .providers import OpenAIProvider, ProviderError

logger = logging.getLogger("assistant")

# Target languages we translate into (English is the base/source — never translated).
SUPPORTED_TARGET_LANGS = ("it", "fr")

LANGUAGE_NAMES = {"it": "Italian", "fr": "French", "en": "English"}

SYSTEM_PROMPT = (
    "You are a professional e-commerce translator for a premium fashion brand. "
    "Translate the product description faithfully into {language}.\n"
    "Rules:\n"
    "- Preserve the exact meaning. Keep a refined, premium fashion tone.\n"
    "- DO NOT invent, add, exaggerate, or remove any facts: sizes, measurements, "
    "fabrics/materials, fit, colours, care instructions and counts must stay identical.\n"
    "- Keep bullet points (lines starting with '•') and the existing line breaks.\n"
    "- Do not add markdown, headings, HTML tags, quotes, or any commentary.\n"
    "- Output ONLY the translated description text — nothing before or after it."
)

# Conservative cap: descriptions are <=2000 chars (~600 tokens); allow room for output.
_MAX_OUTPUT_TOKENS = 1000


def translation_available():
    """True only if a key is configured and the AI feature is enabled."""
    return bool(getattr(settings, "AI_API_KEY", "")) and getattr(
        settings, "AI_ASSISTANT_ENABLED", True
    )


def is_supported(target_lang):
    return (target_lang or "")[:2] in SUPPORTED_TARGET_LANGS


def translate_text(text, target_lang, source_lang="en", retries=1):
    """Translate plain-text ``text`` into ``target_lang`` and return plain text.

    Raises ``ProviderError`` with a SAFE code on failure ('missing_key',
    'unsupported_lang', 'network', 'http_<status>', 'payload', 'empty'). The caller
    (command / accessor) decides the fallback; the site never blocks on this.
    """
    target_lang = (target_lang or "")[:2]
    language = LANGUAGE_NAMES.get(target_lang)
    if not language or target_lang not in SUPPORTED_TARGET_LANGS:
        raise ProviderError("unsupported_lang")

    text = (text or "").strip()
    if not text:
        raise ProviderError("empty")

    provider = OpenAIProvider()
    if not provider.available():
        raise ProviderError("missing_key")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(language=language)},
        {"role": "user", "content": text},
    ]

    last_exc = None
    for attempt in range(max(1, retries + 1)):
        try:
            raw = provider.chat(messages, max_tokens=_MAX_OUTPUT_TOKENS, temperature=0.1)
            cleaned = _plain_text(raw)
            if not cleaned:
                raise ProviderError("payload")
            return cleaned
        except ProviderError as exc:
            last_exc = exc
            logger.warning("translation attempt %s/%s failed: %s",
                           attempt + 1, retries + 1, exc)
    raise last_exc or ProviderError("unknown")


def _plain_text(text):
    """Defense in depth: run the model output back through the Printify sanitizer so a
    stray tag/markdown can never reach the page, and enforce the 2000-char contract."""
    return clean_printify_description(text or "")[:2000]


def ensure_product_translation(product, lang, *, force=False, apply=False):
    """Idempotently ensure a fresh translation of ``product`` into ``lang`` exists.

    Reads the cache; on a miss/stale source (or ``force``) translates via OpenAI and
    persists when ``apply`` is True. NEVER raises — returns a safe result dict with an
    ``action`` of cached/would_translate/translated/failed/skipped. On failure an
    existing good translation is preserved (so the PDP keeps falling back gracefully).
    """
    from store.models import ProductDescriptionTranslation

    lang = (lang or "")[:2]
    result = {"product_id": product.id, "language": lang,
              "action": "skipped", "status": "", "error": ""}

    if lang not in SUPPORTED_TARGET_LANGS:
        result["status"] = "unsupported_lang"
        return result

    source = (product.description or "").strip()
    if not source:
        result["status"] = "no_source"
        return result

    src_hash = product.description_source_hash()
    existing = product.description_translations.filter(language=lang).first()
    fresh = (existing and existing.status == ProductDescriptionTranslation.STATUS_DONE
             and existing.source_hash == src_hash and bool(existing.translated_text))

    if fresh and not force:
        result["action"] = "cached"
        result["status"] = "done"
        return result

    if not apply:
        result["action"] = "would_translate"
        result["status"] = "stale" if existing else "missing"
        return result

    try:
        translated = translate_text(source, lang)
    except ProviderError as exc:
        code = str(exc)[:40]
        result["action"] = "failed"
        result["status"] = "error"
        result["error"] = code
        # Preserve any existing good translation as a fallback; only record the error
        # when there is nothing usable to keep.
        if not (existing and existing.status == ProductDescriptionTranslation.STATUS_DONE
                and existing.translated_text):
            ProductDescriptionTranslation.objects.update_or_create(
                product=product, language=lang,
                defaults={"source_hash": src_hash,
                          "status": ProductDescriptionTranslation.STATUS_ERROR,
                          "error_code": code},
            )
        return result

    ProductDescriptionTranslation.objects.update_or_create(
        product=product, language=lang,
        defaults={"translated_text": translated, "source_hash": src_hash,
                  "status": ProductDescriptionTranslation.STATUS_DONE, "error_code": ""},
    )
    result["action"] = "translated"
    result["status"] = "done"
    return result
