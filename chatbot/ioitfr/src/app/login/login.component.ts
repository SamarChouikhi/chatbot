import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { TranslateService } from '@ngx-translate/core';
import { LanguageService, AppLang } from '../core/services/language.service';
import { ThemeService } from '../core/services/theme.service';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss']
})
export class LoginComponent implements OnInit {
  loginForm!: FormGroup;
  isLoading = false;
  showPassword = false;
  errorMessage = '';
  returnUrl = '/dashboard';

  get isDark(): boolean { return this.themeSvc.isDark; }
  get currentLang(): AppLang { return this.langSvc.current; }
  get langs(): AppLang[] { return this.langSvc.langs; }
  switchLang(lang: AppLang): void { this.langSvc.use(lang); }
  langLabel(lang: AppLang): string {
    return { fr: 'FR', en: 'EN', ar: 'ع' }[lang];
  }

  constructor(
    private fb: FormBuilder,
    private router: Router,
    private route: ActivatedRoute,
    private authService: AuthService,
    private translate: TranslateService,
    private langSvc: LanguageService,
    private themeSvc: ThemeService
  ) {}

  ngOnInit(): void {
    this.loginForm = this.fb.group({
      email: ['', [Validators.required]], 
      password: ['', [Validators.required]],
      rememberMe: [false]
    });

    this.returnUrl = this.route.snapshot.queryParams['returnUrl'] || '/dashboard';

    // Si déjà connecté, rediriger
    if (this.authService.isAuthenticated()) {
      this.router.navigate([this.returnUrl]);
    }
  }

  onSubmit(): void {
    if (this.loginForm.invalid) {
      this.markFormGroupTouched(this.loginForm);
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';

    const loginValue = (this.loginForm.value.email || '').trim();
    const passwordValue = this.loginForm.value.password;
    const rememberMe = this.loginForm.value.rememberMe; // ← valeur de la case

    this.authService.login(loginValue, passwordValue, rememberMe).subscribe({
      next: () => {
        this.router.navigate([this.returnUrl]);
      },
      error: (err) => {
        this.isLoading = false;
        if (err.status === 401) {
          this.errorMessage = err.error?.message || err.error?.error || this.translate.instant('LOGIN.ERR_INVALID');
        } else if (err.status === 0) {
          this.errorMessage = this.translate.instant('LOGIN.ERR_SERVER');
        } else {
          this.errorMessage = this.translate.instant('LOGIN.ERR_GENERIC');
        }
      }
    });
  }

  togglePasswordVisibility(): void {
    this.showPassword = !this.showPassword;
  }

  isFieldInvalid(fieldName: string): boolean {
    const field = this.loginForm.get(fieldName);
    return !!(field && field.invalid && (field.dirty || field.touched));
  }

  private markFormGroupTouched(formGroup: FormGroup): void {
    Object.keys(formGroup.controls).forEach(key => {
      const control = formGroup.get(key);
      control?.markAsTouched();
      if (control instanceof FormGroup) {
        this.markFormGroupTouched(control);
      }
    });
  }
}