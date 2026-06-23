"""LLM provider abstraction. OpenAI is called over HTTPS via `requests` (no extra
SDK). When no key is configured or the call fails, we fall back to returning the
best curated knowledge answer — the widget always works and never leaks data."""
import logging

import requests
from django.conf import settings

logger = logging.getLogger("assistant")


class ProviderError(Exception):
    pass


class OpenAIProvider:
    """Calls the OpenAI Chat Completions API. The key is read from settings/env
    and is NEVER logged."""

    name = "openai"
    ENDPOINT = "https://api.openai.com/v1/chat/completions"

    def __init__(self):
        self.api_key = getattr(settings, "AI_API_KEY", "") or ""
        self.model = getattr(settings, "AI_MODEL", "gpt-4o-mini")
        self.max_tokens = getattr(settings, "AI_MAX_TOKENS", 500)
        self.timeout = getattr(settings, "AI_TIMEOUT_SECONDS", 20)

    def available(self):
        return bool(self.api_key)

    def chat(self, messages, max_tokens=None, temperature=0.2):
        """Low-level Chat Completions call. Returns the assistant message content.
        Logs status codes only — never the response body or the key."""
        try:
            resp = requests.post(
                self.ENDPOINT,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": max_tokens or self.max_tokens,
                    "temperature": temperature,
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.warning("assistant openai request failed: %s", type(exc).__name__)
            raise ProviderError("network") from exc

        if resp.status_code != 200:
            # Log status only — never the body (could echo the key in error envelopes).
            logger.warning("assistant openai HTTP %s", resp.status_code)
            raise ProviderError(f"http_{resp.status_code}")

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except (ValueError, KeyError, IndexError) as exc:
            logger.warning("assistant openai bad payload")
            raise ProviderError("payload") from exc

    def complete(self, system_prompt, history):
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        return self.chat(messages, max_tokens=self.max_tokens, temperature=0.2)


class FallbackProvider:
    """No LLM: return the single most relevant curated answer, or the decline
    sentence. Keeps the assistant useful and 100% grounded with zero API calls."""

    name = "fallback"

    def answer_from_knowledge(self, knowledge, lang, decline):
        if knowledge:
            return knowledge[0].answer_for(lang)
        return decline


def get_provider():
    """Return the configured LLM provider if usable, else None (caller falls back)."""
    if not getattr(settings, "AI_ASSISTANT_ENABLED", True):
        return None
    provider = (getattr(settings, "AI_PROVIDER", "openai") or "").lower()
    if provider == "openai":
        p = OpenAIProvider()
        return p if p.available() else None
    return None  # 'mock'/unknown -> use FallbackProvider in the service layer
