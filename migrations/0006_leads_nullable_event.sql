-- Make event_id nullable in leads (standalone QR flow no longer uses events table)
PRAGMA foreign_keys=OFF;

CREATE TABLE leads_new (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  whatsapp_message_id  TEXT NOT NULL,
  from_phone           TEXT NOT NULL,
  wa_display_name      TEXT,
  event_id             TEXT,
  ref_id               TEXT,
  qr_id                INTEGER,
  match_method         TEXT NOT NULL,
  raw_text             TEXT,
  created_at           INTEGER NOT NULL
);

INSERT INTO leads_new
  (id, whatsapp_message_id, from_phone, wa_display_name, event_id, ref_id, qr_id, match_method, raw_text, created_at)
SELECT
  id, whatsapp_message_id, from_phone, wa_display_name, event_id, ref_id, qr_id, match_method, raw_text, created_at
FROM leads;

DROP TABLE leads;
ALTER TABLE leads_new RENAME TO leads;

PRAGMA foreign_keys=ON;
