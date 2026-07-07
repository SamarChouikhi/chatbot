import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError, timeout } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface QuickReply {
  label: string;
  value: string;
}

export interface AriaChartDataset {
  label  : string;
  data   : number[];
  color ?: string;
  colors?: string[];
}

export interface AriaChartConfig {
  type    : 'line' | 'bar' | 'doughnut';
  title   : string;
  labels  : string[];
  datasets: AriaChartDataset[];
  unit   ?: string;
  yMax   ?: number;
}

export interface StreamEvent {
  type         : 'thinking' | 'tool' | 'chunk' | 'done' | 'error' | 'file' | 'pdf' | 'pdf_analysis';
  data        ?: string;
  level       ?: string;
  thread_id   ?: string;
  message_id  ?: number;
  backend     ?: string;
  duration    ?: number;
  quick_replies?: QuickReply[];
  chart_data  ?: AriaChartConfig[];
  file_id     ?: string;
  filename    ?: string;
  // PDF sensor report (jsPDF frontend)
  report_type ?: string;   // e.g. 'water:all'
  // PDF analyse ARIA (backend reportlab)  ← nouveau
  pdf_url     ?: string;
}

export interface ChatResponse {
  answer    : string;
  backend   : string;
  level     : string;
  duration  : number;
  thread_id : string;
  message_id: number | null;
  confidence: 'haute' | 'moyenne' | 'faible' | null;
}

export interface Thread {
  thread_id    : string;
  title        : string;
  message_count: number;
  created_at   : string;
  updated_at   : string;
  preview?     : string;
  is_favorite? : boolean;
}

export interface MessageHistory {
  id?        : number;
  role       : string;
  content    : string;
  level?     : string;
  backend?   : string;
  created_at : string;
  feedback?  : 'up' | 'down' | null;
  chart_data?: AriaChartConfig[];
}

export interface TranscribeResponse {
  text    : string;
  language: string;
}

export interface VisionResponse {
  analysis: string;
  model   : string;
}

@Injectable({ providedIn: 'root' })
export class AriaService {

  private readonly PYTHON  = environment.ariaApiUrl;
  private readonly TIMEOUT = 120000;

  constructor(private http: HttpClient) {}

  getCurrentUserId(): string {
    try {
      const userStr = localStorage.getItem('user') || sessionStorage.getItem('user') || '{}';
      const user = JSON.parse(userStr);
      return user.login || 'default_user';
    } catch {
      return 'default_user';
    }
  }

  getCurrentUserRole(): string {
    try {
      const userStr = localStorage.getItem('user') || sessionStorage.getItem('user') || '{}';
      const user = JSON.parse(userStr);
      return user.role || 'EMPLOYEE';
    } catch {
      return 'EMPLOYEE';
    }
  }

  ask(question: string, threadId?: string,
      userId: string = 'default_user', lang?: string): Observable<ChatResponse> {
    const body: any = { question, userId };
    if (threadId) body.threadId = threadId;
    if (lang) body.lang = lang;
    // allowed_modules non envoyé : le backend Python fait la lookup depuis aria_employees
    return this.http.post<ChatResponse>(`${this.PYTHON}/chat`, body).pipe(
      timeout(this.TIMEOUT),
      catchError(err => {
        let msg = 'Impossible de contacter le serveur.';
        if (err.name === 'TimeoutError') msg = 'Delai depasse. Reessayez.';
        if (err.status === 429)          msg = 'Trop de requetes. Attendez.';
        if (err.status === 503)          msg = 'Service ARIA non disponible.';
        if (err.status !== 0 && err.status !== 429 && err.status !== 503)
          msg = `Erreur serveur (${err.status})`;
        return throwError(() => new Error(msg));
      })
    );
  }

  getThreads(userId = 'default_user', limit = 20): Observable<Thread[]> {
    const params = new HttpParams().set('user_id', userId).set('limit', limit);
    return this.http.get<Thread[]>(`${this.PYTHON}/threads`, { params });
  }

  getMessages(threadId: string, limit = 50): Observable<MessageHistory[]> {
    return this.http.get<MessageHistory[]>(
      `${this.PYTHON}/threads/${threadId}/messages`,
      { params: new HttpParams().set('limit', limit) }
    );
  }

  newConversation(userId = 'default_user'): Observable<{ thread_id: string }> {
    return this.http.post<{ thread_id: string }>(
      `${this.PYTHON}/new`, {}, { params: new HttpParams().set('user_id', userId) }
    );
  }

  toggleFavoriteAPI(threadId: string): Observable<any> {
    return this.http.put(`${this.PYTHON}/threads/${threadId}/favorite`, {});
  }

  deleteThread(threadId: string): Observable<any> {
    return this.http.delete(`${this.PYTHON}/threads/${threadId}`);
  }

  updateTitle(threadId: string, title: string): Observable<any> {
    const params = new HttpParams().set('title', title);
    return this.http.put(`${this.PYTHON}/threads/${threadId}/title`, {}, { params });
  }

  askStream(question: string, threadId?: string, userId = 'default_user', lang?: string): Observable<StreamEvent> {
    const params = new URLSearchParams({ question, userId });
    if (threadId) params.append('threadId', threadId);
    if (lang) params.append('lang', lang);
    const url = `${this.PYTHON}/chat/stream?${params.toString()}`;

    return new Observable<StreamEvent>(observer => {
      const es = new EventSource(url);

      const timer = setTimeout(() => {
        es.close();
        observer.error(new Error('Délai dépassé. Reformulez votre question.'));
      }, this.TIMEOUT);

      es.onmessage = (e: MessageEvent) => {
        try {
          const event = JSON.parse(e.data) as StreamEvent;
          observer.next(event);
          if (event.type === 'done' || event.type === 'error') {
            clearTimeout(timer);
            observer.complete();
            es.close();
          }
        } catch { /* ignore malformed frames */ }
      };

      es.onerror = () => {
        clearTimeout(timer);
        observer.error(new Error('Connexion SSE interrompue.'));
        es.close();
      };

      return () => {
        clearTimeout(timer);
        es.close();
      };
    }).pipe(
      catchError(err => throwError(() => new Error(err.message || 'Erreur SSE')))
    );
  }

  streamChat(question: string, threadId?: string, userId = 'default_user', lang?: string): EventSource {
    let url = `${this.PYTHON}/chat/stream?question=${encodeURIComponent(question)}&userId=${userId}`;
    if (threadId) url += `&threadId=${encodeURIComponent(threadId)}`;
    if (lang) url += `&lang=${encodeURIComponent(lang)}`;
    return new EventSource(url);
  }

  postFeedback(messageId: number, threadId: string,
               vote: 'up' | 'down', userId = 'default_user'): Observable<any> {
    return this.http.post(`${this.PYTHON}/feedback`, {
      message_id: messageId, thread_id: threadId,
      vote, user_id: userId
    });
  }

  getFeedbackStats(): Observable<any> {
    return this.http.get(`${this.PYTHON}/feedback/stats`);
  }

  health(): Observable<any> {
    return this.http.get(`${this.PYTHON}/health`).pipe(timeout(5000));
  }

  // ── Vision — analyse d'image via Gemini ──────
  analyzeImage(imageFile: File, question = ''): Observable<VisionResponse> {
    const form = new FormData();
    form.append('file', imageFile, imageFile.name);
    if (question.trim()) form.append('question', question.trim());

    return this.http.post<VisionResponse>(`${this.PYTHON}/analyze-image`, form).pipe(
      timeout(60000),
      catchError(err => {
        let msg = "Erreur d'analyse d'image.";
        if (err.name === 'TimeoutError') msg = 'Analyse trop longue (>60s). Réessayez.';
        if (err.status === 0)   msg = 'Serveur inaccessible.';
        if (err.status === 401) msg = 'Clé VISION_API_KEY invalide.';
        if (err.status === 413) msg = 'Image trop grande (max 20 Mo).';
        if (err.status === 415) msg = 'Format non supporté. Utilisez JPEG, PNG ou WEBP.';
        if (err.status === 429) msg = 'Quota Gemini dépassé. Attendez quelques secondes.';
        if (err.status === 500) msg = err.error?.detail || 'Erreur serveur interne.';
        return throwError(() => ({ error: { detail: msg } }));
      })
    );
  }

  // ── Speech-to-Text via AssemblyAI ──────────────────────
  transcribe(audioBlob: Blob, language = 'fr'): Observable<TranscribeResponse> {
    const form = new FormData();

    const mimeType = audioBlob.type || 'audio/webm';
    const ext = mimeType.includes('mp3') ? 'mp3'
              : mimeType.includes('wav') ? 'wav'
              : mimeType.includes('ogg') ? 'ogg'
              : 'webm';

    form.append('file', audioBlob, `recording.${ext}`);
    form.append('language', language);

    return this.http.post<TranscribeResponse>(`${this.PYTHON}/transcribe`, form).pipe(
      timeout(60000),
      catchError(err => {
        console.error('[STT] HTTP status:', err.status, '| name:', err.name, '| body:', err.error);
        let msg = 'Erreur de transcription.';
        if (err.name === 'TimeoutError') msg = 'Transcription trop longue (>60s). Réessayez.';
        if (err.status === 0)            msg = 'Serveur inaccessible (localhost:8001).';
        if (err.status === 422)          msg = `Paramètre invalide : ${JSON.stringify(err.error?.detail)}`;
        if (err.status === 429)          msg = 'Quota dépassé. Attendez quelques secondes.';
        if (err.status === 413)          msg = 'Audio trop long. Maximum 25 Mo.';
        if (err.status === 401)          msg = 'Clé API invalide.';
        if (err.status === 500)          msg = err.error?.detail || 'Erreur serveur interne.';
        return throwError(() => ({ error: { detail: msg } }));
      })
    );
  }
}