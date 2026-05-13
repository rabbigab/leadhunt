-- LeadHunt — Gestion des comptes Facebook et health monitoring

-- Comptes Facebook gérés par le scraper
CREATE TABLE IF NOT EXISTS fb_accounts (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  label                    TEXT NOT NULL,          -- ex: "Compte A", "Backup 1"
  fb_email                 TEXT UNIQUE NOT NULL,
  status                   TEXT NOT NULL DEFAULT 'warming'
                             CHECK (status IN ('warming','active','banned','retired')),
  warming_started_at       TIMESTAMPTZ,
  activated_at             TIMESTAMPTZ,            -- date passage en 'active'
  banned_at                TIMESTAMPTZ,
  groups_assigned          TEXT[] NOT NULL DEFAULT '{}', -- fb_group_ids assignés
  last_scrape_at           TIMESTAMPTZ,
  last_interaction_at      TIMESTAMPTZ,
  consecutive_zero_cycles  INTEGER NOT NULL DEFAULT 0,   -- cycles sans posts extraits
  total_leads_found        INTEGER NOT NULL DEFAULT 0,
  total_bans               INTEGER NOT NULL DEFAULT 0,
  notes                    TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Événements de santé (bans, pannes DOM, erreurs réseau)
CREATE TABLE IF NOT EXISTS health_events (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id   UUID REFERENCES fb_accounts(id),
  event_type   TEXT NOT NULL
                 CHECK (event_type IN ('ban_detected','dom_break','network_error',
                                       'login_fail','captcha','zero_posts','recovered')),
  group_id     TEXT,
  details      TEXT,
  resolved     BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_health_events_account  ON health_events(account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_events_resolved ON health_events(resolved) WHERE NOT resolved;

-- Interactions effectuées (audit + tuning)
CREATE TABLE IF NOT EXISTS fb_interactions (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id   UUID REFERENCES fb_accounts(id),
  action       TEXT NOT NULL CHECK (action IN ('like','comment','scroll','profile_view')),
  target_url   TEXT,
  group_id     TEXT,
  details      TEXT,          -- ex: texte du commentaire
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fb_interactions_account ON fb_interactions(account_id, created_at DESC);

-- Vérification
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('fb_accounts','health_events','fb_interactions');
