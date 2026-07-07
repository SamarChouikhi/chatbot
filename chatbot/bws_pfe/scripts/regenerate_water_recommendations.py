"""
P3b — Régénération des recommandations eau.
À lancer depuis chatbot/bws_pfe/ APRÈS avoir exécuté :
  - fix_daily_water_units.sql
  - reset_water_recommendations.sql

Usage :
    cd chatbot/bws_pfe
    python scripts/regenerate_water_recommendations.py
"""
import sys
from pathlib import Path

# Assure que les imports trouvent les modules du projet
sys.path.insert(0, str(Path(__file__).parents[1]))

from mcp_server.db.connection import engine
from api.pipeline.recommendation_engine import generate_domain, compute_baselines

print("=== Étape 1 : calcul des baselines eau ===")
try:
    compute_baselines(engine, 'water')
    print("  Baselines calculées.")
except Exception as e:
    print(f"  ERREUR baselines : {e}")
    sys.exit(1)

print("\n=== Étape 2 : génération des recommandations eau ===")
try:
    count = generate_domain(engine, 'water')
    print(f"  {count} recommandation(s) générée(s).")
except Exception as e:
    print(f"  ERREUR génération : {e}")
    sys.exit(1)

print("\nTerminé. Vérifier dans MySQL :")
print("  SELECT id, rec_type, device_id, priority, estimated_saving_tnd")
print("  FROM aria_recommendations WHERE domain='water' ORDER BY created_at DESC LIMIT 5;")
