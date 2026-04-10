-- Legacy campaign inventory: superseded by qrs + /api/qrs. Worker never referenced these tables.
-- Drop child first (physical_qrs.event_id -> events.id).
DROP TABLE IF EXISTS physical_qrs;
DROP TABLE IF EXISTS events;
