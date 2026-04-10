-- Domain language: ref_id = qrs.id; promo_code_sent; drivers own QR ref + UPI URL; DLC surrogate id + ref_id.
PRAGMA foreign_keys=OFF;

-- Leads: drop brand FK, legacy text ref_id (replaced by integer ref_id from qr_id), rename columns
ALTER TABLE leads DROP COLUMN brand_id;
DROP TABLE IF EXISTS brands;

ALTER TABLE leads DROP COLUMN ref_id;
ALTER TABLE leads RENAME COLUMN qr_id TO ref_id;
ALTER TABLE leads RENAME COLUMN coupon_code_sent TO promo_code_sent;

-- Drivers: link to generated QR (qrs.id); UPI QR image URL from R2
ALTER TABLE drivers ADD COLUMN qr_ref_id INTEGER;
ALTER TABLE drivers ADD COLUMN upi_qr_asset_url TEXT;

UPDATE drivers
SET qr_ref_id = (
  SELECT q.id FROM qrs q WHERE q.driver_id = drivers.id
)
WHERE EXISTS (SELECT 1 FROM qrs q WHERE q.driver_id = drivers.id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_drivers_qr_ref_id ON drivers (qr_ref_id);

-- qrs: remove reverse link (driver holds qr_ref_id)
ALTER TABLE qrs DROP COLUMN driver_id;

-- DLC: surrogate id + ref_id
CREATE TABLE driver_lead_counts_new (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  ref_id               INTEGER NOT NULL,
  week_id              INTEGER NOT NULL REFERENCES weeks(id),
  lead_count           INTEGER NOT NULL,
  computed_at          INTEGER NOT NULL,
  UNIQUE (ref_id, week_id)
);

INSERT INTO driver_lead_counts_new (ref_id, week_id, lead_count, computed_at)
SELECT qr_id, week_id, lead_count, computed_at
FROM driver_lead_counts;

DROP TABLE driver_lead_counts;
ALTER TABLE driver_lead_counts_new RENAME TO driver_lead_counts;

CREATE INDEX idx_dlc_week ON driver_lead_counts (week_id);

PRAGMA foreign_keys=ON;
