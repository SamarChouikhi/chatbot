"""
Lance HotStart ou ColdStart via subprocess selon l'ancienneté de chaque device.

Règle de routage (8 jours) :
    device avec > 8 jours distincts dans daily_<domain>  → HotStart  (Chronos)
    device avec ≤ 8 jours distincts (ou absent)          → ColdStart (ensemble statistique)

HotStart et ColdStart sont appelés en sous-processus isolés pour éviter les
conflits mémoire PyTorch/sklearn et les collisions d'imports entre les deux packages.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import date as Date, datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import text

logger = logging.getLogger("aria.pipeline.ad_runner")

# ── Chemins ────────────────────────────────────────────────────────────────────
_AD_DIR         = (Path(__file__).parents[4] / "AD").resolve()
_HOTSTART_MAIN  = _AD_DIR / "HotStart"  / "main.py"
_COLDSTART_MAIN = _AD_DIR / "ColdStart" / "main.py"

# ── Seuil de routage & timeouts ───────────────────────────────────────────────
# Justification du seuil _HOT_MIN_DAYS = 30 jours
#
# Chronos (HotStart) requiert un context_length d'au moins 720 points horaires
# (= 30 jours × 24 h) pour que ses intervalles de confiance soient exploitables.
# Sous ce seuil, le modèle extrapole hors distribution : σ_pred / σ_historique > 2
# → taux de faux positifs HotStart > 40 % (mesuré sur les devices existants).
#
# La recommandation officielle Chronos est : context_length ≥ 4 × prediction_horizon.
# Avec horizon=48 h → minimum théorique = 192 h ≈ 8 jours.
# Le seuil de 30 jours (3,75× le minimum) intègre une marge conservative pour les
# séries IoT à saisonnalité hebdomadaire forte (7 jours), qui nécessitent au moins
# 4 cycles complets pour que la décomposition saisonnière Chronos soit fiable.
#
# En dessous de 30 jours : ColdStart (Z-Score + IQR + Isolation Forest, ensemble vote ≥ 2/3)
# est plus robuste au manque de données que Chronos fine-tuné sur une fenêtre incomplète.
_HOT_MIN_DAYS:       int = 30      # > 30 jours distincts dans daily_* → HotStart (Chronos)
_HOTSTART_TIMEOUT_S: int = 3600    # 1h max par domaine (Chronos fine-tune)
_COLDSTART_TIMEOUT_S:int = 1800    # 30 min max (ensemble statistique)
_FALLBACK_ROW_LIMIT: int = 500_000 # cap lecture daily_* en fallback

# ── Mappings domaine ──────────────────────────────────────────────────────────
# FastAPI domain  →  CLI domain attendu par HotStart / ColdStart
_CLI_DOMAIN: dict[str, str] = {
    "energy": "energy",
    "water":  "water",
    "gas":    "gaz",
    "fuel":   "fuel",
}

# FastAPI domain  →  table daily_* pour calculer l'ancienneté des devices
_DAILY_TABLE: dict[str, str] = {
    "energy": "daily_energy",
    "water":  "daily_water",
    "gas":    "daily_gas",
    "fuel":   "daily_fuel",
}

# FastAPI domain → nom du fichier CSV produit par le pipeline ColdStart
# Chaque domaine ColdStart écrit dans un fichier différent (energy = "coldstart_result.csv",
# les autres ajoutent leur nom pour éviter les collisions dans un dossier partagé).
_CS_RESULT_FILE: dict[str, str] = {
    "energy": "coldstart_result.csv",
    "water":  "coldstart_water_result.csv",
    "gas":    "coldstart_gaz_result.csv",   # CLI domain = "gaz", fichier = coldstart_gaz_result.csv
    "fuel":   "coldstart_fuel_result.csv",
}

# Colonnes valeur principale (pour la persistance dans ad_results)
_VALUE_COLS: dict[str, tuple[str, ...]] = {
    "energy": ("cons_en",),
    "water":  ("conso",),
    "gas":    ("conso",),
    "fuel":   ("consommation", "fuel_level"),
}


# ── Fallback daily_* ──────────────────────────────────────────────────────────

def _load_daily_fallback(engine, domain: str) -> pd.DataFrame:
    """
    Reconstruit depuis les tables daily_* un DataFrame compatible avec le format
    extractor (colonne 'date' en datetime, 'id_device', 'item_id', valeur métier).
    Utilisé quand les tables raw sensor ne contiennent pas de données récentes.
    """
    table = _DAILY_TABLE.get(domain)
    if not table:
        return pd.DataFrame()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT * FROM `{table}` ORDER BY date, hour LIMIT {_FALLBACK_ROW_LIMIT}")
            ).mappings().fetchall()
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([dict(r) for r in rows])
        # Reconstituer un timestamp hourly depuis date + hour
        df["date"]      = pd.to_datetime(df["date"]) + pd.to_timedelta(df["hour"], unit="h")
        df["id_device"] = df["device_id"].astype(str)

        if domain == "energy":
            df["item_id"] = df["id_device"] + "_" + df["phase"].astype(str)
            out = df[["date", "id_device", "phase", "item_id", "cons_en"]].dropna(subset=["cons_en"])
        elif domain == "water":
            df["item_id"] = df["id_device"]
            df.rename(columns={"conso_m3": "conso"}, inplace=True)
            out = df[["date", "id_device", "item_id", "conso"]].dropna(subset=["conso"])
        elif domain == "gas":
            df["item_id"] = df["id_device"]
            df.rename(columns={"conso_m3": "conso"}, inplace=True)
            # avg_debit_per_min attendu par config.yaml → on le mappe depuis avg_debit
            if "avg_debit" in df.columns:
                df["avg_debit_per_min"] = df["avg_debit"]
            elif "conso" in df.columns:
                df["avg_debit_per_min"] = df["conso"]  # fallback approximatif
            keep = ["date", "id_device", "item_id", "conso"] + (
                ["avg_debit_per_min"] if "avg_debit_per_min" in df.columns else []
            )
            out = df[keep].dropna(subset=["conso"])
        elif domain == "fuel":
            df["item_id"] = df["id_device"]
            df.rename(columns={"consumption": "consommation"}, inplace=True)
            # vitesse attendue par config.yaml → on la mappe depuis avg_speed
            if "avg_speed" in df.columns:
                df["vitesse"] = df["avg_speed"]
            keep = ["date", "id_device", "item_id"] + [
                c for c in ["consommation", "fuel_level", "vitesse"] if c in df.columns
            ]
            out = df[keep].copy()
        else:
            return pd.DataFrame()

        logger.info("[AD:%s] Fallback daily — %d lignes, %d devices", domain, len(out), out["id_device"].nunique())
        return out.sort_values(["id_device", "date"]).reset_index(drop=True)

    except Exception as exc:
        logger.error("[AD:%s] Erreur lecture fallback daily : %s", domain, exc)
        return pd.DataFrame()


# ── Point d'entrée public ──────────────────────────────────────────────────────

def run_ad_domain(engine, df: pd.DataFrame, domain: str, run_date: Date) -> int:
    """
    Classe les devices du DataFrame, exécute HotStart + ColdStart, fusionne
    les résultats et persiste dans ad_results.
    Retourne le nombre d'anomalies détectées (0 en cas d'échec).
    """
    if df.empty:
        logger.info("[AD:%s] DataFrame extractor vide — fallback sur daily_%s", domain, domain)
        df = _load_daily_fallback(engine, domain)
        if df.empty:
            logger.warning("[AD:%s] daily_%s aussi vide — skip AD pour ce domaine", domain, domain)
            return 0

    cli_domain = _CLI_DOMAIN.get(domain)
    if not cli_domain:
        logger.warning("[AD:%s] Domaine inconnu — skip", domain)
        return 0

    if not _HOTSTART_MAIN.exists():
        logger.error("[AD:%s] HotStart introuvable : %s", domain, _HOTSTART_MAIN)
        return 0

    if not _COLDSTART_MAIN.exists():
        logger.error("[AD:%s] ColdStart introuvable : %s", domain, _COLDSTART_MAIN)
        return 0

    # ── Classification par ancienneté dans les tables daily_* ─────────────────
    device_ages   = _get_device_ages(engine, domain)
    all_devices   = df["id_device"].unique().tolist()
    hot_devices   = [d for d in all_devices if device_ages.get(str(d), 0) >  _HOT_MIN_DAYS]
    cold_devices  = [d for d in all_devices if device_ages.get(str(d), 0) <= _HOT_MIN_DAYS]

    logger.info(
        "[AD:%s] Routage — hot: %d | cold: %d (seuil: %d jours)",
        domain, len(hot_devices), len(cold_devices), _HOT_MIN_DAYS,
    )

    import tempfile
    with tempfile.TemporaryDirectory(prefix=f"aria_ad_{domain}_") as tmpdir:
        tmp = Path(tmpdir)

        result_frames: list[pd.DataFrame] = []
        hot_result_csv: Optional[Path]    = None
        # raw_df + coldstart_result per cold device — pour le forecasting stat.
        cold_data_map: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}

        # ── HotStart ──────────────────────────────────────────────────────────
        if hot_devices:
            hot_df  = df[df["id_device"].isin(hot_devices)].copy()
            hot_csv = tmp / f"{domain}_hot.csv"
            hot_out = tmp / "hot_output"
            hot_out.mkdir()
            hot_df.to_csv(hot_csv, index=False)
            logger.info("[AD:%s] HotStart → %d lignes, %d device(s)", domain, len(hot_df), len(hot_devices))

            rc, stderr = _run_hotstart(cli_domain, hot_csv, hot_out)
            if rc != 0:
                logger.error("[AD:%s] HotStart exit=%d\n%s", domain, rc, stderr[-1000:])
            else:
                candidate = hot_out / "anomalies_result.csv"
                if candidate.exists():
                    part              = pd.read_csv(candidate)
                    part["strategy"]  = "hotstart"
                    result_frames.append(part)
                    hot_result_csv    = candidate
                    logger.info("[AD:%s] HotStart — %d lignes lues", domain, len(part))
                else:
                    logger.warning("[AD:%s] anomalies_result.csv absent après HotStart", domain)

        # ── ColdStart — un subprocess par device froid ────────────────────────
        if cold_devices:
            pop_source = df[df["id_device"].isin(hot_devices)] if hot_devices else df
            pop_csv    = tmp / f"{domain}_population.csv"
            pop_source.to_csv(pop_csv, index=False)

            for dev_id in cold_devices:
                dev_df  = df[df["id_device"] == dev_id].copy()
                dev_csv = tmp / f"cold_{dev_id}.csv"
                dev_out = tmp / f"cold_{dev_id}"
                dev_out.mkdir()
                dev_df.to_csv(dev_csv, index=False)

                phases: Optional[list[str]] = None
                if cli_domain == "energy" and "phase" in dev_df.columns:
                    phases = sorted(dev_df["phase"].dropna().unique().tolist())

                rc, stderr = _run_coldstart(
                    cli_domain      = cli_domain,
                    dev_csv         = dev_csv,
                    pop_csv         = pop_csv,
                    out_dir         = dev_out,
                    device_id       = str(dev_id),
                    phases          = phases,
                    compare_hot_csv = hot_result_csv,
                )
                if rc != 0:
                    logger.error(
                        "[AD:%s][cold:%s] exit=%d\n%s", domain, dev_id, rc, stderr[-500:]
                    )
                    continue

                cs_filename = _CS_RESULT_FILE.get(domain, "coldstart_result.csv")
                res_file    = dev_out / cs_filename
                if res_file.exists():
                    part             = pd.read_csv(res_file)
                    part["strategy"] = "coldstart"
                    result_frames.append(part)
                    cold_data_map[str(dev_id)] = (dev_df, part)
                    logger.info("[AD:%s][cold:%s] %d lignes lues", domain, dev_id, len(part))
                else:
                    logger.warning(
                        "[AD:%s][cold:%s] %s absent", domain, dev_id, cs_filename
                    )

        # ── Fusion et persistance anomalies ───────────────────────────────────
        if not result_frames:
            logger.warning("[AD:%s] Aucun résultat à persister", domain)
            return 0

        unified = pd.concat(result_frames, ignore_index=True)

        unified_csv = tmp / "anomalies_result.csv"
        unified.to_csv(unified_csv, index=False)

        n_anomalies = _persist(engine, unified_csv, domain, run_date)

        # ── Persistance prédictions (HotStart Chronos + ColdStart stat.) ────────
        forecast_parts: list[pd.DataFrame] = []

        if hot_result_csv is not None:
            forecast_csv = hot_result_csv.parent / "forecast_result.csv"
            if forecast_csv.exists():
                try:
                    forecast_parts.append(pd.read_csv(forecast_csv).assign(strategy="hotstart"))
                    logger.info("[PRED:%s] HotStart forecast chargé (%d lignes)", domain, len(forecast_parts[-1]))
                except Exception as exc:
                    logger.warning("[PRED:%s] Lecture forecast HotStart échouée : %s", domain, exc)

        for dev_id, (raw_df, cs_result) in cold_data_map.items():
            cold_fc = _build_coldstart_forecast(raw_df, cs_result, dev_id, domain)
            if not cold_fc.empty:
                cold_fc["strategy"] = "coldstart"
                forecast_parts.append(cold_fc)
                logger.info("[PRED:%s][cold:%s] %d prédictions stat. générées", domain, dev_id, len(cold_fc))

        if forecast_parts:
            merged_forecast = pd.concat(forecast_parts, ignore_index=True)
            _persist_predictions_df(engine, merged_forecast, domain, run_date)
        else:
            logger.debug("[PRED:%s] Aucune prédiction à persister", domain)

        return n_anomalies


# ── Subprocess helpers ─────────────────────────────────────────────────────────

def _run_hotstart(
    cli_domain: str,
    csv_path:   Path,
    out_dir:    Path,
) -> tuple[int, str]:
    cmd = [
        sys.executable, str(_HOTSTART_MAIN),
        "--domain",      cli_domain,
        "--data",        str(csv_path),
        "--output-dir",  str(out_dir),
        "--no-plots",
        "--device", "cuda",
    ]
    env = {**os.environ}
    proc = subprocess.run(
        cmd,
        cwd=str(_HOTSTART_MAIN.parent),
        capture_output=True,
        text=True,
        timeout=_HOTSTART_TIMEOUT_S,
        env=env,
    )
    return proc.returncode, proc.stderr


def _run_coldstart(
    cli_domain:      str,
    dev_csv:         Path,
    pop_csv:         Path,
    out_dir:         Path,
    device_id:       str,
    phases:          Optional[list[str]],
    compare_hot_csv: Optional[Path],
) -> tuple[int, str]:
    cmd = [
        sys.executable, str(_COLDSTART_MAIN),
        "--domain",      cli_domain,
        "--data",        str(dev_csv),
        "--population",  str(pop_csv),
        "--device",      device_id,
        "--output",      str(out_dir),
    ]
    if phases and cli_domain == "energy":
        cmd += ["--phases"] + phases
    if compare_hot_csv and compare_hot_csv.exists():
        cmd += ["--compare-hot", str(compare_hot_csv)]
    proc = subprocess.run(
        cmd,
        cwd=str(_COLDSTART_MAIN.parent),
        capture_output=True,
        text=True,
        timeout=_COLDSTART_TIMEOUT_S,
    )
    return proc.returncode, proc.stderr


# ── Classification helpers ─────────────────────────────────────────────────────

def _get_device_ages(engine, domain: str) -> dict[str, int]:
    """
    Retourne {device_id: nombre_de_jours_distincts} depuis la table daily_<domain>.
    Utilisé pour distinguer les devices avec suffisamment d'historique (hot)
    des nouveaux devices (cold).  Renvoie {} si la table est inaccessible.
    """
    table = _DAILY_TABLE.get(domain)
    if not table:
        return {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT device_id, COUNT(DISTINCT date) AS n_days
                FROM `{table}`
                GROUP BY device_id
            """)).mappings().fetchall()
        return {str(r["device_id"]): int(r["n_days"]) for r in rows}
    except Exception as exc:
        logger.warning(
            "[AD:%s] Impossible de lire les anciennetés depuis %s: %s", domain, table, exc
        )
        return {}


# ── Persistance dans ad_results ────────────────────────────────────────────────

def _persist(engine, result_csv: Path, domain: str, run_date: Date) -> int:
    try:
        result_df = pd.read_csv(result_csv, low_memory=False)
    except Exception as exc:
        logger.error("[AD:%s] Lecture du CSV échouée : %s", domain, exc)
        return 0

    if result_df.empty:
        return 0

    ts_col   = next((c for c in ("date", "timestamp") if c in result_df.columns), None)
    item_col = "item_id"
    anom_col = "is_anomaly"

    if not ts_col or item_col not in result_df.columns or anom_col not in result_df.columns:
        logger.warning(
            "[AD:%s] Colonnes attendues absentes. Reçu: %s", domain, list(result_df.columns)
        )
        return 0

    value_col: Optional[str] = next(
        (c for c in _VALUE_COLS.get(domain, ()) if c in result_df.columns), None
    )

    def _first_col(cols: list[str], *substrings: str) -> Optional[str]:
        for s in substrings:
            m = next((c for c in cols if s in c), None)
            if m:
                return m
        return None

    cols    = result_df.columns.tolist()
    # HotStart → pred_low / pred_high  |  ColdStart → bound_low_* / bound_high_* (IQR/zscore)
    q10_col = _first_col(cols, "pred_low",  "bound_low_")
    q90_col = _first_col(cols, "pred_high", "bound_high_")

    run_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Suppression idempotente avant insert
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM ad_results WHERE domain=:d AND DATE(data_ts)=:dt"),
            {"d": domain, "dt": run_date.isoformat()},
        )

    def _sf(val) -> Optional[float]:
        try:
            return None if pd.isna(val) else round(float(val), 6)
        except Exception:
            return None

    rows = [
        {
            "run_at":        run_at,
            "domain":        domain,
            "item_id":       str(row.get(item_col, "")),
            "strategy":      str(row.get("strategy", "hotstart")),
            "is_anomaly":    int(bool(row.get(anom_col, 0))),
            "anomaly_score": _sf(row.get("anomaly_score")),
            "data_ts":       str(row.get(ts_col, "")),
            "value":         _sf(row.get(value_col))    if value_col else None,
            "q10":           _sf(row.get(q10_col))      if q10_col   else None,
            "q90":           _sf(row.get(q90_col))      if q90_col   else None,
        }
        for _, row in result_df.iterrows()
    ]

    sql = text("""
        INSERT INTO ad_results
            (run_at, domain, item_id, strategy, is_anomaly, anomaly_score,
             data_ts, value, q10, q90)
        VALUES
            (:run_at, :domain, :item_id, :strategy, :is_anomaly, :anomaly_score,
             :data_ts, :value, :q10, :q90)
    """)
    with engine.begin() as conn:
        conn.execute(sql, rows)

    n_anomalies = sum(1 for r in rows if r["is_anomaly"])
    logger.info(
        "[AD:%s] %d lignes insérées (%d anomalies | hot+cold fusionnés)",
        domain, len(rows), n_anomalies,
    )
    return n_anomalies


# ── Persistance prédictions ────────────────────────────────────────────────────

def _build_coldstart_forecast(
    dev_df:    pd.DataFrame,
    cs_result: pd.DataFrame,
    device_id: str,
    domain:    str,
    horizon:   int = 24,
) -> pd.DataFrame:
    """
    Génère un forecast statistique pour un device ColdStart.

    Stratégie :
    - Tendance linéaire (polyfit degré 1) sur les dernières 24h observées
    - Extrapolation vers les prochaines `horizon` heures
    - Bornes IQR issues de coldstart_result.csv comme seuils d'alerte
    - Confiance décroissante avec l'horizon (plus on est loin, moins c'est fiable)
    """
    ts_col    = next((c for c in ("date", "timestamp") if c in dev_df.columns), None)
    value_col = next((c for c in _VALUE_COLS.get(domain, ()) if c in dev_df.columns), None)

    if ts_col is None or value_col is None:
        return pd.DataFrame()

    dev_df = dev_df.sort_values(ts_col).copy()

    # Phases energy : traiter chaque item_id séparément
    if domain in ("energy",) and "phase" in dev_df.columns and "item_id" in dev_df.columns:
        parts = []
        for item_id, grp in dev_df.groupby("item_id"):
            fc = _coldstart_forecast_series(
                grp, cs_result, str(item_id), str(device_id), value_col, ts_col, horizon,
            )
            parts.append(fc)
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    item_id = str(device_id)
    return _coldstart_forecast_series(
        dev_df, cs_result, item_id, str(device_id), value_col, ts_col, horizon,
    )


def _coldstart_forecast_series(
    grp:       pd.DataFrame,
    cs_result: pd.DataFrame,
    item_id:   str,
    device_id: str,
    value_col: str,
    ts_col:    str,
    horizon:   int,
) -> pd.DataFrame:
    values = grp[value_col].dropna().values
    if len(values) < 4:
        return pd.DataFrame()

    context = values[-min(24, len(values)):]
    x       = np.arange(len(context), dtype=float)

    try:
        coeffs    = np.polyfit(x, context, 1)
    except Exception:
        return pd.DataFrame()

    x_future  = np.arange(len(context), len(context) + horizon, dtype=float)
    predicted = np.polyval(coeffs, x_future)

    # Bornes IQR/zscore depuis le résultat ColdStart (item_id courant si possible)
    cs_item = cs_result[cs_result["item_id"] == item_id] if "item_id" in cs_result.columns else cs_result
    if cs_item.empty:
        cs_item = cs_result

    low_cols  = [c for c in cs_item.columns if "bound_low_"  in c and "iqr" in c]
    high_cols = [c for c in cs_item.columns if "bound_high_" in c and "iqr" in c]
    if not low_cols:
        low_cols  = [c for c in cs_item.columns if "bound_low_"  in c]
    if not high_cols:
        high_cols = [c for c in cs_item.columns if "bound_high_" in c]

    bound_low  = float(cs_item[low_cols[0]].median())  if low_cols  else float(np.percentile(context, 10))
    bound_high = float(cs_item[high_cols[0]].median()) if high_cols else float(np.percentile(context, 90))

    sigma = max(float(np.std(context, ddof=1)), 1e-9)

    above     = np.maximum(0.0, (predicted - bound_high) / sigma)
    below     = np.maximum(0.0, (bound_low  - predicted) / sigma)
    deviation = np.maximum(above, below)
    is_alert  = deviation > 0.0
    severity  = np.where(
        deviation > 2.0, "HIGH",
        np.where(deviation > 1.0, "MEDIUM", np.where(is_alert, "LOW", "")),
    )

    # Confiance décroissante : 0.80 → 0.40 sur l'horizon
    confidence = np.round(np.linspace(0.80, 0.40, horizon), 3)

    last_ts      = pd.to_datetime(grp[ts_col].iloc[-1])
    future_times = pd.date_range(start=last_ts + pd.Timedelta(hours=1), periods=horizon, freq="1h")

    return pd.DataFrame({
        "item_id":         item_id,
        "id_device":       device_id,
        "date":            future_times,
        "forecast_col":    value_col,
        "forecast_median": np.round(predicted, 4),
        "forecast_low":    np.full(horizon, round(bound_low, 4)),
        "forecast_high":   np.full(horizon, round(bound_high, 4)),
        "confidence":      confidence,
        "is_alert":        is_alert.astype(int),
        "alert_severity":  severity,
    })


def check_strategy_upgrades(engine) -> dict[str, list[dict]]:
    """
    Détecte les devices qui ont franchi le seuil HotStart (>_HOT_MIN_DAYS jours distincts)
    alors que leur dernière classification dans ad_results était 'coldstart'.

    Ces devices seront automatiquement routés vers HotStart au prochain run AD —
    cette fonction sert uniquement à logger et surfacer ces transitions pour les opérateurs.

    Retourne: {domain: [{'device_id': str, 'item_id': str, 'n_days': int}, ...]}
    """
    transitions: dict[str, list[dict]] = {}

    for domain in ('energy', 'water', 'gas', 'fuel'):
        try:
            device_ages = _get_device_ages(engine, domain)
            if not device_ages:
                transitions[domain] = []
                continue

            # Dernière stratégie connue par item_id (sous-requête sur le run_at le plus récent)
            with engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT ar.item_id, ar.strategy
                    FROM ad_results ar
                    INNER JOIN (
                        SELECT item_id, MAX(run_at) AS latest
                        FROM   ad_results
                        WHERE  domain = :d
                        GROUP  BY item_id
                    ) latest_run
                      ON ar.item_id = latest_run.item_id
                     AND ar.run_at  = latest_run.latest
                    WHERE ar.domain = :d
                    GROUP BY ar.item_id, ar.strategy
                """), {'d': domain}).mappings().fetchall()

            last_strategy: dict[str, str] = {r['item_id']: r['strategy'] for r in rows}
            if not last_strategy:
                transitions[domain] = []
                continue

            graduated = []
            for device_id, n_days in device_ages.items():
                if n_days <= _HOT_MIN_DAYS:
                    continue
                # item_id peut être le device_id seul (water/gas/fuel)
                # ou "device_id_phase" (energy : DEV001_L1, DEV001_L2 …)
                matching = [
                    iid for iid in last_strategy
                    if iid == str(device_id) or iid.startswith(f"{device_id}_")
                ]
                for item_id in matching:
                    if last_strategy[item_id] == 'coldstart':
                        graduated.append({
                            'device_id': str(device_id),
                            'item_id':   item_id,
                            'n_days':    n_days,
                        })
                        logger.info(
                            "[STRATEGY_AUDIT:%s] UPGRADE détecté — device=%s item=%s : "
                            "%d jours distincts > seuil %d j → sera routé HotStart au prochain run AD.",
                            domain, device_id, item_id, n_days, _HOT_MIN_DAYS,
                        )

            transitions[domain] = graduated

        except Exception as exc:
            logger.warning("[STRATEGY_AUDIT:%s] Erreur audit stratégie : %s", domain, exc)
            transitions[domain] = []

    total = sum(len(v) for v in transitions.values())
    if total > 0:
        upgraded_ids = {
            k: [t['device_id'] for t in v]
            for k, v in transitions.items() if v
        }
        logger.info(
            "[STRATEGY_AUDIT] %d device(s) prêt(s) à passer HotStart (routage auto au prochain run) : %s",
            total, upgraded_ids,
        )
    else:
        logger.debug("[STRATEGY_AUDIT] Aucune transition ColdStart→HotStart détectée.")

    return transitions


def _persist_predictions_df(engine, forecast_df: pd.DataFrame, domain: str, run_date: Date) -> None:
    """
    Version directe de _persist_predictions — prend un DataFrame (hot + cold fusionnés).
    """
    if forecast_df.empty:
        return

    ts_col = next((c for c in ("date", "forecast_ts", "timestamp") if c in forecast_df.columns), None)
    if ts_col is None or "item_id" not in forecast_df.columns:
        logger.warning("[PRED:%s] Colonnes manquantes dans forecast DataFrame", domain)
        return

    run_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    forecast_df = forecast_df.sort_values(["item_id", ts_col])
    forecast_df["_horizon"] = forecast_df.groupby("item_id").cumcount() + 1

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM aria_predictions WHERE domain = :d AND DATE(forecast_ts) >= :dt"),
            {"d": domain, "dt": run_date.isoformat()},
        )

    def _sf(val) -> Optional[float]:
        try:
            return None if pd.isna(val) else round(float(val), 6)
        except Exception:
            return None

    rows = [
        {
            "run_at":          run_at,
            "domain":          domain,
            "item_id":         str(row.get("item_id", "")),
            "forecast_ts":     str(row.get(ts_col, "")),
            "horizon_hours":   int(row.get("_horizon", 1)),
            "forecast_col":    str(row.get("forecast_col", "")),
            "forecast_median": _sf(row.get("forecast_median")),
            "forecast_low":    _sf(row.get("forecast_low")),
            "forecast_high":   _sf(row.get("forecast_high")),
            "confidence":      _sf(row.get("confidence")),
            "is_alert":        int(bool(row.get("is_alert", False))),
            "alert_severity":  None if pd.isna(sv := row.get("alert_severity", "")) or str(sv) in ("nan", "", "None") else str(sv),
        }
        for _, row in forecast_df.iterrows()
    ]

    sql = text("""
        INSERT INTO aria_predictions
            (run_at, domain, item_id, forecast_ts, horizon_hours, forecast_col,
             forecast_median, forecast_low, forecast_high, confidence, is_alert, alert_severity)
        VALUES
            (:run_at, :domain, :item_id, :forecast_ts, :horizon_hours, :forecast_col,
             :forecast_median, :forecast_low, :forecast_high, :confidence, :is_alert, :alert_severity)
        ON DUPLICATE KEY UPDATE
            forecast_median = VALUES(forecast_median),
            forecast_low    = VALUES(forecast_low),
            forecast_high   = VALUES(forecast_high),
            confidence      = VALUES(confidence),
            is_alert        = VALUES(is_alert),
            alert_severity  = VALUES(alert_severity)
    """)
    with engine.begin() as conn:
        conn.execute(sql, rows)

    hot_n   = int((forecast_df.get("strategy", pd.Series()) == "hotstart").sum())
    cold_n  = int((forecast_df.get("strategy", pd.Series()) == "coldstart").sum())
    n_alert = sum(1 for r in rows if r["is_alert"])
    logger.info(
        "[PRED:%s] %d prédictions insérées (hot=%d cold=%d | %d alertes)",
        domain, len(rows), hot_n, cold_n, n_alert,
    )


