"""Fetch + optimize premium homepage imagery from the Pexels API.

Curated, REPRODUCIBLE fetch: images are pinned by Pexels photo id (not a random
search), so re-running yields the same assets. For every photo it produces
responsive, optimized WebP + JPEG renditions under
``greatkart/static/images/home/pexels/`` and writes a secrets-safe ``CREDITS.json``
attribution manifest.

Security:
  * The API key is read ONLY from the ``PEXELS_API_KEY`` environment variable and
    is NEVER printed (not in errors, not in --verbosity output).
  * No key, token or PII is written to any committed file.
  * Without ``--apply`` the command is a dry run (reports, writes nothing).
  * Existing files are only overwritten with ``--apply`` and the action is logged.

Usage::

    # dry run - show the plan, fetch nothing
    python manage.py fetch_pexels_home_assets

    # actually download + optimize + write CREDITS.json
    PEXELS_API_KEY=... python manage.py fetch_pexels_home_assets --apply

    # refresh a single asset
    python manage.py fetch_pexels_home_assets --apply --only hero-editorial
"""
from __future__ import annotations

import io
import json
import os
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# --- Curated manifest --------------------------------------------------------
# Each entry is pinned by Pexels photo id for reproducibility. ``query`` records
# the search phrase the photo was discovered with (documentation only). Crops use
# ``bias`` = vertical focus (0 = top, 1 = bottom) when the source must be cut to
# the target aspect ratio.
ASSETS = [
    {
        "slug": "hero-editorial",
        "pexels_id": 20238933,
        "query": "minimalist fashion model neutral",
        "role": "Homepage hero - wide full-bleed (desktop) + portrait crop (mobile)",
        # Mirror horizontally so the model sits right-of-centre, leaving clean dark
        # negative space on the left for the headline/CTA copy.
        "flip": True,
        "renditions": [
            {"name": "hero-editorial-2000", "w": 2000, "h": 900, "bias": 0.28},
            {"name": "hero-editorial-1280", "w": 1280, "h": 620, "bias": 0.28},
            {"name": "hero-editorial-mobile-900", "w": 900, "h": 1120, "bias": 0.16},
        ],
    },
    {
        "slug": "editorial-fabric",
        "pexels_id": 5908251,
        "query": "folded premium clothing detail texture",
        "role": "Editorial 'Quality you can feel' split band",
        "renditions": [
            {"name": "editorial-fabric-1200", "w": 1200, "h": 900, "bias": 0.45},
            {"name": "editorial-fabric-700", "w": 700, "h": 560, "bias": 0.45},
        ],
    },
    {
        "slug": "edit-neutrals",
        "pexels_id": 11674381,
        "query": "minimalist beige fashion apparel",
        "role": "The Edit card - 'New neutrals'",
        "renditions": [
            {"name": "edit-neutrals-760", "w": 760, "h": 950, "bias": 0.22},
            {"name": "edit-neutrals-440", "w": 440, "h": 560, "bias": 0.22},
        ],
    },
    {
        "slug": "edit-tees",
        "pexels_id": 7665783,
        "query": "white t-shirt apparel studio",
        "role": "The Edit card - 'Everyday tees'",
        "renditions": [
            {"name": "edit-tees-760", "w": 760, "h": 950, "bias": 0.18},
            {"name": "edit-tees-440", "w": 440, "h": 560, "bias": 0.18},
        ],
    },
    {
        "slug": "edit-afterdark",
        "pexels_id": 29538549,
        "query": "dark moody fashion portrait",
        "role": "The Edit card - 'After dark'",
        "renditions": [
            {"name": "edit-afterdark-760", "w": 760, "h": 950, "bias": 0.30},
            {"name": "edit-afterdark-440", "w": 440, "h": 560, "bias": 0.30},
        ],
    },
]

API_PHOTO = "https://api.pexels.com/v1/photos/{id}"
UA = "Glitchy-Homepage/1.0 (+https://github.com/badrway25/Glitchy)"
WEBP_Q = 80
JPEG_Q = 82


class Command(BaseCommand):
    help = "Fetch + optimize premium homepage imagery from Pexels (key from env, never printed)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Download and write files (default: dry run).")
        parser.add_argument("--only", default="",
                            help="Limit to a single asset slug (e.g. hero-editorial).")
        parser.add_argument("--webp-quality", type=int, default=WEBP_Q)
        parser.add_argument("--jpeg-quality", type=int, default=JPEG_Q)

    # -- helpers --------------------------------------------------------------
    def _out_dir(self):
        base = settings.STATICFILES_DIRS[0]
        return os.path.join(base, "images", "home", "pexels")

    def _request(self, url, key=None):
        import requests
        headers = {"User-Agent": UA}
        if key:
            headers["Authorization"] = key
        r = requests.get(url, headers=headers, timeout=60)
        r.raise_for_status()
        return r

    @staticmethod
    def _crop_to(im, tw, th, bias):
        from PIL import Image
        w, h = im.size
        target, cur = tw / th, w / h
        if cur > target:                      # too wide -> trim sides (center)
            nw = int(round(h * target))
            x = (w - nw) // 2
            im = im.crop((x, 0, x + nw, h))
        else:                                 # too tall -> trim top/bottom (biased)
            nh = int(round(w / target))
            y = int(round((h - nh) * bias))
            im = im.crop((0, y, w, y + nh))
        return im.resize((tw, th), Image.LANCZOS)

    # -- main -----------------------------------------------------------------
    def handle(self, *args, **opts):
        from PIL import Image  # noqa: F401  (fail early if Pillow missing)

        apply = opts["apply"]
        only = opts["only"].strip()
        webp_q, jpeg_q = opts["webp_quality"], opts["jpeg_quality"]
        assets = [a for a in ASSETS if not only or a["slug"] == only]
        if only and not assets:
            raise CommandError(f"No asset with slug {only!r}.")

        out_dir = self._out_dir()
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Pexels homepage assets -> {out_dir}  ({'APPLY' if apply else 'DRY RUN'})"))

        key = (os.environ.get("PEXELS_API_KEY") or "").strip()
        if apply and not key:
            raise CommandError(
                "PEXELS_API_KEY is not set in the environment. Set it (it is read "
                "only from env and never printed) and re-run with --apply.")

        if not apply:
            for a in assets:
                names = ", ".join(r["name"] for r in a["renditions"])
                self.stdout.write(f"  - {a['slug']:18s} id={a['pexels_id']:<10} {a['role']}")
                self.stdout.write(f"      query={a['query']!r}")
                self.stdout.write(f"      renditions: {names}  (webp+jpg)")
            self.stdout.write(self.style.WARNING(
                "\nDry run - no network calls, no files written. Re-run with --apply."))
            return

        os.makedirs(out_dir, exist_ok=True)
        credits = []
        written = 0
        for a in assets:
            meta = self._request(API_PHOTO.format(id=a["pexels_id"]), key).json()
            # highest-quality source we can crop from
            src_url = meta["src"].get("original") or meta["src"]["large2x"]
            img = Image.open(io.BytesIO(self._request(src_url).content)).convert("RGB")
            if a.get("flip"):
                from PIL import ImageOps
                img = ImageOps.mirror(img)
            self.stdout.write(self.style.HTTP_INFO(
                f"  {a['slug']}: {meta['width']}x{meta['height']} by {meta['photographer']}"))
            for r in a["renditions"]:
                crop = self._crop_to(img, r["w"], r["h"], r.get("bias", 0.3))
                webp_path = os.path.join(out_dir, r["name"] + ".webp")
                jpg_path = os.path.join(out_dir, r["name"] + ".jpg")
                crop.save(webp_path, "WEBP", quality=webp_q, method=6)
                crop.save(jpg_path, "JPEG", quality=jpeg_q, optimize=True, progressive=True)
                kb_w = os.path.getsize(webp_path) // 1024
                kb_j = os.path.getsize(jpg_path) // 1024
                self.stdout.write(f"      {r['name']}: {r['w']}x{r['h']}  webp {kb_w}KB / jpg {kb_j}KB")
                written += 2
            credits.append({
                "slug": a["slug"],
                "role": a["role"],
                "query": a["query"],
                "pexels_id": a["pexels_id"],
                "pexels_url": meta["url"],
                "photographer": meta["photographer"],
                "photographer_url": meta["photographer_url"],
                "source_dimensions": f'{meta["width"]}x{meta["height"]}',
                "alt": meta.get("alt") or "",
                "files": [r["name"] + ".webp" for r in a["renditions"]]
                         + [r["name"] + ".jpg" for r in a["renditions"]],
                "downloaded": date.today().isoformat(),
                "license": "Pexels License (free to use, attribution appreciated) - https://www.pexels.com/license/",
            })

        credits_path = os.path.join(out_dir, "CREDITS.json")
        with open(credits_path, "w", encoding="utf-8") as f:
            json.dump({"source": "Pexels", "assets": credits}, f, indent=2, ensure_ascii=False)
        self.stdout.write(self.style.SUCCESS(
            f"\nWrote {written} files + CREDITS.json for {len(credits)} assets. "
            "(API key was read from env and never printed.)"))
