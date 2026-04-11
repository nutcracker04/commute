-- Wipe all application tables and reset INTEGER PRIMARY KEY AUTOINCREMENT counters.
-- Remote: npx wrangler d1 execute commute-leads --remote --file=scripts/clear_all_tables.sql
-- Local:  npx wrangler d1 execute commute-leads --local  --file=scripts/clear_all_tables.sql

PRAGMA foreign_keys = OFF;

DELETE FROM driver_lead_counts;
DELETE FROM leads;

UPDATE drivers SET qr_ref_id = NULL WHERE qr_ref_id IS NOT NULL;

DELETE FROM weeks;
DELETE FROM drivers;
DELETE FROM qrs;

DELETE FROM sqlite_sequence WHERE name IN (
  'qrs',
  'leads',
  'driver_lead_counts',
  'drivers',
  'weeks'
);

PRAGMA foreign_keys = ON;
