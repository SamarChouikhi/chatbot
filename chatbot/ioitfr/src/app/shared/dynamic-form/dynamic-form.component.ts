import {
  Component, Input, Output, EventEmitter, OnInit, OnChanges
} from '@angular/core';
import {
  FormBuilder, FormGroup, FormArray,
  Validators, AbstractControl
} from '@angular/forms';
import { Observable } from 'rxjs';
import { finalize } from 'rxjs/operators';
import { TranslateService } from '@ngx-translate/core';
import { FieldConfig } from './field-config';
import { NotificationService } from '../../core/services/notification.service';

@Component({
  selector: 'app-dynamic-form',
  templateUrl: './dynamic-form.component.html',
  styleUrls: ['./dynamic-form.component.scss']
})
export class DynamicFormComponent implements OnInit, OnChanges {

  // ── Inputs ──────────────────────────────────────────────────────────────────

  /** Définition des champs à afficher */
  @Input() fields: FieldConfig[] = [];

  /** true → affiche +/− pour ajouter/supprimer des lignes (FormArray) */
  @Input() repeatable = false;

  /** Pré-remplissage en mode non-répétable */
  @Input() initialValue: Record<string, any> | null = null;

  /** Pré-remplissage en mode répétable (une entrée par ligne) */
  @Input() initialRows: Record<string, any>[] = [];

  /** Texte du bouton submit (clé i18n ou libellé déjà résolu) */
  @Input() submitLabel = 'DYN_FORM.SUBMIT';

  /**
   * Fonction appelée lors du submit.
   * Elle reçoit les valeurs du formulaire et doit retourner un Observable.
   * Si non fournie, le composant se contente d'émettre (formSubmit).
   */
  @Input() submitFn?: (data: any) => Observable<any>;

  /** Message toast affiché en cas de succès (clé i18n ou message déjà résolu) */
  @Input() successMessage = 'DYN_FORM.DEFAULT_SUCCESS';

  /** Message toast affiché en cas d'erreur API (clé i18n ou message déjà résolu) */
  @Input() errorMessage = 'DYN_FORM.DEFAULT_ERROR';

  /** Afficher un bouton Annuler */
  @Input() showCancel = false;

  // ── Outputs ─────────────────────────────────────────────────────────────────

  /** Émet la réponse API (ou les valeurs du form si pas de submitFn) */
  @Output() formSubmit = new EventEmitter<any>();

  /** Émet quand l'utilisateur clique Annuler */
  @Output() formCancel = new EventEmitter<void>();

  // ── État interne ─────────────────────────────────────────────────────────────

  form!: FormGroup;
  loading = false;

  constructor(
    private fb:        FormBuilder,
    private notif:     NotificationService,
    private translate: TranslateService
  ) {}

  ngOnInit():    void { this.buildForm(); }
  ngOnChanges(): void { if (this.form) this.buildForm(); }

  // ════════════════════════════════════════════════════════════════════════════
  // Construction du formulaire
  // ════════════════════════════════════════════════════════════════════════════

  private buildForm(): void {
    if (this.repeatable) {
      const rows = this.initialRows.length
        ? this.initialRows.map(r => this.buildRow(r))
        : [this.buildRow()];
      this.form = this.fb.group({ rows: this.fb.array(rows) });
    } else {
      this.form = this.buildRow(this.initialValue ?? undefined);
    }
  }

  /** Construit un FormGroup à partir de la config `fields` */
  private buildRow(data?: Record<string, any>): FormGroup {
    const group: Record<string, any> = {};
    for (const f of this.fields) {
      const val        = data?.[f.key] ?? f.defaultValue ?? this.emptyFor(f);
      const validators = [];
      if (f.required)              validators.push(Validators.required);
      if (f.type === 'email')      validators.push(Validators.email);
      if (f.min      !== undefined) validators.push(Validators.min(f.min));
      if (f.max      !== undefined) validators.push(Validators.max(f.max));
      if (f.minLength !== undefined) validators.push(Validators.minLength(f.minLength));
      if (f.maxLength !== undefined) validators.push(Validators.maxLength(f.maxLength));
      group[f.key] = [val, validators];
    }
    return this.fb.group(group);
  }

  private emptyFor(f: FieldConfig): any {
    if (f.type === 'checkbox') return false;
    if (f.type === 'number')   return null;
    return '';
  }

  // ════════════════════════════════════════════════════════════════════════════
  // Helpers FormArray (mode répétable)
  // ════════════════════════════════════════════════════════════════════════════

  get rows(): FormArray {
    return this.form.get('rows') as FormArray;
  }

  getRow(i: number): FormGroup {
    return this.rows.at(i) as FormGroup;
  }

  addRow(): void {
    this.rows.push(this.buildRow());
  }

  removeRow(i: number): void {
    if (this.rows.length > 1) this.rows.removeAt(i);
  }

  // ════════════════════════════════════════════════════════════════════════════
  // Helpers validation (pour le template)
  // ════════════════════════════════════════════════════════════════════════════

  ctrl(key: string): AbstractControl | null {
    return this.form.get(key);
  }

  ctrlAt(row: number, key: string): AbstractControl | null {
    return this.getRow(row).get(key);
  }

  isInvalid(key: string, row?: number): boolean {
    const c = row !== undefined ? this.ctrlAt(row, key) : this.ctrl(key);
    return !!(c?.invalid && c.touched);
  }

  errMsg(key: string, row?: number): string {
    const c = row !== undefined ? this.ctrlAt(row, key) : this.ctrl(key);
    if (!c?.errors) return '';
    if (c.errors['required'])  return this.translate.instant('DYN_FORM.VALIDATION.REQUIRED');
    if (c.errors['email'])     return this.translate.instant('DYN_FORM.VALIDATION.EMAIL');
    if (c.errors['min'])       return this.translate.instant('DYN_FORM.VALIDATION.MIN', { min: c.errors['min'].min });
    if (c.errors['max'])       return this.translate.instant('DYN_FORM.VALIDATION.MAX', { max: c.errors['max'].max });
    if (c.errors['minlength']) return this.translate.instant('DYN_FORM.VALIDATION.MINLENGTH', { length: c.errors['minlength'].requiredLength });
    if (c.errors['maxlength']) return this.translate.instant('DYN_FORM.VALIDATION.MAXLENGTH', { length: c.errors['maxlength'].requiredLength });
    return this.translate.instant('DYN_FORM.VALIDATION.INVALID');
  }

  // ════════════════════════════════════════════════════════════════════════════
  // Soumission
  // ════════════════════════════════════════════════════════════════════════════

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const value = this.repeatable ? this.rows.value : this.form.value;

    if (!this.submitFn) {
      // pas de fonction API fournie → émission directe
      this.formSubmit.emit(value);
      return;
    }

    this.loading = true;
    this.submitFn(value)
      .pipe(finalize(() => this.loading = false))
      .subscribe({
        next: (res) => {
          this.notif.push({
            severity: 'info',
            title:    this.translate.instant('DYN_FORM.SUCCESS_TITLE'),
            message:  this.translate.instant(this.successMessage)
          });
          this.formSubmit.emit(res ?? value);
          this.buildForm();  // reset après succès
        },
        error: (err) => {
          const msg = err?.error?.message ?? this.translate.instant(this.errorMessage);
          this.notif.push({ severity: 'high', title: this.translate.instant('DYN_FORM.ERROR_TITLE'), message: msg });
        }
      });
  }

  onCancel(): void {
    this.formCancel.emit();
  }
}
