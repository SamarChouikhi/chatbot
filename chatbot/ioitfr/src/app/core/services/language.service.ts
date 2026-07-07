import { Injectable } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';

export type AppLang = 'fr' | 'en' | 'ar';

const STORAGE_KEY = 'app_lang';
const DEFAULT_LANG: AppLang = 'fr';

@Injectable({ providedIn: 'root' })
export class LanguageService {

  readonly langs: AppLang[] = ['fr', 'en', 'ar'];

  constructor(private translate: TranslateService) {}

  init(): void {
    this.translate.addLangs(this.langs);
    this.translate.setDefaultLang(DEFAULT_LANG);
    const saved = localStorage.getItem(STORAGE_KEY) as AppLang | null;
    const lang: AppLang = this.langs.includes(saved as AppLang) ? (saved as AppLang) : DEFAULT_LANG;
    this.use(lang);
  }

  use(lang: AppLang): void {
    this.translate.use(lang);
    localStorage.setItem(STORAGE_KEY, lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  }

  get current(): AppLang {
    return (this.translate.currentLang as AppLang) ?? DEFAULT_LANG;
  }

  get isRtl(): boolean {
    return this.current === 'ar';
  }
}
