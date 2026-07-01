# Ultra-Premium Admin Login (2026)

**Branch:** `feature/admin-premium-login-and-panel` (from
`release/staging-printify-fashion-store` @ `4675123`). **No migration, no new dependency.** No
deploy, no secret exposure.

## 1. Scope (honest)
The stated priority was the **admin login page**. That is what this phase delivers, in depth.
The rest of the admin (dashboard, product/order/Printify admin) was already elevated in the
previous two phases (Unfold "Commerce Studio", secure Printify vault, visual-analytics
dashboard) — so this phase focuses on the login and a matching brand mark rather than
re-doing already-premium surfaces. Further global polish is listed under *Limits*.

## 2. What the login now is
A **split-panel luxury sign-in** (`templates/admin/login.html`, extends Unfold's
`unauthenticated` layout so the admin CSS still loads):
- **Left brand hero** — espresso/ink gradient with a soft floating gold glow, the **animated
  Glitchy monogram**, "Glitchy · Commerce Studio", an editorial tagline, three honest **trust
  notes** (encrypted credential vault · safe defaults · live catalog health), and an
  **environment badge** (Local/Staging/Production).
- **Right form card** — an elevated card on warm ivory: "Sign in / Welcome back", the Unfold
  username+password fields (keeps Unfold's password reveal + focus styling), a gold submit
  button, a "Forgot your password?" link, and a "🔒 Secure access · staff only" note. A
  refined **error state** replaces Django's default error block.

## 3. The animated monogram (owner feedback)
The first version didn't match the site. Corrected to mirror the real Glitchy logo: a **cream
"G"** with **three horizontal tricolore strokes (green/white/red) breaking off to the left**
as glitch fragments — and they **oscillate left↔right** (staggered `translateX` "glitch"
motion), matching the brand's identity. Pure inline SVG + CSS keyframes, **reduced-motion
safe** (the strokes and the hero glow freeze under `prefers-reduced-motion`).

## 4. Design / UX
- Palette: espresso ink + champagne gold + cream, emerald ticks, ruby error — the same admin
  tokens (`.gl-*`), with a warm dark theme.
- Focus states, error state, password field, submit CTA, help text and microcopy all refined.
- **Responsive:** ≥900px split-panel; below that the hero becomes a top band and the form
  stacks (0 overflow at 390). Dark mode is warm and legible.

## 5. Security
No token, key, PII or `PRINTIFY_CONFIG_KEY` anywhere in the login HTML/CSS/JS (test-asserted +
verified live). A regression test also guards the `{# #}`-must-be-single-line rule (a
multi-line Django comment had briefly leaked as visible text and was fixed).

## 6. QA
`/admin/login/`, 1440 + 390, **light + dark**, **console 0**, **0 overflow**, error state
verified, the tricolore animation confirmed running (translateX oscillation). 4 secret/PII-safe
screenshots in `docs/qa/phase70_admin_login/`.

## 7. Limits / next (honest)
- This phase did **not** re-work the change-forms, list filters, or add drag-and-drop — those
  remain as delivered by Unfold + phases 68–69. Real follow-ups if you want to keep pushing:
  a sticky save-bar on change forms, saved/quick filters on the product list, a richer
  Printify "control center" page (beyond the config admin + dashboard card), and applying the
  animated monogram to the sidebar header.
- The monogram is a faithful SVG reinterpretation of the PNG logo (the brand ships only PNGs);
  a shared SVG asset could later be reused on the storefront too.
