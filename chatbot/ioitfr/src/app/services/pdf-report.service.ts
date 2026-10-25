import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { of, firstValueFrom } from 'rxjs';
import { catchError } from 'rxjs/operators';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { WaterService, RtWmDto } from './water.service';
import { GazService, RtGmDto } from './gaz.service';
import { ElectricityService, RtEnPDto } from './electricity.service';
import { FuelService, FuelLatestDto } from './fuel.service';
import { normalizeBattery } from '../shared/battery.util';

// ════════════════════════════════════════════════════════════════════════════
// PARTIE PDF — génération des rapports PDF (jsPDF) par domaine et par filtre
// ════════════════════════════════════════════════════════════════════════════

// ── Public types ────────────────────────────────────────────────────────────

export type ReportDomain = 'water' | 'gaz' | 'electricity' | 'fuel';
export type ReportFilter = 'all' | 'active' | 'inactive' | 'alert' | 'leak' | 'fraud' | 'low_battery';

export interface ReportRequest {
  domain : ReportDomain;
  filter : ReportFilter;
  label  : string;
}

// ── Color palette ────────────────────────────────────────────────────────────

const DOMAIN_COLOR: Record<ReportDomain, [number, number, number]> = {
  water      : [14,  165, 233],
  gaz        : [245, 158, 11],
  electricity: [99,  102, 241],
  fuel       : [239, 68,  68],
};

const DOMAIN_LABEL: Record<ReportDomain, string> = {
  water      : 'Eau',
  gaz        : 'Gaz',
  electricity: 'Électricité',
  fuel       : 'Carburant',
};

const INACTIVE_THRESHOLD_MS = 8 * 60 * 60 * 1000;

// ── Service ──────────────────────────────────────────────────────────────────

@Injectable({ providedIn: 'root' })
export class PdfReportService {

  constructor(
    private http    : HttpClient,
    private waterSvc: WaterService,
    private gazSvc  : GazService,
    private elecSvc : ElectricityService,
    private fuelSvc : FuelService,
  ) {}

  // ── Entry points ────────────────────────────────────────────────────────

  /** Appelé par le bouton header (rapport eau complet) */
  async generateWaterReport(): Promise<void> {
    return this.generateReport({ domain: 'water', filter: 'all', label: 'Eau — Tous les capteurs' });
  }

  /** Point d'entrée générique déclenché par l'intent ARIA */
  async generateReport(req: ReportRequest): Promise<void> {
    const [logoB64, rows] = await Promise.all([
      this.fetchLogoBase64(),
      this.fetchAndFilter(req),
    ]);

    const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
    const now = new Date();

    this.drawHeader(doc, logoB64, req, now);
    this.drawKpiCards(doc, rows, req);
    const tableStartY = this.drawCharts(doc, rows, req, 82);
    this.drawTable(doc, rows, req, tableStartY);
    this.drawFooters(doc, req);

    const ts  = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    const slug = `${req.domain}-${req.filter}`;
    doc.save(`rapport-${slug}_${ts}.pdf`);
  }

  // ── Data fetching & filtering ────────────────────────────────────────────

  private async fetchAndFilter(req: ReportRequest): Promise<SensorRow[]> {
    switch (req.domain) {
      case 'water'      : return this.filterWater(req.filter);
      case 'gaz'        : return this.filterGaz(req.filter);
      case 'electricity': return this.filterElec(req.filter);
      case 'fuel'       : return this.filterFuel(req.filter);
    }
  }

  private async filterWater(f: ReportFilter): Promise<SensorRow[]> {
    const all = await firstValueFrom(this.waterSvc.getRealTimeAll().pipe(catchError(() => of([]))));
    return this.applyFilter(all.map(s => waterToRow(s)), f, all.map(s => ({
      status: s.status, battery: normalizeBattery(s.batteryLevel), date: s.date,
    })));
  }

  private async filterGaz(f: ReportFilter): Promise<SensorRow[]> {
    const all = await firstValueFrom(this.gazSvc.getRealTimeAll().pipe(catchError(() => of([]))));
    return this.applyFilter(all.map(s => gazToRow(s)), f, all.map(s => ({
      status: s.status, battery: normalizeBattery(s.batteryLevel), date: s.date,
    })));
  }

  private async filterElec(f: ReportFilter): Promise<SensorRow[]> {
    const all = await firstValueFrom(this.elecSvc.getRealTimeAll().pipe(catchError(() => of([]))));
    return this.applyFilter(all.map(s => elecToRow(s)), f, all.map(s => ({
      status: s.status, battery: normalizeBattery(s.batteryLevel), date: s.date,
    })));
  }

  private async filterFuel(f: ReportFilter): Promise<SensorRow[]> {
    const all = await firstValueFrom(this.fuelSvc.getAllLatest().pipe(catchError(() => of([]))));
    return this.applyFilter(all.map(s => fuelToRow(s)), f, all.map(s => ({
      status: s.status, battery: 100, date: s.date,
    })));
  }

  private applyFilter(
    rows   : SensorRow[],
    filter : ReportFilter,
    meta   : Array<{ status: string; battery: number; date: string }>,
  ): SensorRow[] {
    const now = Date.now();
    const isInactive = (m: typeof meta[0]) => now - new Date(m.date).getTime() > INACTIVE_THRESHOLD_MS;

    switch (filter) {
      case 'active'     : return rows.filter((_, i) => meta[i].status === 'OK' && !isInactive(meta[i]));
      case 'inactive'   : return rows.filter((_, i) => isInactive(meta[i]));
      case 'alert'      : return rows.filter((_, i) => meta[i].status !== 'OK');
      case 'leak'       : return rows.filter((_, i) => meta[i].status === 'LEAK');
      case 'fraud'      : return rows.filter((_, i) => meta[i].status === 'FRAUD');
      case 'low_battery': return rows.filter((_, i) => meta[i].battery < 20);
      default           : return rows;
    }
  }

  // ── PDF rendering ────────────────────────────────────────────────────────

  private drawHeader(doc: jsPDF, logoB64: string, req: ReportRequest, now: Date): void {
    const W     = doc.internal.pageSize.getWidth();
    const BAND  = 44;
    const [r, g, b] = DOMAIN_COLOR[req.domain];

    doc.setFillColor(12, 18, 34);
    doc.rect(0, 0, W, BAND, 'F');
    doc.setFillColor(r, g, b);
    doc.rect(0, 0, W, 2.5, 'F');

    if (logoB64) {
      try { doc.addImage(`data:image/png;base64,${logoB64}`, 'PNG', 8, 10, 36, 18); }
      catch { /* logo non critique */ }
    }

    doc.setTextColor(255, 255, 255);
    doc.setFontSize(14);
    doc.setFont('helvetica', 'bold');
    doc.text(`Rapport ${DOMAIN_LABEL[req.domain]}`, W / 2, 17, { align: 'center' });

    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(r + 60, g + 60, b + 60);
    doc.text(req.label, W / 2, 26, { align: 'center' });

    doc.setFontSize(8);
    doc.setTextColor(160, 190, 210);
    doc.text(`Généré le ${formatDateFR(now)}`, W / 2, 34, { align: 'center' });

    doc.setFillColor(r, g, b);
    doc.roundedRect(W - 37, 12, 29, 11, 2, 2, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(8);
    doc.setFont('helvetica', 'bold');
    doc.text('ARIA IOIT', W - 22.5, 19, { align: 'center' });

    doc.setDrawColor(r, g, b);
    doc.setLineWidth(0.5);
    doc.line(0, BAND, W, BAND);
  }

  private drawKpiCards(doc: jsPDF, rows: SensorRow[], req: ReportRequest): void {
    const W   = doc.internal.pageSize.getWidth();
    const Y   = 52;
    const PAD = 14;
    const [r, g, b] = DOMAIN_COLOR[req.domain];

    const total   = rows.length;
    const ok      = rows.filter(s => s.rawStatus === 'OK').length;
    const notOk   = rows.filter(s => s.rawStatus !== 'OK').length;
    const lowBat  = rows.filter(s => s.rawBattery < 20).length;

    const kpis: Array<{ label: string; value: number; rgb: [number, number, number] }> = [
      { label: 'Capteurs affichés', value: total,  rgb: [30, 41, 59]    },
      { label: 'Statut OK',         value: ok,     rgb: [16, 185, 129]  },
      { label: 'Anomalies',         value: notOk,  rgb: [r, g, b]       },
      { label: 'Bat. faible (<20%)',value: lowBat, rgb: [168, 85, 247]  },
    ];

    doc.setFontSize(9.5);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(30, 41, 59);
    doc.text('Résumé', PAD, Y - 4);

    const CARD_H = 22;
    const GAP    = 4;
    const CARD_W = (W - 2 * PAD - GAP * (kpis.length - 1)) / kpis.length;

    kpis.forEach((kpi, i) => {
      const x = PAD + i * (CARD_W + GAP);
      doc.setFillColor(248, 250, 252);
      doc.roundedRect(x, Y, CARD_W, CARD_H, 2, 2, 'F');
      doc.setFillColor(...kpi.rgb);
      doc.roundedRect(x, Y, CARD_W, 2.5, 1, 1, 'F');

      doc.setFontSize(13);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(...kpi.rgb);
      doc.text(String(kpi.value), x + CARD_W / 2, Y + 12, { align: 'center' });

      doc.setFontSize(6.5);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(100, 116, 139);
      doc.text(kpi.label, x + CARD_W / 2, Y + 19, { align: 'center' });
    });
  }

  private drawCharts(doc: jsPDF, rows: SensorRow[], req: ReportRequest, startY: number): number {
    if (rows.length === 0) return startY;

    const W          = doc.internal.pageSize.getWidth();
    const PAD        = 14;
    const CHART_H    = 58;
    const GAP        = 6;
    const CHART_W    = (W - 2 * PAD - GAP) / 2;
    const [r, g, b]  = DOMAIN_COLOR[req.domain];

    this.drawStatusBars(doc, PAD,                    startY, CHART_W, CHART_H, rows, [r, g, b]);
    this.drawValueBars (doc, PAD + CHART_W + GAP,    startY, CHART_W, CHART_H, rows, req, [r, g, b]);

    return startY + CHART_H + 10;
  }

  private drawStatusBars(
    doc: jsPDF, x: number, y: number, w: number, h: number,
    rows: SensorRow[], rgb: [number, number, number],
  ): void {
    const ok     = rows.filter(s => s.rawStatus === 'OK').length;
    const notOk  = rows.filter(s => s.rawStatus !== 'OK').length;
    const lowBat = rows.filter(s => s.rawBattery < 20).length;
    const maxVal = Math.max(ok, notOk, lowBat, 1);

    doc.setFillColor(248, 250, 252);
    doc.roundedRect(x, y, w, h, 2, 2, 'F');
    doc.setDrawColor(226, 232, 240);
    doc.setLineWidth(0.3);
    doc.roundedRect(x, y, w, h, 2, 2, 'S');

    doc.setFontSize(7.5);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(30, 41, 59);
    doc.text('Répartition des états', x + w / 2, y + 7, { align: 'center' });

    const BAR_Y   = y + 12;
    const BAR_H   = h - 26;
    const barW    = 14;
    const gap     = 10;
    const totalW  = 3 * barW + 2 * gap;
    const startX  = x + (w - totalW) / 2;

    const bars: Array<{ val: number; rgb: [number, number, number]; label: string }> = [
      { val: ok,    rgb: [16, 185, 129],  label: 'OK'          },
      { val: notOk, rgb,                  label: 'Anomalies'   },
      { val: lowBat,rgb: [168, 85, 247],  label: 'Bat. faible' },
    ];

    doc.setDrawColor(203, 213, 225);
    doc.setLineWidth(0.25);
    doc.line(x + 6, BAR_Y + BAR_H, x + w - 6, BAR_Y + BAR_H);

    bars.forEach((bar, i) => {
      const bx   = startX + i * (barW + gap);
      const bH   = bar.val > 0 ? Math.max((bar.val / maxVal) * BAR_H, 3) : 0;
      const by   = BAR_Y + BAR_H - bH;

      if (bH > 0) {
        doc.setFillColor(...bar.rgb);
        doc.roundedRect(bx, by, barW, bH, 1, 1, 'F');
      }

      doc.setFontSize(7);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(...bar.rgb);
      doc.text(String(bar.val), bx + barW / 2, by - 2, { align: 'center' });

      doc.setFontSize(5.5);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(100, 116, 139);
      doc.text(bar.label, bx + barW / 2, BAR_Y + BAR_H + 5, { align: 'center' });
    });
  }

  private drawValueBars(
    doc: jsPDF, x: number, y: number, w: number, h: number,
    rows: SensorRow[], req: ReportRequest, rgb: [number, number, number],
  ): void {
    doc.setFillColor(248, 250, 252);
    doc.roundedRect(x, y, w, h, 2, 2, 'F');
    doc.setDrawColor(226, 232, 240);
    doc.setLineWidth(0.3);
    doc.roundedRect(x, y, w, h, 2, 2, 'S');

    const colLabel = VALUE_COLUMN_LABEL[req.domain];
    doc.setFontSize(7.5);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(30, 41, 59);
    doc.text(`${colLabel} par capteur`, x + w / 2, y + 7, { align: 'center' });

    const SHOW    = Math.min(rows.length, 7);
    const items   = rows.slice(0, SHOW).map(r => ({
      id : r.id,
      val: parseFloat(r.col3.replace(/[^0-9.-]/g, '')) || 0,
    }));
    const maxVal  = Math.max(...items.map(v => v.val), 1);
    const INNER_X = x + 6;
    const ID_W    = 14;
    const BAR_X   = INNER_X + ID_W;
    const BAR_MAX = w - ID_W - 12;
    const BAR_H   = 5;
    const AREA_H  = h - 16;
    const rowGap  = AREA_H / Math.max(SHOW, 1);
    const topY    = y + 12;

    items.forEach((item, i) => {
      const by    = topY + i * rowGap;
      const barW  = Math.max((item.val / maxVal) * BAR_MAX, item.val > 0 ? 1 : 0);

      doc.setFontSize(5.5);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(71, 85, 105);
      doc.text(item.id, INNER_X, by + BAR_H - 1);

      doc.setFillColor(226, 232, 240);
      doc.roundedRect(BAR_X, by, BAR_MAX, BAR_H, 0.8, 0.8, 'F');

      if (barW > 0) {
        doc.setFillColor(...rgb);
        doc.roundedRect(BAR_X, by, barW, BAR_H, 0.8, 0.8, 'F');
      }

      if (barW > 10) {
        doc.setFontSize(4.5);
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(255, 255, 255);
        doc.text(item.val.toFixed(0), BAR_X + barW - 1, by + BAR_H - 1, { align: 'right' });
      }
    });
  }

  private drawTable(doc: jsPDF, rows: SensorRow[], req: ReportRequest, startY: number): void {
    const W = doc.internal.pageSize.getWidth();
    const [r, g, b] = DOMAIN_COLOR[req.domain];

    const filterLabel = FILTER_LABEL[req.filter];
    doc.setFontSize(9.5);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(30, 41, 59);
    doc.text(`${DOMAIN_LABEL[req.domain]} — ${filterLabel}  (${rows.length} capteur${rows.length > 1 ? 's' : ''})`, 14, startY);
    doc.setDrawColor(r, g, b);
    doc.setLineWidth(0.35);
    doc.line(14, startY + 2, W - 14, startY + 2);

    if (rows.length === 0) {
      doc.setFontSize(9);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(148, 163, 184);
      doc.text('Aucun capteur correspondant à ce critère.', 14, startY + 12);
      return;
    }

    const cols = DOMAIN_COLUMNS[req.domain];

    autoTable(doc, {
      startY: startY + 5,
      head: [cols.map(c => c.header)],
      body: rows.map(row => cols.map(c => row[c.key as keyof SensorRow] ?? '-')),
      headStyles: {
        fillColor   : [12, 18, 34],
        textColor   : [255, 255, 255],
        fontStyle   : 'bold',
        fontSize    : 8,
        halign      : 'center',
        cellPadding : 3,
      },
      bodyStyles: {
        fontSize    : 7.5,
        halign      : 'center',
        textColor   : [30, 41, 59],
        cellPadding : 2.5,
      },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      columnStyles: {
        0: { halign: 'left', fontStyle: 'bold', cellWidth: 14 },
      },
      didParseCell: (data: any) => {
        if (data.section === 'body' && data.column.index === 1) {
          const status = rows[data.row.index]?.rawStatus;
          const [cr, cg, cb] = statusRgb(status);
          data.cell.styles.textColor = [cr, cg, cb];
          data.cell.styles.fontStyle = 'bold';
        }
      },
      margin: { left: 14, right: 14 },
    });
  }

  private drawFooters(doc: jsPDF, req: ReportRequest): void {
    const total = doc.getNumberOfPages();
    const W     = doc.internal.pageSize.getWidth();
    const H     = doc.internal.pageSize.getHeight();

    for (let i = 1; i <= total; i++) {
      doc.setPage(i);
      doc.setFillColor(241, 245, 249);
      doc.rect(0, H - 11, W, 11, 'F');
      doc.setDrawColor(203, 213, 225);
      doc.setLineWidth(0.3);
      doc.line(0, H - 11, W, H - 11);
      doc.setFontSize(7);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(148, 163, 184);
      doc.text(`Rapport ${DOMAIN_LABEL[req.domain]} — ${FILTER_LABEL[req.filter]} | Généré par ARIA IOIT`, 14, H - 4.5);
      doc.text(`Page ${i} / ${total}`, W - 14, H - 4.5, { align: 'right' });
    }
  }

  // ── Logo ─────────────────────────────────────────────────────────────────

  private async fetchLogoBase64(): Promise<string> {
    try {
      const blob = await firstValueFrom(
        this.http.get('assets/logo-bws-dark.png', { responseType: 'blob' })
      );
      return blobToBase64(blob);
    } catch { return ''; }
  }
}

// ── Unified row type ─────────────────────────────────────────────────────────

interface SensorRow {
  id         : string;
  status     : string;
  rawStatus  : string;
  rawBattery : number;
  col3       : string;
  col4       : string;
  col5       : string;
  col6       : string;
  col7       : string;
  updatedAt  : string;
}

// ── Domain column definitions ─────────────────────────────────────────────────

const DOMAIN_COLUMNS: Record<ReportDomain, Array<{ header: string; key: string }>> = {
  water: [
    { header: '#ID',          key: 'id'        },
    { header: 'État',         key: 'status'    },
    { header: 'Index (L)',    key: 'col3'      },
    { header: 'Batterie',     key: 'col4'      },
    { header: 'Fuite',        key: 'col5'      },
    { header: 'Fraude',       key: 'col6'      },
    { header: 'RSSI',         key: 'col7'      },
    { header: 'Dernière MAJ', key: 'updatedAt' },
  ],
  gaz: [
    { header: '#ID',             key: 'id'        },
    { header: 'État',            key: 'status'    },
    { header: 'Index',           key: 'col3'      },
    { header: 'Débit moy (m³/min)', key: 'col4'  },
    { header: 'Batterie',        key: 'col5'      },
    { header: 'Fuite',           key: 'col6'      },
    { header: 'RSSI',            key: 'col7'      },
    { header: 'Dernière MAJ',    key: 'updatedAt' },
  ],
  electricity: [
    { header: '#ID',          key: 'id'        },
    { header: 'État',         key: 'status'    },
    { header: 'Conso L1(kWh)',key: 'col3'      },
    { header: 'Conso L2(kWh)',key: 'col4'      },
    { header: 'Conso L3(kWh)',key: 'col5'      },
    { header: 'cos φ moy',   key: 'col6'       },
    { header: 'THD moy',     key: 'col7'       },
    { header: 'Dernière MAJ', key: 'updatedAt' },
  ],
  fuel: [
    { header: '#ID',           key: 'id'        },
    { header: 'État',          key: 'status'    },
    { header: 'Conso (L)',     key: 'col3'      },
    { header: 'Niveau (%)',    key: 'col4'      },
    { header: 'Kilométrage',   key: 'col5'      },
    { header: 'Effic. (L/100)',key: 'col6'      },
    { header: 'Coût (TND)',    key: 'col7'      },
    { header: 'Dernière MAJ',  key: 'updatedAt' },
  ],
};

const VALUE_COLUMN_LABEL: Record<ReportDomain, string> = {
  water      : 'Index (L)',
  gaz        : 'Index',
  electricity: 'Conso L1 (kWh)',
  fuel       : 'Conso (L)',
};

const FILTER_LABEL: Record<ReportFilter, string> = {
  all        : 'Tous les capteurs',
  active     : 'Capteurs actifs',
  inactive   : 'Capteurs inactifs',
  alert      : 'Capteurs en alerte',
  leak       : 'Fuites détectées',
  fraud      : 'Fraudes détectées',
  low_battery: 'Batterie faible',
};

// ── Domain → SensorRow mappers ────────────────────────────────────────────────

function waterToRow(s: RtWmDto): SensorRow {
  return {
    id        : `#${s.idDevice}`,
    status    : statusLabel(s.status),
    rawStatus : s.status,
    rawBattery: normalizeBattery(s.batteryLevel),
    col3      : s.wmIndex.toFixed(1),
    col4      : `${normalizeBattery(s.batteryLevel).toFixed(0)}%`,
    col5      : s.leak  ? '⚠ OUI' : 'non',
    col6      : s.fraud ? '⚠ OUI' : 'non',
    col7      : `${s.rssi} dBm`,
    updatedAt : shortDate(s.date),
  };
}

function gazToRow(s: RtGmDto): SensorRow {
  return {
    id        : `#${s.idDevice}`,
    status    : statusLabel(s.status),
    rawStatus : s.status,
    rawBattery: normalizeBattery(s.batteryLevel),
    col3      : s.index.toFixed(1),
    col4      : s.avgDebitPerMin.toFixed(3),
    col5      : `${normalizeBattery(s.batteryLevel).toFixed(0)}%`,
    col6      : s.leak ? '⚠ OUI' : 'non',
    col7      : `${s.rssi} dBm`,
    updatedAt : shortDate(s.date),
  };
}

function elecToRow(s: RtEnPDto): SensorRow {
  const avgCosfi = ((s.cosfiL1 + s.cosfiL2 + s.cosfiL3) / 3).toFixed(2);
  const avgThd   = ((s.thdL1   + s.thdL2   + s.thdL3)   / 3).toFixed(1);
  return {
    id        : `#${s.idDevice}`,
    status    : statusLabel(s.status),
    rawStatus : s.status,
    rawBattery: normalizeBattery(s.batteryLevel),
    col3      : s.enL1.toFixed(2),
    col4      : s.enL2.toFixed(2),
    col5      : s.enL3.toFixed(2),
    col6      : avgCosfi,
    col7      : `${avgThd}%`,
    updatedAt : shortDate(s.date),
  };
}

function fuelToRow(s: FuelLatestDto): SensorRow {
  return {
    id        : `#${s.deviceId}`,
    status    : statusLabel(s.status),
    rawStatus : s.status,
    rawBattery: 100,
    col3      : s.consumptionLiters.toFixed(1),
    col4      : `${s.consumptionPercentage.toFixed(0)}%`,
    col5      : `${s.mileageKm.toFixed(0)} km`,
    col6      : s.efficiencyL100km.toFixed(1),
    col7      : s.costTnd.toFixed(2),
    updatedAt : shortDate(s.date),
  };
}

// ── Pure helpers ──────────────────────────────────────────────────────────────

function pad(n: number): string { return String(n).padStart(2, '0'); }

function shortDate(d: string): string {
  const dt = new Date(d);
  return `${pad(dt.getDate())}/${pad(dt.getMonth() + 1)}/${dt.getFullYear()} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}

function formatDateFR(d: Date): string {
  return d.toLocaleDateString('fr-FR', {
    weekday: 'long', year: 'numeric', month: 'long',
    day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function statusLabel(s: string): string {
  return ({ OK: 'OK', LEAK: 'FUITE', FRAUD: 'FRAUDE', ALERT: 'ALERTE',
            HIGH_CONSO: 'SURCONSO', LOW_EFFICIENCY: 'INEFFIC.',
            LOW_BATTERY: 'BAT. FAIBLE', HIGH_THD: 'THD ÉLEVÉ',
            LOW_COSFI: 'cosφ FAIBLE' } as Record<string, string>)[s] ?? s;
}

function statusRgb(s: string): [number, number, number] {
  return ({
    OK             : [16, 185, 129],
    LEAK           : [239, 68, 68],
    FRAUD          : [245, 158, 11],
    ALERT          : [245, 158, 11],
    HIGH_CONSO     : [239, 68, 68],
    LOW_EFFICIENCY : [245, 158, 11],
    LOW_BATTERY    : [168, 85, 247],
    HIGH_THD       : [239, 68, 68],
    LOW_COSFI      : [245, 158, 11],
  } as Record<string, [number, number, number]>)[s] ?? [100, 116, 139];
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = () => resolve((reader.result as string).split(',')[1] ?? '');
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}
