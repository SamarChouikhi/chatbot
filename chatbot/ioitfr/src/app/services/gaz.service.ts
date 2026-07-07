import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { environment } from '../../environments/environment';

// ══════════════════════════════════════════════════════════════════════════════
// INTERFACES — calquées exactement sur les DTOs Quarkus GazDto.java
// ══════════════════════════════════════════════════════════════════════════════

export interface RtGmDto {
  idDevice:       number;
  date:           string;
  index:          number;
  leak:           number;
  fraud:          number;
  batteryLevel:   number;
  nAlert:         number;
  minDebitPerMin: number;
  maxDebitPerMin: number;
  avgDebitPerMin: number;
  rssi:           number;
  snr:            number;
  status:         'OK' | 'LEAK' | 'FRAUD' | 'ALERT';
}

export interface ArchiveGmDto {
  idDevice:       number;
  date:           string;
  forwardFlow:    number;
  reverseFlow:    number;
  index:          number;
  leak:           number;
  fraud:          number;
  batteryLevel:   number;
  minDebitPerMin: number;
  maxDebitPerMin: number;
  avgDebitPerMin: number;
}

export interface ArchiveGmHDto {
  idDevice:       number;
  date:           string;
  conso:          number;
  reverseConso:   number;
  index:          number;
  avgDebitPerMin: number;
  minDebitPerMin: number;
  maxDebitPerMin: number;
}

export interface ArchiveGmJDto {
  idDevice:       number;
  date:           string;
  conso:          number;
  reverseConso:   number;
  index:          number;
  avgDebitPerMin: number;
  minDebitPerMin: number;
  maxDebitPerMin: number;
}

export interface ArchiveGmMDto {
  idDevice:       number;
  date:           string;
  conso:          number;
  reverseConso:   number;
  index:          number;
  avgDebitPerMin: number;
}

export interface InitGmDto {
  idDevice:                   number;
  date:                       string;
  consoH:                     number;
  consoJ:                     number;
  consoM:                     number;
  alertState:                 number;
  highConsumptionCounter:     number;
  excessiveConsumptionCounter:number;
  lowConsumptionCounter:      number;
  avgDebitPerMin:             number;
  minDebitPerMin:             number;
  maxDebitPerMin:             number;
}

export interface GazSummaryDto {
  idDevice:    number;
  lastUpdate:  string;
  totalConsoH: number;   // L cette heure
  totalConsoJ: number;   // L ce jour
  totalConsoM: number;   // L ce mois
  avgDebit:    number;
  alertCount:  number;
  leakCount:   number;
  co2Kg:       number;   // kgCO2
  costTnd:     number;   // TND
  trend:       string;   // ex: "+5.2%"
}

export interface GazChartPointDto {
  label: string;
  conso: number;
  debit: number;
  co2:   number;
}

export interface GazChartDto {
  points:     GazChartPointDto[];
  totalConso: number;
  totalCo2:   number;
  totalCost:  number;
}

export interface GazAlertDto {
  idDevice: number;
  date:     string;
  type:     'LEAK' | 'FRAUD' | 'HIGH_CONSO' | 'LOW_BATTERY';
  message:  string;
  severity: 'LOW' | 'HIGH' | 'CRITICAL';
}

export interface GazComparisonDto {
  currentPeriodConso:  number;
  previousPeriodConso: number;
  variationPercent:    number;
  trend:               'UP' | 'DOWN' | 'STABLE';
}

// ══════════════════════════════════════════════════════════════════════════════

@Injectable({ providedIn: 'root' })
export class GazService {

  private readonly base = `${environment.apiUrl}/api/gaz`;

  constructor(private http: HttpClient) {}

  // ── Helpers ──────────────────────────────────────────────────────────────

  /** Formate une Date en ISO local sans timezone : "2025-09-01T00:00:00" */
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

  getRealTimeAll(): Observable<RtGmDto[]> {
    return this.http.get<RtGmDto[]>(`${this.base}/realtime`).pipe(
      catchError(() => of([]))
    );
  }

  getRealTime(idDevice: number): Observable<RtGmDto | null> {
    return this.http.get<RtGmDto>(`${this.base}/realtime/${idDevice}`).pipe(
      catchError(() => of(null))
    );
  }

  getRealTimeAlerts(): Observable<RtGmDto[]> {
    return this.http.get<RtGmDto[]>(`${this.base}/realtime/alerts`).pipe(
      catchError(() => of([]))
    );
  }

  getRealTimeLeaks(): Observable<RtGmDto[]> {
    return this.http.get<RtGmDto[]>(`${this.base}/realtime/leaks`).pipe(
      catchError(() => of([]))
    );
  }

  // ── Brut 10 min ───────────────────────────────────────────────────────────

  getRaw(from: Date, to: Date, device?: number): Observable<ArchiveGmDto[]> {
    return this.http.get<ArchiveGmDto[]>(`${this.base}/raw`,
      { params: this.params(from, to, device) }
    ).pipe(catchError(() => of([])));
  }

  getLatestRaw(idDevice: number): Observable<ArchiveGmDto | null> {
    return this.http.get<ArchiveGmDto>(`${this.base}/raw/${idDevice}/latest`).pipe(
      catchError(() => of(null))
    );
  }

  // ── Horaire ───────────────────────────────────────────────────────────────

  getHourly(from: Date, to: Date, device?: number): Observable<ArchiveGmHDto[]> {
    return this.http.get<ArchiveGmHDto[]>(`${this.base}/hourly`,
      { params: this.params(from, to, device) }
    ).pipe(catchError(() => of([])));
  }

  // ── Journalier ────────────────────────────────────────────────────────────

  getDaily(from: Date, to: Date, device?: number): Observable<ArchiveGmJDto[]> {
    return this.http.get<ArchiveGmJDto[]>(`${this.base}/daily`,
      { params: this.params(from, to, device) }
    ).pipe(catchError(() => of([])));
  }

  // ── Mensuel ───────────────────────────────────────────────────────────────

  getMonthlyByDevice(idDevice: number): Observable<ArchiveGmMDto[]> {
    return this.http.get<ArchiveGmMDto[]>(`${this.base}/monthly/${idDevice}`).pipe(
      catchError(() => of([]))
    );
  }

  getMonthly(from: Date, to: Date, device?: number): Observable<ArchiveGmMDto[]> {
    return this.http.get<ArchiveGmMDto[]>(`${this.base}/monthly`,
      { params: this.params(from, to, device) }
    ).pipe(catchError(() => of([])));
  }

  // ── Résumé / Dashboard ────────────────────────────────────────────────────

  getSummary(idDevice: number, from: Date, to: Date): Observable<GazSummaryDto | null> {
    return this.http.get<GazSummaryDto>(`${this.base}/summary/${idDevice}`,
      { params: this.params(from, to) }
    ).pipe(catchError(() => of(null)));
  }

  getAllSummaries(from: Date, to: Date): Observable<GazSummaryDto[]> {
    return this.http.get<GazSummaryDto[]>(`${this.base}/summary`,
      { params: this.params(from, to) }
    ).pipe(catchError(() => of([])));
  }

  // ── Chart ─────────────────────────────────────────────────────────────────

  getDailyChart(idDevice: number, from: Date, to: Date): Observable<GazChartDto | null> {
    return this.http.get<GazChartDto>(`${this.base}/chart/daily/${idDevice}`,
      { params: this.params(from, to) }
    ).pipe(catchError(() => of(null)));
  }

  getMonthlyChart(idDevice: number, from: Date, to: Date): Observable<GazChartDto | null> {
    return this.http.get<GazChartDto>(`${this.base}/chart/monthly/${idDevice}`,
      { params: this.params(from, to) }
    ).pipe(catchError(() => of(null)));
  }

  // ── Alertes ───────────────────────────────────────────────────────────────

  getAlerts(): Observable<GazAlertDto[]> {
    return this.http.get<GazAlertDto[]>(`${this.base}/alerts`).pipe(
      catchError(() => of([]))
    );
  }

  // ── Comparaison ───────────────────────────────────────────────────────────

  compare(idDevice: number, from: Date, to: Date): Observable<GazComparisonDto | null> {
    return this.http.get<GazComparisonDto>(`${this.base}/compare/${idDevice}`,
      { params: this.params(from, to) }
    ).pipe(catchError(() => of(null)));
  }

  // ── Config ────────────────────────────────────────────────────────────────

  getConfig(idDevice: number): Observable<InitGmDto | null> {
    return this.http.get<InitGmDto>(`${this.base}/config/${idDevice}`).pipe(
      catchError(() => of(null))
    );
  }

  // ── Helpers périodes prêts à l'emploi ─────────────────────────────────────

  /** Retourne [début du mois courant, maintenant] */
  getCurrentMonthRange(): { from: Date; to: Date } {
    const now  = new Date();
    const from = new Date(now.getFullYear(), now.getMonth(), 1);
    return { from, to: now };
  }

  /** Retourne [il y a N jours, maintenant] */
  getLastNDaysRange(n: number): { from: Date; to: Date } {
    const to   = new Date();
    const from = new Date();
    from.setDate(from.getDate() - n);
    return { from, to };
  }
}