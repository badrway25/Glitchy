"""Admin-editable homepage imagery (storefront/visuals.py + SiteVisualAsset).

Contract: the site ships with its designed static artwork and keeps working
untouched; an admin may override a named slot with an upload; anything invalid
falls back to the static asset rather than breaking the layout.
"""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Account
from storefront.models import SiteVisualAsset
from storefront.visuals import SLOTS, slot_config, visual_for


def _png(width=1600, height=720, color=(40, 40, 40)):
    """A real PNG so Pillow can read its dimensions."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return SimpleUploadedFile("visual.png", buf.getvalue(), content_type="image/png")


class SlotRegistryTests(TestCase):
    def test_every_slot_declares_guidance(self):
        self.assertTrue(SLOTS)
        for key, cfg in SLOTS.items():
            self.assertTrue(cfg.get("label"), key)
            self.assertTrue(cfg.get("fallback_static"), key)
            self.assertTrue(cfg.get("recommended_width"), key)
            self.assertTrue(cfg.get("recommended_height"), key)
            self.assertTrue(cfg.get("aspect_ratio"), key)

    def test_home_hero_slot_exists(self):
        self.assertIn("home_hero", SLOTS)
        self.assertIn("hero-editorial", slot_config("home_hero")["fallback_static"])


class FallbackTests(TestCase):
    def test_no_row_returns_static_fallback(self):
        v = visual_for("home_hero")
        self.assertFalse(v["is_custom"])
        self.assertIn("hero-editorial", v["url"])
        self.assertTrue(v["alt"])

    def test_inactive_row_falls_back(self):
        SiteVisualAsset.objects.create(slot="home_hero", image=_png(),
                                       alt_text="Custom hero", is_active=False)
        self.assertFalse(visual_for("home_hero")["is_custom"])

    def test_row_without_image_falls_back(self):
        SiteVisualAsset.objects.create(slot="home_hero", alt_text="No file")
        self.assertFalse(visual_for("home_hero")["is_custom"])

    def test_unknown_slot_is_safe(self):
        v = visual_for("does_not_exist")
        self.assertFalse(v["is_custom"])
        self.assertEqual(v["url"], "")


@override_settings(MEDIA_ROOT="/tmp/glitchy-visual-tests")
class CustomImageTests(TestCase):
    def test_active_row_wins_and_reports_custom(self):
        SiteVisualAsset.objects.create(slot="home_hero", image=_png(),
                                       alt_text="Studio campaign", is_active=True)
        v = visual_for("home_hero")
        self.assertTrue(v["is_custom"])
        self.assertIn("visual", v["url"])
        self.assertEqual(v["alt"], "Studio campaign")

    def test_mobile_image_is_exposed_when_present(self):
        SiteVisualAsset.objects.create(
            slot="home_hero", image=_png(), mobile_image=_png(900, 1120),
            alt_text="Hero", is_active=True)
        v = visual_for("home_hero")
        self.assertTrue(v["mobile_url"])
        self.assertNotEqual(v["mobile_url"], v["url"])

    def test_focal_point_becomes_object_position(self):
        SiteVisualAsset.objects.create(slot="home_hero", image=_png(),
                                       alt_text="Hero", is_active=True,
                                       focal_point_x=20, focal_point_y=80)
        self.assertEqual(visual_for("home_hero")["object_position"], "20% 80%")

    def test_alt_text_falls_back_to_slot_default_when_blank(self):
        SiteVisualAsset.objects.create(slot="home_hero", image=_png(),
                                       alt_text="", is_active=True)
        self.assertTrue(visual_for("home_hero")["alt"])


@override_settings(MEDIA_ROOT="/tmp/glitchy-visual-tests")
class ValidationTests(TestCase):
    def _form(self, **kwargs):
        from storefront.forms import SiteVisualAssetForm
        data = {"slot": "home_hero", "alt_text": "Alt", "is_active": True,
                "focal_point_x": 50, "focal_point_y": 50}
        data.update(kwargs.pop("data", {}))
        files = kwargs.pop("files", {})
        return SiteVisualAssetForm(data=data, files=files)

    def test_correct_aspect_ratio_accepted(self):
        form = self._form(files={"image": _png(2000, 900)})   # hero ~2.22
        self.assertTrue(form.is_valid(), form.errors)

    def test_wildly_wrong_aspect_ratio_rejected(self):
        form = self._form(files={"image": _png(600, 1600)})   # portrait into a hero
        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)

    def test_too_small_image_rejected(self):
        form = self._form(files={"image": _png(200, 90)})
        self.assertFalse(form.is_valid())

    def test_oversized_file_rejected(self):
        big = SimpleUploadedFile("huge.png", b"\x89PNG\r\n\x1a\n" + b"0" * (6 * 1024 * 1024),
                                 content_type="image/png")
        form = self._form(files={"image": big})
        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)

    def test_svg_rejected(self):
        svg = SimpleUploadedFile("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                                 content_type="image/svg+xml")
        form = self._form(files={"image": svg})
        self.assertFalse(form.is_valid())

    def test_alt_text_required_when_uploading(self):
        form = self._form(data={"alt_text": ""}, files={"image": _png(2000, 900)})
        self.assertFalse(form.is_valid())
        self.assertIn("alt_text", form.errors)


@override_settings(MEDIA_ROOT="/tmp/glitchy-visual-tests",
                   ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class HomepageRenderTests(TestCase):
    def test_home_renders_static_by_default(self):
        html = self.client.get("/").content.decode()
        self.assertIn("hero-editorial", html)
        self.assertEqual(html.count("<html"), 1)

    def test_home_renders_custom_hero_when_set(self):
        SiteVisualAsset.objects.create(slot="home_hero", image=_png(2000, 900),
                                       alt_text="Custom campaign", is_active=True)
        html = self.client.get("/").content.decode()
        self.assertIn("Custom campaign", html)
        self.assertIn("/media/", html)

    def test_custom_edit_card_image_renders(self):
        SiteVisualAsset.objects.create(slot="home_edit_1", image=_png(760, 950),
                                       alt_text="Neutrals custom", is_active=True)
        html = self.client.get("/").content.decode()
        self.assertIn("Neutrals custom", html)


@override_settings(MEDIA_ROOT="/tmp/glitchy-visual-tests",
                   ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class VisualsAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser("A", "B", "vis@x.com", "vis",
                                                  "pw-Str0ng!123")

    def test_admin_changelist_renders_with_previews(self):
        SiteVisualAsset.objects.create(slot="home_hero", image=_png(), alt_text="Hero",
                                       is_active=True)
        self.client.force_login(self.su)
        resp = self.client.get("/admin/storefront/sitevisualasset/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Home hero")

    def test_admin_requires_staff(self):
        resp = self.client.get("/admin/storefront/sitevisualasset/")
        self.assertEqual(resp.status_code, 302)

    def test_guidance_shown_on_change_form(self):
        asset = SiteVisualAsset.objects.create(slot="home_hero", alt_text="Hero")
        self.client.force_login(self.su)
        resp = self.client.get(f"/admin/storefront/sitevisualasset/{asset.pk}/change/")
        self.assertContains(resp, "2000")        # recommended width guidance
