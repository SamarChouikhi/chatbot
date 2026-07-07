import { Component, EventEmitter, Output } from '@angular/core';
import { Observable } from 'rxjs';
import {
  NotificationService, AlertRule, ToastSeverity
} from '../../core/services/notification.service';

type Metric = 'THD' | 'COSFI' | 'CONSO';

interface RuleForm {
  label:     string;
  metric:    Metric;
  operator:  '>' | '<';
  threshold: number;
  severity:  ToastSeverity;
  enabled:   boolean;
}

@Component({
  selector: 'app-alert-rules',
  templateUrl: './alert-rules.component.html',
  styleUrls: ['./alert-rules.component.scss']
})
export class AlertRulesComponent {

  @Output() close = new EventEmitter<void>();

  readonly rules$:       Observable<AlertRule[]>;
  readonly liveMetrics$: Observable<Record<string, number>>;

  form: RuleForm     = this.blankForm();
  showForm           = false;
  editingId: string | null = null;

  readonly metrics: Metric[]          = ['THD', 'COSFI', 'CONSO'];
  readonly severities: ToastSeverity[] = ['critical', 'high', 'low', 'info'];

  readonly metricLabels: Record<Metric, string> = {
    THD:   'THD — distorsion harmonique (%)',
    COSFI: 'cos φ — facteur de puissance',
    CONSO: 'Consommation mensuelle (kWh)',
  };
  readonly metricUnits: Record<Metric, string>  = { THD: '%', COSFI: '', CONSO: 'kWh' };

  readonly metricDefaults: Record<Metric, { op: '>' | '<'; threshold: number }> = {
    THD:   { op: '>', threshold: 5    },
    COSFI: { op: '<', threshold: 0.85 },
    CONSO: { op: '>', threshold: 500  },
  };

  readonly sevColors: Record<ToastSeverity, string> = {
    critical: '#ef4444', high: '#f97316', low: '#eab308', info: '#3b82f6',
  };
  readonly sevLabels: Record<ToastSeverity, string> = {
    critical: 'Critique', high: 'Haute', low: 'Basse', info: 'Info',
  };

  constructor(private notif: NotificationService) {
    this.rules$       = this.notif.rules$;
    this.liveMetrics$ = this.notif.liveMetrics$;
  }

  openAdd(): void {
    this.form      = this.blankForm();
    this.editingId = null;
    this.showForm  = true;
  }

  openEdit(rule: AlertRule): void {
    this.form = {
      label: rule.label, metric: rule.metric, operator: rule.operator,
      threshold: rule.threshold, severity: rule.severity, enabled: rule.enabled,
    };
    this.editingId = rule.id;
    this.showForm  = true;
  }

  cancelForm(): void { this.showForm = false; this.editingId = null; }

  onMetricChange(): void {
    const d             = this.metricDefaults[this.form.metric];
    this.form.operator  = d.op;
    this.form.threshold = d.threshold;
    this.form.label     = this.metricLabels[this.form.metric];
  }

  save(): void {
    if (!this.form.label?.trim()) return;
    if (this.editingId) {
      this.notif.updateRule({ ...this.form, id: this.editingId });
    } else {
      this.notif.addRule(this.form);
    }
    this.showForm  = false;
    this.editingId = null;
  }

  toggle(rule: AlertRule): void { this.notif.toggleRule(rule.id); }
  remove(rule: AlertRule): void { this.notif.removeRule(rule.id); }

  test(rule: AlertRule): void {
    this.notif.push({
      severity: rule.severity,
      title:    `[TEST] ${rule.label}`,
      message:  `Simulation — seuil : ${rule.threshold}${this.metricUnits[rule.metric]}`,
    });
  }

  private blankForm(): RuleForm {
    return { label: 'THD élevé', metric: 'THD', operator: '>', threshold: 5, severity: 'high', enabled: true };
  }
}
