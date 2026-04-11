-- Full reset: (1) delete every row, (2) reset AUTOINCREMENT so next ids start at 1.
-- Remote: npx wrangler d1 execute commute-leads --remote --file=scripts/clear_all_tables.sql
-- Local:  npx wrangler d1 execute commute-leads --local  --file=scripts/clear_all_tables.sql

PRAGMA foreign_keys = OFF;

-- =============================================================================
-- STEP 1 — Remove all data from every application table (dependency-safe order)
-- =============================================================================

DELETE FROM driver_lead_counts;
DELETE FROM leads;

UPDATE drivers SET qr_ref_id = NULL WHERE qr_ref_id IS NOT NULL;

DELETE FROM weeks;
DELETE FROM drivers;
DELETE FROM qrs;

-- =============================================================================
-- STEP 2 — Reset AUTOINCREMENT counters (SQLite stores these in sqlite_sequence)
-- =============================================================================

DELETE FROM sqlite_sequence WHERE name IN (
  'qrs',
  'leads',
  'driver_lead_counts',
  'drivers',
  'weeks'
);

PRAGMA foreign_keys = ON;
