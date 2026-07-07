import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { Router } from '@angular/router';
import { skip } from 'rxjs/operators';
import { AuthService } from './auth.service';
import { JwtService } from '../core/services/jwt.service';

/** Helper : encode un payload en JWT factice. */
function makeToken(payload: object): string {
  const b64 = (obj: object) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
  return `${b64({ alg: 'HS256' })}.${b64(payload)}.sig`;
}

const NOW_SEC = () => Math.floor(Date.now() / 1000);

describe('AuthService', () => {
  let service: AuthService;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule, RouterTestingModule],
      providers: [AuthService, JwtService],
    });
    localStorage.clear();
    sessionStorage.clear();
    service = TestBed.inject(AuthService);
    router  = TestBed.inject(Router);
    // Empêche router.navigate(['/login']) de lever NG04002 (route non enregistrée)
    spyOn(router, 'navigate').and.returnValue(Promise.resolve(true));
  });

  afterEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('devrait être créé', () => {
    expect(service).toBeTruthy();
  });

  // ── isAuthenticated() ──────────────────────────────────────────────────────

  describe('isAuthenticated()', () => {
    it('retourne false si aucun token', () => {
      expect(service.isAuthenticated()).toBeFalse();
    });

    it('retourne false si le token est expiré', () => {
      const token = makeToken({ exp: NOW_SEC() - 60, iat: NOW_SEC() - 3660 });
      localStorage.setItem('access_token', token);
      expect(service.isAuthenticated()).toBeFalse();
    });

    it('retourne true si le token est valide', () => {
      const token = makeToken({ exp: NOW_SEC() + 3600, iat: NOW_SEC() });
      localStorage.setItem('access_token', token);
      expect(service.isAuthenticated()).toBeTrue();
    });
  });

  // ── logout() ──────────────────────────────────────────────────────────────

  describe('logout()', () => {
    it('supprime access_token et refresh_token', () => {
      localStorage.setItem('access_token', 'a');
      localStorage.setItem('refresh_token', 'r');
      service.logout();
      expect(localStorage.getItem('access_token')).toBeNull();
      expect(localStorage.getItem('refresh_token')).toBeNull();
    });

    it('supprime user et allowed_modules', () => {
      localStorage.setItem('user', '{"login":"alice"}');
      localStorage.setItem('allowed_modules', '["eau"]');
      service.logout();
      expect(localStorage.getItem('user')).toBeNull();
      expect(localStorage.getItem('allowed_modules')).toBeNull();
    });

    it('émet false sur authState$ après logout', (done) => {
      // skip(1) ignore la valeur initiale du BehaviorSubject (émise à la souscription)
      service.authState$.pipe(skip(1)).subscribe(state => {
        expect(state).toBeFalse();
        done();
      });
      service.logout();
    });

    it('navigue vers /login', () => {
      service.logout();
      expect(router.navigate).toHaveBeenCalledWith(['/login']);
    });
  });

  // ── getToken() ────────────────────────────────────────────────────────────

  describe('getToken()', () => {
    it('retourne null si aucun token en storage', () => {
      expect(service.getToken()).toBeNull();
    });

    it('retourne le token de localStorage', () => {
      localStorage.setItem('access_token', 'test-token');
      expect(service.getToken()).toBe('test-token');
    });
  });

  // ── getCurrentLogin() / getCurrentRole() / getUserRole() ─────────────────

  describe('Lecture user courant', () => {
    beforeEach(() => {
      localStorage.setItem('user', JSON.stringify({ login: 'wassef.ayari', role: 'SUPER_ADMIN' }));
    });

    it('getCurrentLogin() retourne le login', () => {
      expect(service.getCurrentLogin()).toBe('wassef.ayari');
    });

    it('getCurrentRole() retourne le rôle', () => {
      expect(service.getCurrentRole()).toBe('SUPER_ADMIN');
    });

    it('getUserRole() retourne le rôle', () => {
      expect(service.getUserRole()).toBe('SUPER_ADMIN');
    });

    it('getCurrentLogin() retourne "Inconnu" si aucun user', () => {
      localStorage.clear();
      expect(service.getCurrentLogin()).toBe('Inconnu');
    });
  });

  // ── getFullName() ────────────────────────────────────────────────────────

  describe('getFullName()', () => {
    it('login séparé par un point → Prenom Nom', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'wassef.ayari', role: 'ADMIN' }));
      expect(service.getFullName()).toBe('Wassef Ayari');
    });

    it('login séparé par tiret bas → Prenom Nom', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'alice_martin', role: 'EMPLOYEE' }));
      expect(service.getFullName()).toBe('Alice Martin');
    });

    it('login email → supprime le domaine et les chiffres', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'john.doe99@gmail.com', role: 'ADMIN' }));
      expect(service.getFullName()).toBe('John Doe');
    });

    it('retourne "Utilisateur" si aucun user', () => {
      localStorage.clear();
      expect(service.getFullName()).toBe('Utilisateur');
    });
  });

  // ── getInitials() ─────────────────────────────────────────────────────────

  describe('getInitials()', () => {
    it('wassef.ayari → WA', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'wassef.ayari', role: 'ADMIN' }));
      expect(service.getInitials()).toBe('WA');
    });

    it('alice_martin → AM', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'alice_martin', role: 'ADMIN' }));
      expect(service.getInitials()).toBe('AM');
    });

    it('retourne une chaîne en majuscules', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'bo', role: 'EMPLOYEE' }));
      const initials = service.getInitials();
      expect(initials).toBe(initials.toUpperCase());
    });
  });

  // ── getRoleLabel() ────────────────────────────────────────────────────────

  describe('getRoleLabel()', () => {
    it('SUPER_ADMIN → "Super Administrateur"', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'a', role: 'SUPER_ADMIN' }));
      expect(service.getRoleLabel()).toBe('Super Administrateur');
    });

    it('EMPLOYEE → "Employé"', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'a', role: 'EMPLOYEE' }));
      expect(service.getRoleLabel()).toBe('Employé');
    });

    it('ADMIN → "Administrateur"', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'a', role: 'ADMIN' }));
      expect(service.getRoleLabel()).toBe('Administrateur');
    });

    it('rôle inconnu → "Utilisateur"', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'a', role: 'UNKNOWN' }));
      expect(service.getRoleLabel()).toBe('Utilisateur');
    });
  });

  // ── getAllowedModules() / hasModule() ─────────────────────────────────────

  describe('getAllowedModules() / hasModule()', () => {
    it('getAllowedModules() retourne null si non défini', () => {
      expect(service.getAllowedModules()).toBeNull();
    });

    it('getAllowedModules() retourne le tableau stocké', () => {
      localStorage.setItem('allowed_modules', JSON.stringify(['eau', 'gaz']));
      expect(service.getAllowedModules()).toEqual(['eau', 'gaz']);
    });

    it('getAllowedModules() retourne null si JSON invalide', () => {
      localStorage.setItem('allowed_modules', '{invalid}');
      expect(service.getAllowedModules()).toBeNull();
    });

    it('hasModule() retourne true pour SUPER_ADMIN quel que soit le module', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'a', role: 'SUPER_ADMIN' }));
      localStorage.setItem('allowed_modules', JSON.stringify(['eau']));
      expect(service.hasModule('gaz')).toBeTrue();
    });

    it('hasModule() vérifie la liste pour un non-admin', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'a', role: 'EMPLOYEE' }));
      localStorage.setItem('allowed_modules', JSON.stringify(['eau']));
      expect(service.hasModule('eau')).toBeTrue();
      expect(service.hasModule('gaz')).toBeFalse();
    });

    it('hasModule() retourne true si allowed_modules est null (pas de restriction)', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'a', role: 'EMPLOYEE' }));
      expect(service.hasModule('eau')).toBeTrue();
    });
  });

  // ── hasPermission() ───────────────────────────────────────────────────────

  describe('hasPermission()', () => {
    it('retourne false si aucun token', () => {
      expect(service.hasPermission('VIEW_ALERTS')).toBeFalse();
    });

    it('retourne true si la permission est dans les groups du token', () => {
      const token = makeToken({
        exp: NOW_SEC() + 3600, iat: NOW_SEC(),
        groups: ['ADMIN', 'VIEW_ALERTS'],
        role: 'ADMIN', login: 'alice'
      });
      localStorage.setItem('access_token', token);
      expect(service.hasPermission('VIEW_ALERTS')).toBeTrue();
    });

    it('retourne false si la permission est absente', () => {
      const token = makeToken({
        exp: NOW_SEC() + 3600, iat: NOW_SEC(),
        groups: ['ADMIN'],
        role: 'ADMIN', login: 'alice'
      });
      localStorage.setItem('access_token', token);
      expect(service.hasPermission('DELETE_USERS')).toBeFalse();
    });
  });
});
