import { Component, OnInit, OnDestroy } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged, takeUntil } from 'rxjs/operators';
import { UserService, UUser } from '../services/users.service';
import { RolesService, Role } from '../services/roles.service';
import { EmployeesService } from '../services/employees.service';
import { DeviceService, Device } from '../services/device.service';
import { AuthService } from '../services/auth.service';

type ModalMode = 'view' | 'create' | 'edit' | 'delete' | null;

@Component({
  selector: 'app-users',
  templateUrl: './users.component.html',
  styleUrls: ['./users.component.scss']
})
export class UsersComponent implements OnInit, OnDestroy {

  // ── Data ──────────────────────────────────────────────────────
  users: UUser[] = [];
  total          = 0;

  // ── Pagination ────────────────────────────────────────────────
  page = 0;
  size = 10;
  get totalPages(): number    { return Math.ceil(this.total / this.size); }
  get pageNumbers(): number[] { return Array.from({ length: this.totalPages }, (_, i) => i); }

  // ── Filters ───────────────────────────────────────────────────
  searchQuery   = '';
  filterAdvisor = '';
  filterBlocked = false;

  // ── Sort ──────────────────────────────────────────────────────
  sortCol = 'login';
  sortDir: 'asc' | 'desc' = 'asc';

  // ── State ─────────────────────────────────────────────────────
  loading    = false;
  saving     = false;
  resetting  = '';
  errorMsg   = '';
  successMsg = '';
  showPwd    = false;
  private successTimer: any;

  // ── Modal ─────────────────────────────────────────────────────
  modalMode: ModalMode       = null;
  selectedUser: UUser | null = null;
  form!: FormGroup;

  roles: Role[] = [];

  // ── Chatbot modules ───────────────────────────────────────────
  availableModules: string[] = [];
  userModules     : string[] = [];
  isAdminChatbot              = false;
  loadingModules              = false;

  // ── Devices panel ─────────────────────────────────────────────
  devicesUser    : UUser | null = null;
  userDevices    : Device[] = [];
  loadingDevices = false;

  readonly typeLabels: Record<number, { label: string; color: string; icon: string }> = {
    1: { label: 'Électricité', color: '#f1c40f', icon: '⚡' },
    2: { label: 'Eau',         color: '#3498db', icon: '💧' },
    3: { label: 'Gaz',         color: '#e74c3c', icon: '🔥' },
    4: { label: 'Carburant',   color: '#e67e22', icon: '⛽' }
  };

  get groupedDevices(): { type: number; label: string; color: string; icon: string; devices: Device[] }[] {
    const map = new Map<number, Device[]>();
    for (const d of this.userDevices) {
      const t = d.type ?? 0;
      if (!map.has(t)) map.set(t, []);
      map.get(t)!.push(d);
    }
    return Array.from(map.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([type, devices]) => ({
        type,
        devices,
        ...(this.typeLabels[type] ?? { label: `Type ${type}`, color: '#aaa', icon: '📡' })
      }));
  }

  private destroy$      = new Subject<void>();
  private searchSubject = new Subject<string>();

  get isSuperAdmin(): boolean { return this.auth.getCurrentRole() === 'SUPER_ADMIN'; }

  constructor(
    private svc         : UserService,
    private rolesSvc    : RolesService,
    private employeesSvc: EmployeesService,
    private deviceSvc   : DeviceService,
    private fb          : FormBuilder,
    private auth        : AuthService
  ) {}

  // ── Lifecycle ─────────────────────────────────────────────────
  ngOnInit(): void {
    this.buildForm();
    this.searchSubject
      .pipe(debounceTime(350), distinctUntilChanged(), takeUntil(this.destroy$))
      .subscribe(() => { this.page = 0; this.load(); });
    this.load();
    this.rolesSvc.getRoles().pipe(takeUntil(this.destroy$)).subscribe({
      next : r   => { this.roles = r; },
      error: err => { console.error('Erreur chargement rôles:', err); }
    });
    this.employeesSvc.getAvailableModules().pipe(takeUntil(this.destroy$)).subscribe({
      next : m   => { this.availableModules = m; },
      error: ()  => {}
    });
  }

  ngOnDestroy(): void { this.destroy$.next(); this.destroy$.complete(); clearTimeout(this.successTimer); }

  private showSuccess(msg: string): void {
    this.successMsg = msg;
    clearTimeout(this.successTimer);
    this.successTimer = setTimeout(() => this.successMsg = '', 3500);
  }

  // ── Form ──────────────────────────────────────────────────────
  private buildForm(): void {
    this.form = this.fb.group({
      login:          ['', Validators.required],
      pwd:            [''],
      loginPere:      [''],
      pwdExpDate:     [''],
      gmtPlus:        [0],
      isAdvisor:      [0],
      roleId:         [null],
      phone:          [''],
      loginFb:        [''],
      idFb:           [''],
      idFbMsg:        [''],
      failedAttempts: [0],
      blockedUntil:   ['']
    });
  }

  // ── Load ──────────────────────────────────────────────────────
  load(): void {
    this.loading  = true;
    this.errorMsg = '';
    const adv = this.filterAdvisor !== '' ? +this.filterAdvisor : undefined;
    this.svc.list(this.page, this.size,
        this.searchQuery || undefined,
        this.filterBlocked || undefined,
        adv)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: res => { this.users = res.data; this.total = res.total; this.loading = false; },
        error: () => { this.errorMsg = 'Erreur lors du chargement.'; this.loading = false; }
      });
  }

  // ── Filters ───────────────────────────────────────────────────
  onSearch(v: string): void  { this.searchQuery = v; this.searchSubject.next(v); }
  clearSearch(): void         { this.searchQuery = ''; this.page = 0; this.load(); }
  onFilterAdvisor(): void     { this.page = 0; this.load(); }
  onFilterBlocked(): void     { this.page = 0; this.load(); }

  // ── Sort ──────────────────────────────────────────────────────
  sort(col: string): void {
    this.sortDir = this.sortCol === col && this.sortDir === 'asc' ? 'desc' : 'asc';
    this.sortCol = col;
    this.users.sort((a: any, b: any) => {
      const va = a[col], vb = b[col];
      if (va == null) return 1; if (vb == null) return -1;
      return (va > vb ? 1 : va < vb ? -1 : 0) * (this.sortDir === 'asc' ? 1 : -1);
    });
  }

  sortIcon(col: string): string {
    if (this.sortCol !== col) return '↕';
    return this.sortDir === 'asc' ? '↑' : '↓';
  }

  goPage(p: number): void {
    if (p < 0 || p >= this.totalPages) return;
    this.page = p; this.load();
  }

  // ── Helpers ───────────────────────────────────────────────────
  isBlocked(u: UUser): boolean {
    return !!u.blockedUntil && new Date(u.blockedUntil) > new Date();
  }

  formatDate(d: string | null): string {
    if (!d) return '—';
    return new Date(d).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
  }

  trackByLogin(_: number, u: UUser): string { return u.login; }

  isInvalid(field: string): boolean {
    const c = this.form.get(field);
    return !!(c && c.invalid && c.touched);
  }

  // ── Modal ─────────────────────────────────────────────────────
  openCreate(): void {
    this.form.enable();
    this.form.reset({ gmtPlus: 0, isAdvisor: 0, failedAttempts: 0 });
    this.selectedUser   = null;
    this.showPwd        = false;
    this.userModules    = [];
    this.isAdminChatbot = false;
    this.modalMode      = 'create';
    this.errorMsg       = '';
  }

  openEdit(u: UUser): void {
    this.form.enable();
    this.selectedUser = u;
    this.form.patchValue({
      ...u,
      pwd:          '',
      pwdExpDate:   u.pwdExpDate   ? u.pwdExpDate.substring(0, 10)  : '',
      blockedUntil: u.blockedUntil ? u.blockedUntil.substring(0, 16) : '',
      roleId:       u.roleId ?? null
    });
    this.form.get('login')?.disable();
    this.showPwd        = false;
    this.userModules    = [];
    this.isAdminChatbot = false;
    this.loadingModules = true;
    this.modalMode      = 'edit';
    this.errorMsg       = '';
    this.employeesSvc.getEmployee(u.login).pipe(takeUntil(this.destroy$)).subscribe({
      next : emp => { this.userModules = emp.allowed_modules; this.isAdminChatbot = emp.is_admin; this.loadingModules = false; },
      error: ()  => { this.loadingModules = false; }
    });
  }

  openView(u: UUser): void {
    this.selectedUser   = u;
    this.userModules    = [];
    this.isAdminChatbot = false;
    this.modalMode      = 'view';
    this.employeesSvc.getEmployee(u.login).pipe(takeUntil(this.destroy$)).subscribe({
      next : emp => { this.userModules = emp.allowed_modules; this.isAdminChatbot = emp.is_admin; },
      error: ()  => {}
    });
  }

  openDelete(u: UUser): void { this.selectedUser = u; this.modalMode = 'delete'; }

  openDevices(u: UUser): void {
    this.devicesUser    = u;
    this.userDevices    = [];
    this.loadingDevices = true;
    this.deviceSvc.listByUser(u.login).pipe(takeUntil(this.destroy$)).subscribe({
      next : devices => { this.userDevices = devices; this.loadingDevices = false; },
      error: ()      => { this.loadingDevices = false; }
    });
  }

  closeDevices(): void { this.devicesUser = null; this.userDevices = []; }

  closeModal(): void {
    this.modalMode      = null;
    this.selectedUser   = null;
    this.errorMsg       = '';
    this.userModules    = [];
    this.isAdminChatbot = false;
    this.form.enable();
  }

  // ── Chatbot module helpers ─────────────────────────────────────
  hasModule(m: string): boolean { return this.userModules.includes(m); }

  toggleModule(m: string): void {
    this.userModules = this.hasModule(m)
      ? this.userModules.filter(x => x !== m)
      : [...this.userModules, m];
  }

  private saveModules(login: string): void {
    this.employeesSvc.saveModules(login, login, this.userModules, this.isAdminChatbot)
      .pipe(takeUntil(this.destroy$)).subscribe();
  }

  // ── CRUD ──────────────────────────────────────────────────────
  save(): void {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.saving   = true;
    this.errorMsg = '';
    const raw     = this.form.getRawValue();

    // pwdExpDate : le form retourne 'YYYY-MM-DD', Jackson/LocalDate l'accepte directement
    const dto: UUser = {
      login:            raw.login,
      pwd:              raw.pwd || null,
      loginPere:        raw.loginPere   || null,
      pwdExpDate:       raw.pwdExpDate  || null,
      gmtPlus:          raw.gmtPlus     != null ? +raw.gmtPlus : null,
      isAdvisor:        +raw.isAdvisor,
      roleId:           raw.roleId      != null ? +raw.roleId : null,
      phone:            raw.phone       || null,
      loginFb:          raw.loginFb     || null,
      idFb:             raw.idFb        || null,
      idFbMsg:          raw.idFbMsg     || null,
      failedAttempts:   raw.failedAttempts != null ? +raw.failedAttempts : 0,
      blockedUntil:     raw.blockedUntil || null,
      resetToken:       null,
      resetTokenExpiry: null
    };

    const obs = this.modalMode === 'create'
      ? this.svc.create(dto)
      : this.svc.update(this.selectedUser!.login, dto);

    obs.pipe(takeUntil(this.destroy$)).subscribe({
      next: (saved) => {
        this.saving = false;
        const login = saved.login ?? this.form.getRawValue().login;
        this.saveModules(login);
        this.closeModal();
        this.showSuccess(this.modalMode === 'create' ? 'Utilisateur créé avec succès.' : 'Utilisateur modifié avec succès.');
        this.load();
      },
      error: (err) => {
        this.saving   = false;
        this.errorMsg = err.status === 409
          ? 'Ce login existe déjà.'
          : (err?.error?.message ?? 'Erreur lors de la sauvegarde.');
      }
    });
  }

  confirmDelete(): void {
    if (!this.selectedUser) return;
    this.saving = true;
    this.svc.delete(this.selectedUser.login)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: () => { this.saving = false; this.closeModal(); this.showSuccess('Utilisateur supprimé.'); this.load(); },
        error: (err) => { this.saving = false; this.errorMsg = err?.error?.message ?? 'Erreur lors de la suppression.'; }
      });
  }

  resetAttempts(login: string): void {
    this.resetting = login;
    this.svc.resetAttempts(login)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: () => { this.resetting = ''; this.load(); },
        error: () => { this.resetting = ''; }
      });
  }
}