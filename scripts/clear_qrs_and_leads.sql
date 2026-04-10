-- One-time data wipe: leads + QR inventory (qrs).
-- Also clears DLC rows for those refs and unlinks drivers' Linked QR.
-- Run: npx wrangler d1 execute commute-leads --remote --file=scripts/clear_qrs_and_leads.sql
-- Local:  npx wrangler d1 execute commute-leads --local  --file=scripts/clear_qrs_and_leads.sql

PRAGMA foreign_keys = OFF;

DELETE FROM leads;
DELETE FROM driver_lead_counts;

UPDATE drivers SET qr_ref_id = NULL WHERE qr_ref_id IS NOT NULL;

DELETE FROM qrs;

-- Reset AUTOINCREMENT counters so new rows start from 1 again (SQLite keeps these in sqlite_sequence).
DELETE FROM sqlite_sequence WHERE name = 'qrs';
DELETE FROM sqlite_sequence WHERE name = 'leads';
DELETE FROM sqlite_sequence WHERE name = 'driver_lead_counts';

PRAGMA foreign_keys = ON;
