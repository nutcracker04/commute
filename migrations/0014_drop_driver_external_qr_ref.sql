-- Remove external_ref and qr_ref_id. SQLite cannot DROP COLUMN on UNIQUE external_ref
-- (implicit index); rebuild table instead.
PRAGMA foreign_keys = OFF;

DROP INDEX IF EXISTS idx_drivers_qr_ref_id;

CREATE TABLE drivers_0014 (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  driver_code          TEXT,
  name                 TEXT NOT NULL,
  phone                TEXT NOT NULL,
  qr_asset_url         TEXT,
  upi_qr_asset_url     TEXT,
  identity_asset_urls  TEXT,
  created_at           INTEGER NOT NULL
);

INSERT INTO drivers_0014 (id, driver_code, name, phone, qr_asset_url, upi_qr_asset_url, identity_asset_urls, created_at)
SELECT id, driver_code, name, phone, qr_asset_url, upi_qr_asset_url, identity_asset_urls, created_at
FROM drivers;

DROP TABLE drivers;
ALTER TABLE drivers_0014 RENAME TO drivers;

CREATE INDEX IF NOT EXISTS idx_drivers_phone ON drivers (phone);

PRAGMA foreign_keys = ON;
