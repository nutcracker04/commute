-- Add sender display name captured from WhatsApp webhook profile
ALTER TABLE leads ADD COLUMN wa_display_name TEXT;
