import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface Permission {
  id: number;
  permission: string;
}

export interface Role {
  id: number;
  userName: string;
  permissions: Permission[];
}

@Injectable({ providedIn: 'root' })
export class RolesService {

  private base = `${environment.apiUrl}/api/roles`;

  constructor(private http: HttpClient) {}

  // ── Roles ────────────────────────────────────────────────────

  getRoles(): Observable<Role[]> {
    return this.http.get<Role[]>(this.base);
  }

  getRole(id: number): Observable<Role> {
    return this.http.get<Role>(`${this.base}/${id}`);
  }

  createRole(name: string): Observable<Role> {
    return this.http.post<Role>(this.base, { userName: name });
  }

  updateRole(id: number, name: string): Observable<Role> {
    return this.http.put<Role>(`${this.base}/${id}`, { userName: name });
  }

  deleteRole(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }

  // ── Permissions ──────────────────────────────────────────────

  getPermissions(): Observable<Permission[]> {
    return this.http.get<Permission[]>(`${this.base}/permissions`);
  }

  createPermission(name: string): Observable<Permission> {
    return this.http.post<Permission>(`${this.base}/permissions`, { permission: name });
  }

  updatePermission(id: number, name: string): Observable<Permission> {
    return this.http.put<Permission>(`${this.base}/permissions/${id}`, { permission: name });
  }

  deletePermission(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/permissions/${id}`);
  }

  // ── Role-Permission assignment ────────────────────────────────

  updatePermissions(roleId: number, permissionIds: number[]): Observable<Role> {
    return this.http.put<Role>(`${this.base}/${roleId}/permissions`, { permissionIds });
  }
}
