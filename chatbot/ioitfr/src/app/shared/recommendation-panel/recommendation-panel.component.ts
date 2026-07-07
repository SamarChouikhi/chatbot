import {
  Component, Input, OnInit, OnDestroy, ChangeDetectionStrategy, ChangeDetectorRef
} from '@angular/core';
import { Subject, interval } from 'rxjs';
import { takeUntil, startWith } from 'rxjs/operators';
import { TranslateService } from '@ngx-translate/core';
import { Recommendation, RecommendationsService } from '../../services/recommendations.service';
import { ChatTriggerService } from '../../core/services/chat-trigger.service';
import { AuthService } from '../../services/auth.service';

// Identifiants de rôle attendus par le moteur de recommandations backend (contrat API, non affichés)
const ROLE_TO_LLM: Record<string, string> = {
  SUPER_ADMIN: 'directeur',
  TECHNICIAN : 'technicien',
  EMPLOYEE   : 'gestionnaire',
};

const PRIORITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

const REC_TYPE_ICONS: Record<string, string> = {
  OVERCONSUMPTION: '📈',
  OPTIMIZATION   : '⚡',
  BUDGET_ALERT   : '💰',
  MAINTENANCE    : '🔧',
  LEAK_RISK      : '💧',
  EFFICIENCY     : '🚗',
};

const REC_TYPE_I18N_KEYS: Record<string, string> = {
  OVERCONSUMPTION: 'RECO_PANEL.TYPE_OVERCONSUMPTION',
  OPTIMIZATION   : 'RECO_PANEL.TYPE_OPTIMIZATION',
  BUDGET_ALERT   : 'RECO_PANEL.TYPE_BUDGET_ALERT',
  MAINTENANCE    : 'RECO_PANEL.TYPE_MAINTENANCE',
  LEAK_RISK      : 'RECO_PANEL.TYPE_LEAK_RISK',
  EFFICIENCY     : 'RECO_PANEL.TYPE_EFFICIENCY',
};

const DOMAIN_I18N_KEYS: Record<string, string> = {
  energy: 'RECO_PANEL.DOMAIN_ENERGY',
  water : 'RECO_PANEL.DOMAIN_WATER',
  gas   : 'RECO_PANEL.DOMAIN_GAS',
  fuel  : 'RECO_PANEL.DOMAIN_FUEL',
};

@Component({
  selector        : 'app-recommendation-panel',
  templateUrl     : './recommendation-panel.component.html',
  styleUrls       : ['./recommendation-panel.component.scss'],
  changeDetection : ChangeDetectionStrategy.OnPush,
})
export class RecommendationPanelComponent implements OnInit, OnDestroy {
  @Input() domain!: string;

  recommendations   : Recommendation[] = [];
  isExpanded        = false;
  isLoading         = true;
  actionLoading     = new Set<number>();
  expandedReasoning = new Set<number>();

  private destroy$ = new Subject<void>();

  isRefreshing = false;
  private llmRole = 'gestionnaire';
  private userId  = '';

  constructor(
    private recoSvc    : RecommendationsService,
    private chatTrigger: ChatTriggerService,
    private authSvc    : AuthService,
    private cdr        : ChangeDetectorRef,
    private translate  : TranslateService,
  ) {}

  ngOnInit(): void {
    const javaRole  = this.authSvc.getUserRole() ?? 'USER';
    this.llmRole    = ROLE_TO_LLM[javaRole] ?? 'gestionnaire';
    this.userId     = this.authSvc.getCurrentLogin();

    // Charge + rafraîchit toutes les 5 minutes
    interval(5 * 60 * 1000)
      .pipe(startWith(0), takeUntil(this.destroy$))
      .subscribe(() => this._load());

    // Recharge le contenu (title/description/action/reasoning localisés côté backend)
    // et recalcule les libellés traduits (getters) quand la langue de la plateforme change
    this.translate.onLangChange
      .pipe(takeUntil(this.destroy$))
      .subscribe(() => this._load());
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  private _load(): void {
    this.isLoading = true;
    this.recoSvc.getByDomain(this.domain, 'pending,accepted', 15, this.llmRole, this.userId, this.translate.currentLang)
      .pipe(takeUntil(this.destroy$))
      .subscribe(data => {
        this.recommendations = data.sort(
          (a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority]
        );
        this.isLoading = false;
        // Auto-expand si recommandation critique présente
        if (this.criticalCount > 0 && !this.isExpanded) {
          this.isExpanded = true;
        }
        this.cdr.markForCheck();
      });
  }

  // ── Computed ──────────────────────────────────────────────────────────────

  get criticalCount(): number { return this.recommendations.filter(r => r.priority === 'critical').length; }
  get highCount()    : number { return this.recommendations.filter(r => r.priority === 'high').length; }
  get totalCount()   : number { return this.recommendations.length; }

  get totalPotentialSaving(): number {
    return this.recommendations.reduce((s, r) => s + (r.estimated_saving_tnd ?? 0), 0);
  }

  get headerClass(): string {
    if (this.isLoading) return 'loading';
    if (this.criticalCount > 0) return 'has-critical';
    if (this.highCount > 0)     return 'has-high';
    if (this.totalCount > 0)    return 'has-medium';
    return 'all-ok';
  }

  get headerIcon(): string {
    if (this.isLoading)         return '⏳';
    if (this.criticalCount > 0) return '🔴';
    if (this.highCount > 0)     return '🟠';
    if (this.totalCount > 0)    return '🟡';
    return '✅';
  }

  get headerLabel(): string {
    if (this.isLoading) return this.translate.instant('RECO_PANEL.ANALYZING');
    if (this.totalCount === 0) return this.translate.instant('RECO_PANEL.ALL_OK');
    const parts: string[] = [];
    if (this.criticalCount > 0) {
      const key = this.criticalCount > 1 ? 'RECO_PANEL.CRITICAL_COUNT_PLURAL' : 'RECO_PANEL.CRITICAL_COUNT';
      parts.push(this.translate.instant(key, { count: this.criticalCount }));
    }
    if (this.highCount > 0) {
      const key = this.highCount > 1 ? 'RECO_PANEL.HIGH_COUNT_PLURAL' : 'RECO_PANEL.HIGH_COUNT';
      parts.push(this.translate.instant(key, { count: this.highCount }));
    }
    const rest = this.totalCount - this.criticalCount - this.highCount;
    if (rest > 0) {
      const key = rest > 1 ? 'RECO_PANEL.OTHER_COUNT_PLURAL' : 'RECO_PANEL.OTHER_COUNT';
      parts.push(this.translate.instant(key, { count: rest }));
    }
    return parts.join(' · ');
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  toggle(): void {
    this.isExpanded = !this.isExpanded;
    this.cdr.markForCheck();
  }

  accept(rec: Recommendation, event: MouseEvent): void {
    event.stopPropagation();
    this._updateStatus(rec, 'accepted');
  }

  dismiss(rec: Recommendation, event: MouseEvent): void {
    event.stopPropagation();
    this._updateStatus(rec, 'dismissed');
  }

  markDone(rec: Recommendation, event: MouseEvent): void {
    event.stopPropagation();
    this._updateStatus(rec, 'done');
  }

  private _updateStatus(rec: Recommendation, status: 'accepted' | 'dismissed' | 'done'): void {
    this.actionLoading.add(rec.id);
    this.cdr.markForCheck();
    this.recoSvc.updateStatus(rec.id, status, this.userId, this.translate.currentLang)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: updated => {
          const idx = this.recommendations.findIndex(r => r.id === rec.id);
          if (idx !== -1) this.recommendations[idx] = updated;
          if (status === 'dismissed' || status === 'done') {
            this.recommendations = this.recommendations.filter(r => r.id !== rec.id);
          }
          this.actionLoading.delete(rec.id);
          this.cdr.markForCheck();
        },
        error: () => {
          this.actionLoading.delete(rec.id);
          this.cdr.markForCheck();
        },
      });
  }

  triggerRefresh(event: MouseEvent): void {
    event.stopPropagation();
    if (this.isRefreshing) return;
    this.isRefreshing = true;
    this.cdr.markForCheck();

    this.recoSvc.refresh(this.llmRole, this.domain)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: () => {
          this.isRefreshing = false;
          this._load();
        },
        error: () => {
          this.isRefreshing = false;
          this.cdr.markForCheck();
        },
      });
  }

  analyzeWithAria(rec: Recommendation, event: MouseEvent): void {
    event.stopPropagation();
    const domainKey   = DOMAIN_I18N_KEYS[rec.domain];
    const domainLabel = domainKey ? this.translate.instant(domainKey) : rec.domain;
    const deviceStr   = rec.device_id
      ? this.translate.instant('RECO_PANEL.PROMPT_ON_DEVICE', { device: rec.device_id })
      : '';
    const savingStr   = rec.estimated_saving_tnd
      ? this.translate.instant('RECO_PANEL.PROMPT_SAVING', { amount: rec.estimated_saving_tnd.toFixed(2) })
      : '';
    const deviStr     = rec.deviation_pct
      ? this.translate.instant('RECO_PANEL.PROMPT_DEVIATION', { pct: rec.deviation_pct.toFixed(1) })
      : '';
    const typeKey     = REC_TYPE_I18N_KEYS[rec.rec_type];
    const typeLabel   = typeKey ? this.translate.instant(typeKey) : rec.rec_type;

    const prompt =
      `${this.translate.instant('RECO_PANEL.PROMPT_HEADER', { domain: domainLabel, device: deviceStr })}\n` +
      `${this.translate.instant('RECO_PANEL.PROMPT_TYPE', { type: typeLabel, deviation: deviStr })}\n` +
      `${rec.description}\n` +
      `${this.translate.instant('RECO_PANEL.PROMPT_ACTION', { action: rec.action, saving: savingStr })}\n` +
      `${this.translate.instant('RECO_PANEL.PROMPT_FOOTER')}`;

    this.chatTrigger.open(prompt);
  }

  // ── Template helpers ──────────────────────────────────────────────────────

  priorityClass(priority: string): string {
    return `priority-${priority}`;
  }

  recTypeIcon(recType: string): string {
    return REC_TYPE_ICONS[recType] ?? '💡';
  }

  recTypeLabel(recType: string): string {
    const key = REC_TYPE_I18N_KEYS[recType];
    return key ? this.translate.instant(key) : recType;
  }

  isActionLoading(id: number): boolean {
    return this.actionLoading.has(id);
  }

  isReasoningExpanded(id: number): boolean {
    return this.expandedReasoning.has(id);
  }

  toggleReasoning(id: number, event: MouseEvent): void {
    event.stopPropagation();
    if (this.expandedReasoning.has(id)) {
      this.expandedReasoning.delete(id);
    } else {
      this.expandedReasoning.add(id);
    }
    this.cdr.markForCheck();
  }

  trackById(_: number, rec: Recommendation): number {
    return rec.id;
  }
}
