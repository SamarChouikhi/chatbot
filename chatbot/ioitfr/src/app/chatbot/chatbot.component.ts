import {
  Component, ElementRef, Input, ViewChild,
  OnInit, OnDestroy, AfterViewChecked
} from '@angular/core';
import { Subject, Observable } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { TranslateService } from '@ngx-translate/core';
import { AriaService, Thread, MessageHistory, VisionResponse, StreamEvent, QuickReply, AriaChartConfig } from '../services/aria.service';
import { ThemeService } from '../core/services/theme.service';
import { AuthService } from '../services/auth.service';
import { UserService } from '../services/users.service';
import { DeviceService } from '../services/device.service';
import { NotificationService } from '../core/services/notification.service';
import { FieldConfig } from '../shared/dynamic-form/field-config';
import { USER_FORM_FIELDS, DEVICE_FORM_FIELDS, ALERT_RULE_FIELDS, DEVICE_TYPE_MODULE_MAP } from '../shared/dynamic-form/form-configs';
import { ChatNavService, NavCard } from '../shared/chat-nav/chat-nav.service';
import { PdfReportService, ReportRequest, ReportDomain, ReportFilter } from '../services/pdf-report.service';
import { ProactiveService } from '../services/proactive.service';
import { ChatTriggerService } from '../core/services/chat-trigger.service';
import { environment } from '../../environments/environment';

export interface ChatFormConfig {
  fields:         FieldConfig[];
  submitLabel:    string;
  submitFn:       (data: any) => Observable<any>;
  successMessage: string;
}

export interface CsvDownload {
  fileId  : string;
  filename: string;
  url     : string;
}

export interface PdfDownload {
  request    : ReportRequest;
  filename   : string;
  generatedAt: Date;
}

export interface PdfAnalysis {
  fileId  : string;
  filename: string;
  url     : string;
}

export interface ChatMessage {
  id           : string;
  messageId   ?: number;
  content      : string;
  imageUrl    ?: string;
  sender       : 'user' | 'bot';
  timestamp    : Date;
  feedback    ?: 'up' | 'down' | null;
  streaming   ?: boolean;
  quickReplies?: QuickReply[];
  formConfig  ?: ChatFormConfig;
  navCard     ?: NavCard;
  chartConfigs?: AriaChartConfig[];
  csvDownload ?: CsvDownload;
  pdfDownload ?: PdfDownload;
  pdfAnalysis ?: PdfAnalysis;
  isProactive ?: boolean;
  proactiveId ?: number;
}

export type ThinkingPhase = 'off' | 'thinking' | 'tool' | 'writing';

export interface ChatSession {
  id      : string;
  title   : string;
  preview : string;
  date    : Date;
  group   : 'today' | 'week' | 'month' | 'older';
}

const DOM_LABEL: Record<ReportDomain, string> = {
  water      : 'Eau',
  gaz        : 'Gaz',
  electricity: 'Électricité',
  fuel       : 'Carburant',
};

const FLT_LABEL: Record<ReportFilter, string> = {
  all        : 'Tous les capteurs',
  active     : 'Capteurs actifs',
  inactive   : 'Capteurs inactifs',
  alert      : 'En alerte',
  leak       : 'Fuites détectées',
  fraud      : 'Fraudes détectées',
  low_battery: 'Batterie faible',
};

@Component({
  selector   : 'app-chatbot',
  templateUrl: './chatbot.component.html',
  styleUrls  : ['./chatbot.component.scss']
})
export class ChatbotComponent implements OnInit, OnDestroy, AfterViewChecked {

  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;
  @ViewChild('messageInput')    private messageInput!: ElementRef;
  @Input() isDashboardMode = false;

  private destroy$          = new Subject<void>();
  private stopGeneration$   = new Subject<void>();
  private shouldScrollToBottom = false;
  readonly USER_ID   = this.ariaService.getCurrentUserId();
  readonly USER_ROLE  = this.ariaService.getCurrentUserRole();

  // ── Initiales et nom complet depuis AuthService ──
  get userInitials(): string { return this.auth.getInitials(); }
  get userFullName(): string { return this.auth.getFullName(); }
  get userRoleLabel(): string { return this.auth.getRoleLabel(); }

  // ── Permissions formulaires rapides ──
  get canAddUser(): boolean    { return this.auth.getCurrentRole() === 'SUPER_ADMIN'; }
  get canAddDevice(): boolean  { return this.auth.hasModule('équipements/capteurs'); }
  get canAddAlert(): boolean   { return this.auth.hasModule('alertes'); }

  // ── State ──────────────────────────────────
  currentThreadId: string | null = null;

  isOpen        = false;
  isFullscreen  = false;
  isHistoryOpen = false;
  showSearch    = false;
  isTyping      = false;
  isListening   = false;
  get isDarkMode(): boolean { return this.theme.isDark; }
  userInput     = '';
  unreadCount      = 0;
  isPdfGenerating       = false;
  private pendingPdf   : ReportRequest | null = null;
  loadedSessionBanner  = '';

  // ── Streaming SSE state ────────────────────────────────────
  streamingMsgId : string | null = null;
  thinkingPhase  : ThinkingPhase = 'off';
  thinkingLabel  = '';
  toolLabel      = '';

  // ── Voice / STT (MediaRecorder → AssemblyAI via backend) ──────────
  isVoiceSupported: boolean | null = null;
  isTranscribing = false;
  audioLevels: number[] = Array(28).fill(3);
  recordingSeconds = 0;
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private meterRafId: number | null = null;
  private recordingTimerId: ReturnType<typeof setInterval> | null = null;
  private voiceCancelled = false;

  get recordingTimeLabel(): string {
    const m = Math.floor(this.recordingSeconds / 60).toString().padStart(2, '0');
    const s = (this.recordingSeconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  }

  // ── TTS (SpeechSynthesis — natif navigateur) ──────────────────
  speakingMsgId: string | null = null;

  // ── Messages ───────────────────────────────
  messages: ChatMessage[] = [];

  editingSessionId : string | null = null;
  editingTitle     : string        = '';

  activeSessionId     = '';
  currentSessionTitle = '';

  sessions        : ChatSession[] = [];
  filteredSessions: ChatSession[] = [];
  historySearchQuery = '';

  get suggestions(): string[] {
    const t = (k: string) => this.translate.instant('CHATBOT.SUGGESTIONS.' + k);
    const mods = this.auth.getAllowedModules();
    if (mods === null) {
      return [t('ANOMALIES'), t('FULL_ANALYSIS'), t('SENSOR_TEMP')];
    }
    const map: Record<string, string> = {
      'eau':                  t('WATER_USAGE'),
      'énergie électrique':   t('ELEC_ANALYSIS'),
      'gaz':                  t('GAS_LEAKS'),
      'carburant':            t('FUEL_LEVEL'),
      'alertes':              t('ACTIVE_ALERTS'),
      'rapports':             t('REPORT_24H'),
      'équipements/capteurs': t('SENSORS_STATUS'),
      'dashboard':            t('SYSTEM_SUMMARY'),
    };
    const picks = mods.filter(m => map[m]).map(m => map[m]).slice(0, 3);
    return picks.length > 0 ? picks : [t('ANOMALIES')];
  }

  constructor(
    private ariaService   : AriaService,
    public  theme         : ThemeService,
    private auth          : AuthService,
    private translate     : TranslateService,
    private userService   : UserService,
    private deviceSvc     : DeviceService,
    private notif         : NotificationService,
    private chatNav       : ChatNavService,
    private pdfReport     : PdfReportService,
    public  proactiveSvc  : ProactiveService,
    private chatTrigger   : ChatTriggerService,
  ) {}

  ngOnInit(): void {
    this.checkVoiceSupport();
    this.loadThreadsFromAPI();
    if (this.isDashboardMode) { this.isOpen = true; this.isHistoryOpen = false; }

    this.chatTrigger.open$.pipe(takeUntil(this.destroy$)).subscribe(question => {
      this.isOpen        = true;
      this.isHistoryOpen = false;
      setTimeout(() => this.sendMessage(question), 120);
    });

    // Connexion SSE proactive — ARIA initie des messages sans question
    if (this.USER_ID) {
      this.proactiveSvc.connect(this.USER_ID);
      this.proactiveSvc.newMessage$
        .pipe(takeUntil(this.destroy$))
        .subscribe(pm => {
          const qrs: QuickReply[] = [
            { label: pm.qr_label || 'Analyser', value: pm.qr_value || pm.message }
          ];
          this.messages.push({
            id          : this.generateId(),
            proactiveId : pm.id,
            content     : pm.message,
            sender      : 'bot',
            timestamp   : new Date(pm.created_at),
            isProactive : true,
            quickReplies: qrs,
          });
          this.shouldScrollToBottom = true;
          if (!this.isOpen && !this.isDashboardMode) this.unreadCount++;
          this.proactiveSvc.markRead(pm.id);
        });
    }
  }

  toggleTheme(): void { this.theme.toggle(); }

  ngAfterViewChecked(): void {
    if (this.shouldScrollToBottom) {
      this.scrollToBottom();
      this.shouldScrollToBottom = false;
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    if (this.isListening) this._stopRecording();
    this.stopSpeaking();
    this.proactiveSvc.disconnect();
  }

  dismissProactive(msg: ChatMessage): void {
    msg.quickReplies = undefined;
    msg.content      = '_(message ignoré)_';
    if (msg.proactiveId) this.proactiveSvc.dismiss(msg.proactiveId);
  }

  private generateId(): string {
    return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
  }

  private focusInput(): void {
    setTimeout(() => this.messageInput?.nativeElement?.focus(), 100);
  }

  private scrollToBottom(): void {
    try {
      const el = this.scrollContainer?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    } catch { /* silent */ }
  }

  // ══════════════════════════════════════════
  // VOICE INPUT — MediaRecorder → AssemblyAI
  // ══════════════════════════════════════════

  private checkVoiceSupport(): void {
    this.isVoiceSupported = !!(navigator.mediaDevices && window.MediaRecorder);
  }

  /**
   * Détecte la langue d'un texte pour le TTS.
   * Priorité : arabe → français → anglais (fallback).
   */
  private _detectLang(text: string): string {
    if (/[؀-ۿ]/.test(text)) return 'ar-SA';
    const frWords = /\b(le|la|les|de|du|des|et|est|un|une|vous|nous|je|tu|il|elle|pas|plus|très|avec|pour|sur|dans|qui|que|ce|au|aux|être|avoir|faire|voici|voilà|donc|mais|aussi|tout|cette|cette|son|ses|leur|leurs|ou|où|ça|bien|peut|même)\b/i;
    if (frWords.test(text)) return 'fr-FR';
    return 'en-US';
  }

  private _stopRecording(): void {
    try { this.mediaRecorder?.stop(); } catch { /* silent */ }
    this.mediaRecorder = null;
    this.audioChunks   = [];
    this.isListening   = false;
    this._stopAudioMeter();
    this._stopRecordingTimer();
  }

  /** Anime la barre de signal (waveform) à partir du niveau audio réel du micro. */
  private _startAudioMeter(stream: MediaStream): void {
    try {
      const Ctx = window.AudioContext || (window as any).webkitAudioContext;
      if (!Ctx) return;
      this.audioCtx = new Ctx();
      if (this.audioCtx.state === 'suspended') this.audioCtx.resume();
      const source = this.audioCtx.createMediaStreamSource(stream);
      this.analyser = this.audioCtx.createAnalyser();
      this.analyser.fftSize = 64;
      this.analyser.smoothingTimeConstant = 0.6;
      source.connect(this.analyser);

      const data = new Uint8Array(this.analyser.frequencyBinCount);
      const barCount = this.audioLevels.length;
      const step = Math.max(1, Math.floor(data.length / barCount));

      const tick = () => {
        if (!this.analyser) return;
        this.analyser.getByteFrequencyData(data);
        this.audioLevels = this.audioLevels.map((_, i) => {
          const v = data[i * step] || 0;
          return Math.max(3, Math.round((v / 255) * 28));
        });
        this.meterRafId = requestAnimationFrame(tick);
      };
      tick();
    } catch { /* dégradation silencieuse : la barre reste statique */ }
  }

  private _stopAudioMeter(): void {
    if (this.meterRafId !== null) { cancelAnimationFrame(this.meterRafId); this.meterRafId = null; }
    this.analyser = null;
    if (this.audioCtx) { this.audioCtx.close().catch(() => {}); this.audioCtx = null; }
    this.audioLevels = this.audioLevels.map(() => 3);
  }

  private _stopRecordingTimer(): void {
    if (this.recordingTimerId !== null) { clearInterval(this.recordingTimerId); this.recordingTimerId = null; }
  }

  /** Annule l'enregistrement en cours sans lancer la transcription. */
  cancelVoiceInput(): void {
    this.voiceCancelled = true;
    try { this.mediaRecorder?.stop(); } catch { /* silent */ }
  }

  speak(msg: ChatMessage): void {
    if (this.speakingMsgId === msg.id) {
      this.stopSpeaking();
      return;
    }
    this.stopSpeaking();
    const plain = msg.content.replace(/[#*`_~>\-]+/g, ' ').replace(/\s+/g, ' ').trim();
    const utter = new SpeechSynthesisUtterance(plain);
    utter.lang  = this._detectLang(plain);
    utter.rate  = 1;
    utter.onend = () => { this.speakingMsgId = null; };
    utter.onerror = () => { this.speakingMsgId = null; };
    this.speakingMsgId = msg.id;
    window.speechSynthesis.speak(utter);
  }

  stopSpeaking(): void {
    window.speechSynthesis?.cancel();
    this.speakingMsgId = null;
  }

  startVoiceInput(): void {
    if (!this.isVoiceSupported) {
      alert('Enregistrement audio non supporté par ce navigateur.');
      return;
    }

    // Second clic : arrêter l'enregistrement et envoyer
    if (this.isListening) {
      this.mediaRecorder?.stop();
      return;
    }

    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
      this.audioChunks     = [];
      this.isListening     = true;
      this.voiceCancelled  = false;
      this.recordingSeconds = 0;
      this._stopRecordingTimer();
      this.recordingTimerId = setInterval(() => { this.recordingSeconds++; }, 1000);
      this._startAudioMeter(stream);

      // Track cloné et dédié au recorder : évite toute interférence entre le
      // tap Web Audio (barre de niveau) et MediaRecorder sur le même track
      // (constaté sur certains pilotes/micros Bluetooth Windows → audio muet).
      const recordStream = new MediaStream(stream.getAudioTracks().map(t => t.clone()));

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus' : 'audio/webm';
      this.mediaRecorder = new MediaRecorder(recordStream, { mimeType });

      this.mediaRecorder.ondataavailable = (e: BlobEvent) => {
        if (e.data.size > 0) this.audioChunks.push(e.data);
      };

      this.mediaRecorder.onstop = () => {
        stream.getTracks().forEach(t => t.stop());
        recordStream.getTracks().forEach(t => t.stop());
        this.isListening = false;
        this._stopAudioMeter();
        this._stopRecordingTimer();

        const wasCancelled = this.voiceCancelled;
        const blob = new Blob(this.audioChunks, { type: mimeType });
        this.audioChunks   = [];
        this.mediaRecorder = null;

        if (wasCancelled) return;

        this.isTranscribing = true;
        const lang = navigator.language?.startsWith('ar') ? 'ar'
                   : navigator.language?.startsWith('en') ? 'en' : 'fr';

        this.ariaService.transcribe(blob, lang).subscribe({
          next: (res) => {
            this.isTranscribing = false;
            if (res.text?.trim()) {
              this.userInput = res.text.trim();
              this.focusInput();
            } else {
              alert('Aucune parole détectée. Réessayez.');
            }
          },
          error: (err) => {
            this.isTranscribing = false;
            alert(err?.error?.detail ?? 'Erreur de transcription. Réessayez.');
          }
        });
      };

      this.mediaRecorder.start();
    }).catch(() => {
      alert('Accès au micro refusé. Autorisez le micro dans le navigateur.');
    });
  }

  // ══════════════════════════════════════════
  // THREADS / SESSIONS
  // ══════════════════════════════════════════

  private threadToSession(t: Thread): ChatSession {
    const date = new Date(t.updated_at);
    return {
      id     : t.thread_id,
      title  : t.title,
      preview: t.preview || '',
      date,
      group  : t.is_favorite ? 'favorites' as any : this.computeGroup(date)
    };
  }

  private computeGroup(date: Date): 'today' | 'week' | 'month' | 'older' {
    const now   = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const d     = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diff  = Math.floor((today.getTime() - d.getTime()) / 86400000);
    if (diff === 0) return 'today';
    if (diff <= 7)  return 'week';
    if (diff <= 30) return 'month';
    return 'older';
  }

  loadThreadsFromAPI(): void {
    this.ariaService.getThreads(this.USER_ID, 50).subscribe({
      next: (threads: Thread[]) => {
        this.sessions         = threads.map(t => this.threadToSession(t));
        this.filteredSessions = [...this.sessions];
        this.favoriteIds = new Set(
          threads.filter(t => t.is_favorite).map(t => t.thread_id)
        );
      },
      error: () => { this.sessions = []; this.filteredSessions = []; }
    });
  }

  getGroupedSessions(group: 'favorites' | 'today' | 'week' | 'month'): ChatSession[] {
    if (group === 'favorites') return this.filteredSessions.filter(s => this.favoriteIds.has(s.id));
    return this.filteredSessions.filter(s => s.group === group && !this.favoriteIds.has(s.id));
  }

  filterHistory(): void {
    const q = this.historySearchQuery.toLowerCase().trim();
    this.filteredSessions = q
      ? this.sessions.filter(s =>
          s.title.toLowerCase().includes(q) || s.preview.toLowerCase().includes(q))
      : [...this.sessions];
  }

  clearHistorySearch(): void {
    this.historySearchQuery = '';
    this.filteredSessions   = [...this.sessions];
  }

  startRenameSession(event: Event, session: ChatSession): void {
    event.stopPropagation();
    this.editingSessionId = session.id;
    this.editingTitle     = session.title;
    setTimeout(() => {
      const input = document.getElementById(`rename-input-${session.id}`) as HTMLInputElement;
      if (input) { input.focus(); input.select(); }
    }, 50);
  }

  confirmRename(session: ChatSession): void {
    const newTitle = this.editingTitle.trim();
    if (newTitle && newTitle !== session.title) {
      session.title = newTitle;
      this.ariaService.updateTitle(session.id, newTitle).subscribe();
      this.filteredSessions = [...this.sessions];
    }
    this.editingSessionId = null;
    this.editingTitle     = '';
  }

  cancelRename(): void {
    this.editingSessionId = null;
    this.editingTitle     = '';
  }

  loadSession(session: ChatSession): void {
    this.activeSessionId      = session.id;
    this.currentSessionTitle  = session.title;
    this.currentThreadId      = session.id;
    this.loadedSessionBanner  = session.title;
    this.messages             = [];
    this.shouldScrollToBottom = true;

    this.ariaService.getMessages(session.id).subscribe({
      next: (msgs: MessageHistory[]) => {
        this.messages = msgs.map(m => ({
          id          : this.generateId(),
          messageId   : m.id,
          // Les tokens [NAV:...] sont strippés à l'affichage — pas de carte dans l'historique
          content     : m.role !== 'user' ? this.chatNav.stripNavToken(m.content) : m.content,
          sender      : m.role === 'user' ? 'user' : 'bot',
          timestamp   : new Date(m.created_at),
          feedback    : m.feedback,
          chartConfigs: m.chart_data?.length ? m.chart_data : undefined,
        }));
        this.shouldScrollToBottom = true;
      },
      error: () => {
        this.messages = [{
          id: this.generateId(),
          content: 'Impossible de charger cette conversation.',
          sender: 'bot', timestamp: new Date()
        }];
      }
    });

    if (window.innerWidth <= 768) this.isHistoryOpen = false;
  }

  deleteSession(event: Event, session: ChatSession): void {
    event.stopPropagation();
    if (!confirm(`Supprimer "${session.title}" ?`)) return;

    this.ariaService.deleteThread(session.id).subscribe({
      next: () => {
        this.sessions         = this.sessions.filter(s => s.id !== session.id);
        this.filteredSessions = this.filteredSessions.filter(s => s.id !== session.id);
        if (this.activeSessionId === session.id) {
          this.activeSessionId      = '';
          this.currentSessionTitle  = '';
          this.loadedSessionBanner  = '';
          this.currentThreadId      = null;
          this.messages             = [];
          this.shouldScrollToBottom = true;
        }
      },
      error: () => alert('Erreur lors de la suppression.')
    });
  }

  newConversation(): void {
    this.ariaService.newConversation(this.USER_ID).subscribe({
      next: (res) => {
        this.currentThreadId      = res.thread_id;
        this.activeSessionId      = '';
        this.currentSessionTitle  = '';
        this.loadedSessionBanner  = '';
        this.userInput            = '';
        this.messages             = [];
        this.shouldScrollToBottom = true;
        if (window.innerWidth <= 768) this.isHistoryOpen = false;
        this.focusInput();
      },
      error: () => {
        this.currentThreadId      = null;
        this.activeSessionId      = '';
        this.currentSessionTitle  = '';
        this.messages             = [];
        this.shouldScrollToBottom = true;
        this.focusInput();
      }
    });
  }

  minimizeChat(): void {
    if (this.isDashboardMode) return;
    this.isOpen = false;
    this.isFullscreen = false;
  }

  toggleChat(): void {
    if (this.isDashboardMode) return;
    this.isOpen = !this.isOpen;
    if (this.isOpen) {
      this.unreadCount          = 0;
      this.shouldScrollToBottom = true;
      this.loadThreadsFromAPI();
      this.focusInput();
    } else {
      if (this.isListening) this._stopRecording();
      this.isHistoryOpen = false;
      this.isFullscreen  = false;
    }
  }

  toggleFullscreen(): void {
    if (this.isDashboardMode) return;
    this.isFullscreen = !this.isFullscreen;
    if (this.isFullscreen) this.isHistoryOpen = false;
    this.shouldScrollToBottom = true;
  }

  toggleSearch(): void { this.showSearch = !this.showSearch; }

  toggleHistory(): void {
    this.isHistoryOpen = !this.isHistoryOpen;
    if (this.isHistoryOpen) this.loadThreadsFromAPI();
    this.shouldScrollToBottom = true;
  }

  onKeyDown(event: Event): void {
    const e = event as KeyboardEvent;
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.sendMessage(); }
  }

  // ══════════════════════════════════════════
  // SEND MESSAGE
  // ══════════════════════════════════════════

  sendMessage(input?: string): void {
    const isImageAttached = !!this.attachedFile && this.attachedFileType === 'image';
    if (isImageAttached && !input) { this._sendImageAnalysis(); return; }

    const message = (input || this.buildMessageWithFile()).trim();
    if (!message || this.isTyping) return;

    this.pendingPdf = this.detectPdfIntent(message);
    this.messages.push({ id: this.generateId(), content: message, sender: 'user', timestamp: new Date() });
    this.userInput           = '';
    this.attachedFile        = null;
    this.attachedFilePreview = '';
    this.shouldScrollToBottom = true;
    this.isTyping            = true;
    this.thinkingPhase       = 'off';
    this.streamingMsgId      = null;

    this.ariaService.askStream(message, this.currentThreadId || undefined, this.USER_ID, this.translate.currentLang)
      .pipe(takeUntil(this.stopGeneration$), takeUntil(this.destroy$))
      .subscribe({
        next: (event: StreamEvent) => {
          switch (event.type) {
            case 'thinking':
              this.thinkingPhase = 'thinking';
              this.thinkingLabel = event.data || this.translate.instant('CHATBOT.THINKING');
              break;

            case 'tool':
              this.thinkingPhase = 'tool';
              this.toolLabel     = event.data || this.translate.instant('CHATBOT.SEARCHING');
              break;

            case 'chunk':
              if (!this.streamingMsgId) {
                this.thinkingPhase = 'writing';
                const botMsg: ChatMessage = {
                  id: this.generateId(), content: '',
                  sender: 'bot', timestamp: new Date(), streaming: true
                };
                this.messages.push(botMsg);
                this.streamingMsgId = botMsg.id;
              }
              const msg = this.messages.find(m => m.id === this.streamingMsgId);
              if (msg) { msg.content += event.data; this.shouldScrollToBottom = true; }
              break;

            case 'done':
              const done = this.messages.find(m => m.id === this.streamingMsgId);
              if (done) {
                done.streaming  = false;
                done.messageId  = event.message_id;
                if (event.quick_replies?.length) {
                  done.content     = done.content.replace(/\[QR:[^\]]+\]\s*$/m, '').trimEnd();
                  done.quickReplies = event.quick_replies;
                }
                if (event.chart_data?.length) {
                  done.chartConfigs = event.chart_data;
                }
                // Détection token de navigation [NAV:key]
                const navKey = this.chatNav.parseNavToken(done.content);
                if (navKey) {
                  done.content = this.chatNav.stripNavToken(done.content);
                  const target = this.chatNav.resolveForCurrentUser(navKey);
                  if (target) {
                    done.navCard = { key: navKey, label: target.label, dismissed: false };
                  }
                }
              }
              if (event.thread_id) {
                this.currentThreadId = event.thread_id;
                this.refreshThreadInSidebar(event.thread_id, message);
              }
              if (this.pendingPdf && done) {
                this.triggerPdf(this.pendingPdf, done);
                this.pendingPdf = null;
              }
              this._resetStreamState();
              if (!this.isOpen && !this.isDashboardMode) this.unreadCount++;
              break;

            case 'file':
              const fileMsg = this.messages.find(m => m.id === this.streamingMsgId);
              if (fileMsg && event.file_id && event.filename) {
                fileMsg.csvDownload = {
                  fileId  : event.file_id,
                  filename: event.filename,
                  url     : `${environment.ariaApiUrl}/download/${event.file_id}`,
                };
              }
              break;

            case 'pdf':
              const pdfTargetMsg = this.messages.find(m => m.id === this.streamingMsgId);
              this.triggerPdf(this.parseReportType(event.report_type || 'water:all'), pdfTargetMsg);
              this.pendingPdf = null;
              break;

            case 'pdf_analysis':
              const pdfAMsg = this.messages.find(m => m.id === this.streamingMsgId);
              if (pdfAMsg && event.file_id && event.filename) {
                pdfAMsg.pdfAnalysis = {
                  fileId  : event.file_id,
                  filename: event.filename,
                  url     : `${environment.ariaApiUrl}/download/${event.file_id}`,
                };
              }
              break;

            case 'error':
              this.messages.push({
                id: this.generateId(),
                content: `⚠️ ${event.data || 'Erreur système.'}`,
                sender: 'bot', timestamp: new Date()
              });
              this._resetStreamState();
              break;
          }
        },
        error: (err: Error) => {
          this.messages.push({
            id: this.generateId(), content: `Erreur : ${err.message}`,
            sender: 'bot', timestamp: new Date()
          });
          this._resetStreamState();
        }
      });
  }

  private _resetStreamState(): void {
    const streaming = this.messages.find(m => m.id === this.streamingMsgId);
    if (streaming) streaming.streaming = false;
    this.isTyping          = false;
    this.thinkingPhase     = 'off';
    this.streamingMsgId    = null;
    this.shouldScrollToBottom = true;
  }

  private _sendImageAnalysis(): void {
    const imageFile = this.attachedFile!;
    const question  = this.userInput.trim() || 'Analyse cette image en détail.';
    const imageUrl  = URL.createObjectURL(imageFile);
    const userText  = this.userInput.trim();

    this.messages.push({
      id: this.generateId(),
      content : userText,
      imageUrl,
      sender  : 'user',
      timestamp: new Date()
    });
    this.userInput            = '';
    this.attachedFile         = null;
    this.attachedFilePreview  = '';
    this.shouldScrollToBottom = true;
    this.isTyping             = true;

    this.ariaService.analyzeImage(imageFile, question)
      .pipe(takeUntil(this.stopGeneration$))
      .subscribe({
        next: (res: VisionResponse) => {
          this.messages.push({
            id: this.generateId(),
            content: res.analysis,
            sender: 'bot', timestamp: new Date()
          });
          this.isTyping             = false;
          this.shouldScrollToBottom = true;
          if (!this.isOpen && !this.isDashboardMode) this.unreadCount++;
        },
        error: (err: any) => {
          const detail = err?.error?.detail ?? "Erreur d'analyse d'image.";
          this.messages.push({
            id: this.generateId(), content: `Erreur : ${detail}`,
            sender: 'bot', timestamp: new Date()
          });
          this.isTyping             = false;
          this.shouldScrollToBottom = true;
        },
        complete: () => URL.revokeObjectURL(imageUrl),
      });
  }

  private refreshThreadInSidebar(threadId: string, firstMessage: string): void {
    const existing = this.sessions.find(s => s.id === threadId);
    const now      = new Date();
    if (existing) {
      existing.preview = firstMessage.substring(0, 60);
      existing.date    = now;
      existing.group   = this.computeGroup(now);
      this.sessions = [existing, ...this.sessions.filter(s => s.id !== threadId)];
    } else {
      const title = firstMessage.length > 40 ? firstMessage.substring(0, 40) + '…' : firstMessage;
      this.sessions = [{
        id: threadId, title, preview: firstMessage.substring(0, 60), date: now, group: 'today'
      }, ...this.sessions];
      this.activeSessionId     = threadId;
      this.currentSessionTitle = title;
    }
    this.filteredSessions = [...this.sessions];
  }

  stopMessage(): void {
    this.stopGeneration$.next();
    const streaming = this.messages.find(m => m.id === this.streamingMsgId);
    if (streaming) {
      streaming.streaming = false;
      if (!streaming.content) streaming.content = 'Génération arrêtée.';
    } else {
      this.messages.push({
        id: this.generateId(), content: 'Génération arrêtée.',
        sender: 'bot', timestamp: new Date()
      });
    }
    this.isTyping          = false;
    this.thinkingPhase     = 'off';
    this.streamingMsgId    = null;
    this.shouldScrollToBottom = true;
  }

  onQuickReply(msg: ChatMessage, value: string): void {
    msg.quickReplies = undefined;
    this.sendMessage(value);
  }

  // ══════════════════════════════════════════
  // FICHIERS JOINTS
  // ══════════════════════════════════════════

  copiedId  : string | null = null;
  openMenuId: string | null = null;
  favoriteIds: Set<string>  = new Set();

  attachedFile        : File | null = null;
  attachedFilePreview = '';
  attachedFileType    : 'image' | 'pdf' | 'text' | 'other' = 'other';

  readonly ACCEPTED_TYPES = '.pdf,.txt,.csv,.md,.json,.png,.jpg,.jpeg,.gif,.webp';
  readonly MAX_FILE_SIZE  = 10 * 1024 * 1024;

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file  = input.files?.[0];
    if (!file) return;
    if (file.size > this.MAX_FILE_SIZE) {
      alert('Fichier trop volumineux. Maximum : 10 MB');
      input.value = '';
      return;
    }
    this.attachedFile = file;
    const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
    if (['png','jpg','jpeg','gif','webp'].includes(ext)) {
      this.attachedFileType = 'image';
      const reader = new FileReader();
      reader.onload = e => this.attachedFilePreview = e.target?.result as string;
      reader.readAsDataURL(file);
    } else if (ext === 'pdf') {
      this.attachedFileType = 'pdf'; this.attachedFilePreview = '';
    } else if (['txt','csv','md','json'].includes(ext)) {
      this.attachedFileType = 'text';
      const reader = new FileReader();
      reader.onload = e => this.attachedFilePreview = (e.target?.result as string).substring(0, 500);
      reader.readAsText(file);
    } else {
      this.attachedFileType = 'other'; this.attachedFilePreview = '';
    }
    input.value = '';
  }

  removeAttachment(): void { this.attachedFile = null; this.attachedFilePreview = ''; }

  onPaste(event: ClipboardEvent): void {
    if (this.isTyping) return;
    const items = event.clipboardData?.items;
    if (!items) return;
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        event.preventDefault();
        const blob = item.getAsFile();
        if (!blob) return;
        if (blob.size > this.MAX_FILE_SIZE) {
          alert('Image trop volumineuse. Maximum : 10 MB');
          return;
        }
        const ext = item.type.split('/')[1]?.replace('jpeg', 'jpg') || 'png';
        this.attachedFile     = new File([blob], `image-collée.${ext}`, { type: item.type });
        this.attachedFileType = 'image';
        const reader = new FileReader();
        reader.onload = e => this.attachedFilePreview = e.target?.result as string;
        reader.readAsDataURL(this.attachedFile);
        return;
      }
    }
  }

  private buildMessageWithFile(): string {
    if (!this.attachedFile) return this.userInput.trim();
    const name    = this.attachedFile.name;
    const size    = (this.attachedFile.size / 1024).toFixed(1);
    const preview = this.attachedFilePreview
      ? `\n\n**Contenu du fichier (extrait) :**\n\`\`\`\n${this.attachedFilePreview}\n\`\`\``
      : '';
    const text = this.userInput.trim();
    return `📎 **Fichier joint : ${name}** (${size} KB)${preview}${text ? '\n\n' + text : ''}`;
  }

  // ══════════════════════════════════════════
  // MENUS / ACTIONS
  // ══════════════════════════════════════════

  toggleMenu(event: Event, sessionId: string): void {
    event.stopPropagation();
    this.openMenuId = this.openMenuId === sessionId ? null : sessionId;
  }

  closeMenu(): void { this.openMenuId = null; }

  toggleFavorite(event: Event, session: ChatSession): void {
    event.stopPropagation();
    this.openMenuId = null;
    this.ariaService.toggleFavoriteAPI(session.id).subscribe({
      next: (res) => {
        if (res.is_favorite) {
          this.favoriteIds.add(session.id);
          session.group = 'favorites' as any;
        } else {
          this.favoriteIds.delete(session.id);
          session.group = this.computeGroup(session.date);
        }
        this.filteredSessions = [...this.sessions];
      }
    });
  }

  isFavorite(sessionId: string): boolean { return this.favoriteIds.has(sessionId); }

  renameFromMenu(event: Event, session: ChatSession): void {
    event.stopPropagation();
    this.openMenuId = null;
    this.startRenameSession(event, session);
  }

  deleteFromMenu(event: Event, session: ChatSession): void {
    event.stopPropagation();
    this.openMenuId = null;
    this.deleteSession(event, session);
  }

  editMessage(msg: ChatMessage): void { this.userInput = msg.content; this.focusInput(); }

  giveFeedback(msg: ChatMessage, vote: 'up' | 'down'): void {
    if (!msg.messageId || !this.currentThreadId) return;
    const newVote = msg.feedback === vote ? null : vote;
    msg.feedback  = newVote;
    if (newVote) {
      this.ariaService.postFeedback(
        msg.messageId, this.currentThreadId, newVote, this.USER_ID
      ).subscribe();
    }
  }

  copyMessage(msg: ChatMessage): void {
    navigator.clipboard.writeText(msg.content).then(() => {
      this.copiedId = msg.id;
      setTimeout(() => this.copiedId = null, 2000);
    });
  }

  retryMessage(msg: ChatMessage): void {
    if (this.isTyping) return;
    this.sendMessage(msg.content);
  }

  downloadWaterReport(): void {
    if (this.isPdfGenerating) return;
    this.isPdfGenerating = true;
    this.pdfReport.generateWaterReport()
      .catch(() => this.notif.push({ severity: 'high', title: 'Rapport PDF', message: 'Erreur lors de la génération du rapport.' }))
      .finally(() => { this.isPdfGenerating = false; });
  }

  private detectPdfIntent(text: string): ReportRequest | null {
    const t = text.toLowerCase()
      .replace(/[éèêë]/g, 'e').replace(/[àâä]/g, 'a')
      .replace(/[îï]/g, 'i').replace(/[ôö]/g, 'o')
      .replace(/[ûü]/g, 'u').replace(/ç/g, 'c');

    // Déclenche uniquement si l'utilisateur demande explicitement un PDF/rapport
    const hasExplicitPdf     = /\bpdf\b/.test(t);
    const hasRapportWithVerb = /rapport/.test(t) && /genere|generer|telecharger|fais|cree|exporte|produis/.test(t);
    if (!hasExplicitPdf && !hasRapportWithVerb) return null;

    // Si la demande porte sur l'analyse ARIA en cours (graphiques, résultats, conversation),
    // le backend génère le PDF — on n'interfère pas avec jsPDF ici.
    if (/analyse|graphique|graphe|resultat|donnee|conversation|cette\s+analyse|ce\s+rapport/.test(t)) return null;

    let domain: ReportDomain = 'water';
    if      (/\bgaz\b|gas\b/.test(t))                            domain = 'gaz';
    else if (/electri|energie|kwh?\b/.test(t))                   domain = 'electricity';
    else if (/carburant|fuel|essence|gasoil|vehicule/.test(t))   domain = 'fuel';

    let filter: ReportFilter = 'all';
    if      (/inactif|inactive|hors.ligne|offline|eteint|arrete|deconnecte/.test(t)) filter = 'inactive';
    else if (/\bactif\b|\bactive\b|en.ligne|online|\bok\b|fonctionn/.test(t))        filter = 'active';
    else if (/fuite|leak/.test(t))                                                    filter = 'leak';
    else if (/fraude|fraud/.test(t))                                                  filter = 'fraud';
    else if (/batterie|battery|faible.bat/.test(t))                                   filter = 'low_battery';
    else if (/alerte|en.alerte/.test(t))                                              filter = 'alert';

    return { domain, filter, label: `${DOM_LABEL[domain]} — ${FLT_LABEL[filter]}` };
  }

  private parseReportType(raw: string): ReportRequest {
    const DOMAINS: ReportDomain[] = ['water', 'gaz', 'electricity', 'fuel'];
    const FILTERS: ReportFilter[] = ['all', 'active', 'inactive', 'alert', 'leak', 'fraud', 'low_battery'];
    const [d, f] = raw.split(':');
    const domain = DOMAINS.includes(d as ReportDomain) ? d as ReportDomain : 'water';
    const filter = FILTERS.includes(f as ReportFilter) ? f as ReportFilter : 'all';
    return { domain, filter, label: `${DOM_LABEL[domain]} — ${FLT_LABEL[filter]}` };
  }

  triggerPdf(req: ReportRequest, targetMsg?: ChatMessage): void {
    const now = new Date();
    const p   = (n: number) => String(n).padStart(2, '0');
    const filename = `rapport-${req.domain}-${req.filter}_${now.getFullYear()}-${p(now.getMonth()+1)}-${p(now.getDate())}.pdf`;
    if (targetMsg) {
      targetMsg.pdfDownload = { request: req, filename, generatedAt: now };
    }
    this.pdfReport.generateReport(req)
      .catch(() => this.notif.push({ severity: 'high', title: 'Rapport PDF', message: 'Erreur lors de la génération du rapport.' }));
  }

  trackByMessage   (_: number, m: ChatMessage): string  { return m.id; }
  trackBySuggestion(_: number, s: string):      string  { return s; }
  trackBySession   (_: number, s: ChatSession): string  { return s.id; }

  // ══════════════════════════════════════════
  // FORMULAIRES DANS LE CHAT
  // ══════════════════════════════════════════

  /** Injecte un message-bulle contenant un formulaire dans la conversation */
  private pushForm(introText: string, config: ChatFormConfig): void {
    this.messages.push({
      id:         this.generateId(),
      content:    introText,
      sender:     'bot',
      timestamp:  new Date(),
      formConfig: config
    });
    this.shouldScrollToBottom = true;
  }

  openUserForm(): void {
    this.pushForm(this.translate.instant('CHATBOT.FORMS.USER_FORM_INTRO'), {
      fields:         USER_FORM_FIELDS,
      submitLabel:    this.translate.instant('CHATBOT.FORMS.USER_FORM_SUBMIT'),
      successMessage: this.translate.instant('CHATBOT.FORMS.USER_CREATED'),
      submitFn:       (data) => this.userService.create(data)
    });
  }

  openDeviceForm(): void {
    const isSuperAdmin = this.auth.getCurrentRole() === 'SUPER_ADMIN';
    const fields = DEVICE_FORM_FIELDS.map(field => {
      if (field.key !== 'type') return field;
      const allowedOptions = (field.options ?? []).filter(opt =>
        isSuperAdmin || this.auth.hasModule(DEVICE_TYPE_MODULE_MAP[opt.value as number])
      );
      return { ...field, options: allowedOptions };
    });
    this.pushForm(this.translate.instant('CHATBOT.FORMS.DEVICE_FORM_INTRO'), {
      fields,
      submitLabel:    this.translate.instant('CHATBOT.FORMS.DEVICE_FORM_SUBMIT'),
      successMessage: this.translate.instant('CHATBOT.FORMS.DEVICE_CREATED'),
      submitFn:       (data) => this.deviceSvc.create(data)
    });
  }

  openAlertForm(): void {
    this.pushForm(this.translate.instant('CHATBOT.FORMS.ALERT_FORM_INTRO'), {
      fields:         ALERT_RULE_FIELDS,
      submitLabel:    this.translate.instant('CHATBOT.FORMS.ALERT_FORM_SUBMIT'),
      successMessage: this.translate.instant('CHATBOT.FORMS.ALERT_CREATED'),
      submitFn:       (data) => {
        this.notif.addRule(data);
        return new Observable(obs => { obs.next(data); obs.complete(); });
      }
    });
  }

  /** Appelé quand le formulaire dans le chat est soumis avec succès */
  onFormInChatSubmit(msg: ChatMessage): void {
    msg.formConfig = undefined;
    msg.content    = '✅ Formulaire soumis avec succès.';
    this.shouldScrollToBottom = true;
  }

  /** Appelé quand l'utilisateur annule le formulaire dans le chat */
  onFormInChatCancel(msg: ChatMessage): void {
    msg.formConfig = undefined;
    msg.content    = 'Formulaire annulé.';
  }

  // ══════════════════════════════════════════
  // NAVIGATION DEPUIS LE CHAT
  // ══════════════════════════════════════════

  /**
   * Déclenché par le clic sur la carte de navigation.
   * Re-vérifie les permissions au moment du clic (pas seulement à l'affichage).
   */
  navigateFromCard(msg: ChatMessage): void {
    if (!msg.navCard || msg.navCard.dismissed) return;

    // Double vérification des droits au moment de l'action
    const target = this.chatNav.resolveForCurrentUser(msg.navCard.key);
    if (!target) {
      msg.navCard.dismissed = true;
      return;
    }

    msg.navCard.dismissed = true;
    const navigated = this.chatNav.navigate(target);

    // Ferme le chatbot flottant après navigation (pas en mode dashboard)
    if (navigated && !this.isDashboardMode) {
      this.isOpen = false;
    }
  }
}