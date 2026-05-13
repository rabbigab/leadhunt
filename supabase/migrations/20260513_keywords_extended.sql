-- LeadHunt — Extension du catalogue de mots-clés
-- 15 catégories supplémentaires pour la communauté francophone en Israël

INSERT INTO keyword_categories (name, keywords) VALUES

  -- Garde d'enfants / babysitting
  ('garde_enfants', ARRAY[
    'baby-sitter', 'babysitter', 'baby sitter', 'garde enfant', 'garde enfants',
    'nounou', 'assistante maternelle', 'garderie', 'crèche', 'halte-garderie',
    'garde périscolaire', 'aide aux devoirs', 'soutien scolaire enfant',
    'accompagnement enfant', 'sortie école'
  ]),

  -- Cours particuliers / soutien scolaire
  ('cours_particuliers', ARRAY[
    'cours particulier', 'cours particuliers', 'soutien scolaire', 'prof particulier',
    'professeur particulier', 'répétiteur', 'cours hébreu', 'cours français',
    'cours maths', 'cours anglais', 'cours piano', 'cours guitare',
    'cours musique', 'cours dessin', 'coaching scolaire'
  ]),

  -- Avocat / juridique
  ('avocat', ARRAY[
    'avocat', 'avocate', 'avocat francophone', 'conseil juridique',
    'aide juridique', 'consultation juridique', 'droit du travail',
    'droit immobilier', 'contrat de travail', 'litige', 'notaire',
    'traduction juridique', 'immigrant visa', 'permis de travail'
  ]),

  -- Comptable / expert-comptable
  ('comptable', ARRAY[
    'comptable', 'expert-comptable', 'expert comptable', 'comptabilité',
    'déclaration impôts', 'déclaration fiscale', 'bilan comptable',
    'création entreprise', 'auto-entrepreneur', 'TVA', 'mas betzia',
    'heshbonaut', 'conseiller fiscal', 'optimisation fiscale'
  ]),

  -- Photographe
  ('photographe', ARRAY[
    'photographe', 'photographie', 'photographe mariage', 'photographe bar mitsvah',
    'photographe bat mitsvah', 'photographe bébé', 'shooting photo',
    'séance photo', 'photographe événement', 'photographe corporate',
    'vidéaste', 'vidéo mariage', 'making of'
  ]),

  -- Coach / accompagnement personnel
  ('coach', ARRAY[
    'coach', 'coaching', 'coach de vie', 'life coach', 'coach professionnel',
    'accompagnement personnel', 'développement personnel', 'coach sportif',
    'personal trainer', 'coach nutrition', 'diététicien', 'diététiste',
    'perte de poids', 'coach business', 'mentor'
  ]),

  -- Médecin / santé générale
  ('medecin', ARRAY[
    'médecin', 'medecin', 'médecin généraliste', 'médecin francophone',
    'docteur', 'pédiatre', 'gynécologue', 'gynécologie', 'dermatologue',
    'ophtalmologue', 'cardiologue', 'psychiatre', 'psychologue',
    'psychothérapeute', 'thérapeute', 'médecin de garde', 'urgence médicale'
  ]),

  -- Dentiste
  ('dentiste', ARRAY[
    'dentiste', 'dentiste francophone', 'chirurgien dentiste', 'chirurgien-dentiste',
    'orthodontiste', 'orthodontie', 'implant dentaire', 'couronne dentaire',
    'détartrage', 'soin dentaire', 'urgence dentaire', 'blanchiment dents',
    'appareil dentaire'
  ]),

  -- Nettoyage / ménage
  ('nettoyage', ARRAY[
    'femme de ménage', 'homme de ménage', 'nettoyage appartement', 'nettoyage maison',
    'aide ménagère', 'ménage', 'nettoyage bureaux', 'nettoyage de printemps',
    'grand nettoyage', 'pesah', 'nikayon', 'femme menage', 'service nettoyage',
    'nettoyage vitres', 'nettoyage moquette'
  ]),

  -- Jardinage / extérieur
  ('jardinage', ARRAY[
    'jardinier', 'jardinage', 'tonte pelouse', 'taille haie', 'taille arbres',
    'entretien jardin', 'aménagement jardin', 'arrosage automatique',
    'paysagiste', 'terrasse', 'pergola', 'clôture', 'dallage', 'gazon'
  ]),

  -- Traduction / interprétariat
  ('traduction', ARRAY[
    'traducteur', 'traductrice', 'traduction', 'interprète', 'interprétariat',
    'traduction hébreu français', 'traduction français hébreu',
    'traduction documents', 'traduction certifiée', 'traduction officielle',
    'traduction contrat', 'traduction médicale', 'traduction juridique',
    'accompagnement médecin', 'accompagnement administration'
  ]),

  -- Aide à domicile / seniors
  ('aide_domicile', ARRAY[
    'aide à domicile', 'aide domicile', 'auxiliaire de vie', 'aide personne âgée',
    'accompagnement senior', 'soins à domicile', 'infirmière à domicile',
    'garde malade', 'aide handicap', 'livraison courses', 'courses pour personne âgée',
    'accompagnement hôpital', 'homecare'
  ]),

  -- Informatique / tech
  ('informatique', ARRAY[
    'informaticien', 'dépannage informatique', 'réparation ordinateur',
    'virus informatique', 'récupération données', 'installation logiciel',
    'configuration réseau', 'wifi', 'imprimante', 'mac repair',
    'développeur', 'site internet', 'création site web', 'site vitrine',
    'application mobile', 'freelance dev'
  ]),

  -- Esthétique / beauté
  ('esthetique', ARRAY[
    'esthéticienne', 'estheticienne', 'épilation', 'manucure', 'pédicure',
    'onglerie', 'extension cils', 'maquillage', 'maquillage mariage',
    'coiffeur', 'coiffeuse', 'coiffure à domicile', 'brushing',
    'coloration', 'lissage', 'balayage', 'massage', 'spa à domicile'
  ]),

  -- Animaux / vétérinaire
  ('animaux', ARRAY[
    'vétérinaire', 'veterinaire', 'vet francophone', 'garde animaux',
    'pet sitter', 'petsitter', 'promenade chien', 'dog sitter',
    'toiletteur', 'toilettage', 'toilettage chien', 'toilettage chat',
    'pension animaux', 'dressage chien', 'éducateur canin'
  ])

ON CONFLICT (name) DO UPDATE SET
  keywords  = EXCLUDED.keywords,
  is_active = TRUE;

-- Vérification
SELECT name, array_length(keywords, 1) AS nb_keywords, is_active
FROM keyword_categories
ORDER BY name;
