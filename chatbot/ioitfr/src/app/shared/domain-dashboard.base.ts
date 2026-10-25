import { Directive, ElementRef, NgZone, OnDestroy, OnInit, inject } from '@angular/core';
import { Router } from '@angular/router';
import { TranslateService } from '@ngx-translate/core';
import { Observable, Subject } from 'rxjs';
import { finalize, takeUntil } from 'rxjs/operators';
import { Chart, ChartConfiguration, ChartItem, ChartType } from 'chart.js';
import { ChatTriggerService } from '../core/services/chat-trigger.service';
import { normalizeBattery } from './battery.util';
import './chart-setup';

export interface DateRange { from: Date; to: Date; }

export interface PeriodOption { label: string; value: number; }

export interface KpiDeviceRow {
  id: number | string;
  val: string;
  unit: string;
  ok: boolean;
  badge: string;
}

/** Contenu du panneau de détail KPI (partagé par les 4 templates domaine). */
export interface KpiDef {
  title: string;
  accent: string;
  value: string;
  unit: string;
  definition: string;
  why: string;
  threshold: number | null;
  thresholdLabel: string | null;
  gaugePercent: number;
  status: 'ok' | 'warn' | 'danger' | null;
  statusLabel: string | null;
  recommendations: string[];
  devices: KpiDeviceRow[];
}

/** Données minimales que chaque domaine doit charger. */
export interface DomainData<TSummary, TAlert> {
  summaries: TSummary[];
  alerts: TAlert[];
}

/** Clé réservée du graphique affiché dans la modale plein écran. */
export const MODAL_CHART = 'modal';

// Les canvas sont dans des blocs *ngIf qui ne sont rendus qu'après la fin du
// chargement : on diffère la création des graphiques le temps que la vue existe.
const CHART_RENDER_DELAY_MS = 300;
const MODAL_RENDER_DELAY_MS = 80;

/**
 * Socle commun des dashboards domaine (électricité, gaz, eau, carburant) :
 * cycle de vie, chargement par période, i18n, panneau KPI, modale graphique,
 * registre des instances Chart.js et helpers de formatage.
 *
 * Chaque sous-classe ne fournit que le métier : appels API, KPIs, graphiques.
 */
@Directive()
export abstract class DomainDashboardBase<
  TSummary,
  TAlert extends { severity: string },
  TData extends DomainData<TSummary, TAlert>
> implements OnInit, OnDestroy {

  protected readonly router    = inject(Router);
  protected readonly zone      = inject(NgZone);
  protected readonly translate = inject(TranslateService);
  private   readonly chatTrigger = inject(ChatTriggerService);

  isLoading = false;
  loadError = false;

  selectedPeriod = 30;
  periodOptions: PeriodOption[] = [];
  dataRange = '';

  summaries: TSummary[] = [];
  alerts:    TAlert[]   = [];

  kpiDefs: Record<string, KpiDef> = {};
  selectedKpi: string | null = null;
  currentKpiDef: KpiDef | null = null;

  chartModalOpen = false;

  protected readonly destroy$ = new Subject<void>();
  private destroyed = false;
  private readonly charts = new Map<string, Chart>();

  protected get isDestroyed(): boolean { return this.destroyed; }

  // Fonction fléchée : garde `this` lié quand elle sert de listener DOM.
  private readonly onEscKey = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') this.closeChartModal();
  };

  /** Classe CSS du fond de la modale : un clic dessus la ferme. */
  protected abstract readonly modalBackdropClass: string;
  /** Libellé du domaine utilisé dans le prompt ARIA par défaut. */
  protected abstract readonly insightLabel: string;

  protected abstract dateRangeFor(days: number): DateRange;
  protected abstract fetchData(range: DateRange): Observable<TData>;
  /** Stocke les données spécifiques au domaine (temps réel, dernières mesures…). */
  protected abstract applyData(data: TData): void;
  protected abstract buildKpi(): void;
  /** Construit les graphiques inline — exécuté hors zone Angular. */
  protected abstract buildCharts(): void;
  /** Construit le graphique de la modale — exécuté hors zone Angular. */
  protected abstract buildModalChart(canvas: HTMLCanvasElement): void;
  protected abstract get modalCanvas(): ElementRef<HTMLCanvasElement> | undefined;
  protected abstract insightPrompts(period: number): Record<string, string>;

  /** Hook : chargement complémentaire une fois les données de base reçues. */
  protected afterDataLoaded(_range: DateRange): void {}
  /** Hook : recalcul des libellés traduits propres au domaine. */
  protected refreshLabels(): void {}

  // ══════════════════════════════════════════════════════════════
  // CYCLE DE VIE
  // ══════════════════════════════════════════════════════════════

  ngOnInit(): void {
    this.buildPeriodOptions();
    this.refreshLabels();
    this.dataRange = this.translate.instant('COMMON.LOADING');
    this.load();
    this.translate.onLangChange.pipe(takeUntil(this.destroy$)).subscribe(() => {
      this.buildPeriodOptions();
      this.refreshLabels();
      this.updateDateRange(this.dateRangeFor(this.selectedPeriod));
      this.buildKpi();
      this.renderCharts();
    });
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.destroy$.next();
    this.destroy$.complete();
    document.removeEventListener('keydown', this.onEscKey);
    this.charts.forEach(c => c.destroy());
    this.charts.clear();
  }

  // ══════════════════════════════════════════════════════════════
  // CHARGEMENT
  // ══════════════════════════════════════════════════════════════

  load(): void {
    this.isLoading = true;
    this.loadError = false;
    const range = this.dateRangeFor(this.selectedPeriod);
    this.updateDateRange(range);

    this.fetchData(range)
      .pipe(takeUntil(this.destroy$), finalize(() => this.isLoading = false))
      .subscribe({
        next: data => {
          this.summaries = data.summaries;
          this.alerts    = data.alerts;
          this.applyData(data);
          this.buildKpi();
          this.afterDataLoaded(range);
          this.scheduleChartsRender();
        },
        error: () => { this.loadError = true; }
      });
  }

  onPeriodChange(period: number): void {
    this.selectedPeriod = period;
    this.load();
  }

  // ══════════════════════════════════════════════════════════════
  // GRAPHIQUES
  // ══════════════════════════════════════════════════════════════

  protected scheduleChartsRender(): void {
    setTimeout(() => this.renderCharts(), CHART_RENDER_DELAY_MS);
  }

  protected renderCharts(): void {
    if (this.destroyed) return;
    this.zone.runOutsideAngular(() => this.buildCharts());
  }

  /** (Re)crée le graphique `key` : l'instance précédente est détruite d'abord. */
  protected renderChart<T extends ChartType>(
    key: string,
    target: ElementRef<HTMLCanvasElement> | ChartItem | undefined,
    config: ChartConfiguration<T, any, any>,
  ): void {
    this.destroyChart(key);
    if (!target) return;
    const item = target instanceof ElementRef ? target.nativeElement : target;
    this.charts.set(key, new Chart(item, config) as unknown as Chart);
  }

  protected destroyChart(key: string): void {
    this.charts.get(key)?.destroy();
    this.charts.delete(key);
  }

  // ══════════════════════════════════════════════════════════════
  // MODALE GRAPHIQUE
  // ══════════════════════════════════════════════════════════════

  protected showChartModal(): void {
    this.chartModalOpen = true;
    document.addEventListener('keydown', this.onEscKey);
    setTimeout(() => this.initModalChart(), MODAL_RENDER_DELAY_MS);
  }

  closeChartModal(): void {
    this.chartModalOpen = false;
    document.removeEventListener('keydown', this.onEscKey);
    this.destroyChart(MODAL_CHART);
  }

  handleChartModalBackdrop(e: MouseEvent): void {
    if ((e.target as HTMLElement).classList.contains(this.modalBackdropClass)) {
      this.closeChartModal();
    }
  }

  private initModalChart(): void {
    const canvas = this.modalCanvas?.nativeElement;
    if (!canvas || this.destroyed) return;
    this.destroyChart(MODAL_CHART);
    this.zone.runOutsideAngular(() => this.buildModalChart(canvas));
  }

  // ══════════════════════════════════════════════════════════════
  // PANNEAU KPI & ARIA
  // ══════════════════════════════════════════════════════════════

  openKpi(key: string): void {
    this.selectedKpi   = key;
    this.currentKpiDef = this.kpiDefs[key] ?? null;
  }

  closeKpi(): void {
    this.selectedKpi   = null;
    this.currentKpiDef = null;
  }

  /** Remplace les définitions KPI et rafraîchit le panneau s'il est ouvert. */
  protected setKpiDefs(defs: Record<string, KpiDef>): void {
    this.kpiDefs = defs;
    if (this.selectedKpi) this.currentKpiDef = defs[this.selectedKpi] ?? null;
  }

  openAriaInsight(section: string, event: MouseEvent): void {
    event.stopPropagation();
    const p = this.selectedPeriod;
    const prompt = this.insightPrompts(p)[section] ?? `Analyse ${this.insightLabel} — ${section} — ${p}j.`;
    this.chatTrigger.open(prompt);
  }

  // ══════════════════════════════════════════════════════════════
  // HELPERS TEMPLATE
  // ══════════════════════════════════════════════════════════════

  countBySeverity(sev: string): number {
    return this.alerts.filter(a => a.severity === sev).length;
  }

  /** Normalise le niveau batterie IoT (spec LoRaWAN 0–254, voir shared/battery.util.ts) */
  normBatt(v: number | null | undefined): number {
    return normalizeBattery(v);
  }

  fmt(n: number, dec = 0): string {
    if (n == null || isNaN(n)) return '0';
    return n.toLocaleString(this.locale, { minimumFractionDigits: dec, maximumFractionDigits: dec });
  }

  fmtAlertDate(d: string): string {
    if (!d) return '—';
    const dt = new Date(d);
    if (isNaN(dt.getTime())) return d;
    const dd = String(dt.getDate()).padStart(2, '0');
    const mm = String(dt.getMonth() + 1).padStart(2, '0');
    const hh = String(dt.getHours()).padStart(2, '0');
    const mn = String(dt.getMinutes()).padStart(2, '0');
    return `${dd}/${mm} ${hh}:${mn}`;
  }

  goBack(): void { this.router.navigate(['/dashboard']); }
  navigateTo(p: string): void { this.router.navigate([p]); }

  protected get locale(): string {
    const l = this.translate.currentLang ?? 'fr';
    return l === 'ar' ? 'ar-TN' : l === 'en' ? 'en-US' : 'fr-FR';
  }

  protected isTrendUp(t: string): boolean { return !t.startsWith('-'); }

  /** 'YYYY-MM-DD…' → 'DD/MM' */
  protected fmtDateLabel(d: string): string {
    if (!d) return '';
    const p = d.substring(0, 10).split('-');
    return p.length === 3 ? `${p[2]}/${p[1]}` : d;
  }

  private buildPeriodOptions(): void {
    const t = this.translate;
    this.periodOptions = [
      { label: t.instant('ENERGY.PERIOD_24H'), value: 1  },
      { label: t.instant('ENERGY.PERIOD_7D'),  value: 7  },
      { label: t.instant('ENERGY.PERIOD_30D'), value: 30 },
      { label: t.instant('ENERGY.PERIOD_3M'),  value: 90 },
    ];
  }

  private updateDateRange({ from, to }: DateRange): void {
    const o: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', year: 'numeric' };
    this.dataRange = `${from.toLocaleDateString(this.locale, o)} → ${to.toLocaleDateString(this.locale, o)}`;
  }
}
