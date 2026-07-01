# Admin Forms Premium Polish + Printify Config UX Fix (2026)

**Branch:** `fix/admin-premium-forms-input-polish` (from
`release/staging-printify-fashion-store` @ `38b337b`). **No migration, no new dependency.** No
deploy, no secret exposure. Token stays write-only/masked.

## 1. Problem reported
The `/admin/printify_integration/printifyaccountconfig/add/` form looked broken: inputs
"invisible", elements overlapping, poor alignment.

## 2. Root cause
`PrintifyAccountConfigAdmin` uses a **custom `ModelForm`**. Django renders a custom form's
fields with its **default widgets** (`class="vTextField"`), which **Unfold does not style** —
Unfold only styles inputs that carry its own utility classes (injected by its widgets /
`formfield_for_dbfield`). Result: the text/number/password inputs rendered at ~20px height
with no border or background → effectively invisible. This affects **any** admin using a
custom form, which is why the owner suspected other forms too. Two secondary issues: Unfold's
sticky save-bar could scroll over the last fields, and my earlier `#content form { padding }`
was too broad (see §4).

## 3. Fixes
1. **Root-cause fix** — `PrintifyAccountConfigForm.__init__` now applies Unfold's own
   `INPUT_CLASSES` / `SELECT_CLASSES` / `CHECKBOX_CLASSES` to every widget, so the custom
   form's fields look native (38px, bordered, focus ring). The token stays a write-only
   `PasswordInput` (still never rendered).
2. **Form design-system + safety-net** — `greatkart/static/glitchy_admin/forms.css` (wired via
   `UNFOLD["STYLES"]`): a *safety net* that styles any admin input **without** Unfold classes
   (so a bare `.vTextField` is never invisible again), plus polish for help text, required
   markers, error state, readonly rows, and a **solid sticky save-bar** with a soft top divider
   and bottom padding so it no longer overlaps fields.
3. **Slim add form (owner feedback)** — auto/read-only fields (Token status, Token set-at,
   Token updated-by, Connection status, Created/Updated at) are **hidden on the add form**
   (they're empty on create) via `get_fieldsets(request, obj)`; the full layout returns when
   editing.
4. **Checkbox layout (owner feedback)** — the checkbox↔label gap is restored and the help text
   is moved **inline beside the label as a small grey span** (was cramped underneath).
5. **Changelist Filters button (owner feedback)** — it had grown to 128px because the earlier
   `#content form` padding hit the changelist **search** form and its sibling Filters button
   stretched. Scoped the padding to `form[id$="_form"]` (change/add only) → button back to a
   normal pill.
6. **Order add 500 (found in audit)** — `/admin/orders/order/add/` threw a `FieldError`
   (`created_at` is non-editable but was in the fieldsets). Orders are created by checkout, so
   `OrderAdmin.has_add_permission` now returns `False` — the broken page and the misleading
   "add" button are gone.
7. **Unused fields (owner feedback)** — `Category.cat_image` is referenced nowhere on the site
   or in code, so it's removed from the Category admin form (Unfold-styled). The column stays
   in the DB — **no migration, no data loss**.

## 4. Security
The token never appears in the add or change form HTML (test-asserted, incl. a config that has
a token); `PRINTIFY_CONFIG_KEY` never appears; non-superusers still cannot enter a token or
edit the publish/order flags; safe defaults unchanged. No token/PII in any screenshot.

## 5. Global audit (honest)
- **Fixed:** PrintifyAccountConfig add/change (the flagged page), the changelist Filters button,
  Order add 500, Category unused field.
- **Verified already fine:** Product and Category add/change inputs (they use default forms, so
  Unfold styles them — 38px, visible). Login form (prior phase). The safety-net CSS protects
  all of them going forward.
- **Not exhaustively re-styled:** every inline/related-widget/date-picker variant — the safety
  net covers visibility, but a deep per-widget redesign was out of scope.

## 6. QA
Local admin, 1440 / tablet 820 / 390, **light + dark**, **console 0**, **0 overflow**. 10
secret/PII-safe screenshots in `docs/qa/admin_forms_polish/`.
**Omitted on purpose:** the Order *change* form screenshot — it necessarily shows the
customer's real email/address to the admin, and the only orders carry the owner's real PII, so
a screenshot would leak PII (the form itself is verified to render + is covered by tests).

## 7. Limits
- The Order change form still shows raw customer fields (correct for an admin, but that's why
  it isn't screenshotted). A future pass could add a masked read-only "customer summary" block.
- The safety-net targets inputs Unfold missed; it deliberately does not restyle Unfold's own
  widgets. `cat_image` is hidden, not dropped (no migration).
