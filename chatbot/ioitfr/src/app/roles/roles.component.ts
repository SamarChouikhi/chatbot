import { Component, OnInit, OnDestroy } from '@angular/core';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { RolesService, Role, Permission } from '../services/roles.service';
import { AuthService } from '../services/auth.service';

const PERMISSION_LABELS: Record<string, string> = {
  VIEW_DASHBOARD:   'Voir le tableau de bord',
  VIEW_ENERGY_DATA: 'Voir données énergie',
  VIEW_WATER_DATA:  'Voir données eau',
  VIEW_GAS_DATA:    'Voir données gaz',
  VIEW_REPORTS:     'Voir les rapports',
  GENERATE_REPORTS: 'Générer des rapports',
  MANAGE_ALERTS:    'Gérer les alertes',
  VIEW_ALERTS:      'Voir les alertes',
  MANAGE_DEVICES:   'Gérer les appareils',
  VIEW_DEVICES:     'Voir les appareils',
  MANAGE_USERS:     'Gérer les utilisateurs',
  VIEW_USERS:       'Voir les utilisateurs',
  MANAGE_SPACES:    'Gérer les espaces',
  VIEW_SPACES:      'Voir les espaces',
  USE_CHATBOT:      'Utiliser le chatbot',
  MANAGE_ROLES:     'Gérer les rôles',
  EXPORT_DATA:      'Exporter les données',
};

@Component({
  selector: 'app-roles',
  templateUrl: './roles.component.html',
  styleUrls: ['./roles.component.scss']
})
export class RolesComponent implements OnInit, OnDestroy {

  // Data
  roles: Role[] = [];
  allPermissions: Permission[] = [];
  selectedRole: Role | null = null;
  checkedIds = new Set<number>();

  // View toggle
  activeView: 'roles' | 'permissions' = 'roles';

  // Global state
  loading    = false;
  saving     = false;
  errorMsg   = '';
  successMsg = '';

  // Role form
  showRoleForm  = false;
  editingRole: Role | null = null;
  roleFormName  = '';
  roleFormBusy  = false;

  // Permission form
  showPermForm  = false;
  editingPerm: Permission | null = null;
  permFormName  = '';
  permFormBusy  = false;

  // Delete confirm
  deleteTarget: { type: 'role' | 'permission'; id: number; name: string } | null = null;
  deleteBusy = false;

  private destroy$      = new Subject<void>();
  private successTimer: any;

  constructor(private svc: RolesService, private auth: AuthService) {}

  ngOnInit(): void { this.loadAll(); }
  ngOnDestroy(): void { this.destroy$.next(); this.destroy$.complete(); clearTimeout(this.successTimer); }

  private showSuccess(msg: string): void {
    this.successMsg = msg;
    clearTimeout(this.successTimer);
    this.successTimer = setTimeout(() => this.successMsg = '', 3500);
  }

  private loadAll(): void {
    this.loading = true;
    this.svc.getRoles().pipe(takeUntil(this.destroy$)).subscribe({
      next:  r  => { this.roles = r; this.loading = false; },
      error: () => { this.errorMsg = 'Erreur lors du chargement des rôles.'; this.loading = false; }
    });
    this.svc.getPermissions().pipe(takeUntil(this.destroy$)).subscribe({
      next: p => this.allPermissions = p
    });
  }

  // ── Role selection & permissions save ────────────────────────

  selectRole(role: Role): void {
    this.selectedRole = role;
    this.checkedIds   = new Set(role.permissions.map(p => p.id));
    this.successMsg   = '';
    this.errorMsg     = '';
  }

  togglePermission(id: number): void {
    this.checkedIds.has(id) ? this.checkedIds.delete(id) : this.checkedIds.add(id);
  }

  isChecked(id: number): boolean { return this.checkedIds.has(id); }

  save(): void {
    if (!this.selectedRole) return;
    this.saving    = true;
    this.errorMsg  = '';
    this.successMsg = '';
    this.svc.updatePermissions(this.selectedRole.id, [...this.checkedIds])
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: updated => {
          const idx = this.roles.findIndex(r => r.id === updated.id);
          if (idx >= 0) this.roles[idx] = updated;
          this.selectedRole = updated;
          this.saving = false;
          this.showSuccess('Permissions sauvegardées avec succès.');
          if (this.auth.getCurrentRole() === updated.userName) {
            this.auth.refreshToken().pipe(takeUntil(this.destroy$)).subscribe();
          }
        },
        error: () => { this.saving = false; this.errorMsg = 'Erreur lors de la sauvegarde.'; }
      });
  }

  // ── Role CRUD ────────────────────────────────────────────────

  openCreateRole(): void {
    this.editingRole  = null;
    this.roleFormName = '';
    this.showRoleForm = true;
  }

  openEditRole(role: Role, event: Event): void {
    event.stopPropagation();
    this.editingRole  = role;
    this.roleFormName = role.userName;
    this.showRoleForm = true;
  }

  closeRoleForm(): void { this.showRoleForm = false; }

  saveRole(): void {
    const name = this.roleFormName.trim().toUpperCase();
    if (!name) return;
    this.roleFormBusy = true;
    const obs = this.editingRole
      ? this.svc.updateRole(this.editingRole.id, name)
      : this.svc.createRole(name);
    obs.pipe(takeUntil(this.destroy$)).subscribe({
      next: role => {
        if (this.editingRole) {
          const idx = this.roles.findIndex(r => r.id === role.id);
          if (idx >= 0) this.roles[idx] = role;
          if (this.selectedRole?.id === role.id) this.selectedRole = role;
          this.showSuccess('Rôle modifié avec succès.');
        } else {
          this.roles.push(role);
          this.showSuccess('Rôle créé avec succès.');
        }
        this.roleFormBusy = false;
        this.showRoleForm = false;
      },
      error: err => {
        this.roleFormBusy = false;
        this.errorMsg = err?.error?.message ?? 'Erreur lors de la sauvegarde du rôle.';
      }
    });
  }

  confirmDeleteRole(role: Role, event: Event): void {
    event.stopPropagation();
    this.deleteTarget = { type: 'role', id: role.id, name: role.userName };
  }

  // ── Permission CRUD ──────────────────────────────────────────

  openCreatePerm(): void {
    this.editingPerm  = null;
    this.permFormName = '';
    this.showPermForm = true;
  }

  openEditPerm(perm: Permission): void {
    this.editingPerm  = perm;
    this.permFormName = perm.permission;
    this.showPermForm = true;
  }

  closePermForm(): void { this.showPermForm = false; }

  savePerm(): void {
    const name = this.permFormName.trim().toUpperCase();
    if (!name) return;
    this.permFormBusy = true;
    const obs = this.editingPerm
      ? this.svc.updatePermission(this.editingPerm.id, name)
      : this.svc.createPermission(name);
    obs.pipe(takeUntil(this.destroy$)).subscribe({
      next: perm => {
        if (this.editingPerm) {
          const idx = this.allPermissions.findIndex(p => p.id === perm.id);
          if (idx >= 0) this.allPermissions[idx] = perm;
          this.showSuccess('Permission modifiée avec succès.');
        } else {
          this.allPermissions.push(perm);
          this.showSuccess('Permission créée avec succès.');
        }
        this.permFormBusy = false;
        this.showPermForm = false;
      },
      error: err => {
        this.permFormBusy = false;
        this.errorMsg = err?.error?.message ?? 'Erreur lors de la sauvegarde de la permission.';
      }
    });
  }

  confirmDeletePerm(perm: Permission): void {
    this.deleteTarget = { type: 'permission', id: perm.id, name: perm.permission };
  }

  // ── Delete confirm ───────────────────────────────────────────

  cancelDelete(): void { this.deleteTarget = null; }

  confirmDelete(): void {
    if (!this.deleteTarget) return;
    this.deleteBusy = true;
    const target = this.deleteTarget;
    const obs = target.type === 'role'
      ? this.svc.deleteRole(target.id)
      : this.svc.deletePermission(target.id);
    obs.pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        if (target.type === 'role') {
          this.roles = this.roles.filter(r => r.id !== target.id);
          if (this.selectedRole?.id === target.id) this.selectedRole = null;
          this.showSuccess('Rôle supprimé.');
        } else {
          this.allPermissions = this.allPermissions.filter(p => p.id !== target.id);
          this.checkedIds.delete(target.id);
          this.showSuccess('Permission supprimée.');
        }
        this.deleteBusy  = false;
        this.deleteTarget = null;
      },
      error: err => {
        this.deleteBusy   = false;
        this.deleteTarget = null;
        this.errorMsg = err?.error?.message ?? 'Erreur lors de la suppression.';
      }
    });
  }

  // ── Helpers ──────────────────────────────────────────────────

  label(permission: string): string {
    return PERMISSION_LABELS[permission] ?? permission;
  }

  roleColor(name: string): string {
    const map: Record<string, string> = {
      SUPER_ADMIN:    '#e74c3c',
      ENERGY_MANAGER: '#0ea5e9',
      ADVISOR:        '#06b6d4',
      TECHNICIAN:     '#10b981',
      EMPLOYEE:       '#0d9488',
      INTERN:         '#64748b',
    };
    return map[name] ?? '#22c55e';
  }

  roleIcon(name: string): string {
    const map: Record<string, string> = {
      SUPER_ADMIN:    'SA',
      ENERGY_MANAGER: 'EM',
      ADVISOR:        'AD',
      TECHNICIAN:     'TC',
      EMPLOYEE:       'EM',
      INTERN:         'IN',
    };
    return map[name] ?? name.substring(0, 2);
  }
}
