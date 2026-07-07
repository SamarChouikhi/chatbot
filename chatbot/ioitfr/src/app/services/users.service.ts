import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface UUser {
  login: string;
  pwd?: string | null;
  loginPere: string | null;
  pwdExpDate: string | null;
  gmtPlus: number | null;
  isAdvisor: number | null;
  loginFb: string | null;
  idFb: string | null;
  idFbMsg: string | null;
  resetToken: string | null;
  resetTokenExpiry: string | null;
  phone: string | null;
  failedAttempts: number | null;
  blockedUntil: string | null;
  roleId?: number | null;
  roleName?: string | null;
}

export interface UserPage {
  data: UUser[];
  total: number;
  page: number;
  size: number;
}

@Injectable({ providedIn: 'root' })
export class UserService {

  private base = `${environment.apiUrl}/api/users`;

  constructor(private http: HttpClient) {}

  list(page = 0, size = 10, search?: string, blocked?: boolean, isAdvisor?: number): Observable<UserPage> {
    let params = new HttpParams().set('page', page).set('size', size);
    if (search)                          params = params.set('search', search);
    if (blocked !== undefined)           params = params.set('blocked', blocked);
    if (isAdvisor !== undefined)         params = params.set('isAdvisor', isAdvisor);
    return this.http.get<UserPage>(this.base, { params });
  }

  getOne(login: string): Observable<UUser> {
    return this.http.get<UUser>(`${this.base}/${login}`);
  }

  create(user: UUser): Observable<UUser> {
    return this.http.post<UUser>(this.base, user);
  }

  update(login: string, user: UUser): Observable<UUser> {
    return this.http.put<UUser>(`${this.base}/${login}`, user);
  }

  delete(login: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${login}`);
  }

  resetAttempts(login: string): Observable<any> {
    return this.http.put(`${this.base}/${login}/reset-attempts`, {});
  }

  assignRole(login: string, roleId: number | null): Observable<UUser> {
    return this.http.put<UUser>(`${this.base}/${login}/role`, { roleId });
  }
}