-- ============================================================
-- P2b — Correction unité daily_water.conso_m3
-- Les valeurs sont stockées en LITRES mais la colonne s'appelle m³.
-- Ce script divise toutes les valeurs par 1000.
--
-- AVANT d'exécuter : faire un backup ou tester avec le SELECT ci-dessous.
-- ============================================================

-- 1. Vérification avant (valeurs en milliers = litres)
SELECT
    device_id,
    MIN(date)          AS premiere_date,
    MAX(date)          AS derniere_date,
    ROUND(SUM(conso_m3), 0) AS total_actuel,
    COUNT(*)           AS nb_lignes
FROM daily_water
WHERE conso_m3 > 0
GROUP BY device_id
ORDER BY total_actuel DESC
LIMIT 10;

-- 2. Correction : diviser par 1000 (litres → m³)
UPDATE daily_water
SET conso_m3 = ROUND(conso_m3 / 1000.0, 4)
WHERE conso_m3 > 0;

-- 3. Vérification après (valeurs raisonnables : 10–200 m³/jour pour un bâtiment)
SELECT
    device_id,
    MIN(date)          AS premiere_date,
    MAX(date)          AS derniere_date,
    ROUND(SUM(conso_m3), 2) AS total_m3_corrige,
    ROUND(AVG(conso_m3), 4) AS moyenne_horaire_m3
FROM daily_water
WHERE conso_m3 > 0
GROUP BY device_id
ORDER BY total_m3_corrige DESC
LIMIT 10;
