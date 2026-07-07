import { Injectable } from '@angular/core';

export interface JwtClaims {
  sub        : string;
  groups    ?: string[];
  role       : string;
  login      : string;
  userId     : string;
  loginPere ?: string;
  exp        : number;
  iat        : number;
}

@Injectable({ providedIn: 'root' })
export class JwtService {

  /** Décode un JWT sans vérification de signature (côté client). */
  decode(token: string): JwtClaims | null {
    try {
      const payload = token.split('.')[1];
      if (!payload) return null;
      let b64 = payload.replace(/-/g, '+').replace(/_/g, '/');
      b64 += '='.repeat((4 - b64.length % 4) % 4);
      const decoded = atob(b64);
      return JSON.parse(decoded) as JwtClaims;
    } catch {
      return null;
    }
  }

  /** Retourne true si le token est expiré ou invalide. */
  isExpired(token: string): boolean {
    const claims = this.decode(token);
    if (!claims) return true;
    return Date.now() >= claims.exp * 1000;
  }

  /** Secondes restantes avant expiration. Négatif = déjà expiré. */
  expiresIn(token: string): number {
    const claims = this.decode(token);
    if (!claims) return -1;
    return claims.exp - Math.floor(Date.now() / 1000);
  }

  /** Retourne le rôle contenu dans le token. */
  getRole(token: string): string | null {
    return this.decode(token)?.role ?? null;
  }

  /** Retourne le login/subject contenu dans le token. */
  getLogin(token: string): string | null {
    const claims = this.decode(token);
    return claims?.login ?? claims?.sub ?? null;
  }

  /** Retourne true si le token expire dans moins de `thresholdSeconds` secondes. */
  isExpiringSoon(token: string, thresholdSeconds = 300): boolean {
    const remaining = this.expiresIn(token);
    return remaining > 0 && remaining < thresholdSeconds;
  }
}
