import { Component, OnInit, OnDestroy } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslateService } from '@ngx-translate/core';
import { Subject, forkJoin } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { DeviceService, Device } from '../services/device.service';
import { GazService, RtGmDto, GazSummaryDto, GazAlertDto } from '../services/gaz.service';
import { WaterService, RtWmDto, WaterSummaryDto, WaterAlertDto } from '../services/water.service';
import { ElectricityService, RtEnPDto, ElecSummaryDto, ElecAlertDto } from '../services/electricity.service';
import { FuelService, FuelLatestDto, FuelSummaryDto, FuelAlertDto } from '../services/fuel.service';
import { normalizeBattery } from '../shared/battery.util';

@Component({
  selector: 'app-device-detail',
  templateUrl: './device-detail.component.html',
  styleUrls: ['./device-detail.component.scss']
})
export class DeviceDetailComponent implements OnInit, OnDestroy {

  device: Device | null = null;
  isLoading = true;
  errorMsg = '';

  rtGaz: RtGmDto | null = null;
  gazSummary: GazSummaryDto | null = null;
  gazAlerts: GazAlertDto[] = [];

  rtWater: RtWmDto | null = null;
  waterSummary: WaterSummaryDto | null = null;
  waterAlerts: WaterAlertDto[] = [];

  rtElec: RtEnPDto | null = null;
  elecSummary: ElecSummaryDto | null = null;
  elecAlerts: ElecAlertDto[] = [];

  fuelLatest: FuelLatestDto | null = null;
  fuelSummary: FuelSummaryDto | null = null;
  fuelAlerts: FuelAlertDto[] = [];

  private destroy$ = new Subject<void>();
  private deviceId = 0;
  private deviceAdresse = 0;

  readonly typeKeys: Record<number, string> = {
    1: 'DEVICES_PAGE.TYPE_ELEC', 2: 'DEVICES_PAGE.TYPE_WATER',
    3: 'DEVICES_PAGE.TYPE_GAS',  4: 'DEVICES_PAGE.TYPE_FUEL'
  };

  constructor(
    private route    : ActivatedRoute,
    private router   : Router,
    private deviceSvc: DeviceService,
    private gazSvc   : GazService,
    private waterSvc : WaterService,
    private elecSvc  : ElectricityService,
    private fuelSvc  : FuelService,
    private translate: TranslateService
  ) {}

  ngOnInit(): void {
    this.deviceId      = +this.route.snapshot.paramMap.get('id')!;
    this.deviceAdresse = +this.route.snapshot.paramMap.get('adresse')!;
    this.load();
  }

  ngOnDestroy(): void { this.destroy$.next(); this.destroy$.complete(); }

  // ══════════════════════════════════════════════════════════════
  // CHARGEMENT
  // ══════════════════════════════════════════════════════════════

  load(): void {
    this.isLoading = true;
    this.errorMsg  = '';
    this.deviceSvc.getOne(this.deviceId, this.deviceAdresse)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next:  d  => { this.device = d; this.loadMonitoring(d); },
        error: () => { this.errorMsg = 'Impossible de charger le dispositif.'; this.isLoading = false; }
      });
  }

  private loadMonitoring(d: Device): void {
    const { from, to } = this.getRange(30);
    switch (d.type) {
      case 1: this.loadElec(d.id, from, to);  break;
      case 2: this.loadWater(d.id, from, to); break;
      case 3: this.loadGaz(d.id, from, to);   break;
      case 4: this.loadFuel(d.id, from, to);  break;
      default: this.isLoading = false;
    }
  }

  // ══════════════════════════════════════════════════════════════
  // CHARGEMENT PAR DOMAINE (gaz / eau / élec / carburant)
  // ══════════════════════════════════════════════════════════════

  private loadGaz(id: number, from: Date, to: Date): void {
    forkJoin([this.gazSvc.getRealTime(id), this.gazSvc.getSummary(id, from, to), this.gazSvc.getAlerts()])
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: ([rt, summary, alerts]) => {
          this.rtGaz      = rt;
          this.gazSummary = summary;
          this.gazAlerts  = alerts.filter(a => a.idDevice === id).slice(0, 5);
          this.isLoading  = false;
        },
        error: () => { this.isLoading = false; }
      });
  }

  private loadWater(id: number, from: Date, to: Date): void {
    forkJoin([this.waterSvc.getRealTime(id), this.waterSvc.getSummary(id, from, to), this.waterSvc.getAlerts()])
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: ([rt, summary, alerts]) => {
          this.rtWater      = rt;
          this.waterSummary = summary;
          this.waterAlerts  = alerts.filter(a => a.idDevice === id).slice(0, 5);
          this.isLoading    = false;
        },
        error: () => { this.isLoading = false; }
      });
  }

  private loadElec(id: number, from: Date, to: Date): void {
    forkJoin([this.elecSvc.getRealTime(id), this.elecSvc.getSummary(id, from, to), this.elecSvc.getAlerts()])
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: ([rt, summary, alerts]) => {
          this.rtElec      = rt;
          this.elecSummary = summary;
          this.elecAlerts  = alerts.filter(a => a.idDevice === id).slice(0, 5);
          this.isLoading   = false;
        },
        error: () => { this.isLoading = false; }
      });
  }

  private loadFuel(id: number, from: Date, to: Date): void {
    forkJoin([this.fuelSvc.getLatest(id), this.fuelSvc.getSummary(id, from, to), this.fuelSvc.getAlerts()])
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: ([latest, summary, alerts]) => {
          this.fuelLatest  = latest;
          this.fuelSummary = summary;
          this.fuelAlerts  = alerts.filter(a => a.deviceId === id).slice(0, 5);
          this.isLoading   = false;
        },
        error: () => { this.isLoading = false; }
      });
  }

  // ══════════════════════════════════════════════════════════════
  // GETTERS AGRÉGÉS (toutes-domaines confondues)
  // ══════════════════════════════════════════════════════════════

  get rtStatus(): string {
    return this.rtGaz?.status || this.rtWater?.status || this.rtElec?.status || this.fuelLatest?.status || '';
  }

  get alerts(): any[] {
    return [...this.gazAlerts, ...this.waterAlerts, ...this.elecAlerts, ...this.fuelAlerts];
  }

  get totalActivePower(): number {
    if (!this.rtElec) return 0;
    return (this.rtElec.activePowerL1 ?? 0) + (this.rtElec.activePowerL2 ?? 0) + (this.rtElec.activePowerL3 ?? 0);
  }

  // ══════════════════════════════════════════════════════════════
  // HELPERS TEMPLATE
  // ══════════════════════════════════════════════════════════════

  goBack(): void { this.router.navigate(['/device']); }

  /** Normalise le niveau batterie IoT (spec LoRaWAN 0–254, voir shared/battery.util.ts) */
  normBatt(v: number | null | undefined): number {
    return normalizeBattery(v);
  }

  getTypeLabel(type: number | null): string {
    return type != null ? this.translate.instant(this.typeKeys[type] ?? String(type)) : '—';
  }

  getStatusColor(status: string): string {
    const map: Record<string, string> = {
      OK: 'green',
      LEAK: 'red', FRAUD: 'red',
      ALERT: 'orange', HIGH_CONSO: 'orange',
      LOW_BATTERY: 'orange', HIGH_THD: 'orange', LOW_COSFI: 'orange',
      LOW_EFFICIENCY: 'orange', HIGH_SPEED: 'orange', EXCESSIVE_IDLE: 'orange'
    };
    return map[status] || 'gray';
  }

  getSeverityColor(severity: string): string {
    const map: Record<string, string> = { LOW: 'yellow', HIGH: 'orange', CRITICAL: 'red' };
    return map[severity] || 'gray';
  }

  private getRange(days: number): { from: Date; to: Date } {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - days);
    return { from, to };
  }
}
