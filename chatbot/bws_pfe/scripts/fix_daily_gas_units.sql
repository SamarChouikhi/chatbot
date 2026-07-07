-- ============================================================
-- Correction unité daily_gas.conso_m3
-- Même bug que daily_water : valeurs stockées en LITRES.
-- Ce script divise par 1000 pour obtenir des m³ réels.
-- ============================================================

-- 1. Vérification avant (valeurs en milliers = litres)
SELECT
    device_id,
    MIN(date)               AS premiere_date,
    MAX(date)               AS derniere_date,
    ROUND(SUM(conso_m3), 0) AS total_actuel,
    COUNT(*)                AS nb_lignes
FROM daily_gas
WHERE conso_m3 > 0
GROUP BY device_id
ORDER BY total_actuel DESC
LIMIT 10;

-- 2. Correction : diviser par 1000 (litres → m³)
UPDATE daily_gas
SET conso_m3 = ROUND(conso_m3 / 1000.0, 4)
WHERE conso_m3 > 0;

-- 3. Vérification après (valeurs raisonnables : 5–100 m³/jour pour un bâtiment)
SELECT
    device_id,
    MIN(date)               AS premiere_date,
    MAX(date)               AS derniere_date,
    ROUND(SUM(conso_m3), 2) AS total_m3_corrige,
    ROUND(AVG(conso_m3), 4) AS moyenne_horaire_m3
FROM daily_gas
WHERE conso_m3 > 0
GROUP BY device_id
ORDER BY total_m3_corrige DESC
LIMIT 10;
