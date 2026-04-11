-- Run after clear_all_tables.sql. Expect every *_id below to be 1 if AUTOINCREMENT was reset.

INSERT INTO qrs (full_prefilled_text, provisioned_at)
VALUES ('__autoinc_test_qr__', strftime('%s', 'now'));

INSERT INTO weeks (start_at, end_at)
VALUES (999001, 999002);

INSERT INTO drivers (name, phone, created_at)
VALUES ('__autoinc_test__', '__autoinc_test_phone__', strftime('%s', 'now'));

INSERT INTO leads (
  whatsapp_message_id, from_phone, wa_display_name, ref_id,
  match_method, raw_text, created_at
)
VALUES (
  '__autoinc_test_wa__', '__autoinc_test_from__', NULL, 1,
  'test', NULL, strftime('%s', 'now')
);

INSERT INTO driver_lead_counts (ref_id, week_id, lead_count, computed_at)
VALUES (1, 1, 0, strftime('%s', 'now'));

SELECT
  (SELECT id FROM qrs WHERE full_prefilled_text = '__autoinc_test_qr__') AS qrs_id,
  (SELECT id FROM weeks WHERE start_at = 999001) AS weeks_id,
  (SELECT id FROM drivers WHERE phone = '__autoinc_test_phone__') AS drivers_id,
  (SELECT id FROM leads WHERE whatsapp_message_id = '__autoinc_test_wa__') AS leads_id,
  (SELECT id FROM driver_lead_counts WHERE ref_id = 1 AND week_id = 1) AS dlc_id;
