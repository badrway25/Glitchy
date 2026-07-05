"""OpenAI admin diagnostics — read-only test connection. Key never printed/logged."""
import logging

from django.utils.translation import gettext as _

logger = logging.getLogger("assistant")


def test_connection(cfg):
    """GET /v1/models with the stored key — read-only, cheap, precise error mapping."""
    from payments import secrets as secretbox
    if not cfg.has_api_key():
        cfg.record_connection("failed", _("No API key saved."))
        return {"ok": False, "error": _("No API key saved yet — set it above first.")}
    if not secretbox.has_key():
        cfg.record_connection("failed", _("Encryption key missing."))
        return {"ok": False, "error": _(
            "PAYMENT_CONFIG_KEY is not configured on the server — the stored key cannot be "
            "decrypted. Configure it, then save the API key again.")}
    key = cfg.get_api_key()
    if not key:
        cfg.record_connection("failed", _("Key cannot be decrypted."))
        return {"ok": False, "error": _(
            "The stored key cannot be decrypted (was PAYMENT_CONFIG_KEY rotated?). Save the "
            "API key again.")}
    try:
        import requests
        resp = requests.get("https://api.openai.com/v1/models",
                            headers={"Authorization": f"Bearer {key}"}, timeout=10)
        if resp.status_code == 200:
            ids = [m.get("id", "") for m in (resp.json().get("data") or [])]
            if cfg.model and cfg.model not in ids:
                cfg.record_connection("connected", _("Key OK — model not in list."))
                return {"ok": True, "detail": _(
                    "OpenAI key works, but the configured model was not found in your "
                    "account's model list — double-check the model id.")}
            cfg.record_connection("connected", _("OpenAI reachable."))
            return {"ok": True, "detail": _("OpenAI connection OK — key valid, model available.")}
        if resp.status_code == 401:
            cfg.record_connection("failed", _("Invalid key (401)."))
            return {"ok": False, "error": _(
                "OpenAI rejected the key (401) — it looks invalid or revoked. Re-copy it "
                "from the OpenAI dashboard.")}
        if resp.status_code == 429:
            cfg.record_connection("failed", _("Quota/billing (429)."))
            return {"ok": False, "error": _(
                "OpenAI answered 429 — quota exhausted or billing not active on the "
                "account.")}
        cfg.record_connection("failed", f"http_{resp.status_code}")
        return {"ok": False, "error": _(
            "OpenAI answered an unexpected status (%(code)s). Try again in a moment.")
            % {"code": resp.status_code}}
    except Exception as exc:
        logger.warning("assistant openai test error=%s", type(exc).__name__)
        cfg.record_connection("failed", _("Network timeout."))
        return {"ok": False, "error": _(
            "Could not reach OpenAI (network/timeout). Check the server's connectivity.")}
