import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface Recommendation {
  id                   : number;
  domain               : string;
  device_id            : string | null;
  rec_type             : string;
  priority             : 'critical' | 'high' | 'medium' | 'low';
  title                : string;
  description          : string;
  action               : string;
  reasoning            : string | null;
  estimated_saving_tnd : number | null;
  deviation_pct        : number | null;
  status               : 'pending' | 'accepted' | 'dismissed' | 'done';
  generated_at         : string;
  expires_at           : string;
  acted_at             : string | null;
  measured_saving_tnd  : number | null;
}

export interface RecoSummary {
  domain              : string;
  total               : number;
  critical_count      : number;
  high_count          : number;
  medium_count        : number;
  total_potential_tnd : number;
  total_realized_tnd  : number;
}

@Injectable({ providedIn: 'root' })
export class RecommendationsService {
  private readonly base = `${environment.ariaApiUrl}/recommendations`;

  constructor(private http: HttpClient) {}

  getByDomain(domain: string, status = 'pending,accepted', limit = 10, userRole = 'gestionnaire', userId?: string, lang?: string): Observable<Recommendation[]> {
    let params = new HttpParams()
      .set('domain', domain)
      .set('status', status)
      .set('limit', limit)
      .set('user_role', userRole);
    if (userId) params = params.set('user_id', userId);
    if (lang) params = params.set('lang', lang);
    return this.http.get<Recommendation[]>(this.base, { params })
      .pipe(catchError(() => of([])));
  }

  updateStatus(id: number, status: 'accepted' | 'dismissed' | 'done', userId?: string, lang?: string): Observable<Recommendation> {
    let params = new HttpParams();
    if (lang) params = params.set('lang', lang);
    return this.http.patch<Recommendation>(`${this.base}/${id}`, { status, user_id: userId ?? null }, { params });
  }

  getSummary(): Observable<RecoSummary[]> {
    return this.http.get<RecoSummary[]>(`${this.base}/summary`)
      .pipe(catchError(() => of([])));
  }

  refresh(userRole: string = 'gestionnaire', domain?: string): Observable<any> {
    const body: any = { user_role: userRole };
    if (domain) body['domain'] = domain;
    return this.http.post(`${this.base}/refresh`, body);
  }
}
