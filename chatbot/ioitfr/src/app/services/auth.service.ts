import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, BehaviorSubject, tap, throwError } from 'rxjs';
import { environment } from '../../environments/environment';
import { JwtService } from '../core/services/jwt.service';

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: {
    login       : string;
    role        : string;
    loginPere   : string;
    userId      : string;
    permissions?: string[];
  };
}

interface EmployeeData {
  allowed_modules: string[];
  is_admin       : boolean;
}

export interface RefreshResponse {
  access_token: string;
  refresh_token?: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {

  private apiUrl       = `${environment.apiUrl}/api/auth`;
  private chatbotApi   = environment.ariaApiUrl;

  // ── Auth state observable ─────────────────────────────────
  /** Émet true/false à chaque changement d'état d'authentification. */
  private _authState$ = new BehaviorSubject<boolean>(this._hasValidToken());
  readonly authState$ = this._authState$.asObservable();

  /** Timer pour le refresh proactif du token avant expiration. */
  private _refreshTimer: any = null;

  constructor(
    private http      : HttpClient,
    private router    : Router,
    private jwtService: JwtService,
  ) {
    const token = this.getToken();
    if (token && !this.jwtService.isExpired(token)) {
      this._scheduleProactiveRefresh(token);
      // Reload modules on page refresh in case localStorage was cleared
      if (!localStorage.getItem('allowed_modules_set')) {
        this._loadEmployeeModules(this.getCurrentLogin());
      }
    }
  }

  // ---------- CONNEXION ----------
  login(login: string, password: string, _rememberMe: boolean = false): Observable<AuthResponse> {
    return this.http.post<AuthResponse>(`${this.apiUrl}/login`, { login, password }).pipe(
      tap(response => {
        localStorage.setItem('access_token', response.access_token);
        localStorage.setItem('refresh_token', response.refresh_token);
        localStorage.setItem('user', JSON.stringify(response.user));
        this._authState$.next(true);
        this._scheduleProactiveRefresh(response.access_token);
        this._loadEmployeeModules(response.user.login);
      })
    );
  }

  // ---------- DÉCONNEXION ----------
  logout(): void {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    localStorage.removeItem('allowed_modules');
    localStorage.removeItem('allowed_modules_set');
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('refresh_token');
    sessionStorage.removeItem('user');
    this._authState$.next(false);
    this._clearRefreshTimer();
    this.router.navigate(['/login']);
  }

  // ---------- MODULES CHATBOT ----------
  private _loadEmployeeModules(userId: string): void {
    if (!userId || userId === 'Inconnu') return;
    this.http.get<EmployeeData>(
      `${this.chatbotApi}/employees/${encodeURIComponent(userId)}`
    ).subscribe({
      next: emp => {
        if (emp.is_admin) {
          localStorage.removeItem('allowed_modules');
        } else {
          localStorage.setItem('allowed_modules', JSON.stringify(emp.allowed_modules ?? []));
        }
        localStorage.setItem('allowed_modules_set', '1');
      },
      error: () => {
        // User not in aria_employees → unrestricted (legacy)
        localStorage.removeItem('allowed_modules');
        localStorage.setItem('allowed_modules_set', '1');
      }
    });
  }

  getAllowedModules(): string[] | null {
    const raw = localStorage.getItem('allowed_modules');
    if (raw === null) return null;
    try { return JSON.parse(raw); } catch { return null; }
  }

  hasModule(module: string): boolean {
    if (this.getCurrentRole() === 'SUPER_ADMIN') return true;
    const modules = this.getAllowedModules();
    if (modules === null) return true;
    return modules.includes(module);
  }

  // ---------- LECTURE DES TOKENS ----------
  getToken(): string | null {
    return localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
  }

  getRefreshToken(): string | null {
    return localStorage.getItem('refresh_token') || sessionStorage.getItem('refresh_token');
  }

  getUser() {
    const userStr = localStorage.getItem('user') || sessionStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
  }

  hasPermission(permission: string): boolean {
    const token = this.getToken();
    if (!token) return false;
    const claims = this.jwtService.decode(token);
    if (!claims) return false;
    return (claims.groups ?? []).includes(permission);
  }

  // ---------- VÉRIFICATION D'AUTHENTIFICATION ----------
  isAuthenticated(): boolean {
    const token = this.getToken();
    if (!token) return false;
    return !this.jwtService.isExpired(token);
  }

  // ---------- REFRESH PROACTIF ─────────────────────────────
  /**
   * Planifie un refresh automatique du token 60 secondes avant son expiration.
   * Évite que l'utilisateur soit déconnecté en pleine utilisation.
   */
  private _scheduleProactiveRefresh(token: string): void {
    this._clearRefreshTimer();
    const expiresIn = this.jwtService.expiresIn(token); // secondes
    if (expiresIn <= 0) return;

    // Refresh 60s avant expiration (minimum 5s pour éviter les loops)
    const delay = Math.max((expiresIn - 60) * 1000, 5000);

    this._refreshTimer = setTimeout(() => {
      this.refreshToken().subscribe({
        next : (res) => this._scheduleProactiveRefresh(res.access_token),
        error: ()    => this.logout(),
      });
    }, delay);
  }

  private _clearRefreshTimer(): void {
    if (this._refreshTimer) {
      clearTimeout(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  private _hasValidToken(): boolean {
    const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
    if (!token) return false;
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return payload.exp > Math.floor(Date.now() / 1000);
    } catch { return false; }
  }

  getUserRole(): string | null {
    const user = this.getUser();
    return user ? user.role : null;
  }

  // ==================== NOUVELLES MÉTHODES POUR LE DASHBOARD ====================
  
  /**
   * Récupère le login de l'utilisateur connecté
   */
  getCurrentLogin(): string {
    const user = this.getUser();
    return user?.login ?? 'Inconnu';
  }

  /**
   * Récupère le rôle de l'utilisateur connecté
   */
  getCurrentRole(): string {
    const user = this.getUser();
    return user?.role ?? 'USER';
  }

  /**
   * Récupère le vrai nom à partir du login (ex: "wassef.ayari" -> "Wassef Ayari")
   */
 getFullName(): string {
  const user = this.getUser();
  if (!user) return 'Utilisateur';

  // Supprimer le domaine email : "chouikhisamar93@gmail.com" → "chouikhisamar93"
  const login = (user.login as string).split('@')[0];

  // Supprimer les chiffres : "chouikhisamar93" → "chouikhisamar"
  const clean = login.replace(/\d+/g, '');

  // Séparateur classique : wassef.ayari → "Wassef Ayari"
  const parts = clean.split(/[._\-\s]+/).filter(p => p.length > 0);
  if (parts.length >= 2) {
    const first = parts[0].charAt(0).toUpperCase() + parts[0].slice(1).toLowerCase();
    const last  = parts[1].charAt(0).toUpperCase() + parts[1].slice(1).toLowerCase();
    return `${first} ${last}`;
  }

  // CamelCase : chouikhiSamar → "Chouikhi Samar"
  const split = clean.replace(/([A-Z])/g, ' $1').trim();
  if (split.includes(' ')) {
    return split.split(' ')
      .map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
      .join(' ');
  }

  // Fallback : capitaliser juste le premier mot
  return clean.charAt(0).toUpperCase() + clean.slice(1).toLowerCase();
}

  /**
   * Récupère les initiales pour l'avatar (ex: "waxx.ayyy" -> "WA")
   */
getInitials(): string {
  const raw = this.getCurrentLogin();
  // Supprimer le domaine email si présent : "chouikhisamar93@gmail.com" → "chouikhisamar93"
  const login = raw.split('@')[0];

  // Séparateur classique : yyy.xx /yy_xx
  const parts = login.split(/[._\-\s]+/).filter(p => p.length > 0);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }

  // CamelCase : chouikhiSamar → CS
  const camel = login.match(/[A-Z]/g);
  if (camel && camel.length >= 1) {
    return (login[0] + camel[0]).toUpperCase();
  }

  // Fallback : 2 premières lettres
  return login.substring(0, 2).toUpperCase();
}
  

  /**
   * Récupère le label du rôle en français
   */
  getRoleLabel(): string {
    const role = this.getCurrentRole();
    switch (role) {
      case 'SUPER_ADMIN': return 'Super Administrateur';
      case 'EMPLOYEE':    return 'Employé';
      case 'ADMIN':       return 'Administrateur';
      default:            return 'Utilisateur';
    }
  }

  /**
   * Récupère le statut de sécurité (expiration du token, tentatives échouées)
   */
  getSecurityStatus() {
    const token = this.getToken();
    if (!token) return { isExpiringSoon: false, daysUntilExpiry: 0, attempts: 0 };

    const claims = this.jwtService.decode(token);
    if (!claims) return { isExpiringSoon: false, daysUntilExpiry: 0, attempts: 0 };

    const now = Math.floor(Date.now() / 1000);
    const daysUntilExpiry = Math.floor((claims.exp - now) / (24 * 60 * 60));
    const isExpiringSoon = daysUntilExpiry <= 7 && daysUntilExpiry > 0;
    const attempts = parseInt(localStorage.getItem('login_attempts') || '0');

    return {
      isExpiringSoon,
      daysUntilExpiry,
      attempts,
      expiresAt: new Date(claims.exp * 1000)
    };
  }

  /**
   * Vérifie si le mot de passe est bientôt expiré (moins de 7 jours)
   */
  isPasswordExpiring(): boolean {
    const security = this.getSecurityStatus();
    return security.isExpiringSoon && security.daysUntilExpiry > 0;
  }

  // ---------- REFRESH TOKEN (avec conservation du même storage) ----------
  refreshToken(): Observable<RefreshResponse> {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) {
      return throwError(() => new Error('Aucun refresh token disponible'));
    }

    const body: RefreshRequest = { refresh_token: refreshToken };

    return this.http.post<RefreshResponse>(`${this.apiUrl}/refresh`, body).pipe(
      tap(response => {
        // Toujours dans localStorage (cohérent avec login())
        localStorage.setItem('access_token', response.access_token);
        if (response.refresh_token) {
          localStorage.setItem('refresh_token', response.refresh_token);
        }
        this._authState$.next(true);
      }),
    );
  }

  // ---------- UTILITAIRES ----------
}