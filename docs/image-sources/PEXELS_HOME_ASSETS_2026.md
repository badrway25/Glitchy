# Homepage imagery — Pexels sources & attribution (2026)

All homepage editorial photography is sourced from **Pexels** under the
[Pexels License](https://www.pexels.com/license/) (free to use, attribution
appreciated). Images were fetched **by photo id** (reproducible) with the
`fetch_pexels_home_assets` management command, then cropped and re-encoded to
optimized **WebP + JPEG** renditions stored locally under
`greatkart/static/images/home/pexels/`. **The site serves the local assets only —
it never hotlinks Pexels.**

The machine-readable manifest is `greatkart/static/images/home/pexels/CREDITS.json`.
No API key, token, or credential is stored in any committed file — the key is read
only from the `PEXELS_API_KEY` environment variable and is never printed.

To refresh:

```bash
# key is read from env, never printed; --apply writes files + CREDITS.json
PEXELS_API_KEY=… python manage.py fetch_pexels_home_assets --apply
```

| Use on site | Pexels ID | Photographer | Source | Discovery query | Local renditions |
|---|---|---|---|---|---|
| **Hero** (wide full-bleed + mobile portrait) | [20238933](https://www.pexels.com/photo/portrait-of-woman-in-black-and-white-20238933/) | [Alessandra Shalbe](https://www.pexels.com/@alessandra-shalbe-859114866) | 7952×4472 | `minimalist fashion model neutral` | `hero-editorial-2000`, `-1280`, `-mobile-900` (webp+jpg) |
| **Editorial split** ("Quality you can feel") | [5908251](https://www.pexels.com/photo/close-up-shot-of-light-brown-cotton-5908251/) | [Mike Murray](https://www.pexels.com/@content-prod-co) | 6000×4000 | `folded premium clothing detail texture` | `editorial-fabric-1200`, `-700` (webp+jpg) |
| **The Edit — New neutrals** (→ Shirts) | [11674381](https://www.pexels.com/photo/a-hand-holding-a-hanger-with-white-polo-long-sleeves-11674381/) | [Marina Podrez](https://www.pexels.com/@marina-podrez-3269296) | 4480×6720 | `minimalist beige fashion apparel` | `edit-neutrals-760`, `-440` (webp+jpg) |
| **The Edit — Everyday tees** (→ T-shirts) | [7665783](https://www.pexels.com/photo/woman-in-white-crew-neck-t-shirt-and-blue-denim-jeans-sitting-on-a-chair-7665783/) | [Heitor Verdi](https://www.pexels.com/@heitorverdifotos) | 4016×6016 | `white t-shirt apparel studio` | `edit-tees-760`, `-440` (webp+jpg) |
| **The Edit — After dark** (→ Jackets) | [29538549](https://www.pexels.com/photo/moody-portrait-of-a-woman-in-urban-setting-29538549/) | [Travel with Lenses](https://www.pexels.com/@travel-with-lenses-734723610) | 4073×6110 | `dark moody fashion portrait` | `edit-afterdark-760`, `-440` (webp+jpg) |

**Downloaded:** 2026-06-29. All images are people/fabric studio/editorial shots
with no visible watermark, no embedded text, and no third-party logos.

## Optimized rendition sizes (committed)

| File | Dimensions | WebP | JPEG |
|---|---|---|---|
| `hero-editorial-2000` | 2000×900 | ~13 KB | ~45 KB |
| `hero-editorial-1280` | 1280×620 | ~7 KB | ~22 KB |
| `hero-editorial-mobile-900` | 900×1120 | ~12 KB | ~36 KB |
| `editorial-fabric-1200` | 1200×900 | ~171 KB | ~213 KB |
| `editorial-fabric-700` | 700×560 | ~57 KB | ~72 KB |
| `edit-neutrals-760` | 760×950 | ~8 KB | ~21 KB |
| `edit-tees-760` | 760×950 | ~36 KB | ~68 KB |
| `edit-afterdark-760` | 760×950 | ~13 KB | ~37 KB |
| (each card also has a `-440` mobile rendition) | 440×560 | 4–15 KB | 9–27 KB |

The dark, low-detail hero compresses extremely well (13 KB WebP at 2000 px), which
keeps the LCP asset very light.
