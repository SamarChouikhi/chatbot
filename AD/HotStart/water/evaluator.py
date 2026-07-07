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
from .config import WaterConfig

_log = get_logger(__name__)


# ── Design system ─────────────────────────────────────────────────────────────

_C = {
    "real":           "#0277bd",   # bleu azur      — consommation réelle
    "pred_fill":      "#c8e6c9",   # vert très clair — intervalle de confiance prédit
    "pred_low_line":  "#43a047",   # vert moyen      — borne inférieure
    "pred_high_line": "#43a047",   # vert moyen      — borne supérieure
    "pred_median":    "#1b5e20",   # vert foncé      — médiane prédite
    "anom_region":    "#d32f2f",   # rouge           — anomalie ponctuelle (fallback)
    "anom_high":      "#e65100",   # orange-rouge    — anomalie élevée (pic haut ↑)
    "anom_low":       "#0097a7",   # teal            — anomalie faible  (pic bas  ↓)
    "LOW":            "#e53935",
    "MEDIUM":         "#b71c1c",
    "HIGH":           "#7f0000",
    "score_fill":     "#ef9a9a",
    "regime":         "#6a1b9a",   # violet          — changement de régime
    "forecast":       "#4a148c",
    "forecast_band":  "#ce93d8",
    "bg":             "#fafbfc",
    "grid":           "#e3e8ee",
    "zero":           "#78909c",
}

_LABEL = {
    "conso":         "Consommation eau (L/h)",
    "reverse_conso": "Retour eau (L/h)",
    "index":         "Index compteur",
}

_UNIT = {
    "conso":         "L/h",
    "reverse_conso": "L/h",
    "index":         "",
}

_SCORE_BANDS = [("LOW", 0, 2), ("MEDIUM", 2, 5), ("HIGH", 5, 11)]


def _quality(pct_inside: float) -> tuple[str, str, str]:
    if pct_inside >= 90:
        return "Excellent", "#2e7d32", "✓"
    if pct_inside >= 75:
        return "Bon",       "#e65100", "≈"
    return "Faible",        "#b71c1c", "✗"


def _fmt_mae(val: float) -> str:
    if val < 1:   return f"{val:.2f}"
    if val < 100: return f"{val:.1f}"
    return f"{val:.0f}"


def _label(col: str) -> str:
    return _LABEL.get(col, col)


def _severity(score: float) -> str:
    if score >= 5:  return "HIGH"
    if score >= 2:  return "MEDIUM"
    return "LOW"


def _apply_style() -> None:
    for name in ("seaborn-v0_8-whitegrid", "seaborn-whitegrid"):
        try:
            plt.style.use(name)
            break
        except OSError:
            continue
    plt.rcParams.update({
        "font.family":       "DejaVu Sans",
        "font.size":         12,
        "axes.titlesize":    13,
        "axes.titleweight":  "bold",
        "axes.labelsize":    11,
        "axes.facecolor":    _C["bg"],
        "figure.facecolor":  "white",
        "axes.spines.top":   False,
        "axes.spines.right": False,
        "axes.grid":         True,
        "grid.color":        _C["grid"],
        "grid.linewidth":    0.5,
        "legend.framealpha": 0.95,
        "legend.edgecolor":  "#cccccc",
        "legend.fontsize":   10,
        "xtick.labelsize":   10,
        "ytick.labelsize":   10,
    })


def _smart_zoom(data: pd.DataFrame, tcol: str, zoom_n: int) -> pd.DataFrame:
    if not data["is_anomaly"].any():
        return data.tail(zoom_n)
    worst_pos = data.index.get_loc(data["anomaly_score"].idxmax())
    half  = zoom_n // 2
    start = max(0, worst_pos - half)
    end   = min(len(data), start + zoom_n)
    return data.iloc[max(0, end - zoom_n): end]


def _clip_pred_to_signal(
    pred_low:    pd.Series,
    pred_high:   pd.Series,
    pred_median: pd.Series,
    real:        pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Clippe pred_low/high/median à ±3× la plage du signal réel.
    Empêche fill_between de couvrir tout l'axe quand Chronos retourne
    une bande astronomique sur des séries quasi-nulles ou à forte variance.
    """
    clean  = real.dropna()
    if clean.empty:
        return pred_low, pred_high, pred_median
    p01    = float(clean.quantile(0.01))
    p99    = float(clean.quantile(0.99))
    span   = max(abs(p99 - p01), abs(float(clean.max())) * 0.05, 1e-9)
    lo     = p01 - 2.0 * span
    hi     = p99 + 2.0 * span
    return (
        pred_low.clip(lo, hi),
        pred_high.clip(lo, hi),
        pred_median.clip(lo, hi),
    )


def _clip_yaxis(ax: plt.Axes, series: pd.Series, margin: float = 0.12) -> None:
    clean = series.dropna()
    if clean.empty:
        return
    p02 = float(clean.quantile(0.02))
    p98 = float(clean.quantile(0.98))
    sig_max = float(clean.max())
    if sig_max > 3 * (p98 + 1e-9):
        span = max(p98 - p02, 1e-9)
        ax.set_ylim(p02 - margin * span, p98 + margin * span * 2)
    else:
        span = max(sig_max - p02, 1e-9)
        ax.set_ylim(min(p02 - margin * span, -0.05 * span),
                    sig_max + margin * span)


def _status_badge(ax: plt.Axes, n_anom: int, n_point: int, n_regime: int, total: int) -> str:
    rate = n_anom / max(total, 1)
    if n_anom == 0:
        color, label = "#2e7d32", "✓  OK"
    elif rate >= 0.05 or n_point >= 20:
        color, label = "#b71c1c", "✗  ALERTE"
    else:
        color, label = "#e65100", "⚠  ATTENTION"

    ax.text(
        0.003, 0.975, f"  {label}  ",
        transform=ax.transAxes, va="top", ha="left",
        fontsize=12, fontweight="bold", color="white",
        bbox=dict(boxstyle="square,pad=0.45", facecolor=color,
                  edgecolor="none", alpha=0.97),
        zorder=20,
    )
    return label.strip().split()[-1]


def _anomaly_rug(ax: plt.Axes, data: pd.DataFrame, tcol: str) -> None:
    point_col = "is_point_anomaly" if "is_point_anomaly" in data.columns else "is_anomaly"
    has_dir   = "is_high_anomaly" in data.columns and "is_low_anomaly" in data.columns

    if has_dir:
        groups = [
            (data[point_col] & data["is_high_anomaly"],                               _C["anom_high"]),
            (data[point_col] & data["is_low_anomaly"],                                _C["anom_low"]),
            (data[point_col] & ~data["is_high_anomaly"] & ~data["is_low_anomaly"],    _C["anom_region"]),
        ]
        for mask, color in groups:
            sub = data[mask]
            if not sub.empty:
                ax.plot(
                    pd.to_datetime(sub[tcol]), np.full(len(sub), 0.04),
                    marker="|", markersize=14, markeredgewidth=2.0,
                    color=color, linestyle="none",
                    transform=ax.get_xaxis_transform(),
                    alpha=0.92, zorder=9, clip_on=True,
                )
    else:
        sub = data[data[point_col]]
        if not sub.empty:
            ax.plot(
                pd.to_datetime(sub[tcol]), np.full(len(sub), 0.04),
                marker="|", markersize=14, markeredgewidth=2.0,
                color=_C["anom_region"], linestyle="none",
                transform=ax.get_xaxis_transform(),
                alpha=0.92, zorder=9, clip_on=True,
            )


def _draw_summary_panel(
    ax:        plt.Axes,
    data:      pd.DataFrame,
    config:    WaterConfig,
    device_id: str,
) -> None:
    ax.axis("off")
    total    = len(data)
    n_anom   = int(data["is_anomaly"].sum())
    n_point  = int(data["is_point_anomaly"].sum()) if "is_point_anomaly" in data.columns else n_anom
    n_regime = int(data["is_regime_change"].sum()) if "is_regime_change" in data.columns else 0
    worst    = float(data["anomaly_score"].max())
    sev      = _severity(worst) if n_anom > 0 else "OK"
    rate     = n_anom / max(total, 1)

    if n_anom == 0:
        s_color, s_txt = "#2e7d32", "✓\nOK"
    elif rate >= 0.05 or n_point >= 20:
        s_color, s_txt = "#b71c1c", "✗\nALERTE"
    else:
        s_color, s_txt = "#e65100", "⚠\nATTENTION"

    ax.text(
        0.5, 0.88, s_txt,
        ha="center", va="center", transform=ax.transAxes,
        fontsize=20, fontweight="bold", color="white",
        bbox=dict(boxstyle="round,pad=0.7", facecolor=s_color, edgecolor="none"),
        zorder=10,
    )

    metrics = (
        f"Device {device_id}\n"
        f"{'─' * 22}\n"
        f"Anomalies   : {n_point}\n"
        f"  ({rate * 100:.1f} % du temps)\n"
        f"Régime      : {n_regime} h\n"
        f"Pire score  : {worst:.1f}  [{sev}]"
    )

    point_col = "is_point_anomaly" if "is_point_anomaly" in data.columns else "is_anomaly"
    top3 = data[data[point_col]].nlargest(3, "anomaly_score")
    if not top3.empty:
        top_lines = [f"{'─' * 22}", "Top anomalies :"]
        for _, row in top3.iterrows():
            ts  = pd.to_datetime(row[config.timestamp_col]).strftime("%d/%m/%Y  %Hh")
            sv  = _severity(float(row["anomaly_score"]))
            top_lines.append(f"  {ts}")
            top_lines.append(f"  score = {row['anomaly_score']:.1f}  [{sv}]")
        metrics += "\n" + "\n".join(top_lines)

    ax.text(
        0.05, 0.63, metrics,
        ha="left", va="top", transform=ax.transAxes,
        fontsize=9.5, fontfamily="monospace", linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                  edgecolor="#cccccc", linewidth=1.2, alpha=0.97),
    )


def _draw_real_pred_anomalies(
    ax:           plt.Axes,
    data:         pd.DataFrame,
    tcol:         str,
    vcol:         str,
    config:       WaterConfig,
    show_regions: bool = True,
) -> list:
    handles  = []
    tcol_dt  = pd.to_datetime(data[tcol])

    pred = data[data["pred_median"].notna()].copy()
    if not pred.empty:
        pred_t = pd.to_datetime(pred[tcol])
        p_lo, p_hi, p_med = _clip_pred_to_signal(
            pred["pred_low"], pred["pred_high"], pred["pred_median"], data[vcol],
        )
        ax.fill_between(pred_t, p_lo, p_hi,
                        alpha=0.18, color=_C["pred_fill"], zorder=1)
        ax.plot(pred_t, p_lo,
                color=_C["pred_low_line"], linewidth=1.2, alpha=0.85, zorder=2)
        ax.plot(pred_t, p_hi,
                color=_C["pred_high_line"], linewidth=1.2, alpha=0.85, zorder=2)
        ax.plot(pred_t, p_med,
                color=_C["pred_median"], linestyle="--", linewidth=1.4, zorder=3)
        handles.append(mpatches.Patch(
            color=_C["pred_fill"], alpha=0.55,
            label=f"Zone normale prédite [q{int(config.q_low*100)}–q{int(config.q_high*100)}]",
        ))
        handles.append(plt.Line2D(
            [0], [0], color=_C["pred_median"],
            linestyle="--", linewidth=1.6, label="Médiane Chronos",
        ))

    ax.plot(tcol_dt, data[vcol], color=_C["real"], linewidth=1.8, zorder=5)
    _clip_yaxis(ax, data[vcol])
    handles.insert(0, plt.Line2D(
        [0], [0], color=_C["real"],
        linewidth=2.0, label=f"Réel — {_label(vcol)}",
    ))

    if show_regions and "is_regime_change" in data.columns and data["is_regime_change"].any():
        n_rg = int(data["is_regime_change"].sum())
        ax.fill_between(tcol_dt, 0, 1, where=data["is_regime_change"].values,
                        transform=ax.get_xaxis_transform(),
                        alpha=0.09, color=_C["regime"], zorder=1.5)
        handles.append(mpatches.Patch(
            color=_C["regime"], alpha=0.5,
            label=f"Changement de régime ({n_rg}h)",
        ))

    point_col = "is_point_anomaly" if "is_point_anomaly" in data.columns else "is_anomaly"
    if show_regions and data[point_col].any():
        has_dir = "is_high_anomaly" in data.columns and "is_low_anomaly" in data.columns
        if has_dir:
            for col_dir, color, mkr, lbl in (
                ("is_high_anomaly", _C["anom_high"], "^", "Anomalie élevée ↑"),
                ("is_low_anomaly",  _C["anom_low"],  "v", "Anomalie faible ↓"),
            ):
                mask = data[point_col] & data[col_dir]
                if not mask.any():
                    continue
                ax.fill_between(tcol_dt, 0, 1, where=mask.values,
                                transform=ax.get_xaxis_transform(),
                                alpha=0.15, color=color, zorder=2)
                anom_d = data[mask & data[vcol].notna()]
                if not anom_d.empty:
                    ax.scatter(pd.to_datetime(anom_d[tcol]), anom_d[vcol],
                               color=color, s=65, marker=mkr, zorder=7,
                               edgecolors="white", linewidths=0.9)
                    handles.append(mpatches.Patch(color=color, label=f"{lbl} ({len(anom_d)})"))
            other = data[point_col] & ~data["is_high_anomaly"] & ~data["is_low_anomaly"]
            if other.any():
                ax.fill_between(tcol_dt, 0, 1, where=other.values,
                                transform=ax.get_xaxis_transform(),
                                alpha=0.12, color=_C["anom_region"], zorder=2)
        else:
            ax.fill_between(tcol_dt, 0, 1, where=data[point_col].values,
                            transform=ax.get_xaxis_transform(),
                            alpha=0.15, color=_C["anom_region"], zorder=2)
            anom = data[data[point_col] & data[vcol].notna()]
            if not anom.empty:
                ax.scatter(
                    pd.to_datetime(anom[tcol]), anom[vcol],
                    color=_C["anom_region"], s=60, marker="o", zorder=7,
                    edgecolors="white", linewidths=0.9,
                )
                handles.append(mpatches.Patch(
                    color=_C["anom_region"],
                    label=f"Anomalie ({len(anom)})",
                ))

    return handles


def _draw_score_panel(ax: plt.Axes, data: pd.DataFrame, tcol: str) -> None:
    score   = data["anomaly_score"].fillna(0)
    tcol_dt = pd.to_datetime(data[tcol])
    ax.fill_between(tcol_dt, 0, score, where=(score > 0),
                    color=_C["score_fill"], alpha=0.85, zorder=2)
    ax.plot(tcol_dt, score, color=_C["HIGH"], linewidth=0.6, zorder=3)
    ax.axhline(2, color=_C["MEDIUM"], linestyle=":", linewidth=0.9, alpha=0.7)
    ax.axhline(5, color=_C["HIGH"],   linestyle=":", linewidth=0.9, alpha=0.7)
    ax.text(0.001, 2.1, "MEDIUM", transform=ax.get_yaxis_transform(),
            fontsize=6.5, color=_C["MEDIUM"], va="bottom")
    ax.text(0.001, 5.1, "HIGH",   transform=ax.get_yaxis_transform(),
            fontsize=6.5, color=_C["HIGH"],   va="bottom")
    ax.set_ylim(0, max(score.max() * 1.15, 6))
    ax.set_ylabel("Score\nanomal.", fontsize=7.5, labelpad=2)
    ax.tick_params(axis="y", labelsize=7)


def _annotate_worst(ax: plt.Axes, data: pd.DataFrame, tcol: str, vcol: str) -> None:
    point_col  = "is_point_anomaly" if "is_point_anomaly" in data.columns else "is_anomaly"
    # Exclure les lignes où vcol est NaN : ax.annotate avec xy=(t, NaN) produit
    # une FancyArrowPatch à coordonnées infinies → overflow dans bbox_inches="tight"
    point_data = data[data[point_col] & data[vcol].notna()]
    if point_data.empty:
        return
    worst   = point_data.loc[point_data["anomaly_score"].idxmax()]
    sev     = _severity(float(worst["anomaly_score"]))
    ts      = pd.to_datetime(worst[tcol]).strftime("%d/%m %Hh")
    if "is_high_anomaly" in worst.index and bool(worst["is_high_anomaly"]):
        dir_lbl = "↑ élevée"
    elif "is_low_anomaly" in worst.index and bool(worst["is_low_anomaly"]):
        dir_lbl = "↓ faible"
    else:
        dir_lbl = sev
    clean   = data[vcol].dropna()
    v_range = float(clean.max() - clean.min()) if not clean.empty else 1.0
    v_rel   = (float(worst[vcol]) - float(clean.min())) / max(v_range, 1e-9)
    dy      = -65 if v_rel > 0.55 else 65
    ax.annotate(
        f"  {dir_lbl}\n  score={worst['anomaly_score']:.1f}\n  {ts}",
        xy         = (pd.to_datetime(worst[tcol]), worst[vcol]),
        xytext     = (45, dy),
        textcoords = "offset points",
        fontsize=7.5, color=_C[sev], fontweight="bold",
        annotation_clip=False,
        arrowprops=dict(arrowstyle="->", color=_C[sev], lw=1.4,
                        connectionstyle="arc3,rad=0.2"),
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                  edgecolor=_C[sev], alpha=0.97),
        zorder=12,
    )


def _fmt_full(ax: plt.Axes, data: pd.DataFrame, tcol: str) -> None:
    span = (pd.to_datetime(data[tcol].max()) - pd.to_datetime(data[tcol].min())).days
    if span > 365:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    elif span > 180:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    elif span > 60:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    else:
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=8)


def _offline_badge(ax: plt.Axes, pct_offline: float) -> None:
    """Affiche un badge 'Compteur inactif' si le device est quasi-nul (>= 90% zéros)."""
    if pct_offline < 0.90:
        return
    ax.text(
        0.5, 0.50,
        f"Compteur inactif\n{pct_offline*100:.0f}% offline",
        transform=ax.transAxes, ha="center", va="center",
        fontsize=10, fontweight="bold", color="#555555",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f5f5f5",
                  edgecolor="#aaaaaa", linewidth=1.2, alpha=0.92),
        zorder=20,
    )


def _fmt_zoom(ax: plt.Axes, zoom: pd.DataFrame, tcol: str) -> None:
    span = (pd.to_datetime(zoom[tcol].max()) - pd.to_datetime(zoom[tcol].min())).days
    if span >= 7:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    else:
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=12))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m\n%Hh"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=7)


# ── Summary ───────────────────────────────────────────────────────────────────

def anomaly_summary(df: pd.DataFrame, config: WaterConfig) -> pd.DataFrame:
    base = _base_summary(df, item_col=config.item_col, extra_cols=[config.device_col])
    for col in config.value_cols:
        flag_col = f"is_anomaly_{col}"
        if flag_col in df.columns:
            per_col = (df.groupby(config.item_col)[flag_col]
                       .sum().astype(int).rename(f"anomalies_{col}"))
            base = base.merge(per_col, on=config.item_col, how="left")
    return base


# ── Main anomaly plot ─────────────────────────────────────────────────────────

def plot_device(df: pd.DataFrame, device_id: str, config: WaterConfig) -> None:
    _apply_style()
    data = (
        df[df[config.device_col] == device_id]
        .sort_values(config.timestamp_col)
        .reset_index(drop=True)
        .copy()
    )
    if data.empty:
        return

    primary = config.value_col
    data[config.timestamp_col] = pd.to_datetime(data[config.timestamp_col])
    d0   = data[config.timestamp_col].min().strftime("%d/%m/%Y")
    d1   = data[config.timestamp_col].max().strftime("%d/%m/%Y")
    ylbl = _label(primary)

    fig   = plt.figure(figsize=(26, 7), facecolor="white")
    outer = gridspec.GridSpec(1, 2, width_ratios=[3, 1],
                               hspace=0.65, wspace=0.10, figure=fig,
                               top=0.88, bottom=0.09, left=0.06, right=0.97)

    fig.suptitle(
        f"ARIA BMS  —  Anomalies Eau  —  Device {device_id}",
        fontsize=17, fontweight="bold", y=0.97,
    )
    fig.text(
        0.5, 0.92,
        f"Période : {d0}  →  {d1}   |   {_label(primary)}",
        ha="center", va="top", fontsize=11, color="#444444",
    )

    inner = gridspec.GridSpecFromSubplotSpec(
        2, 1, subplot_spec=outer[0, 0],
        height_ratios=[4, 1], hspace=0.08,
    )
    ax_main  = fig.add_subplot(inner[0])
    ax_score = fig.add_subplot(inner[1], sharex=ax_main)

    n_anom   = int(data["is_anomaly"].sum())
    n_point  = int(data["is_point_anomaly"].sum()) if "is_point_anomaly" in data.columns else n_anom
    n_regime = int(data["is_regime_change"].sum()) if "is_regime_change" in data.columns else 0

    handles = _draw_real_pred_anomalies(ax_main, data, config.timestamp_col, primary, config)
    _anomaly_rug(ax_main, data, config.timestamp_col)
    _status_badge(ax_main, n_anom, n_point, n_regime, len(data))
    _annotate_worst(ax_main, data, config.timestamp_col, primary)

    ax_main.set_title(
        f"Device {device_id}   —   {n_point} anomalie(s) ponctuelle(s)   |   {n_regime} h de dérive",
        loc="left", fontsize=12, pad=10,
    )
    ax_main.set_ylabel(ylbl, fontsize=11)
    ax_main.legend(handles=handles, loc="upper right", ncol=2,
                   fontsize=9, framealpha=0.95)
    plt.setp(ax_main.get_xticklabels(), visible=False)

    _draw_score_panel(ax_score, data, config.timestamp_col)
    _fmt_full(ax_score, data, config.timestamp_col)
    ax_score.tick_params(axis="x", labelsize=9)

    ax_zoom = fig.add_subplot(outer[0, 1])
    zoom    = _smart_zoom(data, config.timestamp_col, config.zoom_hours)
    z_pred  = zoom[zoom["pred_median"].notna()]

    ax_zoom.plot(pd.to_datetime(zoom[config.timestamp_col]), zoom[primary],
                 color=_C["real"], linewidth=1.4, label=ylbl, zorder=4)
    if not z_pred.empty:
        zt = pd.to_datetime(z_pred[config.timestamp_col])
        ax_zoom.fill_between(zt, z_pred["pred_low"], z_pred["pred_high"],
                             alpha=0.22, color=_C["pred_fill"], zorder=1)
        ax_zoom.plot(zt, z_pred["pred_low"],
                     color=_C["pred_low_line"], linewidth=0.8, alpha=0.9, zorder=2)
        ax_zoom.plot(zt, z_pred["pred_high"],
                     color=_C["pred_high_line"], linewidth=0.8, alpha=0.9, zorder=2)
        ax_zoom.plot(zt, z_pred["pred_median"],
                     color=_C["pred_median"], linestyle="--", linewidth=2.0,
                     label="Médiane prédite", zorder=3)

    if zoom["is_anomaly"].any():
        has_dir_z = "is_high_anomaly" in zoom.columns and "is_low_anomaly" in zoom.columns
        if has_dir_z:
            for col_dir, color, mkr in (
                ("is_high_anomaly", _C["anom_high"], "^"),
                ("is_low_anomaly",  _C["anom_low"],  "v"),
            ):
                z_mask = zoom["is_anomaly"] & zoom[col_dir]
                if z_mask.any():
                    ax_zoom.fill_between(pd.to_datetime(zoom[config.timestamp_col]), 0, 1,
                                         where=z_mask.values,
                                         transform=ax_zoom.get_xaxis_transform(),
                                         alpha=0.20, color=color, zorder=0)
                    zd = zoom[z_mask & zoom[primary].notna()]
                    if not zd.empty:
                        ax_zoom.scatter(pd.to_datetime(zd[config.timestamp_col]), zd[primary],
                                        color=color, s=80, zorder=6,
                                        marker=mkr, edgecolors="white", linewidths=0.8)
            other_z = zoom["is_anomaly"] & ~zoom["is_high_anomaly"] & ~zoom["is_low_anomaly"]
            if other_z.any():
                ax_zoom.fill_between(pd.to_datetime(zoom[config.timestamp_col]), 0, 1,
                                     where=other_z.values,
                                     transform=ax_zoom.get_xaxis_transform(),
                                     alpha=0.20, color=_C["anom_region"], zorder=0)
        else:
            z_anom = zoom[zoom["is_anomaly"] & zoom[primary].notna()]
            ax_zoom.fill_between(pd.to_datetime(zoom[config.timestamp_col]), 0, 1,
                                 where=zoom["is_anomaly"].values,
                                 transform=ax_zoom.get_xaxis_transform(),
                                 alpha=0.20, color=_C["anom_region"], zorder=0)
            ax_zoom.scatter(pd.to_datetime(z_anom[config.timestamp_col]), z_anom[primary],
                            color=_C["anom_region"], s=80, zorder=6,
                            marker="o", edgecolors="white", linewidths=0.8)

    zoom_d0 = pd.to_datetime(zoom[config.timestamp_col].min()).strftime("%d/%m")
    zoom_d1 = pd.to_datetime(zoom[config.timestamp_col].max()).strftime("%d/%m")
    suffix  = "pire anomalie" if data["is_anomaly"].any() else "récent"
    ax_zoom.set_title(f"Zoom {suffix}  [{zoom_d0} → {zoom_d1}]", loc="left", fontsize=9)
    ax_zoom.yaxis.set_label_position("right")
    ax_zoom.yaxis.tick_right()
    ax_zoom.legend(fontsize=7, loc="upper left")
    _fmt_zoom(ax_zoom, zoom, config.timestamp_col)

    os.makedirs(config.output_dir, exist_ok=True)
    out = os.path.join(config.output_dir, f"anomaly_{device_id}.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    _log.info("Plot saved: %s", out)


def plot_device_features(df: pd.DataFrame, device_id: str, config: WaterConfig) -> None:
    if len(config.value_cols) < 2:
        return

    _apply_style()
    data = (
        df[df[config.device_col] == device_id]
        .sort_values(config.timestamp_col)
        .reset_index(drop=True)
        .copy()
    )
    data[config.timestamp_col] = pd.to_datetime(data[config.timestamp_col])
    d0 = data[config.timestamp_col].min().strftime("%d/%m/%Y")
    d1 = data[config.timestamp_col].max().strftime("%d/%m/%Y")

    n_cols = len(config.value_cols)
    fig = plt.figure(figsize=(24, 4 * n_cols), facecolor="white")
    fig.suptitle(
        f"Détail par feature  —  Device {device_id}  |  {d0} → {d1}",
        fontsize=11, fontweight="bold",
    )

    outer = gridspec.GridSpec(n_cols, 1, hspace=0.55, figure=fig,
                               top=0.93, bottom=0.05, left=0.07, right=0.97)

    for j, col in enumerate(config.value_cols):
        flag_col = f"is_anomaly_{col}"
        pred_col = f"pred_median_{col}"
        low_col  = f"pred_low_{col}"
        high_col = f"pred_high_{col}"

        plot_data = data.copy()
        if pred_col in data.columns:
            plot_data["pred_median"] = data[pred_col]
            plot_data["pred_low"]    = data[low_col]
            plot_data["pred_high"]   = data[high_col]
        else:
            for c in ("pred_median", "pred_low", "pred_high"):
                plot_data[c] = np.nan

        if flag_col in data.columns:
            plot_data["is_anomaly"]    = data[flag_col]
            plot_data["anomaly_score"] = data[f"anomaly_score_{col}"]
        else:
            plot_data["is_anomaly"]    = False
            plot_data["anomaly_score"] = 0.0

        n_anom_col = int(data[flag_col].sum()) if flag_col in data.columns else 0
        pct_col    = n_anom_col / len(data) * 100 if len(data) > 0 else 0

        inner = gridspec.GridSpecFromSubplotSpec(
            2, 1, subplot_spec=outer[j],
            height_ratios=[4, 1], hspace=0.08,
        )
        ax_main  = fig.add_subplot(inner[0])
        ax_score = fig.add_subplot(inner[1], sharex=ax_main)

        handles = _draw_real_pred_anomalies(
            ax_main, plot_data, config.timestamp_col, col, config,
        )
        ax_main.set_title(
            f"{_label(col)}  —  {n_anom_col} anomalies ({pct_col:.1f}%)",
            loc="left", fontsize=9,
        )
        ax_main.set_ylabel(_label(col), fontsize=8)
        ax_main.legend(handles=handles, fontsize=7, loc="upper left", ncol=3)
        plt.setp(ax_main.get_xticklabels(), visible=False)

        _draw_score_panel(ax_score, plot_data, config.timestamp_col)
        _fmt_full(ax_score, data, config.timestamp_col)

    os.makedirs(config.output_dir, exist_ok=True)
    out = os.path.join(config.output_dir, f"anomaly_{device_id}_features.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    _log.info("Feature plot saved: %s", out)


def plot_all_devices(df: pd.DataFrame, config: WaterConfig) -> None:
    for device_id in sorted(df[config.device_col].unique()):
        plot_device(df, device_id, config)
        plot_device_features(df, device_id, config)


# ── Forecasting ───────────────────────────────────────────────────────────────

_SEVERITY_COLORS = {"HIGH": _C["HIGH"], "MEDIUM": _C["MEDIUM"], "LOW": _C["LOW"]}


def forecast_summary(forecast_df: pd.DataFrame, config: WaterConfig) -> pd.DataFrame:
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


def plot_forecast_device(
    df:          pd.DataFrame,
    forecast_df: pd.DataFrame,
    device_id:   str,
    config:      WaterConfig,
) -> None:
    _apply_style()
    if forecast_df.empty:
        return
    primary = config.value_col
    data = df[df[config.device_col] == device_id].sort_values(config.timestamp_col).copy()
    if data.empty:
        return

    fc = forecast_df[
        (forecast_df[config.device_col] == device_id)
        & (forecast_df["forecast_col"] == primary)
    ].copy()
    data[config.timestamp_col] = pd.to_datetime(data[config.timestamp_col])
    if not fc.empty:
        fc[config.timestamp_col] = pd.to_datetime(fc[config.timestamp_col])

    fig = plt.figure(figsize=(26, 5), facecolor="white")
    gs  = gridspec.GridSpec(1, 2, width_ratios=[3, 1], hspace=0.55, wspace=0.10, figure=fig,
                            top=0.87, bottom=0.12, left=0.06, right=0.97)
    fig.suptitle(
        f"Prévision préventive  —  Device {device_id}\n"
        f"Horizon : {config.forecast_horizon}h  |  {_label(primary)}",
        fontsize=11, fontweight="bold", y=0.97,
    )

    ax_l  = fig.add_subplot(gs[0, 0])
    tail  = data.tail(config.context_length)
    ax_l.plot(tail[config.timestamp_col], tail[primary],
              color=_C["real"], linewidth=1.3, label="Historique", zorder=4)

    if not fc.empty:
        ax_l.fill_between(fc[config.timestamp_col],
                          fc["forecast_low"], fc["forecast_high"],
                          alpha=0.38, color=_C["forecast_band"],
                          label=f"Intervalle [q{int(config.q_low*100)}–q{int(config.q_high*100)}]")
        ax_l.plot(fc[config.timestamp_col], fc["forecast_median"],
                  color=_C["forecast"], linestyle="--", linewidth=2.0,
                  label="Médiane prévision", zorder=3)
        for sev, col in _SEVERITY_COLORS.items():
            alerts = fc[fc["alert_severity"] == sev]
            if not alerts.empty:
                ax_l.scatter(alerts[config.timestamp_col], alerts["forecast_median"],
                             color=col, s=80, zorder=5,
                             marker="D" if sev == "HIGH" else "o",
                             edgecolors="white", linewidths=0.6,
                             label=f"Alerte {sev} ({len(alerts)})")
        ax_l.axvline(tail[config.timestamp_col].iloc[-1],
                     color=_C["zero"], linestyle=":", linewidth=1.2, label="Maintenant")

    ax_l.set_title(f"Device {device_id}  —  Historique + Prévision {config.forecast_horizon}h",
                   loc="left")
    ax_l.set_ylabel(_label(primary), fontsize=9)
    ax_l.legend(ncol=2, fontsize=7.5, loc="upper left")
    _fmt_zoom(ax_l, data.tail(config.context_length + config.forecast_horizon),
              config.timestamp_col)

    ax_r = fig.add_subplot(gs[0, 1])
    if not fc.empty:
        ax_r.plot(fc[config.timestamp_col], fc["confidence"],
                  color=_C["forecast"], linewidth=1.6)
        ax_r.axhline(config.min_confidence, color=_C["HIGH"],
                     linestyle="--", linewidth=1.1,
                     label=f"Seuil min ({config.min_confidence})")
        ax_r.fill_between(fc[config.timestamp_col],
                          fc["confidence"], config.min_confidence,
                          where=(fc["confidence"] < config.min_confidence),
                          alpha=0.30, color=_C["HIGH"])
        ax_r.set_ylim(0, 1.05)
    ax_r.set_title("Score de confiance", loc="left")
    ax_r.yaxis.set_label_position("right")
    ax_r.yaxis.tick_right()
    ax_r.legend(fontsize=7.5, loc="lower left")
    _fmt_zoom(ax_r, fc if not fc.empty else data.tail(10), config.timestamp_col)

    os.makedirs(config.output_dir, exist_ok=True)
    out = os.path.join(config.output_dir, f"forecast_{device_id}.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    _log.info("Forecast plot saved: %s", out)


def plot_all_forecasts(
    df:          pd.DataFrame,
    forecast_df: pd.DataFrame,
    config:      WaterConfig,
) -> None:
    for device_id in sorted(df[config.device_col].unique()):
        plot_forecast_device(df, forecast_df, device_id, config)


# ── Combined view ─────────────────────────────────────────────────────────────

def plot_combined_device(df: pd.DataFrame, device_id: str, config: WaterConfig) -> None:
    _apply_style()
    primary = config.value_col
    data = (
        df[df[config.device_col] == device_id]
        .sort_values(config.timestamp_col)
        .reset_index(drop=True)
        .copy()
    )
    if data.empty:
        return

    data[config.timestamp_col] = pd.to_datetime(data[config.timestamp_col])
    d0 = data[config.timestamp_col].min().strftime("%d/%m/%Y")
    d1 = data[config.timestamp_col].max().strftime("%d/%m/%Y")

    n_anom   = int(data["is_anomaly"].sum())
    n_point  = int(data["is_point_anomaly"].sum()) if "is_point_anomaly" in data.columns else n_anom
    n_regime = int(data["is_regime_change"].sum()) if "is_regime_change" in data.columns else 0

    fig   = plt.figure(figsize=(26, 7), facecolor="white")
    outer = gridspec.GridSpec(1, 2, width_ratios=[4, 1],
                               hspace=0.65, wspace=0.08, figure=fig,
                               top=0.88, bottom=0.09, left=0.06, right=0.97)

    fig.suptitle(f"Device {device_id}  —  Eau", fontsize=17, fontweight="bold", y=0.97)
    fig.text(
        0.5, 0.92,
        f"Période : {d0}  →  {d1}   |   {_label(primary)}",
        ha="center", va="top", fontsize=11, color="#444444",
    )

    inner = gridspec.GridSpecFromSubplotSpec(
        2, 1, subplot_spec=outer[0, 0],
        height_ratios=[4, 1], hspace=0.08,
    )
    ax_main  = fig.add_subplot(inner[0])
    ax_score = fig.add_subplot(inner[1], sharex=ax_main)

    handles = _draw_real_pred_anomalies(ax_main, data, config.timestamp_col, primary, config)
    _anomaly_rug(ax_main, data, config.timestamp_col)
    _status_badge(ax_main, n_anom, n_point, n_regime, len(data))
    _annotate_worst(ax_main, data, config.timestamp_col, primary)

    ax_main.set_title(
        f"Device {device_id}   —   {n_point} anomalie(s) ponctuelle(s)   |   {n_regime} h de dérive",
        loc="left", fontsize=12, pad=10,
    )
    ax_main.set_ylabel(_label(primary), fontsize=11)
    ax_main.legend(handles=handles, loc="upper right", ncol=2, fontsize=9)
    plt.setp(ax_main.get_xticklabels(), visible=False)

    _draw_score_panel(ax_score, data, config.timestamp_col)
    _fmt_full(ax_score, data, config.timestamp_col)
    ax_score.tick_params(axis="x", labelsize=9)

    ax_summary = fig.add_subplot(outer[0, 1])
    _draw_summary_panel(ax_summary, data, config, device_id)

    os.makedirs(config.output_dir, exist_ok=True)
    out = os.path.join(config.output_dir, f"combined_{device_id}.png")
    fig.savefig(out, dpi=160)
    plt.close(fig)
    _log.info("Combined plot saved: %s", out)


def plot_all_combined(df: pd.DataFrame, config: WaterConfig) -> None:
    for device_id in sorted(df[config.device_col].unique()):
        plot_combined_device(df, device_id, config)


# ── Real vs Prediction ────────────────────────────────────────────────────────

def plot_real_vs_pred_device(df: pd.DataFrame, device_id: str, config: WaterConfig) -> None:
    _apply_style()
    primary = config.value_col
    data = (
        df[df[config.device_col] == device_id]
        .sort_values(config.timestamp_col)
        .reset_index(drop=True)
        .copy()
    )
    if data.empty:
        return

    data[config.timestamp_col] = pd.to_datetime(data[config.timestamp_col])
    d0 = data[config.timestamp_col].min().strftime("%d/%m/%Y")
    d1 = data[config.timestamp_col].max().strftime("%d/%m/%Y")

    fig   = plt.figure(figsize=(22, 5), facecolor="white")
    outer = gridspec.GridSpec(1, 2, width_ratios=[4, 1], hspace=0.55, wspace=0.10, figure=fig,
                               top=0.87, bottom=0.12, left=0.06, right=0.97)
    fig.suptitle(
        f"Réel vs Prédiction Chronos  —  Device {device_id}  (Eau)",
        fontsize=15, fontweight="bold", y=0.97,
    )
    fig.text(0.5, 0.92, f"Période : {d0}  →  {d1}   |   {_label(primary)}",
             ha="center", va="top", fontsize=10, color="#555555")

    ax      = fig.add_subplot(outer[0, 0])
    ax_info = fig.add_subplot(outer[0, 1])
    ax_info.axis("off")

    t    = data[config.timestamp_col]
    real = data[primary]
    pred = data[data["pred_median"].notna()]

    _PRED_LINE = "#f57c00"
    handles    = []

    if not pred.empty:
        pt = pd.to_datetime(pred[config.timestamp_col])
        ax.fill_between(pt, pred["pred_low"], pred["pred_high"],
                        alpha=0.10, color=_PRED_LINE, zorder=1)

    point_col = "is_point_anomaly" if "is_point_anomaly" in data.columns else "is_anomaly"
    n_out     = int(data[point_col].sum())
    if n_out > 0:
        ax.fill_between(t, 0, 1, where=data[point_col].values,
                        transform=ax.get_xaxis_transform(),
                        alpha=0.12, color=_C["anom_region"], zorder=1.5)
        handles.append(mpatches.Patch(
            color=_C["anom_region"], alpha=0.5,
            label=f"Hors bande — {n_out} point(s)",
        ))

    if not pred.empty:
        ax.plot(pt, pred["pred_median"],
                color=_PRED_LINE, linewidth=1.8, zorder=4)
        handles.append(plt.Line2D(
            [0], [0], color=_PRED_LINE, linewidth=2.0,
            label="Prédiction Chronos",
        ))

    ax.plot(t, real, color=_C["real"], linewidth=1.8, zorder=5)
    _clip_yaxis(ax, real)
    handles.insert(0, plt.Line2D(
        [0], [0], color=_C["real"], linewidth=2.0,
        label=f"Réel — {_label(primary)}",
    ))

    ax.set_title(f"Device {device_id}  —  {_label(primary)}", loc="left", fontsize=11)
    ax.set_ylabel(_label(primary), fontsize=10)
    ax.legend(handles=handles, loc="upper left", ncol=3, fontsize=9, framealpha=0.95)
    _fmt_full(ax, data, config.timestamp_col)

    if not pred.empty:
        merged  = pred.copy()
        inside  = (merged[primary] >= merged["pred_low"]) & (merged[primary] <= merged["pred_high"])
        pct_cov = inside.mean() * 100
        normal  = merged[~merged[point_col] & (merged[primary] > 0)]
        mae_abs = float((normal[primary] - normal["pred_median"]).abs().mean()) \
                  if len(normal) >= 2 else 0.0
        unit    = _UNIT.get(primary, "")

        q_label, q_color, q_sym = _quality(pct_cov)
        ax_info.text(
            0.5, 0.88, f"{q_sym}\n{q_label}",
            ha="center", va="center", transform=ax_info.transAxes,
            fontsize=20, fontweight="bold", color="white",
            bbox=dict(boxstyle="round,pad=0.7", facecolor=q_color, edgecolor="none"),
        )
        metrics = (
            f"Device {device_id}\n"
            f"{'─' * 22}\n"
            f"Couverture    {pct_cov:.1f} %\n"
            f"Erreur moy.   {_fmt_mae(mae_abs)} {unit}\n"
            f"{'─' * 22}\n"
            f"Prédictions   {len(merged):,}\n"
            f"Hors bande    {n_out:,}"
        ).strip()
        ax_info.text(
            0.05, 0.63, metrics,
            ha="left", va="top", transform=ax_info.transAxes,
            fontsize=9, fontfamily="monospace", linespacing=1.5,
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor=q_color, linewidth=1.5, alpha=0.97),
        )
    else:
        ax_info.text(
            0.5, 0.6, f"Device {device_id}\n{'─' * 18}\nPas de\nprédiction",
            ha="center", va="center", transform=ax_info.transAxes,
            fontsize=10, fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="#aaaaaa", linewidth=1.5),
        )

    os.makedirs(config.output_dir, exist_ok=True)
    out = os.path.join(config.output_dir, f"real_vs_pred_{device_id}.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    _log.info("Real-vs-pred plot saved: %s", out)


def plot_all_real_vs_pred(df: pd.DataFrame, config: WaterConfig) -> None:
    for device_id in sorted(df[config.device_col].unique()):
        plot_real_vs_pred_device(df, device_id, config)


# ── Helpers partagés pour les overviews ──────────────────────────────────────

def _overview_slots(n: int) -> tuple[float, float, float]:
    """Retourne (top_margin, slot_h, inner_h) pour N devices empilés."""
    top_margin = 0.975
    bottom_margin = 0.015
    slot_h  = (top_margin - bottom_margin) / n
    inner_h = slot_h - 0.008
    return top_margin, slot_h, inner_h


def _overview_fig(title: str, n: int, row_h: float = 5.5) -> plt.Figure:
    fig = plt.figure(figsize=(26, max(n * row_h, 8.0)), facecolor="white")
    fig.suptitle(title, fontsize=14, fontweight="bold", y=0.992)
    return fig


def _slot_gs(fig: plt.Figure, slot_top: float, slot_bottom: float,
             n_rows: int, height_ratios: list[int], hspace: float = 0.06,
             ) -> gridspec.GridSpec:
    return gridspec.GridSpec(
        n_rows, 1, height_ratios=height_ratios, hspace=hspace,
        top=slot_top, bottom=slot_bottom, left=0.06, right=0.97, figure=fig,
    )


# ── 1 — Détection d'anomalies (signal + Chronos + score) ─────────────────────

def plot_overview_anomaly(df: pd.DataFrame, config: WaterConfig) -> None:
    """Tous les devices — détection d'anomalies empilés en un seul fichier."""
    _apply_style()
    primary = config.value_col
    devices = sorted(df[config.device_col].unique())
    n       = len(devices)

    t_min = pd.to_datetime(df[config.timestamp_col].min()).strftime("%d/%m/%Y")
    t_max = pd.to_datetime(df[config.timestamp_col].max()).strftime("%d/%m/%Y")
    fig = _overview_fig(
        f"ARIA BMS  —  Détection d'anomalies  —  {n} devices  |  {t_min} → {t_max}",
        n, row_h=5.5,
    )
    top_margin, slot_h, inner_h = _overview_slots(n)

    for idx, device_id in enumerate(devices):
        data = (
            df[df[config.device_col] == device_id]
            .sort_values(config.timestamp_col).reset_index(drop=True).copy()
        )
        data[config.timestamp_col] = pd.to_datetime(data[config.timestamp_col])

        slot_top    = top_margin - idx * slot_h
        slot_bottom = slot_top - inner_h
        gs = _slot_gs(fig, slot_top, slot_bottom, 2, [4, 1])
        ax_main  = fig.add_subplot(gs[0])
        ax_score = fig.add_subplot(gs[1], sharex=ax_main)

        n_anom   = int(data["is_anomaly"].sum())
        n_point  = int(data["is_point_anomaly"].sum()) if "is_point_anomaly" in data.columns else n_anom
        n_regime = int(data["is_regime_change"].sum()) if "is_regime_change" in data.columns else 0

        pct_offline = float((data[primary] == 0).mean())
        handles = _draw_real_pred_anomalies(ax_main, data, config.timestamp_col, primary, config)
        _anomaly_rug(ax_main, data, config.timestamp_col)
        _status_badge(ax_main, n_anom, n_point, n_regime, len(data))
        _annotate_worst(ax_main, data, config.timestamp_col, primary)
        _offline_badge(ax_main, pct_offline)

        ax_main.set_title(
            f"Device {device_id}   —   {n_point} anomalie(s) ponctuelle(s)   |   {n_regime} h de dérive",
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


# ── 2 — Réel vs Prédiction Chronos ───────────────────────────────────────────

def plot_overview_real_vs_pred(df: pd.DataFrame, config: WaterConfig) -> None:
    """Tous les devices — réel vs prédiction Chronos en un seul fichier."""
    _apply_style()
    primary = config.value_col
    devices = sorted(df[config.device_col].unique())
    n       = len(devices)

    t_min = pd.to_datetime(df[config.timestamp_col].min()).strftime("%d/%m/%Y")
    t_max = pd.to_datetime(df[config.timestamp_col].max()).strftime("%d/%m/%Y")
    fig = _overview_fig(
        f"ARIA BMS  —  Réel vs Prédiction Chronos  —  {n} devices  |  {t_min} → {t_max}",
        n, row_h=4.0,
    )
    top_margin, slot_h, inner_h = _overview_slots(n)

    for idx, device_id in enumerate(devices):
        data = (
            df[df[config.device_col] == device_id]
            .sort_values(config.timestamp_col).reset_index(drop=True).copy()
        )
        data[config.timestamp_col] = pd.to_datetime(data[config.timestamp_col])

        slot_top    = top_margin - idx * slot_h
        slot_bottom = slot_top - inner_h
        gs = _slot_gs(fig, slot_top, slot_bottom, 1, [1])
        ax = fig.add_subplot(gs[0])

        t    = data[config.timestamp_col]
        real = data[primary]
        pred = data[data["pred_median"].notna()]

        if not pred.empty:
            pt  = pd.to_datetime(pred[config.timestamp_col])
            p_lo, p_hi, p_med = _clip_pred_to_signal(
                pred["pred_low"], pred["pred_high"], pred["pred_median"], real,
            )
            ax.fill_between(pt, p_lo, p_hi,
                            alpha=0.20, color=_C["pred_fill"], zorder=1)
            ax.plot(pt, p_med,
                    color=_C["pred_median"], linestyle="--",
                    linewidth=1.4, zorder=3, label="Médiane Chronos")

        point_col = "is_point_anomaly" if "is_point_anomaly" in data.columns else "is_anomaly"
        n_out = int(data[point_col].sum())
        if n_out > 0:
            ax.fill_between(t, 0, 1, where=data[point_col].values,
                            transform=ax.get_xaxis_transform(),
                            alpha=0.13, color=_C["anom_region"], zorder=1.5,
                            label=f"Hors bande ({n_out})")

        ax.plot(t, real, color=_C["real"], linewidth=1.3, zorder=5,
                label=f"Réel — {_label(primary)}")
        _clip_yaxis(ax, real)

        pct_offline = float((real == 0).mean())
        _offline_badge(ax, pct_offline)

        cov_txt = "—"
        if not pred.empty:
            inside  = (pred[primary] >= pred["pred_low"]) & (pred[primary] <= pred["pred_high"])
            cov_txt = f"Couverture : {inside.mean() * 100:.1f} %"

        ax.set_title(
            f"Device {device_id}   —   {cov_txt}   |   {n_out} point(s) hors bande",
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


# ── 3 — Prévision préventive + score de confiance ────────────────────────────

def plot_overview_forecast(
    df:          pd.DataFrame,
    forecast_df: pd.DataFrame,
    config:      WaterConfig,
) -> None:
    """Tous les devices — prévision préventive + confiance en un seul fichier."""
    if forecast_df.empty:
        _log.warning("Forecast empty — skipping overview_forecast.png")
        return

    _apply_style()
    primary = config.value_col
    devices = sorted(df[config.device_col].unique())
    n       = len(devices)

    fig = _overview_fig(
        f"ARIA BMS  —  Prévision préventive  —  {n} devices  |  Horizon : {config.forecast_horizon}h",
        n, row_h=5.0,
    )
    top_margin, slot_h, inner_h = _overview_slots(n)

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
        gs = _slot_gs(fig, slot_top, slot_bottom, 2, [4, 1])
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
                label=f"Intervalle [q{int(config.q_low*100)}–q{int(config.q_high*100)}]",
            )
            ax_main.plot(fc[config.timestamp_col], fc["forecast_median"],
                         color=_C["forecast"], linestyle="--", linewidth=1.8,
                         label="Médiane prévision", zorder=3)
            for sev, col in _SEVERITY_COLORS.items():
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
            f"Device {device_id}   —   {n_alerts} alerte(s) / {config.forecast_horizon}h",
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
