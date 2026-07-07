"""
Evaluator for gaz — adapté du module water.
Couleurs : orange/teal (identité visuelle gaz).
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common.base_evaluator import anomaly_summary as _base_summary
from common.logger import get_logger
from .config import GazConfig

_log = get_logger(__name__)

# ── Design system gaz ─────────────────────────────────────────────────────────

_C = {
    "real":           "#00695c",   # teal foncé       — consommation réelle
    "pred_fill":      "#fff3e0",   # orange très clair — intervalle de confiance
    "pred_low_line":  "#e65100",   # orange foncé      — borne inférieure
    "pred_high_line": "#e65100",
    "pred_median":    "#bf360c",   # rouge-orange foncé — médiane prédite
    "anom_region":    "#d32f2f",
    "LOW":            "#e53935",
    "MEDIUM":         "#b71c1c",
    "HIGH":           "#7f0000",
    "score_fill":     "#ef9a9a",
    "regime":         "#6a1b9a",
    "forecast":       "#e65100",
    "forecast_band":  "#ffe0b2",
    "bg":             "#fafbfc",
    "grid":           "#e3e8ee",
    "zero":           "#78909c",
}

_LABEL = {
    "conso":            "Consommation gaz (L/h)",
    "avg_debit_per_min":"Debit moyen (L/min)",
    "min_debit_per_min":"Debit min (L/min)",
    "max_debit_per_min":"Debit max (L/min)",
    "index":            "Index compteur gaz",
}
_UNIT = {
    "conso":            "L/h",
    "avg_debit_per_min":"L/min",
    "min_debit_per_min":"L/min",
    "max_debit_per_min":"L/min",
    "index":            "",
}


def _label(col: str) -> str:
    return _LABEL.get(col, col)


def _severity(score: float) -> str:
    if score >= 5:  return "HIGH"
    if score >= 2:  return "MEDIUM"
    return "LOW"


def _quality(pct_inside: float) -> tuple[str, str, str]:
    if pct_inside >= 90: return "Excellent", "#2e7d32", "V"
    if pct_inside >= 75: return "Bon",       "#e65100", "~"
    return "Faible",         "#b71c1c", "X"


def _fmt_mae(val: float) -> str:
    if val < 1:   return f"{val:.2f}"
    if val < 100: return f"{val:.1f}"
    return f"{val:.0f}"


def _apply_style() -> None:
    for name in ("seaborn-v0_8-whitegrid", "seaborn-whitegrid"):
        try:
            plt.style.use(name)
            break
        except OSError:
            continue
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 12,
        "axes.titlesize": 13, "axes.titleweight": "bold",
        "axes.labelsize": 11, "axes.facecolor": _C["bg"],
        "figure.facecolor": "white",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": _C["grid"], "grid.linewidth": 0.5,
        "legend.framealpha": 0.95, "legend.edgecolor": "#cccccc",
        "legend.fontsize": 10, "xtick.labelsize": 10, "ytick.labelsize": 10,
    })


def _smart_zoom(data: pd.DataFrame, tcol: str, zoom_n: int) -> pd.DataFrame:
    if not data["is_anomaly"].any():
        return data.tail(zoom_n)
    worst_pos = data.index.get_loc(data["anomaly_score"].idxmax())
    half  = zoom_n // 2
    start = max(0, worst_pos - half)
    end   = min(len(data), start + zoom_n)
    return data.iloc[max(0, end - zoom_n): end]


def _clip_pred_to_signal(pred_low, pred_high, pred_median, real):
    clean = real.dropna()
    if clean.empty:
        return pred_low, pred_high, pred_median
    p01  = float(clean.quantile(0.01))
    p99  = float(clean.quantile(0.99))
    span = max(abs(p99 - p01), abs(float(clean.max())) * 0.05, 1e-9)
    lo, hi = p01 - 2.0 * span, p99 + 2.0 * span
    return pred_low.clip(lo, hi), pred_high.clip(lo, hi), pred_median.clip(lo, hi)


def _clip_yaxis(ax, series, margin=0.12):
    clean = series.dropna()
    if clean.empty:
        return
    p02, p98   = float(clean.quantile(0.02)), float(clean.quantile(0.98))
    sig_max    = float(clean.max())
    if sig_max > 3 * (p98 + 1e-9):
        span = max(p98 - p02, 1e-9)
        ax.set_ylim(p02 - margin * span, p98 + margin * span * 2)
    else:
        span = max(sig_max - p02, 1e-9)
        ax.set_ylim(min(p02 - margin * span, -0.05 * span), sig_max + margin * span)


def _status_badge(ax, n_anom, n_point, n_regime, total):
    rate = n_anom / max(total, 1)
    if n_anom == 0:
        color, label = "#2e7d32", "V  OK"
    elif rate >= 0.05 or n_point >= 20:
        color, label = "#b71c1c", "X  ALERTE"
    else:
        color, label = "#e65100", "!  ATTENTION"
    ax.text(
        0.003, 0.975, f"  {label}  ",
        transform=ax.transAxes, va="top", ha="left",
        fontsize=12, fontweight="bold", color="white",
        bbox=dict(boxstyle="square,pad=0.45", facecolor=color, edgecolor="none", alpha=0.97),
        zorder=20,
    )


def _anomaly_rug(ax, data, tcol):
    point_col = "is_point_anomaly" if "is_point_anomaly" in data.columns else "is_anomaly"
    sub = data[data[point_col]]
    if not sub.empty:
        ax.plot(
            pd.to_datetime(sub[tcol]), np.full(len(sub), 0.04),
            marker="|", markersize=14, markeredgewidth=2.0,
            color=_C["anom_region"], linestyle="none",
            transform=ax.get_xaxis_transform(),
            alpha=0.92, zorder=9, clip_on=True,
        )


def _draw_real_pred_anomalies(ax, data, tcol, vcol, config, show_regions=True):
    handles = []
    tcol_dt = pd.to_datetime(data[tcol])

    pred = data[data["pred_median"].notna()].copy()
    if not pred.empty:
        pred_t = pd.to_datetime(pred[tcol])
        p_lo, p_hi, p_med = _clip_pred_to_signal(
            pred["pred_low"], pred["pred_high"], pred["pred_median"], data[vcol],
        )
        ax.fill_between(pred_t, p_lo, p_hi, alpha=0.20, color=_C["pred_fill"], zorder=1)
        ax.plot(pred_t, p_lo, color=_C["pred_low_line"],  linewidth=1.2, alpha=0.85, zorder=2)
        ax.plot(pred_t, p_hi, color=_C["pred_high_line"], linewidth=1.2, alpha=0.85, zorder=2)
        ax.plot(pred_t, p_med, color=_C["pred_median"], linestyle="--", linewidth=1.4, zorder=3)
        handles.append(mpatches.Patch(
            color=_C["pred_fill"], alpha=0.55,
            label=f"Zone normale [q{int(config.q_low*100)}-q{int(config.q_high*100)}]",
        ))
        handles.append(plt.Line2D(
            [0], [0], color=_C["pred_median"], linestyle="--",
            linewidth=1.6, label="Mediane Chronos",
        ))

    ax.plot(tcol_dt, data[vcol], color=_C["real"], linewidth=1.8, zorder=5)
    _clip_yaxis(ax, data[vcol])
    handles.insert(0, plt.Line2D(
        [0], [0], color=_C["real"], linewidth=2.0, label=f"Reel - {_label(vcol)}",
    ))

    if show_regions and "is_regime_change" in data.columns and data["is_regime_change"].any():
        n_rg = int(data["is_regime_change"].sum())
        ax.fill_between(tcol_dt, 0, 1, where=data["is_regime_change"].values,
                        transform=ax.get_xaxis_transform(),
                        alpha=0.09, color=_C["regime"], zorder=1.5)
        handles.append(mpatches.Patch(
            color=_C["regime"], alpha=0.5, label=f"Changement de regime ({n_rg}h)",
        ))

    point_col = "is_point_anomaly" if "is_point_anomaly" in data.columns else "is_anomaly"
    if show_regions and data[point_col].any():
        ax.fill_between(tcol_dt, 0, 1, where=data[point_col].values,
                        transform=ax.get_xaxis_transform(),
                        alpha=0.15, color=_C["anom_region"], zorder=2)
        anom = data[data[point_col] & data[vcol].notna()]
        if not anom.empty:
            ax.scatter(pd.to_datetime(anom[tcol]), anom[vcol],
                       color=_C["anom_region"], s=60, marker="o", zorder=7,
                       edgecolors="white", linewidths=0.9)
            handles.append(mpatches.Patch(
                color=_C["anom_region"], label=f"Anomalie ({len(anom)})",
            ))
    return handles


def _draw_score_panel(ax, data, tcol):
    score   = data["anomaly_score"].fillna(0)
    tcol_dt = pd.to_datetime(data[tcol])
    ax.fill_between(tcol_dt, 0, score, where=(score > 0),
                    color=_C["score_fill"], alpha=0.85, zorder=2)
    ax.plot(tcol_dt, score, color=_C["HIGH"], linewidth=0.6, zorder=3)
    ax.axhline(2, color=_C["MEDIUM"], linestyle=":", linewidth=0.9, alpha=0.7)
    ax.axhline(5, color=_C["HIGH"],   linestyle=":", linewidth=0.9, alpha=0.7)
    ax.text(0.001, 2.1, "MEDIUM", transform=ax.get_yaxis_transform(), fontsize=6.5,
            color=_C["MEDIUM"], va="bottom")
    ax.text(0.001, 5.1, "HIGH",   transform=ax.get_yaxis_transform(), fontsize=6.5,
            color=_C["HIGH"],   va="bottom")
    ax.set_ylim(0, max(score.max() * 1.15, 6))
    ax.set_ylabel("Score\nanomal.", fontsize=7.5, labelpad=2)
    ax.tick_params(axis="y", labelsize=7)


def _fmt_full(ax, data, tcol):
    span = (pd.to_datetime(data[tcol].max()) - pd.to_datetime(data[tcol].min())).days
    if span > 180:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    elif span > 60:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    else:
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=8)


def _fmt_zoom(ax, zoom, tcol):
    span = (pd.to_datetime(zoom[tcol].max()) - pd.to_datetime(zoom[tcol].min())).days
    if span >= 7:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    else:
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=12))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m\n%Hh"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=7)


# ── Summary ───────────────────────────────────────────────────────────────────

def anomaly_summary(df: pd.DataFrame, config: GazConfig) -> pd.DataFrame:
    base = _base_summary(df, item_col=config.item_col, extra_cols=[config.device_col])
    for col in config.value_cols:
        flag_col = f"is_anomaly_{col}"
        if flag_col in df.columns:
            per_col = (
                df.groupby(config.item_col)[flag_col]
                .sum().astype(int).rename(f"anomalies_{col}")
            )
            base = base.merge(per_col, on=config.item_col, how="left")
    return base


def forecast_summary(forecast_df: pd.DataFrame, config: GazConfig) -> pd.DataFrame:
    if forecast_df.empty:
        return pd.DataFrame()
    rows = []
    for (item_id, col), grp in forecast_df.groupby(
        [config.item_col, "forecast_col"], sort=True
    ):
        rows.append({
            config.item_col:        item_id,
            config.device_col:      item_id,
            "forecast_col":         col,
            "total_hours":          len(grp),
            "alert_count":          int(grp["is_alert"].sum()),
            "HIGH":                 int((grp["alert_severity"] == "HIGH").sum()),
            "MEDIUM":               int((grp["alert_severity"] == "MEDIUM").sum()),
            "LOW":                  int((grp["alert_severity"] == "LOW").sum()),
            "avg_confidence":       round(float(grp["confidence"].mean()), 3),
            "low_confidence_hours": int((grp["confidence"] < config.min_confidence).sum()),
        })
    return pd.DataFrame(rows)


# ── Overview plots ────────────────────────────────────────────────────────────

def plot_overview_anomaly(df: pd.DataFrame, config: GazConfig) -> None:
    _apply_style()
    primary = config.value_col
    devices = sorted(df[config.device_col].unique())
    n       = len(devices)

    t_min = pd.to_datetime(df[config.timestamp_col].min()).strftime("%d/%m/%Y")
    t_max = pd.to_datetime(df[config.timestamp_col].max()).strftime("%d/%m/%Y")

    fig       = plt.figure(figsize=(26, max(n * 5.5, 8.0)), facecolor="white")
    fig.suptitle(
        f"ARIA BMS  -  Detection d'anomalies Gaz  -  {n} devices  |  {t_min} -> {t_max}",
        fontsize=14, fontweight="bold", y=0.992,
    )

    top_margin = 0.975
    bottom_margin = 0.015
    slot_h    = (top_margin - bottom_margin) / n
    inner_h   = slot_h - 0.008

    for idx, device_id in enumerate(devices):
        data = (
            df[df[config.device_col] == device_id]
            .sort_values(config.timestamp_col).reset_index(drop=True).copy()
        )
        data[config.timestamp_col] = pd.to_datetime(data[config.timestamp_col])

        slot_top    = top_margin - idx * slot_h
        slot_bottom = slot_top - inner_h
        gs = gridspec.GridSpec(
            2, 1, height_ratios=[4, 1], hspace=0.06,
            top=slot_top, bottom=slot_bottom, left=0.06, right=0.97, figure=fig,
        )
        ax_main  = fig.add_subplot(gs[0])
        ax_score = fig.add_subplot(gs[1], sharex=ax_main)

        n_anom   = int(data["is_anomaly"].sum())
        n_point  = int(data["is_point_anomaly"].sum()) if "is_point_anomaly" in data.columns else n_anom
        n_regime = int(data["is_regime_change"].sum()) if "is_regime_change" in data.columns else 0

        handles = _draw_real_pred_anomalies(ax_main, data, config.timestamp_col, primary, config)
        _anomaly_rug(ax_main, data, config.timestamp_col)
        _status_badge(ax_main, n_anom, n_point, n_regime, len(data))

        ax_main.set_title(
            f"Device {device_id}   -   {n_point} anomalie(s)   |   {n_regime}h de derive",
            loc="left", fontsize=10, pad=5,
        )
        ax_main.set_ylabel(_label(primary), fontsize=9)
        ax_main.legend(handles=handles, loc="upper right", ncol=2, fontsize=8, framealpha=0.95)
        plt.setp(ax_main.get_xticklabels(), visible=False)

        _draw_score_panel(ax_score, data, config.timestamp_col)
        _fmt_full(ax_score, data, config.timestamp_col)
        ax_score.tick_params(axis="x", labelsize=8)

    os.makedirs(config.output_dir, exist_ok=True)
    out = os.path.join(config.output_dir, "overview_anomaly.png")
    fig.savefig(out, dpi=130)
    plt.close(fig)
    _log.info("Saved: %s", out)


def plot_overview_real_vs_pred(df: pd.DataFrame, config: GazConfig) -> None:
    _apply_style()
    primary = config.value_col
    devices = sorted(df[config.device_col].unique())
    n       = len(devices)

    t_min = pd.to_datetime(df[config.timestamp_col].min()).strftime("%d/%m/%Y")
    t_max = pd.to_datetime(df[config.timestamp_col].max()).strftime("%d/%m/%Y")

    fig = plt.figure(figsize=(26, max(n * 4.0, 8.0)), facecolor="white")
    fig.suptitle(
        f"ARIA BMS  -  Reel vs Prediction Chronos (Gaz)  -  {n} devices  |  {t_min} -> {t_max}",
        fontsize=14, fontweight="bold", y=0.992,
    )
    top_margin = 0.975
    bottom_margin = 0.015
    slot_h  = (top_margin - bottom_margin) / n
    inner_h = slot_h - 0.008

    for idx, device_id in enumerate(devices):
        data = (
            df[df[config.device_col] == device_id]
            .sort_values(config.timestamp_col).reset_index(drop=True).copy()
        )
        data[config.timestamp_col] = pd.to_datetime(data[config.timestamp_col])

        slot_top    = top_margin - idx * slot_h
        slot_bottom = slot_top - inner_h
        gs = gridspec.GridSpec(
            1, 1, top=slot_top, bottom=slot_bottom, left=0.06, right=0.97, figure=fig,
        )
        ax = fig.add_subplot(gs[0])

        real = data[primary]
        pred = data[data["pred_median"].notna()]

        if not pred.empty:
            pt = pd.to_datetime(pred[config.timestamp_col])
            p_lo, p_hi, p_med = _clip_pred_to_signal(
                pred["pred_low"], pred["pred_high"], pred["pred_median"], real,
            )
            ax.fill_between(pt, p_lo, p_hi, alpha=0.20, color=_C["pred_fill"], zorder=1)
            ax.plot(pt, p_med, color=_C["pred_median"], linestyle="--",
                    linewidth=1.4, zorder=3, label="Mediane Chronos")

        point_col = "is_point_anomaly" if "is_point_anomaly" in data.columns else "is_anomaly"
        n_out = int(data[point_col].sum())
        if n_out > 0:
            ax.fill_between(
                data[config.timestamp_col], 0, 1, where=data[point_col].values,
                transform=ax.get_xaxis_transform(),
                alpha=0.13, color=_C["anom_region"], zorder=1.5,
                label=f"Hors bande ({n_out})",
            )

        ax.plot(data[config.timestamp_col], real,
                color=_C["real"], linewidth=1.3, zorder=5, label=f"Reel - {_label(primary)}")
        _clip_yaxis(ax, real)

        cov_txt = "---"
        if not pred.empty:
            inside  = (pred[primary] >= pred["pred_low"]) & (pred[primary] <= pred["pred_high"])
            cov_txt = f"Couverture : {inside.mean() * 100:.1f} %"

        ax.set_title(
            f"Device {device_id}   -   {cov_txt}   |   {n_out} point(s) hors bande",
            loc="left", fontsize=10, pad=5,
        )
        ax.set_ylabel(_label(primary), fontsize=9)
        ax.legend(loc="upper right", ncol=3, fontsize=8, framealpha=0.95)
        _fmt_full(ax, data, config.timestamp_col)
        ax.tick_params(axis="x", labelsize=8)

    os.makedirs(config.output_dir, exist_ok=True)
    out = os.path.join(config.output_dir, "overview_real_vs_pred.png")
    fig.savefig(out, dpi=130)
    plt.close(fig)
    _log.info("Saved: %s", out)


def plot_overview_forecast(
    df: pd.DataFrame, forecast_df: pd.DataFrame, config: GazConfig,
) -> None:
    if forecast_df.empty:
        _log.warning("Forecast empty - skipping overview_forecast.png")
        return

    _apply_style()
    primary = config.value_col
    devices = sorted(df[config.device_col].unique())
    n       = len(devices)

    fig = plt.figure(figsize=(26, max(n * 5.0, 8.0)), facecolor="white")
    fig.suptitle(
        f"ARIA BMS  -  Prevision preventive Gaz  -  {n} devices  |  Horizon : {config.forecast_horizon}h",
        fontsize=14, fontweight="bold", y=0.992,
    )
    top_margin    = 0.975
    bottom_margin = 0.015
    slot_h  = (top_margin - bottom_margin) / n
    inner_h = slot_h - 0.008

    _SEV_COLORS = {"HIGH": _C["HIGH"], "MEDIUM": _C["MEDIUM"], "LOW": _C["LOW"]}

    for idx, device_id in enumerate(devices):
        data = (
            df[df[config.device_col] == device_id]
            .sort_values(config.timestamp_col).reset_index(drop=True).copy()
        )
        data[config.timestamp_col] = pd.to_datetime(data[config.timestamp_col])

        fc = forecast_df[
            (forecast_df[config.device_col] == device_id)
            & (forecast_df["forecast_col"] == primary)
        ].copy()
        if not fc.empty:
            fc[config.timestamp_col] = pd.to_datetime(fc[config.timestamp_col])

        slot_top    = top_margin - idx * slot_h
        slot_bottom = slot_top - inner_h
        gs = gridspec.GridSpec(
            2, 1, height_ratios=[4, 1], hspace=0.06,
            top=slot_top, bottom=slot_bottom, left=0.06, right=0.97, figure=fig,
        )
        ax_main = fig.add_subplot(gs[0])
        ax_conf = fig.add_subplot(gs[1], sharex=ax_main)

        tail = data.tail(min(config.context_length, len(data)))
        ax_main.plot(tail[config.timestamp_col], tail[primary],
                     color=_C["real"], linewidth=1.3, label="Historique", zorder=4)

        n_alerts = 0
        if not fc.empty:
            ax_main.fill_between(
                fc[config.timestamp_col], fc["forecast_low"], fc["forecast_high"],
                alpha=0.35, color=_C["forecast_band"],
                label=f"Intervalle [q{int(config.q_low*100)}-q{int(config.q_high*100)}]",
            )
            ax_main.plot(fc[config.timestamp_col], fc["forecast_median"],
                         color=_C["forecast"], linestyle="--", linewidth=1.8,
                         label="Mediane prevision", zorder=3)
            for sev, col in _SEV_COLORS.items():
                alerts = fc[fc["alert_severity"] == sev]
                if not alerts.empty:
                    ax_main.scatter(
                        alerts[config.timestamp_col], alerts["forecast_median"],
                        color=col, s=55, zorder=5,
                        marker="D" if sev == "HIGH" else "o",
                        edgecolors="white", linewidths=0.5,
                        label=f"Alerte {sev} ({len(alerts)})",
                    )
            ax_main.axvline(tail[config.timestamp_col].iloc[-1],
                            color=_C["zero"], linestyle=":", linewidth=1.1, alpha=0.8,
                            label="Maintenant")
            n_alerts = int(fc["is_alert"].sum())

        ax_main.set_title(
            f"Device {device_id}   -   {n_alerts} alerte(s) / {config.forecast_horizon}h",
            loc="left", fontsize=10, pad=5,
        )
        ax_main.set_ylabel(_label(primary), fontsize=9)
        ax_main.legend(loc="upper left", ncol=3, fontsize=7.5, framealpha=0.95)
        plt.setp(ax_main.get_xticklabels(), visible=False)

        if not fc.empty:
            ax_conf.plot(fc[config.timestamp_col], fc["confidence"],
                         color=_C["forecast"], linewidth=1.4)
            ax_conf.axhline(config.min_confidence, color=_C["HIGH"],
                            linestyle="--", linewidth=0.9, alpha=0.8)
            ax_conf.fill_between(
                fc[config.timestamp_col], fc["confidence"], config.min_confidence,
                where=(fc["confidence"] < config.min_confidence),
                alpha=0.28, color=_C["HIGH"],
            )
            ax_conf.set_ylim(0, 1.05)
        ax_conf.set_ylabel("Confiance", fontsize=7.5, labelpad=2)
        ax_conf.tick_params(axis="y", labelsize=7)
        _fmt_full(ax_conf, data, config.timestamp_col)
        ax_conf.tick_params(axis="x", labelsize=8)

    os.makedirs(config.output_dir, exist_ok=True)
    out = os.path.join(config.output_dir, "overview_forecast.png")
    fig.savefig(out, dpi=130)
    plt.close(fig)
    _log.info("Saved: %s", out)
