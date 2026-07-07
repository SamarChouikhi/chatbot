import { TestBed } from '@angular/core/testing';
import { JwtService } from './jwt.service';

/**
 * Génère un JWT valide (ou expiré) côté test sans dépendance réseau.
 * La signature est factice — JwtService ne la vérifie pas côté client.
 */
function makeToken(payload: object): string {
  const header  = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
  const body    = btoa(JSON.stringify(payload))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
  return `${header}.${body}.fakesignature`;
}

const NOW_SEC = () => Math.floor(Date.now() / 1000);

describe('JwtService', () => {
  let service: JwtService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [JwtService] });
    service = TestBed.inject(JwtService);
  });

  // ── decode() ────────────────────────────────────────────────────────────────

  describe('decode()', () => {
    it('retourne les claims pour un token valide', () => {
      const token  = makeToken({ sub: 'alice', role: 'ADMIN', login: 'alice', exp: NOW_SEC() + 3600, iat: NOW_SEC() });
      const claims = service.decode(token);
      expect(claims).not.toBeNull();
      expect(claims!.sub).toBe('alice');
      expect(claims!.role).toBe('ADMIN');
    });

    it('retourne null pour un token malformé', () => {
      expect(service.decode('not.a.token')).toBeNull();
    });

    it('retourne null pour une chaîne vide', () => {
      expect(service.decode('')).toBeNull();
    });

    it('retourne null quand le payload n\'est pas du JSON valide', () => {
      const token = `header.${btoa('not-json')}.sig`;
      expect(service.decode(token)).toBeNull();
    });

    it('retourne null quand il manque le segment payload', () => {
      expect(service.decode('onlyone')).toBeNull();
    });

    it('décode les caractères base64url (_ et -)', () => {
      const payload = { sub: 'user+test', role: 'EMPLOYEE', login: 'user', exp: NOW_SEC() + 3600, iat: NOW_SEC() };
      const token   = makeToken(payload);
      const claims  = service.decode(token);
      expect(claims).not.toBeNull();
    });
  });

  // ── isExpired() ──────────────────────────────────────────────────────────────

  describe('isExpired()', () => {
    it('retourne false pour un token encore valide', () => {
      const token = makeToken({ exp: NOW_SEC() + 3600, iat: NOW_SEC() });
      expect(service.isExpired(token)).toBeFalse();
    });

    it('retourne true pour un token expiré', () => {
      const token = makeToken({ exp: NOW_SEC() - 60, iat: NOW_SEC() - 3660 });
      expect(service.isExpired(token)).toBeTrue();
    });

    it('retourne true pour un token malformé', () => {
      expect(service.isExpired('bad.token.here')).toBeTrue();
    });

    it('retourne true pour une chaîne vide', () => {
      expect(service.isExpired('')).toBeTrue();
    });
  });

  // ── expiresIn() ───────────────────────────────────────────────────────────────

  describe('expiresIn()', () => {
    it('retourne un nombre positif pour un token valide', () => {
      const token = makeToken({ exp: NOW_SEC() + 3600, iat: NOW_SEC() });
      expect(service.expiresIn(token)).toBeGreaterThan(0);
    });

    it('retourne un nombre négatif pour un token expiré', () => {
      const token = makeToken({ exp: NOW_SEC() - 60, iat: NOW_SEC() - 3660 });
      expect(service.expiresIn(token)).toBeLessThan(0);
    });

    it('retourne -1 pour un token malformé', () => {
      expect(service.expiresIn('bad')).toBe(-1);
    });

    it('est proche de la durée passée en paramètre', () => {
      const duration = 1800; // 30 min
      const token    = makeToken({ exp: NOW_SEC() + duration, iat: NOW_SEC() });
      const remaining = service.expiresIn(token);
      expect(remaining).toBeGreaterThan(duration - 2);
      expect(remaining).toBeLessThanOrEqual(duration);
    });
  });

  // ── getRole() ────────────────────────────────────────────────────────────────

  describe('getRole()', () => {
    it('retourne le rôle du token', () => {
      const token = makeToken({ role: 'SUPER_ADMIN', exp: NOW_SEC() + 3600, login: 'bob', iat: NOW_SEC() });
      expect(service.getRole(token)).toBe('SUPER_ADMIN');
    });

    it('retourne null pour un token sans role', () => {
      const token = makeToken({ sub: 'bob', exp: NOW_SEC() + 3600, iat: NOW_SEC() });
      expect(service.getRole(token)).toBeNull();
    });

    it('retourne null pour un token malformé', () => {
      expect(service.getRole('bad')).toBeNull();
    });
  });

  // ── getLogin() ────────────────────────────────────────────────────────────────

  describe('getLogin()', () => {
    it('retourne le login si présent dans les claims', () => {
      const token = makeToken({ login: 'alice', sub: 'sub-val', exp: NOW_SEC() + 3600, iat: NOW_SEC() });
      expect(service.getLogin(token)).toBe('alice');
    });

    it('retourne sub si login absent', () => {
      const token = makeToken({ sub: 'alice', exp: NOW_SEC() + 3600, iat: NOW_SEC() });
      expect(service.getLogin(token)).toBe('alice');
    });

    it('retourne null pour un token malformé', () => {
      expect(service.getLogin('bad')).toBeNull();
    });
  });

  // ── isExpiringSoon() ──────────────────────────────────────────────────────────

  describe('isExpiringSoon()', () => {
    it('retourne true si expiration < threshold (défaut 300s)', () => {
      const token = makeToken({ exp: NOW_SEC() + 200, iat: NOW_SEC() });
      expect(service.isExpiringSoon(token)).toBeTrue();
    });

    it('retourne false si expiration > threshold', () => {
      const token = makeToken({ exp: NOW_SEC() + 3600, iat: NOW_SEC() });
      expect(service.isExpiringSoon(token)).toBeFalse();
    });

    it('retourne false pour un token déjà expiré', () => {
      const token = makeToken({ exp: NOW_SEC() - 60, iat: NOW_SEC() - 3660 });
      expect(service.isExpiringSoon(token)).toBeFalse();
    });

    it('respecte un seuil personnalisé', () => {
      const token = makeToken({ exp: NOW_SEC() + 50, iat: NOW_SEC() });
      expect(service.isExpiringSoon(token, 100)).toBeTrue();
      expect(service.isExpiringSoon(token, 30)).toBeFalse();
    });
  });
});
