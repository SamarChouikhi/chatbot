import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface KpiSummary {
  electricityCo2: number;
  waterCo2: number;
  gasCo2: number;
  fuelCo2: number;
  totalCo2: number;
  totalCost: number;
  electricityTrend: string;
  waterTrend: string;
  gasTrend: string;
  fuelTrend: string;
  alertCount: number;
}

export interface ChartData {
  label: string;
  electricity: number;
  water: number;
  fuel: number;
}

export interface DeviceStats {
  activeDevices: number;
  totalDevices: number;
  activeSpaces: number;
  totalSpaces: number;
  alertDevices: number;
}

export interface AlertSummary {
  date: string;
  deviceName: string;
  message: string;
  severity: string;
}

export interface FullDashboard {
  summary: KpiSummary;
  chartData: ChartData[];
  deviceStats: DeviceStats;
  alerts: AlertSummary[];
}

@Injectable({ providedIn: 'root' })
export class KpiService {
  private base = `${environment.apiUrl}/api/kpis`;

  constructor(private http: HttpClient) {}

  getFullDashboard(): Observable<FullDashboard> {
    return this.http.get<FullDashboard>(`${this.base}/full`);
  }

  getChartData(period = 30): Observable<{ chartData: ChartData[] }> {
    return this.http.get<{ chartData: ChartData[] }>(`${this.base}/chart-data?period=${period}`);
  }
}
