-- Which provisioned QR row (qrs.id / same ref id as leads.ref_id) is assigned to this driver.
ALTER TABLE drivers ADD COLUMN qr_ref_id INTEGER;
CREATE UNIQUE INDEX IF NOT EXISTS idx_drivers_qr_ref_id ON drivers (qr_ref_id);
