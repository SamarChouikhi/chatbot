"""
Générateur de données fake pour le RAG ARIA.

Génère ~60 documents réalistes couvrant :
  - equipment_spec     : specs techniques par device (puissance, espace, historique pannes)
  - maintenance_proc   : procédures de maintenance par type d'anomalie
  - anomaly_playbook   : patterns connus avec causes racines et solutions
  - intervention_report: rapports d'intervention passés (fictions réalistes)
  - building_zone      : caractéristiques des zones du bâtiment
  - contract_info      : tarifs, horaires creuses, seuils budgétaires

Usage :
  cd chatbot/bws_pfe
  python -m rag.seed_fake_data
  python -m rag.seed_fake_data --clear   # efface et réinsère
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

DOCUMENTS: list[dict] = []


def _doc(doc_id, category, title, content, domain=None, device_id=None, keywords=""):
    DOCUMENTS.append({
        'doc_id'   : doc_id,
        'category' : category,
        'domain'   : domain,
        'device_id': device_id,
        'title'    : title,
        'content'  : content,
        'keywords' : keywords,
    })


# ══════════════════════════════════════════════════════════════════════════════
# SPECS ÉQUIPEMENTS — Énergie
# ══════════════════════════════════════════════════════════════════════════════

_doc('spec_en_001', 'equipment_spec', 'Compteur triphasé EN_001 — Tableau électrique principal RDC',
"""
Identifiant device : EN_001
Domaine : Énergie électrique
Espace : Tableau principal RDC — Bâtiment A
Type : Compteur d'énergie triphasé Schneider Electric PM5560
Puissance nominale : 400 kW (phases L1+L2+L3 combinées)
Courant maximal : 630 A par phase
Tension nominale : 400V AC

Caractéristiques de consommation typique :
- Consommation journalière normale : 180–220 kWh/j (hiver), 140–175 kWh/j (été)
- Pic de charge habituel : 8h–12h et 14h–17h (jours ouvrables)
- Consommation de veille (22h–6h) : max 15 kWh/h
- Phase L1 : alimentation HVAC et climatisation (50% du total)
- Phase L2 : éclairage et bureautique (30% du total)
- Phase L3 : serveurs et équipements techniques (20% du total)

Historique pannes connues :
- Jan 2023 : déséquilibre phases L1/L2 suite à surcharge climatisation — résolu par rééquilibrage
- Juil 2023 : pic anormal 14h-16h causé par démarrage simultané 3 groupes froids non planifié
- Problème récurrent en été (juin-août) : dépassement P90 dû à la climatisation haute charge

Maintenance préventive : vérification annuelle des connexions, nettoyage bornes, test relais.
Intervalle de calibration : 24 mois.
""",
domain='energy', device_id='EN_001',
keywords='énergie électrique compteur triphasé schneider tableau principal RDC climatisation HVAC pic consommation')

_doc('spec_en_042', 'equipment_spec', 'Compteur énergie EN_042 — Atelier de production',
"""
Identifiant device : EN_042
Domaine : Énergie électrique
Espace : Atelier de production — Hall B
Type : Compteur d'énergie Carlo Gavazzi EM340
Puissance nominale : 160 kW
Courant maximal : 250 A

Consommation typique :
- Jours ouvrables 6h–18h : 45–65 kWh/h (machines production actives)
- Pause 12h–13h : chute à 20–25 kWh/h
- Hors production (18h–6h, weekends) : 3–8 kWh/h (ventilation + sécurité)
- Pic du lundi matin (démarrage machines froides) : pointe jusqu'à 85 kWh/h

Historique pannes connues :
- Mar 2023 : consommation nocturne anormale (+300%) — cause : compresseur d'air laissé en marche
- Août 2023 : dérive progressive sur 10 jours — cause : encrassement filtre climatiseur atelier
- Nov 2023 : pic 14h-16h mardi/jeudi — cause : four à induction ancien cycle de chauffe

IMPORTANT : La dérive progressive (croissance >15% sur 7 jours) sur ce device est systématiquement
liée soit à un encrassement filtres HVAC, soit à une dégradation des condensateurs du variateur
de fréquence principal.

Maintenance : nettoyage filtres tous les 3 mois, vérification variateurs annuelle.
""",
domain='energy', device_id='EN_042',
keywords='énergie atelier production variateur filtre HVAC dérive compresseur machine')

_doc('spec_en_015', 'equipment_spec', 'Compteur énergie EN_015 — Serveurs datacenter',
"""
Identifiant device : EN_015
Domaine : Énergie électrique
Espace : Salle serveurs — Niveau -1 (Bâtiment C)
Type : Compteur Socomec Diris A60
Puissance nominale : 200 kW (alimentation ondulée UPS)
Charge typique : 120–145 kW (80% de la capacité nominale)

Profil consommation :
- Consommation quasi-constante 24h/24 : 118–148 kWh/h
- Variations normales liées aux backups (2h–4h UTC) : +8–12 kWh/h pendant 2h
- Pic mensuel lors des mises à jour système (dimanche 3h UTC) : +20 kWh/h pendant 1h

Seuils d'alerte configurés :
- WARNING : >155 kWh/h pendant plus de 30 min
- CRITICAL : >170 kWh/h (risque déclenchement disjoncteur 200A)

Historique incidents :
- Fév 2024 : consommation +18% sur 48h — cause : fuite liquide de refroidissement,
  réduction efficacité refroidissement, les serveurs ont augmenté leur fréquence CPU
- Tout pic soudain >20% sur ce device nécessite vérification immédiate du refroidissement
  avant suspicion d'une surcharge applicative

Maintenance : vérification mensuelle température ambiante salle serveurs (max 22°C),
inspection trimestrielle circuit de refroidissement.
""",
domain='energy', device_id='EN_015',
keywords='serveurs datacenter UPS refroidissement onduleur consommation constante backup')

_doc('spec_en_078', 'equipment_spec', 'Compteur énergie EN_078 — Parking sous-sol éclairage',
"""
Identifiant device : EN_078
Domaine : Énergie électrique
Espace : Parking souterrain niveaux -1 et -2
Type : Compteur Legrand 4 modèles
Puissance nominale : 40 kW (éclairage LED + ventilation)
Consommation journalière normale : 380–420 kWh/j

Profil éclairage :
- Éclairage détection mouvement : active pendant 30 min après dernier passage
- Éclairage minimal permanent (balisage) : 8 kWh/h constant
- Ventilation CO : active si CO > 50 ppm, consomme 12 kWh/h supplémentaires

Problèmes connus :
- Les détecteurs de mouvement défaillants maintiennent l'éclairage allumé en permanence
  → symptôme : consommation constante à 22–25 kWh/h au lieu de 8 kWh/h la nuit
- Ventilation CO bloquée en mode manuel → consommation fixe +12 kWh/h

PATTERN DIAGNOSTIC : Si consommation nocturne (22h–6h) dépasse 18 kWh/h de manière stable,
vérifier capteurs de mouvement avant toute autre cause.
""",
domain='energy', device_id='EN_078',
keywords='parking éclairage LED détection mouvement ventilation CO balisage nocturne')


# ══════════════════════════════════════════════════════════════════════════════
# SPECS ÉQUIPEMENTS — Eau
# ══════════════════════════════════════════════════════════════════════════════

_doc('spec_wm_001', 'equipment_spec', 'Compteur eau WM_001 — Réseau général bâtiment',
"""
Identifiant device : WM_001
Domaine : Eau
Espace : Nourrice principale — Local technique RDC
Type : Compteur volumétrique Itron Cyble 5
Débit nominal : 40 m³/h
Pression nominale : 10 bar

Consommation typique (bâtiment de bureaux 500 personnes) :
- Journée ouvrable : 12–18 m³/j
- Weekend : 0.5–1.2 m³/j (fuites admissibles + arrosage automatique si programmé)
- Consommation nocturne normale (1h–5h) : 0.02–0.08 m³/h (résiduel)

Seuils de détection fuite :
- FUITE MINEURE : débit nuit > 0.15 m³/h pendant >2h consécutives
- FUITE MAJEURE : débit nuit > 0.5 m³/h pendant >30 min
- ROW BREAK potentiel : débit nuit > 2 m³/h (alerte immédiate)

Historique incidents :
- Avr 2023 : fuite nuit 0.8 m³/h — joint défaillant vanne principale étage 2
- Sep 2023 : consommation weekend +400% — arrosage automatique mal programmé (8h au lieu de 1h)
- Jan 2024 : débit résiduel 0.3 m³/h nuit — WC cassette fuyante × 6 (vanne automatique ouverte)

IMPORTANT : Toute consommation nocturne (1h–5h) > 0.15 m³/h sur 2 nuits consécutives
doit déclencher inspection physique des canalisations, particulièrement aux jonctions du niveau 2.
""",
domain='water', device_id='WM_001',
keywords='eau compteur fuite nuit débit réseau jonction canalisation arrosage WC')

_doc('spec_wm_012', 'equipment_spec', 'Compteur eau WM_012 — Cuisines et cafétéria',
"""
Identifiant device : WM_012
Domaine : Eau
Espace : Bloc cuisine + cafétéria — Bâtiment B RDC
Type : Compteur Sensus iPERL 20mm
Débit nominal : 6 m³/h

Profil consommation :
- Service déjeuner 11h–14h : 0.8–1.2 m³/h
- Nettoyage matin 7h–8h : 0.4–0.6 m³/h
- Nettoyage soir 18h–19h : 0.3–0.5 m³/h
- Hors service (reste) : quasi nul (<0.02 m³/h)
- Consommation journalière totale : 4–7 m³/j

Problèmes courants :
- Lave-vaisselle industriel (350 couverts) : démarrage à 60°C augmente consommation 40%
  → pic 1.8 m³/h à 11h30 et 13h30 → normal, ne pas alerter
- Adoucisseur d'eau : cycle de régénération nocturne (2h–3h) consomme 0.25 m³ sur 30 min
  → peut déclencher fausse alerte LEAK_RISK — vérifier heure avant intervention

EXCLUSION FUITE : Si pic nocturne unique entre 2h et 3h de ≤0.5 m³ sur 30 min,
vérifier d'abord le cycle adoucisseur avant de déclarer une fuite.
""",
domain='water', device_id='WM_012',
keywords='cuisine cafétéria lave-vaisselle adoucisseur régénération nocturne débit eau')

_doc('spec_wm_025', 'equipment_spec', 'Compteur eau WM_025 — Tour de refroidissement HVAC',
"""
Identifiant device : WM_025
Domaine : Eau
Espace : Toiture — Tour de refroidissement unités CTA
Type : Compteur Badger Meter M2000
Débit nominal : 25 m³/h

Fonctionnement :
- Consommation liée à la charge thermique du bâtiment (évapo-condensation)
- Été (juin-août) : 3–8 m³/h pendant fonctionnement climatisation
- Hiver : quasi nul sauf réchauffage anti-gel (0.1 m³/h)
- Appoint automatique si niveau bas : 0.5 m³ par événement (max 3×/j)

CORRÉLATION CRITIQUE avec EN_001 (énergie HVAC) :
Si WM_025 augmente anormalement en même temps que EN_001, cause probable :
FUITE CIRCUIT PRIMAIRE de la tour de refroidissement — perte eau + perte efficacité thermique
→ boucle thermique force augmentation puissance + consommation eau simultanément.

Seuils critiques :
- > 10 m³/h hors période été : fuite circuit primaire (CRITICAL)
- Appoint > 5×/j : perte eau évaporative excessive, vérifier drift eliminator

Maintenance : inspection mensuelle drift eliminator, traitement biocide trimestriel (légionellose).
""",
domain='water', device_id='WM_025',
keywords='tour refroidissement HVAC évaporation légionellose circuit primaire dérive corrélation énergie')


# ══════════════════════════════════════════════════════════════════════════════
# SPECS ÉQUIPEMENTS — Gaz
# ══════════════════════════════════════════════════════════════════════════════

_doc('spec_gm_001', 'equipment_spec', 'Compteur gaz GM_001 — Chaufferie centrale',
"""
Identifiant device : GM_001
Domaine : Gaz naturel
Espace : Chaufferie — Sous-sol Bâtiment A
Type : Compteur à ultrasons Elster Instromet Q.Sonic 5
Débit nominal : 160 m³/h
Pression service : 0.5 bar (réseau moyenne pression)

Profil consommation saisonnier :
- Hiver (déc–fév) : 80–130 m³/h pendant plage chauffage 6h–20h
- Mi-saison (oct–nov, mar–avr) : 20–50 m³/h
- Été (mai–sep) : 2–8 m³/h (eau chaude sanitaire uniquement)
- Nuit toute l'année (22h–6h) : 1–3 m³/h (pilote + maintien température minimale)

Indicateurs de dysfonctionnement brûleur :
- Rendement nominal : 92% (chaudière condensation Viessmann Vitocrossal 300)
- Si consommation +15% pour même production thermique → encrassement échangeur
- Si consommation nocturne > 8 m³/h hors saison → vannes de zone restées ouvertes

PATTERN ANOMALIE MAINTENANCE : Toute augmentation monotone sur 7 jours + >15% au total
sur ce device correspond quasi systématiquement à une dégradation de l'échangeur thermique
ou à un encrassement de la chaudière (dépôts calcaires).
Diagnostic rapide : mesurer CO2 fumées (devrait être 8.5–9.5%) — si <8% = mauvais réglage air/gaz.

Entretien annuel obligatoire : nettoyage corps de chauffe, vérification combustion, ramonage.
""",
domain='gas', device_id='GM_001',
keywords='gaz chaufferie chaudière brûleur échangeur calcaire condensation rendement combustion')

_doc('spec_gm_008', 'equipment_spec', 'Compteur gaz GM_008 — Restaurant et cuisine professionnelle',
"""
Identifiant device : GM_008
Domaine : Gaz naturel
Espace : Cuisine professionnelle — Niveau 1 Bâtiment B
Type : Compteur BK-G25 Elster
Débit maximal : 40 m³/h

Profil consommation :
- Service matin (7h–10h) : 3–5 m³/h (fours préchauffage, eau chaude)
- Service déjeuner (10h–15h) : 12–18 m³/h (fours, plaques, friteuses)
- Nettoyage (15h–17h) : 2–4 m³/h (eau chaude nettoyage)
- Service dîner (18h–22h) : 8–12 m³/h
- Fermeture (22h–7h) : <0.3 m³/h (veilleuses uniquement)

Sécurité gaz :
- Détecteur gaz type ATEX en cuisine — déclenchement à 20% LIE
- Électrovanne de coupure automatique reliée aux alarmes incendie
- Vérification mensuelle obligatoire joints souples appareils de cuisson

ALERTE FUITE : Toute consommation > 0.8 m³/h entre 22h et 6h est anormale et nécessite
intervention immédiate (vérification veilleuses et joints). La fermeture de l'électrovanne
générale ramène à 0 — si persistance = fuite côté alimentation.
""",
domain='gas', device_id='GM_008',
keywords='gaz cuisine restaurant fours électrovanne ATEX veilleuse fuite nuit détecteur')


# ══════════════════════════════════════════════════════════════════════════════
# SPECS ÉQUIPEMENTS — Carburant
# ══════════════════════════════════════════════════════════════════════════════

_doc('spec_fm_003', 'equipment_spec', 'Capteur carburant FM_003 — Groupe électrogène de secours',
"""
Identifiant device : FM_003
Domaine : Carburant (gasoil)
Espace : Local groupe électrogène — Bâtiment C
Type : Capteur niveau fioul Afriso ELS
Capacité cuve : 2000 L
Consommation nominale groupe : 28 L/h à pleine charge (80 kVA)

Consommation normale :
- Tests mensuels (dernier samedi du mois, 10h–12h) : 56 L sur 2h = ~28 L/h
- Coupures secteur réelles : variable selon durée (base 28 L/h)
- Hors test et hors coupure : 0 L (groupe à l'arrêt)

DÉTECTION ANOMALIE :
- Consommation > 5 L/j sans test programmé → fuite sur circuit carburant ou vol
- Test mensuel > 70 L (>35 L/h) → problème rendement moteur, encrassement injecteurs
- Niveau baisse sans consommation → fuite cuve (priorité CRITICAL, risque environnemental)

Maintenance :
- Vérification mensuelle niveau + test démarrage
- Vidange huile tous les 6 mois
- Filtre gasoil annuel
- Purge eau condensation tous les 3 mois (base cuve)
""",
domain='fuel', device_id='FM_003',
keywords='carburant gasoil groupe électrogène cuve fuite test mensuel injecteur vidange')

_doc('spec_fm_v01', 'equipment_spec', 'Capteur carburant flotte véhicule VEH_001',
"""
Identifiant device : VEH_001
Domaine : Carburant (essence SP95)
Type véhicule : Renault Trafic 2.0 dCi — Véhicule utilitaire de livraison
Consommation homologuée : 7.2 L/100km (cycle mixte)
Consommation réelle typique flotte : 8.5–9.8 L/100km (charge + stop-and-go ville)

Facteurs de dégradation consommation :
- Pression pneus insuffisante (+1 L/100km par -0.5 bar)
- Filtre à air encrassé (+0.5–1.5 L/100km)
- Thermostat défaillant (+1–2 L/100km — moteur reste froid)
- Injecteurs encrassés (+1–2.5 L/100km)
- Conduite agressive (accélérations brusques) : jusqu'à +4 L/100km

Seuil d'alerte flotte : >35% au-dessus de la moyenne flotte hebdomadaire
(seuil conservateur pour exclure variations normales charges/trajets)

Maintenance recommandée si dépassement :
1. Vérifier pression pneus (cible 2.8 bar chargé)
2. Inspecter filtre à air
3. Lire codes défauts OBD (P0300-P0308 → injecteur, P0128 → thermostat)
4. Si aucun défaut visible → audit conduite chauffeur
""",
domain='fuel', device_id='VEH_001',
keywords='véhicule utilitaire consommation carburant pneus filtre injecteur thermostat OBD conduite')


# ══════════════════════════════════════════════════════════════════════════════
# PROCÉDURES DE MAINTENANCE — Par type d'anomalie
# ══════════════════════════════════════════════════════════════════════════════

_doc('proc_overconsumption_energy', 'maintenance_procedure',
     'Procédure diagnostic surconsommation électrique',
"""
PROCÉDURE : Diagnostic surconsommation énergie électrique
Applicable à : rec_type = OVERCONSUMPTION, domain = energy
Déclenchement : consommation > P90 baseline sur 26h consécutives

ÉTAPE 1 — Localiser les heures de pic (15 min)
  - Identifier les tranches horaires dépassant P90
  - Croiser avec le planning d'occupation du bâtiment
  - Si pic pendant heures de bureau : cause probable = équipement ajouté ou mode dégradé HVAC
  - Si pic nocturne (22h-6h) : équipement resté allumé ou variateur en mode manuel

ÉTAPE 2 — Analyse par phase (20 min, compteur triphasé)
  - L1 > 150% normal : problème HVAC ou climatisation
  - L2 > 150% normal : éclairage ou nouvelles charges bureautiques
  - L3 > 150% normal : équipements techniques ou informatiques

ÉTAPE 3 — Vérification physique (30–60 min)
  □ Température locaux HVAC : si T° diff vs consigne >2°C → chiller ou groupe froid en panne
  □ Éclairage zones vides : capteurs présence défaillants
  □ Armoires électriques : disjoncteurs temporaires ajoutés sans déclaration
  □ Sous-stations non surveillées : compresseurs d'air, pompes secondaires

ÉTAPE 4 — Actions correctives
  - Court terme : couper équipements non essentiels hors heures de bureau
  - Moyen terme : audit énergétique complet si surconsommation >48h
  - HVAC : nettoyage filtres ou rééquilibrage si cause confirmée

COÛT ESTIMÉ INTERVENTION : 2–4h technicien (100–200 TND)
""",
domain='energy',
keywords='surconsommation énergie pic phase HVAC éclairage diagnostic audit filtres climatisation')

_doc('proc_leak_water', 'maintenance_procedure',
     'Procédure diagnostic risque de fuite eau',
"""
PROCÉDURE : Diagnostic et intervention fuite eau
Applicable à : rec_type = LEAK_RISK, domain = water
Déclenchement : consommation nocturne (1h–5h) > P50 baseline

ÉTAPE 1 — Confirmer la fuite (5 min)
  - Relever le compteur général WM à 2h du matin précises
  - Revérifier après 30 min sans utilisation
  - Si différence > 0 L : fuite confirmée, mesurer le débit résiduel

ÉTAPE 2 — Localisation par isolation sectorielle (20–30 min)
  - Fermer vanne bâtiment B → si débit s'arrête : fuite bâtiment B
  - Procéder par dichotomie (étage par étage, zone par zone)
  - PRIORITÉ : vérifier les joints de vanne du niveau 2 (historique incidents)

ÉTAPE 3 — Points de fuite fréquents (inspecter en premier)
  □ WC : chasse d'eau (test colorant coloré) — fuite 3–15 L/h silencieuse
  □ Robinets goutte à goutte (cuisine, sanitaires)
  □ Raccords flexibles sous lavabos (durée de vie 7 ans)
  □ Vanne d'arrêt principale : corps de vanne corrodé
  □ Arrosage automatique : électrovanne bloquée ouverte

ÉTAPE 4 — Si fuite non localisée
  - Faire appel à détection de fuite acoustique (prestataire)
  - Délai max avant intervention : 24h si débit < 0.2 m³/h, IMMÉDIAT si > 1 m³/h

COÛT ESTIMÉ : Fuite WC : 30 min + joint (15 TND matériel). Fuite canalisation : 100–500 TND.
""",
domain='water',
keywords='fuite eau nuit WC robinet vanne isolation canalisation détection acoustique')

_doc('proc_maintenance_hvac', 'maintenance_procedure',
     'Procédure intervention dégradation HVAC progressive',
"""
PROCÉDURE : Maintenance préventive HVAC — dérive progressive
Applicable à : rec_type = MAINTENANCE, domain = energy ou gas
Déclenchement : hausse monotone consommation >15% sur 7 jours

CONTEXTE : Une croissance linéaire de consommation sur 7 jours sans événement particulier
indique quasi systématiquement une dégradation mécanique progressive, pas une anomalie ponctuelle.

ÉTAPE 1 — Identification rapide (10 min)
  - Calculer le taux de croissance : (J7-J1)/J1 × 100%
  - Si >40% : urgence intervention cette semaine
  - Si 15–40% : planifier dans les 5 jours ouvrables

ÉTAPE 2 — Diagnostic HVAC (45 min)
  □ Mesurer ΔP sur filtres à air (cible < 50 Pa, critique > 100 Pa)
  □ Vérifier température d'entrée/sortie échangeur (efficacité thermique)
  □ État des ailettes (corrosion, dépôts calcaires sur condenseur)
  □ Niveau de fluide frigorigène (manomètre BP/HP)
  □ Vérifier point de consigne régulateur — dérive capteur température

ÉTAPE 3 — Actions selon diagnostic
  - Filtres encrassés (ΔP > 80 Pa) : remplacement immédiat (20 min, 80–200 TND)
  - Échangeur colmaté : nettoyage haute pression (2h, 150–300 TND)
  - Fuite frigorigène : recharge R32/R410A (technicien certifié, 300–600 TND)
  - Dérive capteur : recalibration ou remplacement sonde (50–100 TND)

ÉCONOMIE ATTENDUE : nettoyage filtres → réduction consommation 10–25%.
""",
domain='energy',
keywords='HVAC maintenance filtres échangeur frigorigène dérive progressive CTA climatisation')

_doc('proc_maintenance_gas', 'maintenance_procedure',
     'Procédure intervention chaudière gaz — dérive consommation',
"""
PROCÉDURE : Maintenance chaudière gaz à condensation
Applicable à : rec_type = MAINTENANCE, domain = gas
Déclenchement : consommation gaz +15% sur 7 jours, tendance monotone

DIAGNOSTICS PRIORITAIRES (chaudière à condensation) :

1. MESURE RENDEMENT (15 min)
  - Analyser les fumées : CO2% (cible 8.5–9.5%), CO (< 50 ppm), O2 (3–5%)
  - Temperature fumées : < 60°C (condensation efficace), si > 80°C = échangeur encrassé
  - Rendement calculé selon PCI : doit être > 90%

2. INSPECTION ÉCHANGEUR (30 min)
  - Dépôts calcaires sur l'échangeur primaire → nettoyage acide faible
  - Corrosion sur siphon condensats → risque panne (remplacer si doute)
  - Vérifier débit retour : ΔT flow/return entre 10°C et 20°C (bon signe)

3. BRÛLEUR (20 min)
  - Nettoyer électrodes allumage (dépôts noirs)
  - Vérifier ajutage gaz (pas d'obstruction)
  - Pression gaz en aval vanne gaz : 17–20 mbar

4. CIRCUIT HYDRAULIQUE
  - Pression circuit chauffage : 1.5–2.5 bar à froid
  - Vase d'expansion : vérifier pression gaz (0.5 bar sous pression circuit)

RÉSULTAT ATTENDU : nettoyage complet annuel → retour consommation -10 à -20%.
Durée intervention : 3–4h technicien qualifié PG.
""",
domain='gas',
keywords='chaudière gaz condensation échangeur brûleur CO2 rendement calcaire maintenance annuelle')

_doc('proc_efficiency_fuel', 'maintenance_procedure',
     'Procédure audit efficacité carburant véhicule',
"""
PROCÉDURE : Audit consommation carburant véhicule utilitaire
Applicable à : rec_type = EFFICIENCY, domain = fuel
Déclenchement : consommation >35% au-dessus moyenne flotte sur 7 jours

SÉQUENCE DIAGNOSTIC (ordre d'intervention, du plus simple au plus complexe) :

1. VÉRIFICATION IMMÉDIATE (5 min, sans outillage)
  □ Pression pneus (manomètre embarqué ou pompe atelier) : cible 2.8 bar chargé, 2.5 bar vide
  □ État charge : surestimation poids transporté habituel ?
  □ Historique trajets semaine : plus de stop-and-go ou km supplémentaires ?

2. LECTURE OBD (15 min, valise diagnostic)
  □ Codes défaut actifs et en attente (P0XXX)
  □ Température liquide refroidissement en régime (cible 87–92°C) → P0128 si thermostat HS
  □ Valeurs live injecteurs : correction carburant ±5% normal, >10% suspect
  □ Pression rampe injection (common rail) : cible 1600 bar à pleine charge

3. INSPECTION PHYSIQUE (20 min)
  □ Filtre à air : tenu à la lumière, si opaque > 30% → remplacer (20 TND)
  □ Filtre à carburant : vérifier date dernier remplacement (tous les 40 000 km)
  □ Signe de fuite carburant sous le véhicule

4. AUDIT CONDUITE (comportemental)
  Si mécanique OK → analyser rapport télémétrie conducteur :
  - Freinages brusques > 3 m/s² : corriger conduite anticipative
  - Arrêts moteur tournant > 3 min : activer start-and-stop ou sensibiliser conducteur

ÉCONOMIE PRÉVUE : pneus corrects → -5 à -8%, filtre air → -3 à -6%, conduite éco → -10 à -20%.
""",
domain='fuel',
keywords='carburant véhicule audit OBD pneus filtre injecteur conduite éco thermostat télémétrie')

_doc('proc_budget_alert', 'maintenance_procedure',
     'Procédure gestion dépassement budgétaire énergie/eau/gaz',
"""
PROCÉDURE : Plan d'action dépassement budgétaire mensuel
Applicable à : rec_type = BUDGET_ALERT (tous domaines)
Déclenchement : projection fin de mois > +10% vs mois précédent

ACTIONS IMMÉDIATES (J0 — découverte alerte)

ÉNERGIE :
  1. Identifier les 3 plus gros consommateurs des 7 derniers jours via dashboard
  2. Vérifier si un équipement a été ajouté sans déclaration
  3. Activer programme ECO sur GTB : consigne chauffage -1°C, éclairage -20%
  4. Planifier éteindre équipements non critiques hors heures de bureau

EAU :
  1. Inspecter points de fuite connus (WC, cuisine) — voir procédure LEAK_RISK
  2. Vérifier si travaux ou nettoyage exceptionnel justifient la hausse
  3. Reporter arrosage automatique aux heures creuses

GAZ :
  1. Baisser consigne chauffage -1°C (économie 7% selon ADEME)
  2. Vérifier si chaudière est en mode été (eau chaude uniquement) en mi-saison
  3. Contrôler fuites sur réseau gaz (odorant perceptible dans chaufferie)

COMMUNICATION :
  - Informer responsable technique sous 24h
  - Si dépassement projeté >20% : escalader au directeur avec plan d'action

SUIVI : réévaluer projection tous les 3 jours jusqu'à fin de mois.
""",
keywords='budget dépassement mensuel plan action économie GTB consigne énergie eau gaz')

_doc('proc_optimization_energy', 'maintenance_procedure',
     'Procédure optimisation consommation heures creuses',
"""
PROCÉDURE : Optimisation consommation électrique heures creuses
Applicable à : rec_type = OPTIMIZATION, domain = energy
Déclenchement : consommation nocturne (22h–6h) > P50 baseline

PRINCIPES DE BASE :
Les heures creuses (22h–6h) doivent avoir une consommation minimale.
Toute consommation significative hors serveurs, sécurité et CVC minimal est potentiellement évitable.

AUDIT CONSOMMATION NOCTURNE (30 min, visite terrain à 23h) :
  □ Éclairage : bureaux éteints ? (ballasts défaillants restent allumés)
  □ Écrans et ordinateurs : en veille ou allumés ?
  □ Prises cafetières, chargeurs, imprimantes : branchés sans utilisation
  □ Climatisation individuelle split : arrêt automatique paramétré ?
  □ Distributeurs automatiques : déjà en mode éco nocturne ?
  □ Signalétique LED : nécessaire la nuit (niveaux -1 et -2) ?

ACTIONS RAPIDES HAUTE VALEUR :
  1. Programmer arrêt automatique éclairage général 21h30 via GTB
  2. Activer politique de mise en veille obligatoire PCs (GPO Active Directory 15 min)
  3. Installer minuteries sur prises cuisine et salle de pause
  4. Régler GTB : chauffe-eau collectif uniquement 22h30–5h (heures creuses tarif)

ÉCONOMIE ESTIMÉE selon taille bâtiment :
  - Éclairage nocturne éteint : -15 à -25 kWh/nuit
  - PCs en veille : -8 à -20 kWh/nuit
  - CVC réduit nocturne : -30 à -60 kWh/nuit
""",
domain='energy',
keywords='optimisation heures creuses nocturne veille éclairage GTB arrêt automatique audit')


# ══════════════════════════════════════════════════════════════════════════════
# PLAYBOOKS ANOMALIES — Patterns connus + causes racines
# ══════════════════════════════════════════════════════════════════════════════

_doc('playbook_energy_hvac_summer', 'anomaly_playbook',
     'Playbook : Pic consommation énergie — été, heures HVAC',
"""
PATTERN ANOMALIE : Surconsommation énergie 13h–17h, juin–août, +40–80% vs baseline
PROBABILITÉ CAUSE : HVAC / Climatisation (85%)

SIGNES DISTINCTIFS :
- Le pic se produit aux heures les plus chaudes de la journée (13h–17h)
- Corrélé à des températures extérieures >30°C
- Phase L1 principalement affectée (compresseurs)
- Disparaît le weekend (occupation nulle → thermostat en mode éco)

CAUSES RACINES CLASSÉES PAR FRÉQUENCE :
1. (40%) Filtres CTA encrassés → efficacité réduite → compresseurs compensent
2. (25%) Panne ou déréglage thermostat de régulation → climatisation tourne en continu
3. (20%) Fuite frigorigène partielle → COP dégradé, compresseur surchargé
4. (10%) Occupation anormalement élevée (événement non planifié → surcharge thermique)
5. (5%) Disfonctionnement registres de bypass VMC

ACTION RECOMMANDÉE :
- Technicien CVC sur site dans les 4h si pic > +80%
- Si pic 40–60% : planifier diagnostic filtres le lendemain matin (avant 9h)
- Mesure immédiate palliative : activer consigne de 26°C au lieu de 23°C (économie 15%)
""",
domain='energy',
keywords='HVAC climatisation été pic consommation filtre frigorigène thermostat COP compresseur')

_doc('playbook_water_night_leak', 'anomaly_playbook',
     'Playbook : Consommation eau anormale nuit — causes et probabilités',
"""
PATTERN ANOMALIE : Consommation eau > P50 baseline entre 1h et 5h du matin
PROBABILITÉ CAUSE : Fuite active (70%), Fausse alarme (30%)

CAUSES RÉELLES — FRÉQUENCE OBSERVÉE :
1. (35%) WC à chasse continue — joint clapets usé. Débit : 3–15 L/h par WC.
   Détection : colorant alimentaire dans réservoir, présence couleur cuvette après 15 min.
2. (20%) Robinet goutte-à-goutte cuisine/sanitaires.
   Débit : 0.1–2 L/h. Inspecter visuellement.
3. (15%) Joint vanne d'arrêt vieilli. Débit : 0.5–5 L/h sous pression.
4. (10%) Fuite canalisation encastrée (niveau 2). Débit variable. Détection acoustique requise.
5. (10%) Arrosage automatique mal programmé.
6. (10%) Fuite vanne pressostatique local technique.

FAUSSES ALARMES (30% des déclenchements) :
- Adoucisseur d'eau : cycle régénération nocturne (0.25 m³ en 30 min entre 2h et 3h)
- Lave-vaisselle programmé nuit : 0.3–0.5 m³ sur 40 min
- Remplissage piscine ou réservoir incendie (événement planifié)

QUALIFICATION RAPIDITE INTERVENTION :
- < 0.15 m³/h : vérifier dans les 48h
- 0.15–0.5 m³/h : intervenir dans les 24h
- > 0.5 m³/h : intervention IMMÉDIATE (facturation eau + dégâts)
""",
domain='water',
keywords='fuite eau nuit WC canalisation adoucisseur arrosage vanne pressostatique dégât')

_doc('playbook_gas_nocturnal', 'anomaly_playbook',
     'Playbook : Consommation gaz nocturne anormale — diagnostics',
"""
PATTERN ANOMALIE : Consommation gaz > P50 baseline entre 22h et 6h
PROBABILITÉ CAUSE : Équipement resté en marche (60%), Fuite (25%), Problème régulation (15%)

DIAGNOSTIC ARBRE DE DÉCISION :

Q1 : La consommation est-elle stable ou croissante sur la nuit ?
  → Stable, niveau modéré (3–8 m³/h hors hiver) : vannes de zone non fermées
  → Stable, niveau élevé (>15 m³/h) : chaudière en mode panique (capteur température HS)
  → Croissante : fuite (pression baisse progressivement si circuit fermé) → APPEL D'URGENCE

Q2 : L'alarme s'est-elle déclenchée dans la chaufferie ?
  → Oui : évacuer, couper gaz général, appeler STEG Gaz (urgence 80 00 00 12)
  → Non : continuer le diagnostic

Q3 : La consommation nocturne est-elle > 15 m³/h ?
  → Oui + pas d'alarme : possible détecteur défaillant → technicien gaz URGENCE
  → Non (3–8 m³/h) : vérifier vannes de zone, thermostat de nuit, programmation GTB

CAUSES FRÉQUENTES DES NUITS FROIDES :
- Programme chauffage non adapté au week-end/fermeture → chaudière tourne inutilement
- Température extérieure exceptionnellement basse → consommation légitime +30%
- Capteur température extérieure défaillant → chauffe en continu même si chaud à l'intérieur

SI ODEUR GAZ DÉTECTÉE : ne pas allumer de lumière, évacuer, appel 197 (urgence gaz).
""",
domain='gas',
keywords='gaz nuit fuite détecteur alarme vanne zone thermostat programmation urgence STEG')

_doc('playbook_fuel_gradual_increase', 'anomaly_playbook',
     'Playbook : Augmentation progressive consommation carburant flotte',
"""
PATTERN ANOMALIE : Consommation carburant +35% vs flotte sur 7 jours, tendance monotone
PROBABILITÉ CAUSE : Problème mécanique (55%), Comportement conducteur (30%), Vol (15%)

CHRONOLOGIE TYPIQUE DÉGRADATION MÉCANIQUE :
Semaine 1 : +10–15% (début encrassement injecteurs ou perte pression pneus)
Semaine 2 : +25–35% (dégradation confirmée, code OBD apparu souvent)
Semaine 3+ : >40% (panne franche imminente si non traitée)

CAUSES PAR KILOMÉTRAGE VÉHICULE :
< 40 000 km : pneus sous-gonflés (cause #1), conduite agressive (#2)
40 000–80 000 km : filtre à air, filtre carburant, bougies préchauffage (diesel)
> 80 000 km : injecteurs encrassés, turbo (fuite), thermostat, EGR colmaté

SUSPICION VOL CARBURANT :
- Consommation élevée MAIS kilométrage normal ou faible
- Anomalie le soir après fermeture dépôt ou week-end
- Plusieurs véhicules touchés simultanément
Action : installer capteur niveau précis + caméra dépôt + audit bons de carburant

COÛT RÉPARATION ESTIMÉ :
  Pneus (4) : 300–600 TND
  Filtre air + carburant : 80–150 TND (main d'œuvre 1h)
  Injecteurs nettoyage : 200–350 TND
  Remplacement injecteurs : 800–1800 TND (4 cylindres)
""",
domain='fuel',
keywords='carburant flotte augmentation progressive injecteur pneus vol OBD kilométrage maintenance')

_doc('playbook_energy_datacenter', 'anomaly_playbook',
     'Playbook : Surconsommation énergie salle serveurs',
"""
PATTERN ANOMALIE : Consommation EN_015 (datacenter) dépasse seuil WARNING >155 kWh/h
PROBABILITÉ CAUSE : Problème refroidissement (45%), Charge anormale serveurs (35%), UPS défaut (20%)

PROCÉDURE D'ESCALADE URGENTE (max 15 min pour agir) :

VÉRIFICATION 1 — Température salle (2 min)
  - Cible opérationnelle : 18–22°C
  - WARNING : >24°C (risque throttling CPU)
  - CRITICAL : >28°C (arrêt automatique serveurs protégé)
  Action si >24°C : vérifier climatisation salle + accès ventilation libre

VÉRIFICATION 2 — Circuit de refroidissement (5 min)
  - Débit chiller (pompe secondaire)
  - Pression circuit primaire (P cible 2–2.5 bar)
  - Niveau réservoir de refroidissement
  - Si fuite visible : ARRÊT IMMÉDIAT refroidissement liquide, contacter prestataire urgence

VÉRIFICATION 3 — Charge serveurs (5 min, dashboard monitoring)
  - CPU load global : normal <70%, warning >85%
  - Si pic inopiné : vérifier tâche cron, backup, migration en cours
  - Contacter équipe IT pour validation

VÉRIFICATION 4 — UPS (3 min)
  - Bypass UPS actif (consomme 3–5% de plus)
  - Batteries UPS en fin de vie → efficacité réduite
  - Test automatique en cours → pic temporaire 15 min

ESCALADE : si cause non identifiée en 15 min → contacter DSI + prestataire datacenter.
""",
domain='energy', device_id='EN_015',
keywords='datacenter serveurs refroidissement UPS température CPU charge climatisation urgence')


# ══════════════════════════════════════════════════════════════════════════════
# RAPPORTS D'INTERVENTION — Historique fictif réaliste
# ══════════════════════════════════════════════════════════════════════════════

_doc('report_20240115_en042', 'intervention_report',
     'Rapport intervention 15/01/2024 — EN_042 surconsommation atelier',
"""
RAPPORT D'INTERVENTION — Réf. INT-2024-0042
Date : 15 janvier 2024
Device concerné : EN_042 (Atelier production, Hall B)
Technicien : Karim B. (électricité + HVAC)
Durée intervention : 3h30

CONTEXTE :
Recommandation IA générée le 14/01 à 04h00 UTC : "Surconsommation EN_042 +67% vs baseline,
pic concentré 14h–16h, score Chronos 0.87". Acceptée par gestionnaire à 08h30.

DIAGNOSTIC SUR SITE :
À l'arrivée (9h00), consommation live : 78 kWh/h vs baseline 47 kWh/h (+66%).
Inspection visuelle hall B : température 28°C (consigne 22°C → différentiel 6°C anormal).

CVC split mural M3 (zone fraiseuses CNC) : filtre complètement obstrué (dépôts copeaux métal +
poussière). ΔP mesuré : 180 Pa (seuil critique 100 Pa). Compresseur forcé à 100% depuis 11 jours.

Unité extérieure CVC M3 : ailettes condenseur encrassées à 60%, échange thermique dégradé.

ACTIONS RÉALISÉES :
  1. Remplacement filtre G4 CVC M3 (30 min, filtre 45 TND)
  2. Nettoyage HP ailettes condenseur (45 min)
  3. Vérification charge frigorigène R410A → OK, pression nominale
  4. Recalibration thermostat de zone

RÉSULTAT IMMÉDIAT :
À 12h30 : consommation EN_042 redescendue à 49 kWh/h (+4% normal).
Économie estimée sur 11 jours de panne : 341 kWh × 0.096 = 32.7 TND.
Recommandation système marquée "done" à 14h00.

RECOMMANDATION PRÉVENTIVE : nettoyage filtres CVC atelier tous les 2 mois (copeaux métaux).
""",
domain='energy', device_id='EN_042',
keywords='intervention rapport EN_042 filtre CVC HVAC atelier copeaux condenseur nettoyage')

_doc('report_20240302_wm001', 'intervention_report',
     'Rapport intervention 02/03/2024 — WM_001 fuite nocturne',
"""
RAPPORT D'INTERVENTION — Réf. INT-2024-0089
Date : 2 mars 2024
Device concerné : WM_001 (réseau général eau)
Technicien : Mehdi S. (plomberie)
Durée intervention : 2h15

CONTEXTE :
Alerte LEAK_RISK générée à 03h47 UTC : débit nocturne 0.38 m³/h sur 2h30 consécutives
(baseline 0.04 m³/h). Chronos score 0.91 (anomalie haute confiance).

INVESTIGATION (méthode isolation) :
03h47 — Arrivée technicien d'astreinte.
Fermeture séquentielle des vannes de secteur :
  - Secteur A (Bâtiment A) : fermeture → débit tombe à 0.22 m³/h. Fuite dans secteur A confirmée.
  - Étage 1 Bâtiment A : fermeture → débit 0.18 m³/h.
  - Étage 2 Bâtiment A : fermeture → débit 0.04 m³/h (résiduel normal).
  → FUITE CONFIRMÉE AU NIVEAU 2, BÂTIMENT A.

LOCALISATION PHYSIQUE :
Local sanitaires hommes, niveau 2 : 3 WC à chasse automatique.
WC 2A-H-03 : cassette de chasse avec clapet joint déchiré → fuite continue 0.31 m³/h.

RÉPARATION :
Remplacement joint clapet chasse automatique TECE (pièce standard 12 TND, 25 min).
Test : débit nocturne revenu à 0.03 m³/h.

COÛT TOTAL : déplacement astreinte 80 TND + 12 TND pièce + 1h facturée = 112 TND.
Économie eau évitée sur 1 mois si non traité : 0.31 × 720h × 0.75 TND = 167 TND/mois.
""",
domain='water', device_id='WM_001',
keywords='rapport fuite eau WM_001 chasse WC clapet isolation secteur niveau 2 nuit')

_doc('report_20231205_gm001', 'intervention_report',
     'Rapport intervention 05/12/2023 — GM_001 dérive chaufferie',
"""
RAPPORT D'INTERVENTION — Réf. INT-2023-0301
Date : 5 décembre 2023
Device concerné : GM_001 (chaufferie centrale)
Technicien : Ali T. (chauffagiste PG certifié)
Durée intervention : 4h

CONTEXTE :
Recommandation MAINTENANCE générée : "+28% consommation gaz sur 7 jours, monotone".
Score Chronos 0.78. Gestionnaire a accepté la recommandation le 04/12 à 09h00.

DIAGNOSTIC COMBUSTION (analyseur KANE 458) :
  CO2 mesuré : 7.2% (cible 8.5–9.5%) → mélange trop pauvre en gaz
  CO : 85 ppm (cible <50 ppm) → combustion incomplète
  Température fumées : 88°C (condensation théorique 55°C → pas en mode condensation)
  Rendement calculé : 84% (cible >92%)

CAUSES IDENTIFIÉES :
  1. Échangeur primaire : dépôts calcaires épais 3–4 mm côté fumées.
     Perte transfer thermique estimée : 15–18%.
  2. Brûleur : électrodes d'allumage corrodées, réglage air/gaz dérivé.

ACTIONS RÉALISÉES :
  1. Nettoyage échangeur acide chlorhydrique dilué 10% (2h) + rinçage
  2. Remplacement électrodes allumage (20 min, pièce 65 TND)
  3. Réglage combustion : CO2 recalibré à 9.1%, CO 18 ppm
  4. Vérification siphon condensats (OK)

APRÈS INTERVENTION :
Rendement mesuré : 93.4%. Température fumées : 52°C (condensation active).
Consommation J+1 : -21% vs moyenne J-7 avant intervention.
Économie estimée sur 3 mois hiver si non traité : 520 TND.
""",
domain='gas', device_id='GM_001',
keywords='rapport chaufferie gaz GM_001 échangeur calcaire combustion brûleur électrodes rendement')

_doc('report_20240410_fuel_veh', 'intervention_report',
     'Rapport audit carburant flotte — Avril 2024',
"""
RAPPORT D'AUDIT CARBURANT — Réf. AUD-2024-004
Date : 10 avril 2024
Périmètre : 8 véhicules utilitaires flotte entreprise
Responsable : Service maintenance / Fleet manager

CONTEXTE :
Recommandation EFFICIENCY générée sur 3 véhicules dépassant +35% flotte :
VEH_003, VEH_007, VEH_011.

RÉSULTATS AUDIT :

VEH_003 (Renault Trafic 2022, 67k km) :
  Pression pneus AV : 2.1 bar (cible 2.8 → écart -0.7 bar)
  Filtre air : état passable (remplacement dans 10k km)
  OBD : aucun code défaut
  Verdict : pneus sous-gonflés. Regonflage → -9% consommation immédiat.

VEH_007 (Peugeot Expert 2019, 112k km) :
  Pression pneus : OK (2.75 bar)
  OBD : P0128 actif (thermostat ouvert bloqué)
  Température liquide refroidissement max 72°C (cible 87°C) → consommation +18%
  Verdict : remplacement thermostat requis (pièce 85 TND + 1.5h main d'œuvre).

VEH_011 (Citroën Jumpy 2020, 88k km) :
  OBD : P0183 (capteur température carburant) + injection long terme >+12%
  Filtre carburant : jamais remplacé (durée de vie dépassée)
  Verdict : remplacement filtre carburant + nettoyage injecteurs.

RÉSULTATS 2 SEMAINES POST-INTERVENTION :
  VEH_003 : -8.5% L/100km
  VEH_007 : -16.2% L/100km (thermostat)
  VEH_011 : -11.7% L/100km
Économie totale mensuelle estimée : 145 TND.
""",
domain='fuel',
keywords='audit carburant flotte véhicules pneus thermostat filtre OBD intervention économie')


# ══════════════════════════════════════════════════════════════════════════════
# ZONES BÂTIMENT — Contexte spatial
# ══════════════════════════════════════════════════════════════════════════════

_doc('zone_bat_a', 'building_zone', 'Zone Bâtiment A — Bureaux administratifs',
"""
ZONE : Bâtiment A — Siège administratif
Superficie : 2 400 m²  |  Niveaux : RDC + 3 étages
Occupation : 180 personnes (jours ouvrables 8h–18h)
Fermetures : weekends, jours fériés nationaux

ÉQUIPEMENTS SURVEILLÉS :
  Énergie : EN_001 (tableau principal), EN_003 (étage 1), EN_004 (étage 2-3)
  Eau     : WM_001 (réseau général), WM_005 (cuisine RDC)
  Gaz     : GM_001 (chaufferie sous-sol)

CONSOMMATION TYPIQUE :
  Énergie : 1 200–1 500 kWh/j (hiver), 900–1 100 kWh/j (été)
  Eau     : 12–18 m³/j
  Gaz     : 80–120 m³/j (hiver), 5–10 m³/j (été)

SPÉCIFICITÉS :
  - Bâtiment à ossature béton, isolation standard 2003 → coefficient U moyen
  - 3 CTA (CentralisAir) alimentées par GM_001 et EN_001
  - Salle de réunion au niveau 3 (120 personnes max) → pic consommation lors d'événements
  - Local serveurs sous-sol : consommation quasi constante 18–22 kWh/h

PATTERNS SAISONNIERS :
  Été : climatisation génère surpuissance 14h–17h si T°ext > 33°C
  Hiver : chaufferie démarre à 5h30 pour atteindre température de confort à 8h
""",
keywords='bâtiment A bureaux administratif occupation énergie eau gaz CTA saisonniers')

_doc('zone_bat_b', 'building_zone', 'Zone Bâtiment B — Restauration et services',
"""
ZONE : Bâtiment B — Cafétéria, cuisine, salles de réunion
Superficie : 1 200 m²  |  Niveaux : 2
Occupation : service restauration 7h–22h, nettoyage 22h–23h

ÉQUIPEMENTS SURVEILLÉS :
  Énergie : EN_010 (cuisine), EN_012 (cafétéria et salles)
  Eau     : WM_012 (cuisine), WM_015 (sanitaires)
  Gaz     : GM_008 (cuisine professionnelle)

PARTICULARITÉS OPÉRATIONNELLES :
  - Cuisine professionnelle avec 2 fours combinés 20 kW chacun
  - Lave-vaisselle industriel Hobart CL44 : cycle 40 min, 18 L eau chaude/cycle
  - Adoucisseur Pentair (régénération nocturne 2h–3h : 0.3 m³ eau + sel)
  - Groupe froid cuisine : 8 kW en continu (légumes, viandes)

CONSOMMATIONS TYPIQUES :
  Énergie : 380–450 kWh/j
  Eau     : 5–8 m³/j (service), 0.1–0.3 m³/j (nuit = adoucisseur uniquement)
  Gaz     : 45–75 m³/j (service), <2 m³/j (veilleuses uniquement la nuit)

ALERTES À CONTEXTUALISER :
  - Pic gaz 11h–14h et 18h–21h = SERVICE NORMAL
  - Eau nocturne 2h–3h : 0.3 m³ → ADOUCISSEUR, pas une fuite
  - Énergie weekend : fermeture cuisines, base <50 kWh/j (froids seulement)
""",
keywords='cafétéria cuisine bâtiment B adoucisseur lave-vaisselle gaz nocturne restauration fours')

_doc('zone_hall_b', 'building_zone', 'Zone Hall B — Production et ateliers',
"""
ZONE : Hall B — Ateliers de production et maintenance
Superficie : 3 500 m²  |  Hauteur : 8 m (haut-plafond)
Occupation : équipes 2×8h (6h–14h et 14h–22h), parfois 3×8h (6h–22h)

ÉQUIPEMENTS SURVEILLÉS :
  Énergie : EN_042 (tableau principal hall), EN_045 (compresseurs), EN_047 (pont roulant)
  Eau     : WM_022 (refroidissement machines), WM_024 (sanitaires)
  Carburant: FM_007 (chariots élévateurs électriques + groupe)

CARACTÉRISTIQUES PRODUCTION :
  - 6 fraiseuses CNC (8 kW chacune)
  - 2 tours à commande numérique (12 kW chacun)
  - Compresseur d'air central Atlas Copco GA37 (37 kW)
  - Pont roulant 5T (kW variable, cycles courts)
  - Ventilation générale (10 kW continu pendant production)

PROFIL CONSOMMATION :
  En production : 85–120 kWh/h
  Pause inter-équipes (14h) : 25–35 kWh/h (machines en veille)
  Hors production (22h–6h) : 8–15 kWh/h (ventilation + sécurité)

NOTE DIAGNOSTIC : la consommation du Hall B est très sensible aux cycles de maintenance.
Un compresseur d'air avec fuite de 5mm génère +8 kWh/h continu (le compresseur relance
toutes les 3 min pour maintenir pression). Ce pattern est indiscernable d'une surconsommation
HVAC sans inspection physique.
""",
keywords='atelier production CNC fraiseuse compresseur air pont roulant équipes hall consommation')


# ══════════════════════════════════════════════════════════════════════════════
# CONTRATS ET TARIFS
# ══════════════════════════════════════════════════════════════════════════════

_doc('contract_electricity_steg', 'contract_info',
     'Contrat électricité STEG — Tarif Moyenne Tension MT',
"""
CONTRAT ÉLECTRICITÉ — STEG (Société Tunisienne de l'Électricité et du Gaz)
Type : Moyenne Tension (MT) — Tarif BT Industriel HTA
Puissance souscrite : 500 kW (dépassement facturé ×3)

STRUCTURE TARIFAIRE :
  Heures de Pointe (HP)  : 7h–10h et 17h–21h (jours ouvrables)  — 0.156 TND/kWh
  Heures Pleines  (HM)   : 6h–7h, 10h–17h, 21h–22h             — 0.096 TND/kWh
  Heures Creuses  (HC)   : 22h–6h                               — 0.063 TND/kWh

COÛT PAR DÉFAUT UTILISÉ DANS LE SYSTÈME : 0.096 TND/kWh (tarif moyen pondéré).

FACTURATION MENSUELLE TYPE :
  Abonnement fixe    : 120 TND/mois
  Consommation       : variable selon consommation
  Prime puissance    : 85 TND/kW/an si dépassement souscription

OPTIMISATION POSSIBLE :
  Déplacer 20% de la consommation vers HC (22h–6h) économise ~33% sur ces kWh.
  Exemples : préchauffage four, lave-linge industriel, charge batteries.

BUDGET ANNUEL ESTIMÉ : 125 000–180 000 TND/an selon saison.
""",
keywords='tarif électricité STEG MT heures pointe creuses facturation budget TND')

_doc('contract_water_sonede', 'contract_info',
     'Contrat eau SONEDE — Tarification volumétrique',
"""
CONTRAT EAU — SONEDE (Société Nationale d'Exploitation et de Distribution des Eaux)
Type abonnement : Usage industriel + tertiaire

TARIFICATION PROGRESSIVE (TND/m³) :
  Tranche 1 (0–500 m³/mois)    : 0.620 TND/m³
  Tranche 2 (501–3000 m³/mois) : 0.750 TND/m³
  Tranche 3 (>3000 m³/mois)    : 0.980 TND/m³

COÛT MOYEN UTILISÉ DANS LE SYSTÈME : 0.75 TND/m³ (tranche 2 dominante).

CONSOMMATION ACTUELLE : 450–650 m³/mois (tranche 2 principalement).
BUDGET ANNUEL : 4 500–6 500 TND/an.

NOTE FUITES : Une fuite de 0.3 m³/h non détectée pendant 30 jours = 216 m³ = 162 TND
perdus, plus coût réparation. Détection précoce ROI quasi immédiat.
""",
keywords='eau SONEDE tarif volumétrique tranche fuite budget m3 TND')

_doc('contract_gas_steg', 'contract_info',
     'Contrat gaz STEG — Usage industriel',
"""
CONTRAT GAZ NATUREL — STEG Gaz
Type : Usage industriel (chaufferie + cuisine professionnelle)
Pression fourniture : 0.5 bar (réseau MDR)

TARIFICATION :
  Gaz industriel usage thermique : 0.450 TND/m³
  Redevance fixe mensuelle       : 95 TND/mois

COÛT UTILISÉ DANS LE SYSTÈME : 0.45 TND/m³.

CONSOMMATION ANNUELLE ESTIMÉE :
  Hiver (nov-mar, 5 mois) : 35 000–45 000 m³
  Autres saisons          : 8 000–12 000 m³
  TOTAL ANNUEL            : 43 000–57 000 m³

BUDGET ANNUEL : 19 000–26 000 TND/an.

SÉCURITÉ OBLIGATOIRE :
  Robinet d'arrêt général accessible en permanence (local chaufferie)
  Numéro urgence gaz STEG : 80 00 00 12 (24h/24)
  Détecteur gaz conforme NF EN 50194, révisé annuellement
""",
keywords='gaz STEG tarif industriel chaufferie urgence budget annuel m3 TND')

_doc('contract_fuel_budget', 'contract_info',
     'Budget carburant flotte — Référentiel consommation',
"""
RÉFÉRENTIEL CARBURANT — Flotte véhicules utilitaires
Gestionnaire : Service achats / Fleet management

FLOTTE ACTUELLE : 12 véhicules (8 diesels, 4 essence)
CONSOMMATION RÉFÉRENCE PAR TYPE :
  Fourgonnette <1.5T (ex: VEH_001, VEH_003) : 8.5 L/100km référence
  Utilitaire 1.5–3.5T (ex: VEH_007)          : 9.8 L/100km référence
  Camionnette >3.5T                           : 14.5 L/100km référence

PRIX CARBURANT UTILISÉ : 1.920 TND/L (gasoil, prix moyen 2024).

SEUIL D'ALERTE UTILISÉ PAR ARIA : +35% vs moyenne flotte sur 7 jours.
Ce seuil est volontairement conservateur pour éviter les faux positifs liés aux variations
normales de charge et de trajets urbains/autoroute.

BUDGET MENSUEL FLOTTE :
  Consommation normale : 1 200–1 600 L/mois
  Coût normal         : 2 300–3 100 TND/mois
  Budget annuel       : 28 000–37 000 TND/an

PROGRAMME ECO-CONDUITE EN COURS :
  Objectif : -12% L/100km en 6 mois via formation conducteurs + télémétrie.
  KPI suivi : score éco-conduite par chauffeur (accélération, freinage, ralenti).
""",
keywords='carburant flotte budget L/100km référence seuil éco-conduite télémétrie gasoil')


# ══════════════════════════════════════════════════════════════════════════════
# DONNÉES D'INSERTION
# ══════════════════════════════════════════════════════════════════════════════

DDL = """
CREATE TABLE IF NOT EXISTS rag_documents (
    id          INT          AUTO_INCREMENT PRIMARY KEY,
    doc_id      VARCHAR(100) NOT NULL UNIQUE,
    category    VARCHAR(50)  NOT NULL,
    domain      VARCHAR(20)  NULL,
    device_id   VARCHAR(50)  NULL,
    title       VARCHAR(255) NOT NULL,
    content     TEXT         NOT NULL,
    keywords    VARCHAR(500) NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FULLTEXT  idx_ft      (title, content, keywords),
    INDEX     idx_device  (device_id),
    INDEX     idx_category(category),
    INDEX     idx_domain  (domain)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def _get_engine():
    """Crée un engine SQLAlchemy depuis les variables d'environnement."""
    import os
    from pathlib import Path

    # Charger .env si présent
    env_file = Path(__file__).parent.parent / '.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    from sqlalchemy import create_engine
    host   = os.environ.get('DB_HOST', 'localhost')
    port   = os.environ.get('DB_PORT', '3306')
    name   = os.environ.get('DB_NAME', 'bw_samar')
    user   = os.environ.get('DB_USER', 'root')
    pwd    = os.environ.get('DB_PASSWORD', '')
    return create_engine(
        f'mysql+pymysql://{user}:{pwd}@{host}:{port}/{name}?charset=utf8mb4',
        pool_pre_ping=True,
    )


def seed(engine, clear: bool = False) -> int:
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text(DDL))

    if clear:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM rag_documents"))
        print("Table vidée.")

    sql = text("""
        INSERT IGNORE INTO rag_documents (doc_id, category, domain, device_id, title, content, keywords)
        VALUES (:doc_id, :category, :domain, :device_id, :title, :content, :keywords)
    """)

    inserted = 0
    with engine.begin() as conn:
        for doc in DOCUMENTS:
            result = conn.execute(sql, doc)
            inserted += result.rowcount

    print(f"Seed terminé : {inserted}/{len(DOCUMENTS)} documents insérés.")
    return inserted


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Seed fake RAG documents')
    parser.add_argument('--clear', action='store_true', help='Vide la table avant insertion')
    args = parser.parse_args()

    engine = _get_engine()
    n = seed(engine, clear=args.clear)
    print(f"Total documents dans DOCUMENTS : {len(DOCUMENTS)}")
    sys.exit(0 if n >= 0 else 1)
