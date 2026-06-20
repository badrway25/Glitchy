import os
import requests

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from store.models import Product, Variation, ProductImage
from printify_integration.printify_client import PrintifyClient
from category.models import Category


PRINTIFY_API_BASE = "https://api.printify.com/v1"


def unique_slug(name: str) -> str:
    base = slugify(name)[:180] or "product"
    slug = base
    i = 2
    while Product.objects.filter(slug=slug).exists():
        suffix = f"-{i}"
        slug = (base[:200 - len(suffix)] + suffix)
        i += 1
    return slug


def price_to_int_eur(v) -> int:
    try:
        cents = int(v)
    except Exception:
        return 0
    return max(0, round(cents / 100))


def fetch_blueprint_title(token: str, blueprint_id: int) -> str | None:
    """
    GET /v1/catalog/blueprints/{id}.json
    """
    try:
        url = f"{PRINTIFY_API_BASE}/catalog/blueprints/{blueprint_id}.json"
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if r.status_code != 200:
            return None
        data = r.json() or {}
        title = data.get("title")
        return title.strip() if isinstance(title, str) else None
    except Exception:
        return None


def get_category_for_printify_product(p: dict, fallback_category: Category) -> Category:
    """
    Decide Category in base al blueprint_id Printify.
    Mapping in settings:
      PRINTIFY_BLUEPRINT_CATEGORY_MAP = { blueprint_id(int): "category-slug" }
    """
    bp = p.get("blueprint_id")
    try:
        bp_int = int(bp) if bp is not None else None
    except Exception:
        bp_int = None

    mapping = getattr(settings, "PRINTIFY_BLUEPRINT_CATEGORY_MAP", {}) or {}
    cat_slug = mapping.get(bp_int)

    if not cat_slug:
        return fallback_category

    cat = Category.objects.filter(slug=cat_slug).first()
    if cat:
        return cat

    # crea categoria se manca
    name = cat_slug.replace("-", " ").title()
    cat, _ = Category.objects.get_or_create(
        slug=cat_slug,
        defaults={
            "category_name": name,
            "description": "Auto-created from Printify blueprint mapping",
        },
    )
    return cat


def _download_image(url: str, timeout: int = 30) -> tuple[str, bytes] | None:
    """
    Scarica un'immagine e ritorna (filename, bytes).
    """
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        filename = os.path.basename(url.split("?")[0]) or "image.jpg"
        return filename, r.content
    except Exception:
        return None


class Command(BaseCommand):
    help = "Sync Printify products into Django store.Product and store.Variation"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--max-pages", type=int, default=20)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--category", type=str, default="Printify")  # fallback
        parser.add_argument("--print-blueprints", action="store_true")   # stampa id->title e poi esce
        parser.add_argument(
            "--refresh-images",
            action="store_true",
            help="If set, deletes existing gallery images and re-downloads them from Printify.",
        )

    def handle(self, *args, **opts):
        token = getattr(settings, "PRINTIFY_API_TOKEN", "")
        shop_id = str(getattr(settings, "PRINTIFY_SHOP_ID", ""))

        if not token or not shop_id:
            self.stderr.write("Missing PRINTIFY_API_TOKEN or PRINTIFY_SHOP_ID in settings/.env")
            return

        client = PrintifyClient(token)

        limit = opts["limit"]
        max_pages = opts["max_pages"]
        dry = opts["dry_run"]
        print_blueprints = opts["print_blueprints"]
        refresh_images = opts["refresh_images"]

        # fallback category
        fallback_name = opts["category"]
        fallback_category, _ = Category.objects.get_or_create(
            category_name=fallback_name,
            defaults={"slug": slugify(fallback_name), "description": "Imported from Printify (fallback)"},
        )
        fallback_slug = fallback_category.slug

        overwrite_category = bool(getattr(settings, "PRINTIFY_SYNC_OVERWRITE_CATEGORY", False))

        created_p = updated_p = 0
        created_v = updated_v = 0

        seen_blueprints: set[int] = set()
        blueprint_titles: dict[int, str] = {}

        for page in range(1, max_pages + 1):
            payload = client.list_products(shop_id=shop_id, limit=limit, page=page)
            data = payload.get("data") or []
            if not data:
                break

            self.stdout.write(f"Page {page}: {len(data)} products")

            for p in data:
                p_id = str(p.get("id") or "")
                title = (p.get("title") or "").strip()
                desc = (p.get("description") or "").strip()
                if not p_id or not title:
                    continue

                # blueprint tracking
                bp = p.get("blueprint_id")
                try:
                    if bp is not None:
                        bp_int = int(bp)
                        seen_blueprints.add(bp_int)
                except Exception:
                    bp_int = None

                # price
                variants = p.get("variants") or []
                price_int = 0
                for v in variants:
                    if v.get("is_enabled"):
                        price_int = price_to_int_eur(v.get("price"))
                        break
                if price_int == 0 and variants:
                    price_int = price_to_int_eur(variants[0].get("price"))

                detected_category = get_category_for_printify_product(p, fallback_category)

                # upsert
                obj = Product.objects.filter(printify_product_id=p_id).first()
                is_new = obj is None

                if is_new:
                    obj = Product(
                        product_name=title,
                        slug=unique_slug(title),
                        description=desc[:500],
                        price=price_int,
                        stock=9999,
                        is_available=True,
                        category=detected_category,
                        printify_product_id=p_id,
                    )
                else:
                    obj.product_name = title
                    obj.description = desc[:500]
                    obj.price = price_int
                    obj.is_available = True
                    obj.stock = max(obj.stock, 9999)

                    # non sovrascrivere sempre la categoria
                    if overwrite_category or not obj.category_id or (obj.category and obj.category.slug == fallback_slug):
                        obj.category = detected_category

                if dry:
                    self.stdout.write(
                        f"  [DRY] {title} | printify_id={p_id} | blueprint_id={bp} | "
                        f"price={price_int} | category={detected_category.slug}"
                    )
                    continue

                obj.save()

                # ----------------------------
                # IMAGES (Printify)
                # - Save ALL images in ProductImage gallery
                # - Default image also becomes Product.images cover (optional)
                # - Idempotent: skip if gallery already exists unless --refresh-images
                # ----------------------------
                images = p.get("images") or []
                if images:
                    if refresh_images:
                        # delete old files + rows
                        old = ProductImage.objects.filter(product=obj)
                        for pi in old:
                            try:
                                if pi.image:
                                    pi.image.delete(save=False)
                            except Exception:
                                pass
                        old.delete()

                    existing_count = ProductImage.objects.filter(product=obj).count()
                    if existing_count == 0:
                        # download all images (no limit)
                        default_src = None

                        for img in images:
                            url = img.get("src")
                            if not url:
                                continue

                            is_def = bool(img.get("is_default"))
                            if is_def and not default_src:
                                default_src = url

                            dl = _download_image(url, timeout=30)
                            if not dl:
                                self.stdout.write(f"  ! gallery image download failed for '{title}'")
                                continue

                            filename, content = dl
                            pi = ProductImage(product=obj, is_default=is_def)
                            pi.image.save(filename, ContentFile(content), save=True)

                        # optional cover: set Product.images to default if empty
                        if not obj.images and default_src:
                            dl = _download_image(default_src, timeout=30)
                            if dl:
                                filename, content = dl
                                obj.images.save(filename, ContentFile(content), save=True)

                created_p += 1 if is_new else 0
                updated_p += 0 if is_new else 1

                # ----------------------------
                # Variations mapping
                # ----------------------------
                options = p.get("options") or []
                option_value_map = {}
                for opt in options:
                    opt_type = (opt.get("type") or "").lower()
                    for val in opt.get("values") or []:
                        option_value_map[val.get("id")] = (opt_type, (val.get("title") or "").strip())

                for v in variants:
                    if not v.get("is_enabled"):
                        continue
                    variant_id = str(v.get("id") or "")
                    if not variant_id:
                        continue

                    for oid in (v.get("options") or []):
                        mapped = option_value_map.get(oid)
                        if not mapped:
                            continue

                        opt_type, opt_title = mapped
                        if opt_type not in ("color", "size") or not opt_title:
                            continue

                        existing = Variation.objects.filter(
                            product=obj,
                            variation_category=opt_type,
                            variation_value__iexact=opt_title,
                        ).first()

                        if existing is None:
                            Variation.objects.create(
                                product=obj,
                                variation_category=opt_type,
                                variation_value=opt_title,
                                is_active=True,
                                printify_variant_id=variant_id,
                            )
                            created_v += 1
                        else:
                            changed = False
                            if not existing.printify_variant_id:
                                existing.printify_variant_id = variant_id
                                changed = True
                            if existing.is_active is False:
                                existing.is_active = True
                                changed = True
                            if changed:
                                existing.save()
                            updated_v += 1

        # print blueprint titles
        if print_blueprints:
            for bp_id in sorted(seen_blueprints):
                if bp_id not in blueprint_titles:
                    blueprint_titles[bp_id] = fetch_blueprint_title(token, bp_id) or "N/A"

            self.stdout.write(self.style.WARNING("Blueprints found (id -> title):"))
            for bp_id in sorted(blueprint_titles.keys()):
                self.stdout.write(self.style.WARNING(f"  {bp_id} -> {blueprint_titles[bp_id]}"))
            self.stdout.write(self.style.WARNING("Set PRINTIFY_BLUEPRINT_CATEGORY_MAP in settings.py."))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Products: +{created_p} / ~{updated_p} | Variations: +{created_v} / ~{updated_v}"
            )
        )
