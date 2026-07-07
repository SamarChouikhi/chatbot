import { Component, OnInit, OnDestroy } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { TranslateService } from '@ngx-translate/core';
import { DeviceService, Device } from '../services/device.service';
import { AuthService } from '../services/auth.service';

type ModalMode = 'create' | 'edit' | 'view' | null;

@Component({
  selector: 'app-devices',
  templateUrl: './devices.component.html',
  styleUrls: ['./devices.component.scss']
})
export class DevicesComponent implements OnInit, OnDestroy {

  // ── Data ─────────────────────────────────────────────────────
  devices: Device[] = [];
  filteredDevices: Device[] = [];
  pagedDevices: Device[] = [];
  total = 0;

  // ── Pagination ───────────────────────────────────────────────
  currentPage = 1;
  pageSize = 10;
  get totalPages(): number { return Math.ceil(this.filteredDevices.length / this.pageSize); }
  get pageNumbers(): number[] { return Array.from({ length: this.totalPages }, (_, i) => i + 1); }

  // ── Filters ──────────────────────────────────────────────────
  searchQuery = '';
  filterType  = '';
  filterGeneral = '';

  // ── Sort ─────────────────────────────────────────────────────
  sortField = 'id';
  sortDir: 'asc' | 'desc' = 'asc';

  // ── State ────────────────────────────────────────────────────
  isLoading  = false;
  isSaving   = false;
  errorMsg   = '';
  successMsg = '';
  private successTimer: any;

  // ── Modal ────────────────────────────────────────────────────
  modalMode: ModalMode = null;
  selectedDevice: Device | null = null;
  deviceToDelete: Device | null = null;
  showDeleteConfirm = false;
  deviceForm!: FormGroup;

  private destroy$ = new Subject<void>();

  readonly typeKeys: Record<number, string> = {
    1: 'DEVICES_PAGE.TYPE_ELEC', 2: 'DEVICES_PAGE.TYPE_WATER',
    3: 'DEVICES_PAGE.TYPE_GAS',  4: 'DEVICES_PAGE.TYPE_FUEL'
  };

  constructor(
    private svc      : DeviceService,
    private authSvc  : AuthService,
    private fb       : FormBuilder,
    private translate: TranslateService
  ) {}

  // ── Lifecycle ─────────────────────────────────────────────────
  ngOnInit(): void {
    this.buildForm();
    this.load();
  }

  ngOnDestroy(): void { this.destroy$.next(); this.destroy$.complete(); clearTimeout(this.successTimer); }

  private showSuccess(msg: string): void {
    this.successMsg = msg;
    clearTimeout(this.successTimer);
    this.successTimer = setTimeout(() => this.successMsg = '', 3500);
  }

  // ── Form ──────────────────────────────────────────────────────
  private buildForm(): void {
    this.deviceForm = this.fb.group({
      id:               [null, Validators.required],
      adresse:          [null, Validators.required],
      nom:              ['', Validators.required],
      description:      [''],
      type:             ['', Validators.required],
      id_espace:        [null, Validators.required],
      id_ls:            [null],
      max_uptime:       [null],
      last_saved_index: [null],
      is_general_meter: [0],
      geometry:         [''],
      login:            [null]
    });
  }

  // ── Load ──────────────────────────────────────────────────────
  load(): void {
    this.isLoading = true;
    this.errorMsg  = '';

    const role  = this.authSvc.getCurrentRole();
    const login = this.authSvc.getCurrentLogin();
    const isEmployee = role === 'EMPLOYEE';

    if (isEmployee) {
      this.svc.listByUser(login).pipe(takeUntil(this.destroy$)).subscribe({
        next: data => {
          this.devices = data;
          this.applyFilters();
          this.isLoading = false;
        },
        error: () => { this.errorMsg = 'Erreur lors du chargement des dispositifs.'; this.isLoading = false; }
      });
      return;
    }

    this.svc.list(0, 9999).pipe(takeUntil(this.destroy$)).subscribe({
      next: res => {
        this.devices = res.data;
        this.applyFilters();
        this.isLoading = false;
      },
      error: () => {
        this.errorMsg  = 'Erreur lors du chargement des dispositifs.';
        this.isLoading = false;
      }
    });
  }

  // ── Filters & Sort ────────────────────────────────────────────
  applyFilters(): void {
    let data = [...this.devices];

    if (this.searchQuery.trim()) {
      const q = this.searchQuery.toLowerCase();
      data = data.filter(d =>
        (d.nom || '').toLowerCase().includes(q) ||
        (d.description || '').toLowerCase().includes(q)
      );
    }

    if (this.filterType) {
      data = data.filter(d => String(d.type) === this.filterType);
    }

    if (this.filterGeneral !== '') {
      data = data.filter(d => String(d.is_general_meter) === this.filterGeneral);
    }

    // Sort
    data.sort((a: any, b: any) => {
      const va = a[this.sortField], vb = b[this.sortField];
      if (va == null) return 1;
      if (vb == null) return -1;
      return (va > vb ? 1 : va < vb ? -1 : 0) * (this.sortDir === 'asc' ? 1 : -1);
    });

    this.filteredDevices = data;
    this.currentPage = 1;
    this.updatePage();
  }

  sort(field: string): void {
    this.sortDir = this.sortField === field && this.sortDir === 'asc' ? 'desc' : 'asc';
    this.sortField = field;
    this.applyFilters();
  }

  clearSearch(): void {
    this.searchQuery = '';
    this.applyFilters();
  }

  updatePage(): void {
    const start = (this.currentPage - 1) * this.pageSize;
    this.pagedDevices = this.filteredDevices.slice(start, start + this.pageSize);
  }

  goToPage(p: number): void {
    if (p < 1 || p > this.totalPages) return;
    this.currentPage = p;
    this.updatePage();
  }

  min(a: number, b: number): number { return Math.min(a, b); }

  // ── Modal ─────────────────────────────────────────────────────
  openModal(mode: ModalMode, device?: Device): void {
    this.modalMode     = mode;
    this.selectedDevice = device || null;
    this.errorMsg      = '';

    if (mode === 'create') {
      this.deviceForm.reset({ is_general_meter: 0, login: this.authSvc.getCurrentLogin() });
      this.deviceForm.get('id')?.enable();
      this.deviceForm.get('adresse')?.enable();
      this.deviceForm.get('login')?.disable();
    } else if (mode === 'edit' && device) {
      this.deviceForm.patchValue({ ...device });
      this.deviceForm.get('id')?.disable();
      this.deviceForm.get('adresse')?.disable();
    } else if (mode === 'view' && device) {
      this.deviceForm.patchValue({ ...device });
      this.deviceForm.disable();
    }
  }

  closeModal(): void {
    this.modalMode      = null;
    this.selectedDevice = null;
    this.errorMsg       = '';
    this.deviceForm.enable();
  }

  closeModalOnBackdrop(event: MouseEvent): void {
    this.closeModal();
  }

  isInvalid(field: string): boolean {
    const c = this.deviceForm.get(field);
    return !!(c && c.invalid && c.touched);
  }

  // ── CRUD ──────────────────────────────────────────────────────
  saveDevice(): void {
    if (this.deviceForm.invalid) { this.deviceForm.markAllAsTouched(); return; }
    this.isSaving = true;
    this.errorMsg = '';

    const raw = this.deviceForm.getRawValue();
    const device: Device = {
      id:               +raw.id,
      adresse:          +raw.adresse,
      nom:              raw.nom,
      description:      raw.description || null,
      type:             raw.type ? +raw.type : null,
      id_espace:        raw.id_espace ? +raw.id_espace : null,
      id_ls:            raw.id_ls ? +raw.id_ls : null,
      max_uptime:       raw.max_uptime ? +raw.max_uptime : null,
      last_saved_index: raw.last_saved_index != null ? +raw.last_saved_index : null,
      is_general_meter: +raw.is_general_meter,
      geometry:         raw.geometry || null,
      login:            raw.login || null
    };

    const obs = this.modalMode === 'create'
      ? this.svc.create(device)
      : this.svc.update(this.selectedDevice!.id, this.selectedDevice!.adresse, device);

    obs.pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.isSaving = false;
        this.closeModal();
        this.showSuccess(this.modalMode === 'create' ? 'Dispositif créé avec succès.' : 'Dispositif modifié avec succès.');
        this.load();
      },
      error: (err) => {
        this.isSaving = false;
        this.errorMsg = err.status === 409 ? 'Ce dispositif existe déjà.' : (err?.error?.message ?? 'Erreur lors de la sauvegarde.');
      }
    });
  }

  confirmDelete(device: Device): void {
    this.deviceToDelete   = device;
    this.showDeleteConfirm = true;
  }

  deleteDevice(): void {
    if (!this.deviceToDelete) return;
    this.isSaving = true;
    this.svc.delete(this.deviceToDelete.id, this.deviceToDelete.adresse)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: () => { this.isSaving = false; this.showDeleteConfirm = false; this.deviceToDelete = null; this.showSuccess('Dispositif supprimé.'); this.load(); },
        error: (err) => { this.isSaving = false; this.errorMsg = err?.error?.message ?? 'Erreur lors de la suppression.'; }
      });
  }

  // ── Utils ─────────────────────────────────────────────────────
  getTypeLabel(type: number | null): string {
    return type != null ? this.translate.instant(this.typeKeys[type] ?? String(type)) : '—';
  }

  trackById(_: number, d: Device): number { return d.id; }
}