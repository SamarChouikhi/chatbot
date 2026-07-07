import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

import { ShellService } from './shell.service';
import { ElecSummaryDto, ElecAlertDto } from '../../services/electricity.service';
import { WaterSummaryDto, WaterAlertDto } from '../../services/water.service';
import { GazSummaryDto, GazAlertDto } from '../../services/gaz.service';
import { FuelSummaryDto, FuelAlertDto } from '../../services/fuel.service';

export type Period = 7 | 30 | 90;

export interface TopEmitter {
  name: string; co2Kg: number; alertCount: number;
  trendDown: boolean; trendVal: string;
  pct: number; color: string; icon: string;
}

@Injectable({ providedIn: 'root' })
export class DashboardService {

  // ── Raw data ──────────────────────────────────────────────────
  elecSummaries:  ElecSummaryDto[]  = [];
  elecAlerts:     ElecAlertDto[]    = [];
  gazSummaries:   GazSummaryDto[]   = [];
  gazAlerts:      GazAlertDto[]     = [];
  waterSummaries: WaterSummaryDto[] = [];
  waterAlerts:    WaterAlertDto[]   = [];
  fuelSummaries:  FuelSummaryDto[]  = [];
  fuelAlerts:     FuelAlertDto[]    = [];

  // ── Electricity KPIs ─────────────────────────────────────────
  elecKwh = 0; elecCo2 = 0; elecCost = 0; elecTrend = '0.0%';
  elecAvgCosfi = 0; elecAvgThd = 0; elecDevices = 0; elecCritical = 0;

  // ── Water KPIs ───────────────────────────────────────────────
  waterM3 = 0; waterCo2 = 0; waterCost = 0; waterTrend = '0.0%';
  waterLeaks = 0; waterFrauds = 0; waterDevices = 0; waterCritical = 0;

  // ── Gas KPIs ─────────────────────────────────────────────────
  gazL = 0; gazCo2 = 0; gazCost = 0; gazTrend = '0.0%';
  gazLeaks = 0; gazAvgDebit = 0; gazDevices = 0; gazCritical = 0;

  // ── Fuel KPIs ────────────────────────────────────────────────
  fuelL = 0; fuelCo2 = 0; fuelCost = 0; fuelTrend = '0.0%';
  fuelKm = 0; fuelAvgSpeed = 0; fuelDevices = 0; fuelCritical = 0;

  // ── Globals ───────────────────────────────────────────────────
  totalCo2 = 0; totalCost = 0;

  // ── CO₂ trajectory ────────────────────────────────────────────
  co2RealisePct = 0; co2Projection = 0; co2ProjectionWarning = false;
  private co2Objective = 0;

  // ── Derived ───────────────────────────────────────────────────
  topEmitters: TopEmitter[] = [];
  hourlyCo2Points: { label: string; co2: number }[] = [];

  readonly updated$ = new Subject<void>();

  constructor(private shellSvc: ShellService) {}

  // ── KPI updates ───────────────────────────────────────────────

  updateElec(summaries: ElecSummaryDto[], alerts: ElecAlertDto[]): void {
    this.elecSummaries = summaries;
    this.elecAlerts    = alerts;
    this.elecKwh       = this.sum(summaries, 'totalConsoJKwh');
    this.elecCo2       = this.sum(summaries, 'co2Kg');
    this.elecCost      = this.sum(summaries, 'costTnd');
    this.elecTrend     = summaries[0]?.trend ?? '0.0%';
    this.elecAvgCosfi  = this.avg(summaries, 'avgCosfi');
    this.elecAvgThd    = this.avg(summaries, 'avgThd');
    this.elecDevices   = summaries.length;
    this.elecCritical  = alerts.filter(a => a.severity === 'CRITICAL').length;
  }

  updateWater(summaries: WaterSummaryDto[], alerts: WaterAlertDto[]): void {
    this.waterSummaries = summaries;
    this.waterAlerts    = alerts;
    this.waterM3        = this.sum(summaries, 'totalConsoM3');
    this.waterCo2       = this.sum(summaries, 'co2Kg');
    this.waterCost      = this.sum(summaries, 'costTnd');
    this.waterTrend     = summaries[0]?.trend ?? '0.0%';
    this.waterLeaks     = this.sum(summaries, 'leakCount');
    this.waterFrauds    = this.sum(summaries, 'fraudCount');
    this.waterDevices   = summaries.length;
    this.waterCritical  = alerts.filter(a => a.severity === 'CRITICAL').length;
  }

  updateGaz(summaries: GazSummaryDto[], alerts: GazAlertDto[]): void {
    this.gazSummaries = summaries;
    this.gazAlerts    = alerts;
    this.gazL         = this.sum(summaries, 'totalConsoM');
    this.gazCo2       = this.sum(summaries, 'co2Kg');
    this.gazCost      = this.sum(summaries, 'costTnd');
    this.gazTrend     = summaries[0]?.trend ?? '0.0%';
    this.gazLeaks     = this.sum(summaries, 'leakCount');
    this.gazAvgDebit  = this.avg(summaries, 'avgDebit');
    this.gazDevices   = summaries.length;
    this.gazCritical  = alerts.filter(a => a.severity === 'CRITICAL').length;
  }

  updateFuel(summaries: FuelSummaryDto[], alerts: FuelAlertDto[]): void {
    this.fuelSummaries = summaries;
    this.fuelAlerts    = alerts;
    this.fuelL         = this.sum(summaries, 'totalConsoL');
    this.fuelCo2       = this.sum(summaries, 'co2Kg');
    this.fuelCost      = this.sum(summaries, 'costTnd');
    this.fuelTrend     = summaries[0]?.trend ?? '0.0%';
    this.fuelKm        = this.sum(summaries, 'totalDistanceKm');
    this.fuelAvgSpeed  = this.avg(summaries, 'avgSpeedKmh');
    this.fuelDevices   = summaries.length;
    this.fuelCritical  = alerts.filter(a => a.severity === 'CRITICAL').length;
  }

  computeGlobals(period: Period, from: Date): void {
    this.totalCo2  = this.elecCo2  + this.waterCo2  + this.gazCo2  + this.fuelCo2;
    this.totalCost = this.elecCost + this.waterCost + this.gazCost + this.fuelCost;

    const totalCritical = this.elecCritical + this.waterCritical + this.gazCritical + this.fuelCritical;
    this.shellSvc.update({
      elecCritical:  this.elecCritical,
      waterLeaks:    this.waterLeaks,
      gazLeaks:      this.gazLeaks,
      totalAlerts:   totalCritical + this.waterLeaks + this.gazLeaks,
      criticalCount: totalCritical,
    });

    this._computeCo2Trajectory(period, from);
    this._computeTopEmitters();
    this._generateHourlyCo2(period);
    this.updated$.next();
  }

  // ── Private computation ───────────────────────────────────────

  private _computeCo2Trajectory(period: Period, from: Date): void {
    this.co2Objective        = 1000 * period;
    this.co2RealisePct       = this.co2Objective > 0
      ? Math.round(this.totalCo2 / this.co2Objective * 100) : 0;
    const daysElapsed        = Math.max(1, Math.ceil((Date.now() - from.getTime()) / 86_400_000));
    this.co2Projection       = Math.round(this.totalCo2 * period / daysElapsed);
    this.co2ProjectionWarning = this.co2Projection > this.co2Objective;
  }

  private _computeTopEmitters(): void {
    type Row = Record<string, unknown>;
    const items: TopEmitter[] = [];

    const push = (
      summaries: Row[], alerts: Row[],
      prefix: string, color: string, icon: string, idField: string,
    ) => {
      for (const s of summaries) {
        const devId      = s[idField];
        const alertCount = alerts.filter(
          a => (a[idField] ?? a['idDevice'] ?? a['deviceId']) === devId
        ).length;
        const trend = (s['trend'] as string) ?? '0.0%';
        items.push({
          name: `${prefix} #${devId}`, co2Kg: (s['co2Kg'] as number) ?? 0,
          alertCount, trendDown: trend.startsWith('-'),
          trendVal: trend.replace(/^[+-]/, ''), pct: 0, color, icon,
        });
      }
    };

    push(this.elecSummaries  as unknown as Row[], this.elecAlerts  as unknown as Row[], 'Elec', '#0ea5e9', '⚡', 'idDevice');
    push(this.waterSummaries as unknown as Row[], this.waterAlerts as unknown as Row[], 'Eau',  '#06b6d4', '💧', 'idDevice');
    push(this.gazSummaries   as unknown as Row[], this.gazAlerts   as unknown as Row[], 'Gaz',  '#0d9488', '🔥', 'idDevice');
    push(this.fuelSummaries  as unknown as Row[], this.fuelAlerts  as unknown as Row[], 'Carb', '#22c55e', '🚗', 'deviceId');

    items.sort((a, b) => b.co2Kg - a.co2Kg);
    const maxCo2 = items[0]?.co2Kg || 1;
    items.forEach(i => i.pct = Math.round(i.co2Kg / maxCo2 * 100));
    this.topEmitters = items.slice(0, 5);
  }

  private _generateHourlyCo2(period: Period): void {
    if (this.totalCo2 <= 0) { this.hourlyCo2Points = []; return; }
    const currentHour = new Date().getHours();
    const avgDaily    = this.totalCo2 / period;
    const weights: Record<number, number> = {
      6: 0.04, 7: 0.06, 8: 0.08, 9: 0.09, 10: 0.09, 11: 0.08,
      12: 0.07, 13: 0.07, 14: 0.08, 15: 0.08, 16: 0.07, 17: 0.06,
      18: 0.05, 19: 0.04, 20: 0.04,
    };
    this.hourlyCo2Points = [];
    for (let h = 6; h <= Math.min(currentHour, 20); h++) {
      const base  = avgDaily * (weights[h] ?? 0.05);
      const noise = base * (Math.random() * 0.18 - 0.09);
      this.hourlyCo2Points.push({
        label: `${h.toString().padStart(2, '0')}h`,
        co2:   Math.max(0, base + noise),
      });
    }
  }

  // ── Helpers ───────────────────────────────────────────────────

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private sum(arr: any[], f: string): number { return arr.reduce((s, d) => s + (d[f] ?? 0), 0); }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private avg(arr: any[], f: string): number { return arr.length ? this.sum(arr, f) / arr.length : 0; }
}
