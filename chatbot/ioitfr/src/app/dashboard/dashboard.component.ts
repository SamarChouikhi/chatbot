import {
  Component, OnInit, OnDestroy, AfterViewInit,
  ElementRef, ViewChild,
} from '@angular/core';
import { Router } from '@angular/router';
import { Chart, registerables } from 'chart.js';
import { Observable, Subject, forkJoin, interval, of } from 'rxjs';
import { takeUntil, finalize, startWith, map, switchMap } from 'rxjs/operators';
import { TranslateService } from '@ngx-translate/core';

import { GazService, GazSummaryDto, GazAlertDto, GazChartDto }           from '../services/gaz.service';
import { ElectricityService, ElecSummaryDto, ElecAlertDto, ElecChartDto } from '../services/electricity.service';
import { WaterService, WaterSummaryDto, WaterAlertDto, WaterChartDto }    from '../services/water.service';
import { FuelService, FuelSummaryDto, FuelAlertDto, FuelChartDto }        from '../services/fuel.service';
import { AnalyticsService, AdAnomaly, AdPrediction }                        from '../services/analytics.service';
import { DashboardService, Period } from '../core/services/dashboard.service';
import { ChatTriggerService } from '../core/services/chat-trigger.service';

Chart.register(...registerables);

type ModalFilter = 'all' | 'elec' | 'water' | 'gaz' | 'fuel';

interface AnomalyGroup {
  item_id:  string;
  domain:   string;
  strategy: string;
  count:    number;
  worst:    AdAnomaly;
  events:   AdAnomaly[];
}

interface SourceConfig<S, A> {
  setLoading:   (v: boolean) => void;
  getRange:     () => { from: Date; to: Date };
  getSummaries: (from: Date, to: Date) => Observable<S[]>;
  getAlerts:    () => Observable<A[]>;
  onData:       (summaries: S[], alerts: A[], from: Date, to: Date) => void;
}

@Component({
  selector:    'app-dashboard',
  templateUrl: './dashboard.component.html',
  styleUrls:   ['./dashboard.component.scss'],
})
export class DashboardComponent implements OnInit, AfterViewInit, OnDestroy {

  // ── Canvas refs ───────────────────────────────────────────────
  @ViewChild('hourlyCo2Canvas') hourlyCo2CanvasRef!: ElementRef<HTMLCanvasElement>;
  @ViewChild('co2ChartCanvas')  co2CanvasRef!:       ElementRef<HTMLCanvasElement>;
  @ViewChild('elecMiniCanvas')  elecMiniRef!:        ElementRef<HTMLCanvasElement>;
  @ViewChild('waterMiniCanvas') waterMiniRef!:       ElementRef<HTMLCanvasElement>;
  @ViewChild('gazMiniCanvas')   gazMiniRef!:         ElementRef<HTMLCanvasElement>;
  @ViewChild('fuelMiniCanvas')  fuelMiniRef!:        ElementRef<HTMLCanvasElement>;
  @ViewChild('modalCo2Canvas')  modalCo2CanvasRef!:  ElementRef<HTMLCanvasElement>;

  // ── Chart instances — Chart<any> évite les conflits de génériques Chart.js ──
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private hourlyCo2Chart: Chart<any> | null = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private co2Chart:       Chart<any> | null = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private elecMini:       Chart<any> | null = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private waterMini:      Chart<any> | null = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private gazMini:        Chart<any> | null = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private fuelMini:       Chart<any> | null = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private modalChart:     Chart<any> | null = null;

  private viewReady       = false;
  private chartInitTimer: ReturnType<typeof setTimeout> | null = null;

  // ── Loading ───────────────────────────────────────────────────
  isLoadingElec  = false;
  isLoadingGaz   = false;
  isLoadingWater = false;
  isLoadingFuel  = false;
  get isLoading(): boolean {
    return this.isLoadingElec || this.isLoadingGaz || this.isLoadingWater || this.isLoadingFuel;
  }

  // ── Period ────────────────────────────────────────────────────
  selectedPeriod: Period = 30;
  periods: { label: string; value: Period }[] = [
    { label: '7j', value: 7 }, { label: '30j', value: 30 }, { label: '90j', value: 90 },
  ];

  // ── Chart data (local) ────────────────────────────────────────
  elecChartData:  ElecChartDto  | null = null;
  gazChartData:   GazChartDto   | null = null;
  waterChartData: WaterChartDto | null = null;
  fuelChartData:  FuelChartDto  | null = null;

  // ── AD Anomalies ──────────────────────────────────────────────
  adAnomalies:    AdAnomaly[] = [];
  adKpis:         Record<string, number> = {};
  isLoadingAd     = false;
  adDomainFilter: string | null = null;
  readonly adDomains = ['energy', 'water', 'gas', 'fuel'];
  expandedGroups  = new Set<string>();

  // ── Prédictions préventives ───────────────────────────────────
  adPredictions:      AdPrediction[] = [];
  isLoadingPredictions = false;

  // ── Display ───────────────────────────────────────────────────
  liveTime  = '';
  dataRange = '—';
  co2Legend: { name: string; value: number; color: string; pct: number }[] = [];

  // ── Delegated getters (template convenience) ─────────────────
  get elecDevices():          number  { return this.dash.elecDevices; }
  get elecTrend():            string  { return this.dash.elecTrend; }
  get elecKwh():              number  { return this.dash.elecKwh; }
  get elecCo2():              number  { return this.dash.elecCo2; }
  get elecCost():             number  { return this.dash.elecCost; }
  get elecAvgCosfi():         number  { return this.dash.elecAvgCosfi; }
  get elecAvgThd():           number  { return this.dash.elecAvgThd; }
  get elecCritical():         number  { return this.dash.elecCritical; }
  get waterDevices():         number  { return this.dash.waterDevices; }
  get waterTrend():           string  { return this.dash.waterTrend; }
  get waterM3():              number  { return this.dash.waterM3; }
  get waterCo2():             number  { return this.dash.waterCo2; }
  get waterCost():            number  { return this.dash.waterCost; }
  get waterLeaks():           number  { return this.dash.waterLeaks; }
  get waterFrauds():          number  { return this.dash.waterFrauds; }
  get waterCritical():        number  { return this.dash.waterCritical; }
  get gazDevices():           number  { return this.dash.gazDevices; }
  get gazTrend():             string  { return this.dash.gazTrend; }
  get gazL():                 number  { return this.dash.gazL; }
  get gazCo2():               number  { return this.dash.gazCo2; }
  get gazCost():              number  { return this.dash.gazCost; }
  get gazAvgDebit():          number  { return this.dash.gazAvgDebit; }
  get gazLeaks():             number  { return this.dash.gazLeaks; }
  get gazCritical():          number  { return this.dash.gazCritical; }
  get fuelDevices():          number  { return this.dash.fuelDevices; }
  get fuelTrend():            string  { return this.dash.fuelTrend; }
  get fuelL():                number  { return this.dash.fuelL; }
  get fuelCo2():              number  { return this.dash.fuelCo2; }
  get fuelKm():               number  { return this.dash.fuelKm; }
  get fuelAvgSpeed():         number  { return this.dash.fuelAvgSpeed; }
  get fuelCritical():         number  { return this.dash.fuelCritical; }
  get hourlyCo2Points():      { label: string; co2: number }[] { return this.dash.hourlyCo2Points; }
  get totalCo2():             number  { return this.dash.totalCo2; }
  get co2RealisePct():        number  { return this.dash.co2RealisePct; }
  get co2ProjectionWarning(): boolean { return this.dash.co2ProjectionWarning; }
  get co2Projection():        number  { return this.dash.co2Projection; }
  get topEmitters():          import('../core/services/dashboard.service').TopEmitter[] { return this.dash.topEmitters; }

  // ── ARIA Card Trigger ─────────────────────────────────────────
  openAriaPopup(domain: string, event: MouseEvent): void {
    event.stopPropagation();
    this.chatTrigger.open(this._buildAriaPrompt(domain));
  }

  private _buildAriaPrompt(domain: string): string {
    const period = this.selectedPeriod;
    switch (domain) {
      case 'electricity':
        return `Interprète ces indicateurs Électricité (${period}j) :
Consommation : ${this.fmt(this.elecKwh, 1)} kWh (tendance : ${this.elecTrend})
CO₂ : ${this.fmt(this.elecCo2, 1)} kgCO₂ | Coût : ${this.fmt(this.elecCost, 0)} TND | cosφ : ${this.elecAvgCosfi.toFixed(2)} | THD : ${this.elecAvgThd.toFixed(1)}%${this.elecCritical > 0 ? ` | ${this.elecCritical} alerte(s) critique(s)` : ''}
Est-ce normal, préoccupant ou excellent ? Réponds en 2-3 lignes.`;

      case 'water':
        return `Interprète ces indicateurs Eau (${period}j) :
Consommation : ${this.fmt(this.waterM3, 2)} m³ (tendance : ${this.waterTrend})
CO₂ : ${this.fmt(this.waterCo2, 1)} kgCO₂ | Coût : ${this.fmt(this.waterCost, 0)} TND | Fuites : ${this.waterLeaks} | Fraudes : ${this.waterFrauds}${this.waterCritical > 0 ? ` | ${this.waterCritical} alerte(s) critique(s)` : ''}
Est-ce normal, préoccupant ou excellent ? Réponds en 2-3 lignes.`;

      case 'gaz':
        return `Interprète ces indicateurs Gaz (${period}j) :
Consommation : ${this.fmt(this.gazL, 0)} L (tendance : ${this.gazTrend})
CO₂ : ${this.fmt(this.gazCo2, 1)} kgCO₂ | Coût : ${this.fmt(this.gazCost, 0)} TND | Débit moyen : ${this.gazAvgDebit.toFixed(1)} L/min | Fuites : ${this.gazLeaks}${this.gazCritical > 0 ? ` | ${this.gazCritical} alerte(s) critique(s)` : ''}
Est-ce normal, préoccupant ou excellent ? Réponds en 2-3 lignes.`;

      case 'fuel':
        return `Interprète ces indicateurs Carburant (${period}j) :
Consommation : ${this.fmt(this.fuelL, 0)} L (tendance : ${this.fuelTrend})
CO₂ : ${this.fmt(this.fuelCo2, 1)} kgCO₂ | Distance : ${this.fmt(this.fuelKm, 0)} km | Vitesse moy. : ${this.fuelAvgSpeed.toFixed(0)} km/h${this.fuelCritical > 0 ? ` | ${this.fuelCritical} alerte(s) critique(s)` : ''}
Est-ce normal, préoccupant ou excellent ? Réponds en 2-3 lignes.`;

      case 'co2-curve': {
        const pts  = this.hourlyCo2Points;
        const peak = pts.reduce((m, p) => p.co2 > m.co2 ? p : m, pts[0] ?? { label: '—', co2: 0 });
        const avg  = pts.length ? pts.reduce((s, p) => s + p.co2, 0) / pts.length : 0;
        return `Analyse la courbe CO₂ horaire d'aujourd'hui :
Total journée actuelle : ${this.fmt(this.totalCo2, 1)} kgCO₂ | Pic : ${peak.co2.toFixed(1)} kgCO₂ à ${peak.label} | Moyenne horaire : ${avg.toFixed(1)} kg/h
Projection fin de journée : ${this.fmt(this.co2Projection, 0)} kgCO₂${this.co2ProjectionWarning ? ' ⚠ dépasse l\'objectif' : ''}
Que révèle cette courbe ? Y a-t-il des pics anormaux ou une tendance préoccupante ? Réponds en 2-3 lignes.`;
      }

      case 'co2-trajectory': {
        const pct  = this.co2RealisePct.toFixed(0);
        const warn = this.co2ProjectionWarning;
        return `Analyse la trajectoire CO₂ pour la période de ${period} jours :
Réalisé : ${this.fmt(this.totalCo2, 0)} kgCO₂ (${pct}% de l'objectif théorique)
Projection fin de période : ${this.fmt(this.co2Projection, 0)} kgCO₂${warn ? ' ⚠ dépasse l\'objectif' : ' ✓ dans les limites'}
Sommes-nous sur une bonne trajectoire ? Quelles actions recommandes-tu ? Réponds en 2-3 lignes.`;
      }

      case 'co2-mix': {
        const total = this.totalCo2 || 1;
        const parts = [
          { name: 'Électricité', val: this.elecCo2,  pct: Math.round(this.elecCo2  / total * 100) },
          { name: 'Eau',         val: this.waterCo2, pct: Math.round(this.waterCo2 / total * 100) },
          { name: 'Gaz',         val: this.gazCo2,   pct: Math.round(this.gazCo2   / total * 100) },
          { name: 'Carburant',   val: this.fuelCo2,  pct: Math.round(this.fuelCo2  / total * 100) },
        ].sort((a, b) => b.val - a.val);
        const breakdown = parts.map(p => `${p.name} : ${this.fmt(p.val, 1)} kgCO₂ (${p.pct}%)`).join(' | ');
        return `Analyse le mix CO₂ par module (${period}j) :
Total : ${this.fmt(this.totalCo2, 0)} kgCO₂
${breakdown}
Quel module domine et pourquoi ? Est-ce une répartition normale pour un bâtiment ? Réponds en 2-3 lignes.`;
      }

      case 'co2-emitters': {
        const emitters = this.topEmitters.slice(0, 5)
          .map((e, i) => `${i + 1}. ${e.name} : ${this.fmt(e.co2Kg, 0)} kg (${e.trendDown ? '↓' : '↑'}${e.trendVal})`)
          .join('\n');
        return `Analyse le classement des top émetteurs CO₂ (${period}j) :
${emitters || 'Aucune donnée disponible'}
Y a-t-il des émetteurs anormaux ? Quels espaces nécessitent une attention immédiate ? Réponds en 2-3 lignes.`;
      }

      default:
        return `Analyse le domaine ${domain} sur les ${period} derniers jours.`;
    }
  }

  // ── Modal ─────────────────────────────────────────────────────
  co2ModalOpen       = false;
  modalActiveFilter: ModalFilter = 'all';
  modalFilters: { key: ModalFilter; icon: string; label: string }[] = [
    { key: 'all',   icon: '',   label: 'COMMON.ALL'      },
    { key: 'elec',  icon: '⚡', label: 'NAV.ELECTRICITY' },
    { key: 'water', icon: '💧', label: 'NAV.WATER'       },
    { key: 'gaz',   icon: '🔥', label: 'NAV.GAS'         },
    { key: 'fuel',  icon: '🚗', label: 'NAV.FUEL'        },
  ];
  modalKpis = {
    total: 0, totalDelta: '—', trendUp: false,
    peak: 0, peakHour: '—', avg: 0, projection: 0, projWarn: false,
  };

  trackByIndex = (i: number) => i;

  private destroy$ = new Subject<void>();
  private cancel$  = new Subject<void>();
  private onEscKey = (e: KeyboardEvent): void => { if (e.key === 'Escape') this.closeCo2Modal(); };

  constructor(
    public  dash:         DashboardService,
    private gazSvc:       GazService,
    private elecSvc:      ElectricityService,
    private waterSvc:     WaterService,
    private fuelSvc:      FuelService,
    private analyticsSvc: AnalyticsService,
    private router:       Router,
    private translate:    TranslateService,
    private chatTrigger:  ChatTriggerService,
  ) {}

  private get locale(): string {
    const l = this.translate.currentLang ?? 'fr';
    return l === 'ar' ? 'ar-TN' : l === 'en' ? 'en-US' : 'fr-FR';
  }

  // ══════════════════════════════════════════════════════════════
  // LIFECYCLE
  // ══════════════════════════════════════════════════════════════

  ngOnInit(): void {
    this.updatePeriodLabels();
    this._startLiveClock();
    this.loadAllData();

    this.dash.updated$.pipe(takeUntil(this.destroy$)).subscribe(() => {
      this.rebuildCo2Legend();
      this._updateDateRange();
      this.tryInitCharts();
    });

    this.translate.onLangChange.pipe(takeUntil(this.destroy$)).subscribe(() => {
      this.updatePeriodLabels();
      this.rebuildCo2Legend();
      this._updateDateRange();
      this.tryInitCharts();
    });
  }

  ngAfterViewInit(): void {
    this.viewReady = true;
    this.tryInitCharts();
  }

  ngOnDestroy(): void {
    if (this.chartInitTimer) clearTimeout(this.chartInitTimer);
    document.removeEventListener('keydown', this.onEscKey);
    this.destroy$.next();
    this.destroy$.complete();
    ([this.hourlyCo2Chart, this.co2Chart,
      this.elecMini, this.waterMini, this.gazMini, this.fuelMini, this.modalChart] as (Chart<any> | null)[])
      .forEach(c => c?.destroy());
  }

  // ══════════════════════════════════════════════════════════════
  // DISPLAY HELPERS
  // ══════════════════════════════════════════════════════════════

  private _startLiveClock(): void {
    interval(60_000).pipe(
      startWith(0),
      map(() => new Date()),
      takeUntil(this.destroy$),
    ).subscribe(now => {
      this.liveTime = `${now.getHours().toString().padStart(2, '0')}h${now.getMinutes().toString().padStart(2, '0')}`;
    });
  }

  private _updateDateRange(): void {
    const { from, to } = this.elecSvc.getLastNDaysRange(this.selectedPeriod);
    const base = { day: '2-digit' as const, month: 'short' as const };
    this.dataRange = [
      from.toLocaleDateString(this.locale, base),
      to.toLocaleDateString(this.locale, { ...base, year: 'numeric' }),
    ].join(' → ');
  }

  private updatePeriodLabels(): void {
    const d = this.translate.instant('DASHBOARD.DAYS_ABBR') ?? 'j';
    this.periods = [
      { label: `7${d}`,  value: 7  },
      { label: `30${d}`, value: 30 },
      { label: `90${d}`, value: 90 },
    ];
  }

  private rebuildCo2Legend(): void {
    const total = this.dash.totalCo2 || 1;
    this.co2Legend = [
      { name: this.translate.instant('NAV.ELECTRICITY'), value: this.dash.elecCo2,  color: '#0ea5e9', pct: Math.round(this.dash.elecCo2  / total * 100) },
      { name: this.translate.instant('NAV.WATER'),       value: this.dash.waterCo2, color: '#06b6d4', pct: Math.round(this.dash.waterCo2 / total * 100) },
      { name: this.translate.instant('NAV.GAS'),         value: this.dash.gazCo2,   color: '#0d9488', pct: Math.round(this.dash.gazCo2   / total * 100) },
      { name: this.translate.instant('NAV.FUEL'),        value: this.dash.fuelCo2,  color: '#22c55e', pct: Math.round(this.dash.fuelCo2  / total * 100) },
    ];
  }

  // ══════════════════════════════════════════════════════════════
  // DATA LOADING
  // ══════════════════════════════════════════════════════════════

  changePeriod(p: Period): void {
    if (this.selectedPeriod === p) return;
    this.cancel$.next();
    this.selectedPeriod = p;
    this.elecChartData = this.waterChartData = this.gazChartData = this.fuelChartData = null;
    this.loadAllData();
  }

  private loadAllData(): void {
    this.loadAdData();
    this._loadSource<ElecSummaryDto, ElecAlertDto>({
      setLoading:   v => this.isLoadingElec = v,
      getRange:     () => this.elecSvc.getLastNDaysRange(this.selectedPeriod),
      getSummaries: (f, t) => this.elecSvc.getAllSummaries(f, t),
      getAlerts:    () => this.elecSvc.getAlerts(),
      onData: (summaries, alerts, from, to) => {
        this.dash.updateElec(summaries, alerts);
        const id = summaries[0]?.idDevice;
        (id ? this.elecSvc.getDailyChart(id, from, to) : of(null)).pipe(
          switchMap(c => (c?.points?.length) ? of(c) : this.analyticsSvc.getEnergyChart(this.selectedPeriod)),
          takeUntil(this.destroy$), takeUntil(this.cancel$),
        ).subscribe(c => { this.elecChartData = c; this.initElecMini(); });
      },
    });

    this._loadSource<GazSummaryDto, GazAlertDto>({
      setLoading:   v => this.isLoadingGaz = v,
      getRange:     () => this.gazSvc.getLastNDaysRange(this.selectedPeriod),
      getSummaries: (f, t) => this.gazSvc.getAllSummaries(f, t),
      getAlerts:    () => this.gazSvc.getAlerts(),
      onData: (summaries, alerts, from, to) => {
        this.dash.updateGaz(summaries, alerts);
        const id = summaries[0]?.idDevice;
        (id ? this.gazSvc.getDailyChart(id, from, to) : of(null)).pipe(
          switchMap(c => (c?.points?.length) ? of(c) : this.analyticsSvc.getGazChart(this.selectedPeriod)),
          takeUntil(this.destroy$), takeUntil(this.cancel$),
        ).subscribe(c => { this.gazChartData = c; this.initGazMini(); });
      },
    });

    this._loadSource<WaterSummaryDto, WaterAlertDto>({
      setLoading:   v => this.isLoadingWater = v,
      getRange:     () => this.waterSvc.getLastNDaysRange(this.selectedPeriod),
      getSummaries: (f, t) => this.waterSvc.getAllSummaries(f, t),
      getAlerts:    () => this.waterSvc.getAlerts(),
      onData: (summaries, alerts, from, to) => {
        this.dash.updateWater(summaries, alerts);
        const id = summaries[0]?.idDevice;
        (id ? this.waterSvc.getDailyChart(id, from, to) : of(null)).pipe(
          switchMap(c => (c?.points?.length) ? of(c) : this.analyticsSvc.getWaterChart(this.selectedPeriod)),
          takeUntil(this.destroy$), takeUntil(this.cancel$),
        ).subscribe(c => { this.waterChartData = c; this.initWaterMini(); });
      },
    });

    this._loadSource<FuelSummaryDto, FuelAlertDto>({
      setLoading:   v => this.isLoadingFuel = v,
      getRange:     () => this.fuelSvc.getLastNDaysRange(this.selectedPeriod),
      getSummaries: (f, t) => this.fuelSvc.getAllSummaries(f, t),
      getAlerts:    () => this.fuelSvc.getAlerts(),
      onData: (summaries, alerts, from, to) => {
        this.dash.updateFuel(summaries, alerts);
        const id = summaries[0]?.deviceId;
        (id ? this.fuelSvc.getDailyChart(id, from, to) : of(null)).pipe(
          switchMap(c => (c?.points?.length) ? of(c) : this.analyticsSvc.getFuelChart(this.selectedPeriod)),
          takeUntil(this.destroy$), takeUntil(this.cancel$),
        ).subscribe(c => { this.fuelChartData = c; this.initFuelMini(); });
      },
    });
  }

  loadAdData(domain?: string): void {
    this.isLoadingAd    = true;
    this.adDomainFilter = domain ?? null;
    this.expandedGroups.clear();
    this.analyticsSvc.getKpis(this.selectedPeriod).pipe(takeUntil(this.destroy$)).subscribe({ next: k => { this.adKpis = k.anomalies; }, error: () => {} });
    this.analyticsSvc.getAnomalies(this.selectedPeriod, domain).pipe(takeUntil(this.destroy$)).subscribe({
      next:  r  => { this.adAnomalies = r.anomalies; this.isLoadingAd = false; },
      error: () => { this.adAnomalies = [];           this.isLoadingAd = false; },
    });
    this.loadPredictions();
  }

  get groupedAnomalies(): AnomalyGroup[] {
    const map = new Map<string, AdAnomaly[]>();
    for (const a of this.adAnomalies) {
      const bucket = map.get(a.item_id);
      if (bucket) bucket.push(a);
      else map.set(a.item_id, [a]);
    }
    const groups: AnomalyGroup[] = [];
    map.forEach((events, item_id) => {
      const sorted = [...events].sort((a, b) => (b.anomaly_score ?? 0) - (a.anomaly_score ?? 0));
      groups.push({ item_id, domain: sorted[0].domain, strategy: sorted[0].strategy, count: events.length, worst: sorted[0], events: sorted });
    });
    return groups.sort((a, b) => (b.worst.anomaly_score ?? 0) - (a.worst.anomaly_score ?? 0));
  }

  toggleGroup(itemId: string): void {
    this.expandedGroups.has(itemId) ? this.expandedGroups.delete(itemId) : this.expandedGroups.add(itemId);
  }

  trackByGroup = (_: number, g: AnomalyGroup) => g.item_id;

  loadPredictions(): void {
    this.isLoadingPredictions = true;
    this.analyticsSvc.getPredictions(48).pipe(takeUntil(this.destroy$)).subscribe({
      next:  r  => { this.adPredictions = r.predictions.slice(0, 8); this.isLoadingPredictions = false; },
      error: () => { this.adPredictions = [];                         this.isLoadingPredictions = false; },
    });
  }

  predSeverityClass(sev: string | null): string {
    if (sev === 'HIGH')   return 'sev-high';
    if (sev === 'MEDIUM') return 'sev-medium';
    return 'sev-low';
  }

  predHorizon(forecastTs: string): string {
    const diff = Math.max(1, Math.round((new Date(forecastTs).getTime() - Date.now()) / 3_600_000));
    return `dans ~${diff}h`;
  }

  get predHighCount(): number {
    return this.adPredictions.filter(p => p.alert_severity === 'HIGH').length;
  }

  domainIcon(domain: string): string {
    const d = (domain ?? '').toLowerCase();
    if (d === 'energy' || d.includes('energ')) return '⚡';
    if (d === 'water'  || d === 'eau')          return '💧';
    if (d === 'gaz'    || d === 'gas')           return '🔥';
    if (d === 'fuel'   || d.includes('carb'))   return '🛢️';
    return '📡';
  }

  private _loadSource<S, A>(config: SourceConfig<S, A>): void {
    config.setLoading(true);
    const { from, to } = config.getRange();
    forkJoin({ summaries: config.getSummaries(from, to), alerts: config.getAlerts() })
      .pipe(
        takeUntil(this.destroy$),
        takeUntil(this.cancel$),
        finalize(() => { config.setLoading(false); this.dash.computeGlobals(this.selectedPeriod, from); }),
      )
      .subscribe({ next: ({ summaries, alerts }) => config.onData(summaries, alerts, from, to), error: () => {} });
  }

  // ══════════════════════════════════════════════════════════════
  // CHART INITIALIZATION
  // ══════════════════════════════════════════════════════════════

  private tryInitCharts(): void {
    if (!this.viewReady) return;
    if (this.chartInitTimer) clearTimeout(this.chartInitTimer);
    this.chartInitTimer = setTimeout(() => {
      this.initHourlyCo2Chart();
      this.initCo2Chart();
      this.initElecMini();
      this.initWaterMini();
      this.initGazMini();
      this.initFuelMini();
    }, 400);
  }

  private initHourlyCo2Chart(): void {
    const canvas = this.hourlyCo2CanvasRef?.nativeElement;
    if (!canvas) return;
    this.hourlyCo2Chart?.destroy();
    this.hourlyCo2Chart = null;
    if (!this.dash.hourlyCo2Points.length) return;

    const ctx = canvas.getContext('2d')!;
    const gr  = ctx.createLinearGradient(0, 0, 0, canvas.parentElement?.clientHeight || 220);
    gr.addColorStop(0,   'rgba(14,165,233,0.35)');
    gr.addColorStop(0.7, 'rgba(14,165,233,0.06)');
    gr.addColorStop(1,   'rgba(14,165,233,0.00)');

    this.hourlyCo2Chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels:   this.dash.hourlyCo2Points.map(p => p.label),
        datasets: [{
          label: 'CO₂ (kg/h)', data: this.dash.hourlyCo2Points.map(p => p.co2),
          borderColor: '#0ea5e9', backgroundColor: gr, fill: true, tension: 0.42,
          pointRadius: 4, pointHoverRadius: 7,
          pointBackgroundColor: '#0ea5e9', pointBorderColor: 'rgba(14,165,233,0.25)',
          pointBorderWidth: 2, borderWidth: 2,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(5,10,28,0.96)', titleColor: '#e2e8f0',
            bodyColor: 'rgba(226,232,240,0.65)', borderColor: 'rgba(255,255,255,0.1)',
            borderWidth: 1, padding: 12, cornerRadius: 10,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            callbacks: { label: (c: any) => ` ${(+c.raw).toLocaleString(this.locale, { maximumFractionDigits: 1 })} kgCO₂` },
          },
        },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: 'rgba(255,255,255,0.35)', font: { size: 10 } } },
          y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: 'rgba(255,255,255,0.35)', font: { size: 10 }, padding: 8 },
               beginAtZero: true, title: { display: true, text: 'kg CO₂', color: 'rgba(255,255,255,0.3)', font: { size: 10 } } },
        },
      },
    });
  }

  private initCo2Chart(): void {
    const canvas = this.co2CanvasRef?.nativeElement;
    if (!canvas) return;
    this.co2Chart?.destroy();
    this.co2Chart = null;
    const vals = [this.dash.elecCo2, this.dash.waterCo2, this.dash.gazCo2, this.dash.fuelCo2];
    if (!vals.some(v => v > 0)) return;

    const ctx = canvas.getContext('2d')!;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    this.co2Chart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: [
          this.translate.instant('NAV.ELECTRICITY'), this.translate.instant('NAV.WATER'),
          this.translate.instant('NAV.GAS'),          this.translate.instant('NAV.FUEL'),
        ],
        datasets: [{
          data: vals,
          backgroundColor: ['rgba(14,165,233,0.88)', 'rgba(6,182,212,0.88)', 'rgba(13,148,136,0.88)', 'rgba(34,197,94,0.88)'],
          borderColor:     ['#0ea5e9', '#06b6d4', '#0d9488', '#22c55e'],
          borderWidth: 2, hoverOffset: 12, spacing: 2,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '72%',
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(5,10,28,0.96)', titleColor: '#e2e8f0',
            bodyColor: 'rgba(226,232,240,0.65)', borderColor: 'rgba(255,255,255,0.1)',
            borderWidth: 1, padding: 12, cornerRadius: 10,
            callbacks: {
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              label: (c: any) => { const t = vals.reduce((a, b) => a + b, 0) || 1; return ` ${c.parsed.toFixed(2)} kgCO₂ — ${Math.round(c.parsed / t * 100)}%`; },
            },
          },
        },
      },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
  }

  private initElecMini():  void { this.elecMini  = this.buildMini(this.elecMiniRef,  this.elecMini,  this.elecChartData?.points  ?? [], '#0ea5e9', [14, 165, 233], p => p.consKwh ?? 0); }
  private initWaterMini(): void { this.waterMini = this.buildMini(this.waterMiniRef, this.waterMini, this.waterChartData?.points ?? [], '#06b6d4', [6,  182, 212], p => p.consoM3 ?? p.conso ?? 0); }
  private initGazMini():   void { this.gazMini   = this.buildMini(this.gazMiniRef,   this.gazMini,   this.gazChartData?.points   ?? [], '#0d9488', [13, 148, 136], p => p.conso ?? 0); }
  private initFuelMini():  void { this.fuelMini  = this.buildMini(this.fuelMiniRef,  this.fuelMini,  this.fuelChartData?.points  ?? [], '#22c55e', [34, 197, 94],  p => p.conso ?? 0); }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private buildMini(ref: ElementRef<HTMLCanvasElement> | undefined, existing: Chart<any> | null, points: any[], color: string, rgb: [number, number, number], getValue: (p: any) => number): Chart<any> | null {
    const canvas = ref?.nativeElement;
    if (!canvas) return null;
    existing?.destroy();
    if (!points.length) return null;
    const ctx = canvas.getContext('2d')!;
    const gr  = ctx.createLinearGradient(0, 0, 0, canvas.parentElement?.clientHeight || 60);
    gr.addColorStop(0, `rgba(${rgb.join(',')},0.45)`);
    gr.addColorStop(1, `rgba(${rgb.join(',')},0.00)`);
    return new Chart(ctx, {
      type: 'line',
      data: {
        labels:   points.map((p: any) => p.label),
        datasets: [{ data: points.map(getValue), borderColor: color, backgroundColor: gr, fill: true, tension: 0.42, pointRadius: 0, borderWidth: 1.5 }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { enabled: false } }, scales: { x: { display: false }, y: { display: false, beginAtZero: true } } },
    });
  }

  // ══════════════════════════════════════════════════════════════
  // MODAL CO₂
  // ══════════════════════════════════════════════════════════════

  openCo2Modal(): void {
    this.co2ModalOpen = true;
    document.addEventListener('keydown', this.onEscKey);
    setTimeout(() => this.initModalChart(), 80);
  }

  closeCo2Modal(): void {
    this.co2ModalOpen = false;
    document.removeEventListener('keydown', this.onEscKey);
    this.modalChart?.destroy();
    this.modalChart = null;
  }

  handleModalBackdrop(e: MouseEvent): void {
    if ((e.target as HTMLElement).classList.contains('co2-modal-backdrop')) {
      this.closeCo2Modal();
    }
  }

  setModalFilter(filter: ModalFilter): void {
    this.modalActiveFilter = filter;
    this.initModalChart();
  }

  private initModalChart(): void {
    const canvas = this.modalCo2CanvasRef?.nativeElement;
    if (!canvas || !this.dash.hourlyCo2Points.length) return;
    this.modalChart?.destroy();
    this.modalChart = null;

    const total = this.dash.totalCo2 || 1;
    const sources: Record<string, { label: string; color: string; rgb: [number, number, number]; pts: { label: string; co2: number }[] }> = {
      elec:  { label: this.translate.instant('NAV.ELECTRICITY'), color: '#0ea5e9', rgb: [14, 165, 233], pts: this.dash.hourlyCo2Points.map(p => ({ label: p.label, co2: p.co2 * (this.dash.elecCo2  / total) })) },
      water: { label: this.translate.instant('NAV.WATER'),       color: '#06b6d4', rgb: [6,  182, 212], pts: this.dash.hourlyCo2Points.map(p => ({ label: p.label, co2: p.co2 * (this.dash.waterCo2 / total) })) },
      gaz:   { label: this.translate.instant('NAV.GAS'),         color: '#0d9488', rgb: [13, 148, 136], pts: this.dash.hourlyCo2Points.map(p => ({ label: p.label, co2: p.co2 * (this.dash.gazCo2   / total) })) },
      fuel:  { label: this.translate.instant('NAV.FUEL'),        color: '#22c55e', rgb: [34, 197, 94],  pts: this.dash.hourlyCo2Points.map(p => ({ label: p.label, co2: p.co2 * (this.dash.fuelCo2  / total) })) },
    };

    const activeKeys = this.modalActiveFilter === 'all' ? Object.keys(sources) : [this.modalActiveFilter];
    const ctx = canvas.getContext('2d')!;

    const datasets = activeKeys.map(key => {
      const s         = sources[key];
      const [r, g, b] = s.rgb;
      const gr        = ctx.createLinearGradient(0, 0, 0, canvas.parentElement?.clientHeight || 300);
      gr.addColorStop(0,   `rgba(${r},${g},${b},0.30)`);
      gr.addColorStop(0.7, `rgba(${r},${g},${b},0.06)`);
      gr.addColorStop(1,   `rgba(${r},${g},${b},0.00)`);
      return {
        label: s.label, data: s.pts.map(p => p.co2),
        borderColor: s.color, backgroundColor: gr,
        fill: true, tension: 0.42,
        pointRadius: activeKeys.length === 1 ? 5 : 3,
        pointHoverRadius: activeKeys.length === 1 ? 9 : 6,
        pointBackgroundColor: s.color, pointBorderColor: `rgba(${r},${g},${b},0.25)`,
        pointBorderWidth: 2, borderWidth: activeKeys.length === 1 ? 2.5 : 1.8,
      };
    });

    const allVals   = activeKeys.flatMap(k => sources[k].pts.map(p => p.co2));
    const kpiTotal  = allVals.reduce((s, v) => s + v, 0);
    const kpiPeak   = Math.max(...allVals, 0);
    const peakIdx   = allVals.indexOf(kpiPeak);
    const kpiAvg    = allVals.length ? kpiTotal / allVals.length : 0;
    const kpiProj   = (kpiTotal / Math.max(1, this.dash.hourlyCo2Points.length)) * 15;
    this.modalKpis  = {
      total: kpiTotal, totalDelta: '↑ +12.3% vs hier', trendUp: true,
      peak: kpiPeak, peakHour: this.dash.hourlyCo2Points[peakIdx]?.label ?? '—',
      avg: kpiAvg, projection: kpiProj, projWarn: kpiProj > kpiTotal * 1.4,
    };

    this.modalChart = new Chart(ctx, {
      type: 'line',
      data: { labels: this.dash.hourlyCo2Points.map(p => p.label), datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: true, position: 'top', labels: { color: 'rgba(255,255,255,0.5)', font: { size: 11 }, boxWidth: 8, boxHeight: 8, padding: 16, usePointStyle: true } },
          tooltip: {
            backgroundColor: 'rgba(5,10,28,0.97)', titleColor: '#e2e8f0',
            bodyColor: 'rgba(226,232,240,0.65)', borderColor: 'rgba(255,255,255,0.1)',
            borderWidth: 1, padding: 14, cornerRadius: 12,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            callbacks: { label: (c: any) => ` ${c.dataset.label}: ${(+c.raw).toLocaleString(this.locale, { maximumFractionDigits: 2 })} kgCO₂` },
          },
        },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: 'rgba(255,255,255,0.35)', font: { size: 10 } } },
          y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: 'rgba(255,255,255,0.35)', font: { size: 10 }, padding: 8 },
               beginAtZero: true, title: { display: true, text: 'kg CO₂', color: 'rgba(255,255,255,0.3)', font: { size: 10 } } },
        },
      },
    });
  }

  // ══════════════════════════════════════════════════════════════
  // NAVIGATION & FORMATTERS
  // ══════════════════════════════════════════════════════════════

  navigateTo(p: string): void { this.router.navigate([p]); }

  fmt(n: number, dec = 0): string {
    if (n == null || isNaN(n)) return '—';
    return n.toLocaleString(this.locale, { minimumFractionDigits: dec, maximumFractionDigits: dec });
  }

  trendClass(t: string): 'positive' | 'negative' | 'neutral' {
    if (!t || t === '0.0%') return 'neutral';
    return t.startsWith('-') ? 'positive' : 'negative';
  }

  trendIcon(t: string): string {
    if (!t || t === '0.0%') return '—';
    return t.startsWith('-') ? '↓' : '↑';
  }

  adTotalAnomalies(): number {
    return Object.values(this.adKpis).reduce((s, n) => s + n, 0);
  }

  adScoreClass(score: number | null): string {
    if (score == null) return '';
    if (score >= 0.8) return 'score-critical';
    if (score >= 0.5) return 'score-warning';
    return 'score-low';
  }

  adDomainIcon(domain: string): string {
    const map: Record<string, string> = { energy: '⚡', water: '💧', gas: '🔥', fuel: '🚗' };
    return map[domain] ?? '●';
  }

  adFormatTs(ts: string): string {
    if (!ts) return '—';
    return new Date(ts).toLocaleString(this.locale, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  }

  adDeviceLabel(item_id: string): string {
    return item_id.replace('_', ' ');
  }

}
