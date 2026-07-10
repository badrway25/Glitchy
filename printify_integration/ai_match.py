"""OpenAI-assisted colour classification for gallery images — the LAST-resort stage.

Why it exists: when neither the Printify payload nor the persisted variant titles
nor local heuristics can tell which colour a mockup shows (e.g. manually added
colour rows with no variant data), an admin can OPT IN to a one-off vision
classification via `build_color_image_maps --apply --openai`.

Guarantees:
- Never called in the request path — offline command only.
- Classification, not generation: the model must pick from the product's OWN
  colour list (or UNKNOWN); anything else is discarded. No invention.
- Results are PERSISTED on ProductColorImage (source="openai"), so each image is
  classified at most once — no repeated spend.
- Fail-safe: key missing / network error / odd answer -> None; the row simply
  stays unresolved and the storefront keeps the default-gallery fallback.
- Reuses the assistant's encrypted-key infrastructure (AssistantConfig / env
  AI_API_KEY via OpenAIProvider). The key is never logged; only status codes are.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("printify")


def classify_image_color(image_url, color_choices, provider=None):
    """Return the colour (lowercased, from `color_choices`) the mockup at
    `image_url` shows, or None when unavailable/unsure/error."""
    from assistant.providers import OpenAIProvider, ProviderError

    provider = provider or OpenAIProvider()
    choices = [str(c).strip().lower() for c in (color_choices or []) if str(c).strip()]
    if not provider.available() or not image_url or not choices:
        return None

    messages = [
        {"role": "system", "content": (
            "You classify e-commerce garment mockup photos by garment colour. "
            "Answer with EXACTLY one colour from the provided list, or UNKNOWN "
            "if you are not sure. No other words.")},
        {"role": "user", "content": [
            {"type": "text", "text": (
                "Colour list: " + ", ".join(choices) +
                ". Which colour from the list is the garment in this image?")},
            {"type": "image_url", "image_url": {"url": image_url, "detail": "low"}},
        ]},
    ]

    for attempt in (1, 2):                      # one retry, same as translate_text
        try:
            answer = provider.chat(messages, max_tokens=12, temperature=0)
        except ProviderError as exc:
            logger.warning("ai colour match failed (%s, attempt %d)", exc, attempt)
            continue
        low = (answer or "").strip().lower().strip(".")
        return low if low in choices else None  # UNKNOWN / free text -> no invention
    return None
