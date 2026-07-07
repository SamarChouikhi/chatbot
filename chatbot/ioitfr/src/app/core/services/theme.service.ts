import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class ThemeService {

  private readonly LS_KEY = 'app-theme';
  private _dark = new BehaviorSubject<boolean>(true);

  readonly isDark$ = this._dark.asObservable();

  get isDark(): boolean { return this._dark.value; }

  constructor() {
    const saved = localStorage.getItem(this.LS_KEY);
    const dark  = saved !== null ? saved === 'dark' : true;
    this._dark.next(dark);
    this.apply(dark);
  }

  toggle(): void {
    const next = !this._dark.value;
    this._dark.next(next);
    localStorage.setItem(this.LS_KEY, next ? 'dark' : 'light');
    this.apply(next);
  }

  setDark(dark: boolean): void {
    this._dark.next(dark);
    localStorage.setItem(this.LS_KEY, dark ? 'dark' : 'light');
    this.apply(dark);
  }

  private apply(dark: boolean): void {
    const html = document.documentElement;
    if (dark) {
      html.classList.remove('light-theme');
    } else {
      html.classList.add('light-theme');
    }
  }
}
