import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { environment } from '../../environments/environment';

// ══════════════════════════════════════════════════════════════════════════════
// INTERFACES — calquées sur FuelDto.java
// ══════════════════════════════════════════════════════════════════════════════

export interface FuelLatestDto {
  deviceId:              number;
  date:                  string;
  fuelType:              string;
  mileageKm:             number;
  consumptionLiters:     number;
  consumptionPercentage: number;
  tankCapacityLiters:    number;
  carbonKg:              number;
  costTnd:               number;
  efficiencyL100km:      number;
  status:                'OK' | 'HIGH_CONSO' | 'LOW_EFFICIENCY';
}

export interface ArchiveFuelDto {
  id:           number;
  date:         string;
  idDevice:     number;
  lat:          number;
  lon:          number;
  temperature:  number;
  vitesse:      number;
  consommation: number;
  distance:     number;
  tempsArret:   number;
}

export interface ArchiveFuelJDto {
  id:           number;
  date:         string;
  idDevice:     number;
  temperature:  number;
  vitesse:      number;
  consommation: number;
  distance:     number;
  tempsArret:   number;
}

export interface ArchiveFuelMDto {
  id:           number;
  date:         string;
  idDevice:     number;
  temperature:  number;
  vitesse:      number;
  consommation: number;
  distance:     number;
  tempsArret:   number;
}

export interface FuelConsumptionDto {
  date:                  string;
  deviceId:              number;
  fuelType:              string;
  mileageKm:             number;
  quantityAddedLiters:   number;
  consumptionLiters:     number;
  consumptionPercentage: number;
  tankCapacityLiters:    number;
  carbonKg:              number;
  costTnd:               number;
}

export interface FuelSummaryDto {
  deviceId:            number;
  lastUpdate:          string;
  totalConsoL:         number;
  totalDistanceKm:     number;
  avgSpeedKmh:         number;
  avgEfficiencyL100km: number;
  co2Kg:               number;
  costTnd:             number;
  fuelType:            string;
  trend:               string;
  alertCount:          number;
}

export interface FuelChartPointDto {
  label:      string;
  conso:      number;
  distance:   number;
  co2:        number;
  cost:       number;
  efficiency: number;
}

export interface FuelChartDto {
  points:          FuelChartPointDto[];
  totalConsoL:     number;
  totalDistanceKm: number;
  totalCo2:        number;
  totalCost:       number;
  avgEfficiency:   number;
}

export interface FuelStatsDto {
  deviceId:            number;
  avgDailyConsoL:      number;
  maxDailyConsoL:      number;
  minDailyConsoL:      number;
  avgDailyDistanceKm:  number;
  totalDistanceKm:     number;
  avgEfficiencyL100km: number;
  avgSpeedKmh:         number;
  totalIdleMinutes:    number;
  variationVsPrevMonth:number;
  totalAlerts:         number;
}

export interface FuelAlertDto {
  deviceId: number;
  date:     string;
  type:     'HIGH_CONSO' | 'LOW_EFFICIENCY' | 'EXCESSIVE_IDLE' | 'HIGH_SPEED';
  message:  string;
  severity: 'LOW' | 'HIGH' | 'CRITICAL';
  value:    number;
}

export interface FuelComparisonDto {
  currentPeriodConso:  number;
  previousPeriodConso: number;
  variationPercent:    number;
  trend:               'UP' | 'DOWN' | 'STABLE';
}

// ══════════════════════════════════════════════════════════════════════════════

@Injectable({ providedIn: 'root' })
export class FuelService {

  private readonly base = `${environment.apiUrl}/api/fuel`;

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

  // ── Dernier état ─────────────────────────────────────────────────────────

  getAllLatest(): Observable<FuelLatestDto[]> {
    return this.http.get<FuelLatestDto[]>(`${this.base}/latest`).pipe(catchError(() => of([])));
  }

  getLatest(deviceId: number): Observable<FuelLatestDto | null> {
    return this.http.get<FuelLatestDto>(`${this.base}/latest/${deviceId}`).pipe(catchError(() => of(null)));
  }

  // ── Résumé ────────────────────────────────────────────────────────────────

  getAllSummaries(from: Date, to: Date): Observable<FuelSummaryDto[]> {
    return this.http.get<FuelSummaryDto[]>(`${this.base}/summary`,
      { params: this.params(from, to) }).pipe(catchError(() => of([])));
  }

  getSummary(deviceId: number, from: Date, to: Date): Observable<FuelSummaryDto | null> {
    return this.http.get<FuelSummaryDto>(`${this.base}/summary/${deviceId}`,
      { params: this.params(from, to) }).pipe(catchError(() => of(null)));
  }

  // ── Charts ────────────────────────────────────────────────────────────────

  getDailyChart(deviceId: number, from: Date, to: Date): Observable<FuelChartDto | null> {
    return this.http.get<FuelChartDto>(`${this.base}/chart/daily/${deviceId}`,
      { params: this.params(from, to) }).pipe(catchError(() => of(null)));
  }

  getMonthlyChart(deviceId: number, from: Date, to: Date): Observable<FuelChartDto | null> {
    return this.http.get<FuelChartDto>(`${this.base}/chart/monthly/${deviceId}`,
      { params: this.params(from, to) }).pipe(catchError(() => of(null)));
  }

  // ── Alertes ───────────────────────────────────────────────────────────────

  getAlerts(): Observable<FuelAlertDto[]> {
    return this.http.get<FuelAlertDto[]>(`${this.base}/alerts`).pipe(catchError(() => of([])));
  }

  // ── fuel_consumption ─────────────────────────────────────────────────────

  getConsumptionByDevice(deviceId: number): Observable<FuelConsumptionDto[]> {
    return this.http.get<FuelConsumptionDto[]>(`${this.base}/consumption/${deviceId}`)
      .pipe(catchError(() => of([])));
  }

  // ── Helpers périodes ─────────────────────────────────────────────────────

  getLastNDaysRange(n: number): { from: Date; to: Date } {
    const to   = new Date();
    const from = new Date();
    from.setDate(from.getDate() - n);
    return { from, to };
  }
}
