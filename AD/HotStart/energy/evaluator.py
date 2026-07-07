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
from .config import EnergyConfig

_log = get_logger(__name__)


# ── Design system ─────────────────────────────────────────────────────────────

_C = {
    # ── Signal réel ───────────────────────────────────────────────────────────
    "real":          "#1565c0",   # bleu foncé       — consommation réelle
    # ── Prédiction Chronos (vert = zone normale attendue) ─────────────────────
    # Vert est totalement distinct du bleu (réel) et du rouge (anomalie).
    # Sémantique trafic : vert = normal, rouge = alerte.
    "pred_fill":     "#a5d6a7",   # vert clair        — intervalle de confiance prédit
    "pred_low_line": "#388e3c",   # vert moyen        — borne inférieure prédite
    "pred_high_line":"#388e3c",   # vert moyen        — borne supérieure prédite
    "pred_median":   "#1b5e20",   # vert très foncé   — médiane prédite (tirets)
    # ── Anomalies (rouge = alerte) ────────────────────────────────────────────
    "anom_region":   "#d32f2f",   # rouge             — fond anomalie ponctuelle (fallback)
    "anom_high":     "#e65100",   # orange-rouge      — anomalie élevée (pic haut ↑)
    "anom_low":      "#0097a7",   # teal              — anomalie faible  (pic bas  ↓)
    "LOW":           "#e53935",   # rouge clair       — sévérité faible
    "MEDIUM":        "#b71c1c",   # rouge foncé       — sévérité moyenne
    "HIGH":          "#7f0000",   # rouge très foncé  — sévérité haute (diamant)
    "score_fill":    "#ef9a9a",   # rose léger        — aire score anomalie
    # ── Changement de régime (violet = dérive pattern) ────────────────────────
    "regime":        "#6a1b9a",   # violet            — changement de pattern
    # ── Prévision préventive (violet foncé) ───────────────────────────────────
    "forecast":      "#4a148c",
    "forecast_band": "#ce93d8",
    # ── UI ────────────────────────────────────────────────────────────────────
    "bg":            "#fafbfc",
    "grid":          "#e3e8ee",
    "zero":          "#78909c",   # bleu-gris         — ligne de base / maintenant
}

# Traduction des noms de colonnes techniques en libellés lisibles pour les graphiques
# Ces labels s'affichent sur les axes Y — l'opérateur voit "Courant RMS (A)" et non "moy_rms_current"
_LABEL = {
    "cons_en":          "Consommation énergie (Wh)",
    "moy_rms_current":  "Courant RMS (A)",
    "moy_active_power": "Puissance active (W)",
    "moy_THD":          "THD (%)",
    "moy_rms_voltage":  "Tension RMS (V)",
    "moy_cosfi":        "Cos φ",
    "cons_en_reactive": "Énergie réactive (VARh)",
    "cons_en_apparent": "Énergie apparente (VAh)",
}

_SCORE_BANDS = [("LOW", 0, 2), ("MEDIUM", 2, 5), ("HIGH", 5, 11)]

_UNIT = {
    "cons_en":          "Wh",
    "moy_rms_current":  "A",
    "moy_active_power": "W",
    "moy_THD":          "%",
    "moy_rms_voltage":  "V",
    "moy_cosfi":        "",
    "cons_en_reactive": "VARh",
    "cons_en_apparent": "VAh",
}


def _quality(pct_inside: float) -> tuple[str, str, str]:
    """(label, hex_color, symbol) based on band coverage."""
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _smart_zoom(data: pd.DataFrame, tcol: str, zoom_n: int) -> pd.DataFrame:
    # Si pas d'anomalie → on zoome sur les dernières heures (données les plus récentes)
    # Sinon → on centre le zoom sur la pire anomalie pour que l'opérateur la voit immédiatement
    if not data["is_anomaly"].any():
        return data.tail(zoom_n)
    worst_pos = data.index.get_loc(data["anomaly_score"].idxmax())
    half  = zoom_n // 2
    start = max(0, worst_pos - half)
    end   = min(len(data), start + zoom_n)
    return data.iloc[max(0, end - zoom_n): end]


def _clip_yaxis(ax: plt.Axes, series: pd.Series, margin: float = 0.12) -> None:
    """
    Clip l'axe Y au 98e percentile pour éviter qu'un spike isolé écrase
    toute la dynamique du signal (cas device inactif longtemps + burst soudain).
    Un margin de 12% est ajouté en haut et en bas.
    Si le max absolu ≤ 2× p98, on laisse matplotlib décider (pas de spike extrême).
    """
    clean = series.dropna()
    if clean.empty:
        return
    p02 = float(clean.quantile(0.02))
    p98 = float(clean.quantile(0.98))
    sig_max = float(clean.max())

    # Spike extrême : max > 3× p98 → on clip à p98 + margin
    if sig_max > 3 * (p98 + 1e-9):
        span = max(p98 - p02, 1e-9)
        ax.set_ylim(p02 - margin * span, p98 + margin * span * 2)
    # Sinon on laisse matplotlib autoscaler (signal "normal")
    else:
        span = max(sig_max - p02, 1e-9)
        ax.set_ylim(min(p02 - margin * span, -0.05 * span),
                    sig_max + margin * span)


def _status_badge(
    ax: plt.Axes,
    n_anom: int,
    n_point: int,
    n_regime: int,
    total: int,
) -> str:
    """
    Badge coloré affiché en haut-gauche du graphique — c'est la première chose que l'opérateur voit.
    Seuils choisis pour refléter la gravité opérationnelle :
      - ALERTE si ≥ 5% du temps est anomalique OU 20+ anomalies ponctuelles (problème systémique)
      - ATTENTION si moins grave mais quand même anormal
      - OK si aucune anomalie détectée
    """
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
    ax:     plt.Axes,
    data:   pd.DataFrame,
    config: EnergyConfig,
    phase:  str,
) -> None:
    """
    Panel résumé opérateur : statut, métriques clés, top 3 pires anomalies.
    Remplace le panneau forecast dans la vue combinée — lisible d'un coup d'œil.
    """
    ax.axis("off")
    total    = len(data)
    n_anom   = int(data["is_anomaly"].sum())
    n_point  = int(data["is_point_anomaly"].sum()) if "is_point_anomaly" in data.columns else n_anom
    n_regime = int(data["is_regime_change"].sum()) if "is_regime_change" in data.columns else 0
    worst    = float(data["anomaly_score"].max())
    sev      = _severity(worst) if n_anom > 0 else "OK"
    rate     = n_anom / max(total, 1)

    # ── Badge statut (grand, centré en haut) ─────────────────────────────────
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

    # ── Métriques ─────────────────────────────────────────────────────────────
    metrics = (
        f"Phase {phase}\n"
        f"{'─' * 22}\n"
        f"Anomalies   : {n_point}\n"
        f"  ({rate * 100:.1f} % du temps)\n"
        f"Régime      : {n_regime} h\n"
        f"Pire score  : {worst:.1f}  [{sev}]"
    )

    # ── Top 3 pires anomalies ─────────────────────────────────────────────────
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


def _stats_box(ax: plt.Axes, data: pd.DataFrame, config: EnergyConfig) -> None:
    total    = len(data)
    n_anom   = int(data["is_anomaly"].sum())
    n_point  = int(data["is_point_anomaly"].sum()) if "is_point_anomaly" in data.columns else n_anom
    n_regime = int(data["is_regime_change"].sum()) if "is_regime_change" in data.columns else 0
    pct_pt   = n_point  / total * 100 if total > 0 else 0
    pct_rg   = n_regime / total * 100 if total > 0 else 0
    worst    = float(data["anomaly_score"].max())
    cov      = data["pred_median"].notna().sum() / total * 100
    sev      = _severity(worst) if n_anom > 0 else "OK"
    d0       = pd.to_datetime(data[config.timestamp_col].min()).strftime("%d/%m/%Y")
    d1       = pd.to_datetime(data[config.timestamp_col].max()).strftime("%d/%m/%Y")

    border = _C.get(sev, "#888") if n_anom > 0 else "#2e7d32"
    txt = (
        f"Période      {d0} → {d1}\n"
        f"Mesures      {total:,}\n"
        f"Couverture   {cov:.0f} %\n"
        f"Ponctuelles  {n_point}  ({pct_pt:.1f} %)\n"
        f"Régime       {n_regime}h  ({pct_rg:.1f} %)\n"
        f"Pire score   {worst:.2f}  [{sev}]"
    )
    ax.text(
        0.997, 0.997, txt,
        transform=ax.transAxes, va="top", ha="right",
        fontsize=7.5, fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                  edgecolor=border, linewidth=2.0, alpha=0.97),
        zorder=15,
    )


def _draw_real_pred_anomalies(
    ax:    plt.Axes,
    data:  pd.DataFrame,
    tcol:  str,
    vcol:  str,
    config: EnergyConfig,
    show_regions: bool = True,
) -> list:
    """
    Tracé en 3 couches superposées — lisibilité maximale :

      Couche 1 (fond)    : zone verte  = intervalle de confiance Chronos (normal attendu)
      Couche 2 (milieu)  : ligne bleue = consommation réelle mesurée
      Couche 3 (dessus)  : zones rouges/violettes = anomalies + changements de pattern

    Sémantique couleur :
      Bleu  → données réelles
      Vert  → prédit normal (Chronos) — distinct du bleu ET du rouge
      Rouge → anomalie ponctuelle (vrai défaut)
      Violet → changement de régime / dérive saisonnière

    Retourne les handles pour la légende (ordonnés : réel → prédit → anomalies).
    """
    handles = []
    tcol_dt = pd.to_datetime(data[tcol])

    # ── Couche 1 : zone prédite normale (fond vert) ──────────────────────────
    # Verte = zone dans laquelle la valeur devrait se trouver selon Chronos.
    # Tout ce qui sort de cette zone est potentiellement anormal.
    pred = data[data["pred_median"].notna()].copy()
    if not pred.empty:
        pred_t = pd.to_datetime(pred[tcol])

        ax.fill_between(
            pred_t,
            pred["pred_low"], pred["pred_high"],
            alpha=0.18, color=_C["pred_fill"], zorder=1, rasterized=True,
        )
        ax.plot(pred_t, pred["pred_low"],
                color=_C["pred_low_line"], linewidth=1.2, alpha=0.85, zorder=2, rasterized=True)
        ax.plot(pred_t, pred["pred_high"],
                color=_C["pred_high_line"], linewidth=1.2, alpha=0.85, zorder=2, rasterized=True)
        ax.plot(
            pred_t, pred["pred_median"],
            color=_C["pred_median"], linestyle="--", linewidth=1.4, zorder=3, rasterized=True,
        )
        # Handles légende — prédiction
        handles.append(mpatches.Patch(
            color=_C["pred_fill"], alpha=0.55,
            label=f"Zone normale prédite [q{int(config.q_low*100)}–q{int(config.q_high*100)}]",
        ))
        handles.append(plt.Line2D(
            [0], [0], color=_C["pred_median"],
            linestyle="--", linewidth=1.6, label="Médiane Chronos",
        ))

    # ── Couche 2 : signal réel (premier plan bleu) ───────────────────────────
    ax.plot(
        tcol_dt, data[vcol],
        color=_C["real"], linewidth=1.8, zorder=5, rasterized=True,
    )
    # Clip Y pour éviter qu'un spike isolé écrase la dynamique du signal
    _clip_yaxis(ax, data[vcol])
    handles.insert(0, plt.Line2D(
        [0], [0], color=_C["real"],
        linewidth=2.0, label=f"Réel — {_label(vcol)}",
    ))

    # ── Couche 3a : changement de régime (fond violet très discret) ──────────
    # Violet = comportement qui change durablement (> seuil_regime_heures).
    # Ne mérite pas une alerte ponctuelle → fond discret, pas de marqueur.
    if show_regions and "is_regime_change" in data.columns and data["is_regime_change"].any():
        n_rg = int(data["is_regime_change"].sum())
        ax.fill_between(
            tcol_dt, 0, 1,
            where=data["is_regime_change"].values,
            transform=ax.get_xaxis_transform(),
            alpha=0.09, color=_C["regime"], zorder=1.5, rasterized=True,
        )
        handles.append(mpatches.Patch(
            color=_C["regime"], alpha=0.5,
            label=f"Changement de régime ({n_rg}h)",
        ))

    # ── Couche 3b : anomalies ponctuelles — direction élevée ↑ ou faible ↓ ──
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
                                alpha=0.15, color=color, zorder=2, rasterized=True)
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
                                alpha=0.12, color=_C["anom_region"], zorder=2, rasterized=True)
        else:
            ax.fill_between(
                tcol_dt, 0, 1,
                where=data[point_col].values,
                transform=ax.get_xaxis_transform(),
                alpha=0.15, color=_C["anom_region"], zorder=2, rasterized=True,
            )
            anom = data[data[point_col]]
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


def _draw_score_panel(
    ax:   plt.Axes,
    data: pd.DataFrame,
    tcol: str,
) -> None:
    """Anomaly score over time — area chart. Instantly shows where anomalies cluster."""
    score = data["anomaly_score"].fillna(0)
    tcol_dt = pd.to_datetime(data[tcol])

    ax.fill_between(tcol_dt, 0, score,
                    where=(score > 0),
                    color=_C["score_fill"], alpha=0.85, zorder=2, rasterized=True)
    ax.plot(tcol_dt, score,
            color=_C["HIGH"], linewidth=0.6, zorder=3, rasterized=True)

    # Severity thresholds
    ax.axhline(2, color=_C["MEDIUM"], linestyle=":", linewidth=0.9, alpha=0.7)
    ax.axhline(5, color=_C["HIGH"],   linestyle=":", linewidth=0.9, alpha=0.7)
    ax.text(0.001, 2.1, "MEDIUM", transform=ax.get_yaxis_transform(),
            fontsize=6.5, color=_C["MEDIUM"], va="bottom")
    ax.text(0.001, 5.1, "HIGH",   transform=ax.get_yaxis_transform(),
            fontsize=6.5, color=_C["HIGH"],   va="bottom")

    ax.set_ylim(0, max(score.max() * 1.15, 6))
    ax.set_ylabel("Score\nanomal.", fontsize=7.5, labelpad=2)
    ax.tick_params(axis="y", labelsize=7)


def _annotate_worst(
    ax:   plt.Axes,
    data: pd.DataFrame,
    tcol: str,
    vcol: str,
) -> None:
    # Annoter uniquement la pire anomalie PONCTUELLE (pas les régimes)
    point_col  = "is_point_anomaly" if "is_point_anomaly" in data.columns else "is_anomaly"
    point_data = data[data[point_col] & data[vcol].notna()]
    if point_data.empty:
        return
    worst = point_data.loc[point_data["anomaly_score"].idxmax()]
    sev   = _severity(float(worst["anomaly_score"]))
    ts    = pd.to_datetime(worst[tcol]).strftime("%d/%m %Hh")
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
        fontsize   = 7.5, color=_C[sev], fontweight="bold",
        annotation_clip = False,
        arrowprops = dict(arrowstyle="->", color=_C[sev], lw=1.4,
                          connectionstyle="arc3,rad=0.2"),
        bbox = dict(boxstyle="round,pad=0.35", facecolor="white",
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

def anomaly_summary(df: pd.DataFrame, config: EnergyConfig) -> pd.DataFrame:
    base = _base_summary(df, item_col=config.item_col,
                         extra_cols=[config.device_col, config.phase_col])
    for col in config.value_cols:
        flag_col = f"is_anomaly_{col}"
        if flag_col in df.columns:
            per_col = (df.groupby(config.item_col)[flag_col]
                       .sum().astype(int).rename(f"anomalies_{col}"))
            base = base.merge(per_col, on=config.item_col, how="left")
    return base


# ── Main anomaly plot ─────────────────────────────────────────────────────────

def plot_device(df: pd.DataFrame, device_id: str, config: EnergyConfig) -> None:
    """
    Génère le PNG principal par device — un bloc de 3 panneaux par phase :

      PANNEAU HAUT (grand)    : signal réel + zone verte prédite + zones rouges anomalies
      PANNEAU BAS (fin)       : score d'anomalie dans le temps (graphique en aire)
      PANNEAU DROIT (zoom)    : gros plan centré sur la pire anomalie détectée

    Fichier de sortie : anomaly_{device_id}.png
    """
    _apply_style()
    phases = sorted(df[df[config.device_col] == device_id][config.phase_col].unique())
    n = len(phases)
    if n == 0:
        return

    primary = config.value_col

    dev_data = df[df[config.device_col] == device_id]
    d0 = pd.to_datetime(dev_data[config.timestamp_col].min()).strftime("%d/%m/%Y")
    d1 = pd.to_datetime(dev_data[config.timestamp_col].max()).strftime("%d/%m/%Y")

    fig = plt.figure(figsize=(14, 5 * n), facecolor="white")

    outer = gridspec.GridSpec(n, 2, width_ratios=[3, 1],
                               hspace=0.65, wspace=0.10, figure=fig)

    fig.suptitle(
        f"ARIA BMS  —  Anomalies  —  Device {device_id}",
        fontsize=17, fontweight="bold", y=0.98,
    )
    fig.text(
        0.5, 0.965,
        f"Période : {d0}  →  {d1}   |   {n} phases   |   {_label(primary)}",
        ha="center", va="top", fontsize=11, color="#444444",
    )

    for i, phase in enumerate(phases):
        item_id = f"{device_id}_{phase}"
        data    = (
            df[df[config.item_col] == item_id]
            .sort_values(config.timestamp_col)
            .reset_index(drop=True)
            .copy()
        )
        data[config.timestamp_col] = pd.to_datetime(data[config.timestamp_col])
        ylbl = _label(primary)

        # Sous-échantillonnage pour l'affichage uniquement
        _step = max(1, len(data) // 1500)
        data_disp = data.iloc[::_step].copy() if _step > 1 else data

        # Inner grid (left side): 2 rows — main signal + score
        inner = gridspec.GridSpecFromSubplotSpec(
            2, 1,
            subplot_spec = outer[i, 0],
            height_ratios = [4, 1],
            hspace = 0.08,
        )
        ax_main  = fig.add_subplot(inner[0])
        ax_score = fig.add_subplot(inner[1], sharex=ax_main)

        # ── ROW A : real / predicted / anomaly regions ────────────────────────
        handles = _draw_real_pred_anomalies(
            ax_main, data_disp, config.timestamp_col, primary, config,
            show_regions=True,
        )
        _anomaly_rug(ax_main, data, config.timestamp_col)

        n_anom   = int(data["is_anomaly"].sum())
        n_point  = int(data["is_point_anomaly"].sum()) if "is_point_anomaly" in data.columns else n_anom
        n_regime = int(data["is_regime_change"].sum()) if "is_regime_change" in data.columns else 0
        _status_badge(ax_main, n_anom, n_point, n_regime, len(data))
        _annotate_worst(ax_main, data, config.timestamp_col, primary)

        ax_main.set_title(
            f"Phase {phase}   —   {n_point} anomalie(s) ponctuelle(s)   |   {n_regime} h de dérive",
            loc="left", fontsize=12, pad=10,
        )
        ax_main.set_ylabel(ylbl, fontsize=11)
        ax_main.legend(handles=handles, loc="upper right", ncol=2,
                       fontsize=9, framealpha=0.95)
        plt.setp(ax_main.get_xticklabels(), visible=False)

        # ── ROW B : anomaly score timeline ───────────────────────────────────
        _draw_score_panel(ax_score, data_disp, config.timestamp_col)
        _fmt_full(ax_score, data, config.timestamp_col)
        ax_score.tick_params(axis="x", labelsize=9)

        # ── RIGHT : smart zoom ────────────────────────────────────────────────
        ax_zoom = fig.add_subplot(outer[i, 1])
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
                z_anom = zoom[zoom["is_anomaly"]]
                ax_zoom.fill_between(
                    pd.to_datetime(zoom[config.timestamp_col]),
                    0, 1,
                    where=zoom["is_anomaly"].values,
                    transform=ax_zoom.get_xaxis_transform(),
                    alpha=0.20, color=_C["anom_region"], zorder=0,
                )
                ax_zoom.scatter(
                    pd.to_datetime(z_anom[config.timestamp_col]), z_anom[primary],
                    color=_C["anom_region"], s=80, zorder=6,
                    marker="o", edgecolors="white", linewidths=0.8,
                )

        zoom_d0 = pd.to_datetime(zoom[config.timestamp_col].min()).strftime("%d/%m")
        zoom_d1 = pd.to_datetime(zoom[config.timestamp_col].max()).strftime("%d/%m")
        suffix = "pire anomalie" if data["is_anomaly"].any() else "récent"
        ax_zoom.set_title(f"Zoom {suffix}  [{zoom_d0} → {zoom_d1}]", loc="left", fontsize=9)
        ax_zoom.yaxis.set_label_position("right")
        ax_zoom.yaxis.tick_right()
        ax_zoom.legend(fontsize=7, loc="upper left")
        _fmt_zoom(ax_zoom, zoom, config.timestamp_col)

    os.makedirs(config.output_dir, exist_ok=True)
    out = os.path.join(config.output_dir, f"anomaly_{device_id}.png")
    fig.savefig(out, dpi=80)
    plt.close(fig)
    _log.info("Plot saved: %s", out)


def plot_device_features(df: pd.DataFrame, device_id: str, config: EnergyConfig) -> None:
    """
    Per-feature detail PNG : one row per value_col.
    Each row = real signal + prediction band + score panel.
    """
    if len(config.value_cols) < 2:
        return

    _apply_style()
    phases = sorted(df[df[config.device_col] == device_id][config.phase_col].unique())

    for phase in phases:
        item_id = f"{device_id}_{phase}"
        data = (
            df[df[config.item_col] == item_id]
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
            f"Détail par feature  —  Device {device_id}  |  Phase {phase}  |  {d0} → {d1}\n"
            f"Bleu = réel  |  Vert = prédit  |  Rouge = anomalie  |  Violet = régime",
            fontsize=11, fontweight="bold",
        )

        outer = gridspec.GridSpec(n_cols, 1, hspace=0.55, figure=fig)

        for j, col in enumerate(config.value_cols):
            flag_col  = f"is_anomaly_{col}"
            pred_col  = f"pred_median_{col}"
            low_col   = f"pred_low_{col}"
            high_col  = f"pred_high_{col}"

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
                show_regions=True,
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
        out = os.path.join(config.output_dir, f"anomaly_{device_id}_{phase}.png")
        fig.savefig(out, dpi=100, bbox_inches="tight")
        plt.close(fig)
        _log.info("Feature plot saved: %s", out)


def plot_all_devices(df: pd.DataFrame, config: EnergyConfig) -> None:
    import gc
    for device_id in sorted(df[config.device_col].unique()):
        try:
            plot_device(df, device_id, config)
        except Exception as exc:
            _log.error("anomaly plot failed for %s: %s", device_id, exc)
        finally:
            plt.close("all")
            gc.collect()
        try:
            plot_device_features(df, device_id, config)
        except Exception as exc:
            _log.error("feature plot failed for %s: %s", device_id, exc)
        finally:
            plt.close("all")
            gc.collect()


# ── Forecasting ───────────────────────────────────────────────────────────────

_SEVERITY_COLORS = {"HIGH": _C["HIGH"], "MEDIUM": _C["MEDIUM"], "LOW": _C["LOW"]}


def forecast_summary(forecast_df: pd.DataFrame, config: EnergyConfig) -> pd.DataFrame:
    if forecast_df.empty:
        return pd.DataFrame()
    rows = []
    for (item_id, col), grp in forecast_df.groupby(
        [config.item_col, "forecast_col"], sort=True
    ):
        parts = str(item_id).rsplit("_", 1)
        rows.append({
            config.item_col:         item_id,
            config.device_col:       parts[0],
            config.phase_col:        parts[1] if len(parts) > 1 else "",
            "forecast_col":          col,
            "total_hours":           len(grp),
            "alert_count":           int(grp["is_alert"].sum()),
            "HIGH":                  int((grp["alert_severity"] == "HIGH").sum()),
            "MEDIUM":                int((grp["alert_severity"] == "MEDIUM").sum()),
            "LOW":                   int((grp["alert_severity"] == "LOW").sum()),
            "avg_confidence":        round(float(grp["confidence"].mean()), 3),
            "low_confidence_hours":  int((grp["confidence"] < config.min_confidence).sum()),
        })
    return pd.DataFrame(rows)


def plot_forecast_device(
    df:          pd.DataFrame,
    forecast_df: pd.DataFrame,
    device_id:   str,
    config:      EnergyConfig,
) -> None:
    _apply_style()
    if forecast_df.empty:
        return
    primary = config.value_col
    phases  = sorted(df[df[config.device_col] == device_id][config.phase_col].unique())
    n = len(phases)
    if n == 0:
        return

    fig = plt.figure(figsize=(18, 5 * n), facecolor="white")
    gs  = gridspec.GridSpec(n, 2, width_ratios=[3, 1], hspace=0.55, wspace=0.10, figure=fig)
    fig.suptitle(
        f"Prévision préventive  —  Device {device_id}\n"
        f"Horizon : {config.forecast_horizon}h  |  {_label(primary)}",
        fontsize=11, fontweight="bold", y=1.02,
    )

    for i, phase in enumerate(phases):
        item_id = f"{device_id}_{phase}"
        hist = (df[df[config.item_col] == item_id]
                .sort_values(config.timestamp_col).copy())
        hist[config.timestamp_col] = pd.to_datetime(hist[config.timestamp_col])

        fc = forecast_df[
            (forecast_df[config.item_col] == item_id)
            & (forecast_df["forecast_col"] == primary)
        ].copy()
        if not fc.empty:
            fc[config.timestamp_col] = pd.to_datetime(fc[config.timestamp_col])

        ax_l = fig.add_subplot(gs[i, 0])
        tail = hist.tail(config.context_length)
        ax_l.plot(tail[config.timestamp_col], tail[primary],
                  color=_C["real"], linewidth=1.3, label="Historique", zorder=4)

        if not fc.empty:
            ax_l.fill_between(fc[config.timestamp_col],
                              fc["forecast_low"], fc["forecast_high"],
                              alpha=0.38, color=_C["forecast_band"],
                              label=f"Intervalle prévision [q{int(config.q_low*100)}–q{int(config.q_high*100)}]")
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

        ax_l.set_title(f"Phase {phase}  —  Historique + Prévision {config.forecast_horizon}h", loc="left")
        ax_l.set_ylabel(_label(primary), fontsize=9)
        ax_l.legend(ncol=2, fontsize=7.5, loc="upper left")
        _fmt_zoom(ax_l, hist.tail(config.context_length + config.forecast_horizon),
                  config.timestamp_col)

        ax_r = fig.add_subplot(gs[i, 1])
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
        _fmt_zoom(ax_r, fc if not fc.empty else hist.tail(10), config.timestamp_col)

    os.makedirs(config.output_dir, exist_ok=True)
    out = os.path.join(config.output_dir, f"forecast_{device_id}.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    _log.info("Forecast plot saved: %s", out)


def plot_all_forecasts(
    df:          pd.DataFrame,
    forecast_df: pd.DataFrame,
    config:      EnergyConfig,
) -> None:
    import gc
    for device_id in sorted(df[config.device_col].unique()):
        plot_forecast_device(df, forecast_df, device_id, config)
        plt.close("all")
        gc.collect()


# ── Combined view ─────────────────────────────────────────────────────────────

def plot_combined_device(
    df:        pd.DataFrame,
    device_id: str,
    config:    EnergyConfig,
) -> None:
    """
    Vue principale destinée à l'opérateur — combine détection et résumé en un seul coup d'œil.

    Layout par phase :
      ┌──────────────────────────────────────┬─────────────────┐
      │  Signal réel + Zone prédite          │  Statut         │
      │  Rug markers d'anomalies             │  + Métriques    │
      │  Badge ALERTE/ATTENTION/OK           │  + Top 3 events │
      ├──────────────────────────────────────┤                 │
      │  Score temporel                      │                 │
      └──────────────────────────────────────┴─────────────────┘

    Le forecast est dans forecast_{device}.png — pas besoin de le répéter ici.
    """
    _apply_style()
    primary = config.value_col
    phases  = sorted(df[df[config.device_col] == device_id][config.phase_col].unique())
    n = len(phases)
    if n == 0:
        return

    dev_data = df[df[config.device_col] == device_id]
    d0 = pd.to_datetime(dev_data[config.timestamp_col].min()).strftime("%d/%m/%Y")
    d1 = pd.to_datetime(dev_data[config.timestamp_col].max()).strftime("%d/%m/%Y")

    fig = plt.figure(figsize=(14, 5 * n), facecolor="white")
    outer = gridspec.GridSpec(n, 2, width_ratios=[4, 1],
                               hspace=0.65, wspace=0.08, figure=fig)

    # Titre lisible par un opérateur — aucun paramètre technique
    fig.suptitle(
        f"Device {device_id}",
        fontsize=17, fontweight="bold", y=0.98,
    )
    fig.text(
        0.5, 0.965,
        f"Période : {d0}  →  {d1}   |   {n} phases analysées   |   {_label(primary)}",
        ha="center", va="top", fontsize=11, color="#444444",
    )

    for i, phase in enumerate(phases):
        item_id = f"{device_id}_{phase}"
        hist = (df[df[config.item_col] == item_id]
                .sort_values(config.timestamp_col)
                .reset_index(drop=True).copy())
        hist[config.timestamp_col] = pd.to_datetime(hist[config.timestamp_col])

        n_anom   = int(hist["is_anomaly"].sum())
        n_point  = int(hist["is_point_anomaly"].sum()) if "is_point_anomaly" in hist.columns else n_anom
        n_regime = int(hist["is_regime_change"].sum()) if "is_regime_change" in hist.columns else 0

        # Sous-échantillonnage pour l'affichage uniquement (stats calculées sur hist complet)
        _step = max(1, len(hist) // 1500)
        hist_disp = hist.iloc[::_step].copy() if _step > 1 else hist

        # ── PANEL GAUCHE : détection ──────────────────────────────────────────
        inner = gridspec.GridSpecFromSubplotSpec(
            2, 1, subplot_spec=outer[i, 0],
            height_ratios=[4, 1], hspace=0.08,
        )
        ax_main  = fig.add_subplot(inner[0])
        ax_score = fig.add_subplot(inner[1], sharex=ax_main)

        handles = _draw_real_pred_anomalies(
            ax_main, hist_disp, config.timestamp_col, primary, config,
        )
        _anomaly_rug(ax_main, hist, config.timestamp_col)
        _status_badge(ax_main, n_anom, n_point, n_regime, len(hist))
        _annotate_worst(ax_main, hist, config.timestamp_col, primary)

        ax_main.set_title(
            f"Phase {phase}   —   {n_point} anomalie(s) ponctuelle(s)   |   {n_regime} h de dérive",
            loc="left", fontsize=12, pad=10,
        )
        ax_main.set_ylabel(_label(primary), fontsize=11)
        ax_main.legend(handles=handles, loc="upper right", ncol=2, fontsize=9)
        plt.setp(ax_main.get_xticklabels(), visible=False)

        _draw_score_panel(ax_score, hist_disp, config.timestamp_col)
        _fmt_full(ax_score, hist, config.timestamp_col)
        ax_score.tick_params(axis="x", labelsize=9)

        # ── PANEL DROIT : résumé opérateur ───────────────────────────────────
        ax_summary = fig.add_subplot(outer[i, 1])
        _draw_summary_panel(ax_summary, hist, config, phase)

    os.makedirs(config.output_dir, exist_ok=True)
    out = os.path.join(config.output_dir, f"combined_{device_id}.png")
    fig.savefig(out, dpi=80)
    plt.close(fig)
    _log.info("Combined plot saved: %s", out)


def plot_all_combined(df: pd.DataFrame, config: EnergyConfig) -> None:
    import gc
    for device_id in sorted(df[config.device_col].unique()):
        try:
            plot_combined_device(df, device_id, config)
        except Exception as exc:
            _log.error("combined plot failed for %s: %s", device_id, exc)
        finally:
            plt.close("all")
            gc.collect()


# ── Real vs Prediction focused view ──────────────────────────────────────────

def plot_real_vs_pred_device(
    df:        pd.DataFrame,
    device_id: str,
    config:    EnergyConfig,
) -> None:
    """
    Vue "réel vs prédiction" — évalue la qualité du modèle Chronos.
    Layout : signal (gauche 4/5) + panneau qualité dédié (droite 1/5) — zéro overlap.
    Fichier de sortie : real_vs_pred_{device_id}.png
    """
    _apply_style()
    primary = config.value_col
    phases  = sorted(df[df[config.device_col] == device_id][config.phase_col].unique())
    n = len(phases)
    if n == 0:
        return

    dev_data = df[df[config.device_col] == device_id]
    d0 = pd.to_datetime(dev_data[config.timestamp_col].min()).strftime("%d/%m/%Y")
    d1 = pd.to_datetime(dev_data[config.timestamp_col].max()).strftime("%d/%m/%Y")

    fig = plt.figure(figsize=(18, 5 * n), facecolor="white")
    fig.suptitle(
        f"Consommation réelle vs Prédiction Chronos  —  Device {device_id}",
        fontsize=15, fontweight="bold", y=1.01,
    )
    fig.text(
        0.5, 0.998,
        f"Période : {d0}  →  {d1}   |   {_label(primary)}",
        ha="center", va="top", fontsize=10, color="#555555",
    )

    outer = gridspec.GridSpec(
        n, 2, width_ratios=[4, 1],
        hspace=0.55, wspace=0.10, figure=fig,
    )

    for i, phase in enumerate(phases):
        ax      = fig.add_subplot(outer[i, 0])
        ax_info = fig.add_subplot(outer[i, 1])
        ax_info.axis("off")

        item_id = f"{device_id}_{phase}"
        data = (
            df[df[config.item_col] == item_id]
            .sort_values(config.timestamp_col)
            .reset_index(drop=True)
            .copy()
        )
        data[config.timestamp_col] = pd.to_datetime(data[config.timestamp_col])
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
        n_out = int(data[point_col].sum())
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

        ax.set_title(f"Phase {phase}  —  {_label(primary)}", loc="left", fontsize=11)
        ax.set_ylabel(_label(primary), fontsize=10)
        ax.legend(handles=handles, loc="upper left", ncol=3, fontsize=9, framealpha=0.95)
        _fmt_full(ax, data, config.timestamp_col)

        # ── Panneau info droit (hors espace données — zéro overlap) ──────
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
                f"Phase {phase}\n"
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
                0.5, 0.6, f"Phase {phase}\n{'─' * 18}\nPas de\nprédiction",
                ha="center", va="center", transform=ax_info.transAxes,
                fontsize=10, fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                          edgecolor="#aaaaaa", linewidth=1.5),
            )

    os.makedirs(config.output_dir, exist_ok=True)
    out = os.path.join(config.output_dir, f"real_vs_pred_{device_id}.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    _log.info("Real-vs-pred plot saved: %s", out)


def plot_all_real_vs_pred(df: pd.DataFrame, config: EnergyConfig) -> None:
    import gc
    for device_id in sorted(df[config.device_col].unique()):
        plot_real_vs_pred_device(df, device_id, config)
        plt.close("all")
        gc.collect()
