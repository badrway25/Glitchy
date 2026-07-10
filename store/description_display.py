"""Premium structuring of the clean plain-text product description for the PDP.

Reorganizes the EXISTING sanitized description (see printify_integration/text.py —
plain text, '• '/'-'/'.:' bullets, newlines) into display sections:

    overview    first prose paragraph — the always-visible intro
    highlights  feature bullets (materials, construction, print quality, …)
    care        care/wash bullets (routed by heading or per-line keywords)
    more        any remaining prose paragraphs (brand story, sizing notes, …)

Purely mechanical: sections are recognized by FORM (bullets, short headings) and a
small multilingual keyword map (EN/IT/FR — the languages the store serves). Every
output line is verbatim input text — nothing is added, reworded or invented. When
the text has no recognizable structure the whole description becomes `overview`
and the template falls back to the classic single-block rendering.

Works identically on the English source and on the cached IT/FR translations
(the translation pipeline preserves bullets and line breaks by contract).
"""
from __future__ import annotations

import re

# Bullet markers: '• ' (our cleaner), '- '/'– '/'* ' (hand-written), '.: ' (classic Printify)
_BULLET_RE = re.compile(r"^\s*(?:[•\-–*]|\.\:)\s+")

# Headings that switch the current bucket (lowercased containment match)
_CARE_HEADINGS = ("care", "washing", "cura", "istruzioni", "lavaggio", "entretien", "lavage")
_FEATURE_HEADINGS = ("feature", "highlights", "caratteristiche", "dettagli",
                     "caractéristiques", "détails", "details", "specifiche")

# Per-line care routing for bullets under no/unknown heading. Matched at a word
# START (suffixes allowed: "washing" counts, "brainwash"/"environmentally" don't).
_CARE_KEYWORDS = (
    # EN
    "wash", "bleach", "tumble", "iron", "dryclean", "dry clean", "steam", "detergent",
    # IT
    "lavare", "lavaggio", "lavatrice", "candeggi", "asciugatrice", "stirare", "vapore",
    "a secco",
    # FR
    "laver", "lavage", "javel", "sèche-linge", "repasser", "vapeur", "nettoyage à sec",
)
_CARE_RE = re.compile(
    "|".join(r"(?<![a-zà-öø-ÿ])" + re.escape(k) for k in _CARE_KEYWORDS))

_MAX_HEADING_LEN = 48


def _is_heading(line, next_line):
    """Short label line introducing a bullet block (e.g. 'Product features')."""
    if len(line) > _MAX_HEADING_LEN or _BULLET_RE.match(line):
        return False
    if line.endswith((".", "!", "?", ":", ";", ",")):
        return False
    return bool(next_line and _BULLET_RE.match(next_line))


def _heading_bucket(line):
    low = line.lower()
    if any(k in low for k in _CARE_HEADINGS):
        return "care"
    if any(k in low for k in _FEATURE_HEADINGS):
        return "highlights"
    return None


def _is_care_line(line):
    return bool(_CARE_RE.search(line.lower()))


def structure_description(text):
    """Parse a clean plain-text description into premium display sections.

    Returns {"overview": str, "highlights": [str], "care": [str], "more": [str],
    "is_structured": bool}. Never raises on odd input; empty input yields empty
    sections with is_structured=False."""
    result = {"overview": "", "highlights": [], "care": [], "more": [],
              "is_structured": False}
    if not text or not str(text).strip():
        return result

    lines = [ln.rstrip() for ln in str(text).splitlines()]
    # index of the first bullet/heading — everything before it is intro prose
    overview_lines = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if _BULLET_RE.match(line) or _is_heading(line, nxt):
            break
        if line:
            overview_lines.append(line)
        elif overview_lines:
            break  # blank line after intro prose ends the overview paragraph
        i += 1
    result["overview"] = "\n".join(overview_lines)

    bucket = None            # None -> route bullets by keywords
    paragraph = []           # accumulator for extra prose

    def flush_paragraph():
        if paragraph:
            result["more"].append(" ".join(paragraph))
            paragraph.clear()

    while i < len(lines):
        line = lines[i].strip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if not line:
            flush_paragraph()
        elif _BULLET_RE.match(line):
            item = _BULLET_RE.sub("", line).strip()
            if item:
                if bucket == "care" or (bucket is None and _is_care_line(item)) or (
                        bucket == "highlights" and _is_care_line(item)):
                    result["care"].append(item)
                else:
                    result["highlights"].append(item)
        elif _is_heading(line, nxt):
            flush_paragraph()
            bucket = _heading_bucket(line)
            if bucket is None:
                # unknown heading ("Sizing notes", a tagline…): keep the label as its
                # own line in `more` — consuming it would silently delete content —
                # and route the following bullets by keywords
                result["more"].append(line)
        else:
            paragraph.append(line)
        i += 1
    flush_paragraph()

    result["is_structured"] = bool(result["highlights"] or result["care"]
                                   or result["more"])
    return result
