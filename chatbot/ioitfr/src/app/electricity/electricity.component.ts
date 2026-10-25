import { Component, ViewChild, ElementRef } from '@angular/core';
import { Observable, forkJoin } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import {
  ElectricityService,
  ElecSummaryDto, ElecAlertDto, ElecChartDto,
  RtEnPDto
} from '../services/electricity.service';
import { ChartConfiguration } from 'chart.js';
import { CHART_BASE } from '../shared/chart-setup';
import { DateRange, DomainDashboardBase, MODAL_CHART } from '../shared/domain-dashboard.base';

// ── Palette centralisée ──────────────────────────────────────
const EP = {
  ...CHART_BASE,
  main:     '#0ea5e9',
  mainDim:  'rgba(14,165,233,0.15)',
  cyan:     '#06b6d4',
  cyanDim:  'rgba(6,182,212,0.15)',
  teal:     '#0d9488',
  tealDim:  'rgba(13,148,136,0.15)',
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
  color: 'blue' | 'green' | 'orange' | 'red' | 'purple' | 'cyan';
  icon: string;
}

interface ChartBar {
  label: string;
  l1: number; l2: number; l3: number;
  total: number; co2: number;
}

interface ElecData {
  summaries: ElecSummaryDto[];
  alerts:    ElecAlertDto[];
  rt:        RtEnPDto[];
}

type ChartModalType = 'evolution' | 'bar';

@Component({
  selector: 'app-electricity',
  templateUrl: './electricity.component.html',
  styleUrls: ['./electricity.component.scss']
})
export class ElectricityComponent extends DomainDashboardBase<ElecSummaryDto, ElecAlertDto, ElecData> {

  @ViewChild('eLineCanvas')      eLineCanvas!:         ElementRef<HTMLCanvasElement>;
  @ViewChild('eDonutCanvas')     eDonutCanvas!:        ElementRef<HTMLCanvasElement>;
  @ViewChild('eBarCanvas')       eBarCanvas!:          ElementRef<HTMLCanvasElement>;
  @ViewChild('eRadarCanvas')     eRadarCanvas!:        ElementRef<HTMLCanvasElement>;
  @ViewChild('eGaugeCanvas')     eGaugeCanvas!:        ElementRef<HTMLCanvasElement>;
  @ViewChild('eDailyCanvas')     eDailyCanvas!:        ElementRef<HTMLCanvasElement>;
  @ViewChild('modalChartCanvas') modalChartCanvasRef!: ElementRef<HTMLCanvasElement>;

  protected override readonly modalBackdropClass = 'elec-chart-modal-backdrop';
  protected override readonly insightLabel = 'électricité';

  rtData: RtEnPDto[]          = [];
  chart:  ElecChartDto | null = null;

  kpiCards:  KpiCard[]  = [];
  chartBars: ChartBar[] = [];

  totalKwh   = 0;
  totalCo2   = 0;
  totalCost  = 0;
  alertCount = 0;
  avgCosfi   = 0;
  avgThd     = 0;

  chartModalType: ChartModalType = 'evolution';
  chartModalTitle = '';
  dailyChartSub   = '';

  constructor(private elecSvc: ElectricityService) { super(); }

  protected override get modalCanvas() { return this.modalChartCanvasRef; }

  protected override insightPrompts(p: number): Record<string, string> {
    return {
      summary:
        `Analyse les statistiques électricité (${p}j) :\n` +
        `Consommation : ${this.fmt(this.totalKwh, 1)} kWh | CO₂ : ${this.fmt(this.totalCo2, 1)} kgCO₂ | Coût : ${this.fmt(this.totalCost, 2)} TND | ${this.alertCount} alerte(s)\n` +
        `cosφ moyen : ${this.avgCosfi.toFixed(3)} | THD moyen : ${this.avgThd.toFixed(1)}%\n` +
        `Résume la situation globale en 2-3 lignes : est-ce normal, bon ou préoccupant ?`,

      stats:
        `Analyse les graphiques statistiques électricité (${p}j) :\n` +
        `${this.summaries.length} compteur(s) | Consommation totale : ${this.fmt(this.totalKwh, 1)} kWh\n` +
        `cosφ moyen : ${this.avgCosfi.toFixed(3)}${this.avgCosfi < 0.85 ? ' ⚠ sous le seuil 0.85' : ' ✓ correct'} | THD : ${this.avgThd.toFixed(1)}%${this.avgThd > 10 ? ' ⚠ élevé' : this.avgThd > 5 ? ' ⚠ modéré' : ' ✓ normal'}\n` +
        `Quelles tendances ces graphiques révèlent-ils ? Y a-t-il des anomalies de facteur de puissance ou de distorsion harmonique ?`,

      quality:
        `Analyse la qualité électrique (${p}j) :\n` +
        `cosφ moyen : ${this.avgCosfi.toFixed(3)} (seuil minimal recommandé : 0.85)\n` +
        `THD moyen : ${this.avgThd.toFixed(1)}% (optimal < 5%, acceptable < 10%)\n` +
        `${this.avgCosfi < 0.85 ? '⚠ cosφ insuffisant — risque de pénalité tarifaire' : '✓ cosφ correct'} | ${this.avgThd > 10 ? '⚠ THD élevé — distorsion harmonique significative' : this.avgThd > 5 ? '⚠ THD modéré' : '✓ THD normal'}\n` +
        `Quelles actions correctives recommandes-tu pour améliorer la qualité du réseau ?`,

      alerts:
        `Analyse les alertes électricité (${p}j) :\n` +
        `${this.alertCount} alerte(s) active(s) | cosφ : ${this.avgCosfi.toFixed(3)} | THD : ${this.avgThd.toFixed(1)}%\n` +
        `Quels sont les risques principaux et les priorités d'action immédiates ?`,
    };
  }

  // ══════════════════════════════════════════════════════════════
  // CHARGEMENT
  // ══════════════════════════════════════════════════════════════

  protected override dateRangeFor(days: number): DateRange {
    return this.elecSvc.getLastNDaysRange(days);
  }

  protected override fetchData({ from, to }: DateRange): Observable<ElecData> {
    return forkJoin({
      summaries: this.elecSvc.getAllSummaries(from, to),
      alerts:    this.elecSvc.getAlerts(),
      rt:        this.elecSvc.getRealTimeAll()
    });
  }

  protected override applyData(data: ElecData): void {
    this.rtData = data.rt;
  }

  protected override afterDataLoaded({ from, to }: DateRange): void {
    const firstDevice = this.summaries[0]?.idDevice;
    if (!firstDevice) { this.buildChartBars(); return; }

    const loader = this.selectedPeriod <= 1
      ? this.elecSvc.getHourlyChart(firstDevice, from, to)
      : this.selectedPeriod <= 30
        ? this.elecSvc.getDailyChart(firstDevice, from, to)
        : this.elecSvc.getMonthlyChart(firstDevice, from, to);

    loader.pipe(takeUntil(this.destroy$)).subscribe(c => {
      this.chart = c;
      this.buildChartBars();
    });
  }

  protected override refreshLabels(): void {
    const t = this.translate;
    this.chartModalTitle = this.chartModalType === 'evolution'
      ? t.instant('ENERGY.EVOLUTION') + ' — kWh'
      : t.instant('ENERGY.CO2_COST_PER_METER');
    this.dailyChartSub = this.chartBars.length > 0
      ? t.instant('ENERGY.DAILY_KWH')
      : t.instant('ENERGY.SUMMARY_BY_METER');
  }

  // ══════════════════════════════════════════════════════════════
  // DONNÉES DÉRIVÉES
  // ══════════════════════════════════════════════════════════════

  protected override buildKpi(): void {
    this.totalKwh  = this.summaries.reduce((s, d) => s + (d.totalConsoJKwh ?? 0), 0);
    this.totalCo2  = this.summaries.reduce((s, d) => s + (d.co2Kg          ?? 0), 0);
    this.totalCost = this.summaries.reduce((s, d) => s + (d.costTnd        ?? 0), 0);
    this.alertCount = this.alerts.length;

    this.avgCosfi = this.rtData.length
      ? this.rtData.reduce((s, r) => s + ((r.cosfiL1 + r.cosfiL2 + r.cosfiL3) / 3), 0) / this.rtData.length
      : (this.summaries[0]?.avgCosfi ?? 0);

    this.avgThd = this.rtData.length
      ? this.rtData.reduce((s, r) => s + ((r.thdL1 + r.thdL2 + r.thdL3) / 3), 0) / this.rtData.length
      : (this.summaries[0]?.avgThd ?? 0);

    const trend      = this.summaries[0]?.trend ?? '+0.0%';
    const criticals  = this.countBySeverity('CRITICAL');
    const t          = this.translate;

    this.kpiCards = [
      {
        label: t.instant('ELEC.KPI_CONSUMPTION'), value: this.fmt(this.totalKwh, 1),
        unit: t.instant('ELEC.KPI_CONSO_UNIT'), trend, trendUp: this.isTrendUp(trend),
        color: 'blue',
        icon: '<svg viewBox="0 0 24 24"><path d="M7 2v11h3v9l7-12h-4l4-8z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('ELEC.KPI_CO2'), value: this.fmt(this.totalCo2, 1),
        unit: t.instant('ELEC.KPI_CO2_UNIT'), trend, trendUp: this.isTrendUp(trend),
        color: 'orange',
        icon: '<svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('ELEC.KPI_COST'), value: this.fmt(this.totalCost, 2),
        unit: 'TND', trend: t.instant('ELEC.KPI_COST_RATE'), trendUp: null,
        color: 'green',
        icon: '<svg viewBox="0 0 24 24"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('ELEC.KPI_ALERTS'), value: String(this.alertCount),
        unit: t.instant('ELEC.KPI_ALERTS_UNIT'),
        trend: this.alertCount === 0
          ? t.instant('ELEC.STATUS_NO_ALERT')
          : t.instant('ELEC.STATUS_CRITICALS', { n: criticals }),
        trendUp: this.alertCount > 0,
        color: this.alertCount > 0 ? 'red' : 'green',
        icon: '<svg viewBox="0 0 24 24"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('ELEC.KPI_COSFI'), value: this.avgCosfi.toFixed(3),
        unit: t.instant('ELEC.KPI_COSFI_UNIT'),
        trend: this.avgCosfi >= 0.85 ? t.instant('ELEC.COSFI_TREND_OK') : t.instant('ELEC.COSFI_TREND_WARN'),
        trendUp: this.avgCosfi >= 0.85,
        color: this.avgCosfi >= 0.85 ? 'green' : 'red',
        icon: '<svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L21 8l-9 9z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('ELEC.KPI_THD'), value: this.avgThd.toFixed(2) + '%',
        unit: t.instant('ELEC.KPI_THD_UNIT'),
        trend: this.avgThd <= 5 ? t.instant('ELEC.THD_TREND_OK') : t.instant('ELEC.THD_TREND_WARN'),
        trendUp: this.avgThd <= 5,
        color: this.avgThd <= 5 ? 'cyan' : 'red',
        icon: '<svg viewBox="0 0 24 24"><path d="M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z" fill="currentColor"/></svg>'
      }
    ];
    this.buildKpiDefs();
  }

  private buildChartBars(): void {
    const pts = this.chart?.points ?? [];
    if (!pts.length) {
      this.chartBars     = [];
      this.dailyChartSub = this.translate.instant('ENERGY.SUMMARY_BY_METER');
      return;
    }
    this.chartBars = pts.map(p => ({
      label: p.label,
      l1: p.consL1 ?? 0, l2: p.consL2 ?? 0, l3: p.consL3 ?? 0,
      total: p.consKwh ?? 0, co2: p.co2Kg ?? 0
    }));
    this.dailyChartSub = this.translate.instant('ENERGY.DAILY_KWH');
    this.scheduleChartsRender();
  }

  // ══════════════════════════════════════════════════════════════
  // CHARTS INLINE
  // ══════════════════════════════════════════════════════════════

  protected override buildCharts(): void {
    this.buildDailyChart();
    this.buildElecLine();
    this.buildElecDonut();
    this.buildElecBar();
    this.buildElecRadar();
    this.buildElecGauge();
  }

  private buildElecLine(): void {
    if (!this.eLineCanvas) return;
    const pts = this.chart?.points ?? [];
    const cfg: ChartConfiguration<'line'> = {
      type: 'line',
      data: {
        labels: pts.map(p => p.label),
        datasets: [{
          label: 'kWh',
          data:   pts.map(p => +(p.consKwh ?? 0).toFixed(2)),
          borderColor:     EP.main,
          backgroundColor: EP.mainDim,
          borderWidth: 2, tension: 0.4, fill: true,
          pointRadius:          pts.length > 20 ? 0 : 3,
          pointBackgroundColor: EP.main
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: EP.tooltip, titleColor: EP.main, bodyColor: '#fff',
            callbacks: { label: ctx => ` ${ctx.parsed.y} kWh` }
          }
        },
        scales: {
          x: { grid: { color: EP.grid }, ticks: { color: EP.text, maxTicksLimit: 8, font: { size: 10 } } },
          y: { grid: { color: EP.grid }, ticks: { color: EP.text, font: { size: 10 }, callback: (v: any) => v + ' kWh' }, beginAtZero: true }
        }
      }
    };
    this.renderChart('line', this.eLineCanvas, cfg);
  }

  private buildElecDonut(): void {
    if (!this.eDonutCanvas || !this.summaries.length) return;
    const colors = [EP.main, EP.cyan, EP.green, EP.teal, EP.blue, EP.lime];
    const cfg: ChartConfiguration<'doughnut'> = {
      type: 'doughnut',
      data: {
        labels:   this.summaries.map(s => `#${s.idDevice}`),
        datasets: [{
          data:            this.summaries.map(s => +(s.totalConsoMKwh ?? 0).toFixed(1)),
          backgroundColor: this.summaries.map((_, i) => colors[i % colors.length] + '99'),
          borderColor:     this.summaries.map((_, i) => colors[i % colors.length]),
          borderWidth: 2, hoverOffset: 6
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '68%',
        plugins: {
          legend: { position: 'bottom', labels: { color: EP.text, font: { size: 10 }, padding: 10, boxWidth: 10 } },
          tooltip: {
            backgroundColor: EP.tooltip, titleColor: EP.main, bodyColor: '#fff',
            callbacks: { label: ctx => ` ${ctx.label} : ${ctx.parsed} kWh` }
          }
        }
      }
    };
    this.renderChart('donut', this.eDonutCanvas, cfg);
  }

  private buildElecBar(): void {
    if (!this.eBarCanvas || !this.summaries.length) return;
    const cfg: ChartConfiguration<'bar'> = {
      type: 'bar',
      data: {
        labels:   this.summaries.map(s => `#${s.idDevice}`),
        datasets: [
          {
            label:           this.translate.instant('ENERGY.CO2_KG'),
            data:            this.summaries.map(s => +(s.co2Kg    ?? 0).toFixed(2)),
            backgroundColor: EP.tealDim, borderColor: EP.teal,
            borderWidth: 1.5, borderRadius: 4
          },
          {
            label:           this.translate.instant('ENERGY.COST_TND_LABEL'),
            data:            this.summaries.map(s => +(s.costTnd  ?? 0).toFixed(2)),
            backgroundColor: EP.greenDim,  borderColor: EP.green,
            borderWidth: 1.5, borderRadius: 4
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: EP.text, font: { size: 10 }, boxWidth: 10 } },
          tooltip: { backgroundColor: EP.tooltip, titleColor: '#fff', bodyColor: EP.text }
        },
        scales: {
          x: { grid: { color: EP.grid }, ticks: { color: EP.text, font: { size: 10 } } },
          y: { grid: { color: EP.grid }, ticks: { color: EP.text, font: { size: 10 } }, beginAtZero: true }
        }
      }
    };
    this.renderChart('bar', this.eBarCanvas, cfg);
  }

  private buildElecRadar(): void {
    if (!this.eRadarCanvas || !this.summaries.length) return;
    const colors  = [EP.main, EP.cyan, EP.green, EP.teal, EP.blue];
    const maxKwh  = Math.max(...this.summaries.map(s => s.totalConsoMKwh ?? 0), 1);
    const maxCo2  = Math.max(...this.summaries.map(s => s.co2Kg          ?? 0), 1);
    const maxCost = Math.max(...this.summaries.map(s => s.costTnd        ?? 0), 1);
    const maxAlert= Math.max(...this.summaries.map(s => s.alertCount     ?? 0), 1);
    const cfg: ChartConfiguration<'radar'> = {
      type: 'radar',
      data: {
        labels: [
          'kWh',
          this.translate.instant('ENERGY.CO2_KG'),
          this.translate.instant('ENERGY.COST_TND_LABEL'),
          this.translate.instant('ENERGY.RADAR_ALERTS'),
          this.translate.instant('ENERGY.RADAR_COSFI')
        ],
        datasets: this.summaries.slice(0, 5).map((s, i) => ({
          label:              `#${s.idDevice}`,
          data: [
            +((s.totalConsoMKwh ?? 0) / maxKwh  * 100).toFixed(1),
            +((s.co2Kg          ?? 0) / maxCo2   * 100).toFixed(1),
            +((s.costTnd        ?? 0) / maxCost  * 100).toFixed(1),
            +((s.alertCount     ?? 0) / maxAlert * 100).toFixed(1),
            +((s.avgCosfi       ?? 0)             * 100).toFixed(1)
          ],
          borderColor:          colors[i % colors.length],
          backgroundColor:      colors[i % colors.length] + '22',
          borderWidth:          1.5,
          pointBackgroundColor: colors[i % colors.length],
          pointRadius:          3
        }))
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { color: EP.text, font: { size: 10 }, boxWidth: 10 } },
          tooltip: { backgroundColor: EP.tooltip, titleColor: '#fff', bodyColor: EP.text }
        },
        scales: {
          r: {
            grid:        { color: EP.grid },
            angleLines:  { color: EP.grid },
            ticks:       { color: EP.text, font: { size: 9 }, backdropColor: 'transparent', stepSize: 25 },
            pointLabels: { color: EP.text, font: { size: 10 } },
            min: 0, max: 100
          }
        }
      }
    };
    this.renderChart('radar', this.eRadarCanvas, cfg);
  }

  private buildElecGauge(): void {
    if (!this.eGaugeCanvas) return;
    const cosfi  = Math.min(Math.max(this.avgCosfi, 0), 1);
    const remain = 1 - cosfi;
    const color  = cosfi >= 0.92 ? EP.green : cosfi >= 0.85 ? EP.cyan : EP.red;
    this.renderChart('gauge', this.eGaugeCanvas, {
      type: 'doughnut',
      data: {
        datasets: [{
          data:            [cosfi, remain],
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
    if (!this.eDailyCanvas) return;

    const pts = this.chartBars;
    const useSummaries = !pts.length && this.summaries.length > 0;
    if (!pts.length && !useSummaries) { this.destroyChart('daily'); return; }

    const isStacked = pts.length > 0;
    const phaseColors = [
      { bg: 'rgba(14,165,233,0.6)',  border: EP.main  },
      { bg: 'rgba(16,185,129,0.6)',  border: EP.green },
      { bg: 'rgba(13,148,136,0.6)',  border: EP.teal  }
    ];
    const meterColors = [EP.main, EP.green, EP.teal, EP.cyan, EP.lime];

    const datasets: any[] = isStacked
      ? ['L1', 'L2', 'L3'].map((lbl, i) => ({
          label: lbl,
          data: pts.map(b => +([b.l1, b.l2, b.l3][i]).toFixed(2)),
          backgroundColor: phaseColors[i].bg,
          borderColor:     phaseColors[i].border,
          borderWidth: 1.5, borderRadius: 3, stack: 'conso'
        }))
      : [{
          label: 'kWh',
          data:            this.summaries.map(s => +(s.totalConsoMKwh ?? 0).toFixed(1)),
          backgroundColor: this.summaries.map((_, i) => meterColors[i % meterColors.length] + '99'),
          borderColor:     this.summaries.map((_, i) => meterColors[i % meterColors.length]),
          borderWidth: 1.5, borderRadius: 5
        }];

    const labels = isStacked
      ? pts.map(b => b.label)
      : this.summaries.map(s => `Compteur #${s.idDevice}`);

    this.renderChart('daily', this.eDailyCanvas, {
      type: 'bar',
      data: { labels, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 700 } as any,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            display: isStacked, position: 'bottom',
            labels: {
              color: EP.text, font: { size: 11, family: 'Inter, sans-serif' },
              boxWidth: 12, boxHeight: 12, usePointStyle: false, padding: 16
            }
          },
          tooltip: {
            backgroundColor: EP.tooltip,
            titleColor: '#e6eaf4',
            bodyColor: 'rgba(230,234,244,0.75)',
            footerColor: EP.main,
            borderColor: 'rgba(14,165,233,0.35)',
            borderWidth: 1,
            padding: { top: 10, bottom: 10, left: 14, right: 14 },
            cornerRadius: 10,
            displayColors: true,
            boxWidth: 10, boxHeight: 10,
            titleFont: { size: 12, weight: 'bold', family: 'Inter, sans-serif' },
            bodyFont:  { size: 12, family: 'Inter, sans-serif' },
            footerFont: { size: 12, weight: 'bold', family: 'Inter, sans-serif' },
            callbacks: {
              title: (items: any[]) => items[0]?.label ?? '',
              label: (ctx: any) => {
                const val = ctx.parsed.y.toLocaleString(this.locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                return `  ${ctx.dataset.label} : ${val} kWh`;
              },
              footer: isStacked
                ? (items: any[]) => {
                    const total = items.reduce((s, i) => s + i.parsed.y, 0);
                    return `  Total : ${total.toLocaleString(this.locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kWh`;
                  }
                : undefined
            }
          }
        },
        scales: {
          x: {
            grid: { color: EP.grid },
            ticks: { color: EP.text, maxTicksLimit: 14, font: { size: 10, family: 'Inter, sans-serif' } },
            stacked: isStacked
          },
          y: {
            grid: { color: EP.grid },
            ticks: {
              color: EP.text, font: { size: 10, family: 'Inter, sans-serif' },
              callback: (v: any) => v + ' kWh', maxTicksLimit: 8
            },
            beginAtZero: true, stacked: isStacked
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
    gr.addColorStop(0,   'rgba(14,165,233,0.35)');
    gr.addColorStop(0.6, 'rgba(14,165,233,0.08)');
    gr.addColorStop(1,   'rgba(14,165,233,0.00)');

    this.renderChart(MODAL_CHART, ctx, {
      type: 'line',
      data: {
        labels:   pts.map(p => p.label),
        datasets: [{
          label:               'kWh',
          data:                pts.map(p => +(p.consKwh ?? 0).toFixed(2)),
          borderColor:         EP.main,
          backgroundColor:     gr,
          borderWidth:         2.5,
          tension:             0.42,
          fill:                true,
          pointRadius:         pts.length > 30 ? 0 : 4,
          pointHoverRadius:    8,
          pointBackgroundColor: EP.main,
          pointBorderColor:    'rgba(14,165,233,0.25)',
          pointBorderWidth:    2,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 600 } as any,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: EP.tooltip, titleColor: EP.main, bodyColor: '#fff',
            borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1,
            padding: 14, cornerRadius: 12,
            callbacks: {
              label: (ctx: any) => ` ${ctx.parsed.y.toLocaleString(this.locale, { maximumFractionDigits: 2 })} kWh`
            }
          }
        },
        scales: {
          x: {
            grid:  { color: EP.grid },
            ticks: { color: EP.text, maxTicksLimit: 12, font: { size: 10, family: 'Inter, sans-serif' } }
          },
          y: {
            grid:  { color: EP.grid },
            ticks: { color: EP.text, font: { size: 10, family: 'Inter, sans-serif' }, padding: 8 },
            beginAtZero: true,
            title: { display: true, text: 'kWh', color: 'rgba(255,255,255,0.3)', font: { size: 10 } }
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
            label:           this.translate.instant('ENERGY.CO2_KG'),
            data:            this.summaries.map(s => +(s.co2Kg   ?? 0).toFixed(2)),
            backgroundColor: 'rgba(13,148,136,0.25)',
            borderColor:     EP.teal,
            borderWidth:     2,
            borderRadius:    6,
            hoverBackgroundColor: 'rgba(13,148,136,0.45)'
          },
          {
            label:           this.translate.instant('ENERGY.COST_TND_LABEL'),
            data:            this.summaries.map(s => +(s.costTnd ?? 0).toFixed(2)),
            backgroundColor: 'rgba(16,185,129,0.2)',
            borderColor:     EP.green,
            borderWidth:     2,
            borderRadius:    6,
            hoverBackgroundColor: 'rgba(16,185,129,0.4)'
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
            labels:   { color: EP.text, font: { size: 11, family: 'Inter, sans-serif' }, boxWidth: 10, boxHeight: 10, padding: 16, usePointStyle: true }
          },
          tooltip: {
            backgroundColor: EP.tooltip, titleColor: '#fff', bodyColor: EP.text,
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
            grid:  { color: EP.grid },
            ticks: { color: EP.text, font: { size: 10, family: 'Inter, sans-serif' } }
          },
          y: {
            grid:  { color: EP.grid },
            ticks: { color: EP.text, font: { size: 10, family: 'Inter, sans-serif' }, padding: 8 },
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
    this.setKpiDefs({
      conso: {
        title: t.instant('ELEC.KPI_CONSUMPTION') + ' (kWh)',
        accent: '#0ea5e9', value: this.fmt(this.totalKwh, 1), unit: 'kWh',
        definition:      t.instant('ELEC.DEF_CONSO'),
        why:             t.instant('ELEC.WHY_CONSO'),
        threshold: null, thresholdLabel: null,
        gaugePercent:    Math.min(this.totalKwh / (this.summaries.length * 5000 || 1) * 100, 100),
        status: null, statusLabel: null,
        recommendations: [t.instant('ELEC.KPI_REC_CONSO_1'), t.instant('ELEC.KPI_REC_CONSO_2'), t.instant('ELEC.KPI_REC_CONSO_3')],
        devices: this.summaries.map(s => ({ id: s.idDevice, val: (s.totalConsoMKwh ?? 0).toFixed(1), unit: 'kWh', ok: true, badge: s.status ?? 'OK' }))
      },
      co2: {
        title: t.instant('ELEC.KPI_CO2') + ' (kgCO₂)',
        accent: '#06b6d4', value: this.fmt(this.totalCo2, 1), unit: 'kgCO₂',
        definition:      t.instant('ELEC.DEF_CO2'),
        why:             t.instant('ELEC.WHY_CO2'),
        threshold: null, thresholdLabel: t.instant('ELEC.FACTOR_CO2'),
        gaugePercent:    Math.min(this.totalCo2 / (this.summaries.length * 3000 || 1) * 100, 100),
        status: null, statusLabel: null,
        recommendations: [t.instant('ELEC.KPI_REC_CO2_1'), t.instant('ELEC.KPI_REC_CO2_2'), t.instant('ELEC.KPI_REC_CO2_3')],
        devices: this.summaries.map(s => ({ id: s.idDevice, val: (s.co2Kg ?? 0).toFixed(2), unit: 'kg', ok: true, badge: s.status ?? 'OK' }))
      },
      cost: {
        title: t.instant('ELEC.KPI_COST') + ' (TND)',
        accent: '#10b981', value: this.fmt(this.totalCost, 2), unit: 'TND',
        definition:      t.instant('ELEC.DEF_COST'),
        why:             t.instant('ELEC.WHY_COST'),
        threshold: null, thresholdLabel: t.instant('ELEC.FACTOR_COST'),
        gaugePercent:    Math.min(this.totalCost / (this.summaries.length * 1500 || 1) * 100, 100),
        status: null, statusLabel: null,
        recommendations: [t.instant('ELEC.KPI_REC_COST_1'), t.instant('ELEC.KPI_REC_COST_2'), t.instant('ELEC.KPI_REC_COST_3')],
        devices: this.summaries.map(s => ({ id: s.idDevice, val: (s.costTnd ?? 0).toFixed(2), unit: 'TND', ok: true, badge: s.status ?? 'OK' }))
      },
      alerts: {
        title: t.instant('ELEC.KPI_ALERTS'),
        accent: '#ef4444', value: String(this.alertCount), unit: t.instant('COMMON.ALERTS'),
        definition:      t.instant('ELEC.DEF_ALERTS'),
        why:             t.instant('ELEC.WHY_ALERTS'),
        threshold: 0, thresholdLabel: t.instant('ELEC.THRESHOLD_THD'),
        gaugePercent:    Math.min(this.alertCount / 10 * 100, 100),
        status:          this.alertCount === 0 ? 'ok' : 'warn',
        statusLabel:     this.alertCount === 0 ? t.instant('ELEC.STATUS_NO_ALERT') : t.instant('ELEC.STATUS_CRITICALS', { n: criticals }),
        recommendations: [t.instant('ELEC.KPI_REC_ALERTS_1'), t.instant('ELEC.KPI_REC_ALERTS_2'), t.instant('ELEC.KPI_REC_ALERTS_3')],
        devices: this.alerts.slice(0, 10).map(a => ({ id: a.idDevice, val: a.type, unit: '', ok: a.severity !== 'CRITICAL', badge: a.severity }))
      },
      cosfi: {
        title: t.instant('ELEC.KPI_COSFI'),
        accent: this.avgCosfi >= 0.85 ? '#10b981' : '#ef4444',
        value: this.avgCosfi.toFixed(3), unit: '',
        definition:      t.instant('ELEC.DEF_COSFI'),
        why:             t.instant('ELEC.WHY_COSFI'),
        threshold: 0.85, thresholdLabel: t.instant('ELEC.THRESHOLD_COSFI'),
        gaugePercent:    this.avgCosfi * 100,
        status:          this.avgCosfi >= 0.85 ? 'ok' : 'danger',
        statusLabel:     this.avgCosfi >= 0.85 ? t.instant('ELEC.COSFI_OK') : t.instant('ELEC.COSFI_WARN'),
        recommendations: [t.instant('ELEC.KPI_REC_COSFI_1'), t.instant('ELEC.KPI_REC_COSFI_2'), t.instant('ELEC.KPI_REC_COSFI_3'), t.instant('ELEC.KPI_REC_COSFI_4')],
        devices: this.summaries.map(s => ({
          id: s.idDevice, val: (s.avgCosfi ?? 0).toFixed(3), unit: '',
          ok: (s.avgCosfi ?? 0) >= 0.85,
          badge: (s.avgCosfi ?? 0) >= 0.85 ? t.instant('ENERGY.COSFI_NOTE_OK') : t.instant('ENERGY.COSFI_NOTE_WARN')
        }))
      },
      thd: {
        title: t.instant('ELEC.KPI_THD'),
        accent: this.avgThd <= 5 ? '#10b981' : '#ef4444',
        value: this.avgThd.toFixed(2) + '%', unit: '',
        definition:      t.instant('ELEC.DEF_THD'),
        why:             t.instant('ELEC.WHY_THD'),
        threshold: 5, thresholdLabel: t.instant('ELEC.THRESHOLD_THD'),
        gaugePercent:    Math.min(this.avgThd / 10 * 100, 100),
        status:          this.avgThd <= 5 ? 'ok' : 'danger',
        statusLabel:     this.avgThd <= 5 ? t.instant('ELEC.THD_OK') : t.instant('ELEC.THD_WARN'),
        recommendations: [t.instant('ELEC.KPI_REC_THD_1'), t.instant('ELEC.KPI_REC_THD_2'), t.instant('ELEC.KPI_REC_THD_3'), t.instant('ELEC.KPI_REC_THD_4')],
        devices: this.summaries.map(s => ({
          id: s.idDevice, val: (s.avgThd ?? 0).toFixed(2) + '%', unit: '',
          ok: (s.avgThd ?? 0) <= 5,
          badge: (s.avgThd ?? 0) <= 5 ? t.instant('ENERGY.THD_NOTE_OK') : t.instant('ENERGY.THD_NOTE_WARN')
        }))
      }
    });
  }

  // ══════════════════════════════════════════════════════════════
  // HELPERS TEMPLATE
  // ══════════════════════════════════════════════════════════════

  get hasDailyData(): boolean {
    return this.chartBars.length > 0 || this.summaries.length > 0;
  }

  get rtForTable(): RtEnPDto[] { return this.rtData.slice(0, 20); }

  totalPower(rt: RtEnPDto): number {
    return ((rt.activePowerL1 ?? 0) + (rt.activePowerL2 ?? 0) + (rt.activePowerL3 ?? 0)) / 1000;
  }
  avgVoltage(rt: RtEnPDto): number {
    return ((rt.rmsVoltageL1 ?? 0) + (rt.rmsVoltageL2 ?? 0) + (rt.rmsVoltageL3 ?? 0)) / 3;
  }
  avgCurrent(rt: RtEnPDto): number {
    return ((rt.rmsCurrentL1 ?? 0) + (rt.rmsCurrentL2 ?? 0) + (rt.rmsCurrentL3 ?? 0)) / 3;
  }
  avgCosfiRt(rt: RtEnPDto): number {
    return ((rt.cosfiL1 ?? 0) + (rt.cosfiL2 ?? 0) + (rt.cosfiL3 ?? 0)) / 3;
  }
  avgThdRt(rt: RtEnPDto): number {
    return ((rt.thdL1 ?? 0) + (rt.thdL2 ?? 0) + (rt.thdL3 ?? 0)) / 3;
  }
  enJour(rt: RtEnPDto): number {
    return (rt.enAccumuleeJourL1 ?? 0) + (rt.enAccumuleeJourL2 ?? 0) + (rt.enAccumuleeJourL3 ?? 0);
  }

  statusClass(s: string): string {
    return s === 'OK' ? 'status-ok' : s === 'LOW_BATTERY' ? 'status-warn' : 'status-alert';
  }

  alertClass(s: string): string {
    return s === 'CRITICAL' ? 'sev-critical' : s === 'HIGH' ? 'sev-high' : 'sev-low';
  }

  alertIcon(type: string): string {
    const m: Record<string, string> = {
      HIGH_THD:    '⚡',
      LOW_COSFI:   '⚙',
      LOW_BATTERY: '🔋',
      HIGH_CONSO:  '📈'
    };
    return m[type] ?? '⚠';
  }

  recommendation(type: string): string {
    const m: Record<string, string> = {
      LOW_BATTERY: this.translate.instant('ELEC.REC_LOW_BATTERY'),
      HIGH_THD:    this.translate.instant('ELEC.REC_HIGH_THD'),
      LOW_COSFI:   this.translate.instant('ELEC.REC_LOW_COSFI'),
      HIGH_CONSO:  this.translate.instant('ELEC.REC_HIGH_CONSO')
    };
    return m[type] ?? this.translate.instant('ELEC.REC_DEFAULT');
  }

  thdWidth(thd: number): string {
    return Math.min(thd / 10 * 100, 100) + '%';
  }

  get co2GaugeWidth(): string {
    const max = (this.summaries.length * 3000) || 100;
    return Math.min(this.totalCo2 / max * 100, 100).toFixed(1) + '%';
  }

  get chartTotalKwh():  string { return (this.chart?.totalConsKwh  ?? 0).toFixed(1); }
  get chartTotalCo2():  string { return (this.chart?.totalCo2Kg    ?? 0).toFixed(2); }
  get chartTotalCost(): string { return (this.chart?.totalCostTnd  ?? 0).toFixed(2); }
}
