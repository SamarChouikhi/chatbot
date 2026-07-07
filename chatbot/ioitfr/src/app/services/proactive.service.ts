import { Injectable, OnDestroy } from '@angular/core';
import { HttpClient }           from '@angular/common/http';
import { BehaviorSubject, Subject } from 'rxjs';
import { environment }          from '../../environments/environment';

export interface ProactiveMessage {
  id:          number;
  domain:      string;
  severity:    'HIGH' | 'MEDIUM' | 'LOW';
  message:     string;
  source_type: 'anomaly' | 'prediction';
  qr_label:    string;
  qr_value:    string;
  created_at:  string;
  read_at:     string | null;
}

@Injectable({ providedIn: 'root' })
export class ProactiveService implements OnDestroy {

  private readonly base = environment.ariaApiUrl;

  /** Flux de nouveaux messages proactifs reçus via SSE. */
  readonly newMessage$ = new Subject<ProactiveMessage>();

  /** Nombre de messages non lus. */
  readonly unreadCount$ = new BehaviorSubject<number>(0);

  private eventSource: EventSource | null = null;
  private userId = '';
  private retryCount = 0;
  private readonly MAX_RETRIES = 5;

  constructor(private http: HttpClient) {}

  /** Initialise la connexion SSE proactive pour un utilisateur. */
  connect(userId: string): void {
    if (this.eventSource || !userId) return;
    this.userId = userId;

    // Charge les messages en attente
    this.loadPending();

    const url = `${this.base}/proactive/stream?userId=${encodeURIComponent(userId)}`;
    this.eventSource = new EventSource(url);

    this.eventSource.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type === 'heartbeat' || !data.id) return;
        const msg: ProactiveMessage = data as ProactiveMessage;
        this.newMessage$.next(msg);
        this.unreadCount$.next(this.unreadCount$.value + 1);
      } catch { /* ignore parse errors */ }
    };

    this.eventSource.onerror = () => {
      this.retryCount++;
      if (this.retryCount > this.MAX_RETRIES) {
        this.disconnect();
      }
    };
  }

  /** Charge les messages en attente depuis l'API REST. */
  loadPending(): void {
    if (!this.userId) return;
    this.http.get<{ count: number; messages: ProactiveMessage[] }>(
      `${this.base}/proactive/messages`, { params: { userId: this.userId } }
    ).subscribe({
      next: res => {
        const unread = res.messages.filter(m => !m.read_at).length;
        this.unreadCount$.next(unread);
        // Émet uniquement les messages non encore lus (évite le ré-affichage à chaque démarrage)
        res.messages.filter(m => !m.read_at).slice().reverse().forEach(m => this.newMessage$.next(m));
      },
      error: () => {},
    });
  }

  markRead(msgId: number): void {
    this.http.post(`${this.base}/proactive/read/${msgId}`, {}).subscribe({ error: () => {} });
    const cur = this.unreadCount$.value;
    if (cur > 0) this.unreadCount$.next(cur - 1);
  }

  dismiss(msgId: number): void {
    this.http.post(
      `${this.base}/proactive/dismiss/${msgId}`,
      {},
      { params: { userId: this.userId } }
    ).subscribe({ error: () => {} });
  }

  disconnect(): void {
    this.eventSource?.close();
    this.eventSource = null;
    this.retryCount  = 0;
  }

  ngOnDestroy(): void {
    this.disconnect();
  }
}
