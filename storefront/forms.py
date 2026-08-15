"""Upload validation for admin-managed site imagery.

The homepage's crops and aspect ratios are part of the design. Rather than trust
an upload and hope, every file is checked before it can be saved: real raster
format, sane weight, minimum dimensions and an aspect ratio close enough to the
slot's. A rejected upload leaves the original static artwork in place.
"""
from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import SiteVisualAsset
from .visuals import (ALLOWED_FORMATS, ASPECT_TOLERANCE, MAX_UPLOAD_BYTES,
                      slot_choices, slot_config)


def _describe(cfg) -> str:
    return _("Recommended size: %(w)d×%(h)d px.") % {
        "w": cfg.get("recommended_width", 0), "h": cfg.get("recommended_height", 0)}


class SiteVisualAssetForm(forms.ModelForm):
    slot = forms.ChoiceField(choices=slot_choices, label=_("Slot"))

    class Meta:
        model = SiteVisualAsset
        fields = ("slot", "title", "image", "mobile_image", "alt_text",
                  "focal_point_x", "focal_point_y", "is_active")

    def _validate_upload(self, field_name, *, enforce_ratio=True):
        upload = self.cleaned_data.get(field_name)
        if not upload or not hasattr(upload, "file"):
            return upload                      # unchanged / cleared — nothing to check

        size = getattr(upload, "size", 0) or 0
        if size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError(
                _("This image is %(mb).1f MB. Please keep it under %(max)d MB so the "
                  "page stays fast.") % {"mb": size / (1024 * 1024),
                                         "max": MAX_UPLOAD_BYTES // (1024 * 1024)})

        try:
            from PIL import Image
            upload.file.seek(0)
            img = Image.open(upload.file)
            img.verify()
            upload.file.seek(0)
            img = Image.open(upload.file)
            fmt, (width, height) = img.format, img.size
            upload.file.seek(0)
        except Exception:
            raise forms.ValidationError(
                _("This file is not a readable image. Use JPG, PNG or WebP."))

        if fmt not in ALLOWED_FORMATS:
            raise forms.ValidationError(
                _("%(fmt)s files are not supported here. Use JPG, PNG or WebP.")
                % {"fmt": fmt or _("These")})

        cfg = slot_config(self.cleaned_data.get("slot") or self.instance.slot)
        if not cfg:
            return upload

        min_w, min_h = cfg.get("min_width", 0), cfg.get("min_height", 0)
        if width < min_w or height < min_h:
            raise forms.ValidationError(
                _("This image is %(w)d×%(h)d px — too small for this slot and it "
                  "would look soft. Minimum %(mw)d×%(mh)d px. %(rec)s")
                % {"w": width, "h": height, "mw": min_w, "mh": min_h,
                   "rec": _describe(cfg)})

        target = cfg.get("aspect_ratio")
        if enforce_ratio and target:
            ratio = width / height if height else 0
            if abs(ratio - target) / target > ASPECT_TOLERANCE:
                raise forms.ValidationError(
                    _("This image is %(shape)s (%(w)d×%(h)d px) but this slot needs a "
                      "%(target)s crop, so it would be cropped badly. %(rec)s")
                    % {"shape": _("portrait") if ratio < 1 else _("landscape"),
                       "w": width, "h": height,
                       "target": _("portrait") if target < 1 else _("landscape"),
                       "rec": _describe(cfg)})
        return upload

    def clean_image(self):
        return self._validate_upload("image")

    def clean_mobile_image(self):
        # the phone crop is deliberately a different shape — size/format only
        return self._validate_upload("mobile_image", enforce_ratio=False)

    def clean(self):
        cleaned = super().clean()
        has_image = bool(cleaned.get("image") or self.instance.image)
        if has_image and not (cleaned.get("alt_text") or "").strip():
            self.add_error("alt_text",
                           _("Describe the image so screen readers and search "
                             "engines can understand it."))
        for field in ("focal_point_x", "focal_point_y"):
            value = cleaned.get(field)
            if value is not None and not (0 <= value <= 100):
                self.add_error(field, _("Use a percentage between 0 and 100."))
        return cleaned
