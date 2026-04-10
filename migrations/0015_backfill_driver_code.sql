-- Auto-style driver codes for existing rows (matches app convention D{id}).
UPDATE drivers
SET driver_code = 'D' || CAST(id AS TEXT)
WHERE driver_code IS NULL OR TRIM(driver_code) = '';
