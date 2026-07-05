# PayPal Checkout Payload Integrity (2026)

**Branch:** `fix/glitchy-paypal-checkout-payload-integrity` (from
`release/staging-printify-fashion-store @ d9e7983`). **No migration.** Sandbox-only; no real
payment, no live keys, all tests mocked. Webhook still intentionally excluded (see §8).

## 1. Root cause — popup showed wrong amount / address / no phone
The PayPal order was created **CLIENT-SIDE** with a bare payload:
```js
createOrder: (data, actions) => actions.order.create({
  purchase_units: [{ amount: { value: String(amount) } }]   // template grand_total only
})
```
- **no `shipping`** → PayPal fell back to the **buyer's wallet default address**;
- **no `items` / `breakdown`** → a context-free total that didn't match what the shopper saw
  itemized in checkout;
- **no phone**, no brand, no locale;
- **no `shipping_preference`** → the wallet address was even editable, guaranteeing divergence
  from the checkout address.
Capture was already server-verified (`orders/paypal.py::verify_capture`, fail-closed) — the
gap was only on the CREATE side.

## 2. Fix — server-side order creation from the checkout snapshot
The payments page comes AFTER `place_order`, so the checkout snapshot **is the pending Order**
(address, E.164 phone, totals with shipping/tax/coupon). New pieces:

- **`payments/paypal_payload.py`** — deterministic Orders v2 builder. Decimal-only, 2-dp
  strings; items from the live cart (real name/price/qty, PHYSICAL_GOODS); breakdown
  `item_total + shipping + tax − discount` where **discount is derived** from the identity so
  the total is the real Glitchy grand total by construction; `PayloadMismatch` refuses
  non-balancing or non-positive totals; shipping name+address from the Order;
  `phone_number` only when the E.164 parses valid; `experience_context` with
  **`shipping_preference: SET_PROVIDED_ADDRESS`** (popup shows the checkout address, wallet
  can't replace it), `user_action: PAY_NOW`, brand name.
- **`orders/paypal.py::create_order(payload)`** — server-side POST `/v2/checkout/orders`
  (resolver credentials, sandbox base by default), fail-closed, logs only http status +
  PayPal `issue` code (never token/PII).
- **`POST /orders/paypal/create-order/`** — resolves the pending order (auth or guest
  session), refuses empty cart / missing address (before any PayPal call) / mismatched
  totals (409 "prevented for your safety"), maps PayPal issues to elegant translated
  messages (`SHIPPING_ADDRESS_INVALID` → "review the address…").
- **JS** — `createOrder` now just fetches that endpoint and returns the id; no amount ever
  computed client-side. `onApprove` keeps client capture + the existing server-side
  `verify_capture` (amount+currency+COMPLETED) before the order is marked paid; the capture id
  sent for verification is now the real capture id (from `purchase_units[].payments.captures`).

## 3. Premium PayPal panel (owner feedback)
The popup CONTENT is PayPal-hosted UI and cannot be styled — what was made premium:
`.pp-panel` card around the buttons (secure-checkout badge, spinner loading state, elegant
inline error box, trust note "you will review the exact total and address inside PayPal"),
SDK buttons styled `pill / black / 48px / vertical`, SDK loaded with `intent=capture` +
**locale** (it_IT / fr_FR / en_US by page language) and the payload carries `brand_name`, so
the popup itself shows Glitchy branding, the checkout address and the itemized total —
which is what actually makes it look right.

## 4. Consistency guarantees
- amounts: Decimal end-to-end; identity check refuses to create on any mismatch (tested);
- address: `SET_PROVIDED_ADDRESS` + address completeness gate before the popup opens;
- phone: same E.164 the checkout validated, split via phonenumbers, omitted when invalid
  (never breaks payment, never guessed);
- capture: server verify of amount/currency/COMPLETED unchanged (fail-closed).

## 5. Tests (13 new, all mocked)
Builder: exact breakdown 33.42 = 26.00+6.90+0.52−0.00, coupon-derived discount balances,
real items, checkout address mapping, SET_PROVIDED_ADDRESS + PAY_NOW, valid phone included /
invalid omitted, mismatch & non-positive refused. Endpoint: success returns PayPal id with the
full payload asserted on the wire (and no token in the response), missing address blocks with
zero PayPal calls, mismatch → 409, `SHIPPING_ADDRESS_INVALID` → elegant 502, unavailable →
"use card". Full suite green.

## 6. QA (sandbox, external calls blocked)
Premium panel renders (badge/note/loading), SDK blocked → elegant fallback message (no broken
buttons), create-order endpoint answers 502 with translated copy and zero secret/token leakage.
Screenshots in `docs/qa/paypal_checkout_payload_integrity/`. **Popup-content screenshots
(amount/address inside PayPal) require the owner's real sandbox credentials on the live
admin** — the payload is what the tests assert; the visual popup check is the first item of
the post-deploy sandbox smoke.

## 7. i18n
11 it + 9 fr new strings (panel copy + all error paths); strict `msgfmt -c` green.

## 8. Webhook — still excluded on purpose
No `/payments/paypal/webhook/` endpoint exists; the flow uses client approve + server-verified
capture. A future mini-phase should add: `POST /payments/paypal/webhook/` verifying the PayPal
transmission signature against the stored `paypal_webhook_id`, handling
CHECKOUT.ORDER.APPROVED / PAYMENT.CAPTURE.* events idempotently. Not needed for the sandbox
smoke.

## 9. Deploy notes
No migration, no new packages. `git pull` → `compilemessages -l it -l fr` → `collectstatic`
→ restart. Then the sandbox smoke: cart → checkout → PayPal tab → popup must show the Glitchy
total, itemized, with the checkout address locked. Live stays off behind the existing gates.
