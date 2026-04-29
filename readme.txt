# Commute Leads — Deployment Reference


## Environment Variable Management

There are two kinds of runtime config, kept and pushed separately:

  Plain vars (non-sensitive)
  ──────────────────────────
  Defined in wrangler.toml under [vars].
  Edit that section locally, then deploy — vars are pushed as part of the
  normal worker deploy. No separate step required.

  Secrets (sensitive)
  ───────────────────
  Stored encrypted in Cloudflare, never in the repo.
  Managed via secrets.json (gitignored). Template: secrets.example.json.

  Known secrets:
    WHATSAPP_OUTBOUND_AUTH_SECRET — Outbound sends only (BSP / Graph API auth header value)

  Inbound WhatsApp webhooks and admin JSON APIs are not authenticated in the worker.


## scripts/sync.sh — one command to push everything

  Usage
  ─────
  ./scripts/sync.sh                 Deploy code + vars from wrangler.toml
  ./scripts/sync.sh --secrets       Bulk-push secrets, then deploy code + vars
  ./scripts/sync.sh --secrets-only  Bulk-push secrets only (no code redeploy)

  How it works
  ────────────
  --secrets / --secrets-only  →  runs: npx wrangler secret bulk secrets.json
  (no --secrets-only flag)    →  runs: npx wrangler deploy
  Both steps can run together with --secrets.

  Wrangler secret bulk pushes all secrets in secrets.json atomically in a
  single API call. The worker is NOT redeployed when using --secrets-only,
  so the new secret values take effect immediately without touching code.

  First-time setup
  ────────────────
  1. cp secrets.example.json secrets.json
  2. Fill in real values in secrets.json (it is gitignored).
  3. ./scripts/sync.sh --secrets        # push secrets + deploy

  Updating only secrets later
  ───────────────────────────
  1. Edit secrets.json.
  2. ./scripts/sync.sh --secrets-only

  Updating only plain vars later
  ──────────────────────────────
  1. Edit wrangler.toml [vars].
  2. ./scripts/sync.sh                  # deploys code + updated vars

  Updating both at once
  ─────────────────────
  1. Edit secrets.json and/or wrangler.toml [vars].
  2. ./scripts/sync.sh --secrets




## Generate Secrets (optional)

# Outbound BSP auth only — if your send API needs a token
openssl rand -hex 32


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
npx wrangler d1 execute commute-leads --remote --file=migrations/0014_drop_driver_external_qr_ref.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0015_backfill_driver_code.sql
npx wrangler d1 execute commute-leads --remote --file=migrations/0016_drivers_qr_ref_id.sql

# If 0014 failed with "cannot drop UNIQUE column: external_ref", use the current 0014 file (table rebuild) and re-run.
# 0015 is safe to run again. If 0016 fails with duplicate column qr_ref_id, skip the ALTER and run only:
#   CREATE UNIQUE INDEX IF NOT EXISTS idx_drivers_qr_ref_id ON drivers (qr_ref_id);

# KV + Queues (if not already created for this account)
# npx wrangler kv namespace create commute-scan-sessions
# npx wrangler queues create commute-session-index
# Enable R2 in the dashboard, then: npx wrangler r2 bucket create commute-leads-assets

# Set secrets — copy the example and fill in values, then bulk-push in one command:
cp secrets.example.json secrets.json   # secrets.json is gitignored
# edit secrets.json with real values, then:
./scripts/sync.sh --secrets-only       # push secrets only (no code redeploy)
# or push secrets + deploy code + vars together:
./scripts/sync.sh --secrets

# --- Provider selection (env-driven universal adapter) ---
# Set WHATSAPP_PROVIDER in wrangler.toml [vars]. A single UniversalProvider reads WA_* vars
# to handle any BSP. Named presets supply defaults; "custom" = configure all paths manually.
# Values: generic (default/legacy), meta, 360dialog, twilio, gupshup, wati, custom

# --- Quick setup with a preset ---
# Set WHATSAPP_PROVIDER to a preset name and the common outbound vars. The preset fills in
# all WA_INBOUND_*, WA_OUTBOUND_*, WA_VERIFY_* defaults automatically.
#
# Common vars for ALL providers (wrangler.toml [vars]):
#   WHATSAPP_OUTBOUND_URL             = "<bsp api endpoint>"
#   WHATSAPP_OUTBOUND_AUTH_HEADER     = "<header name>"
#   WHATSAPP_BUSINESS_PHONE           = "91XXXXXXXXXX"   (E.164, no leading +)
# Secret (secrets.json):
#   WHATSAPP_OUTBOUND_AUTH_SECRET     = "<auth value>"

# Example: Meta Cloud API
#   WHATSAPP_PROVIDER             = "meta"
#   WHATSAPP_OUTBOUND_URL         = "https://graph.facebook.com/v25.0/{phone_number_id}/messages"
#   WHATSAPP_OUTBOUND_AUTH_HEADER = "Authorization"
#   Secrets: WHATSAPP_OUTBOUND_AUTH_SECRET = "Bearer <token>"

# Example: 360dialog
#   WHATSAPP_PROVIDER             = "360dialog"
#   WHATSAPP_OUTBOUND_URL         = "https://waba-v2.360dialog.io/messages"
#   WHATSAPP_OUTBOUND_AUTH_HEADER = "D360-API-KEY"
#   Secret: WHATSAPP_OUTBOUND_AUTH_SECRET = "<api-key>"

# Example: Twilio
#   WHATSAPP_PROVIDER             = "twilio"
#   WHATSAPP_OUTBOUND_URL         = "https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json"
#   WHATSAPP_OUTBOUND_AUTH_HEADER = "Authorization"
#   WHATSAPP_BUSINESS_PHONE       = "14155238886"
#   Secrets: WHATSAPP_OUTBOUND_AUTH_SECRET = "Basic base64(SID:Token)", WHATSAPP_AUTH_TOKEN = "<auth token>"

# Example: Gupshup
#   WHATSAPP_PROVIDER             = "gupshup"
#   WHATSAPP_OUTBOUND_URL         = "https://api.gupshup.io/wa/api/v1/msg"
#   WHATSAPP_BUSINESS_PHONE       = "917472850482"
#   WHATSAPP_GUPSHUP_APP_NAME     = "myapp"
#   Secret: WHATSAPP_OUTBOUND_AUTH_SECRET = "<api-key>" (sent as 'apikey' header)

# Example: WATI
#   WHATSAPP_PROVIDER             = "wati"
#   WHATSAPP_OUTBOUND_URL         = "https://live-mt-server.wati.io/{tenant-id}"
#   Secret: WHATSAPP_OUTBOUND_AUTH_SECRET = "<api-token>" (sent as Bearer)

# --- Any custom / unknown BSP (MSG91, Interakt, Kaleyra, AiSensy, etc.) ---
# Set WHATSAPP_PROVIDER = "custom", then configure all WA_* vars manually:
#
# Inbound field extraction (read your BSP's webhook docs for field names):
#   WA_INBOUND_UNWRAP       = "none" | "meta" | "form"   (how to deserialize the body)
#   WA_INBOUND_FROM_PATH    = "sender.phone"              (dot-path to sender phone)
#   WA_INBOUND_TEXT_PATH    = "message.text"               (dot-path to message text)
#   WA_INBOUND_ID_PATH      = "messageId"                  (dot-path to message ID)
#   WA_INBOUND_NAME_PATH    = "sender.name"                (dot-path to sender name)
#   WA_INBOUND_TS_PATH      = "timestamp"                  (dot-path to timestamp)
#   WA_INBOUND_TS_UNIT      = "s" | "ms"                   (default "s")
#   WA_INBOUND_FROM_STRIP   = ""                           (prefix to strip from phone)
#   WA_INBOUND_SKIP_WHEN    = "direction=outbound"         (skip rule: path=value or path!=value)
#   WA_INBOUND_TYPE_PATH    = "type"                       (message type field)
#   WA_INBOUND_TYPE_VALUE   = "text"                       (expected type value)
#
# Outbound body template (read your BSP's send API docs):
#   WA_OUTBOUND_BODY_TEMPLATE  = '{"to":"{to}","message":"{text_escaped}"}'
#   WA_OUTBOUND_CONTENT_TYPE   = "application/json" | "application/x-www-form-urlencoded"
#   WA_OUTBOUND_URL_TEMPLATE   = ""  (optional: if BSP encodes recipient in URL)
#   Placeholders: {to}, {from}, {text_escaped}, {text_urlencoded}, {text_json_urlencoded}, {base_url}, {app_name}
#
# Inbound POST verification (WA_VERIFY_*) is not implemented — all webhooks are accepted.
#
# GET challenge:
#   WA_GET_CHALLENGE      = "none" | "meta"

# --- Backward compatibility (generic / legacy) ---
# When WHATSAPP_PROVIDER is unset or "generic" and no WA_INBOUND_* vars exist, the legacy
# payload.py heuristic + whatsapp_outbound.py builder is used. No migration needed.

# Deploy worker (code + vars from wrangler.toml [vars])
./scripts/sync.sh
# or: npx wrangler deploy

# Verify
curl https://commute-leads-worker.harshithsai24.workers.dev/health
curl https://commute-leads-worker.harshithsai24.workers.dev/api/leads


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

# VITE_API_BASE_URL=https://commute-leads-worker.harshithsai24.workers.dev

# Optional worker var (wrangler.toml [vars]): ADMIN_AVAILABLE_REFS_MAX_LIMIT — cap per request for
# GET /api/qrs/available-refs (default 5000). The admin UI pages through until all unassigned ids load.


## Google Forms (optional)

# On submit, Apps Script POSTs multipart to POST /api/drivers (same as admin UI). Setup: scripts/google-forms/README.md


## WhatsApp webhook

# Callback URL (register in your BSP / Cloud API webhook settings)
https://commute-leads-worker.harshithsai24.workers.dev/webhook/whatsapp

# GET challenge (WA_GET_CHALLENGE): meta echoes hub.challenge; none returns plain "ok".
#
# Inbound parsing (driven by WA_INBOUND_UNWRAP + WA_INBOUND_*_PATH):
#   none  – parse JSON, extract fields via dot-paths
#   meta  – unwrap Meta entry→changes→value envelope, then extract per message
#   form  – parse as x-www-form-urlencoded, then extract via field names
#
# Outbound (driven by WA_OUTBOUND_BODY_TEMPLATE + WA_OUTBOUND_URL_TEMPLATE):
#   Template string with {to}, {text_escaped}, etc. placeholders — supports JSON, form-encoded, or empty body

# Example inbound JSON template (merge fields depend on your provider; must parse to text + sender phone):
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
- Drivers: `name`, `phone`; `driver_code` auto `D{id}`; **`qr_ref_id`** = same ref as `qrs.id` / `leads.ref_id`, required on create; UPI QR + identity required on create; PATCH cannot clear UPI/identity. Optional legacy `qr_asset_url` via `PUT /api/drivers/{id}/qr-image` only. No `external_ref`. `GET /api/qrs/available-refs` lists `qrs.id` values not yet assigned to a driver. Leads use `ref_id` = `qrs.id` from scans.
- Leads store `coupon_code_sent` after a match (prefix + random body; no brands table). Vars: `COUPON_CODE_PREFIX`, optional `COUPON_RANDOM_LENGTH`, `COUPON_WHATSAPP_TEMPLATE` (`{code}`, `{code_spaced}`). Legacy prefix keys: `PROMO_CODE_PREFIX`, `BRAND_COUPON_PREFIX`.
- `driver_lead_counts` has surrogate `id`, unique `(ref_id, week_id)`; counts increment on each new lead and the Sunday cron reconciles from `leads` for the prior IST week.


## Local Development

# Start worker locally
npx wrangler dev

# Start frontend locally (proxies /api to wrangler on port 8787)
cd frontend && npm run dev

# Local D1 schema: if `wrangler dev` errors with missing tables (e.g. no such table: weeks), your
# SQLite file is behind. Apply migrations in order. Old clones often stopped at 0003; run 0004–0016:
for f in \
  migrations/0004_leads_name.sql \
  migrations/0005_standalone_qrs.sql \
  migrations/0006_leads_nullable_event.sql \
  migrations/0007_scan_sessions_per_scan.sql \
  migrations/0008_drop_legacy_events_and_physical_qrs.sql \
  migrations/0009_commission_schema.sql \
  migrations/0010_drop_scan_sessions.sql \
  migrations/0011_domain_alignment.sql \
  migrations/0012_drop_processed_inbound.sql \
  migrations/0013_rename_promo_to_coupon.sql \
  migrations/0014_drop_driver_external_qr_ref.sql \
  migrations/0015_backfill_driver_code.sql \
  migrations/0016_drivers_qr_ref_id.sql
do
  npx wrangler d1 execute commute-leads --local --file="$f"
done

# If you already have qrs/weeks/current schema and only need newer patches, run the matching files only
# (do not re-run the full loop above).

# Weekly DLC cron: Sunday 06:00 UTC (see wrangler.toml [triggers]); manual run:
# curl -X POST https://<worker>/api/admin/run-dlc
#
# Test the scheduled handler locally (Python Worker): `npx wrangler dev --local --test-scheduled`,
# then GET http://localhost:8787/cdn-cgi/handler/scheduled (Wrangler’s /__scheduled route may 404 for Python).
