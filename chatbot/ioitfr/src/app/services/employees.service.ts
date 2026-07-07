import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, switchMap, throwError } from 'rxjs';
import { environment } from '../../environments/environment';

export interface EmployeeModules {
  id?            : number;
  user_id        : string;
  name           : string;
  allowed_modules: string[];
  is_admin       : boolean;
}

@Injectable({ providedIn: 'root' })
export class EmployeesService {

  private readonly BASE = `${environment.ariaApiUrl}/employees`;

  constructor(private http: HttpClient) {}

  getAvailableModules(): Observable<string[]> {
    return this.http.get<string[]>(`${this.BASE}/modules`);
  }

  getEmployee(userId: string): Observable<EmployeeModules> {
    return this.http.get<EmployeeModules>(`${this.BASE}/${userId}`);
  }

  /** Creates or updates the employee's chatbot modules. */
  saveModules(userId: string, name: string, modules: string[], isAdmin = false): Observable<EmployeeModules> {
    const updateBody = { name, allowed_modules: modules, is_admin: isAdmin };
    return this.http.put<EmployeeModules>(`${this.BASE}/${userId}`, updateBody).pipe(
      catchError(err => {
        if (err.status === 404) {
          return this.http.post<EmployeeModules>(this.BASE, {
            user_id: userId, name, allowed_modules: modules, is_admin: isAdmin
          });
        }
        return throwError(() => err);
      })
    );
  }
}
