-- Ajoute le champ status sur detected_leads pour le CRM-lite Telegram
-- Valeurs : 'new' | 'contacted' | 'false_positive' | 'converted'

ALTER TABLE detected_leads
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'new'
    CHECK (status IN ('new', 'contacted', 'false_positive', 'converted')),
  ADD COLUMN IF NOT EXISTS status_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_detected_leads_status ON detected_leads(status);

-- Vérification
SELECT status, COUNT(*) FROM detected_leads GROUP BY status;
