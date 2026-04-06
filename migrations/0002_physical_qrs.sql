-- Pre-provisioned physical QR inventory: ref_id + text before print; TTL from first scan
CREATE TABLE physical_qrs (
  ref_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(id),
  full_prefilled_text TEXT NOT NULL,
  batch_id TEXT,
  label TEXT,
  external_sku TEXT,
  slug TEXT UNIQUE,
  provisioned_at INTEGER NOT NULL,
  first_scanned_at INTEGER,
  expires_at INTEGER
);

CREATE INDEX idx_physical_qrs_expires ON physical_qrs (expires_at);
CREATE INDEX idx_physical_qrs_event ON physical_qrs (event_id);
CREATE INDEX idx_physical_qrs_batch ON physical_qrs (batch_id);
CREATE INDEX idx_physical_qrs_first_scanned ON physical_qrs (first_scanned_at);
