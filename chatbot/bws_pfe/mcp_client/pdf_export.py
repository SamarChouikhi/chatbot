"""
pdf_export.py — Génère un rapport PDF d'analyse ARIA avec graphiques embarqués.

Dépendances : reportlab, matplotlib (déjà dans requirements.txt si AD est installé,
              sinon : pip install reportlab matplotlib)

Usage :
    from mcp_client.pdf_export import generate_analysis_pdf
    file_id, filename = generate_analysis_pdf(title, text, charts, lang, question)
    # → fichier dans PDF_TMP_DIR/<file_id>.pdf, expire après 1h
"""

from __future__ import annotations

import io
import logging
import re
import time
import uuid
import tempfile
from pathlib import Path

logger = logging.getLogger('aria.pdf')

PDF_TMP_DIR  = Path(tempfile.gettempdir()) / 'aria_pdf'
_MAX_AGE_SEC = 3600          # 1 heure

# Palette de couleurs cohérente avec l'UI ARIA (dark theme)
_PALETTE    = ['#0ea5e9', '#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444', '#f97316']
_DARK_BG    = '#0f172a'
_CARD_BG    = '#1e293b'
_MUTED      = '#64748b'
_LIGHT_TEXT = '#e2e8f0'
_BORDER     = '#334155'
_BRAND      = '#0ea5e9'


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cleanup() -> None:
    """Supprime les PDF expirés."""
    if not PDF_TMP_DIR.exists():
        return
    now = time.time()
    for f in PDF_TMP_DIR.iterdir():
        try:
            if now - f.stat().st_mtime > _MAX_AGE_SEC:
                f.unlink(missing_ok=True)
        except Exception:
            pass


def _hex(color: str):
    """Convertit une couleur hex en objet reportlab Color."""
    from reportlab.lib import colors
    return colors.HexColor(color)


# ─────────────────────────────────────────────────────────────────────────────
# Rendu graphique (matplotlib → PNG bytes)
# ─────────────────────────────────────────────────────────────────────────────

def _render_chart(chart: dict, width_px: int = 540, height_px: int = 270) -> bytes | None:
    """Convertit un AriaChartConfig en image PNG (fond sombre, style dashboard)."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np

        ctype   = chart.get('type', 'bar')
        title   = chart.get('title', '')
        labels  = chart.get('labels', [])
        datasets = chart.get('datasets', [])
        unit    = chart.get('unit', '')
        y_max   = chart.get('yMax')

        dpi  = 110
        fig, ax = plt.subplots(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)

        fig.patch.set_facecolor(_DARK_BG)
        ax.set_facecolor(_CARD_BG)
        for spine in ax.spines.values():
            spine.set_color(_BORDER)
        ax.tick_params(colors=_MUTED, labelsize=7)
        ax.set_title(title, color=_LIGHT_TEXT, fontsize=8, pad=5, loc='left')
        if unit:
            ax.set_ylabel(unit, color=_MUTED, fontsize=7)

        if ctype == 'doughnut':
            data_vals   = datasets[0]['data']    if datasets else []
            item_colors = (datasets[0].get('colors')
                           or [_PALETTE[i % len(_PALETTE)] for i in range(len(data_vals))])
            wedges, texts, autos = ax.pie(
                data_vals, labels=labels, colors=item_colors,
                autopct='%1.0f%%', startangle=90,
                wedgeprops={'width': 0.52, 'edgecolor': _DARK_BG, 'linewidth': 1.5},
                textprops={'color': _LIGHT_TEXT, 'fontsize': 6},
            )
            for at in autos:
                at.set_fontsize(6)
                at.set_color(_LIGHT_TEXT)

        elif ctype in ('bar', 'line'):
            x = np.arange(len(labels))
            n = len(datasets)
            w = min(0.8 / max(n, 1), 0.4)

            for idx, ds in enumerate(datasets):
                color  = ds.get('color') or _PALETTE[idx % len(_PALETTE)]
                vals   = ds.get('data', [])
                icolors = ds.get('colors') or [color] * len(vals)
                lbl    = ds.get('label', '')

                if ctype == 'line':
                    ax.plot(x, vals, color=color, marker='o', markersize=2.5,
                            linewidth=1.4, label=lbl)
                    ax.fill_between(x, vals, alpha=0.08, color=color)
                else:
                    offset = (idx - n / 2 + 0.5) * w
                    ax.bar(x + offset, vals, width=w * 0.88,
                           color=icolors, label=lbl, zorder=2,
                           edgecolor=_DARK_BG, linewidth=0.4)

            ax.set_xticks(x)
            step = max(1, len(labels) // 9)
            ax.set_xticklabels(
                [l if i % step == 0 else '' for i, l in enumerate(labels)],
                rotation=30, ha='right', fontsize=6, color=_MUTED,
            )
            ax.yaxis.grid(True, color=_BORDER, linewidth=0.5, zorder=0)
            ax.set_axisbelow(True)
            if y_max:
                ax.set_ylim(0, y_max)
            if n > 1:
                ax.legend(fontsize=6, labelcolor=_MUTED,
                          facecolor=_CARD_BG, edgecolor=_BORDER, framealpha=0.9,
                          loc='upper right')

        plt.tight_layout(pad=0.7)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', facecolor=fig.get_facecolor(),
                    bbox_inches='tight', dpi=dpi)
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    except Exception as exc:
        logger.warning(f'[PDF] chart render failed ({chart.get("title")}): {exc}')
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Conversion Markdown → flowables reportlab
# ─────────────────────────────────────────────────────────────────────────────

def _inline_md(text: str) -> str:
    """Transforme le Markdown inline en balises HTML reportlab."""
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'\*\*(.+?)\*\*',     r'<b>\1</b>',         text)
    text = re.sub(r'\*(.+?)\*',         r'<i>\1</i>',         text)
    text = re.sub(r'`(.+?)`',           r'<font name="Courier">\1</font>', text)
    # Icônes emoji — reportlab les passe en boîte vide, on les garde tels quels
    return text


def _md_to_flowables(text: str, styles: dict) -> list:
    """Convertit un texte Markdown en liste de flowables reportlab."""
    from reportlab.platypus import Paragraph, Spacer
    from reportlab.lib.units import cm

    body   = styles['body']
    h3     = styles['h3']
    bullet = styles['bullet']
    code   = styles['code']

    flowables = []
    in_code   = False
    code_buf  = []

    for raw_line in text.split('\n'):
        line = raw_line.rstrip()

        # Blocs de code ```
        if line.startswith('```'):
            if in_code:
                if code_buf:
                    for cl in code_buf:
                        flowables.append(Paragraph(cl or ' ', code))
                code_buf = []
                in_code  = False
                flowables.append(Spacer(1, 0.15 * cm))
            else:
                in_code = True
            continue
        if in_code:
            code_buf.append(line.replace('&', '&amp;').replace('<', '&lt;'))
            continue

        stripped = line.strip()
        if not stripped:
            flowables.append(Spacer(1, 0.18 * cm))
            continue

        if stripped.startswith('### '):
            flowables.append(Paragraph(_inline_md(stripped[4:]), h3))
        elif stripped.startswith('## '):
            flowables.append(Paragraph(_inline_md(stripped[3:]), h3))
        elif stripped.startswith('# '):
            flowables.append(Paragraph(_inline_md(stripped[2:]), h3))
        elif re.match(r'^[-•*]\s', stripped):
            flowables.append(Paragraph('• ' + _inline_md(stripped[2:].strip()), bullet))
        elif re.match(r'^\d+\.\s', stripped):
            content = re.sub(r'^\d+\.\s+', '', stripped)
            flowables.append(Paragraph(_inline_md(content), bullet))
        elif re.match(r'^\*\*[^*]+\*\*\s*:?\s*$', stripped):
            flowables.append(Paragraph(_inline_md(stripped), body))
        else:
            flowables.append(Paragraph(_inline_md(stripped), body))

    return flowables


# ─────────────────────────────────────────────────────────────────────────────
# Numérotation de pages (canvas callback)
# ─────────────────────────────────────────────────────────────────────────────

def _make_on_page(brand_hex, dark_hex, muted_hex, light_hex, border_hex, margin_pt, title_str):
    """Retourne le callback de page (header + footer sur fond sombre)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors

    BRAND  = colors.HexColor(brand_hex)
    DARK   = colors.HexColor(dark_hex)
    MUTED  = colors.HexColor(muted_hex)
    LIGHT  = colors.HexColor(light_hex)
    W, H   = A4
    M      = margin_pt

    def _on_page(c, doc):
        c.saveState()

        # Fond entier
        c.setFillColor(DARK)
        c.rect(0, 0, W, H, fill=1, stroke=0)

        # Barre header
        from reportlab.lib.units import cm
        bar_h = 1.7 * cm
        c.setFillColor(BRAND)
        c.rect(0, H - bar_h, W, bar_h, fill=1, stroke=0)

        # Titre dans header
        c.setFillColor(LIGHT)
        c.setFont('Helvetica-Bold', 10)
        c.drawString(M, H - bar_h + 0.52 * cm, 'ARIA — Rapport d\'analyse')

        # Sous-titre dans header (titre tronqué)
        if title_str:
            c.setFont('Helvetica', 7.5)
            c.setFillColor(colors.HexColor('#bfdbfe'))
            short = title_str[:70] + ('…' if len(title_str) > 70 else '')
            c.drawRightString(W - M, H - bar_h + 0.52 * cm, short)

        # Footer
        c.setStrokeColor(colors.HexColor(border_hex))
        c.setLineWidth(0.4)
        c.line(M, 1.0 * cm, W - M, 1.0 * cm)
        c.setFont('Helvetica', 7)
        c.setFillColor(MUTED)
        ts = time.strftime('%d/%m/%Y à %H:%M')
        c.drawString(M, 0.55 * cm, f'Généré le {ts} par ARIA — Analyse IoT')
        c.drawRightString(W - M, 0.55 * cm, f'Page {doc.page}')

        c.restoreState()

    return _on_page


# ─────────────────────────────────────────────────────────────────────────────
# Fonction principale
# ─────────────────────────────────────────────────────────────────────────────

def generate_analysis_pdf(
    title   : str,
    text    : str,
    charts  : list[dict],
    lang    : str = 'fr',
    question: str = '',
) -> tuple[str, str] | None:
    """
    Génère un PDF d'analyse ARIA avec texte Markdown + graphiques matplotlib.

    Args:
        title    : Titre du rapport (première ligne de la réponse ARIA)
        text     : Réponse complète en Markdown
        charts   : Liste de AriaChartConfig dicts (de chart_builder.py)
        lang     : Langue de l'UI (non utilisé pour l'instant — rapport en fr)
        question : Question originale de l'utilisateur (affichée en sous-titre)

    Returns:
        (file_id, filename) ou None si échec
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib.enums import TA_LEFT
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Image,
            HRFlowable, KeepTogether,
        )

        PDF_TMP_DIR.mkdir(parents=True, exist_ok=True)
        _cleanup()

        file_id  = str(uuid.uuid4())
        safe_t   = re.sub(r'[^\w\-]', '_', (title or 'Analyse')[:35]).strip('_')
        filename = f'ARIA_{safe_t}_{time.strftime("%Y%m%d_%H%M")}.pdf'
        path     = PDF_TMP_DIR / f'{file_id}.pdf'

        W, H  = A4
        M     = 1.8 * cm   # marges

        # ── Palette ────────────────────────────────────────────
        C_BRAND  = _hex(_BRAND)
        C_DARK   = _hex(_DARK_BG)
        C_MUTED  = _hex(_MUTED)
        C_LIGHT  = _hex(_LIGHT_TEXT)
        C_BORDER = _hex(_BORDER)
        C_ACCENT = _hex('#06b6d4')

        # ── Styles de paragraphe ───────────────────────────────
        _base = dict(fontName='Helvetica', leading=13)

        s_body = ParagraphStyle(
            'body', **_base, fontSize=9, textColor=C_LIGHT, spaceAfter=3,
        )
        s_h3 = ParagraphStyle(
            'h3', fontName='Helvetica-Bold', fontSize=10, leading=14,
            textColor=C_BRAND, spaceBefore=8, spaceAfter=4,
        )
        s_bullet = ParagraphStyle(
            'bullet', **_base, fontSize=9, textColor=C_LIGHT,
            leftIndent=14, spaceAfter=2,
        )
        s_code = ParagraphStyle(
            'code', fontName='Courier', fontSize=7.5, leading=11,
            textColor=_hex('#94a3b8'), backColor=_hex('#0f172a'),
            leftIndent=8, rightIndent=8, spaceAfter=1,
        )
        s_title = ParagraphStyle(
            'title', fontName='Helvetica-Bold', fontSize=15, leading=18,
            textColor=C_LIGHT, spaceAfter=4, alignment=TA_LEFT,
        )
        s_meta = ParagraphStyle(
            'meta', **_base, fontSize=8, textColor=C_MUTED,
        )
        s_chart_lbl = ParagraphStyle(
            'chart_lbl', **_base, fontSize=7.5, textColor=C_MUTED, spaceAfter=2,
        )

        styles = {
            'body'  : s_body,
            'h3'    : s_h3,
            'bullet': s_bullet,
            'code'  : s_code,
        }

        # ── Document ───────────────────────────────────────────
        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            leftMargin=M, rightMargin=M,
            topMargin=2.3 * cm,   # sous la barre header
            bottomMargin=1.5 * cm,
        )

        on_page = _make_on_page(
            _BRAND, _DARK_BG, _MUTED, _LIGHT_TEXT, _BORDER, M, title or ''
        )

        story = []

        # ── Bloc titre ─────────────────────────────────────────
        story.append(Spacer(1, 0.25 * cm))
        story.append(Paragraph(title or 'Rapport d\'analyse ARIA', s_title))
        if question:
            q_short = question[:130] + ('…' if len(question) > 130 else '')
            story.append(Paragraph(f'Question : {q_short}', s_meta))
        story.append(Spacer(1, 0.25 * cm))
        story.append(HRFlowable(width='100%', thickness=0.5,
                                color=C_BRAND, spaceAfter=8))

        # ── Corps de l'analyse ─────────────────────────────────
        for flowable in _md_to_flowables(text, styles):
            story.append(flowable)

        # ── Section graphiques ─────────────────────────────────
        if charts:
            story.append(Spacer(1, 0.4 * cm))
            story.append(HRFlowable(width='100%', thickness=0.4,
                                    color=_hex(_BORDER), spaceAfter=6))
            story.append(Paragraph('Graphiques', s_h3))
            story.append(Spacer(1, 0.2 * cm))

            # Largeur disponible et hauteur proportionnelle
            avail_w  = W - 2 * M
            img_h    = avail_w * 0.42

            # Conversion pt → px (matplotlib attend des px à dpi=110)
            px_w = int(avail_w * (110 / 72))
            px_h = int(img_h   * (110 / 72))

            for chart in charts:
                png = _render_chart(chart, width_px=px_w, height_px=px_h)
                if not png:
                    continue
                img_buf = io.BytesIO(png)
                img     = Image(img_buf, width=avail_w, height=img_h)
                lbl     = chart.get('title', '')
                block   = KeepTogether([
                    Paragraph(lbl, s_chart_lbl) if lbl else Spacer(1, 0.05 * cm),
                    img,
                    Spacer(1, 0.45 * cm),
                ])
                story.append(block)

        # ── Build ──────────────────────────────────────────────
        doc.build(story, onFirstPage=on_page, onLaterPages=on_page)

        # Stocke le nom suggéré pour la route /download/
        (PDF_TMP_DIR / f'{file_id}.name').write_text(filename, encoding='utf-8')

        size_kb = path.stat().st_size // 1024
        logger.info(f'[PDF] OK → {filename} ({size_kb} KB, {len(charts)} chart(s))')
        return file_id, filename

    except Exception as exc:
        logger.error(f'[PDF] generate_analysis_pdf failed: {exc}', exc_info=True)
        return None
