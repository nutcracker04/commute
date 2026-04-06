-- Events / campaigns: template parts and WhatsApp destination
CREATE TABLE events (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  wa_phone_e164 TEXT NOT NULL,
  greeting TEXT NOT NULL DEFAULT 'Hey!',
  context_text TEXT NOT NULL,
  request_text TEXT NOT NULL DEFAULT 'I''d like more info',
  created_at INTEGER NOT NULL
);

-- One row per QR scan / redirect
CREATE TABLE scan_sessions (
  ref_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(id),
  full_prefilled_text TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);

CREATE INDEX idx_scan_sessions_expires ON scan_sessions (expires_at);
CREATE INDEX idx_scan_sessions_event ON scan_sessions (event_id);

-- WhatsApp delivery deduplication
CREATE TABLE processed_inbound_messages (
  whatsapp_message_id TEXT PRIMARY KEY,
  from_phone TEXT,
  processed_at INTEGER NOT NULL,
  ref_id TEXT,
  event_id TEXT,
  match_method TEXT
);

-- Captured leads after a confident match
CREATE TABLE leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  whatsapp_message_id TEXT NOT NULL,
  from_phone TEXT NOT NULL,
  event_id TEXT NOT NULL,
  ref_id TEXT,
  match_method TEXT NOT NULL,
  raw_text TEXT,
  created_at INTEGER NOT NULL
);

-- Local dev seed (replace in production via your admin flow)
INSERT INTO events (id, name, wa_phone_e164, greeting, context_text, request_text, created_at)
VALUES (
  'evt_demo',
  'Demo campaign',
  '15551234567',
  'Hey!',
  'Regarding the offer',
  'I''d like more info',
  strftime('%s', 'now')
);
