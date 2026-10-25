import { Component, ViewChild, ElementRef } from '@angular/core';
import { Observable, forkJoin } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import {
  GazService, GazSummaryDto, GazAlertDto, GazChartDto, RtGmDto
} from '../services/gaz.service';
import { ChartConfiguration } from 'chart.js';
import { CHART_BASE } from '../shared/chart-setup';
import { DateRange, DomainDashboardBase, MODAL_CHART } from '../shared/domain-dashboard.base';

// ── Palette centralisée ──────────────────────────────────────
const GP = {
  ...CHART_BASE,
  main:     '#0d9488',
  mainDim:  'rgba(13,148,136,0.15)',
  cyan:     '#06b6d4',
  cyanDim:  'rgba(6,182,212,0.15)',
  teal:     '#0f766e',
  tealDim:  'rgba(15,118,110,0.15)',
  green:    '#10b981',
  greenDim: 'rgba(16,185,129,0.15)',
  lime:     '#22c55e',
  blue:     '#0369a1',
  blueDim:  'rgba(3,105,161,0.15)',
  red:      '#e74c3c',
};

interface KpiCard {
  label: string; value: string; unit: string;
  trend: string; trendUp: boolean | null;
  color: 'gaz' | 'green' | 'orange' | 'red' | 'cyan';
  icon: string;
}

interface ChartBar {
  label: string;
  conso: number;
  co2: number;
  debit: number;
}

interface GazData {
  summaries: GazSummaryDto[];
  alerts:    GazAlertDto[];
  rt:        RtGmDto[];
}

type ChartModalType = 'evolution' | 'bar';

@Component({
  selector: 'app-gaz',
  templateUrl: './gaz.component.html',
  styleUrls: ['./gaz.component.scss']
})
export class GazComponent extends DomainDashboardBase<GazSummaryDto, GazAlertDto, GazData> {

  @ViewChild('gLineCanvas')      gLineCanvas!:         ElementRef<HTMLCanvasElement>;
  @ViewChild('gDonutCanvas')     gDonutCanvas!:        ElementRef<HTMLCanvasElement>;
  @ViewChild('gBarCanvas')       gBarCanvas!:          ElementRef<HTMLCanvasElement>;
  @ViewChild('gFlowCanvas')      gFlowCanvas!:         ElementRef<HTMLCanvasElement>;
  @ViewChild('gGaugeCanvas')     gGaugeCanvas!:        ElementRef<HTMLCanvasElement>;
  @ViewChild('gDailyCanvas')     gDailyCanvas!:        ElementRef<HTMLCanvasElement>;
  @ViewChild('modalChartCanvas') modalChartCanvasRef!: ElementRef<HTMLCanvasElement>;

  protected override readonly modalBackdropClass = 'gaz-chart-modal-backdrop';
  protected override readonly insightLabel = 'Gaz';

  rtData: RtGmDto[]          = [];
  chart:  GazChartDto | null = null;

  kpiCards:  KpiCard[]  = [];
  chartBars: ChartBar[] = [];

  totalConso = 0;
  totalCo2   = 0;
  totalCost  = 0;
  alertCount = 0;
  avgDebit   = 0;
  leakCount  = 0;

  chartModalType: ChartModalType = 'evolution';
  chartModalTitle = '';
  dailyChartSub   = '';

  constructor(private gazSvc: GazService) { super(); }

  protected override get modalCanvas() { return this.modalChartCanvasRef; }

  protected override insightPrompts(p: number): Record<string, string> {
    const consoM3 = (this.totalConso / 1000).toFixed(2);
    return {
      summary: `Analyse les statistiques Gaz (${p}j) :\n` +
        `Consommation : ${consoM3} m³ (${this.totalConso.toFixed(0)} L)\n` +
        `CO₂ émis : ${this.totalCo2.toFixed(1)} kgCO₂ | Coût : ${this.totalCost.toFixed(2)} TND\n` +
        `Débit moyen : ${this.avgDebit.toFixed(2)} m³/h | Alertes : ${this.alertCount}\n` +
        `Capteurs actifs : ${this.summaries.length}\n` +
        `Est-ce normal, préoccupant ou excellent ? Réponds en 2-3 lignes.`,

      stats: `Analyse les graphiques statistiques Gaz (${p}j) :\n` +
        `Total consommé : ${consoM3} m³ sur ${this.summaries.length} capteur(s)\n` +
        `CO₂ : ${this.totalCo2.toFixed(1)} kg | Coût : ${this.totalCost.toFixed(2)} TND\n` +
        `Identifie les anomalies de débit et pics de consommation.`,

      quality: `Analyse le résumé par capteur Gaz (${p}j) :\n` +
        `${this.summaries.length} capteur(s) · Débit moyen : ${this.avgDebit.toFixed(2)} m³/h · Alertes : ${this.alertCount}\n` +
        `Donne un diagnostic qualité du réseau gaz.`,

      alerts: `Analyse les alertes gaz actives (${p}j) :\n` +
        `Total : ${this.alertCount} alerte(s) · Capteurs : ${this.summaries.length}\n` +
        `Quelles sont les actions prioritaires à mener ?`,
    };
  }

  // ══════════════════════════════════════════════════════════════
  // CHARGEMENT
  // ══════════════════════════════════════════════════════════════

  protected override dateRangeFor(days: number): DateRange {
    return this.gazSvc.getLastNDaysRange(days);
  }

  protected override fetchData({ from, to }: DateRange): Observable<GazData> {
    return forkJoin({
      summaries: this.gazSvc.getAllSummaries(from, to),
      alerts:    this.gazSvc.getAlerts(),
      rt:        this.gazSvc.getRealTimeAll()
    });
  }

  protected override applyData(data: GazData): void {
    this.rtData = data.rt;
  }

  protected override afterDataLoaded({ from, to }: DateRange): void {
    const firstDevice = this.summaries[0]?.idDevice;
    if (!firstDevice) { this.buildChartBars(); return; }

    const loader = this.selectedPeriod <= 30
      ? this.gazSvc.getDailyChart(firstDevice, from, to)
      : this.gazSvc.getMonthlyChart(firstDevice, from, to);

    loader.pipe(takeUntil(this.destroy$)).subscribe((result: any) => {
      if (result && 'points' in result) {
        this.chart = result as GazChartDto;
      } else if (Array.isArray(result)) {
        this.chart = {
          points: result.map((r: any) => ({
            label: this.fmtDateLabel(r.date ?? ''),
            conso: r.conso ?? 0,
            debit: r.avgDebitPerMin ?? 0,
            co2:   (r.conso ?? 0) / 1000 * 2.04
          })),
          totalConso: result.reduce((s: number, r: any) => s + (r.conso ?? 0), 0),
          totalCo2: 0, totalCost: 0
        };
      }
      this.buildChartBars();
    });
  }

  protected override refreshLabels(): void {
    const t = this.translate;
    this.chartModalTitle = this.chartModalType === 'evolution'
      ? t.instant('ENERGY.EVOLUTION') + ' — m³'
      : t.instant('ENERGY.CO2_COST_PER_METER');
    this.dailyChartSub = this.chartBars.length > 0
      ? t.instant('ENERGY.DAILY_L')
      : t.instant('ENERGY.SUMMARY_BY_METER');
  }

  // ══════════════════════════════════════════════════════════════
  // DONNÉES DÉRIVÉES
  // ══════════════════════════════════════════════════════════════

  protected override buildKpi(): void {
    this.totalConso = this.summaries.reduce((s, d) => s + (d.totalConsoM ?? 0), 0);
    this.totalCo2   = this.summaries.reduce((s, d) => s + (d.co2Kg       ?? 0), 0);
    this.totalCost  = this.summaries.reduce((s, d) => s + (d.costTnd     ?? 0), 0);
    this.alertCount = this.alerts.length;
    this.avgDebit   = this.rtData.length
      ? this.rtData.reduce((s, r) => s + (r.avgDebitPerMin ?? 0), 0) / this.rtData.length
      : (this.summaries[0]?.avgDebit ?? 0);

    const trend      = this.summaries[0]?.trend ?? '+0.0%';
    const criticals  = this.countBySeverity('CRITICAL');
    this.leakCount   = this.rtData.filter(r => r.leak > 0).length;
    const leakCnt    = this.leakCount;
    const t          = this.translate;

    this.kpiCards = [
      {
        label: t.instant('GAZ.KPI_CONSUMPTION'), value: this.fmt(this.totalConso / 1000, 2),
        unit: t.instant('GAZ.KPI_CONSO_UNIT'), trend, trendUp: this.isTrendUp(trend),
        color: 'gaz',
        icon: '<svg viewBox="0 0 24 24"><path d="M13.5.67s.74 2.65.74 4.8c0 2.06-1.35 3.73-3.41 3.73-2.07 0-3.63-1.67-3.63-3.73l.03-.36C5.21 7.51 4 10.62 4 14c0 4.42 3.58 8 8 8s8-3.58 8-8C20 8.61 17.41 3.8 13.5.67z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('GAZ.KPI_CO2'), value: this.fmt(this.totalCo2, 1),
        unit: t.instant('GAZ.KPI_CO2_UNIT'), trend, trendUp: this.isTrendUp(trend),
        color: 'orange',
        icon: '<svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('GAZ.KPI_COST'), value: this.fmt(this.totalCost, 2),
        unit: 'TND', trend: t.instant('GAZ.KPI_COST_RATE'), trendUp: null,
        color: 'green',
        icon: '<svg viewBox="0 0 24 24"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('GAZ.KPI_ALERTS'), value: String(this.alertCount),
        unit: t.instant('GAZ.KPI_ALERTS_UNIT'),
        trend: this.alertCount === 0
          ? t.instant('GAZ.STATUS_NO_ALERT')
          : t.instant('GAZ.STATUS_CRITICALS', { n: criticals }),
        trendUp: this.alertCount > 0,
        color: this.alertCount > 0 ? 'red' : 'green',
        icon: '<svg viewBox="0 0 24 24"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('GAZ.KPI_DEBIT'), value: this.avgDebit.toFixed(2),
        unit: 'L/min', trend: '—', trendUp: null,
        color: 'cyan',
        icon: '<svg viewBox="0 0 24 24"><path d="M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('GAZ.KPI_LEAKS'), value: String(leakCnt),
        unit: t.instant('GAZ.KPI_LEAKS_UNIT'),
        trend: leakCnt > 0 ? t.instant('GAZ.LEAKS_WARN_SHORT') : t.instant('GAZ.LEAKS_NONE'),
        trendUp: leakCnt > 0,
        color: leakCnt > 0 ? 'red' : 'green',
        icon: '<svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" fill="currentColor"/></svg>'
      }
    ];
    this.buildKpiDefs();
  }

  private buildChartBars(): void {
    const pts = this.chart?.points ?? [];
    if (!pts.length) {
      this.chartBars    = [];
      this.dailyChartSub = this.translate.instant('ENERGY.SUMMARY_BY_METER');
      return;
    }
    this.chartBars = pts.map(p => ({
      label: p.label,
      conso: p.conso ?? 0,
      co2:   p.co2   ?? 0,
      debit: p.debit ?? 0
    }));
    this.dailyChartSub = this.translate.instant('ENERGY.DAILY_L');
    this.scheduleChartsRender();
  }

  protected override buildCharts(): void {
    this.buildDailyChart();
    this.buildGazLine();
    this.buildGazDonut();
    this.buildGazBar();
    this.buildGazFlowChart();
    this.buildGazGauge();
  }

  // ══════════════════════════════════════════════════════════════
  // CHARTS INLINE
  // ══════════════════════════════════════════════════════════════

  private buildGazLine(): void {
    if (!this.gLineCanvas) return;
    const pts = this.chart?.points ?? [];
    const cfg: ChartConfiguration<'line'> = {
      type: 'line',
      data: {
        labels: pts.map(p => p.label),
        datasets: [{
          label: 'm³',
          data:   pts.map(p => +((p.conso ?? 0) / 1000).toFixed(3)),
          borderColor:     GP.main,
          backgroundColor: GP.mainDim,
          borderWidth: 2, tension: 0.4, fill: true,
          pointRadius:          pts.length > 20 ? 0 : 3,
          pointBackgroundColor: GP.main
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: GP.tooltip, titleColor: GP.main, bodyColor: '#fff',
            callbacks: { label: (ctx: any) => ` ${ctx.parsed.y} m³` }
          }
        },
        scales: {
          x: { grid: { color: GP.grid }, ticks: { color: GP.text, maxTicksLimit: 8, font: { size: 10 } } },
          y: { grid: { color: GP.grid }, ticks: { color: GP.text, font: { size: 10 }, callback: (v: any) => v + ' m³' }, beginAtZero: true }
        }
      }
    };
    this.renderChart('line', this.gLineCanvas, cfg);
  }

  private buildGazDonut(): void {
    if (!this.gDonutCanvas || !this.summaries.length) return;
    const colors = [GP.main, GP.cyan, GP.green, GP.teal, GP.blue, GP.lime];
    const cfg: ChartConfiguration<'doughnut'> = {
      type: 'doughnut',
      data: {
        labels:   this.summaries.map(s => `#${s.idDevice}`),
        datasets: [{
          data:            this.summaries.map(s => +((s.totalConsoM ?? 0) / 1000).toFixed(3)),
          backgroundColor: this.summaries.map((_, i) => colors[i % colors.length] + '99'),
          borderColor:     this.summaries.map((_, i) => colors[i % colors.length]),
          borderWidth: 2, hoverOffset: 6
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '68%',
        plugins: {
          legend: { position: 'bottom', labels: { color: GP.text, font: { size: 10 }, padding: 10, boxWidth: 10 } },
          tooltip: {
            backgroundColor: GP.tooltip, titleColor: GP.main, bodyColor: '#fff',
            callbacks: { label: (ctx: any) => ` ${ctx.label} : ${ctx.parsed} m³` }
          }
        }
      }
    };
    this.renderChart('donut', this.gDonutCanvas, cfg);
  }

  private buildGazBar(): void {
    if (!this.gBarCanvas || !this.summaries.length) return;
    const cfg: ChartConfiguration<'bar'> = {
      type: 'bar',
      data: {
        labels:   this.summaries.map(s => `#${s.idDevice}`),
        datasets: [
          {
            label:           this.translate.instant('ENERGY.CO2_KG'),
            data:            this.summaries.map(s => +(s.co2Kg    ?? 0).toFixed(2)),
            backgroundColor: GP.cyanDim, borderColor: GP.cyan,
            borderWidth: 1.5, borderRadius: 4
          },
          {
            label:           this.translate.instant('ENERGY.COST_TND_LABEL'),
            data:            this.summaries.map(s => +(s.costTnd  ?? 0).toFixed(2)),
            backgroundColor: GP.greenDim,  borderColor: GP.green,
            borderWidth: 1.5, borderRadius: 4
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: GP.text, font: { size: 10 }, boxWidth: 10 } },
          tooltip: { backgroundColor: GP.tooltip, titleColor: '#fff', bodyColor: GP.text }
        },
        scales: {
          x: { grid: { color: GP.grid }, ticks: { color: GP.text, font: { size: 10 } } },
          y: { grid: { color: GP.grid }, ticks: { color: GP.text, font: { size: 10 } }, beginAtZero: true }
        }
      }
    };
    this.renderChart('bar', this.gBarCanvas, cfg);
  }

  private buildGazFlowChart(): void {
    if (!this.gFlowCanvas) return;
    const pts = this.chart?.points ?? [];
    if (!pts.length) { this.destroyChart('flow'); return; }
    const labels = pts.map(p => p.label);
    const avg    = pts.map(p => +(p.debit ?? 0).toFixed(3));
    const min    = avg.map(v => +(v * 0.65).toFixed(3));
    const max    = avg.map(v => +(v * 1.35).toFixed(3));

    this.renderChart('flow', this.gFlowCanvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: this.translate.instant('GAZ.COL_DEBIT_MAX'),
            data: max,
            borderColor: 'rgba(13,148,136,0.45)',
            backgroundColor: 'rgba(13,148,136,0.08)',
            borderWidth: 1, borderDash: [4, 3] as any,
            pointRadius: 0, tension: 0.4, fill: '+1' as any
          },
          {
            label: this.translate.instant('GAZ.COL_DEBIT_MOY'),
            data: avg,
            borderColor: GP.main, backgroundColor: GP.mainDim,
            borderWidth: 2,
            pointRadius: pts.length > 20 ? 0 : 3,
            pointBackgroundColor: GP.main,
            tension: 0.4, fill: false as any
          },
          {
            label: this.translate.instant('GAZ.COL_DEBIT_MIN'),
            data: min,
            borderColor: 'rgba(13,148,136,0.45)',
            backgroundColor: 'transparent',
            borderWidth: 1, borderDash: [4, 3] as any,
            pointRadius: 0, tension: 0.4, fill: false as any
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { color: GP.text, font: { size: 10 }, boxWidth: 10 } },
          tooltip: {
            backgroundColor: GP.tooltip, borderColor: GP.mainDim, borderWidth: 1,
            titleColor: GP.main, bodyColor: '#fff',
            callbacks: { label: (ctx: any) => ` ${ctx.dataset.label}: ${ctx.parsed.y} L/min` }
          }
        },
        scales: {
          x: { grid: { color: GP.grid }, ticks: { color: GP.text, maxTicksLimit: 8, font: { size: 10 } } },
          y: { grid: { color: GP.grid }, ticks: { color: GP.text, font: { size: 10 }, callback: (v: any) => v + ' L/min' }, beginAtZero: true }
        }
      }
    } as any);
  }

  private buildGazGauge(): void {
    if (!this.gGaugeCanvas) return;
    const maxDebit  = 100;
    const ratio     = Math.min(Math.max(this.avgDebit / maxDebit, 0), 1);
    const remain    = 1 - ratio;
    const color     = ratio < 0.3 ? GP.green : ratio < 0.7 ? GP.main : GP.cyan;
    this.renderChart('gauge', this.gGaugeCanvas, {
      type: 'doughnut',
      data: {
        datasets: [{
          data:            [ratio, remain],
          backgroundColor: [color + 'cc', 'rgba(255,255,255,0.05)'],
          borderColor:     [color,         'transparent'],
          borderWidth:     [2, 0],
          hoverOffset:     0
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        circumference: 180, rotation: -90, cutout: '72%',
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        animation: { animateRotate: true, duration: 900 }
      }
    } as any);
  }

  private buildDailyChart(): void {
    if (!this.gDailyCanvas) return;

    const pts = this.chartBars;
    const useSummaries = !pts.length && this.summaries.length > 0;
    if (!pts.length && !useSummaries) { this.destroyChart('daily'); return; }

    const isTimeSeries = pts.length > 0;
    const meterColors  = [GP.main, GP.green, GP.teal, GP.cyan, GP.lime];

    const datasets: any[] = isTimeSeries
      ? [{
          label: 'm³',
          data:            pts.map(b => +((b.conso ?? 0) / 1000).toFixed(3)),
          backgroundColor: 'rgba(13,148,136,0.45)',
          borderColor:     GP.main,
          borderWidth:     1.5,
          borderRadius:    4,
          borderSkipped:   false
        }]
      : [{
          label: 'm³',
          data:            this.summaries.map(s => +((s.totalConsoM ?? 0) / 1000).toFixed(2)),
          backgroundColor: this.summaries.map((_, i) => meterColors[i % meterColors.length] + '99'),
          borderColor:     this.summaries.map((_, i) => meterColors[i % meterColors.length]),
          borderWidth:     1.5,
          borderRadius:    5
        }];

    const labels = isTimeSeries
      ? pts.map(b => b.label)
      : this.summaries.map(s => `Compteur #${s.idDevice}`);

    this.renderChart('daily', this.gDailyCanvas, {
      type: 'bar',
      data: { labels, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 700 } as any,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: GP.tooltip,
            titleColor: '#e6eaf4',
            bodyColor:  'rgba(230,234,244,0.75)',
            footerColor: GP.main,
            borderColor: 'rgba(13,148,136,0.35)',
            borderWidth: 1,
            padding: { top: 10, bottom: 10, left: 14, right: 14 },
            cornerRadius: 10,
            titleFont: { size: 12, weight: 'bold', family: 'Inter, sans-serif' },
            bodyFont:  { size: 12, family: 'Inter, sans-serif' },
            callbacks: {
              title: (items: any[]) => items[0]?.label ?? '',
              label: (ctx: any) => {
                const val = ctx.parsed.y.toLocaleString(this.locale, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
                return `  ${ctx.dataset.label} : ${val} m³`;
              }
            }
          }
        },
        scales: {
          x: {
            grid:  { color: GP.grid },
            ticks: { color: GP.text, maxTicksLimit: 14, font: { size: 10, family: 'Inter, sans-serif' } }
          },
          y: {
            grid:  { color: GP.grid },
            ticks: {
              color: GP.text, font: { size: 10, family: 'Inter, sans-serif' },
              callback: (v: any) => v + ' m³', maxTicksLimit: 8
            },
            beginAtZero: true
          }
        }
      } as any
    } as any);
  }

  // ══════════════════════════════════════════════════════════════
  // MODAL CHART — Évolution & CO₂/Coût
  // ══════════════════════════════════════════════════════════════

  openChartModal(type: ChartModalType): void {
    this.chartModalType = type;
    this.refreshLabels();
    this.showChartModal();
  }

  protected override buildModalChart(canvas: HTMLCanvasElement): void {
    if (this.chartModalType === 'evolution') {
      this.buildModalEvolution(canvas);
    } else {
      this.buildModalBar(canvas);
    }
  }

  private buildModalEvolution(canvas: HTMLCanvasElement): void {
    const pts = this.chart?.points ?? [];
    if (!pts.length) return;

    const ctx = canvas.getContext('2d')!;
    const h   = canvas.parentElement?.clientHeight || 320;
    const gr  = ctx.createLinearGradient(0, 0, 0, h);
    gr.addColorStop(0,   'rgba(13,148,136,0.35)');
    gr.addColorStop(0.6, 'rgba(13,148,136,0.08)');
    gr.addColorStop(1,   'rgba(13,148,136,0.00)');

    this.renderChart(MODAL_CHART, ctx, {
      type: 'line',
      data: {
        labels:   pts.map(p => p.label),
        datasets: [{
          label:                'm³',
          data:                 pts.map(p => +((p.conso ?? 0) / 1000).toFixed(3)),
          borderColor:          GP.main,
          backgroundColor:      gr,
          borderWidth:          2.5,
          tension:              0.42,
          fill:                 true,
          pointRadius:          pts.length > 30 ? 0 : 4,
          pointHoverRadius:     8,
          pointBackgroundColor: GP.main,
          pointBorderColor:     'rgba(13,148,136,0.25)',
          pointBorderWidth:     2,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 600 } as any,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: GP.tooltip, titleColor: GP.main, bodyColor: '#fff',
            borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1,
            padding: 14, cornerRadius: 12,
            callbacks: {
              label: (ctx: any) => ` ${ctx.parsed.y.toLocaleString(this.locale, { maximumFractionDigits: 3 })} m³`
            }
          }
        },
        scales: {
          x: {
            grid:  { color: GP.grid },
            ticks: { color: GP.text, maxTicksLimit: 12, font: { size: 10, family: 'Inter, sans-serif' } }
          },
          y: {
            grid:  { color: GP.grid },
            ticks: { color: GP.text, font: { size: 10, family: 'Inter, sans-serif' }, padding: 8 },
            beginAtZero: true,
            title: { display: true, text: 'm³', color: 'rgba(255,255,255,0.3)', font: { size: 10 } }
          }
        }
      }
    });
  }

  private buildModalBar(canvas: HTMLCanvasElement): void {
    if (!this.summaries.length) return;

    this.renderChart(MODAL_CHART, canvas, {
      type: 'bar',
      data: {
        labels:   this.summaries.map(s => `Compteur #${s.idDevice}`),
        datasets: [
          {
            label:                   this.translate.instant('ENERGY.CO2_KG'),
            data:                    this.summaries.map(s => +(s.co2Kg   ?? 0).toFixed(2)),
            backgroundColor:         'rgba(6,182,212,0.2)',
            borderColor:             GP.cyan,
            borderWidth:             2,
            borderRadius:            6,
            hoverBackgroundColor:    'rgba(6,182,212,0.4)'
          },
          {
            label:                   this.translate.instant('ENERGY.COST_TND_LABEL'),
            data:                    this.summaries.map(s => +(s.costTnd ?? 0).toFixed(2)),
            backgroundColor:         'rgba(16,185,129,0.2)',
            borderColor:             GP.green,
            borderWidth:             2,
            borderRadius:            6,
            hoverBackgroundColor:    'rgba(16,185,129,0.4)'
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 600 } as any,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            display:  true,
            position: 'top',
            labels:   { color: GP.text, font: { size: 11, family: 'Inter, sans-serif' }, boxWidth: 10, boxHeight: 10, padding: 16, usePointStyle: true }
          },
          tooltip: {
            backgroundColor: GP.tooltip, titleColor: '#fff', bodyColor: GP.text,
            borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1,
            padding: 14, cornerRadius: 12,
            callbacks: {
              label: (ctx: any) => {
                const unit = ctx.datasetIndex === 0 ? ' kgCO₂' : ' TND';
                return ` ${ctx.dataset.label}: ${ctx.parsed.y.toLocaleString(this.locale, { maximumFractionDigits: 2 })}${unit}`;
              }
            }
          }
        },
        scales: {
          x: {
            grid:  { color: GP.grid },
            ticks: { color: GP.text, font: { size: 10, family: 'Inter, sans-serif' } }
          },
          y: {
            grid:  { color: GP.grid },
            ticks: { color: GP.text, font: { size: 10, family: 'Inter, sans-serif' }, padding: 8 },
            beginAtZero: true
          }
        }
      }
    });
  }

  // ══════════════════════════════════════════════════════════════
  // KPI DETAIL PANEL
  // ══════════════════════════════════════════════════════════════

  private buildKpiDefs(): void {
    const t         = this.translate;
    const criticals = this.countBySeverity('CRITICAL');
    const lc        = this.leakCount;
    this.setKpiDefs({
      conso: {
        title:          t.instant('GAZ.KPI_CONSUMPTION') + ' (m³)',
        accent:         '#0d9488',
        value:          this.fmt(this.totalConso / 1000, 2),
        unit:           'm³',
        definition:     t.instant('GAZ.DEF_CONSO'),
        why:            t.instant('GAZ.WHY_CONSO'),
        threshold: null, thresholdLabel: null,
        gaugePercent:   Math.min(this.totalConso / 1000 / ((this.summaries.length * 1000) || 1) * 100, 100),
        status: null, statusLabel: null,
        recommendations: [t.instant('GAZ.KPI_REC_CONSO_1'), t.instant('GAZ.KPI_REC_CONSO_2'), t.instant('GAZ.KPI_REC_CONSO_3')],
        devices: this.summaries.map(s => ({ id: s.idDevice, val: ((s.totalConsoM ?? 0) / 1000).toFixed(2), unit: 'm³', ok: true, badge: s.alertCount > 0 ? 'ALERTE' : 'OK' }))
      },
      co2: {
        title:          t.instant('GAZ.KPI_CO2') + ' (kgCO₂)',
        accent:         '#06b6d4',
        value:          this.fmt(this.totalCo2, 2),
        unit:           'kgCO₂',
        definition:     t.instant('GAZ.DEF_CO2'),
        why:            t.instant('GAZ.WHY_CO2'),
        threshold: null, thresholdLabel: t.instant('GAZ.FACTOR_CO2'),
        gaugePercent:   Math.min(this.totalCo2 / ((this.summaries.length * 2000) || 1) * 100, 100),
        status: null, statusLabel: null,
        recommendations: [t.instant('GAZ.KPI_REC_CO2_1'), t.instant('GAZ.KPI_REC_CO2_2'), t.instant('GAZ.KPI_REC_CO2_3')],
        devices: this.summaries.map(s => ({ id: s.idDevice, val: (s.co2Kg ?? 0).toFixed(2), unit: 'kg', ok: true, badge: s.alertCount > 0 ? 'ALERTE' : 'OK' }))
      },
      cost: {
        title:          t.instant('GAZ.KPI_COST') + ' (TND)',
        accent:         '#10b981',
        value:          this.fmt(this.totalCost, 2),
        unit:           'TND',
        definition:     t.instant('GAZ.DEF_COST'),
        why:            t.instant('GAZ.WHY_COST'),
        threshold: null, thresholdLabel: t.instant('GAZ.FACTOR_COST'),
        gaugePercent:   Math.min(this.totalCost / ((this.summaries.length * 500) || 1) * 100, 100),
        status: null, statusLabel: null,
        recommendations: [t.instant('GAZ.KPI_REC_COST_1'), t.instant('GAZ.KPI_REC_COST_2'), t.instant('GAZ.KPI_REC_COST_3')],
        devices: this.summaries.map(s => ({ id: s.idDevice, val: (s.costTnd ?? 0).toFixed(2), unit: 'TND', ok: true, badge: s.alertCount > 0 ? 'ALERTE' : 'OK' }))
      },
      alerts: {
        title:          t.instant('GAZ.KPI_ALERTS'),
        accent:         '#ef4444',
        value:          String(this.alertCount),
        unit:           t.instant('COMMON.ALERTS'),
        definition:     t.instant('GAZ.DEF_ALERTS'),
        why:            t.instant('GAZ.WHY_ALERTS'),
        threshold: 0, thresholdLabel: t.instant('GAZ.THRESHOLD_ALERTS'),
        gaugePercent:   Math.min(this.alertCount / 10 * 100, 100),
        status:         this.alertCount === 0 ? 'ok' : 'warn',
        statusLabel:    this.alertCount === 0 ? t.instant('GAZ.STATUS_NO_ALERT') : t.instant('GAZ.STATUS_CRITICALS', { n: criticals }),
        recommendations: [t.instant('GAZ.KPI_REC_ALERTS_1'), t.instant('GAZ.KPI_REC_ALERTS_2'), t.instant('GAZ.KPI_REC_ALERTS_3')],
        devices: this.alerts.slice(0, 10).map(a => ({ id: a.idDevice, val: a.type, unit: '', ok: a.severity !== 'CRITICAL', badge: a.severity }))
      },
      debit: {
        title:          t.instant('GAZ.KPI_DEBIT') + ' (L/min)',
        accent:         '#00bcd4',
        value:          this.avgDebit.toFixed(2),
        unit:           'L/min',
        definition:     t.instant('GAZ.DEF_DEBIT'),
        why:            t.instant('GAZ.WHY_DEBIT'),
        threshold: null, thresholdLabel: null,
        gaugePercent:   Math.min(this.avgDebit / 100 * 100, 100),
        status: null, statusLabel: null,
        recommendations: [t.instant('GAZ.KPI_REC_DEBIT_1'), t.instant('GAZ.KPI_REC_DEBIT_2'), t.instant('GAZ.KPI_REC_DEBIT_3')],
        devices: this.rtData.slice(0, 10).map(r => ({ id: r.idDevice, val: (r.avgDebitPerMin ?? 0).toFixed(2), unit: 'L/min', ok: r.leak === 0, badge: r.status ?? 'OK' }))
      },
      leaks: {
        title:          t.instant('GAZ.KPI_LEAKS'),
        accent:         lc > 0 ? '#ef4444' : '#10b981',
        value:          String(lc),
        unit:           t.instant('COMMON.METERS'),
        definition:     t.instant('GAZ.DEF_LEAKS'),
        why:            t.instant('GAZ.WHY_LEAKS'),
        threshold: 0, thresholdLabel: t.instant('GAZ.THRESHOLD_LEAKS'),
        gaugePercent:   Math.min(lc / (this.rtData.length || 1) * 100, 100),
        status:         lc === 0 ? 'ok' : 'danger',
        statusLabel:    lc === 0 ? t.instant('GAZ.LEAKS_NONE') : t.instant('GAZ.STATUS_LEAKS_N', { n: lc }),
        recommendations: [t.instant('GAZ.KPI_REC_LEAKS_1'), t.instant('GAZ.KPI_REC_LEAKS_2'), t.instant('GAZ.KPI_REC_LEAKS_3')],
        devices: this.rtData.filter(r => r.leak > 0).map(r => ({ id: r.idDevice, val: t.instant('GAZ.LEAK_ACTIVE'), unit: '', ok: false, badge: 'CRITICAL' }))
      }
    });
  }

  // ══════════════════════════════════════════════════════════════
  // HELPERS TEMPLATE
  // ══════════════════════════════════════════════════════════════

  get hasDailyData(): boolean {
    return this.chartBars.length > 0 || this.summaries.length > 0;
  }

  get rtForTable(): RtGmDto[] { return this.rtData.slice(0, 20); }

  get co2GaugeWidth(): string {
    const max = (this.summaries.length * 2000) || 100;
    return Math.min(this.totalCo2 / max * 100, 100).toFixed(1) + '%';
  }

  get debitGaugeWidth(): string {
    return Math.min(this.avgDebit / 100 * 100, 100).toFixed(1) + '%';
  }

  get leakGaugeWidth(): string {
    if (!this.rtData.length) return '0%';
    return Math.min(this.leakCount / this.rtData.length * 100, 100).toFixed(1) + '%';
  }

  get chartTotalConso(): string { return ((this.chart?.totalConso ?? 0) / 1000).toFixed(2); }
  get chartTotalCo2():   string { return (this.chart?.totalCo2   ?? 0).toFixed(2); }
  get chartTotalCost():  string { return (this.chart?.totalCost  ?? 0).toFixed(2); }

  statusClass(s: string): string {
    return s === 'OK' ? 'status-ok' : s === 'LEAK' || s === 'FRAUD' ? 'status-alert' : 'status-warn';
  }

  alertClass(s: string): string {
    return s === 'CRITICAL' ? 'sev-critical' : s === 'HIGH' ? 'sev-high' : 'sev-low';
  }

  alertIcon(type: string): string {
    const m: Record<string, string> = {
      LEAK:        '💧',
      FRAUD:       '⚠',
      HIGH_CONSO:  '📈',
      LOW_BATTERY: '🔋'
    };
    return m[type] ?? '⚠';
  }

  recommendation(type: string): string {
    const m: Record<string, string> = {
      LEAK:        this.translate.instant('GAZ.REC_LEAK'),
      FRAUD:       this.translate.instant('GAZ.REC_FRAUD'),
      HIGH_CONSO:  this.translate.instant('GAZ.REC_HIGH_CONSO'),
      LOW_BATTERY: this.translate.instant('GAZ.REC_LOW_BATTERY')
    };
    return m[type] ?? this.translate.instant('GAZ.REC_DEFAULT');
  }
}
