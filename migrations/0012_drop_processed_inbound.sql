-- Webhook dedupe moved to KV (fallback path) + UNIQUE(leads.whatsapp_message_id).
-- Fails if duplicate whatsapp_message_id values already exist in leads (clean up first).
DROP TABLE IF EXISTS processed_inbound_messages;

CREATE UNIQUE INDEX idx_leads_whatsapp_message_id ON leads (whatsapp_message_id);
