import { Component, OnInit, OnDestroy } from '@angular/core';
import { FormBuilder, FormGroup, Validators, AbstractControl, ValidationErrors } from '@angular/forms';
import { Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged, takeUntil } from 'rxjs/operators';
import { Alert, AlertService } from '../services/alerts.service';
import { DeviceService, Device } from '../services/device.service';
import { AnalyticsService, AdAnomaly, AdPrediction } from '../services/analytics.service';

type ActiveTab = 'rules' | 'ad' | 'predictions';

type ModalMode = 'view' | 'create' | 'edit' | 'delete' | null;

// ── Validator : date >= aujourd'hui (create only) ──────────────
function notInPastValidator(control: AbstractControl): ValidationErrors | null {
  if (!control.value) return null;
  const picked  = new Date(control.value);
  const todayMs = new Date().setHours(0, 0, 0, 0);
  return picked.getTime() < todayMs ? { pastDate: true } : null;
}

// ── Types d'alertes disponibles ───────────────────────────────
export const ALERT_TYPES: { value: string; label: string; level: 'critical' | 'warning' | 'info' | 'default' }[] = [
  { value: 'temperature_high',    label: 'Température haute',        level: 'critical' },
  { value: 'temperature_low',     label: 'Température basse',        level: 'warning'  },
  { value: 'humidity_high',       label: 'Humidité haute',           level: 'warning'  },
  { value: 'humidity_low',        label: 'Humidité basse',           level: 'warning'  },
  { value: 'battery_low',         label: 'Batterie faible',          level: 'info'     },
  { value: 'signal_loss',         label: 'Perte de signal',          level: 'critical' },
  { value: 'energy_overconsumption', label: 'Sur-consommation énergie', level: 'critical' },
  { value: 'energy_warning',      label: 'Avertissement énergie',    level: 'warning'  },
  { value: 'voltage_anomaly',     label: 'Anomalie tension',         level: 'critical' },
  { value: 'current_anomaly',     label: 'Anomalie courant',         level: 'critical' },
  { value: 'power_factor_low',    label: 'Facteur de puissance bas', level: 'warning'  },
  { value: 'thd_high',            label: 'THD élevé',                level: 'warning'  },
  { value: 'door_open',           label: 'Porte ouverte',            level: 'info'     },
  { value: 'motion_detected',     label: 'Mouvement détecté',        level: 'info'     },
  { value: 'maintenance_due',     label: 'Maintenance requise',      level: 'info'     },
  { value: 'system_error',        label: 'Erreur système',           level: 'critical' },
];

@Component({
  selector: 'app-alerts',
  templateUrl: './alerts.component.html',
  styleUrls: ['./alerts.component.scss']
})
export class AlertsComponent implements OnInit, OnDestroy {

  // ── Data ──────────────────────────────────────────────────────
  alerts: Alert[]   = [];
  total             = 0;
  types: string[]   = [];

  // ── Devices (pour les selects) ────────────────────────────────
  devices: Device[]        = [];
  devicesLoading           = false;
  readonly alertTypes      = ALERT_TYPES;

  // ── Date min (aujourd'hui) pour les inputs date ───────────────
  get todayIso(): string {
    const now = new Date();
    // format: YYYY-MM-DDTHH:mm (datetime-local)
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T00:00`;
  }

  // ── Pagination ────────────────────────────────────────────────
  page = 0;
  size = 10;
  get totalPages(): number  { return Math.ceil(this.total / this.size); }
  get pageNumbers(): number[] {
    return Array.from({ length: this.totalPages }, (_, i) => i);
  }

  // ── Filters ───────────────────────────────────────────────────
  searchType        = '';
  filterIdDevice?: number;
  filterMessage     = '';
  
  showAdvancedFilters = false;

  // ── Sort ──────────────────────────────────────────────────────
  sortCol           = 'date';
  sortDir: 'asc' | 'desc' = 'desc';

  // ── State ─────────────────────────────────────────────────────
  loading           = false;
  saving            = false;
  errorMsg          = '';
  successMsg        = '';
  private successTimer: any;

  // ── AD Anomalies tab ──────────────────────────────────────────
  activeTab: ActiveTab    = 'rules';
  adAnomalies: AdAnomaly[]= [];
  adLoading               = false;
  adDomainFilter          = '';
  adDays                  = 90;
  readonly adDayOptions   = [7, 14, 30, 90, 365];
  readonly adDomainOptions = [
    { value: '',       label: 'Tous les domaines' },
    { value: 'energy', label: '⚡ Énergie' },
    { value: 'water',  label: '💧 Eau' },
    { value: 'gas',    label: '🔥 Gaz' },
    { value: 'fuel',   label: '🚗 Carburant' },
  ];

  // ── Prédictions tab ───────────────────────────────────────────
  predictions: AdPrediction[] = [];
  predLoading                 = false;
  predHorizon                 = 24;
  predDomainFilter            = '';
  readonly predHorizonOptions = [6, 12, 24, 48];

  // computed caches (rebuilt on each predictions load)
  private _domainStats: Array<{domain:string;total:number;highCount:number;medCount:number;lowCount:number;highPct:number;medPct:number;lowPct:number}> = [];
  private _predGrouped: Array<{id:string;label:string;icon:string;severity:string;items:AdPrediction[]}> = [];
  private _groupsState: Record<string,{expanded:boolean;showAll:boolean}> = {
    imminent:  {expanded:true,showAll:false},
    urgent:    {expanded:true,showAll:false},
    preventif: {expanded:true,showAll:false},
  };

  get domainStats()    { return this._domainStats; }
  get predGrouped()    { return this._predGrouped; }
  get predHighCount()  { return this.predictions.filter(p => p.alert_severity === 'HIGH').length;   }
  get predMedCount()   { return this.predictions.filter(p => p.alert_severity === 'MEDIUM').length; }
  get predLowCount()   { return this.predictions.filter(p => p.alert_severity === 'LOW').length;    }

  // ── Modal ─────────────────────────────────────────────────────
  modalMode: ModalMode      = null;
  selectedAlert: Alert | null = null;
  form!: FormGroup;

  private destroy$      = new Subject<void>();
  private searchSubject = new Subject<string>();

  constructor(
    private svc:          AlertService,
    private devSvc:       DeviceService,
    private analyticsSvc: AnalyticsService,
    private fb:           FormBuilder
  ) {}

  // ── Lifecycle ─────────────────────────────────────────────────
  ngOnInit(): void {
    this.buildForm();
    this.loadTypes();
    this.loadDevices();

    this.searchSubject.pipe(
      debounceTime(350),
      distinctUntilChanged(),
      takeUntil(this.destroy$)
    ).subscribe(() => { this.page = 0; this.load(); });

    this.load();
  }

  ngOnDestroy(): void { this.destroy$.next(); this.destroy$.complete(); clearTimeout(this.successTimer); }

  // ── AD Tab ────────────────────────────────────────────────────
  switchTab(tab: ActiveTab): void {
    this.activeTab = tab;
    if (tab === 'ad' && this.adAnomalies.length === 0) {
      this.loadAdAnomalies();
    }
    if (tab === 'predictions' && this.predictions.length === 0) {
      this.loadPredictions();
    }
  }

  loadPredictions(): void {
    this.predLoading = true;
    this.analyticsSvc.getPredictions(this.predHorizon, this.predDomainFilter || undefined)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: r => {
          this.predictions = r.predictions;
          this.predLoading = false;
          this._computeDomainStats();
          this._computePredGrouped();
        },
        error: () => { this.predictions = []; this.predLoading = false; },
      });
  }

  private _computeDomainStats(): void {
    this._domainStats = ['energy','water','gas','fuel'].map(domain => {
      const items      = this.predictions.filter(p => p.domain === domain);
      const total      = items.length;
      const highCount  = items.filter(p => p.alert_severity === 'HIGH').length;
      const medCount   = items.filter(p => p.alert_severity === 'MEDIUM').length;
      const lowCount   = total - highCount - medCount;
      return { domain, total, highCount, medCount, lowCount,
        highPct: total ? highCount / total * 100 : 0,
        medPct:  total ? medCount  / total * 100 : 0,
        lowPct:  total ? lowCount  / total * 100 : 0 };
    });
  }

  private _computePredGrouped(): void {
    for (const k of Object.keys(this._groupsState)) this._groupsState[k].showAll = false;
    const now    = Date.now();
    const sorted = [...this.predictions].sort((a, b) =>
      new Date(a.forecast_ts).getTime() - new Date(b.forecast_ts).getTime());
    const groups = [
      { id:'imminent',  label:'Imminent · < 6h',   icon:'🚨', severity:'HIGH',   items:[] as AdPrediction[] },
      { id:'urgent',    label:'Urgent · 6h – 24h', icon:'⚠️', severity:'MEDIUM', items:[] as AdPrediction[] },
      { id:'preventif', label:'Préventif · > 24h', icon:'📊', severity:'LOW',    items:[] as AdPrediction[] },
    ];
    for (const p of sorted) {
      const diff = new Date(p.forecast_ts).getTime() - now;
      if (diff < 6 * 3_600_000)       groups[0].items.push(p);
      else if (diff < 24 * 3_600_000) groups[1].items.push(p);
      else                             groups[2].items.push(p);
    }
    this._predGrouped = groups.filter(g => g.items.length > 0);
  }

  toggleGroup(id: string):       void    { if (this._groupsState[id]) this._groupsState[id].expanded = !this._groupsState[id].expanded; }
  isGroupExpanded(id: string):   boolean { return this._groupsState[id]?.expanded ?? true; }
  showAllInGroup(id: string):    void    { if (this._groupsState[id]) this._groupsState[id].showAll = true; }
  isGroupShowAll(id: string):    boolean { return this._groupsState[id]?.showAll  ?? false; }

  timeToAlert(forecastTs: string): string {
    const diff = new Date(forecastTs).getTime() - Date.now();
    if (diff <= 0) return 'Passé';
    const h = Math.floor(diff / 3_600_000);
    const m = Math.floor((diff % 3_600_000) / 60_000);
    if (h === 0) return `dans ${m}m`;
    if (m === 0) return `dans ${h}h`;
    return `dans ${h}h ${m}m`;
  }

  medianPct(p: AdPrediction): number {
    const lo = p.forecast_low ?? 0, hi = p.forecast_high ?? 0, med = p.forecast_median ?? lo;
    const span = hi - lo;
    return span === 0 ? 50 : Math.min(100, Math.max(0, (med - lo) / span * 100));
  }

  isOfflineDevice(p: AdPrediction): boolean {
    return p.forecast_low === 0 && p.forecast_high === 0 && p.forecast_median === 0;
  }

  confDashArray(c: number | null): string {
    return c != null ? `${Math.round(c * 88)} 88` : '0 88';
  }

  confColor(c: number | null): string {
    if (c == null)  return 'rgba(255,255,255,0.15)';
    if (c >= 0.7)   return '#2dd4bf';
    if (c >= 0.4)   return '#fb923c';
    return '#f87171';
  }

  confLabel(c: number | null): string {
    return c != null ? Math.round(c * 100) + '%' : '—';
  }

  sevIcon(sev: string | null): string {
    if (sev === 'HIGH')   return '🔴';
    if (sev === 'MEDIUM') return '🟠';
    return '🟡';
  }

  domainLabel(domain: string): string {
    const map: Record<string,string> = { energy:'Énergie', water:'Eau', gas:'Gaz', fuel:'Carburant' };
    return map[domain] ?? domain;
  }

  predSeverityClass(sev: string | null): string {
    if (sev === 'HIGH')   return 'sev-high';
    if (sev === 'MEDIUM') return 'sev-medium';
    return 'sev-low';
  }

  predHorizonLabel(forecastTs: string): string {
    const diff = Math.max(1, Math.round((new Date(forecastTs).getTime() - Date.now()) / 3_600_000));
    return `dans ~${diff}h`;
  }

  loadAdAnomalies(): void {
    this.adLoading = true;
    this.analyticsSvc.getAnomalies(this.adDays, this.adDomainFilter || undefined)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next:  r  => { this.adAnomalies = r.anomalies; this.adLoading = false; },
        error: () => { this.adAnomalies = [];           this.adLoading = false; },
      });
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
    return new Date(ts).toLocaleString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  }

  trackByAdAnomaly(_: number, a: AdAnomaly): string {
    return `${a.domain}_${a.item_id}_${a.data_ts}`;
  }

  private showSuccess(msg: string): void {
    this.successMsg = msg;
    clearTimeout(this.successTimer);
    this.successTimer = setTimeout(() => this.successMsg = '', 3500);
  }

  // ── Form ──────────────────────────────────────────────────────
  private buildForm(): void {
    this.form = this.fb.group({
      // ── Clé primaire ──
      date: ['', [
        Validators.required,
        notInPastValidator              // date >= aujourd'hui (create)
      ]],
      idDevice: [null, [
        Validators.required,
        Validators.min(1)
      ]],
      type: ['', Validators.required],

      // ── Valeurs mesurées ──
      valeur: [null, [
        Validators.min(-9999),
        Validators.max(9999)
      ]],
      diff: [null, [
        Validators.min(-9999),
        Validators.max(9999)
      ]],
      valMin: [null, [
        Validators.min(-9999),
        Validators.max(9999)
      ]],
      valMax: [null, [
        Validators.min(-9999),
        Validators.max(9999)
      ]],
      tempsInfraction: [null, [
        Validators.min(0),
        Validators.max(86400)           // max 24h en secondes
      ]],

      // ── Messages ──
      message:          ['', Validators.maxLength(500)],
      messageEn:        ['', Validators.maxLength(500)],
      recommendationFr: ['', Validators.maxLength(500)],
      recommendationEn: ['', Validators.maxLength(500)],
      from:             ['', Validators.maxLength(45)],
    }, { validators: this.valMinMaxValidator });
  }

  // ── Cross-field validator : valMin <= valMax ──────────────────
  private valMinMaxValidator(group: AbstractControl): ValidationErrors | null {
    const min = group.get('valMin')?.value;
    const max = group.get('valMax')?.value;
    if (min !== null && max !== null && min !== '' && max !== '' && +min > +max) {
      return { minGtMax: true };
    }
    return null;
  }

  // ── Load data ─────────────────────────────────────────────────
  load(): void {
    this.loading  = true;
    this.errorMsg = '';
    this.svc.list(this.page, this.size, this.searchType || undefined, this.filterIdDevice)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: res => {
          this.alerts  = this.applyClientSideFilters(res.data);
          this.total   = this.alerts.length;
          this.loading = false;
        },
        error: () => {
          this.errorMsg = 'Erreur lors du chargement des alertes.';
          this.loading  = false;
        }
      });
  }

  // Filtres côté client
  private applyClientSideFilters(alerts: Alert[]): Alert[] {
    let filtered = [...alerts];

    // Filtre par message
    if (this.filterMessage) {
      const query = this.filterMessage.toLowerCase();
      filtered = filtered.filter(a => 
        (a.message && a.message.toLowerCase().includes(query)) ||
        (a.messageEn && a.messageEn.toLowerCase().includes(query)) ||
        (a.recommendationFr && a.recommendationFr.toLowerCase().includes(query)) ||
        (a.recommendationEn && a.recommendationEn.toLowerCase().includes(query))
      );
    }

    return filtered;
  }

  loadTypes(): void {
    this.svc.getTypes().pipe(takeUntil(this.destroy$)).subscribe(t => (this.types = t));
  }

  loadDevices(): void {
    this.devicesLoading = true;
    this.devSvc.list(0, 9999)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: res => {
          this.devices        = res.data;
          this.devicesLoading = false;
        },
        error: () => { this.devicesLoading = false; }
      });
  }

  // ── Helpers device ────────────────────────────────────────────
  deviceLabel(d: Device): string {
    return d.nom ? `#${d.id} — ${d.nom}` : `#${d.id}`;
  }

  getDeviceName(id: number | null): string {
    if (id == null) return '—';
    const d = this.devices.find(x => x.id === id);
    return d ? (d.nom ?? `#${id}`) : `#${id}`;
  }

  getAlertTypeLabel(value: string): string {
    return this.alertTypes.find(t => t.value === value)?.label ?? value;
  }

  // ── Filters ───────────────────────────────────────────────────
  onSearchType(value: string): void {
    this.searchType = value;
    this.searchSubject.next(value);
  }

  clearSearch(): void {
    this.searchType = '';
    this.page       = 0;
    this.load();
  }

  onFilterDevice(value: string): void {
    this.filterIdDevice = value ? +value : undefined;
    this.page           = 0;
    this.load();
  }

  toggleAdvancedFilters(): void {
    this.showAdvancedFilters = !this.showAdvancedFilters;
  }

  applyFilters(): void {
    this.page = 0;
    this.load();
  }

  resetAllFilters(): void {
    this.searchType      = '';
    this.filterIdDevice  = undefined;
    this.filterMessage   = '';
    this.page            = 0;
    this.load();
  }

  get hasActiveFilters(): boolean {
    return !!(this.searchType || this.filterIdDevice || this.filterMessage);
  }

  get activeFiltersCount(): number {
    let count = 0;
    if (this.searchType) count++;
    if (this.filterIdDevice) count++;
    if (this.filterMessage) count++;
    return count;
  }

  // ── Sort ─────────────────────────────────────────────────────
  sort(col: string): void {
    this.sortDir = this.sortCol === col && this.sortDir === 'asc' ? 'desc' : 'asc';
    this.sortCol = col;
    this.alerts.sort((a: any, b: any) => {
      const va = a[col], vb = b[col];
      if (va == null) return 1;
      if (vb == null) return -1;
      return (va > vb ? 1 : va < vb ? -1 : 0) * (this.sortDir === 'asc' ? 1 : -1);
    });
  }

  sortIcon(col: string): string {
    if (this.sortCol !== col) return '↕';
    return this.sortDir === 'asc' ? '↑' : '↓';
  }

  // ── Pagination ────────────────────────────────────────────────
  goPage(p: number): void {
    if (p < 0 || p >= this.totalPages) return;
    this.page = p;
    this.load();
  }

  // ── Row helpers ───────────────────────────────────────────────
  rowClass(a: Alert): string {
    const t = (a.type || '').toLowerCase();
    if (t.includes('critical') || t.includes('error'))   return 'row-red';
    if (t.includes('warning'))                            return 'row-orange';
    if (t.includes('info'))                               return 'row-yellow';
    return '';
  }

  levelClass(a: Alert): string {
    const t = (a.type || '').toLowerCase();
    if (t.includes('critical') || t.includes('error'))   return 'level-red';
    if (t.includes('warning'))                            return 'level-orange';
    if (t.includes('info'))                               return 'level-yellow';
    return 'badge-gray';
  }

  levelDot(a: Alert): string {
    const t = (a.type || '').toLowerCase();
    if (t.includes('critical') || t.includes('error'))   return 'dot-red';
    if (t.includes('warning'))                            return 'dot-orange';
    if (t.includes('info'))                               return 'dot-yellow';
    return '';
  }

  // ── Niveau d'un type d'alerte (pour le select) ───────────────
  alertTypeLevelClass(value: string): string {
    const t = this.alertTypes.find(x => x.value === value);
    if (!t) return 'badge-gray';
    if (t.level === 'critical') return 'level-red';
    if (t.level === 'warning')  return 'level-orange';
    if (t.level === 'info')     return 'level-yellow';
    return 'badge-gray';
  }

  // ── Modal helpers ─────────────────────────────────────────────
  openView(a: Alert): void   { this.selectedAlert = a; this.modalMode = 'view'; }
  openDelete(a: Alert): void { this.selectedAlert = a; this.modalMode = 'delete'; }

  openCreate(): void {
    this.form.enable();
    this.form.reset();
    this.selectedAlert = null;
    this.modalMode     = 'create';
    this.errorMsg      = '';

    // Réactiver le validator notInPast pour la création
    this.form.get('date')?.setValidators([Validators.required, notInPastValidator]);
    this.form.get('date')?.updateValueAndValidity();
  }

  openEdit(a: Alert): void {
    this.form.enable();
    this.selectedAlert = a;
    this.form.patchValue({ ...a, date: a.date ? a.date.substring(0, 16) : '' });

    // En édition : pas de contrainte "date future" sur la clé primaire
    this.form.get('date')?.setValidators([Validators.required]);
    this.form.get('date')?.updateValueAndValidity();

    // Clé primaire non modifiable
    this.form.get('date')?.disable();
    this.form.get('idDevice')?.disable();
    this.form.get('type')?.disable();
    this.modalMode = 'edit';
    this.errorMsg  = '';
  }

  closeModal(): void {
    this.modalMode     = null;
    this.selectedAlert = null;
    this.errorMsg      = '';
    this.form.enable();
  }

  isInvalid(field: string): boolean {
    const c = this.form.get(field);
    return !!(c && c.invalid && c.touched);
  }

  hasError(field: string, errorKey: string): boolean {
    const c = this.form.get(field);
    return !!(c && c.hasError(errorKey) && c.touched);
  }

  get hasMinGtMaxError(): boolean {
    return !!(this.form.hasError('minGtMax') &&
      (this.form.get('valMin')?.touched || this.form.get('valMax')?.touched));
  }

  // ── CRUD ──────────────────────────────────────────────────────
  save(): void {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.saving   = true;
    this.errorMsg = '';
    const dto: Alert = { ...this.form.getRawValue() };

    const obs = this.modalMode === 'create'
      ? this.svc.create(dto)
      : this.svc.update(
          this.selectedAlert!.date,
          this.selectedAlert!.idDevice,
          this.selectedAlert!.type,
          dto
        );

    obs.pipe(takeUntil(this.destroy$)).subscribe({
      next:  () => {
        this.saving = false;
        this.closeModal();
        this.showSuccess(this.modalMode === 'create' ? 'Alerte créée avec succès.' : 'Alerte modifiée avec succès.');
        this.load();
      },
      error: (err) => { this.saving = false; this.errorMsg = err?.error?.message ?? 'Erreur lors de la sauvegarde.'; }
    });
  }

  confirmDelete(): void {
    if (!this.selectedAlert) return;
    this.saving = true;
    this.svc.delete(
      this.selectedAlert.date,
      this.selectedAlert.idDevice,
      this.selectedAlert.type
    ).pipe(takeUntil(this.destroy$))
     .subscribe({
        next:  () => { this.saving = false; this.closeModal(); this.showSuccess('Alerte supprimée.'); this.load(); },
        error: (err) => { this.saving = false; this.errorMsg = err?.error?.message ?? 'Erreur lors de la suppression.'; }
      });
  }

  // ── AD v2 helpers ─────────────────────────────────────────────
  adCountByDomain(domain: string): number {
    return this.adAnomalies.filter(a => a.domain === domain).length;
  }

  adCriticalCount(): number {
    return this.adAnomalies.filter(a => (a.anomaly_score ?? 0) >= 0.8).length;
  }

  adScoreColor(score: number | null): string {
    if (score == null) return 'rgba(255,255,255,0.15)';
    if (score >= 0.8)  return '#f87171';
    if (score >= 0.5)  return '#fb923c';
    return '#4ade80';
  }

  adScoreDash(score: number | null): string {
    const circ = 119.4; // 2 * π * 19 (r=19 dans le SVG 48x48)
    return score != null ? `${(score * circ).toFixed(1)} ${circ}` : `0 ${circ}`;
  }

  adValuePct(a: AdAnomaly): number {
    const lo = a.q10 ?? 0, hi = a.q90 ?? 0, val = a.value ?? lo;
    const span = hi - lo;
    return span === 0 ? 50 : Math.min(100, Math.max(0, (val - lo) / span * 100));
  }

  // ── Utils ─────────────────────────────────────────────────────
  formatDate(d: string | null): string {
    if (!d) return '—';
    return new Date(d).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
  }

  trackByAlert(_: number, a: Alert): string {
    return `${a.date}_${a.idDevice}_${a.type}`;
  }

  trackByDevice(_: number, d: Device): number { return d.id; }
}