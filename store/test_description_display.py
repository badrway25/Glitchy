"""Unit tests for the premium description structurer (store/description_display.py).

The structurer reorganizes the EXISTING clean plain-text description into
Overview / Highlights / Care / More sections — purely by form and known headings.
It never invents content: every output line comes verbatim from the input.
"""
from django.test import SimpleTestCase

from store.description_display import structure_description


REAL_STYLE = (
    "This lightweight tee reads like a whispered bedtime mantra — soft, simple, "
    "and quietly comforting. Wear it as your go-to sleep tee.\n"
    "\n"
    "Product features\n"
    "- 100% ring-spun cotton for a soft, lightweight (153 g/m²) feel.\n"
    "- Tubular knit construction — no side seams for a clean, durable finish.\n"
    "\n"
    "Care instructions\n"
    "- Do not dryclean\n"
    "- Machine wash: cold (max 30C or 90F), with similar colors"
)


class StructureRealStyleTests(SimpleTestCase):
    def test_headed_sections_split(self):
        s = structure_description(REAL_STYLE)
        self.assertTrue(s["is_structured"])
        self.assertIn("whispered bedtime mantra", s["overview"])
        self.assertNotIn("Product features", s["overview"])
        self.assertEqual(len(s["highlights"]), 2)
        self.assertIn("100% ring-spun cotton for a soft, lightweight (153 g/m²) feel.",
                      s["highlights"])
        self.assertEqual(len(s["care"]), 2)
        self.assertIn("Do not dryclean", s["care"])
        self.assertEqual(s["more"], [])

    def test_no_content_invented(self):
        s = structure_description(REAL_STYLE)
        joined = " ".join([s["overview"]] + s["highlights"] + s["care"] + s["more"])
        for token in joined.replace("\n", " ").split():
            self.assertIn(token, REAL_STYLE)


class BulletStyleTests(SimpleTestCase):
    def test_dot_bullets_from_cleaner(self):
        text = "Intro paragraph.\n• Soft cotton\n• Machine wash: cold"
        s = structure_description(text)
        self.assertEqual(s["highlights"], ["Soft cotton"])
        self.assertEqual(s["care"], ["Machine wash: cold"])  # care keyword routing

    def test_classic_printify_dot_colon_bullets(self):
        text = "Intro.\n.: 100% combed ringspun cotton\n.: Tumble dry: low heat"
        s = structure_description(text)
        self.assertEqual(s["highlights"], ["100% combed ringspun cotton"])
        self.assertEqual(s["care"], ["Tumble dry: low heat"])

    def test_care_keywords_route_without_heading(self):
        text = ("Intro.\n"
                "- Garment-dyed finish\n"
                "- Do not bleach\n"
                "- Iron, steam or dry: low heat")
        s = structure_description(text)
        self.assertEqual(s["highlights"], ["Garment-dyed finish"])
        self.assertEqual(len(s["care"]), 2)


class LocalizedTests(SimpleTestCase):
    def test_italian_care_keywords(self):
        text = ("Un tessuto morbido e leggero.\n"
                "• 100% cotone biologico\n"
                "• Lavare in lavatrice a freddo\n"
                "• Non candeggiare")
        s = structure_description(text)
        self.assertEqual(s["highlights"], ["100% cotone biologico"])
        self.assertEqual(len(s["care"]), 2)

    def test_french_headed_sections(self):
        text = ("Douceur au quotidien.\n"
                "\n"
                "Caractéristiques\n"
                "- 100% coton peigné\n"
                "\n"
                "Entretien\n"
                "- Laver en machine à froid")
        s = structure_description(text)
        self.assertEqual(s["highlights"], ["100% coton peigné"])
        self.assertEqual(s["care"], ["Laver en machine à froid"])


class FallbackTests(SimpleTestCase):
    def test_plain_wall_of_text_is_all_overview(self):
        text = "Just one long paragraph without any bullets or headings at all."
        s = structure_description(text)
        self.assertFalse(s["is_structured"])
        self.assertEqual(s["overview"], text)
        self.assertEqual(s["highlights"], [])

    def test_empty_and_none_are_safe(self):
        for value in ("", None, "   \n  "):
            s = structure_description(value)
            self.assertEqual(s["overview"], "")
            self.assertFalse(s["is_structured"])

    def test_extra_prose_paragraphs_go_to_more(self):
        text = ("Intro paragraph.\n"
                "\n"
                "• Soft cotton\n"
                "\n"
                "A second long paragraph about the brand story.\n"
                "\n"
                "And a third one with sizing notes.")
        s = structure_description(text)
        self.assertIn("Intro paragraph.", s["overview"])
        self.assertEqual(len(s["more"]), 2)
        self.assertIn("A second long paragraph about the brand story.", s["more"])

    def test_unknown_heading_kept_in_more(self):
        text = ("Intro.\n"
                "\n"
                "Sizing notes\n"
                "- Runs small, size up\n")
        s = structure_description(text)
        # unknown heading: neither the label nor its bullets are lost
        self.assertIn("Sizing notes", s["more"])
        all_text = " ".join(s["highlights"] + s["more"])
        self.assertIn("Runs small, size up", all_text)


class KeywordBoundaryTests(SimpleTestCase):
    """Care keywords match at word starts only — review regression: 'iron' must not
    match 'environmentally', 'wash' must not match 'brainwash'."""

    def test_embedded_keyword_does_not_misfile_feature_bullet(self):
        text = ("Intro.\n"
                "- Environmentally friendly packaging\n"
                "- Brainwash-proof design\n"
                "- Iron, steam or dry: low heat")
        s = structure_description(text)
        self.assertIn("Environmentally friendly packaging", s["highlights"])
        self.assertIn("Brainwash-proof design", s["highlights"])
        self.assertEqual(s["care"], ["Iron, steam or dry: low heat"])

    def test_suffixed_keyword_still_matches(self):
        text = "Intro.\n- Washing machine safe at 30C"
        s = structure_description(text)
        self.assertEqual(s["care"], ["Washing machine safe at 30C"])
