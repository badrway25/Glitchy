# Production Readiness Gaps (honest status)

Snapshot after the P0 (Phase 25) + P1 (Phases 26–27) remediation. Distinguishes
**code-ready** from **needs a manual/external action**. Not "all green".

## ✅ Code-ready (done & tested)
- Payment security: Stripe webhook signature-verified; PayPal **fail-closed** (server-verify or disabled).
- Fulfilment emails: in-production / shipped / tracking events fire on status transitions + admin actions.
- Static for prod: WhiteNoise + compression; `collectstatic` clean.
- Catalogue: real composition/fit/care + sale + colour/size variations (`seed_staging_catalog`).
- SEO: sitemap.xml, robots.txt, canonical, hreflang (EN/IT/FR), OG/Twitter.
- Legal/GDPR: Privacy / Terms / Cookie pages + cookie-consent banner.
- Refund accounting: idempotent (admin + webhook both SET, never double-count).
- Search unified with advanced filters + no-results discovery.
- Order tracking shown in-site.
- **Admin PII masking** (emails/phones/tokens masked in lists).
- Backfill is **dry-run by default**, never fabricates costs.
- Production security headers in code (`if not DEBUG:` SSL redirect, HSTS, secure cookies, nosniff, X-Frame DENY).
- Operational gates: `integration_status`, `credential_readiness_check.sh`, `rotate_secrets_check.sh`.

## ⛔ Pre-staging blocker (manual, owner-only)
- **Rotate the OpenAI key** and set `OPENAI_KEY_ROTATED=True`. Gate enforced; staging blocked until done.

## 🔧 Needs real credentials / external action (pre-production)
| Gap | Why it can't be closed in code | Action |
|-----|--------------------------------|--------|
| Stripe **live** | needs real live keys + a publicly reachable webhook | add live keys, register webhook, test a real order |
| Printify **push + real shipping** | needs real token/shop + authorisation to send orders | sync, set `SHIPPING_USE_PRINTIFY=True`, then `PRINTIFY_PUSH_ENABLED=True` when authorised |
| n8n + SMTP/Gmail/IMAP | needs real credentials + imported workflows | configure, import flows, verify delivery |
| GitHub remote + deploy | no remote configured | add remote, deploy to staging host |
| Postgres | dev uses SQLite | provision Postgres, set `DATABASE_URL` |
| Backfill historical costs | needs real Printify cost data | sync products, then `backfill_order_costs --apply` |
| Legal review | templates are a starting point | have counsel review Privacy/Terms/Cookie |

## Verdict
- Review: **YES** · Merge: **after manual approval** · Staging: **after OpenAI rotation** · Production: **NO** (the table above).
