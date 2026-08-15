"""Guard: no unterminated `{# … #}` comments in templates.

Django's `{# #}` comment is SINGLE-LINE only. Spread it over two lines and the
rest of it renders as visible text to customers — which is exactly what happened
on the checkout summary and the homepage hero during this phase. This test scans
every template so the mistake cannot reach a page again.
"""
from pathlib import Path

from django.test import SimpleTestCase

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


class TemplateCommentGuardTests(SimpleTestCase):
    def test_no_single_line_comment_spans_multiple_lines(self):
        offenders = []
        for path in TEMPLATES_DIR.rglob("*.html"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "{#" in line and "#}" not in line.split("{#", 1)[1]:
                    offenders.append(f"{path.relative_to(TEMPLATES_DIR)}:{number}")
        self.assertEqual(
            offenders, [],
            "Django {# #} comments must open and close on the SAME line — use "
            "{% comment %}…{% endcomment %} for multi-line notes. Offenders: "
            + ", ".join(offenders))
