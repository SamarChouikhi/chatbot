import {
  Component, OnInit, OnDestroy,
  HostListener, ElementRef
} from '@angular/core';
import { Router, NavigationEnd, ActivatedRoute } from '@angular/router';
import { Subject } from 'rxjs';
import { filter, takeUntil } from 'rxjs/operators';
import { AuthService } from '../services/auth.service';
import { UserService, UUser } from '../services/users.service';
import { ShellService, ShellState } from '../core/services/shell.service';
import { AlertService, Alert } from '../services/alerts.service';
import { ThemeService } from '../core/services/theme.service';

@Component({
  selector: 'app-shell',
  templateUrl: './shell.component.html',
  styleUrls: ['./shell.component.scss']
})
export class ShellComponent implements OnInit, OnDestroy {

  sidebarCollapsed  = false;
  showUserMenu      = false;
  showAlertDropdown = false;
  showProfileModal  = false;
  alertsLoading     = false;
  recentAlerts: Alert[] = [];
  currentUser: UUser | null = null;
  securityMessage  = '✅ Sécurité optimale';
  passwordExpiring = false;
  daysUntilExpiry: number | string = '?';
  forbiddenMsg     = false;
  pageTitle        = 'Dashboard';

  state: ShellState = {
    elecCritical: 0, waterLeaks: 0, gazLeaks: 0, totalAlerts: 0, criticalCount: 0
  };

  private destroy$    = new Subject<void>();
  private secInterval: any;

  get userLogin():         string  { return this.auth.getCurrentLogin(); }
  get userInitials():      string  { return this.auth.getInitials(); }
  get userRoleLabel():     string  { return this.auth.getRoleLabel(); }
  get userName():          string  { return this.auth.getFullName(); }
  // ── Navigation permissions (driven by role permissions) ──
  get canViewDashboard():  boolean { return this.auth.hasPermission('VIEW_DASHBOARD'); }
  get canViewElec():       boolean { return this.auth.hasPermission('VIEW_ENERGY_DATA'); }
  get canViewWater():      boolean { return this.auth.hasPermission('VIEW_WATER_DATA'); }
  get canViewGaz():        boolean { return this.auth.hasPermission('VIEW_GAS_DATA'); }
  get canViewFuel():       boolean { return this.auth.hasPermission('EXPORT_DATA'); }
  get canViewAlerts():     boolean { return this.auth.hasPermission('VIEW_ALERTS') || this.auth.hasPermission('MANAGE_ALERTS'); }
  get canViewUsers():      boolean { return this.auth.hasPermission('MANAGE_USERS') || this.auth.hasPermission('VIEW_USERS'); }
  get canViewRoles():      boolean { return this.auth.hasPermission('MANAGE_ROLES'); }
  get canViewDevices():    boolean { return this.auth.hasPermission('VIEW_DEVICES') || this.auth.hasPermission('MANAGE_DEVICES'); }
  get showAdminSection():  boolean { return this.canViewUsers || this.canViewRoles || this.canViewDevices; }
  get canUseChatbot():     boolean { return this.auth.isAuthenticated(); }

  get isDark(): boolean { return this.theme.isDark; }
  toggleTheme(): void { this.theme.toggle(); }

  constructor(
    private auth:      AuthService,
    private userSvc:   UserService,
    private shellSvc:  ShellService,
    private alertSvc:  AlertService,
    private router:    Router,
    private route:     ActivatedRoute,
    private elRef:     ElementRef,
    private theme:     ThemeService,
  ) {}

  ngOnInit(): void {
    this.sidebarCollapsed = window.innerWidth < 768;
    this.loadSecurityStatus();
    this.secInterval = setInterval(() => this.loadSecurityStatus(), 60_000);

    this.shellSvc.state$.pipe(takeUntil(this.destroy$))
      .subscribe(s => this.state = s);

    this.router.events.pipe(
      filter(e => e instanceof NavigationEnd),
      takeUntil(this.destroy$)
    ).subscribe(() => {
      if (this.router.url.includes('forbidden=1')) {
        this.forbiddenMsg = true;
        this.router.navigate([], { replaceUrl: true });
        setTimeout(() => this.forbiddenMsg = false, 4000);
      }
      this.pageTitle = this.deepestTitle();
    });

    this.pageTitle = this.deepestTitle();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    clearInterval(this.secInterval);
  }

  toggleSidebar(): void { this.sidebarCollapsed = !this.sidebarCollapsed; }

  toggleAlertDropdown(): void {
    this.showAlertDropdown = !this.showAlertDropdown;
    if (this.showAlertDropdown && this.recentAlerts.length === 0) {
      this.alertsLoading = true;
      this.alertSvc.list(0, 6).pipe(takeUntil(this.destroy$)).subscribe({
        next:  res => { this.recentAlerts = res.data; this.alertsLoading = false; },
        error: ()  => { this.alertsLoading = false; }
      });
    }
    this.showUserMenu = false;
  }

  goToAlerts(): void {
    this.showAlertDropdown = false;
    this.router.navigate(['/alerts']);
  }

  alertLevel(type: string): string {
    const t = (type || '').toLowerCase();
    if (t.includes('critical') || t.includes('error') || t.includes('voltage') || t.includes('signal') || t.includes('overconsumption')) return 'critical';
    if (t.includes('warning') || t.includes('temperature') || t.includes('humidity') || t.includes('power_factor') || t.includes('thd')) return 'warning';
    return 'info';
  }

  toggleUserMenu(): void {
    this.showUserMenu = !this.showUserMenu;
    if (this.showUserMenu) {
      this.currentUser = this.buildUserFromToken();
      this.userSvc.getOne(this.userLogin).pipe(takeUntil(this.destroy$))
        .subscribe({ next: u => this.currentUser = u, error: () => {} });
    }
  }

  openProfile(): void {
    this.showUserMenu = false;
    this.currentUser  = this.buildUserFromToken();
    this.showProfileModal = true;
    this.userSvc.getOne(this.userLogin).pipe(takeUntil(this.destroy$))
      .subscribe({ next: u => this.currentUser = u, error: () => {} });
  }

  private buildUserFromToken(): UUser {
    const u = this.auth.getUser();
    return {
      login          : u?.login     ?? this.userLogin,
      loginPere      : u?.loginPere ?? null,
      roleName       : this.auth.getRoleLabel(),
      phone          : null,
      pwdExpDate     : null,
      gmtPlus        : null,
      isAdvisor      : null,
      loginFb        : null,
      idFb           : null,
      idFbMsg        : null,
      resetToken     : null,
      resetTokenExpiry: null,
      failedAttempts : null,
      blockedUntil   : null,
    };
  }

  closeProfile(): void { this.showProfileModal = false; }

  logout(): void { this.auth.logout(); }

  private deepestTitle(): string {
    let r = this.route;
    while (r.firstChild) r = r.firstChild;
    return r.snapshot.data['title'] ?? 'Dashboard';
  }

  private loadSecurityStatus(): void {
    const s = this.auth.getSecurityStatus();
    this.passwordExpiring   = this.auth.isPasswordExpiring();
    this.daysUntilExpiry    = s?.daysUntilExpiry ?? '?';
    this.securityMessage    = this.passwordExpiring
      ? `⚠️ Mot de passe expire dans ${this.daysUntilExpiry} jours`
      : '✅ Sécurité optimale';
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(e: MouseEvent): void {
    const el = this.elRef.nativeElement;
    if (!el.querySelector('.user-menu-wrap')?.contains(e.target as HTMLElement))
      this.showUserMenu = false;
    if (!el.querySelector('.alert-pill-wrap')?.contains(e.target as HTMLElement))
      this.showAlertDropdown = false;
  }

  @HostListener('document:keydown.escape')
  onEsc(): void { this.showUserMenu = false; this.showAlertDropdown = false; }

  @HostListener('window:resize')
  onResize(): void {
    if (window.innerWidth >= 768 && this.sidebarCollapsed) return;
    if (window.innerWidth < 768) this.sidebarCollapsed = true;
  }
}
