-- ============================================================
-- P3a — Purge recommandations et baselines eau
-- À exécuter APRÈS fix_daily_water_units.sql
-- ============================================================

-- Supprimer les recos pending eau (basées sur des valeurs fausses)
DELETE FROM aria_recommendations
WHERE domain = 'water' AND status = 'pending';

-- Supprimer les baselines eau (calculées sur des litres, donc fausses)
DELETE FROM device_baselines
WHERE domain = 'water';

-- Vérification
SELECT 'aria_recommendations water pending restantes' AS check_label,
       COUNT(*) AS count
FROM aria_recommendations
WHERE domain = 'water' AND status = 'pending'

UNION ALL

SELECT 'device_baselines water restantes',
       COUNT(*)
FROM device_baselines
WHERE domain = 'water';
