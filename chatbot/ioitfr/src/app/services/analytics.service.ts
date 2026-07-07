/**
 * Appelle les endpoints FastAPI /analytics/* (port 8001).
 * Retourne exactement les mêmes DTOs que les services Java
 * pour que le dashboard puisse les utiliser en fallback transparent.
 */
import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { map, catchError } from 'rxjs/operators';
import { environment } from '../../environments/environment';

import { ElecChartDto }  from './electricity.service';
import { WaterChartDto } from './water.service';
import { GazChartDto }   from './gaz.service';
import { FuelChartDto }  from './fuel.service';

export interface AdPrediction {
  domain:          string;
  item_id:         string;
  forecast_ts:     string;
  horizon_hours:   number;
  forecast_col:    string;
  forecast_median: number | null;
  forecast_low:    number | null;
  forecast_high:   number | null;
  confidence:      number | null;
  is_alert:        number;
  alert_severity:  string | null;
  run_at:          string;
}

export interface AdPredictionsResponse {
  horizon_hours: number;
  domain:        string | null;
  count:         number;
  predictions:   AdPrediction[];
}

export interface AdAnomaly {
  domain:        string;
  item_id:       string;
  strategy:      string;
  is_anomaly:    number;
  anomaly_score: number | null;
  data_ts:       string;
  value:         number | null;
  q10:           number | null;
  q90:           number | null;
  run_at:        string;
}

export interface AdKpis {
  date:      string;
  anomalies: Record<string, number>;
}

export interface AdAnomaliesResponse {
  start:     string;
  end:       string;
  domain:    string | null;
  count:     number;
  anomalies: AdAnomaly[];
}

interface AnalyticsRow {
  device_id:   string;
  date:        string;
  hour:        number;
  phase?:      string;
  // energy
  cons_en?:    number;
  // water
  conso_m3?:   number;
  nb_fuites?:  number;
  nb_fraudes?: number;
  // gas
  avg_debit?:  number;
  // fuel
  consumption?: number;
  avg_speed?:   number;
  fuel_level?:  number;
}

interface AnalyticsResponse {
  data:  AnalyticsRow[];
  count: number;
}

@Injectable({ providedIn: 'root' })
export class AnalyticsService {

  private readonly base = `${environment.ariaApiUrl}/analytics`;

  constructor(private http: HttpClient) {}

  // ── Energie ────────────────────────────────────────────────────────────────

  // Le fallback analytics couvre les archives historiques — on force 90j minimum
  // pour garantir que les données (qui peuvent avoir plusieurs semaines de retard) soient atteintes.
  private _days(days: number): number { return Math.max(days, 365); }

  getEnergyChart(days: number): Observable<ElecChartDto | null> {
    return this.http.get<AnalyticsResponse>(`${this.base}/energy`, {
      params: new HttpParams().set('days', this._days(days)),
    }).pipe(
      map(res => this._toElecChart(res.data ?? [])),
      catchError(() => of(null)),
    );
  }

  private _toElecChart(data: AnalyticsRow[]): ElecChartDto | null {
    if (!data.length) return null;

    const byDate = new Map<string, number>();
    for (const row of data) {
      byDate.set(row.date, (byDate.get(row.date) ?? 0) + (row.cons_en ?? 0));
    }

    const points = [...byDate.entries()].map(([date, kwh]) => ({
      label:      this._fmtDate(date),
      consKwh:    kwh,
      consL1:     0,
      consL2:     0,
      consL3:     0,
      avgCosfi:   0,
      avgThd:     0,
      avgVoltage: 0,
      co2Kg:      kwh * 0.233,
    }));

    const total = points.reduce((s, p) => s + p.consKwh, 0);
    return { points, totalConsKwh: total, totalCo2Kg: total * 0.233, totalCostTnd: 0 };
  }

  // ── Eau ────────────────────────────────────────────────────────────────────

  getWaterChart(days: number): Observable<WaterChartDto | null> {
    return this.http.get<AnalyticsResponse>(`${this.base}/water`, {
      params: new HttpParams().set('days', this._days(days)),
    }).pipe(
      map(res => this._toWaterChart(res.data ?? [])),
      catchError(() => of(null)),
    );
  }

  private _toWaterChart(data: AnalyticsRow[]): WaterChartDto | null {
    if (!data.length) return null;

    const byDate = new Map<string, number>();
    for (const row of data) {
      byDate.set(row.date, (byDate.get(row.date) ?? 0) + (row.conso_m3 ?? 0));
    }

    const points = [...byDate.entries()].map(([date, m3]) => ({
      label:   this._fmtDate(date),
      conso:   m3 * 1000,
      consoM3: m3,
      co2:     m3 * 0.376,
      cost:    0,
    }));

    const totalM3 = points.reduce((s, p) => s + p.consoM3, 0);
    return {
      points,
      totalConsoL:  totalM3 * 1000,
      totalConsoM3: totalM3,
      totalCo2:     totalM3 * 0.376,
      totalCost:    0,
    };
  }

  // ── Gaz ────────────────────────────────────────────────────────────────────

  getGazChart(days: number): Observable<GazChartDto | null> {
    return this.http.get<AnalyticsResponse>(`${this.base}/gas`, {
      params: new HttpParams().set('days', this._days(days)),
    }).pipe(
      map(res => this._toGazChart(res.data ?? [])),
      catchError(() => of(null)),
    );
  }

  private _toGazChart(data: AnalyticsRow[]): GazChartDto | null {
    if (!data.length) return null;

    const byDate = new Map<string, { conso: number; debit: number; n: number }>();
    for (const row of data) {
      const cur = byDate.get(row.date) ?? { conso: 0, debit: 0, n: 0 };
      cur.conso += row.conso_m3 ?? 0;
      cur.debit += row.avg_debit ?? 0;
      cur.n     += 1;
      byDate.set(row.date, cur);
    }

    const points = [...byDate.entries()].map(([date, v]) => ({
      label: this._fmtDate(date),
      conso: v.conso,
      debit: v.n ? v.debit / v.n : 0,
      co2:   v.conso * 2.04,
    }));

    const total = points.reduce((s, p) => s + p.conso, 0);
    return { points, totalConso: total, totalCo2: total * 2.04, totalCost: 0 };
  }

  // ── Carburant ──────────────────────────────────────────────────────────────

  getFuelChart(days: number): Observable<FuelChartDto | null> {
    return this.http.get<AnalyticsResponse>(`${this.base}/fuel`, {
      params: new HttpParams().set('days', this._days(days)),
    }).pipe(
      map(res => this._toFuelChart(res.data ?? [])),
      catchError(() => of(null)),
    );
  }

  private _toFuelChart(data: AnalyticsRow[]): FuelChartDto | null {
    if (!data.length) return null;

    const byDate = new Map<string, { conso: number; speed: number; n: number }>();
    for (const row of data) {
      const cur = byDate.get(row.date) ?? { conso: 0, speed: 0, n: 0 };
      cur.conso += row.consumption ?? 0;
      cur.speed += row.avg_speed   ?? 0;
      cur.n     += 1;
      byDate.set(row.date, cur);
    }

    const points = [...byDate.entries()].map(([date, v]) => ({
      label:      this._fmtDate(date),
      conso:      v.conso,
      distance:   0,
      co2:        v.conso * 2.68,
      cost:       0,
      efficiency: v.n ? v.speed / v.n : 0,
    }));

    const total = points.reduce((s, p) => s + p.conso, 0);
    return {
      points,
      totalConsoL:     total,
      totalDistanceKm: 0,
      totalCo2:        total * 2.68,
      totalCost:       0,
      avgEfficiency:   0,
    };
  }

  // ── Anomalies AD ───────────────────────────────────────────────────────────

  getAnomalies(days = 30, domain?: string): Observable<AdAnomaliesResponse> {
    let params = new HttpParams().set('days', days).set('only_true', true);
    if (domain) params = params.set('domain', domain);
    return this.http.get<AdAnomaliesResponse>(`${this.base}/anomalies`, { params }).pipe(
      catchError(() => of({ start: '', end: '', domain: domain ?? null, count: 0, anomalies: [] })),
    );
  }

  getPredictions(hours = 48, domain?: string, onlyAlert = true): Observable<AdPredictionsResponse> {
    // include_past=true : affiche aussi les prédictions passées quand le pipeline
    // n'a pas tourné aujourd'hui (données de démonstration ou pipeline différé)
    let params = new HttpParams()
      .set('hours', hours)
      .set('only_alert', onlyAlert)
      .set('include_past', true);
    if (domain) params = params.set('domain', domain);
    return this.http.get<AdPredictionsResponse>(`${this.base}/predictions`, { params }).pipe(
      catchError(() => of({ horizon_hours: hours, domain: domain ?? null, count: 0, predictions: [] })),
    );
  }

  getKpis(days = 7, date?: string): Observable<AdKpis> {
    let params = new HttpParams().set('days', days);
    if (date) params = params.set('date', date);
    return this.http.get<AdKpis>(`${this.base}/kpis`, { params }).pipe(
      map(r => ({ date: r.date, anomalies: r.anomalies ?? {} })),
      catchError(() => of({ date: '', anomalies: {} })),
    );
  }

  // ── Utilitaire ─────────────────────────────────────────────────────────────

  private _fmtDate(d: string): string {
    if (!d) return '';
    const p = d.substring(0, 10).split('-');
    return p.length === 3 ? `${p[2]}/${p[1]}` : d;
  }
}
