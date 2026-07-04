# City / Province / Postal Code Autocomplete for Checkout (2026)

**Branch:** `feat/glitchy-city-province-postal-autocomplete` (from
`release/staging-printify-fashion-store @ 0e0d9a8`). **No migration.** JS/template/i18n/tests
only. No real Google calls anywhere in tests/QA (stubbed).

## Problem
Autocomplete existed only on the street field. City, State/Province and Postal code were plain
inputs, so the "professional" destination-first flow still relied on free typing for the fields
that give the street its context.

## Architecture — one controller, four fields
`address-autocomplete.js` was refactored around a reusable **`PredictionField`** factory
(debounce, min-chars, premium list, keyboard nav, hint states, loading, blur-close, programmatic
fill guard). Four instances share one AutocompleteService/PlacesService pair and one billing
session token:

| Field | Places request | Prediction filter | On select (Place Details, address_components only) |
|---|---|---|---|
| City | `types:['(cities)']` + country restriction | all | fills city + province (admin L2/L1 short) + confirms country + **honest CAP** + resets street verification |
| State/Province | `types:['(regions)']` + country | admin_area L1/L2/L3 or locality | fills province (short name — "MI", "Lombardia") + resets verification |
| Postal code | `types:['(regions)']`, query biased with the typed city | only `postal_code` predictions | fills the real CAP; back-fills empty city/province; resets verification |
| Street | `types:['address']`, query biased "street, CAP city" + country | all | full fill (street+number, city, province, CAP, country) + `google_place_id` + `address_verified` |

## The honest CAP rule
The postal code is auto-filled **only when Google returns a `postal_code` component** on the
selected place:
- single-CAP towns (e.g. Vigevano) → the locality place carries `postal_code` → **auto-filled**
  (QA-verified: 27029);
- multi-CAP cities (Milano, Roma, Torino, Napoli…) → the locality place has NO `postal_code` →
  the field stays empty with the professional hint *"Postal code not unique here — it completes
  automatically when you pick the street"* (QA-verified);
- a full street selection always fills the exact CAP (QA-verified: Via Torino 21 → 20123);
- picking a CAP from the CAP suggestions uses the real `postal_code` place.
**A CAP is never guessed.** Nothing is country-hardcoded — the same component logic serves IT,
FR (postal_town/localities) and every supported country.

## Consistency (backend)
The verification contract is unchanged (strict never trusts hidden fields; place_id + fail-closed
server validation when the server key is configured). Improvement: the server-side Google
Address Validation request now also sends **`administrativeArea`** (the province), so an
incoherent city/province/CAP combination is flagged by Google in strict mode
(`hasUnconfirmedComponents` → blocked) and in warning mode (→ explicit confirmation checkbox).
Test asserts the field reaches the request body.

## UX / a11y
Same premium suggestion list for all four fields with per-type icons (city / map / envelope /
marker), main+secondary line, hover/arrow/Enter/Escape, `role=combobox/listbox/option`,
aria-expanded, blur-close, min-chars & no-results & not-configured hints, z-index safe, mobile
390 verified (no overflow, single flag phone-prefix intact).

## QA (Google stubbed — zero external calls)
Italy end-to-end: "Mil" → Milano suggested (restriction `it`) → select → province "MI" auto,
CAP empty + honest hint → "Via Tor" biased ("Via Tor, Milano") → select → CAP 20123 + verified
badge; province field "Mil" → admin-area options → "MI", verification reset; CAP "201" → real
20123 (query biased by Milano); Vigevano → CAP auto-filled; strict submit with fake city +
spoofed hidden → blocked, fields preserved; mobile 390 clean. 7 screenshots in
`docs/qa/city_province_postal_autocomplete_checkout/`.

## Privacy
Suggestions are user-initiated keystrokes to Google Places with session tokens (billing-correct);
only `address_components` are requested (never geometry/lat-lng); no input or address is ever
logged; server validation posts only what the shopper is submitting to us, read-only.

## Limits (honest)
- Live behaviour with a REAL browser key is a deploy-time smoke (all QA is stubbed by design).
- Province suggestions accept locality-type results too (Google often models Italian provinces
  through their capital city) — the filter is deliberately inclusive; selection always stores
  the administrative short name when present.
- The CAP list for a multi-CAP city (e.g. all 20121–20162 of Milano) is reachable by typing the
  CAP prefix; the city place itself cannot enumerate them (Places API limitation, documented).

## Deploy notes
No migration, no new packages. `git pull` → `compilemessages -l it -l fr` → `collectstatic` →
restart. Works automatically wherever the Google browser key + autocomplete are already enabled.
