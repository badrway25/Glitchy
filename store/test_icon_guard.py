"""Icon guard: the site ships Font Awesome 5.8.2 — FA6-only icon names render as empty
squares. This test keeps FA6-only names out of source templates and JS (see project
memory: FontAwesome version gotcha)."""
import pathlib
import re

from django.conf import settings
from django.test import SimpleTestCase

BASE = pathlib.Path(settings.BASE_DIR)
SCAN = [BASE / "templates", BASE / "greatkart" / "static" / "js"]

# FA6-only names (their FA5 equivalents in parentheses) — extend as needed.
FA6_ONLY = re.compile(
    r"fa-(circle-check|circle-info|circle-xmark|triangle-exclamation|xmark|"
    r"bag-shopping|cart-shopping|magnifying-glass|arrow-right-from-bracket|heart-crack)\b")


class IconGuardTests(SimpleTestCase):
    def test_no_fa6_only_icon_names_in_source(self):
        offenders = []
        for root in SCAN:
            for ext in ("*.html", "*.js"):
                for path in root.rglob(ext):
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    for m in FA6_ONLY.finditer(text):
                        offenders.append(f"{path.relative_to(BASE)}: {m.group(0)}")
        self.assertEqual(offenders, [],
                         "FA6-only icon names on the FA5 build (render empty):\n" + "\n".join(offenders))
