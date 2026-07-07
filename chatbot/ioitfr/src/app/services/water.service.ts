import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { environment } from '../../environments/environment';

// ══════════════════════════════════════════════════════════════════════════════
// INTERFACES — calquées sur les DTOs Quarkus WaterDto.java
// ══════════════════════════════════════════════════════════════════════════════

export interface RtWmDto {
  idDevice:     number;
  date:         string;
  wmIndex:      number;
  leak:         number;
  fraud:        number;
  batteryLevel: number;
  nAlert:       number;
  rssi:         number;
  snr:          number;
  status:       'OK' | 'LEAK' | 'FRAUD' | 'ALERT';
}

export interface ArchiveWmDto {
  idDevice:     number;
  date:         string;
  forwardFlow:  number;
  reverseFlow:  number;
  wmIndex:      number;
  leak:         number;
  fraud:        number;
  batteryLevel: number;
  rssi:         number;
  snr:          number;
}

export interface ArchiveWmHDto {
  idDevice:     number;
  date:         string;
  conso:        number;
  reverseConso: number;
  wmIndex:      number;
  batteryLevel: number;
}

export interface ArchiveWmJDto {
  idDevice:     number;
  date:         string;
  conso:        number;
  reverseConso: number;
  wmIndex:      number;
  batteryLevel: number;
}

export interface ArchiveWmMDto {
  idDevice:     number;
  date:         string;
  conso:        number;
  reverseConso: number;
  wmIndex:      number;
  batteryLevel: number;
}

export interface InitWmDto {
  idDevice:                   number;
  date:                       string;
  consoH:                     number;
  consoJ:                     number;
  consoM:                     number;
  reverseConsoH:              number;
  reverseConsoJ:              number;
  reverseConsoM:              number;
  infractionConsoH:           number;
  infractionConsoJ:           number;
  infractionConsoM:           number;
  alertState:                 number;
  highConsumptionCounter:     number;
  excessiveConsumptionCounter:number;
  lowConsumptionCounter:      number;
}

export interface WaterSummaryDto {
  idDevice:    number;
  lastUpdate:  string;
  totalConsoH: number;
  totalConsoJ: number;
  totalConsoM: number;
  totalConsoM3:number;
  alertCount:  number;
  leakCount:   number;
  fraudCount:  number;
  co2Kg:       number;
  costTnd:     number;
  trend:       string;
}

export interface WaterChartPointDto {
  label:   string;
  conso:   number;
  consoM3: number;
  co2:     number;
  cost:    number;
}

export interface WaterChartDto {
  points:      WaterChartPointDto[];
  totalConsoL: number;
  totalConsoM3:number;
  totalCo2:    number;
  totalCost:   number;
}

export interface WaterStatsDto {
  idDevice:             number;
  avgDailyConsoL:       number;
  maxDailyConsoL:       number;
  minDailyConsoL:       number;
  avgMonthlyConsoL:     number;
  daysWithLeak:         number;
  totalAlerts:          number;
  variationVsPrevMonth: number;
}

export interface WaterAlertDto {
  idDevice: number;
  date:     string;
  type:     'LEAK' | 'FRAUD' | 'HIGH_CONSO' | 'LOW_BATTERY';
  message:  string;
  severity: 'LOW' | 'HIGH' | 'CRITICAL';
}

export interface WaterComparisonDto {
  currentPeriodConso:  number;
  previousPeriodConso: number;
  variationPercent:    number;
  trend:               'UP' | 'DOWN' | 'STABLE';
}

// ══════════════════════════════════════════════════════════════════════════════

@Injectable({ providedIn: 'root' })
export class WaterService {

  private readonly base = `${environment.apiUrl}/api/water`;

  constructor(private http: HttpClient) {}

  // ── Helpers ──────────────────────────────────────────────────────────────

  private fmt(d: Date): string {
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}` +
           `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  private params(from?: Date, to?: Date, device?: number): HttpParams {
    let p = new HttpParams();
    if (from)   p = p.set('from',   this.fmt(from));
    if (to)     p = p.set('to',     this.fmt(to));
    if (device) p = p.set('device', device);
    return p;
  }

  // ── Temps réel ────────────────────────────────────────────────────────────

  getRealTimeAll(): Observable<RtWmDto[]> {
    return this.http.get<RtWmDto[]>(`${this.base}/realtime`).pipe(catchError(() => of([])));
  }

  getRealTime(idDevice: number): Observable<RtWmDto | null> {
    return this.http.get<RtWmDto>(`${this.base}/realtime/${idDevice}`).pipe(catchError(() => of(null)));
  }

  getRealTimeAlerts(): Observable<RtWmDto[]> {
    return this.http.get<RtWmDto[]>(`${this.base}/realtime/alerts`).pipe(catchError(() => of([])));
  }

  getRealTimeLeaks(): Observable<RtWmDto[]> {
    return this.http.get<RtWmDto[]>(`${this.base}/realtime/leaks`).pipe(catchError(() => of([])));
  }

  // ── Agrégats ─────────────────────────────────────────────────────────────

  getHourly(from: Date, to: Date, device?: number): Observable<ArchiveWmHDto[]> {
    return this.http.get<ArchiveWmHDto[]>(`${this.base}/hourly`,
      { params: this.params(from, to, device) }).pipe(catchError(() => of([])));
  }

  getDaily(from: Date, to: Date, device?: number): Observable<ArchiveWmJDto[]> {
    return this.http.get<ArchiveWmJDto[]>(`${this.base}/daily`,
      { params: this.params(from, to, device) }).pipe(catchError(() => of([])));
  }

  getMonthlyByDevice(idDevice: number): Observable<ArchiveWmMDto[]> {
    return this.http.get<ArchiveWmMDto[]>(`${this.base}/monthly/${idDevice}`).pipe(catchError(() => of([])));
  }

  getMonthly(from: Date, to: Date, device?: number): Observable<ArchiveWmMDto[]> {
    return this.http.get<ArchiveWmMDto[]>(`${this.base}/monthly`,
      { params: this.params(from, to, device) }).pipe(catchError(() => of([])));
  }

  // ── Résumé ────────────────────────────────────────────────────────────────

  getSummary(idDevice: number, from: Date, to: Date): Observable<WaterSummaryDto | null> {
    return this.http.get<WaterSummaryDto>(`${this.base}/summary/${idDevice}`,
      { params: this.params(from, to) }).pipe(catchError(() => of(null)));
  }

  getAllSummaries(from: Date, to: Date): Observable<WaterSummaryDto[]> {
    return this.http.get<WaterSummaryDto[]>(`${this.base}/summary`,
      { params: this.params(from, to) }).pipe(catchError(() => of([])));
  }

  // ── Charts ────────────────────────────────────────────────────────────────

  getHourlyChart(idDevice: number, from: Date, to: Date): Observable<WaterChartDto | null> {
    return this.http.get<WaterChartDto>(`${this.base}/chart/hourly/${idDevice}`,
      { params: this.params(from, to) }).pipe(catchError(() => of(null)));
  }

  getDailyChart(idDevice: number, from: Date, to: Date): Observable<WaterChartDto | null> {
    return this.http.get<WaterChartDto>(`${this.base}/chart/daily/${idDevice}`,
      { params: this.params(from, to) }).pipe(catchError(() => of(null)));
  }

  getMonthlyChart(idDevice: number, from: Date, to: Date): Observable<WaterChartDto | null> {
    return this.http.get<WaterChartDto>(`${this.base}/chart/monthly/${idDevice}`,
      { params: this.params(from, to) }).pipe(catchError(() => of(null)));
  }

  // ── Statistiques ─────────────────────────────────────────────────────────

  getStats(idDevice: number, from: Date, to: Date): Observable<WaterStatsDto | null> {
    return this.http.get<WaterStatsDto>(`${this.base}/stats/${idDevice}`,
      { params: this.params(from, to) }).pipe(catchError(() => of(null)));
  }

  getAllStats(from: Date, to: Date): Observable<WaterStatsDto[]> {
    return this.http.get<WaterStatsDto[]>(`${this.base}/stats`,
      { params: this.params(from, to) }).pipe(catchError(() => of([])));
  }

  // ── Alertes ───────────────────────────────────────────────────────────────

  getAlerts(): Observable<WaterAlertDto[]> {
    return this.http.get<WaterAlertDto[]>(`${this.base}/alerts`).pipe(catchError(() => of([])));
  }

  // ── Comparaison ───────────────────────────────────────────────────────────

  compare(idDevice: number, from: Date, to: Date): Observable<WaterComparisonDto | null> {
    return this.http.get<WaterComparisonDto>(`${this.base}/compare/${idDevice}`,
      { params: this.params(from, to) }).pipe(catchError(() => of(null)));
  }

  // ── Config ────────────────────────────────────────────────────────────────

  getConfig(idDevice: number): Observable<InitWmDto | null> {
    return this.http.get<InitWmDto>(`${this.base}/config/${idDevice}`).pipe(catchError(() => of(null)));
  }

  // ── Helpers périodes ─────────────────────────────────────────────────────

  getLastNDaysRange(n: number): { from: Date; to: Date } {
    const to   = new Date();
    const from = new Date();
    from.setDate(from.getDate() - n);
    return { from, to };
  }

  getCurrentMonthRange(): { from: Date; to: Date } {
    const now  = new Date();
    const from = new Date(now.getFullYear(), now.getMonth(), 1);
    return { from, to: now };
  }
}
