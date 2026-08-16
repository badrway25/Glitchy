# QA — Admin Mail Control Center (2026-08-16)

Branch: `fix/glitchy-admin-mail-control-center`. Local browser QA, **no deploy, no push**.
All values are throwaway (`*.example.test`, RFC-6761 reserved), the encryption key was a
throwaway Fernet key, email used the **console** backend (no real send), the assistant ran
in **mock** mode, and QA data was deleted from the dev DB afterwards. Admin access used a
dev-only auto-login middleware (normal server-side `login()`, no cookie injection) — not
committed, lives in the scratchpad.

## Verified in admin
- **Layout premium** — "Mail control" sidebar group (Email configuration / Outbox / Contact requests); Status + Resolved-configuration card; Addresses / SMTP transport / n8n sections; Save + "Send test email".
- **Empty / disabled state** — resolved panel shows *Support address: hidden (placeholder)*, *Email configured: no*, "This config is disabled — the server env is used instead". No customer-facing `support@example.com`.
- **Write-only + masked secrets** — the SMTP password field is a `PasswordInput` that renders **empty** ("leave blank to keep the current password"); after save the status shows only `•••• <last4> · fp:<fingerprint>`. The fingerprint is a one-way sha256 prefix (non-reversible).
- **No ciphertext / plaintext in HTML** — measured on every page: the Fernet ciphertext (the encrypted-blob format) and the entered password never appear in the rendered HTML.
- **Test send safe** — "Send test email" (superadmin-only, rate-limited) with provider=console → *"Test email sent — Sent 1 test message to admin@example.test"*; the message printed to the server log (console backend), no network, no secret in the result.
- **Permissions** — superadmin sees the editable form + secret fields; a non-superadmin staffer sees the page **fully read-only** (no editable fields, no password/secret fields); anonymous is redirected to `/admin/login/` (unit test).

## Verified customer-facing
- **Assistant** (refund/payment) → CONTACT SUPPORT + `/contact/?category=payment`, **no product cards**, **no** `support@example.com` (nor any address quoted — it routes to the form).
- **Contact center uses the admin config** — a submitted contact request routed its notification to **`admin@example.test`** (the DB Mail-Control-Center value; the env had `ADMIN_NOTIFY_EMAIL=""` and a placeholder support), proving the resolver prefers the admin config. Recipient is masked in the Outbox.

## Proof secrets never appear (HTML/log/screenshots)
| Surface | Password plaintext | Fernet ciphertext | Real email |
| --- | --- | --- | --- |
| Filled/masked change page | not present | not present | not present |
| Test-result page | not present | not present | not present |
| Staff (read-only) page | not present | not present | not present |
| Outbox list | not present | not present | not present (masked) |
Screenshots show only `•••• <last4> · fp:<fp>` (throwaway password) and `*.example.test` addresses.

## Screenshots
`admin-mail-settings-empty-warning.png` · `admin-mail-settings-filled-masked.png` ·
`admin-mail-test-safe-result.png` · `admin-mail-permission-denied.png` (staff, read-only) ·
`assistant-contact-no-placeholder.png` · `contact-uses-admin-mail-config.png`

## Note
QA surfaced that a non-superadmin staffer could still edit the *addresses* (not secrets).
Tightened so non-superadmins get the whole config read-only — committed separately as a fix
with a regression test.
