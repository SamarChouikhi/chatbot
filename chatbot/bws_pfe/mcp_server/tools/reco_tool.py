"""
Outil MCP : get_recommendations
Retourne les recommandations IA personnalisées actives pour un domaine donné.
ARIA peut appeler cet outil pour contextualiser ses réponses avec les vraies
recommandations calculées par le moteur (baselines personnelles, ROI, etc.).
"""
import json
import logging
from mcp_server.tools._helpers import ok, err

logger = logging.getLogger('aria.tools.reco')


def get_recommendations(domain: str = 'all', limit: int = 10, device_id: str = '') -> str:
    """
    Retourne les recommandations IA actives générées par le moteur de recommandations personnalisées.

    Args:
        domain    : Domaine à filtrer — "energy" | "water" | "gas" | "fuel" | "all"
        limit     : Nombre maximum de recommandations à retourner (1–20)
        device_id : (optionnel) Filtre sur un compteur/équipement précis (ex : "6301", "EN_001_L1")

    Returns:
        JSON avec la liste des recommandations, chacune avec :
        - priority  : critical / high / medium / low
        - rec_type  : OVERCONSUMPTION / OPTIMIZATION / BUDGET_ALERT / MAINTENANCE / LEAK_RISK / EFFICIENCY
        - title     : titre court
        - description: explication détaillée avec chiffres réels
        - action    : action concrète recommandée
        - estimated_saving_tnd : économie potentielle estimée
        - deviation_pct : déviation % vs baseline personnelle
        - status    : pending / accepted / dismissed / done

    Note: Le moteur génère des recommandations uniquement pour les domaines de consommation
    (energy, water, gas, fuel). Les capteurs IoT (THL, PIR, WM bruts) ne sont pas couverts.
    """
    tool = 'get_recommendations'
    logger.info('[%s] domain=%s device_id=%s limit=%d', tool, domain, device_id or 'all', limit)

    try:
        from mcp_server.db.connection import engine
        if engine is None:
            return err(tool, 'Base de données non disponible', 'Vérifiez la connexion MySQL')
    except Exception as exc:
        return err(tool, f'Connexion DB impossible : {exc}')

    limit = max(1, min(20, limit))

    try:
        from sqlalchemy import text

        where_parts = ["status IN ('pending','accepted')", "expires_at > NOW()"]
        params: dict = {'limit': limit}

        if domain != 'all':
            where_parts.append("domain = :domain")
            params['domain'] = domain

        if device_id:
            where_parts.append("device_id = :device_id")
            params['device_id'] = device_id

        where = ' AND '.join(where_parts)
        sql = text(f"""
            SELECT id, domain, device_id, rec_type, priority, title, description, action,
                   estimated_saving_tnd, deviation_pct, status, generated_at
            FROM aria_recommendations
            WHERE {where}
            ORDER BY FIELD(priority,'critical','high','medium','low'), generated_at DESC
            LIMIT :limit
        """)

        with engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        if not rows:
            note = (
                f'Aucune recommandation active pour le device {device_id}. '
                'Note : le moteur couvre uniquement les compteurs énergie/eau/gaz/carburant. '
                'Pour un capteur IoT (THL, PIR, WM brut), utilisez realtime_data ou alerts_summary.'
                if device_id else
                'Aucune recommandation active — consommation dans les normes ou cycle non encore exécuté.'
            )
            return ok({
                'domain'         : domain,
                'device_id'      : device_id or None,
                'count'          : 0,
                'recommendations': [],
                'message'        : note,
            })

        recos = [
            {
                'id'                  : r[0],
                'domain'              : r[1],
                'device_id'           : r[2],
                'rec_type'            : r[3],
                'priority'            : r[4],
                'title'               : r[5],
                'description'         : r[6],
                'action'              : r[7],
                'estimated_saving_tnd': round(r[8], 2) if r[8] else None,
                'deviation_pct'       : round(r[9], 1) if r[9] else None,
                'status'              : r[10],
                'generated_at'        : str(r[11]),
            }
            for r in rows
        ]

        total_saving = sum(r['estimated_saving_tnd'] or 0 for r in recos)
        critical_n   = sum(1 for r in recos if r['priority'] == 'critical')
        high_n       = sum(1 for r in recos if r['priority'] == 'high')

        return ok({
            'domain'                  : domain,
            'count'                   : len(recos),
            'critical_count'          : critical_n,
            'high_count'              : high_n,
            'total_potential_saving_tnd': round(total_saving, 2),
            'recommendations'         : recos,
        })

    except Exception as exc:
        logger.error('[%s] Erreur : %s', tool, exc, exc_info=True)
        return err(tool, f'Erreur récupération recommandations : {exc}')
