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


## Local Development

# Start worker locally
npx wrangler dev

# Start frontend locally (proxies /api to wrangler on port 8787)
cd frontend && npm run dev

# Run new migration locally
npx wrangler d1 execute commute-leads --local --file=migrations/0004_leads_name.sql
