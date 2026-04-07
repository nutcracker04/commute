-- Rebuild scan_sessions so each physical scan gets its own row.
-- Previously qr_id was PRIMARY KEY so a second scan of the same QR overwrote the
-- first person's session. Now id is the PK and qr_id is a plain indexed column.
-- claimed_at: set by the queue consumer when an LCS match consumes this session row.
PRAGMA foreign_keys=OFF;

CREATE TABLE scan_sessions_new (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  qr_id      INTEGER NOT NULL REFERENCES qrs(id),
  full_text  TEXT NOT NULL,
  scanned_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  claimed_at INTEGER
);

INSERT INTO scan_sessions_new (qr_id, full_text, scanned_at, expires_at, claimed_at)
SELECT qr_id, full_text, scanned_at, expires_at, NULL
FROM scan_sessions;

DROP TABLE scan_sessions;
ALTER TABLE scan_sessions_new RENAME TO scan_sessions;

CREATE INDEX idx_scan_sessions_expires ON scan_sessions (expires_at);
CREATE INDEX idx_scan_sessions_qr     ON scan_sessions (qr_id);

PRAGMA foreign_keys=ON;
