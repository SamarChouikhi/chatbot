import { Injectable } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../../services/auth.service';

// ── Types publics ────────────────────────────────────────────────────────────

export type NavKey =
  | 'electricity' | 'water' | 'gaz' | 'fuel'
  | 'alerts' | 'devices' | 'dashboard' | 'users' | 'roles';

export interface NavTarget {
  readonly path:           string;   // route Angular interne — hardcodée ici uniquement
  readonly label:          string;
  readonly requiredModule: string | null;  // null = accès admin uniquement
  readonly adminOnly:      boolean;
}

export interface NavCard {
  key:       NavKey;
  label:     string;
  dismissed: boolean;
}

// ── Whitelist figée — seule source de vérité pour les routes navigables ─────
//
// RÈGLE : aucune route ne peut être ajoutée au runtime.
// Le LLM ne fournit jamais de path, seulement une clé parmi celles-ci.

const NAV_MAP: Readonly<Record<NavKey, NavTarget>> = Object.freeze({
  electricity: { path: '/electricity', label: 'Électricité',    requiredModule: 'énergie électrique',   adminOnly: false },
  water:       { path: '/water',       label: 'Eau',             requiredModule: 'eau',                  adminOnly: false },
  gaz:         { path: '/gaz',         label: 'Gaz',             requiredModule: 'gaz',                  adminOnly: false },
  fuel:        { path: '/fuel',        label: 'Carburant',       requiredModule: 'carburant',            adminOnly: false },
  alerts:      { path: '/alerts',      label: 'Alertes',         requiredModule: 'alertes',              adminOnly: false },
  devices:     { path: '/device',      label: 'Équipements',     requiredModule: 'équipements/capteurs', adminOnly: false },
  dashboard:   { path: '/dashboard',   label: 'Dashboard',       requiredModule: 'dashboard',            adminOnly: false },
  users:       { path: '/users',       label: 'Utilisateurs',    requiredModule: null,                   adminOnly: true  },
  roles:       { path: '/roles',       label: 'Rôles',           requiredModule: null,                   adminOnly: true  },
});

// Regex stricte : uniquement lettres minuscules et underscores.
// Toute autre forme (chiffres, majuscules, /, ..) est rejetée.
const TOKEN_RE = /\[NAV:([a-z_]+)\]/;

// ── Service ──────────────────────────────────────────────────────────────────

@Injectable({ providedIn: 'root' })
export class ChatNavService {

  constructor(
    private router: Router,
    private auth:   AuthService,
  ) {}

  /**
   * Extrait la clé de navigation d'un texte produit par l'IA.
   * Retourne null si le token est absent, malformé ou non whitelisté.
   * N'émet jamais d'exception — une erreur d'analyse = null.
   */
  parseNavToken(text: string): NavKey | null {
    try {
      const match = text.match(TOKEN_RE);
      if (!match) return null;
      const raw = match[1];
      return this.isValidKey(raw) ? raw : null;
    } catch {
      return null;
    }
  }

  /**
   * Supprime le token [NAV:...] du texte avant affichage.
   */
  stripNavToken(text: string): string {
    return text.replace(/\s*\[NAV:[a-z_]+\]\s*/g, ' ').trim();
  }

  /**
   * Résout la cible de navigation pour l'utilisateur courant.
   *
   * Retourne null si :
   *  - la clé est inconnue (ne figure pas dans le whitelist)
   *  - la route est admin-only et l'utilisateur ne l'est pas
   *  - le module requis n'est pas dans les modules autorisés de l'utilisateur
   *
   * Ce double contrôle (parsing + résolution) garantit qu'une clé valide
   * mais non autorisée n'est jamais présentée à l'utilisateur.
   */
  resolveForCurrentUser(key: NavKey): NavTarget | null {
    if (!this.isValidKey(key)) return null;

    const target = NAV_MAP[key];
    const role   = this.auth.getCurrentRole();

    if (target.adminOnly) {
      return (role === 'SUPER_ADMIN' || role === 'ADMIN') ? target : null;
    }

    if (target.requiredModule !== null && !this.auth.hasModule(target.requiredModule)) {
      return null;
    }

    return target;
  }

  /**
   * Exécute la navigation vers une cible résolue.
   *
   * Vérifications finales (défense en profondeur) :
   *  - le path doit commencer par /
   *  - pas de traversal (..)
   *  - pas de protocole (://)
   * Si l'une d'elles échoue le path est rejeté sans lever d'exception.
   */
  navigate(target: NavTarget): boolean {
    const p = target.path;
    if (!p.startsWith('/') || p.includes('..') || p.includes('://')) {
      return false;
    }
    this.router.navigate([p]);
    return true;
  }

  private isValidKey(key: string): key is NavKey {
    return Object.prototype.hasOwnProperty.call(NAV_MAP, key);
  }
}
