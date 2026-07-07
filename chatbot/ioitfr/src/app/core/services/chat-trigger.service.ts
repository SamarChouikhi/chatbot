import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class ChatTriggerService {
  private readonly _open$ = new Subject<string>();

  readonly open$ = this._open$.asObservable();

  open(question: string): void {
    this._open$.next(question);
  }
}
