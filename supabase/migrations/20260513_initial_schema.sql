-- LeadHunt MVP — schéma initial
-- À exécuter dans le SQL Editor de ton projet Supabase dédié "leadhunt"

-- Posts détectés (leads)
CREATE TABLE IF NOT EXISTS detected_leads (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fb_post_id       TEXT UNIQUE NOT NULL,
  group_id         TEXT NOT NULL,
  group_name       TEXT,
  author_name      TEXT,
  post_content     TEXT NOT NULL,
  post_url         TEXT NOT NULL,
  matched_keywords TEXT[] NOT NULL DEFAULT '{}',
  matched_category TEXT NOT NULL,
  confidence       REAL NOT NULL DEFAULT 1.0,
  detected_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  notified         BOOLEAN NOT NULL DEFAULT FALSE,
  notified_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_detected_leads_detected_at ON detected_leads(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_detected_leads_category    ON detected_leads(matched_category);
CREATE INDEX IF NOT EXISTS idx_detected_leads_group_id    ON detected_leads(group_id);

-- Groupes surveillés
CREATE TABLE IF NOT EXISTS monitored_groups (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fb_group_id     TEXT UNIQUE NOT NULL,
  group_name      TEXT NOT NULL,
  group_url       TEXT NOT NULL,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  last_scraped_at TIMESTAMPTZ,
  posts_found     INTEGER NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Catégories de mots-clés
CREATE TABLE IF NOT EXISTS keyword_categories (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name       TEXT UNIQUE NOT NULL,
  keywords   TEXT[] NOT NULL DEFAULT '{}',
  is_active  BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Sessions de scraping (logs)
CREATE TABLE IF NOT EXISTS scrape_sessions (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at   TIMESTAMPTZ,
  groups_scraped INTEGER NOT NULL DEFAULT 0,
  posts_checked  INTEGER NOT NULL DEFAULT 0,
  leads_found    INTEGER NOT NULL DEFAULT 0,
  errors         TEXT[] NOT NULL DEFAULT '{}'
);

-- Données initiales : catégories de mots-clés MVP
INSERT INTO keyword_categories (name, keywords) VALUES
  ('plomberie',    ARRAY['plombier', 'plomberie', 'fuite d''eau', 'dégât des eaux', 'degat des eaux', 'chauffe-eau', 'chauffe eau', 'robinet', 'canalisation', 'wc bouché', 'toilettes bouchées', 'baignoire']),
  ('electricite',  ARRAY['électricien', 'electricien', 'prise électrique', 'prise electrique', 'disjoncteur', 'tableau électrique', 'tableau electrique', 'court-circuit', 'interrupteur', 'câblage', 'cablage', 'installation electrique']),
  ('serrurerie',   ARRAY['serrurier', 'serrure', 'porte bloquée', 'porte bloquee', 'clé perdue', 'cle perdue', 'verrou', 'blindage', 'ouverture porte', 'changement serrure', 'double de clé']),
  ('peinture',     ARRAY['peintre', 'peinture', 'enduit', 'tapisserie', 'papier peint', 'ravalement', 'lasure', 'vernis', 'rénovation murs', 'renovation murs']),
  ('bricolage',    ARRAY['bricoleur', 'bricolage', 'réparation', 'reparation', 'montage meuble', 'assemblage ikea', 'fixation', 'petits travaux', 'pose étagère', 'pose etagere', 'pose robinet', 'rideaux']),
  ('osteopathie',  ARRAY['ostéopathe', 'osteopathe', 'ostéopathie', 'osteopathie', 'manipulation', 'mal de dos', 'douleur dos', 'douleur cervicale', 'torticolis', 'lombalgie', 'sciatique', 'rééducation']),
  ('kine',         ARRAY['kiné', 'kine', 'kinésithérapeute', 'kinesitherapeute', 'physio', 'physiothérapeute', 'physiotherapeute', 'rééducation', 'reeducation', 'massage thérapeutique']),
  ('traiteur',     ARRAY['traiteur', 'buffet', 'réception', 'reception', 'cocktail', 'livraison repas', 'cuisine à domicile', 'cuisine a domicile', 'commande repas', 'bar mitsva', 'bar mitsvah', 'mariage traiteur']),
  ('demenagement', ARRAY['déménageur', 'demenageur', 'déménagement', 'demenagement', 'transport meubles', 'aide déménagement', 'aide demenagement', 'camion déménagement', 'monte-meuble'])
ON CONFLICT (name) DO NOTHING;

-- Vérification
SELECT 'detected_leads'     AS table_name, COUNT(*) FROM detected_leads
UNION ALL
SELECT 'monitored_groups',   COUNT(*) FROM monitored_groups
UNION ALL
SELECT 'keyword_categories', COUNT(*) FROM keyword_categories
UNION ALL
SELECT 'scrape_sessions',    COUNT(*) FROM scrape_sessions;
