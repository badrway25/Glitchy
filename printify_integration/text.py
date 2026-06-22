"""Sanitize Printify product descriptions to clean, safe plain text.

Printify returns HTML (<p>, <br>, <ul>, <li>, …). We convert it to readable PLAIN TEXT
(bullets + paragraph breaks) before storing/displaying. Output is never marked safe and is
rendered escaped, so there is no XSS surface — and customers never see raw tags.
"""
import html
import re

_SCRIPT_STYLE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_LI_OPEN = re.compile(r"<li[^>]*>", re.IGNORECASE)
_BLOCK_CLOSE = re.compile(r"</(p|div|li|ul|ol|h[1-6]|tr|section|article)\s*>", re.IGNORECASE)
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_MULTI_NL = re.compile(r"\n{3,}")
_TRAIL_WS = re.compile(r"[ \t]+\n")


def clean_printify_description(raw):
    """Return clean plain text (bullets as '• ', paragraph breaks preserved)."""
    if not raw:
        return ""
    text = str(raw)
    text = _SCRIPT_STYLE.sub("", text)          # drop script/style entirely
    text = _LI_OPEN.sub("\n• ", text)           # list items -> bullets
    text = _BR.sub("\n", text)                  # line breaks
    text = _BLOCK_CLOSE.sub("\n", text)         # block closes -> newline
    text = _TAG.sub("", text)                   # strip every remaining tag
    text = html.unescape(text)                  # &amp; -> & , &nbsp; -> space, etc.
    text = text.replace("\xa0", " ").replace("\r", "")
    # normalise whitespace
    lines = [re.sub(r"[ \t]{2,}", " ", ln).strip() for ln in text.split("\n")]
    text = "\n".join(lines)
    text = _TRAIL_WS.sub("\n", text)
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()


def looks_like_html(value):
    """True if a stored description still contains tags (for the cleanup command)."""
    return bool(value) and bool(_TAG.search(str(value)))
