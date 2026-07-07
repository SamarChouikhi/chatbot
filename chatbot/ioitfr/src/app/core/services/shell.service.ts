import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export interface ShellState {
  elecCritical:  number;
  waterLeaks:    number;
  gazLeaks:      number;
  totalAlerts:   number;
  criticalCount: number;
}

const INITIAL: ShellState = {
  elecCritical: 0, waterLeaks: 0, gazLeaks: 0, totalAlerts: 0, criticalCount: 0
};

@Injectable({ providedIn: 'root' })
export class ShellService {
  private _state$ = new BehaviorSubject<ShellState>(INITIAL);
  readonly state$ = this._state$.asObservable();

  update(patch: Partial<ShellState>): void {
    this._state$.next({ ...this._state$.value, ...patch });
  }
}
