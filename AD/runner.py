"""
ARIA AD — Unified runner: routes each device to HotStart or ColdStart
based on the volume of available historical data.

Routing rule (user-defined):
    device has > COLD_THRESHOLD_HOURS rows in the input DataFrame → HotStart (Chronos)
    device has ≤ COLD_THRESHOLD_HOURS rows                        → ColdStart (statistical ensemble)

Default threshold: 720 rows ≈ 30 days of hourly data.

Both runners are called as isolated subprocesses to avoid PyTorch / sklearn
memory conflicts and import collisions between the two packages.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
_AD_DIR         = Path(__file__).parent.resolve()
_HOTSTART_MAIN  = _AD_DIR / "HotStart"  / "main.py"
_COLDSTART_MAIN = _AD_DIR / "ColdStart" / "main.py"

# ── Threshold ──────────────────────────────────────────────────────────────────
COLD_THRESHOLD_HOURS: int = 720  # 30 days × 24 h

# ── Domain → device column mapping ────────────────────────────────────────────
_DEVICE_COL: dict[str, str] = {
    "energy": "id_device",
    "water":  "id_device",
    "gaz":    "id_device",
    "fuel":   "id_device",
}

# ── Domain → ColdStart result filename (each pipeline saves a domain-specific name)
_CS_RESULT_FILE: dict[str, str] = {
    "energy": "coldstart_result.csv",
    "water":  "coldstart_water_result.csv",
    "gaz":    "coldstart_gaz_result.csv",
    "fuel":   "coldstart_fuel_result.csv",
}

_log = logging.getLogger("aria.ad.runner")


# ── Public API ─────────────────────────────────────────────────────────────────

def classify_devices(
    df: pd.DataFrame,
    device_col: str,
    threshold: int = COLD_THRESHOLD_HOURS,
) -> tuple[list, list]:
    """
    Split device list into (hot_devices, cold_devices) by raw row count.

    A device is considered "hot" when it exceeds *threshold* rows,
    meaning it has enough history for Chronos sliding-window forecasting.
    """
    counts = df.groupby(device_col).size()
    hot    = sorted(counts[counts >  threshold].index.tolist())
    cold   = sorted(counts[counts <= threshold].index.tolist())
    return hot, cold


def run_domain(
    domain:          str,
    df:              pd.DataFrame,
    output_dir:      Path,
    generate_plots:  bool = True,
    retrain:         bool = False,
    accelerator:     str  = "cpu",
    threshold_hours: int  = COLD_THRESHOLD_HOURS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Main integration point.

    1. Classifies every device as hot or cold.
    2. Runs HotStart (subprocess) on hot devices.
    3. Runs ColdStart (subprocess) on each cold device, using the hot-device
       data as statistical population; passes HotStart results for comparison.
    4. Merges both result DataFrames and adds a 'strategy' column.
    5. Writes anomalies_result.csv + anomalies_summary.csv to *output_dir*.

    Returns (unified_result_df, summary_df).
    """
    if domain not in _DEVICE_COL:
        raise ValueError(
            f"Domaine inconnu: {domain!r}. Valeurs acceptées: {sorted(_DEVICE_COL)}"
        )

    device_col = _DEVICE_COL[domain]
    if device_col not in df.columns:
        raise ValueError(
            f"Colonne '{device_col}' absente du DataFrame (colonnes: {df.columns.tolist()})"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    hot_devices, cold_devices = classify_devices(df, device_col, threshold_hours)
    _log.info(
        "[%s] Routage — hot: %d device(s) | cold: %d device(s) | seuil: %d h",
        domain, len(hot_devices), len(cold_devices), threshold_hours,
    )

    hot_result_df:  pd.DataFrame = pd.DataFrame()
    cold_result_df: pd.DataFrame = pd.DataFrame()

    with tempfile.TemporaryDirectory(prefix=f"aria_unified_{domain}_") as _tmp:
        tmp = Path(_tmp)

        # ── HotStart ──────────────────────────────────────────────────────────
        hot_result_csv: Optional[Path] = None

        if hot_devices:
            hot_df  = df[df[device_col].isin(hot_devices)].copy()
            hot_csv = tmp / f"{domain}_hot.csv"
            hot_out = tmp / "hot_output"
            hot_out.mkdir()
            hot_df.to_csv(hot_csv, index=False)
            _log.info("[HotStart:%s] %d lignes | %d device(s)", domain, len(hot_df), len(hot_devices))

            rc = _run_hotstart(domain, hot_csv, hot_out, accelerator, retrain, generate_plots)
            candidate = hot_out / "anomalies_result.csv"
            if rc == 0 and candidate.exists():
                hot_result_df              = pd.read_csv(candidate)
                hot_result_df["strategy"]  = "hotstart"
                hot_result_csv             = candidate
                n_anom = int(_col(hot_result_df, "is_anomaly").sum())
                _log.info("[HotStart:%s] %d lignes lues | %d anomalies", domain, len(hot_result_df), n_anom)
            else:
                _log.error("[HotStart:%s] échec ou résultat absent (exit=%d)", domain, rc)

        # ── ColdStart — un subprocess par device froid ────────────────────────
        if cold_devices:
            # Population = hot-device data (or full df when no hot devices exist)
            pop_source = df[df[device_col].isin(hot_devices)] if hot_devices else df
            pop_csv    = tmp / f"{domain}_population.csv"
            pop_source.to_csv(pop_csv, index=False)

            cold_parts: list[pd.DataFrame] = []

            for dev_id in cold_devices:
                dev_df  = df[df[device_col] == dev_id].copy()
                dev_csv = tmp / f"cold_{dev_id}.csv"
                dev_out = tmp / f"cold_{dev_id}"
                dev_out.mkdir()
                dev_df.to_csv(dev_csv, index=False)

                # Energy: infer phases present in real data
                phases: Optional[list[str]] = None
                if domain == "energy" and "phase" in dev_df.columns:
                    phases = sorted(dev_df["phase"].dropna().unique().tolist())

                rc = _run_coldstart(
                    domain          = domain,
                    dev_csv         = dev_csv,
                    pop_csv         = pop_csv,
                    out_dir         = dev_out,
                    device_id       = str(dev_id),
                    phases          = phases,
                    compare_hot_csv = hot_result_csv,
                )
                res_file = dev_out / _CS_RESULT_FILE.get(domain, "coldstart_result.csv")
                if rc == 0 and res_file.exists():
                    part              = pd.read_csv(res_file)
                    part["strategy"]  = "coldstart"
                    cold_parts.append(part)
                    n_anom = int(_col(part, "is_anomaly").sum())
                    _log.info(
                        "[ColdStart:%s][%s] %d lignes | %d anomalies",
                        domain, dev_id, len(part), n_anom,
                    )
                else:
                    _log.error("[ColdStart:%s][%s] échec (exit=%d)", domain, dev_id, rc)

            if cold_parts:
                cold_result_df = pd.concat(cold_parts, ignore_index=True)

        # ── Merge ─────────────────────────────────────────────────────────────
        frames = [f for f in (hot_result_df, cold_result_df) if not f.empty]
        if not frames:
            _log.warning("[%s] Aucun résultat — tous les runs ont échoué.", domain)
            return pd.DataFrame(), pd.DataFrame()

        unified = pd.concat(frames, ignore_index=True)
        _fill_missing_cols(unified)

        result_path  = output_dir / "anomalies_result.csv"
        summary_path = output_dir / "anomalies_summary.csv"
        unified.to_csv(result_path,  index=False)
        summary = _build_summary(unified, device_col)
        summary.to_csv(summary_path, index=False)

        n_hot  = int((unified["strategy"] == "hotstart").sum())
        n_cold = int((unified["strategy"] == "coldstart").sum())
        n_anom = int(_col(unified, "is_anomaly").sum())
        _log.info(
            "[%s] Résultat unifié: %d lignes (hot=%d cold=%d) | %d anomalies → %s",
            domain, len(unified), n_hot, n_cold, n_anom, result_path,
        )
        return unified, summary


# ── Subprocess helpers ─────────────────────────────────────────────────────────

def _run_hotstart(
    domain:      str,
    csv_path:    Path,
    out_dir:     Path,
    accelerator: str,
    retrain:     bool,
    plots:       bool,
) -> int:
    cmd = [
        sys.executable, str(_HOTSTART_MAIN),
        "--domain",      domain,
        "--data",        str(csv_path),
        "--output-dir",  str(out_dir),
        "--device",      accelerator,
    ]
    if not plots:
        cmd.append("--no-plots")
    if retrain:
        cmd.append("--retrain")
    return _run_proc(cmd, cwd=_HOTSTART_MAIN.parent, label=f"HotStart:{domain}", timeout=3600)


def _run_coldstart(
    domain:          str,
    dev_csv:         Path,
    pop_csv:         Path,
    out_dir:         Path,
    device_id:       str,
    phases:          Optional[list[str]],
    compare_hot_csv: Optional[Path],
) -> int:
    cmd = [
        sys.executable, str(_COLDSTART_MAIN),
        "--domain",      domain,
        "--data",        str(dev_csv),
        "--population",  str(pop_csv),
        "--device",      device_id,
        "--output",      str(out_dir),
    ]
    if phases and domain == "energy":
        cmd += ["--phases"] + phases
    if compare_hot_csv and compare_hot_csv.exists():
        cmd += ["--compare-hot", str(compare_hot_csv)]
    return _run_proc(
        cmd, cwd=_COLDSTART_MAIN.parent,
        label=f"ColdStart:{domain}:{device_id}", timeout=1800,
    )


def _run_proc(cmd: list, cwd: Path, label: str, timeout: int) -> int:
    _log.debug("[%s] %s", label, " ".join(str(c) for c in cmd))
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        _log.error("[%s] Timeout après %ds", label, timeout)
        return -1
    if proc.returncode != 0:
        _log.error("[%s] exit=%d\n%s", label, proc.returncode, proc.stderr[-2000:])
    return proc.returncode


# ── Post-processing helpers ────────────────────────────────────────────────────

def _col(df: pd.DataFrame, name: str, fill=0) -> pd.Series:
    """Return column *name* or a zero-filled Series if absent."""
    return df[name] if name in df.columns else pd.Series(fill, index=df.index)


def _fill_missing_cols(df: pd.DataFrame) -> None:
    """
    Ensure columns produced by only one strategy exist in the merged DataFrame.
    HotStart-only: pred_median/low/high
    ColdStart-only: warmup_active, is_synthetic
    """
    for col in ("pred_median", "pred_low", "pred_high", "warmup_active", "is_synthetic"):
        if col not in df.columns:
            df[col] = float("nan")


def _build_summary(df: pd.DataFrame, device_col: str) -> pd.DataFrame:
    group_cols = [c for c in (device_col, "strategy") if c in df.columns]
    rows: list[dict] = []
    for keys, grp in df.groupby(group_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)
        rows.append({
            **dict(zip(group_cols, keys)),
            "total_points":  len(grp),
            "anomaly_count": int(_col(grp, "is_anomaly").sum()),
            "anomaly_rate":  round(float(_col(grp, "is_anomaly").mean()), 4),
            "max_score":     round(float(_col(grp, "anomaly_score", 0.0).max()), 4),
        })
    return pd.DataFrame(rows)
