# Commute Leads — Deployment Reference

## Generate Secrets

# Admin API secret (use same value for worker + frontend .env)
openssl rand -hex 32

# MSG91 webhook secret
openssl rand -hex 20


## Worker (Cloudflare Workers)

# First-time: run all migrations on production D1
npx wrangler d1 execute commute-leads --remote --file=migrations/0001_initial.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0002_physical_qrs.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0003_drop_scan_sessions.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0004_leads_name.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0005_standalone_qrs.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0006_leads_nullable_event.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0007_scan_sessions_per_scan.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0008_drop_legacy_events_and_physical_qrs.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0009_commission_schema.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0010_drop_scan_sessions.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0011_domain_alignment.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0012_drop_processed_inbound.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0013_rename_promo_to_coupon.sql

# KV + Queues (if not already created for this account)
# npx wrangler kv namespace create commute-scan-sessions
# npx wrangler queues create commute-session-index
# Enable R2 in the dashboard, then: npx wrangler r2 bucket create commute-leads-assets

# Set secrets (one-time, stored encrypted in Cloudflare)
npx wrangler secret put ADMIN_API_SECRET
npx wrangler secret put MSG91_AUTH_KEY
npx wrangler secret put MSG91_INTEGRATED_NUMBER
npx wrangler secret put MSG91_WEBHOOK_SECRET

# Deploy worker
npx wrangler deploy

# Verify
curl https://commute-leads-worker.harshithsai24.workers.dev/health
curl -H "X-Admin-Key: <secret>" https://commute-leads-worker.harshithsai24.workers.dev/api/leads


## Frontend (Cloudflare Pages)

# Install dependencies
cd frontend && npm install

# Build
cd frontend && npm run build

# First deploy (creates the Pages project)
npx wrangler pages deploy dist --project-name=commute-leads

# Subsequent deploys
cd frontend && npm run build && npx wrangler pages deploy dist --project-name=commute-leads


## Frontend Environment Variables (set in Cloudflare Pages dashboard)
# Settings → Environment variables → Production

VITE_ADMIN_API_SECRET=<same value as ADMIN_API_SECRET>
VITE_API_BASE_URL=https://commute-leads-worker.harshithsai24.workers.dev


## MSG91 Webhook Setup

# URL to register in MSG91 Dashboard → WhatsApp → Webhook (New)
https://commute-leads-worker.harshithsai24.workers.dev/webhook/whatsapp

# Event type: On Inbound Request Received
# Custom header to add in MSG91 webhook config:
#   Key:   X-Webhook-Secret
#   Value: <same value as MSG91_WEBHOOK_SECRET>

# Inbound payload body to use in MSG91 webhook config:
{
  "crqid": "{{crqid}}",
  "companyId": "{{companyId}}",
  "requestedAt": "{{requestedAt}}",
  "customerNumber": "{{customerNumber}}",
  "customerName": "{{customerName}}",
  "requestId": "{{requestId}}",
  "reason": "{{reason}}",
  "uuid": "{{uuid}}",
  "integratedNumber": "{{integratedNumber}}",
  "direction": "{{direction}}",
  "contentType": "{{contentType}}",
  "text": "{{text}}",
  "content": "{{content}}",
  "messages": "{{messages}}",
  "ts": "{{ts}}"
}


## Data model (after 0011 + 0012 + 0013_rename_promo_to_coupon.sql)

- D1 tables: `qrs`, `leads`, `drivers`, `weeks`, `driver_lead_counts` (plus `d1_migrations` if using wrangler apply). Inbound dedupe: unique `leads.whatsapp_message_id` + KV `wi:nm:*` for unmatched fallback replies only.
- `ref_id` on leads and `driver_lead_counts` is the integer `qrs.id` (same id as `GET /r/{id}`).
- Drivers store `qr_ref_id` (FK to `qrs.id`), WhatsApp QR image URL in `qr_asset_url`, UPI QR in `upi_qr_asset_url`, plus identity URLs. Link QR ↔ driver only via driver fields (no `qrs.driver_id`).
- Leads store `coupon_code_sent` after a match (prefix + random body; no brands table). Vars: `COUPON_CODE_PREFIX`, optional `COUPON_RANDOM_LENGTH`, `COUPON_WHATSAPP_TEMPLATE` (`{code}`, `{code_spaced}`). Legacy prefix keys: `PROMO_CODE_PREFIX`, `BRAND_COUPON_PREFIX`.
- `driver_lead_counts` has surrogate `id`, unique `(ref_id, week_id)`; counts increment on each new lead and the Sunday cron reconciles from `leads` for the prior IST week.


## Local Development

# Start worker locally
npx wrangler dev

# Start frontend locally (proxies /api to wrangler on port 8787)
cd frontend && npm run dev

# Run new migrations locally (after prior chain is applied)
npx wrangler d1 execute commute-leads --local --file=migrations/0009_commission_schema.sql
npx wrangler d1 execute commute-leads --local --file=migrations/0010_drop_scan_sessions.sql
npx wrangler d1 execute commute-leads --local --file=migrations/0011_domain_alignment.sql
npx wrangler d1 execute commute-leads --local --file=migrations/0012_drop_processed_inbound.sql
npx wrangler d1 execute commute-leads --local --file=migrations/0013_rename_promo_to_coupon.sql

# Weekly DLC cron: Sunday 06:00 UTC (see wrangler.toml [triggers]); manual run:
# curl -X POST -H "X-Admin-Key: <secret>" https://<worker>/api/admin/run-dlc
