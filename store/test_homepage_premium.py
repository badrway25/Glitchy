"""Phase 58: premium dynamic homepage — wide Pexels hero, 'The Edit' cards,
accessible motion. Verifies render, responsive imagery, a11y, i18n, no secrets,
and reduced-motion guards. No real data; assets are local (no Pexels hotlink)."""
import json
import pathlib

from django.conf import settings
from django.test import TestCase

BASE = pathlib.Path(settings.BASE_DIR)
SRC = BASE / "greatkart" / "static"
CSS = SRC / "css" / "premium.css"
JS = SRC / "js" / "home-motion.js"
PEXELS_DIR = SRC / "images" / "home" / "pexels"
DOC = BASE / "docs" / "PREMIUM_DYNAMIC_HOMEPAGE_PEXELS_2026.md"
SRC_DOC = BASE / "docs" / "image-sources" / "PEXELS_HOME_ASSETS_2026.md"


class HomepagePremiumTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # The Edit cards map to these real category slugs; seed them so we test the
        # real wiring (cards -> category pages) rather than the /store fallback.
        from category.models import Category
        for name, slug in [("Shirts", "shirts"), ("T Shirt", "t-shirt"),
                           ("Jackets", "jackets")]:
            Category.objects.get_or_create(slug=slug, defaults={"category_name": name})

    def _html(self, path="/"):
        return self.client.get(path).content.decode()

    # -- hero render ----------------------------------------------------------
    def test_hero_wide_renders(self):
        html = self._html("/")
        self.assertIn('class="hero-x"', html)
        self.assertIn("hero-x-title", html)
        self.assertIn("hero-x-cta", html)

    def test_hero_uses_picture_with_webp_and_mobile_source(self):
        html = self._html("/")
        self.assertIn("<picture", html)
        self.assertIn('type="image/webp"', html)
        # art-directed mobile crop
        self.assertIn("hero-editorial-mobile-900", html)
        # responsive desktop widths
        self.assertIn("hero-editorial-2000", html)
        self.assertIn("hero-editorial-1280", html)

    def test_hero_img_has_dimensions_and_priority(self):
        """width/height (no CLS) + fetchpriority high (LCP) on the hero <img>."""
        html = self._html("/")
        self.assertIn('width="2000"', html)
        self.assertIn('height="900"', html)
        self.assertIn('fetchpriority="high"', html)

    def test_hero_preload_present(self):
        html = self._html("/")
        self.assertIn('rel="preload"', html)
        self.assertIn("hero-editorial-1280.webp", html)

    # -- the edit cards -------------------------------------------------------
    def test_edit_cards_render_with_real_category_links(self):
        html = self._html("/")
        self.assertEqual(html.count('class="edit-card"'), 3)
        # links resolve to real category pages (seeded slugs)
        self.assertIn("/store/category/shirts/", html)
        self.assertIn("/store/category/t-shirt/", html)
        self.assertIn("/store/category/jackets/", html)

    # -- imagery / alt text ---------------------------------------------------
    def test_all_home_pexels_images_have_alt(self):
        html = self._html("/")
        # every <img> that points at a pexels home asset must carry a non-empty alt
        import re
        imgs = re.findall(r"<img[^>]+home/pexels/[^>]*>", html)
        self.assertTrue(imgs, "expected pexels <img> tags on the homepage")
        for tag in imgs:
            self.assertRegex(tag, r'alt="[^"]+"', f"missing alt: {tag[:80]}")

    def test_non_lcp_images_lazy(self):
        html = self._html("/")
        # edit + editorial imagery is lazy; the hero is NOT (it is LCP)
        self.assertIn('loading="lazy"', html)
        hero = html.split("hero-x-scrim")[0]
        self.assertNotIn('loading="lazy"', hero)

    def test_no_external_pexels_hotlink(self):
        """Homepage must serve LOCAL assets, never hotlink images.pexels.com."""
        html = self._html("/")
        self.assertNotIn("images.pexels.com", html)
        self.assertNotIn("api.pexels.com", html)

    # -- i18n EN/IT/FR --------------------------------------------------------
    def test_strings_localized(self):
        self.assertIn("Find your look", self._html("/"))
        it = self._html("/it/")
        self.assertIn("Trova il tuo look", it)
        self.assertIn("La selezione", it)
        fr = self._html("/fr/")
        self.assertIn("Trouvez votre look", fr)
        self.assertIn("La sélection", fr)

    def test_no_duplicate_made_on_demand(self):
        """'Made on demand' lives once (the promise card), not repeated as chips."""
        html = self._html("/")
        self.assertLessEqual(html.count("Made on demand"), 1)

    # -- CSS / JS / motion ----------------------------------------------------
    def test_css_has_hero_and_edit_styles(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".hero-x", css)
        self.assertIn(".edit-card", css)
        self.assertIn("hero-kenburns", css)

    def test_css_reduced_motion_guard(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", css)
        # hero animation explicitly disabled under reduced motion
        self.assertIn(".hero-x-img{animation:none", css.replace(" ", ""))

    def test_js_reduced_motion_and_no_leak(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", js)
        self.assertIn("IntersectionObserver", js)
        self.assertNotIn("PEXELS", js)

    # -- assets present -------------------------------------------------------
    def test_optimized_assets_exist_webp_and_jpg(self):
        for name in ["hero-editorial-2000", "hero-editorial-1280",
                     "hero-editorial-mobile-900", "editorial-fabric-1200",
                     "edit-neutrals-760", "edit-tees-760", "edit-afterdark-760"]:
            self.assertTrue((PEXELS_DIR / f"{name}.webp").exists(), f"missing {name}.webp")
            self.assertTrue((PEXELS_DIR / f"{name}.jpg").exists(), f"missing {name}.jpg")

    def test_hero_assets_within_perf_budget(self):
        """Hero LCP asset must stay light (< 500KB) for fast first paint."""
        for fmt in ("webp", "jpg"):
            kb = (PEXELS_DIR / f"hero-editorial-2000.{fmt}").stat().st_size / 1024
            self.assertLess(kb, 500, f"hero-editorial-2000.{fmt} too big: {kb:.0f}KB")

    # -- documentation + attribution, no secrets ------------------------------
    def test_pexels_credits_documented_no_secret(self):
        credits = PEXELS_DIR / "CREDITS.json"
        self.assertTrue(credits.exists())
        data = json.loads(credits.read_text(encoding="utf-8"))
        self.assertEqual(data["source"], "Pexels")
        self.assertTrue(data["assets"])
        for a in data["assets"]:
            self.assertIn("photographer", a)
            self.assertIn("pexels_url", a)
        # no key leaked anywhere in the manifest
        raw = credits.read_text(encoding="utf-8")
        self.assertNotIn("Authorization", raw)
        self.assertNotIn("PEXELS_API_KEY", raw)

    def test_docs_present(self):
        self.assertTrue(DOC.exists(), "missing PREMIUM_DYNAMIC_HOMEPAGE_PEXELS_2026.md")
        self.assertTrue(SRC_DOC.exists(), "missing PEXELS_HOME_ASSETS_2026.md")

    def test_fetch_command_reads_key_from_env_only(self):
        """The fetch command must read the key from env and never print it."""
        cmd = (BASE / "storefront" / "management" / "commands"
               / "fetch_pexels_home_assets.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("PEXELS_API_KEY")', cmd)
        self.assertIn("never printed", cmd.lower().replace("\n", " "))
