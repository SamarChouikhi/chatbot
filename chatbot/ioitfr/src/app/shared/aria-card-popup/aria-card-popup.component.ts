import {
  Component, Input, Output, EventEmitter,
  OnChanges, OnDestroy, SimpleChanges,
  ViewChild, ElementRef, AfterViewChecked,
} from '@angular/core';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { TranslateService } from '@ngx-translate/core';
import { AriaService, StreamEvent } from '../../services/aria.service';

export interface AriaCardContext {
  domain: 'electricity' | 'water' | 'gaz' | 'fuel' | 'co2';
  title: string;
  icon: string;
  accentColor: string;
  mainValue: string;
  unit: string;
  trend: string;
  trendPositive: boolean;
  metrics: { label: string; value: string }[];
  criticals: number;
  period: number;
  quickReplies: string[];
}

interface PopupMessage {
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
}

@Component({
  selector: 'app-aria-card-popup',
  templateUrl: './aria-card-popup.component.html',
  styleUrls: ['./aria-card-popup.component.scss'],
})
export class AriaCardPopupComponent implements OnChanges, OnDestroy, AfterViewChecked {
  @Input()  context!: AriaCardContext;
  @Input()  isOpen = false;
  @Output() closed = new EventEmitter<void>();

  @ViewChild('msgScroll') private msgScroll!: ElementRef<HTMLElement>;

  messages: PopupMessage[] = [];
  inputText = '';
  isStreaming = false;
  isInitialLoad = true;

  private threadId: string | undefined;
  private destroy$ = new Subject<void>();
  private stop$    = new Subject<void>();
  private doScroll = false;

  constructor(private aria: AriaService, private translate: TranslateService) {}

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['isOpen']?.currentValue === true && this.context) {
      this.messages      = [];
      this.threadId      = undefined;
      this.isInitialLoad = true;
      this._autoAnalyze();
    }
  }

  ngAfterViewChecked(): void {
    if (this.doScroll) {
      this._scrollBottom();
      this.doScroll = false;
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  close(): void {
    this.stop$.next();
    this.closed.emit();
  }

  onBackdropClick(e: MouseEvent): void {
    if ((e.target as HTMLElement).classList.contains('popup-overlay')) {
      this.close();
    }
  }

  sendQuickReply(text: string): void {
    this.isInitialLoad = false;
    this._sendMessage(text);
  }

  onInputKeydown(e: KeyboardEvent): void {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      this._submitInput();
    }
  }

  submitInput(): void {
    this._submitInput();
  }

  get showQuickReplies(): boolean {
    return this.isInitialLoad && !this.isStreaming && this.messages.length > 0 && !this.messages[this.messages.length - 1]?.streaming;
  }

  private _submitInput(): void {
    const q = this.inputText.trim();
    if (!q || this.isStreaming) return;
    this.inputText     = '';
    this.isInitialLoad = false;
    this._sendMessage(q);
  }

  private _autoAnalyze(): void {
    this._stream(this._buildContextPrompt());
  }

  private _sendMessage(question: string): void {
    this.messages.push({ role: 'user', content: question });
    this.doScroll = true;
    this._stream(question);
  }

  private _stream(question: string): void {
    this.isStreaming = true;
    const userId = this.aria.getCurrentUserId();
    const botMsg: PopupMessage = { role: 'assistant', content: '', streaming: true };
    this.messages.push(botMsg);
    this.doScroll = true;

    this.aria.askStream(question, this.threadId, userId, this.translate.currentLang)
      .pipe(takeUntil(this.destroy$), takeUntil(this.stop$))
      .subscribe({
        next: (event: StreamEvent) => {
          if (event.type === 'chunk' && event.data) {
            botMsg.content += event.data;
            this.doScroll   = true;
          }
          if (event.type === 'done') {
            botMsg.streaming  = false;
            this.isStreaming  = false;
            if (event.thread_id) this.threadId = event.thread_id;
            this.doScroll = true;
          }
        },
        error: (err: Error) => {
          botMsg.content    = err.message || 'Erreur de connexion à ARIA.';
          botMsg.streaming  = false;
          this.isStreaming  = false;
          this.doScroll     = true;
        },
      });
  }

  private _buildContextPrompt(): string {
    const c           = this.context;
    const metricsStr  = c.metrics.map(m => `${m.label} : ${m.value}`).join(' | ');
    const critStr     = c.criticals > 0 ? ` | ${c.criticals} alerte(s) critique(s)` : '';
    return `Interprète ces indicateurs de tableau de bord (données déjà calculées) :
Domaine : ${c.title} | Période : ${c.period} derniers jours
Valeur principale : ${c.mainValue} ${c.unit} (tendance : ${c.trend})
${metricsStr}${critStr}
En 2-3 lignes, dis-moi si c'est normal, préoccupant ou excellent. Sois direct et précis.`;
  }

  private _scrollBottom(): void {
    const el = this.msgScroll?.nativeElement;
    if (el) el.scrollTop = el.scrollHeight;
  }
}
