-- Brands (coupon issuance); single default row seeded below.
CREATE TABLE brands (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  name                 TEXT NOT NULL,
  coupon_prefix        TEXT NOT NULL DEFAULT '',
  created_at           INTEGER NOT NULL
);

INSERT INTO brands (id, name, coupon_prefix, created_at)
VALUES (1, 'Default', 'CMP', strftime('%s', 'now'));

-- Driver registry (R2 URLs filled via admin upload endpoints).
CREATE TABLE drivers (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  external_ref         TEXT UNIQUE,
  driver_code          TEXT,
  name                 TEXT NOT NULL,
  phone                TEXT NOT NULL,
  qr_asset_url         TEXT,
  identity_asset_urls  TEXT,
  created_at           INTEGER NOT NULL
);

CREATE INDEX idx_drivers_phone ON drivers (phone);

-- Commission reporting weeks (unix seconds, half-open interval [start_at, end_at) recommended in app).
CREATE TABLE weeks (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  start_at             INTEGER NOT NULL,
  end_at               INTEGER NOT NULL,
  UNIQUE (start_at, end_at)
);

CREATE INDEX idx_weeks_bounds ON weeks (start_at, end_at);

-- Per-QR lead counts per week (filled by scheduled job only).
CREATE TABLE driver_lead_counts (
  qr_id                INTEGER NOT NULL,
  week_id              INTEGER NOT NULL REFERENCES weeks(id),
  lead_count           INTEGER NOT NULL,
  computed_at          INTEGER NOT NULL,
  PRIMARY KEY (qr_id, week_id)
);

CREATE INDEX idx_dlc_week ON driver_lead_counts (week_id);

-- Link inventory rows to drivers (optional).
ALTER TABLE qrs ADD COLUMN driver_id INTEGER REFERENCES drivers(id);

-- Lead extensions: brand-scoped coupon sent on WhatsApp.
ALTER TABLE leads ADD COLUMN coupon_code_sent TEXT;
ALTER TABLE leads ADD COLUMN brand_id INTEGER REFERENCES brands(id);
