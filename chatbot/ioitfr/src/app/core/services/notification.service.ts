import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, Subscription } from 'rxjs';
import { RealtimeService } from './realtime.service';

export type ToastSeverity = 'critical' | 'high' | 'low' | 'info';

export interface Toast {
  id:        string;
  severity:  ToastSeverity;
  title:     string;
  message:   string;
  deviceId?: number;
  value?:    number;
  unit?:     string;
  createdAt: Date;
}

export interface AlertRule {
  id:        string;
  label:     string;
  metric:    'THD' | 'COSFI' | 'CONSO';
  operator:  '>' | '<';
  threshold: number;
  severity:  ToastSeverity;
  enabled:   boolean;
}

const RULES_KEY = 'aria_alert_rules_v1';

const AUTO_DISMISS_MS: Record<ToastSeverity, number> = {
  critical: 0,       // persistant — dismiss manuel obligatoire
  high:     8_000,
  low:      5_000,
  info:     4_000,
};

const DEFAULT_RULES: AlertRule[] = [
  { id: 'r_thd',   label: 'THD élevé (>5%)',              metric: 'THD',   operator: '>', threshold: 5,    severity: 'high',     enabled: true  },
  { id: 'r_cosfi', label: 'cosφ faible (<0.85)',     metric: 'COSFI', operator: '<', threshold: 0.85, severity: 'high',     enabled: true  },
  { id: 'r_conso', label: 'Surconsommation (>500 kWh/m)', metric: 'CONSO', operator: '>', threshold: 500,  severity: 'critical', enabled: false },
];

@Injectable({ providedIn: 'root' })
export class NotificationService {

  private _toasts$ = new BehaviorSubject<Toast[]>([]);
  private _rules$  = new BehaviorSubject<AlertRule[]>(this.loadRules());

  readonly toasts$: Observable<Toast[]>     = this._toasts$.asObservable();
  readonly rules$:  Observable<AlertRule[]> = this._rules$.asObservable();

  private sseSub?: Subscription;
  private dedupMap = new Map<string, number>(); // clé → expiration ms

  // Cache des dernières données reçues — permet de ré-évaluer quand une règle change
  private _lastRt:        Array<{ idDevice: number; thdL1: number; thdL2: number; thdL3: number; cosfiL1: number; cosfiL2: number; cosfiL3: number }> = [];
  private _lastSummaries: Array<{ idDevice: number; totalConsoMKwh: number }> = [];

  // Dernières valeurs mesurées par métrique (pour affichage dans le panneau)
  private _liveMetrics$ = new BehaviorSubject<Record<string, number>>({});
  readonly liveMetrics$: Observable<Record<string, number>> = this._liveMetrics$.asObservable();

  constructor(private rtSvc: RealtimeService) {}

  // ── Toast API ─────────────────────────────────────────────────────────────

  push(partial: Omit<Toast, 'id' | 'createdAt'>): void {
    const toast: Toast = {
      ...partial,
      id:        Date.now().toString(36) + Math.random().toString(36).slice(2),
      createdAt: new Date(),
    };
    this._toasts$.next([toast, ...this._toasts$.getValue()].slice(0, 8));

    const delay = AUTO_DISMISS_MS[toast.severity];
    if (delay > 0) setTimeout(() => this.dismiss(toast.id), delay);
  }

  dismiss(id: string): void {
    this._toasts$.next(this._toasts$.getValue().filter(t => t.id !== id));
  }

  dismissAll(): void { this._toasts$.next([]); }

  // ── SSE stream ────────────────────────────────────────────────────────────

  subscribeToStream(token: string): void {
    if (!token || (this.sseSub && !this.sseSub.closed)) return;
    this.sseSub = this.rtSvc.alertStream(token).subscribe({
      next:  data => this.ingestSseAlert(data),
      error: ()   => { /* reconnexion automatique gérée par SseService */ },
    });
  }

  stopStream(): void { this.sseSub?.unsubscribe(); }

  // ── Ingestion alerte SSE brute ────────────────────────────────────────────

  ingestSseAlert(data: any): void {
    const sev: ToastSeverity =
      data?.severity === 'CRITICAL' ? 'critical' :
      data?.severity === 'HIGH'     ? 'high'     : 'low';
    this.push({
      severity: sev,
      title:    data?.type    ?? 'Alerte',
      message:  data?.message ?? '',
      deviceId: data?.idDevice,
      value:    data?.value,
    });
  }

  // ── Évaluation données RT : THD et COSFI uniquement ─────────────────────

  evaluateRtData(rtData: Array<{
    idDevice: number;
    thdL1:    number; thdL2: number; thdL3: number;
    cosfiL1:  number; cosfiL2: number; cosfiL3: number;
  }>): void {
    if (!rtData?.length) return;
    this._lastRt = rtData;
    this._runRtEval();
  }

  // ── Évaluation sommaires : CONSO mensuelle (source fiable) ───────────────

  evaluateSummaries(summaries: Array<{
    idDevice:       number;
    totalConsoMKwh: number;
  }>): void {
    if (!summaries?.length) return;
    this._lastSummaries = summaries;
    this._runSummaryEval();
  }

  private _runRtEval(): void {
    const now   = Date.now();
    const rules = this._rules$.getValue().filter(r => r.enabled && r.metric !== 'CONSO');
    this.cleanDedup(now);
    // Calcul des moyennes globales pour affichage live
    if (this._lastRt.length) {
      const avgThd   = this._lastRt.reduce((s, r) => s + (r.thdL1 + r.thdL2 + r.thdL3) / 3, 0) / this._lastRt.length;
      const avgCosfi = this._lastRt.reduce((s, r) => s + (r.cosfiL1 + r.cosfiL2 + r.cosfiL3) / 3, 0) / this._lastRt.length;
      this._liveMetrics$.next({ ...this._liveMetrics$.getValue(), THD: +avgThd.toFixed(2), COSFI: +avgCosfi.toFixed(3) });
    }
    for (const rt of this._lastRt) {
      this.applyRules(rules, {
        THD:   (rt.thdL1   + rt.thdL2   + rt.thdL3)   / 3,
        COSFI: (rt.cosfiL1 + rt.cosfiL2 + rt.cosfiL3) / 3,
      }, rt.idDevice, now);
    }
  }

  private _runSummaryEval(): void {
    const now   = Date.now();
    const rules = this._rules$.getValue().filter(r => r.enabled && r.metric === 'CONSO');
    this.cleanDedup(now);
    if (this._lastSummaries.length) {
      const totalConso = this._lastSummaries.reduce((s, r) => s + (r.totalConsoMKwh ?? 0), 0);
      this._liveMetrics$.next({ ...this._liveMetrics$.getValue(), CONSO: +totalConso.toFixed(1) });
    }
    for (const s of this._lastSummaries) {
      this.applyRules(rules, { CONSO: s.totalConsoMKwh ?? 0 }, s.idDevice, now);
    }
  }

  private applyRules(
    rules:    AlertRule[],
    metrics:  Record<string, number>,
    deviceId: number,
    now:      number,
  ): void {
    const units: Record<string, string> = { THD: '%', COSFI: '', CONSO: ' kWh' };

    for (const rule of rules) {
      const val = metrics[rule.metric];
      if (val == null) continue;

      const triggered = rule.operator === '>' ? val > rule.threshold : val < rule.threshold;
      if (!triggered) continue;

      const key = `${rule.id}_${deviceId}`;
      if (this.dedupMap.has(key)) continue;
      this.dedupMap.set(key, now + 120_000);

      this.push({
        severity: rule.severity,
        title:    rule.label,
        message:  `Dispositif #${deviceId} — valeur : ${val.toFixed(2)}${units[rule.metric]}`,
        deviceId,
        value:    +val.toFixed(3),
        unit:     units[rule.metric],
      });
    }
  }

  // ── Rules CRUD ────────────────────────────────────────────────────────────

  get rules(): AlertRule[] { return this._rules$.getValue(); }

  addRule(rule: Omit<AlertRule, 'id'>): void {
    const r: AlertRule = { ...rule, id: Date.now().toString(36) };
    this._rules$.next([...this.rules, r]);
    this.persistRules();
  }

  updateRule(updated: AlertRule): void {
    this._rules$.next(this.rules.map(r => r.id === updated.id ? updated : r));
    this.persistRules();
    // Ré-évaluation immédiate avec les données en cache
    this._invalidateDedupForRule(updated.id);
    if (updated.enabled) {
      updated.metric === 'CONSO' ? this._runSummaryEval() : this._runRtEval();
    }
  }

  removeRule(id: string): void {
    this._rules$.next(this.rules.filter(r => r.id !== id));
    this.persistRules();
  }

  toggleRule(id: string): void {
    const r = this.rules.find(r => r.id === id);
    if (r) this.updateRule({ ...r, enabled: !r.enabled });
  }

  private _invalidateDedupForRule(ruleId: string): void {
    for (const key of this.dedupMap.keys()) {
      if (key.startsWith(ruleId + '_')) this.dedupMap.delete(key);
    }
  }

  // ── Persistence localStorage ──────────────────────────────────────────────

  private loadRules(): AlertRule[] {
    try {
      const stored = JSON.parse(localStorage.getItem(RULES_KEY) ?? 'null');
      return Array.isArray(stored) && stored.length ? stored : [...DEFAULT_RULES];
    } catch { return [...DEFAULT_RULES]; }
  }

  private persistRules(): void {
    localStorage.setItem(RULES_KEY, JSON.stringify(this.rules));
  }

  private cleanDedup(now: number): void {
    for (const [k, exp] of this.dedupMap) {
      if (now > exp) this.dedupMap.delete(k);
    }
  }
}
