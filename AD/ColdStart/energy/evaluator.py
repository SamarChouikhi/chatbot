from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from common.logger import get_logger
from .config import ColdStartConfig

_log = get_logger(__name__)

_PALETTE = {
    "normal":          "#2196F3",   # blue
    "anomaly":         "#F44336",   # red
    "point_anomaly":   "#FF9800",   # orange
    "regime_change":   "#9C27B0",   # purple
    "bound_fill":      "#BBDEFB",   # light blue
    "synthetic_bg":    "#E8F5E9",   # light green background
    "real_bg":         "#FFFFFF",   # white background
}


# ── Summary tables ─────────────────────────────────────────────────────────────

def anomaly_summary(result: pd.DataFrame, config: ColdStartConfig) -> pd.DataFrame:
    """Per-device summary table (mirrors HotStart anomaly_summary structure)."""
    rows: list[dict] = []

    for item_id, group in result.groupby(config.item_col):
        total       = len(group)
        n_anom      = int(group["is_anomaly"].sum())
        n_point     = int(group.get("is_point_anomaly", pd.Series(False)).sum())
        n_regime    = int(group.get("is_regime_change", pd.Series(False)).sum())
        n_offline   = int(group.get("is_offline",       pd.Series(False)).sum())
        warmup_done = not bool(group.get("warmup_active", pd.Series(True)).any())

        row: dict = {
            "item_id":          item_id,
            "device":           str(item_id).rsplit("_", 1)[0],
            "phase":            str(item_id).rsplit("_", 1)[1] if "_" in str(item_id) else "",
            "total_hours":      total,
            "anomaly_count":    n_anom,
            "anomaly_rate":     round(n_anom / max(total, 1), 4),
            "point_anomalies":  n_point,
            "regime_change_h":  n_regime,
            "offline_hours":    n_offline,
            "warmup_complete":  warmup_done,
        }

        # Per-column breakdown
        for col in config.value_cols:
            flag = f"is_anomaly_{col}"
            if flag in group.columns:
                row[f"anomaly_{col}"] = int(group[flag].sum())

        # Per-algorithm breakdown
        for col in config.value_cols:
            for algo in ("zscore", "iqr", "isolation_forest"):
                flag = f"algo_{col}_{algo}"
                if flag in group.columns:
                    row[f"{algo}_{col}"] = int(group[flag].sum())

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    summary = pd.DataFrame(rows).sort_values("item_id").reset_index(drop=True)
    _log.info(
        "Résumé cold start : %d séries  |  %d anomalies totales",
        len(summary),
        int(summary["anomaly_count"].sum()),
    )
    return summary


def comparison_summary(
    cold_result: pd.DataFrame,
    hot_result:  pd.DataFrame | None,
    config:      ColdStartConfig,
) -> pd.DataFrame:
    """
    Side-by-side comparison of cold-start vs hot-start detection rates.
    Returns empty DataFrame if hot_result is None.
    """
    if hot_result is None or hot_result.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    common_items = set(cold_result[config.item_col].unique()) & set(
        hot_result[config.item_col].unique()
    )

    for item_id in sorted(common_items):
        cold_g = cold_result[cold_result[config.item_col] == item_id]
        hot_g  = hot_result[hot_result[config.item_col]  == item_id]

        cold_rate = round(float(cold_g["is_anomaly"].mean()), 4)
        hot_rate  = round(float(hot_g["is_anomaly"].mean()),  4)

        rows.append({
            "item_id":          item_id,
            "cold_anomaly_rate": cold_rate,
            "hot_anomaly_rate":  hot_rate,
            "delta":             round(cold_rate - hot_rate, 4),
        })

    return pd.DataFrame(rows)


# ── Plots ──────────────────────────────────────────────────────────────────────

def _save_fig(fig: plt.Figure, path: str) -> None:
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    _log.info("Saved: %s", path)


def plot_anomaly_series(
    result:     pd.DataFrame,
    config:     ColdStartConfig,
    output_dir: str,
) -> None:
    """One plot per item_id: time series with anomaly overlay + per-algo flags."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for item_id, group in result.groupby(config.item_col):
        group = group.sort_values(config.timestamp_col).copy()
        ts    = pd.to_datetime(group[config.timestamp_col])
        col   = config.value_col

        if col not in group.columns:
            continue

        values  = group[col].to_numpy(dtype=float)
        is_anom = group["is_anomaly"].to_numpy(dtype=bool)
        is_syn  = group.get("is_synthetic", pd.Series(False, index=group.index)).to_numpy(dtype=bool)

        fig, axes = plt.subplots(
            nrows=2, figsize=(16, 8), sharex=True,
            gridspec_kw={"height_ratios": [3, 1]},
        )
        fig.suptitle(
            f"Cold Start — {item_id}  |  {col}  |  {int(is_anom.sum())} anomalies",
            fontsize=12, fontweight="bold",
        )

        ax_main, ax_flag = axes

        # ── Background shading: synthetic vs real ─────────────────────────────
        if is_syn.any():
            syn_changes = np.diff(is_syn.astype(int), prepend=0, append=0)
            starts = np.where(syn_changes == 1)[0]
            ends   = np.where(syn_changes == -1)[0]
            for s, e in zip(starts, ends):
                ax_main.axvspan(
                    ts.iloc[min(s, len(ts)-1)],
                    ts.iloc[min(e-1, len(ts)-1)],
                    alpha=0.12, color=_PALETTE["synthetic_bg"],
                    label="Synthétique" if s == starts[0] else "",
                )

        # ── Main series ───────────────────────────────────────────────────────
        ax_main.plot(ts, values, color=_PALETTE["normal"], lw=0.8, alpha=0.85, label=col)

        # ── IQR bounds (if present) ───────────────────────────────────────────
        low_col  = f"bound_low_{col}_iqr"
        high_col = f"bound_high_{col}_iqr"
        if low_col in group.columns and high_col in group.columns:
            ax_main.fill_between(
                ts,
                group[low_col], group[high_col],
                alpha=0.15, color=_PALETTE["bound_fill"], label="IQR bounds",
            )

        # ── Anomaly scatter ────────────────────────────────────────────────────
        is_point  = group.get("is_point_anomaly",  pd.Series(False, index=group.index)).to_numpy(dtype=bool)
        is_regime = group.get("is_regime_change",  pd.Series(False, index=group.index)).to_numpy(dtype=bool)

        if is_point.any():
            ax_main.scatter(
                ts[is_point], values[is_point],
                color=_PALETTE["point_anomaly"], s=25, zorder=5, label="Point anomaly",
            )
        if is_regime.any():
            ax_main.scatter(
                ts[is_regime], values[is_regime],
                color=_PALETTE["regime_change"], marker="s", s=20, zorder=5, label="Regime change",
            )

        ax_main.set_ylabel(col)
        ax_main.legend(fontsize=7, loc="upper right")
        ax_main.grid(True, alpha=0.3)

        # ── Flag panel: per-algorithm binary flags ────────────────────────────
        y_pos   = 0
        y_ticks = []
        y_labels= []
        for algo in ("zscore", "iqr", "isolation_forest"):
            flag_col = f"algo_{col}_{algo}"
            if flag_col not in group.columns:
                continue
            flags = group[flag_col].to_numpy(dtype=bool)
            if flags.any():
                ax_flag.scatter(
                    ts[flags], np.full(flags.sum(), y_pos),
                    marker="|", s=40, color=_PALETTE["anomaly"], lw=0.8,
                )
            y_ticks.append(y_pos)
            y_labels.append(algo)
            y_pos += 1

        # Global ensemble flag
        ax_flag.scatter(
            ts[is_anom], np.full(is_anom.sum(), y_pos),
            marker="|", s=60, color=_PALETTE["anomaly"], lw=1.2,
        )
        y_ticks.append(y_pos)
        y_labels.append("ensemble")

        ax_flag.set_yticks(y_ticks)
        ax_flag.set_yticklabels(y_labels, fontsize=8)
        ax_flag.set_ylabel("Algorithme", fontsize=8)
        ax_flag.set_ylim(-0.5, y_pos + 0.5)
        ax_flag.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax_flag.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.setp(ax_flag.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=7)
        ax_flag.grid(True, alpha=0.2)

        safe_id = str(item_id).replace("/", "_").replace("\\", "_")
        _save_fig(fig, str(out / f"coldstart_{safe_id}.png"))


def plot_population_vs_new_device(
    population_df: pd.DataFrame,
    new_device_df: pd.DataFrame,
    config:        ColdStartConfig,
    output_dir:    str,
) -> None:
    """
    Distribution comparison: population devices vs new device's detected values.
    One histogram per value column.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for col in config.value_cols:
        if col not in population_df.columns or col not in new_device_df.columns:
            continue

        pop_vals = population_df[col].dropna().to_numpy()
        new_vals = new_device_df[col].dropna().to_numpy()

        if len(pop_vals) == 0 or len(new_vals) == 0:
            continue

        fig, ax = plt.subplots(figsize=(10, 5))
        fig.suptitle(
            f"Distribution {col} — Population vs {config.new_device_id}",
            fontsize=12, fontweight="bold",
        )

        bins = np.linspace(
            min(np.percentile(pop_vals, 1), np.percentile(new_vals, 1)),
            max(np.percentile(pop_vals, 99), np.percentile(new_vals, 99)),
            60,
        )

        ax.hist(pop_vals, bins=bins, density=True, alpha=0.5,
                color=_PALETTE["normal"], label=f"Population ({len(population_df[config.item_col].unique())} devices)")
        ax.hist(new_vals, bins=bins, density=True, alpha=0.5,
                color=_PALETTE["anomaly"], label=f"Nouveau device ({config.new_device_id})")

        ax.set_xlabel(col)
        ax.set_ylabel("Densité")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)

        _save_fig(fig, str(out / f"distribution_{col}.png"))


def plot_algo_comparison(
    result:     pd.DataFrame,
    config:     ColdStartConfig,
    output_dir: str,
) -> None:
    """
    Stacked bar chart: anomaly counts per algorithm per device-phase series.
    Useful to see which algorithm is the most sensitive and where.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    col = config.value_col
    algo_names = ["zscore", "iqr", "isolation_forest", "ensemble"]
    counts: dict[str, list[int]] = {a: [] for a in algo_names}
    labels: list[str] = []

    for item_id, group in result.groupby(config.item_col):
        labels.append(str(item_id))
        for algo in ("zscore", "iqr", "isolation_forest"):
            flag = f"algo_{col}_{algo}"
            counts[algo].append(int(group[flag].sum()) if flag in group.columns else 0)
        counts["ensemble"].append(int(group["is_anomaly"].sum()))

    if not labels:
        return

    x  = np.arange(len(labels))
    w  = 0.18
    colors = ["#64B5F6", "#81C784", "#FFB74D", _PALETTE["anomaly"]]

    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 1.5), 5))
    for i, (algo, color) in enumerate(zip(algo_names, colors)):
        ax.bar(x + i * w, counts[algo], width=w, label=algo, color=color, alpha=0.85)

    ax.set_xticks(x + w * 1.5)
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("Nombre d'anomalies")
    ax.set_title("Comparaison algorithmes cold start par série")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    _save_fig(fig, str(out / "algo_comparison.png"))
