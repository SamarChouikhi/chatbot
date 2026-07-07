import { Component, OnInit, OnDestroy, AfterViewInit, ViewChild, ElementRef, NgZone } from '@angular/core';
import { Router } from '@angular/router';
import { Subject, forkJoin } from 'rxjs';
import { ChatTriggerService } from '../core/services/chat-trigger.service';
import { takeUntil, finalize } from 'rxjs/operators';
import { TranslateService } from '@ngx-translate/core';
import {
  FuelService, FuelSummaryDto, FuelAlertDto, FuelLatestDto
} from '../services/fuel.service';
import {
  Chart, ChartConfiguration,
  BarController, DoughnutController, RadarController,
  CategoryScale, LinearScale, RadialLinearScale,
  PointElement, LineElement, BarElement, ArcElement,
  Tooltip, Legend
} from 'chart.js';

Chart.register(
  BarController, DoughnutController, RadarController,
  CategoryScale, LinearScale, RadialLinearScale,
  PointElement, LineElement, BarElement, ArcElement,
  Tooltip, Legend
);

const FP = {
  main: '#22c55e', mainDim: 'rgba(34,197,94,0.15)',
  cyan: '#06b6d4', cyanDim: 'rgba(6,182,212,0.15)',
  green: '#10b981', greenDim: 'rgba(16,185,129,0.15)',
  teal: '#0d9488', tealDim: 'rgba(13,148,136,0.15)',
  blue: '#0ea5e9', blueDim: 'rgba(14,165,233,0.15)',
  deepBlue: '#0369a1',
  red: '#e74c3c',
  grid: 'rgba(255,255,255,0.06)', text: 'rgba(255,255,255,0.45)'
};

interface KpiCard {
  label: string; value: string; unit: string;
  trend: string; trendGood: boolean | null;
  color: 'blue' | 'green' | 'orange' | 'red' | 'cyan' | 'amber';
  icon: string;
}

@Component({
  selector: 'app-fuel',
  templateUrl: './fuel.component.html',
  styleUrls: ['./fuel.component.scss']
})
export class FuelComponent implements OnInit, OnDestroy, AfterViewInit {

  @ViewChild('fDonutCanvas')   fDonutCanvas!:   ElementRef<HTMLCanvasElement>;
  @ViewChild('fBarCanvas')     fBarCanvas!:     ElementRef<HTMLCanvasElement>;
  @ViewChild('fRadarCanvas')   fRadarCanvas!:   ElementRef<HTMLCanvasElement>;
  @ViewChild('fModalCanvas')   fModalCanvas!:   ElementRef<HTMLCanvasElement>;

  private fDonutChart:   any = null;
  private fBarChart:     any = null;
  private fRadarChart:   any = null;
  private fModalChart:   any = null;

  isLoading        = false;
  loadError        = false;

  selectedPeriod = 30;
  periodOptions: { label: string; value: number }[] = [];
  dataRange = '';

  summaries: FuelSummaryDto[] = [];
  alerts:    FuelAlertDto[]   = [];
  latest:    FuelLatestDto[]  = [];

  kpiCards:  KpiCard[] = [];
  kpiDefs:   Record<string, any> = {};

  totalConsoL      = 0;
  totalDistanceKm  = 0;
  totalCo2         = 0;
  totalCost        = 0;
  alertCount       = 0;

  chartModalOpen = false;

  private destroy$ = new Subject<void>();

  private onEscKey = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') this.closeChartModal();
  };

  constructor(private fuelSvc: FuelService, private router: Router, private zone: NgZone, private translate: TranslateService, private chatTrigger: ChatTriggerService) {}

  openAriaInsight(section: string, event: MouseEvent): void {
    event.stopPropagation();
    const p = this.selectedPeriod;
    const prompts: Record<string, string> = {
      summary: `Analyse les statistiques Carburant (${p}j) :\n` +
        `Consommation : ${this.totalConsoL.toFixed(1)} L | Distance : ${this.totalDistanceKm.toFixed(0)} km\n` +
        `CO₂ émis : ${this.totalCo2.toFixed(1)} kgCO₂ | Coût : ${this.totalCost.toFixed(2)} TND\n` +
        `Alertes : ${this.alertCount} | Véhicules actifs : ${this.summaries.length}\n` +
        `Est-ce normal, préoccupant ou excellent ? Réponds en 2-3 lignes.`,

      stats: `Analyse les graphiques statistiques Carburant (${p}j) :\n` +
        `Total consommé : ${this.totalConsoL.toFixed(1)} L sur ${this.summaries.length} véhicule(s)\n` +
        `Distance : ${this.totalDistanceKm.toFixed(0)} km · CO₂ : ${this.totalCo2.toFixed(1)} kg\n` +
        `Identifie les véhicules les plus consommateurs et les inefficacités.`,

      quality: `Analyse le résumé par véhicule Carburant (${p}j) :\n` +
        `${this.summaries.length} véhicule(s) · Distance totale : ${this.totalDistanceKm.toFixed(0)} km\n` +
        `Ratio moyen : ${this.totalDistanceKm > 0 ? ((this.totalConsoL / this.totalDistanceKm) * 100).toFixed(1) : 'N/A'} L/100km\n` +
        `Donne un diagnostic d'efficacité de la flotte.`,

      alerts: `Analyse les alertes carburant actives (${p}j) :\n` +
        `Total : ${this.alertCount} alerte(s) · Véhicules : ${this.summaries.length}\n` +
        `Quelles sont les actions prioritaires à mener ?`,
    };
    this.chatTrigger.open(prompts[section] ?? `Analyse Carburant — ${section} — ${p}j.`);
  }

  ngOnInit(): void {
    this.dataRange = this.translate.instant('COMMON.LOADING');
    this._buildPeriodOptions();
    this.load();
    this.translate.onLangChange.pipe(takeUntil(this.destroy$)).subscribe(() => {
      this._buildPeriodOptions();
      const { from, to } = this.fuelSvc.getLastNDaysRange(this.selectedPeriod);
      this.updateDateRange(from, to);
      this.buildKpi();
      this.buildAllFuelCharts();
    });
  }
  ngAfterViewInit(): void {}
  ngOnDestroy(): void {
    this.destroy$.next(); this.destroy$.complete();
    document.removeEventListener('keydown', this.onEscKey);
    [this.fDonutChart, this.fBarChart, this.fRadarChart, this.fModalChart]
      .forEach((c: any) => c?.destroy());
  }

  load(): void {
    this.isLoading = true;
    this.loadError = false;
    const { from, to } = this.fuelSvc.getLastNDaysRange(this.selectedPeriod);
    this.updateDateRange(from, to);

    forkJoin({
      summaries: this.fuelSvc.getAllSummaries(from, to),
      alerts:    this.fuelSvc.getAlerts(),
      latest:    this.fuelSvc.getAllLatest()
    })
    .pipe(takeUntil(this.destroy$), finalize(() => this.isLoading = false))
    .subscribe({
      next: ({ summaries, alerts, latest }) => {
        this.summaries = summaries;
        this.alerts    = alerts;
        this.latest    = latest;
        this.buildKpi();
        setTimeout(() => this.buildAllFuelCharts(), 300);
      },
      error: () => { this.loadError = true; }
    });
  }

  onPeriodChange(period: number): void { this.selectedPeriod = period; this.load(); }

  private buildKpi(): void {
    this.totalConsoL     = this.summaries.reduce((s, d) => s + (d.totalConsoL     ?? 0), 0);
    this.totalDistanceKm = this.summaries.reduce((s, d) => s + (d.totalDistanceKm ?? 0), 0);
    this.totalCo2        = this.summaries.reduce((s, d) => s + (d.co2Kg           ?? 0), 0);
    this.totalCost       = this.summaries.reduce((s, d) => s + (d.costTnd         ?? 0), 0);
    this.alertCount      = this.alerts.length;

    const t        = this.translate;
    const trend    = this.summaries[0]?.trend ?? '+0.0%';
    const avgEff   = this.totalDistanceKm > 0 ? (this.totalConsoL / this.totalDistanceKm) * 100 : 0;
    const criticals = this.alerts.filter(a => a.severity === 'CRITICAL').length;

    this.kpiCards = [
      {
        label: t.instant('FUEL.KPI_CONSUMPTION'), value: this.fmt(this.totalConsoL, 1),
        unit: t.instant('FUEL.KPI_CONSO_UNIT'), trend, trendGood: !trend.startsWith('+'),
        color: 'amber',
        icon: '<svg viewBox="0 0 24 24"><path d="M19.77 7.23l.01-.01-3.72-3.72L15 4.56l2.11 2.11c-.94.36-1.61 1.26-1.61 2.33 0 1.38 1.12 2.5 2.5 2.5.36 0 .69-.08 1-.21v7.21c0 .55-.45 1-1 1s-1-.45-1-1V14c0-1.1-.9-2-2-2h-1V5c0-1.1-.9-2-2-2H6c-1.1 0-2 .9-2 2v16h10v-7.5h1.5v5c0 1.38 1.12 2.5 2.5 2.5s2.5-1.12 2.5-2.5V9c0-.69-.28-1.32-.73-1.77zM18 10c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zM8 18v-4.5H6L11 7v4.5h2L8 18z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('FUEL.KPI_DISTANCE'), value: this.fmt(this.totalDistanceKm, 1),
        unit: t.instant('FUEL.KPI_DIST_UNIT'), trend, trendGood: trend.startsWith('+'),
        color: 'blue',
        icon: '<svg viewBox="0 0 24 24"><path d="M21 3L3 10.53v.98l6.84 2.65L12.48 21h.98L21 3z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('FUEL.KPI_CO2'), value: this.fmt(this.totalCo2, 1),
        unit: t.instant('FUEL.KPI_CO2_UNIT'), trend, trendGood: !trend.startsWith('+'),
        color: 'orange',
        icon: '<svg viewBox="0 0 24 24"><path d="M17 8C8 10 5.9 16.17 3.82 21.34L5.71 22l1.03-2.41C8.63 20.14 10.28 20.5 12 20.5c4.42 0 8-3.58 8-8 0-1.5-.41-2.87-1-4.08z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('FUEL.KPI_COST'), value: this.fmt(this.totalCost, 2),
        unit: t.instant('FUEL.KPI_COST_UNIT'), trend: t.instant('FUEL.TARIF_INDICATIF'), trendGood: null,
        color: 'green',
        icon: '<svg viewBox="0 0 24 24"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('FUEL.KPI_EFFICIENCY'), value: this.fmt(avgEff, 1),
        unit: t.instant('FUEL.KPI_EFF_UNIT'),
        trend: avgEff > 15 ? t.instant('FUEL.EFF_WARN') : t.instant('FUEL.EFF_OK'),
        trendGood: avgEff <= 15 && avgEff > 0,
        color: avgEff > 15 ? 'red' : 'cyan',
        icon: '<svg viewBox="0 0 24 24"><path d="M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z" fill="currentColor"/></svg>'
      },
      {
        label: t.instant('FUEL.KPI_ALERTS'), value: String(this.alertCount),
        unit: t.instant('FUEL.KPI_ALERTS_UNIT'),
        trend: this.alertCount === 0 ? t.instant('FUEL.STATUS_NO_ALERT') : t.instant('FUEL.STATUS_CRITICALS', { n: criticals }),
        trendGood: this.alertCount === 0,
        color: this.alertCount > 0 ? 'red' : 'green',
        icon: '<svg viewBox="0 0 24 24"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" fill="currentColor"/></svg>'
      }
    ];

    this._buildKpiDefs();
  }

  get consoGaugeWidth(): string {
    const max = (this.summaries.length * 500) || 1;
    return Math.min(this.totalCo2 / max * 100, 100).toFixed(1) + '%';
  }

  get effGaugeWidth(): string {
    const avgEff = this.totalDistanceKm > 0 ? (this.totalConsoL / this.totalDistanceKm) * 100 : 0;
    return Math.min(avgEff / 20 * 100, 100).toFixed(1) + '%';
  }

  private buildAllFuelCharts(): void {
    this.zone.runOutsideAngular(() => {
      this.buildFuelDonut();
      this.buildFuelBar();
      this.buildFuelRadar();
    });
  }

  private buildFuelDonut(): void {
    if (!this.fDonutCanvas || !this.summaries.length) return;
    this.fDonutChart?.destroy();
    const colors = [FP.main, FP.cyan, FP.green, FP.teal, FP.blue, FP.deepBlue];
    const cfg: ChartConfiguration<'doughnut'> = {
      type: 'doughnut',
      data: {
        labels: this.summaries.map(s => `#${s.deviceId}`),
        datasets: [{
          data: this.summaries.map(s => +(s.totalConsoL ?? 0).toFixed(1)),
          backgroundColor: this.summaries.map((_, i) => colors[i % colors.length] + '99'),
          borderColor: this.summaries.map((_, i) => colors[i % colors.length]),
          borderWidth: 2, hoverOffset: 6
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '68%',
        plugins: {
          legend: { position: 'bottom', labels: { color: FP.text, font: { size: 10 }, padding: 10, boxWidth: 10 } },
          tooltip: { backgroundColor: 'rgba(6,12,26,0.95)', titleColor: FP.main, bodyColor: '#fff',
            callbacks: { label: (ctx: any) => ` ${ctx.label} : ${ctx.parsed} L` } }
        }
      }
    };
    this.fDonutChart = new Chart(this.fDonutCanvas.nativeElement, cfg);
  }

  private buildFuelBar(): void {
    if (!this.fBarCanvas || !this.summaries.length) return;
    this.fBarChart?.destroy();
    const cfg: ChartConfiguration<'bar'> = {
      type: 'bar',
      data: {
        labels: this.summaries.map(s => `#${s.deviceId}`),
        datasets: [
          {
            label: this.translate.instant('ENERGY.CO2_KG'),
            data: this.summaries.map(s => +(s.co2Kg ?? 0).toFixed(2)),
            backgroundColor: FP.tealDim, borderColor: FP.teal, borderWidth: 1.5, borderRadius: 4
          },
          {
            label: this.translate.instant('ENERGY.COST_TND_LABEL'),
            data: this.summaries.map(s => +(s.costTnd ?? 0).toFixed(2)),
            backgroundColor: FP.greenDim, borderColor: FP.green, borderWidth: 1.5, borderRadius: 4
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: FP.text, font: { size: 10 }, boxWidth: 10 } },
          tooltip: { backgroundColor: 'rgba(6,12,26,0.95)', titleColor: '#fff', bodyColor: FP.text }
        },
        scales: {
          x: { grid: { color: FP.grid }, ticks: { color: FP.text, font: { size: 10 } } },
          y: { grid: { color: FP.grid }, ticks: { color: FP.text, font: { size: 10 } }, beginAtZero: true }
        }
      }
    };
    this.fBarChart = new Chart(this.fBarCanvas.nativeElement, cfg);
  }

  private buildFuelRadar(): void {
    if (!this.fRadarCanvas || !this.summaries.length) return;
    this.fRadarChart?.destroy();
    const colors = [FP.main, FP.cyan, FP.green, FP.teal, FP.blue];
    const maxConso = Math.max(...this.summaries.map(s => s.totalConsoL    ?? 0), 1);
    const maxDist  = Math.max(...this.summaries.map(s => s.totalDistanceKm ?? 0), 1);
    const maxCo2   = Math.max(...this.summaries.map(s => s.co2Kg           ?? 0), 1);
    const maxCost  = Math.max(...this.summaries.map(s => s.costTnd         ?? 0), 1);
    const cfg: ChartConfiguration<'radar'> = {
      type: 'radar',
      data: {
        labels: [
          this.translate.instant('FUEL.KPI_CONSUMPTION'),
          this.translate.instant('FUEL.KPI_DISTANCE'),
          this.translate.instant('ENERGY.CO2_KG'),
          this.translate.instant('ENERGY.COST_TND_LABEL'),
          this.translate.instant('FUEL.KPI_EFFICIENCY')
        ],
        datasets: this.summaries.slice(0, 5).map((s, i) => ({
          label: `#${s.deviceId}`,
          data: [
            +((s.totalConsoL     ?? 0) / maxConso * 100).toFixed(1),
            +((s.totalDistanceKm ?? 0) / maxDist  * 100).toFixed(1),
            +((s.co2Kg           ?? 0) / maxCo2   * 100).toFixed(1),
            +((s.costTnd         ?? 0) / maxCost  * 100).toFixed(1),
            +(Math.min((s.avgEfficiencyL100km ?? 0) / 20 * 100, 100)).toFixed(1)
          ],
          borderColor: colors[i % colors.length],
          backgroundColor: colors[i % colors.length] + '22',
          borderWidth: 1.5,
          pointBackgroundColor: colors[i % colors.length],
          pointRadius: 3
        }))
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { color: FP.text, font: { size: 10 }, boxWidth: 10 } },
          tooltip: { backgroundColor: 'rgba(6,12,26,0.95)', titleColor: '#fff', bodyColor: FP.text }
        },
        scales: {
          r: {
            grid: { color: FP.grid }, angleLines: { color: FP.grid },
            ticks: { color: FP.text, font: { size: 9 }, backdropColor: 'transparent', stepSize: 25 },
            pointLabels: { color: FP.text, font: { size: 10 } },
            min: 0, max: 100
          }
        }
      }
    };
    this.fRadarChart = new Chart(this.fRadarCanvas.nativeElement, cfg);
  }

  // ── Modal chart ────────────────────────────────────────────────

  openChartModal(): void {
    this.chartModalOpen = true;
    document.addEventListener('keydown', this.onEscKey);
    setTimeout(() => this.initModalChart(), 80);
  }

  closeChartModal(): void {
    this.chartModalOpen = false;
    document.removeEventListener('keydown', this.onEscKey);
    this.fModalChart?.destroy();
    this.fModalChart = null;
  }

  handleChartModalBackdrop(e: MouseEvent): void {
    if ((e.target as HTMLElement).classList.contains('elec-chart-modal-backdrop')) {
      this.closeChartModal();
    }
  }

  private initModalChart(): void {
    const canvas = this.fModalCanvas?.nativeElement;
    if (!canvas) return;
    this.fModalChart?.destroy();
    this.fModalChart = null;
    this.zone.runOutsideAngular(() => this.buildModalBar(canvas));
  }

  private buildModalBar(canvas: HTMLCanvasElement): void {
    if (!this.summaries.length) return;
    this.fModalChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: this.summaries.map(s => `#${s.deviceId}`),
        datasets: [
          {
            label: this.translate.instant('ENERGY.CO2_KG'),
            data: this.summaries.map(s => +(s.co2Kg   ?? 0).toFixed(2)),
            backgroundColor: 'rgba(13,148,136,0.25)', borderColor: FP.teal,
            borderWidth: 2, borderRadius: 6
          },
          {
            label: this.translate.instant('ENERGY.COST_TND_LABEL'),
            data: this.summaries.map(s => +(s.costTnd ?? 0).toFixed(2)),
            backgroundColor: 'rgba(34,197,94,0.2)', borderColor: FP.main,
            borderWidth: 2, borderRadius: 6
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: true, position: 'top', labels: { color: FP.text, font: { size: 11 }, boxWidth: 10, padding: 16 } },
          tooltip: { backgroundColor: 'rgba(6,12,26,0.95)', titleColor: '#fff', bodyColor: FP.text }
        },
        scales: {
          x: { grid: { color: FP.grid }, ticks: { color: FP.text, font: { size: 10 } } },
          y: { grid: { color: FP.grid }, ticks: { color: FP.text, font: { size: 10 } }, beginAtZero: true }
        }
      }
    } as any);
  }

  // ── Helpers ────────────────────────────────────────────────────

  private _buildPeriodOptions(): void {
    this.periodOptions = [
      { label: this.translate.instant('ENERGY.PERIOD_24H'), value: 1  },
      { label: this.translate.instant('ENERGY.PERIOD_7D'),  value: 7  },
      { label: this.translate.instant('ENERGY.PERIOD_30D'), value: 30 },
      { label: this.translate.instant('ENERGY.PERIOD_3M'),  value: 90 },
    ];
  }

  get latestForTable(): FuelLatestDto[] { return this.latest.slice(0, 20); }

  statusClass(s: string): string {
    return s === 'OK' ? 'status-ok' : s === 'HIGH_CONSO' ? 'status-alert' : 'status-warn';
  }

  alertClass(s: string): string { return 'sev-' + s.toLowerCase(); }

  alertIcon(type: string): string {
    const m: Record<string, string> = {
      HIGH_CONSO:     '⛽',
      LOW_EFFICIENCY: '📉',
      EXCESSIVE_IDLE: '🚗',
      HIGH_SPEED:     '⚡'
    };
    return m[type] ?? '⚠';
  }

  recommendation(type: string): string {
    const m: Record<string, string> = {
      HIGH_CONSO:     this.translate.instant('FUEL.REC_HIGH_CONSO'),
      LOW_EFFICIENCY: this.translate.instant('FUEL.REC_LOW_EFFICIENCY'),
      EXCESSIVE_IDLE: this.translate.instant('FUEL.REC_EXCESSIVE_IDLE'),
      HIGH_SPEED:     this.translate.instant('FUEL.REC_HIGH_SPEED')
    };
    return m[type] ?? this.translate.instant('FUEL.REC_DEFAULT');
  }

  countBySeverity(sev: string): number { return this.alerts.filter(a => a.severity === sev).length; }

  fmtAlertDate(d: string): string {
    if (!d) return '—';
    const dt = new Date(d);
    if (isNaN(dt.getTime())) return d;
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

  private updateDateRange(from: Date, to: Date): void {
    const o: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', year: 'numeric' };
    this.dataRange = `${from.toLocaleDateString(this.locale, o)} → ${to.toLocaleDateString(this.locale, o)}`;
  }

  navigateTo(p: string): void { this.router.navigate([p]); }
  goBack():              void { this.router.navigate(['/dashboard']); }

  selectedKpi:    string | null = null;
  currentKpiDef:  any           = null;

  openKpi(key: string): void { this.selectedKpi = key; this.currentKpiDef = this.kpiDefs[key] ?? null; }
  closeKpi():           void { this.selectedKpi = null; this.currentKpiDef = null; }

  private _buildKpiDefs(): void {
    const t        = this.translate;
    const avgEff   = this.totalDistanceKm > 0 ? (this.totalConsoL / this.totalDistanceKm) * 100 : 0;
    const criticals = this.alerts.filter(a => a.severity === 'CRITICAL').length;
    const nSumm    = this.summaries.length;

    this.kpiDefs = {
      conso: {
        title: t.instant('FUEL.KPI_CONSUMPTION'), value: this.fmt(this.totalConsoL, 1), unit: 'L',
        accent: '#22c55e',
        gaugePercent: Math.min(this.totalConsoL / ((nSumm * 500) || 1) * 100, 100),
        threshold: nSumm * 500, thresholdLabel: t.instant('FUEL.THRESHOLD_CONSO_N', { n: nSumm * 500 }),
        status: null, statusLabel: null,
        definition: t.instant('FUEL.DEF_CONSO'), why: t.instant('FUEL.WHY_CONSO'),
        recommendations: [t.instant('FUEL.KPI_REC_CONSO_1'), t.instant('FUEL.KPI_REC_CONSO_2')],
        devices: this.summaries.map(s => ({ id: s.deviceId, val: this.fmt(s.totalConsoL, 1), unit: 'L', ok: true, badge: 'OK' }))
      },
      distance: {
        title: t.instant('FUEL.KPI_DISTANCE'), value: this.fmt(this.totalDistanceKm, 1), unit: 'km',
        accent: '#0ea5e9',
        gaugePercent: Math.min(this.totalDistanceKm / ((nSumm * 5000) || 1) * 100, 100),
        threshold: nSumm * 5000, thresholdLabel: t.instant('FUEL.THRESHOLD_DIST_N', { n: nSumm * 5000 }),
        status: null, statusLabel: null,
        definition: t.instant('FUEL.DEF_DIST'), why: t.instant('FUEL.WHY_DIST'),
        recommendations: [t.instant('FUEL.KPI_REC_DIST_1'), t.instant('FUEL.KPI_REC_DIST_2')],
        devices: this.summaries.map(s => ({ id: s.deviceId, val: this.fmt(s.totalDistanceKm, 0), unit: 'km', ok: true, badge: 'OK' }))
      },
      co2: {
        title: t.instant('FUEL.KPI_CO2'), value: this.fmt(this.totalCo2, 1), unit: 'kg',
        accent: '#06b6d4',
        gaugePercent: Math.min(this.totalCo2 / ((nSumm * 500) || 1) * 100, 100),
        threshold: nSumm * 500, thresholdLabel: t.instant('FUEL.FACTOR_CO2'),
        status: this.totalCo2 > nSumm * 500 ? 'warn' : null,
        statusLabel: this.totalCo2 > nSumm * 500 ? t.instant('FUEL.CO2_HIGH') : null,
        definition: t.instant('FUEL.DEF_CO2'), why: t.instant('FUEL.WHY_CO2'),
        recommendations: [t.instant('FUEL.KPI_REC_CO2_1'), t.instant('FUEL.KPI_REC_CO2_2')],
        devices: this.summaries.map(s => ({ id: s.deviceId, val: this.fmt(s.co2Kg, 1), unit: 'kg', ok: s.co2Kg <= 500, badge: s.co2Kg > 500 ? 'HAUT' : 'OK' }))
      },
      cost: {
        title: t.instant('FUEL.KPI_COST'), value: this.fmt(this.totalCost, 2), unit: 'TND',
        accent: '#10b981',
        gaugePercent: Math.min(this.totalCost / ((nSumm * 1000) || 1) * 100, 100),
        threshold: nSumm * 1000, thresholdLabel: t.instant('FUEL.FACTOR_COST'),
        status: null, statusLabel: null,
        definition: t.instant('FUEL.DEF_COST'), why: t.instant('FUEL.WHY_COST'),
        recommendations: [t.instant('FUEL.KPI_REC_COST_1'), t.instant('FUEL.KPI_REC_COST_2')],
        devices: this.summaries.map(s => ({ id: s.deviceId, val: this.fmt(s.costTnd, 2), unit: 'TND', ok: true, badge: 'OK' }))
      },
      efficiency: {
        title: t.instant('FUEL.KPI_EFFICIENCY'), value: this.fmt(avgEff, 1), unit: 'L/100km',
        accent: avgEff > 15 ? '#ef4444' : '#0d9488',
        gaugePercent: Math.min(avgEff / 20 * 100, 100),
        threshold: 15, thresholdLabel: t.instant('FUEL.THRESHOLD_EFF'),
        status: avgEff > 15 ? 'danger' : avgEff > 10 ? 'warn' : 'ok',
        statusLabel: avgEff > 15 ? t.instant('FUEL.EFF_WARN') : t.instant('FUEL.EFF_OK'),
        definition: t.instant('FUEL.DEF_EFF'), why: t.instant('FUEL.WHY_EFF'),
        recommendations: [t.instant('FUEL.KPI_REC_EFF_1'), t.instant('FUEL.KPI_REC_EFF_2'), t.instant('FUEL.KPI_REC_EFF_3')],
        devices: this.summaries.map(s => ({ id: s.deviceId, val: this.fmt(s.avgEfficiencyL100km, 1), unit: 'L/100', ok: s.avgEfficiencyL100km <= 15, badge: s.avgEfficiencyL100km > 15 ? 'HAUT' : 'OK' }))
      },
      alerts: {
        title: t.instant('FUEL.KPI_ALERTS'), value: String(this.alertCount), unit: t.instant('COMMON.ALERTS'),
        accent: this.alertCount > 0 ? '#ef4444' : '#10b981',
        gaugePercent: Math.min(this.alertCount / 10 * 100, 100),
        threshold: 0, thresholdLabel: t.instant('FUEL.THRESHOLD_ALERTS'),
        status: this.alertCount > 5 ? 'danger' : this.alertCount > 0 ? 'warn' : 'ok',
        statusLabel: this.alertCount === 0 ? t.instant('FUEL.STATUS_NO_ALERT') : t.instant('FUEL.STATUS_CRITICALS', { n: criticals }),
        definition: t.instant('FUEL.DEF_ALERTS'), why: t.instant('FUEL.WHY_ALERTS'),
        recommendations: [t.instant('FUEL.KPI_REC_ALERTS_1'), t.instant('FUEL.KPI_REC_ALERTS_2')],
        devices: this.alerts.slice(0, 10).map(a => ({ id: a.deviceId, val: a.type, unit: a.severity, ok: a.severity !== 'CRITICAL', badge: a.severity }))
      }
    };

    // Met à jour currentKpiDef si un KPI est déjà ouvert
    if (this.selectedKpi) {
      this.currentKpiDef = this.kpiDefs[this.selectedKpi] ?? null;
    }
  }
}
