import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface Alert {
  date: string;
  idDevice: number;
  type: string;
  valeur: number | null;
  diff: number | null;
  valMin: number | null;
  valMax: number | null;
  tempsInfraction: number | null;
  message: string | null;
  messageEn: string | null;
  recommendationEn: string | null;
  recommendationFr: string | null;
  from: string | null;
}

export interface AlertPage {
  data: Alert[];
  total: number;
  page: number;
  size: number;
}

@Injectable({ providedIn: 'root' })
export class AlertService {

  private base = `${environment.apiUrl}/api/alerts`;

  constructor(private http: HttpClient) {}

  list(page = 0, size = 10, type?: string, idDevice?: number): Observable<AlertPage> {
    let params = new HttpParams()
      .set('page', page)
      .set('size', size);
    if (type)     params = params.set('type', type);
    if (idDevice) params = params.set('idDevice', idDevice);
    return this.http.get<AlertPage>(this.base, { params });
  }

  getTypes(): Observable<string[]> {
    return this.http.get<string[]>(`${this.base}/types`);
  }

  getOne(date: string, idDevice: number, type: string): Observable<Alert> {
    return this.http.get<Alert>(`${this.base}/${encodeURIComponent(date)}/${idDevice}/${encodeURIComponent(type)}`);
  }

  create(alert: Alert): Observable<Alert> {
    return this.http.post<Alert>(this.base, alert);
  }

  update(date: string, idDevice: number, type: string, alert: Alert): Observable<Alert> {
    return this.http.put<Alert>(`${this.base}/${encodeURIComponent(date)}/${idDevice}/${encodeURIComponent(type)}`, alert);
  }

  delete(date: string, idDevice: number, type: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${encodeURIComponent(date)}/${idDevice}/${encodeURIComponent(type)}`);
  }
}