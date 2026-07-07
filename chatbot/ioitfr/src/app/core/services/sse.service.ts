import { Injectable, NgZone } from '@angular/core';
import { Observable } from 'rxjs';

export interface SseEvent<T = any> {
  type : string;
  data : T;
}

/**
 * SseService — Server-Sent Events avec support Authorization header.
 *
 * EventSource natif ne supporte pas les headers custom.
 * On utilise fetch() + ReadableStream pour contourner cette limitation
 * et envoyer le JWT dans Authorization: Bearer <token>.
 *
 * Usage :
 *   this.sseService.stream<MyType>('/api/events', token).subscribe(event => { ... });
 */
@Injectable({ providedIn: 'root' })
export class SseService {

  constructor(private zone: NgZone) {}

  /**
   * Ouvre un flux SSE authentifié vers `url`.
   * Reconnexion automatique toutes les `retryMs` ms en cas d'erreur réseau.
   *
   * @param url      URL du endpoint SSE
   * @param token    JWT Bearer token (optionnel)
   * @param retryMs  Délai de reconnexion en ms (défaut: 3000)
   */
  stream<T = any>(url: string, token?: string, retryMs = 3000): Observable<SseEvent<T>> {
    return new Observable(observer => {
      let abortCtrl = new AbortController();
      let retryTimer: any;
      let closed = false;

      const headers: Record<string, string> = {
        'Accept': 'text/event-stream',
      };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const connect = async () => {
        if (closed) return;
        abortCtrl = new AbortController();

        try {
          const response = await fetch(url, {
            method : 'GET',
            headers,
            signal : abortCtrl.signal,
          });

          if (!response.ok || !response.body) {
            throw new Error(`SSE HTTP ${response.status}`);
          }

          const reader  = response.body.getReader();
          const decoder = new TextDecoder();
          let   buffer  = '';

          while (true) {
            const { value, done } = await reader.read();
            if (done || closed) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() ?? '';

            let eventType = 'message';
            let dataLines: string[] = [];

            for (const line of lines) {
              if (line.startsWith('event:')) {
                eventType = line.slice(6).trim();
              } else if (line.startsWith('data:')) {
                dataLines.push(line.slice(5).trim());
              } else if (line === '') {
                // Fin d'un bloc SSE
                if (dataLines.length > 0) {
                  const raw = dataLines.join('\n');
                  try {
                    const parsed = JSON.parse(raw) as T;
                    this.zone.run(() => observer.next({ type: eventType, data: parsed }));
                  } catch {
                    this.zone.run(() => observer.next({ type: eventType, data: raw as any }));
                  }
                  dataLines = [];
                  eventType = 'message';
                }
              }
            }
          }
        } catch (err: any) {
          if (err?.name === 'AbortError' || closed) return;
          // Reconnexion automatique
          retryTimer = setTimeout(() => connect(), retryMs);
        }
      };

      connect();

      // Nettoyage à la désinscription
      return () => {
        closed = true;
        clearTimeout(retryTimer);
        abortCtrl.abort();
      };
    });
  }

  /**
   * Flux SSE simple (sans auth) — compatibilité EventSource native.
   * Utile pour les endpoints publics ou lorsque le token est dans l'URL.
   */
  streamNative(url: string): Observable<SseEvent> {
    return new Observable(observer => {
      const es = new EventSource(url);

      es.onmessage = (e) => this.zone.run(() =>
        observer.next({ type: 'message', data: this._tryParse(e.data) })
      );

      es.addEventListener('error', () => {
        // EventSource reconnecte automatiquement
      });

      es.onerror = (e) => {
        if (es.readyState === EventSource.CLOSED) {
          this.zone.run(() => observer.error(e));
        }
      };

      return () => es.close();
    });
  }

  private _tryParse(raw: string): any {
    try { return JSON.parse(raw); } catch { return raw; }
  }
}
