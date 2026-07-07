import { Component, OnDestroy } from '@angular/core';
import {
  FormBuilder, FormGroup, Validators,
  AbstractControl, ValidationErrors
} from '@angular/forms';
import { Router } from '@angular/router';
import { Subject, Subscription, interval } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { RecoveryService } from '../../services/recovery.service';
import { TranslateService } from '@ngx-translate/core';
import { LanguageService, AppLang } from '../../core/services/language.service';
import { ThemeService } from '../../core/services/theme.service';

type RecoveryStep = 'request' | 'verify' | 'reset' | 'success';

@Component({
  selector: 'app-forgot-password',
  templateUrl: './forgot-password.component.html',
  styleUrls: ['./forgot-password.component.scss']
})
export class ForgotPasswordComponent implements OnDestroy {

  // ─── Lifecycle ────────────────────────────────────────────
  private destroy$     = new Subject<void>();   // détruit le composant
  private timerStop$   = new Subject<void>();   // stoppe uniquement le timer
  private timerSub    ?: Subscription;

  // ─── Formulaires ─────────────────────────────────────────
  requestForm : FormGroup;
  verifyForm  : FormGroup;
  resetForm   : FormGroup;

  // ─── État UI ──────────────────────────────────────────────
  currentStep         : RecoveryStep = 'request';
  isLoading           = false;
  errorMessage        = '';
  showPassword        = false;
  showConfirmPassword = false;
  timeRemaining       = 0;

  // ─── Données internes (jamais exposées au template) ───────
  private _email      = '';
  private _resetToken = '';

  get isDark(): boolean { return this.themeSvc.isDark; }
  get currentLang(): AppLang { return this.langSvc.current; }
  get langs(): AppLang[] { return this.langSvc.langs; }
  switchLang(lang: AppLang): void { this.langSvc.use(lang); }
  langLabel(lang: AppLang): string { return { fr: 'FR', en: 'EN', ar: 'ع' }[lang]; }

  constructor(
    private fb              : FormBuilder,
    private router          : Router,
    private recoveryService : RecoveryService,
    private translate       : TranslateService,
    private langSvc         : LanguageService,
    private themeSvc        : ThemeService
  ) {
    this.requestForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]]
    });

    this.verifyForm = this.fb.group({
      code: ['', [
        Validators.required,
        Validators.minLength(6),
        Validators.maxLength(6)
      ]]
    });

    this.resetForm = this.fb.group(
      {
        newPassword    : ['', [Validators.required, Validators.minLength(8)]],
        confirmPassword: ['', Validators.required]
      },
      { validators: this._passwordMatchValidator }
    );
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    this.timerStop$.next();
    this.timerStop$.complete();
  }

  // ════════════════════════════════════════════════════════
  // ÉTAPE 1 — Demande de code par email
  // ════════════════════════════════════════════════════════
  onRequestRecovery(): void {
    if (this.requestForm.invalid) { this._touch(this.requestForm); return; }

    this.isLoading    = true;
    this.errorMessage = '';

    this.recoveryService.requestRecovery(this.requestForm.value.email)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: () => {
          this._email       = this.requestForm.value.email;
          this.currentStep  = 'verify';
          this.isLoading    = false;
          this._startTimer();
        },
        error: (err) => {
          this.isLoading    = false;
          this.errorMessage = this._mapError(err, 'FORGOT.ERR_SEND');
        }
      });
  }

  // ════════════════════════════════════════════════════════
  // ÉTAPE 2 — Vérification du code reçu par email
  // ════════════════════════════════════════════════════════
  onVerifyCode(): void {
    if (this.verifyForm.invalid) { this._touch(this.verifyForm); return; }
    if (this.timeRemaining === 0) {
      this.errorMessage = this.translate.instant('FORGOT.ERR_EXPIRED');
      return;
    }

    this.isLoading    = true;
    this.errorMessage = '';

    this.recoveryService.verifyCode(this._email, this.verifyForm.value.code)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (resp: { resetToken: string }) => {
          this._resetToken  = resp.resetToken;
          this.currentStep  = 'reset';
          this.isLoading    = false;
          this._stopTimer();
        },
        error: (err: { status: number; error?: any }) => {
          this.isLoading    = false;
          this.errorMessage = this._mapError(err, 'FORGOT.ERR_INVALID_CODE');
        }
      });
  }

  // ════════════════════════════════════════════════════════
  // ÉTAPE 3 — Nouveau mot de passe
  // ════════════════════════════════════════════════════════
  onResetPassword(): void {
    if (this.resetForm.invalid) { this._touch(this.resetForm); return; }

    this.isLoading    = true;
    this.errorMessage = '';

    this.recoveryService.resetPassword(this._resetToken, this.resetForm.value.newPassword)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: () => {
          this.currentStep = 'success';
          this.isLoading   = false;
        },
        error: (err) => {
          this.isLoading    = false;
          this.errorMessage = this._mapError(err, 'FORGOT.ERR_RESET');
        }
      });
  }

  // ════════════════════════════════════════════════════════
  // NAVIGATION
  // ════════════════════════════════════════════════════════
  goToLogin(): void {
    this.router.navigate(['/login']);
  }

  restartRequest(): void {
    this._stopTimer();
    this.currentStep  = 'request';
    this.errorMessage = '';
    this.verifyForm.reset();
  }

  // ════════════════════════════════════════════════════════
  // STEPPER
  // ════════════════════════════════════════════════════════
  isDone(step: RecoveryStep): boolean {
    const order: RecoveryStep[] = ['request', 'verify', 'reset', 'success'];
    return order.indexOf(this.currentStep) > order.indexOf(step);
  }

  // ════════════════════════════════════════════════════════
  // TIMER — Subject dédié, indépendant du lifecycle
  // ════════════════════════════════════════════════════════
  private _startTimer(): void {
    this._stopTimer();
    this.timeRemaining = 600; // 10 minutes
    this.timerStop$    = new Subject<void>();

    this.timerSub = interval(1000)
      .pipe(takeUntil(this.timerStop$))
      .subscribe(() => {
        if (this.timeRemaining > 0) {
          this.timeRemaining--;
        } else {
          this._stopTimer();
        }
      });
  }

  private _stopTimer(): void {
    this.timerStop$.next();
    this.timerSub?.unsubscribe();
  }

  formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  // ════════════════════════════════════════════════════════
  // FORCE DU MOT DE PASSE
  // ════════════════════════════════════════════════════════
  get passwordStrengthClass(): string {
    const pwd = this.resetForm.get('newPassword')?.value || '';
    if (pwd.length < 8) return 'weak';
    const score = [/[A-Z]/.test(pwd), /[0-9]/.test(pwd), /[^A-Za-z0-9]/.test(pwd)]
      .filter(Boolean).length;
    if (score === 3) return 'strong';
    if (score >= 1) return 'medium';
    return 'weak';
  }

  get passwordStrengthLabel(): string {
    const map: Record<string, string> = {
      weak  : 'FORGOT.STRENGTH_WEAK',
      medium: 'FORGOT.STRENGTH_MEDIUM',
      strong: 'FORGOT.STRENGTH_STRONG'
    };
    return this.translate.instant(map[this.passwordStrengthClass] ?? 'FORGOT.STRENGTH_WEAK');
  }

  get passwordMismatch(): boolean {
    return this.resetForm.hasError('mismatch')
      && !!this.resetForm.get('confirmPassword')?.touched;
  }

  // ════════════════════════════════════════════════════════
  // HELPERS
  // ════════════════════════════════════════════════════════
  isFieldInvalid(form: FormGroup, field: string): boolean {
    const ctrl = form.get(field);
    return !!(ctrl?.invalid && (ctrl.dirty || ctrl.touched));
  }

  private _touch(form: FormGroup): void {
    Object.values(form.controls).forEach(c => c.markAsTouched());
  }

  private _mapError(err: any, fallbackKey: string): string {
    if (err.status === 0)   return this.translate.instant('FORGOT.ERR_SERVER');
    if (err.status === 404) return this.translate.instant('FORGOT.ERR_NOT_FOUND');
    if (err.status === 429) return this.translate.instant('FORGOT.ERR_TOO_MANY');
    return err.error?.message || err.error?.error || this.translate.instant(fallbackKey);
  }

  private _passwordMatchValidator(group: AbstractControl): ValidationErrors | null {
    const pass    = group.get('newPassword')?.value;
    const confirm = group.get('confirmPassword')?.value;
    return pass === confirm ? null : { mismatch: true };
  }
}
