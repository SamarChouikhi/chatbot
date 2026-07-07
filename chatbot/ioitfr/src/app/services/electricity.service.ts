import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { environment } from '../../environments/environment';

// ══════════════════════════════════════════════════════════════════════════════
// INTERFACES — calquées exactement sur les DTOs Quarkus ElectricityDto.java
// ══════════════════════════════════════════════════════════════════════════════

export interface RtEnPDto {
  idDevice:       number;
  date:           string;
  enL1:           number;
  enL2:           number;
  enL3:           number;
  cosfiL1:        number;
  cosfiL2:        number;
  cosfiL3:        number;
  thdL1:          number;
  thdL2:          number;
  thdL3:          number;
  thdcL1:         number;
  thdcL2:         number;
  thdcL3:         number;
  rmsCurrentL1:   number;
  rmsCurrentL2:   number;
  rmsCurrentL3:   number;
  rmsVoltageL1:   number;
  rmsVoltageL2:   number;
  rmsVoltageL3:   number;
  activePowerL1:  number;
  activePowerL2:  number;
  activePowerL3:  number;
  enReactiveL1:   number;
  enReactiveL2:   number;
  enReactiveL3:   number;
  enApparentL1:   number;
  enApparentL2:   number;
  enApparentL3:   number;
  enAccumuleeJourL1: number;
  enAccumuleeJourL2: number;
  enAccumuleeJourL3: number;
  enAccumuleeMoisL1: number;
  enAccumuleeMoisL2: number;
  enAccumuleeMoisL3: number;
  rssi:           number;
  snr:            number;
  batteryLevel:   number;
  status:         'OK' | 'LOW_BATTERY' | 'HIGH_THD' | 'LOW_COSFI';
}

export interface ArchiveEnPHDto {
  idDevice:       number;
  date:           string;
  consEnL1:       number;
  consEnL2:       number;
  consEnL3:       number;
  totalConsKwh:   number;
  enL1:           number;
  enL2:           number;
  enL3:           number;
  moyCosfiL1:     number;
  moyCosfiL2:     number;
  moyCosfiL3:     number;
  moyThdL1:       number;
  moyThdL2:       number;
  moyThdL3:       number;
  batteryLevel:   number;
}

export interface ArchiveEnPJDto {
  idDevice:       number;
  date:           string;
  consEnL1:       number;
  consEnL2:       number;
  consEnL3:       number;
  totalConsKwh:   number;
  enL1:           number;
  enL2:           number;
  enL3:           number;
  moyCosfiL1:     number;
  moyCosfiL2:     number;
  moyCosfiL3:     number;
  moyThdL1:       number;
  moyThdL2:       number;
  moyThdL3:       number;
  batteryLevel:   number;
}

export interface ArchiveEnPMDto {
  idDevice:       number;
  date:           string;
  consEnL1:       number;
  consEnL2:       number;
  consEnL3:       number;
  totalConsKwh:   number;
  enL1:           number;
  enL2:           number;
  enL3:           number;
  moyCosfiL1:     number;
  moyCosfiL2:     number;
  moyCosfiL3:     number;
  moyThdL1:       number;
  moyThdL2:       number;
  moyThdL3:       number;
  batteryLevel:   number;
}

export interface ElecSummaryDto {
  idDevice:          number;
  lastUpdate:        string;
  totalConsoHKwh:    number;   // kWh cette heure
  totalConsoJKwh:    number;   // kWh ce jour
  totalConsoMKwh:    number;   // kWh ce mois
  consoL1Kwh:        number;
  consoL2Kwh:        number;
  consoL3Kwh:        number;
  avgCosfi:          number;   // facteur de puissance moyen
  avgThd:            number;   // THD moyen
  avgVoltage:        number;   // tension moyenne (V)
  avgCurrent:        number;   // courant moyen (A)
  totalActivePowerKw:number;   // puissance active totale (kW)
  co2Kg:             number;   // kg CO2 eq
  costTnd:           number;   // coût estimé TND
  alertCount:        number;
  trend:             string;   // ex: "+5.2%"
  batteryLevel:      number;
  status:            'OK' | 'LOW_BATTERY' | 'HIGH_THD' | 'LOW_COSFI';
}

export interface ElecChartPointDto {
  label:      string;
  consKwh:    number;
  consL1:     number;
  consL2:     number;
  consL3:     number;
  avgCosfi:   number;
  avgThd:     number;
  avgVoltage: number;
  co2Kg:      number;
}

export interface ElecChartDto {
  points:        ElecChartPointDto[];
  totalConsKwh:  number;
  totalCo2Kg:    number;
  totalCostTnd:  number;
}

export interface ElecAlertDto {
  idDevice: number;
  date:     string;
  type:     'LOW_BATTERY' | 'HIGH_THD' | 'LOW_COSFI' | 'HIGH_CONSO';
  message:  string;
  severity: 'LOW' | 'HIGH' | 'CRITICAL';
  value:    number;
}

export interface ElecComparisonDto {
  currentPeriodKwh:  number;
  previousPeriodKwh: number;
  variationPercent:  number;
  trend:             'UP' | 'DOWN' | 'STABLE';
  currentCo2Kg:      number;
  previousCo2Kg:     number;
  currentCostTnd:    number;
  previousCostTnd:   number;
}

// ══════════════════════════════════════════════════════════════════════════════

@Injectable({ providedIn: 'root' })
export class ElectricityService {

  private readonly base = `${environment.apiUrl}/api/electricity`;

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

  getRealTimeAll(): Observable<RtEnPDto[]> {
    return this.http.get<RtEnPDto[]>(`${this.base}/realtime`).pipe(
      catchError(() => of([]))
    );
  }

  getRealTime(idDevice: number): Observable<RtEnPDto | null> {
    return this.http.get<RtEnPDto>(`${this.base}/realtime/${idDevice}`).pipe(
      catchError(() => of(null))
    );
  }

  getDevicesWithLowBattery(): Observable<RtEnPDto[]> {
    return this.http.get<RtEnPDto[]>(`${this.base}/realtime/alerts/battery`).pipe(
      catchError(() => of([]))
    );
  }

  getDevicesWithHighTHD(): Observable<RtEnPDto[]> {
    return this.http.get<RtEnPDto[]>(`${this.base}/realtime/alerts/thd`).pipe(
      catchError(() => of([]))
    );
  }

  getDevicesWithLowCosfi(): Observable<RtEnPDto[]> {
    return this.http.get<RtEnPDto[]>(`${this.base}/realtime/alerts/cosfi`).pipe(
      catchError(() => of([]))
    );
  }

  // ── Horaire ───────────────────────────────────────────────────────────────

  getHourly(from: Date, to: Date, device?: number): Observable<ArchiveEnPHDto[]> {
    return this.http.get<ArchiveEnPHDto[]>(`${this.base}/hourly`,
      { params: this.params(from, to, device) }
    ).pipe(catchError(() => of([])));
  }

  // ── Journalier ────────────────────────────────────────────────────────────

  getDaily(from: Date, to: Date, device?: number): Observable<ArchiveEnPJDto[]> {
    return this.http.get<ArchiveEnPJDto[]>(`${this.base}/daily`,
      { params: this.params(from, to, device) }
    ).pipe(catchError(() => of([])));
  }

  // ── Mensuel ───────────────────────────────────────────────────────────────

  getMonthlyByDevice(idDevice: number): Observable<ArchiveEnPMDto[]> {
    return this.http.get<ArchiveEnPMDto[]>(`${this.base}/monthly/${idDevice}`).pipe(
      catchError(() => of([]))
    );
  }

  getMonthly(from: Date, to: Date, device?: number): Observable<ArchiveEnPMDto[]> {
    return this.http.get<ArchiveEnPMDto[]>(`${this.base}/monthly`,
      { params: this.params(from, to, device) }
    ).pipe(catchError(() => of([])));
  }

  // ── Résumé / Dashboard ────────────────────────────────────────────────────

  getSummary(idDevice: number, from: Date, to: Date): Observable<ElecSummaryDto | null> {
    return this.http.get<ElecSummaryDto>(`${this.base}/summary/${idDevice}`,
      { params: this.params(from, to) }
    ).pipe(catchError(() => of(null)));
  }

  getAllSummaries(from: Date, to: Date): Observable<ElecSummaryDto[]> {
    return this.http.get<ElecSummaryDto[]>(`${this.base}/summary`,
      { params: this.params(from, to) }
    ).pipe(catchError(() => of([])));
  }

  // ── Chart ─────────────────────────────────────────────────────────────────

  getHourlyChart(idDevice: number, from: Date, to: Date): Observable<ElecChartDto | null> {
    return this.http.get<ElecChartDto>(`${this.base}/chart/hourly/${idDevice}`,
      { params: this.params(from, to) }
    ).pipe(catchError(() => of(null)));
  }

  getDailyChart(idDevice: number, from: Date, to: Date): Observable<ElecChartDto | null> {
    return this.http.get<ElecChartDto>(`${this.base}/chart/daily/${idDevice}`,
      { params: this.params(from, to) }
    ).pipe(catchError(() => of(null)));
  }

  getMonthlyChart(idDevice: number, from: Date, to: Date): Observable<ElecChartDto | null> {
    return this.http.get<ElecChartDto>(`${this.base}/chart/monthly/${idDevice}`,
      { params: this.params(from, to) }
    ).pipe(catchError(() => of(null)));
  }

  // ── Alertes ───────────────────────────────────────────────────────────────

  getAlerts(): Observable<ElecAlertDto[]> {
    return this.http.get<ElecAlertDto[]>(`${this.base}/alerts`).pipe(
      catchError(() => of([]))
    );
  }

  // ── Comparaison ───────────────────────────────────────────────────────────

  compare(idDevice: number, from: Date, to: Date): Observable<ElecComparisonDto | null> {
    return this.http.get<ElecComparisonDto>(`${this.base}/compare/${idDevice}`,
      { params: this.params(from, to) }
    ).pipe(catchError(() => of(null)));
  }

  // ── Qualité réseau ────────────────────────────────────────────────────────

  getPowerQualityDaily(idDevice: number, from: Date, to: Date): Observable<any[]> {
    return this.http.get<any[]>(`${this.base}/quality/daily/${idDevice}`,
      { params: this.params(from, to) }
    ).pipe(catchError(() => of([])));
  }

  getPowerQualityMonthly(idDevice: number, from: Date, to: Date): Observable<any[]> {
    return this.http.get<any[]>(`${this.base}/quality/monthly/${idDevice}`,
      { params: this.params(from, to) }
    ).pipe(catchError(() => of([])));
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
