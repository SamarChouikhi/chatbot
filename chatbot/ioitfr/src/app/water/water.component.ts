import { Component, OnInit, OnDestroy, AfterViewInit, ViewChild, ElementRef, NgZone, ChangeDetectorRef } from '@angular/core';
import { Router } from '@angular/router';
import { Subject, forkJoin } from 'rxjs';
import { ChatTriggerService } from '../core/services/chat-trigger.service';
import { takeUntil, finalize } from 'rxjs/operators';
import { TranslateService } from '@ngx-translate/core';
import {
  WaterService, WaterSummaryDto, WaterAlertDto, WaterChartDto, RtWmDto
} from '../services/water.service';
import {
  Chart, ChartConfiguration,
  LineController, BarController, DoughnutController, RadarController,
  CategoryScale, LinearScale, RadialLinearScale,
  PointElement, LineElement, BarElement, ArcElement,
  Tooltip, Legend, Filler
} from 'chart.js';

Chart.register(
  LineController, BarController, DoughnutController, RadarController,
  CategoryScale, LinearScale, RadialLinearScale,
  PointElement, LineElement, BarElement, ArcElement,
  Tooltip, Legend, Filler
);

interface KpiCard {
  label: string; value: string; unit: string;
  trend: string; trendGood: boolean | null;
  color: 'blue' | 'green' | 'orange' | 'red' | 'cyan';
  icon: string;
}

interface ChartBar { label: string; conso: number; co2: number; debit: number; }

const PALETTE = {
  water:    '#06b6d4', waterDim:    'rgba(6,182,212,0.15)',
  cyan:     '#0ea5e9', cyanDim:     'rgba(14,165,233,0.15)',
  green:    '#10b981', greenDim:    'rgba(16,185,129,0.15)',
  teal:     '#0d9488', tealDim:     'rgba(13,148,136,0.15)',
  blue:     '#0369a1', blueDim:     'rgba(3,105,161,0.15)',
  lime:     '#22c55e',
  red:      '#e74c3c', redDim:      'rgba(231,76,60,0.15)',
  grid:     'rgba(255,255,255,0.06)',
  text:     'rgba(255,255,255,0.45)'
};

@Component({
  selector: 'app-water',
  templateUrl: './water.component.html',
  styleUrls: ['./water.component.scss']
})
export class WaterComponent implements OnInit, OnDestroy, AfterViewInit {

  @ViewChild('lineCanvas')        lineCanvas!:        ElementRef<HTMLCanvasElement>;
  @ViewChild('donutCanvas')       donutCanvas!:       ElementRef<HTMLCanvasElement>;
  @ViewChild('barCo2Canvas')      barCo2Canvas!:      ElementRef<HTMLCanvasElement>;
  @ViewChild('radarCanvas')       radarCanvas!:       ElementRef<HTMLCanvasElement>;
  @ViewChild('groupedBarCanvas')  groupedBarCanvas!:  ElementRef<HTMLCanvasElement>;
  @ViewChild('wDailyCanvas')      wDailyCanvas!:      ElementRef<HTMLCanvasElement>;
  @ViewChild('modalChartCanvas')  modalChartCanvasRef!: ElementRef<HTMLCanvasElement>;

  private lineChart!:        Chart<any>;
  private donutChart!:       Chart<any>;
  private barCo2Chart!:      Chart<any>;
  private radarChart!:       Chart<any>;
  private groupedBarChart!:  Chart<any>;
  private wDailyChart:       any = null;
  private modalChart:        any = null;

  chartsReady = false;

  chartModalOpen = false;
  chartModalType: 'evolution' | 'co2cost' | 'consoByMeter' = 'evolution';

  chartModalTitle = '';
  chartModalBadge = 'Ligne';

  private onEscKey = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') this.closeChartModal();
  };

  isLoading        = false;
  loadError        = false;

  selectedPeriod = 30;
  periodOptions: Array<{ label: string; value: number }> = [];
  dataRange = '';

  summaries: WaterSummaryDto[] = [];
  alerts:    WaterAlertDto[]   = [];
  rtData:    RtWmDto[]         = [];
  chart:     WaterChartDto | null = null;

  kpiCards:  KpiCard[]  = [];
  chartBars: ChartBar[] = [];

  totalConsoM3 = 0;
  totalCo2     = 0;
  totalCost    = 0;
  alertCount   = 0;

  private destroy$ = new Subject<void>();

  constructor(private waterSvc: WaterService, private router: Router, private zone: NgZone, private translate: TranslateService, private cdr: ChangeDetectorRef, private chatTrigger: ChatTriggerService) {}

  openAriaInsight(section: string, event: MouseEvent): void {
    event.stopPropagation();
    const p = this.selectedPeriod;
    const prompts: Record<string, string> = {
      summary: `Analyse les statistiques Eau (${p}j) :\n` +
        `Consommation : ${this.totalConsoM3.toFixed(3)} m³\n` +
        `CO₂ traitement : ${this.totalCo2.toFixed(2)} kgCO₂ | Coût : ${this.totalCost.toFixed(2)} TND\n` +
        `Fuites détectées : ${this.leakCount} | Alertes : ${this.alertCount}\n` +
        `Compteurs actifs : ${this.summaries.length}\n` +
        `Est-ce normal, préoccupant ou excellent ? Réponds en 2-3 lignes.`,

      stats: `Analyse les graphiques statistiques Eau (${p}j) :\n` +
        `Total consommé : ${this.totalConsoM3.toFixed(3)} m³ sur ${this.summaries.length} compteur(s)\n` +
        `CO₂ : ${this.totalCo2.toFixed(2)} kg | Coût : ${this.totalCost.toFixed(2)} TND\n` +
        `Identifie les pics de consommation et les compteurs problématiques.`,

      quality: `Analyse le résumé par compteur Eau (${p}j) :\n` +
        `${this.summaries.length} compteur(s) · Fuites : ${this.leakCount} · Alertes : ${this.alertCount}\n` +
        `Donne un diagnostic qualité du réseau hydrique.`,

      alerts: `Analyse les alertes eau actives (${p}j) :\n` +
        `Total : ${this.alertCount} alerte(s) · Fuites : ${this.leakCount} compteur(s) affecté(s)\n` +
        `Quelles sont les actions prioritaires à mener ?`,
    };
    this.chatTrigger.open(prompts[section] ?? `Analyse Eau — ${section} — ${p}j.`);
  }

  ngOnInit(): void {
    this._buildPeriodOptions();
    this.dataRange = this.translate.instant('COMMON.LOADING');
    this.load();
    this.translate.onLangChange.pipe(takeUntil(this.destroy$)).subscribe(() => {
      this._buildPeriodOptions();
      const { from, to } = this.waterSvc.getLastNDaysRange(this.selectedPeriod);
      this.updateDateRange(from, to);
      this.buildKpi();
      this.buildAllCharts();
    });
  }
  ngAfterViewInit(): void { this.chartsReady = true; }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    document.removeEventListener('keydown', this.onEscKey);
    [this.lineChart, this.donutChart, this.barCo2Chart, this.radarChart, this.groupedBarChart, this.wDailyChart, this.modalChart]
      .forEach(c => c?.destroy());
  }

  load(): void {
    this.isLoading = true;
    this.loadError = false;
    const { from, to } = this.waterSvc.getLastNDaysRange(this.selectedPeriod);
    this.updateDateRange(from, to);

    forkJoin({
      summaries: this.waterSvc.getAllSummaries(from, to),
      alerts:    this.waterSvc.getAlerts(),
      rt:        this.waterSvc.getRealTimeAll()
    })
    .pipe(takeUntil(this.destroy$), finalize(() => this.isLoading = false))
    .subscribe({
      next: ({ summaries, alerts, rt }) => {
        this.summaries = summaries;
        this.alerts    = alerts;
        this.rtData    = rt;
        this.buildKpi();
        this.loadChart(from, to);
        setTimeout(() => this.buildAllCharts(), 300);
      },
      error: () => { this.loadError = true; }
    });
  }

  onPeriodChange(period: number): void { this.selectedPeriod = period; this.load(); }

  private loadChart(from: Date, to: Date): void {
    const firstDevice = this.summaries[0]?.idDevice;
    if (!firstDevice) { this.buildChartBars(); return; }

    const loader = this.selectedPeriod <= 30
      ? this.waterSvc.getDailyChart(firstDevice, from, to)
      : this.waterSvc.getMonthlyChart(firstDevice, from, to);

    loader.pipe(takeUntil(this.destroy$)).subscribe((result: any) => {
      if (result && 'points' in result) {
        this.chart = result as WaterChartDto;
      } else if (Array.isArray(result)) {
        this.chart = {
          points: result.map((r: any) => ({
            label:   this.fmtDateLabel(r.date ?? ''),
            conso:   r.conso   ?? 0,
            consoM3: (r.conso  ?? 0) / 1000,
            co2:     (r.conso  ?? 0) / 1000 * 0.30,
            cost:    (r.conso  ?? 0) / 1000 * 0.40
          })),
          totalConsoL:  result.reduce((s: number, r: any) => s + (r.conso ?? 0), 0),
          totalConsoM3: result.reduce((s: number, r: any) => s + (r.conso ?? 0), 0) / 1000,
          totalCo2:  0,
          totalCost: 0
        };
      }
      this.buildChartBars();
    });
  }

  private buildKpi(): void {
    this.totalConsoM3 = this.summaries.reduce((s, d) => s + (d.totalConsoM3 ?? 0), 0);
    this.totalCo2     = this.summaries.reduce((s, d) => s + (d.co2Kg        ?? 0), 0);
    this.totalCost    = this.summaries.reduce((s, d) => s + (d.costTnd      ?? 0), 0);
    this.alertCount   = this.alerts.length;

    const leakCount = this.rtData.filter(r => r.leak > 0).length;
    const trend     = this.summaries[0]?.trend ?? '+0.0%';

    const t = this.translate;
    const criticals = this.alerts.filter(a => a.severity === 'CRITICAL').length;
    this.kpiCards = [
      {
        label: t.instant('WATER.KPI_CONSUMPTION'), value: this.fmt(this.totalConsoM3, 3),
        unit: t.instant('WATER.KPI_CONSO_UNIT'), trend, trendGood: !trend.startsWith('+'),
        color: 'blue',
        icon: '<svg viewBox="0 0 24 24"><path d="M12 2c-5.33 4.55-8 8.48-8 11.8 0 4.98 3.8 8.2 8 8.2s8-3.22 8-8.2c0-3.32-2.67-7.25-8-11.8z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('WATER.KPI_CO2'), value: this.fmt(this.totalCo2, 2),
        unit: t.instant('WATER.KPI_CO2_UNIT'), trend, trendGood: !trend.startsWith('+'),
        color: 'orange',
        icon: '<svg viewBox="0 0 24 24"><path d="M17 8C8 10 5.9 16.17 3.82 21.34L5.71 22l1.03-2.41C8.63 20.14 10.28 20.5 12 20.5c4.42 0 8-3.58 8-8 0-1.5-.41-2.87-1-4.08z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('WATER.KPI_COST'), value: this.fmt(this.totalCost, 2),
        unit: 'TND', trend: t.instant('WATER.TARIF_INDICATIF'), trendGood: null,
        color: 'green',
        icon: '<svg viewBox="0 0 24 24"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('WATER.KPI_ALERTS'), value: String(this.alertCount),
        unit: t.instant('WATER.KPI_ALERTS_UNIT'),
        trend: this.alertCount === 0 ? t.instant('WATER.STATUS_NO_ALERT') : t.instant('WATER.STATUS_CRITICALS', { n: criticals }),
        trendGood: this.alertCount === 0,
        color: this.alertCount > 0 ? 'red' : 'green',
        icon: '<svg viewBox="0 0 24 24"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('WATER.KPI_LEAKS'), value: String(leakCount),
        unit: t.instant('WATER.KPI_LEAKS_UNIT'),
        trend: leakCount > 0 ? t.instant('WATER.LEAKS_WARN_SHORT') : t.instant('WATER.LEAKS_NONE'),
        trendGood: leakCount === 0,
        color: leakCount > 0 ? 'red' : 'green',
        icon: '<svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('WATER.KPI_INDEX'), value: this.fmt(this.rtData.reduce((s, r) => s + (r.wmIndex ?? 0), 0), 0),
        unit: t.instant('WATER.KPI_INDEX_UNIT'), trend: '—', trendGood: null,
        color: 'cyan',
        icon: '<svg viewBox="0 0 24 24"><path d="M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z" fill="currentColor"/></svg>'
      }
    ];
    this._buildKpiDefs();
  }

  private buildChartBars(): void {
    const pts = this.chart?.points ?? [];
    if (!pts.length) { this.chartBars = []; return; }
    this.chartBars = pts.map(p => ({
      label: p.label,
      conso: p.conso ?? 0,
      co2:   p.co2   ?? 0,
      debit: 0
    }));
    setTimeout(() => this.buildAllCharts(), 300);
  }

  // ── Chart.js builders ────────────────────────────────────────────────────

  private buildAllCharts(): void {
    this.zone.runOutsideAngular(() => {
      this.buildLineChart();
      this.buildDonutChart();
      this.buildBarCo2Chart();
      this.buildRadarChart();
      this.buildGroupedWaterBar();
      this.buildWaterDailyChart();
    });
    this.cdr.detectChanges();
  }

  private destroyChart(c: Chart | undefined): void { c?.destroy(); }

  private buildLineChart(): void {
    if (!this.lineCanvas) return;
    this.destroyChart(this.lineChart);
    const pts    = this.chart?.points ?? [];
    const labels = pts.map(p => p.label);
    const data   = pts.map(p => +(p.consoM3 ?? 0).toFixed(3));
    const cfg: ChartConfiguration<'line'> = {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: this.translate.instant('ENERGY.CONSO_M3'),
          data,
          borderColor:     PALETTE.water,
          backgroundColor: 'rgba(6,182,212,0.08)',
          borderWidth: 2,
          pointRadius: data.length > 20 ? 0 : 3,
          pointBackgroundColor: PALETTE.water,
          tension: 0.4,
          fill: true
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(6,12,26,0.95)',
            borderColor: PALETTE.waterDim, borderWidth: 1,
            titleColor: PALETTE.water, bodyColor: '#fff',
            callbacks: { label: ctx => ` ${ctx.parsed.y} m³` }
          }
        },
        scales: {
          x: { grid: { color: PALETTE.grid }, ticks: { color: PALETTE.text, maxTicksLimit: 8, font: { size: 10 } } },
          y: { grid: { color: PALETTE.grid }, ticks: { color: PALETTE.text, font: { size: 10 }, callback: v => v + ' m³' }, beginAtZero: true }
        }
      }
    };
    this.lineChart = new Chart(this.lineCanvas.nativeElement, cfg);
  }

  private buildDonutChart(): void {
    if (!this.donutCanvas || !this.summaries.length) return;
    this.destroyChart(this.donutChart);
    const colors = [PALETTE.water, PALETTE.cyan, PALETTE.green, PALETTE.teal, PALETTE.blue, PALETTE.lime];
    const cfg: ChartConfiguration<'doughnut'> = {
      type: 'doughnut',
      data: {
        labels: this.summaries.map(s => `#${s.idDevice}`),
        datasets: [{
          data:            this.summaries.map(s => +(s.totalConsoM3 ?? 0).toFixed(3)),
          backgroundColor: this.summaries.map((_, i) => colors[i % colors.length] + '99'),
          borderColor:     this.summaries.map((_, i) => colors[i % colors.length]),
          borderWidth: 2,
          hoverOffset: 6
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        cutout: '68%',
        plugins: {
          legend: { position: 'bottom', labels: { color: PALETTE.text, font: { size: 10 }, padding: 10, boxWidth: 10 } },
          tooltip: {
            backgroundColor: 'rgba(6,12,26,0.95)',
            borderColor: PALETTE.waterDim, borderWidth: 1,
            titleColor: PALETTE.water, bodyColor: '#fff',
            callbacks: { label: ctx => ` ${ctx.label} : ${ctx.parsed} m³` }
          }
        }
      }
    };
    this.donutChart = new Chart(this.donutCanvas.nativeElement, cfg);
  }

  private buildBarCo2Chart(): void {
    if (!this.barCo2Canvas || !this.summaries.length) return;
    this.destroyChart(this.barCo2Chart);
    const labels = this.summaries.map(s => `#${s.idDevice}`);
    const cfg: ChartConfiguration<'bar'> = {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: this.translate.instant('ENERGY.CO2_KG'),
            data: this.summaries.map(s => +(s.co2Kg ?? 0).toFixed(2)),
            backgroundColor: PALETTE.tealDim,
            borderColor:     PALETTE.teal,
            borderWidth: 1.5,
            borderRadius: 4
          },
          {
            label: this.translate.instant('ENERGY.COST_TND_LABEL'),
            data: this.summaries.map(s => +(s.costTnd ?? 0).toFixed(2)),
            backgroundColor: PALETTE.greenDim,
            borderColor:     PALETTE.green,
            borderWidth: 1.5,
            borderRadius: 4
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: PALETTE.text, font: { size: 10 }, boxWidth: 10 } },
          tooltip: {
            backgroundColor: 'rgba(6,12,26,0.95)',
            borderColor: PALETTE.grid, borderWidth: 1,
            titleColor: '#fff', bodyColor: PALETTE.text
          }
        },
        scales: {
          x: { grid: { color: PALETTE.grid }, ticks: { color: PALETTE.text, font: { size: 10 } } },
          y: { grid: { color: PALETTE.grid }, ticks: { color: PALETTE.text, font: { size: 10 } }, beginAtZero: true }
        }
      }
    };
    this.barCo2Chart = new Chart(this.barCo2Canvas.nativeElement, cfg);
  }

  private buildRadarChart(): void {
    if (!this.radarCanvas || !this.summaries.length) return;
    this.destroyChart(this.radarChart);
    const colors = [PALETTE.water, PALETTE.cyan, PALETTE.green, PALETTE.teal, PALETTE.blue];
    const maxConso = Math.max(...this.summaries.map(s => s.totalConsoM3 ?? 0), 1);
    const maxCo2   = Math.max(...this.summaries.map(s => s.co2Kg        ?? 0), 1);
    const maxCost  = Math.max(...this.summaries.map(s => s.costTnd      ?? 0), 1);
    const maxAlert = Math.max(...this.summaries.map(s => s.alertCount   ?? 0), 1);
    const cfg: ChartConfiguration<'radar'> = {
      type: 'radar',
      data: {
        labels: [this.translate.instant('ENERGY.CONSO_M3'), this.translate.instant('ENERGY.CO2_KG'), this.translate.instant('ENERGY.COST_TND_LABEL'), this.translate.instant('ENERGY.RADAR_ALERTS'), this.translate.instant('ENERGY.RADAR_LEAKS')],
        datasets: this.summaries.slice(0, 5).map((s, i) => ({
          label: this.translate.instant('KPI_PANEL.DEVICE_PREFIX') + s.idDevice,
          data: [
            +((s.totalConsoM3 ?? 0) / maxConso * 100).toFixed(1),
            +((s.co2Kg        ?? 0) / maxCo2   * 100).toFixed(1),
            +((s.costTnd      ?? 0) / maxCost  * 100).toFixed(1),
            +((s.alertCount   ?? 0) / maxAlert * 100).toFixed(1),
            (s.leakCount ?? 0) > 0 ? 100 : 0
          ],
          borderColor:     colors[i % colors.length],
          backgroundColor: colors[i % colors.length] + '22',
          borderWidth: 1.5,
          pointBackgroundColor: colors[i % colors.length],
          pointRadius: 3
        }))
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { color: PALETTE.text, font: { size: 10 }, boxWidth: 10 } },
          tooltip: {
            backgroundColor: 'rgba(6,12,26,0.95)',
            borderColor: PALETTE.grid, borderWidth: 1,
            titleColor: '#fff', bodyColor: PALETTE.text
          }
        },
        scales: {
          r: {
            grid:      { color: PALETTE.grid },
            angleLines: { color: PALETTE.grid },
            ticks:     { color: PALETTE.text, font: { size: 9 }, backdropColor: 'transparent', stepSize: 25 },
            pointLabels: { color: PALETTE.text, font: { size: 10 } },
            min: 0, max: 100
          }
        }
      }
    };
    this.radarChart = new Chart(this.radarCanvas.nativeElement, cfg);
  }

  get chartMax(): number {
    if (!this.chartBars.length) return 100;
    return Math.max(...this.chartBars.map(b => b.conso), 1);
  }

  barH(v: number): number { return Math.round((v / this.chartMax) * 100); }

  get rtForTable(): RtWmDto[] { return this.rtData.slice(0, 20); }

  /** Normalise le niveau batterie IoT (255 = alimentation externe = 100%) */
  normBatt(v: number | null | undefined): number {
    if (v == null) return 0;
    if (v >= 200)  return 100;   // 255 = alimentation externe / full
    return Math.min(v, 100);
  }

  statusClass(s: string): string {
    return s === 'OK' ? 'status-ok' : (s === 'LEAK' || s === 'FRAUD') ? 'status-alert' : 'status-warn';
  }

  alertClass(s: string): string {
    return 'sev-' + s.toLowerCase();
  }

  alertIcon(type: string): string {
    const m: Record<string, string> = { LEAK: '💧', FRAUD: '⚠', HIGH_CONSO: '📈', LOW_BATTERY: '🔋' };
    return m[type] ?? '⚠';
  }

  recommendation(type: string): string {
    const m: Record<string, string> = {
      LEAK:        this.translate.instant('WATER.REC_LEAK'),
      FRAUD:       this.translate.instant('WATER.REC_FRAUD'),
      HIGH_CONSO:  this.translate.instant('WATER.REC_HIGH_CONSO'),
      LOW_BATTERY: this.translate.instant('WATER.REC_LOW_BATTERY')
    };
    return m[type] ?? this.translate.instant('WATER.REC_DEFAULT');
  }

  countBySeverity(sev: string): number { return this.alerts.filter(a => a.severity === sev).length; }

  get leakCount(): number { return this.rtData.filter(r => r.leak > 0).length; }
  get totalIndex(): number { return this.rtData.reduce((s, r) => s + (r.wmIndex ?? 0), 0); }

  get chartTotalConso(): string { return ((this.chart?.totalConsoM3 ?? 0)).toFixed(3); }
  get chartTotalCo2():   string { return (this.chart?.totalCo2  ?? 0).toFixed(2); }
  get chartTotalCost():  string { return (this.chart?.totalCost ?? 0).toFixed(2); }

  fmtAlertDate(d: string): string {
    if (!d) return '—';
    const dt = new Date(d);
    const dd = String(dt.getDate()).padStart(2,'0');
    const mm = String(dt.getMonth()+1).padStart(2,'0');
    const hh = String(dt.getHours()).padStart(2,'0');
    const mn = String(dt.getMinutes()).padStart(2,'0');
    return `${dd}/${mm} ${hh}:${mn}`;
  }

  private get locale(): string {
    const l = this.translate.currentLang ?? 'fr';
    return l === 'ar' ? 'ar-TN' : l === 'en' ? 'en-US' : 'fr-FR';
  }

  fmt(n: number, dec = 0): string {
    if (n == null || isNaN(n)) return '0';
    return n.toLocaleString(this.locale, { minimumFractionDigits: dec, maximumFractionDigits: dec });
  }

  private fmtDateLabel(d: string): string {
    if (!d) return '';
    const p = d.substring(0,10).split('-');
    return p.length === 3 ? `${p[2]}/${p[1]}` : d;
  }

  private updateDateRange(from: Date, to: Date): void {
    const o: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', year: 'numeric' };
    this.dataRange = `${from.toLocaleDateString(this.locale, o)} → ${to.toLocaleDateString(this.locale, o)}`;
  }

  private buildGroupedWaterBar(): void {
    if (!this.groupedBarCanvas || !this.summaries.length) return;
    this.destroyChart(this.groupedBarChart);
    const colors = [PALETTE.water, PALETTE.cyan, PALETTE.green, PALETTE.teal, PALETTE.blue, PALETTE.lime];
    const labels = this.summaries.map(s => `#${s.idDevice}`);
    const cfg: ChartConfiguration<'bar'> = {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: this.translate.instant('ENERGY.CONSO_M3'),
          data: this.summaries.map(s => +(s.totalConsoM3 ?? 0).toFixed(3)),
          backgroundColor: this.summaries.map((_, i) => colors[i % colors.length] + '55'),
          borderColor:     this.summaries.map((_, i) => colors[i % colors.length]),
          borderWidth: 1.5,
          borderRadius: 5,
          borderSkipped: false
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(6,12,26,0.95)',
            borderColor: PALETTE.waterDim, borderWidth: 1,
            titleColor: PALETTE.water, bodyColor: '#fff',
            callbacks: { label: ctx => ` ${ctx.parsed.x.toFixed(3)} m³` }
          }
        },
        scales: {
          x: {
            grid: { color: PALETTE.grid },
            ticks: { color: PALETTE.text, font: { size: 10 }, callback: v => v + ' m³' },
            beginAtZero: true
          },
          y: {
            grid: { color: 'transparent' },
            ticks: { color: PALETTE.text, font: { size: 11, weight: 'bold' } }
          }
        }
      }
    };
    this.groupedBarChart = new Chart(this.groupedBarCanvas.nativeElement, cfg);
  }

  private buildWaterDailyChart(): void {
    if (!this.wDailyCanvas) return;
    this.wDailyChart?.destroy();
    const pts = this.chart?.points ?? [];
    const cfg: ChartConfiguration<'bar'> = {
      type: 'bar',
      data: {
        labels: pts.map(p => p.label),
        datasets: [{
          label: this.translate.instant('WATER.KPI_CONSUMPTION'),
          data: pts.map(p => +((p.consoM3 ?? (p.conso ?? 0) / 1000)).toFixed(3)),
          backgroundColor: 'rgba(6,182,212,0.35)',
          borderColor: PALETTE.water,
          borderWidth: 1.5,
          borderRadius: 4,
          borderSkipped: false
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { backgroundColor: 'rgba(6,12,26,0.95)', titleColor: PALETTE.water, bodyColor: '#fff', callbacks: { label: ctx => ` ${ctx.parsed.y} m³` } }
        },
        scales: {
          x: { grid: { color: PALETTE.grid }, ticks: { color: PALETTE.text, maxTicksLimit: 15, font: { size: 10 } } },
          y: { grid: { color: PALETTE.grid }, ticks: { color: PALETTE.text, font: { size: 10 }, callback: v => v + ' m³' }, beginAtZero: true }
        }
      }
    };
    this.wDailyChart = new Chart(this.wDailyCanvas.nativeElement, cfg);
  }

  openChartModal(type: 'evolution' | 'co2cost' | 'consoByMeter' = 'evolution'): void {
    this.chartModalType  = type;
    this.chartModalTitle = type === 'co2cost'      ? this.translate.instant('ENERGY.CO2_COST_PER_METER')
                         : type === 'consoByMeter' ? this.translate.instant('ENERGY.CONSO_BY_METER')
                         :                           this.translate.instant('ENERGY.EVOLUTION') + ' — m³';
    this.chartModalBadge = type === 'evolution' ? 'Ligne' : 'Barres';
    this.chartModalOpen = true;
    document.addEventListener('keydown', this.onEscKey);
    setTimeout(() => this.initModalChart(), 80);
  }

  closeChartModal(): void {
    this.chartModalOpen = false;
    document.removeEventListener('keydown', this.onEscKey);
    this.modalChart?.destroy();
    this.modalChart = null;
  }

  handleChartModalBackdrop(e: MouseEvent): void {
    if ((e.target as HTMLElement).classList.contains('water-chart-modal-backdrop')) {
      this.closeChartModal();
    }
  }

  private initModalChart(): void {
    const canvas = this.modalChartCanvasRef?.nativeElement;
    if (!canvas) return;
    this.modalChart?.destroy();
    this.modalChart = null;
    this.zone.runOutsideAngular(() => {
      if (this.chartModalType === 'co2cost')      this.buildModalBarCo2(canvas);
      else if (this.chartModalType === 'consoByMeter') this.buildModalGroupedBar(canvas);
      else                                         this.buildModalEvolution(canvas);
    });
  }

  private buildModalEvolution(canvas: HTMLCanvasElement): void {
    const pts = this.chart?.points ?? [];
    if (!pts.length) return;
    const ctx = canvas.getContext('2d')!;
    const h   = canvas.parentElement?.clientHeight || 320;
    const gr  = ctx.createLinearGradient(0, 0, 0, h);
    gr.addColorStop(0,   'rgba(6,182,212,0.35)');
    gr.addColorStop(0.6, 'rgba(6,182,212,0.08)');
    gr.addColorStop(1,   'rgba(6,182,212,0.00)');

    this.modalChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels:   pts.map(p => p.label),
        datasets: [{
          label:               'm³',
          data:                pts.map(p => +(p.consoM3 ?? 0).toFixed(3)),
          borderColor:         PALETTE.water,
          backgroundColor:     gr,
          borderWidth:         2.5,
          tension:             0.42,
          fill:                true,
          pointRadius:         pts.length > 30 ? 0 : 4,
          pointHoverRadius:    8,
          pointBackgroundColor: PALETTE.water,
          pointBorderColor:    'rgba(6,182,212,0.25)',
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
            backgroundColor: 'rgba(6,12,26,0.95)',
            titleColor: PALETTE.water, bodyColor: '#fff',
            borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1,
            padding: 14, cornerRadius: 12,
            callbacks: { label: (ctx: any) => ` ${ctx.parsed.y.toFixed(3)} m³` }
          }
        },
        scales: {
          x: {
            grid:  { color: PALETTE.grid },
            ticks: { color: PALETTE.text, maxTicksLimit: 12, font: { size: 10 } }
          },
          y: {
            grid:  { color: PALETTE.grid },
            ticks: { color: PALETTE.text, font: { size: 10 }, padding: 8, callback: (v: any) => v + ' m³' },
            beginAtZero: true,
            title: { display: true, text: 'm³', color: 'rgba(255,255,255,0.3)', font: { size: 10 } }
          }
        }
      }
    });
  }

  private buildModalBarCo2(canvas: HTMLCanvasElement): void {
    if (!this.summaries.length) return;
    this.modalChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: this.summaries.map(s => `#${s.idDevice}`),
        datasets: [
          {
            label: this.translate.instant('ENERGY.CO2_KG'),
            data: this.summaries.map(s => +(s.co2Kg ?? 0).toFixed(2)),
            backgroundColor: 'rgba(13,148,136,0.25)',
            borderColor: PALETTE.teal,
            borderWidth: 2, borderRadius: 6,
            hoverBackgroundColor: 'rgba(13,148,136,0.45)'
          },
          {
            label: this.translate.instant('ENERGY.COST_TND_LABEL'),
            data: this.summaries.map(s => +(s.costTnd ?? 0).toFixed(2)),
            backgroundColor: PALETTE.greenDim,
            borderColor: PALETTE.green,
            borderWidth: 2, borderRadius: 6,
            hoverBackgroundColor: 'rgba(16,185,129,0.4)'
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 600 } as any,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: true, position: 'top', labels: { color: PALETTE.text, font: { size: 11 }, boxWidth: 10, boxHeight: 10, padding: 16, usePointStyle: true } },
          tooltip: {
            backgroundColor: 'rgba(6,12,26,0.95)', titleColor: '#fff', bodyColor: PALETTE.text,
            borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, padding: 14, cornerRadius: 12,
            callbacks: { label: (ctx: any) => { const u = ctx.datasetIndex === 0 ? ' kgCO₂' : ' TND'; return ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)}${u}`; } }
          }
        },
        scales: {
          x: { grid: { color: PALETTE.grid }, ticks: { color: PALETTE.text, font: { size: 10 } } },
          y: { grid: { color: PALETTE.grid }, ticks: { color: PALETTE.text, font: { size: 10 }, padding: 8 }, beginAtZero: true }
        }
      }
    });
  }

  private buildModalGroupedBar(canvas: HTMLCanvasElement): void {
    if (!this.summaries.length) return;
    const colors = [PALETTE.water, PALETTE.cyan, PALETTE.green, PALETTE.teal, PALETTE.blue, PALETTE.lime];
    this.modalChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: this.summaries.map(s => `#${s.idDevice}`),
        datasets: [{
          label: this.translate.instant('ENERGY.CONSO_M3'),
          data: this.summaries.map(s => +(s.totalConsoM3 ?? 0).toFixed(3)),
          backgroundColor: this.summaries.map((_, i) => colors[i % colors.length] + '55'),
          borderColor:     this.summaries.map((_, i) => colors[i % colors.length]),
          borderWidth: 2, borderRadius: 6, borderSkipped: false
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 600 } as any,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(6,12,26,0.95)', titleColor: PALETTE.water, bodyColor: '#fff',
            borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, padding: 14, cornerRadius: 12,
            callbacks: { label: (ctx: any) => ` ${ctx.parsed.x.toFixed(3)} m³` }
          }
        },
        scales: {
          x: { grid: { color: PALETTE.grid }, ticks: { color: PALETTE.text, font: { size: 10 }, callback: (v: any) => v + ' m³' }, beginAtZero: true },
          y: { grid: { color: 'transparent' }, ticks: { color: PALETTE.text, font: { size: 11, weight: 'bold' } } }
        }
      }
    });
  }

  navigateTo(p: string): void { this.router.navigate([p]); }
  goBack(): void { this.router.navigate(['/dashboard']); }

  // ── KPI Detail Panel ──────────────────────────────────────────
  selectedKpi: string | null = null;
  openKpi(key: string): void { this.selectedKpi = key; this.currentKpiDef = this.kpiDefs[key] ?? null; }
  closeKpi(): void { this.selectedKpi = null; this.currentKpiDef = null; }

  kpiDefs: Record<string, any> = {};
  currentKpiDef: any = null;

  private _buildPeriodOptions(): void {
    const t = this.translate;
    this.periodOptions = [
      { label: t.instant('ENERGY.PERIOD_24H'), value: 1  },
      { label: t.instant('ENERGY.PERIOD_7D'),  value: 7  },
      { label: t.instant('ENERGY.PERIOD_30D'), value: 30 },
      { label: t.instant('ENERGY.PERIOD_3M'),  value: 90 },
    ];
  }

  private _buildKpiDefs(): void {
    const t = this.translate;
    const leakCount  = this.rtData.filter(r => r.leak > 0).length;
    const totalIndex = this.rtData.reduce((s, r) => s + (r.wmIndex ?? 0), 0);
    const criticals  = this.countBySeverity('CRITICAL');
    this.kpiDefs = {
      conso: {
        title: t.instant('WATER.KPI_CONSUMPTION') + ' (m³)',
        accent: '#06b6d4',
        value: this.fmt(this.totalConsoM3, 3),
        unit: 'm³',
        definition: t.instant('WATER.DEF_CONSO'),
        why: t.instant('WATER.WHY_CONSO'),
        threshold: null, thresholdLabel: null,
        gaugePercent: Math.min(this.totalConsoM3 / ((this.summaries.length * 500) || 1) * 100, 100),
        status: null, statusLabel: null,
        recommendations: [t.instant('WATER.KPI_REC_CONSO_1'), t.instant('WATER.KPI_REC_CONSO_2'), t.instant('WATER.KPI_REC_CONSO_3')],
        devices: this.summaries.map(s => ({ id: s.idDevice, val: (s.totalConsoM3 ?? 0).toFixed(3), unit: 'm³', ok: true, badge: s.alertCount > 0 ? 'ALERTE' : 'OK' }))
      },
      co2: {
        title: t.instant('WATER.KPI_CO2') + ' (kgCO₂)',
        accent: '#0d9488',
        value: this.fmt(this.totalCo2, 2),
        unit: 'kgCO₂',
        definition: t.instant('WATER.DEF_CO2'),
        why: t.instant('WATER.WHY_CO2'),
        threshold: null, thresholdLabel: t.instant('WATER.FACTOR_CO2'),
        gaugePercent: Math.min(this.totalCo2 / ((this.summaries.length * 150) || 1) * 100, 100),
        status: null, statusLabel: null,
        recommendations: [t.instant('WATER.KPI_REC_CO2_1'), t.instant('WATER.KPI_REC_CO2_2'), t.instant('WATER.KPI_REC_CO2_3')],
        devices: this.summaries.map(s => ({ id: s.idDevice, val: (s.co2Kg ?? 0).toFixed(2), unit: 'kg', ok: true, badge: s.alertCount > 0 ? 'ALERTE' : 'OK' }))
      },
      cost: {
        title: t.instant('WATER.KPI_COST') + ' (TND)',
        accent: '#10b981',
        value: this.fmt(this.totalCost, 2),
        unit: 'TND',
        definition: t.instant('WATER.DEF_COST'),
        why: t.instant('WATER.WHY_COST'),
        threshold: null, thresholdLabel: t.instant('WATER.FACTOR_COST'),
        gaugePercent: Math.min(this.totalCost / ((this.summaries.length * 200) || 1) * 100, 100),
        status: null, statusLabel: null,
        recommendations: [t.instant('WATER.KPI_REC_COST_1'), t.instant('WATER.KPI_REC_COST_2'), t.instant('WATER.KPI_REC_COST_3')],
        devices: this.summaries.map(s => ({ id: s.idDevice, val: (s.costTnd ?? 0).toFixed(2), unit: 'TND', ok: true, badge: s.alertCount > 0 ? 'ALERTE' : 'OK' }))
      },
      alerts: {
        title: t.instant('WATER.KPI_ALERTS'),
        accent: '#ef4444',
        value: String(this.alertCount),
        unit: t.instant('COMMON.ALERTS'),
        definition: t.instant('WATER.DEF_ALERTS'),
        why: t.instant('WATER.WHY_ALERTS'),
        threshold: 0, thresholdLabel: t.instant('WATER.THRESHOLD_LEAKS'),
        gaugePercent: Math.min(this.alertCount / 10 * 100, 100),
        status: this.alertCount === 0 ? 'ok' : 'warn',
        statusLabel: this.alertCount === 0 ? t.instant('WATER.STATUS_NO_ALERT') : t.instant('WATER.STATUS_CRITICALS', { n: criticals }),
        recommendations: [t.instant('WATER.KPI_REC_ALERTS_1'), t.instant('WATER.KPI_REC_ALERTS_2'), t.instant('WATER.KPI_REC_ALERTS_3')],
        devices: this.alerts.slice(0, 10).map(a => ({ id: a.idDevice, val: a.type, unit: '', ok: a.severity !== 'CRITICAL', badge: a.severity }))
      },
      leaks: {
        title: t.instant('WATER.KPI_LEAKS'),
        accent: leakCount > 0 ? '#ef4444' : '#10b981',
        value: String(leakCount),
        unit: t.instant('COMMON.METERS'),
        definition: t.instant('WATER.DEF_LEAKS'),
        why: t.instant('WATER.WHY_LEAKS'),
        threshold: 0, thresholdLabel: t.instant('WATER.THRESHOLD_LEAKS'),
        gaugePercent: Math.min(leakCount / (this.rtData.length || 1) * 100, 100),
        status: leakCount === 0 ? 'ok' : 'danger',
        statusLabel: leakCount === 0 ? t.instant('WATER.LEAKS_OK') : t.instant('WATER.LEAKS_WARN'),
        recommendations: [t.instant('WATER.KPI_REC_LEAKS_1'), t.instant('WATER.KPI_REC_LEAKS_2'), t.instant('WATER.KPI_REC_LEAKS_3')],
        devices: this.rtData.filter(r => r.leak > 0).map(r => ({ id: r.idDevice, val: t.instant('ENERGY.FLAG_YES'), unit: '', ok: false, badge: 'CRITICAL' }))
      },
      index: {
        title: t.instant('WATER.KPI_INDEX'),
        accent: '#0ea5e9',
        value: this.fmt(totalIndex, 0),
        unit: 'L',
        definition: t.instant('WATER.DEF_INDEX'),
        why: t.instant('WATER.WHY_INDEX'),
        threshold: null, thresholdLabel: null,
        gaugePercent: 50,
        status: null, statusLabel: null,
        recommendations: [t.instant('WATER.KPI_REC_INDEX_1'), t.instant('WATER.KPI_REC_INDEX_2'), t.instant('WATER.KPI_REC_INDEX_3')],
        devices: this.rtData.slice(0, 10).map(r => ({ id: r.idDevice, val: (r.wmIndex ?? 0).toLocaleString(this.locale), unit: 'L', ok: r.leak === 0 && r.fraud === 0, badge: r.status ?? 'OK' }))
      }
    };
    if (this.selectedKpi) this.currentKpiDef = this.kpiDefs[this.selectedKpi] ?? null;
  }
}
