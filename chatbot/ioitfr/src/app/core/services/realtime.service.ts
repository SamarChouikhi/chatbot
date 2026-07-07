import { Injectable, OnDestroy } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import {
  Observable, Subject, BehaviorSubject, interval,
  Subscription, of, EMPTY
} from 'rxjs';
import {
  switchMap, catchError, distinctUntilChanged,
  takeUntil, share, filter, map
} from 'rxjs/operators';
import { SseService, SseEvent } from './sse.service';
import { environment } from 'src/environments/environment';

// ── Types capteurs ────────────────────────────────────────────
export interface SensorReading {
  device_id    : string | number;
  table        : string;
  last_update ?: string;
  // THL
  temperature ?: { value: number; unit: string };
  humidity    ?: { value: number; unit: string };
  luminosity  ?: { value: number; unit: string };
  // WM / GM
  forward_flow?: number;
  index       ?: number;
  leak        ?: number;
  fraud       ?: number;
  // EN
  active_power_L1?: { value: number; unit: string };
  voltage_L1     ?: { value: number; unit: string };
  cosfi_L1       ?: number;
  // SM
  wind_speed  ?: { value: number; unit: string };
  pressure    ?: { value: number; unit: string };
  uv_index    ?: number;
  // Commun
  battery_level?: { value: number; unit: string };
  rssi         ?: { value: number; unit: string };
  status       ?: number;
  raw          ?: any;
}

export interface RealtimePayload {
  sensor_type: string;
  sensors    : SensorReading[];
  count      : number;
  tables     : string[];
  duration   : number;
}

export interface AriaStreamChunk {
  token    ?: string;   // texte partiel
  answer   ?: string;   // réponse complète (dernier événement)
  done     ?: boolean;
  error    ?: string;
}

// ── Service ───────────────────────────────────────────────────
@Injectable({ providedIn: 'root' })
export class RealtimeService implements OnDestroy {

  private readonly ARIA_API   = environment.ariaApiUrl;
  private readonly BACKEND_API = environment.apiUrl;

  /** Intervalle de polling des capteurs en ms (défaut 30s) */
  private readonly POLL_MS    = 30_000;

  private destroy$            = new Subject<void>();
  private _sensors$           = new BehaviorSubject<SensorReading[]>([]);
  private _connected$         = new BehaviorSubject<boolean>(false);
  private pollSub            ?: Subscription;

  // ── Observable public des données capteurs ────────────────
  /** Émet à chaque mise à jour des capteurs (polling 30s). */
  sensors$: Observable<SensorReading[]> = this._sensors$.asObservable();

  /** Émet true lorsque la connexion est active. */
  connected$: Observable<boolean> = this._connected$.asObservable().pipe(
    distinctUntilChanged()
  );

  constructor(
    private http  : HttpClient,
    private sseSvc: SseService,
  ) {}

  // ══════════════════════════════════════════════════════════
  // POLLING — Données capteurs toutes les 30 secondes
  // ══════════════════════════════════════════════════════════

  /**
   * Démarre le polling automatique des données temps réel.
   * Appelle GET /realtime toutes les `intervalMs` ms.
   * Appel idempotent — un seul polling actif à la fois.
   *
   * @param sensorType  'all' | 'thl' | 'wm' | 'en' | 'gm' | 'sm'
   * @param intervalMs  Intervalle en ms (défaut: 30 000)
   */
  startPolling(sensorType = 'all', intervalMs = this.POLL_MS): void {
    if (this.pollSub && !this.pollSub.closed) return;

    this.pollSub = interval(intervalMs).pipe(
      switchMap(() => this._fetchRealtime(sensorType)),
      takeUntil(this.destroy$),
    ).subscribe();

    // Premier appel immédiat
    this._fetchRealtime(sensorType).subscribe();
  }

  /** Arrête le polling. */
  stopPolling(): void {
    this.pollSub?.unsubscribe();
    this._connected$.next(false);
  }

  private _fetchRealtime(sensorType: string): Observable<void> {
    return this.http.get<{ status: string; sensors?: SensorReading[] }>(
      `${this.ARIA_API}/realtime`,
      { params: { sensor_type: sensorType } }
    ).pipe(
      map(res => {
        const sensors = res?.sensors ?? [];
        this._sensors$.next(sensors);
        this._connected$.next(true);
      }),
      catchError(() => {
        this._connected$.next(false);
        return EMPTY;
      })
    );
  }

  // ══════════════════════════════════════════════════════════
  // SSE — Streaming réponse ARIA (chatbot)
  // ══════════════════════════════════════════════════════════

  /**
   * Ouvre un flux SSE vers ARIA pour le streaming de réponse chatbot.
   * Retourne un Observable qui émet les chunks de texte progressivement.
   *
   * @param question   Question de l'utilisateur
   * @param token      JWT Bearer token
   * @param threadId   ID du thread (optionnel)
   * @param userId     ID de l'utilisateur
   */
  streamAriaResponse(
    question: string,
    token   : string,
    threadId?: string,
    userId  = 'default_user',
  ): Observable<AriaStreamChunk> {
    const params = new URLSearchParams({
      question,
      userId,
      ...(threadId ? { threadId } : {}),
    });
    const url = `${this.ARIA_API}/chat/stream?${params.toString()}`;

    return this.sseSvc.stream<AriaStreamChunk>(url, token).pipe(
      filter(event => event.type === 'message' || event.type === 'chunk' || event.type === 'done'),
      map(event => event.data),
      takeUntil(this.destroy$),
      share(),
    );
  }

  // ══════════════════════════════════════════════════════════
  // SSE — Alertes en temps réel depuis le backend
  // ══════════════════════════════════════════════════════════

  /**
   * Flux SSE des alertes depuis le backend Quarkus.
   * Reconnexion automatique gérée par SseService.
   *
   * @param token  JWT Bearer token
   */
  alertStream(token: string): Observable<any> {
    const url = `${this.BACKEND_API}/api/alerts/stream`;
    return this.sseSvc.stream<any>(url, token).pipe(
      filter(event => event.type === 'alert' || event.type === 'message'),
      map(event => event.data),
      takeUntil(this.destroy$),
      share(),
    );
  }

  // ══════════════════════════════════════════════════════════
  // Snapshot — lecture ponctuelle (sans polling)
  // ══════════════════════════════════════════════════════════

  /** Lecture unique des capteurs sans démarrer le polling. */
  getSnapshot(sensorType = 'all'): Observable<SensorReading[]> {
    return this.http.get<{ sensors: SensorReading[] }>(
      `${this.ARIA_API}/realtime`,
      { params: { sensor_type: sensorType } }
    ).pipe(
      map(res => res?.sensors ?? []),
      catchError(() => of([]))
    );
  }

  // ── Helpers publics ───────────────────────────────────────

  /** Dernière valeur connue des capteurs (synchrone). */
  get currentSensors(): SensorReading[] {
    return this._sensors$.getValue();
  }

  /** true si le polling est actif et a reçu des données. */
  get isConnected(): boolean {
    return this._connected$.getValue();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    this._sensors$.complete();
    this._connected$.complete();
  }
}
