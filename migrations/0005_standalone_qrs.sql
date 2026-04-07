-- Standalone QR table (sequential IDs, permanent, no event dependency)
CREATE TABLE IF NOT EXISTS qrs (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  full_prefilled_text TEXT NOT NULL,
  provisioned_at   INTEGER NOT NULL
);

-- Per-scan temporary sessions (refreshed on every scan, TTL enforced by expires_at)
CREATE TABLE IF NOT EXISTS scan_sessions (
  qr_id      INTEGER PRIMARY KEY REFERENCES qrs(id),
  full_text  TEXT NOT NULL,
  scanned_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scan_sessions_expires ON scan_sessions (expires_at);

-- Add qr_id to leads (old rows will have NULL here; new rows use this instead of ref_id)
ALTER TABLE leads ADD COLUMN qr_id INTEGER;
