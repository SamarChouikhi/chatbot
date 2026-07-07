import { TestBed } from '@angular/core/testing';
import { CanActivateFn, RouterStateSnapshot, ActivatedRouteSnapshot } from '@angular/router';
import { RouterTestingModule } from '@angular/router/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';

import { authGuard } from './auth.guard';
import { AuthService } from 'src/app/services/auth.service';
import { JwtService } from 'src/app/core/services/jwt.service';

describe('authGuard', () => {
  let authService: AuthService;

  const executeGuard: CanActivateFn = (...guardParameters) =>
    TestBed.runInInjectionContext(() => authGuard(...guardParameters));

  const mockRoute  = {} as ActivatedRouteSnapshot;
  const mockState  = { url: '/dashboard' } as RouterStateSnapshot;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [RouterTestingModule, HttpClientTestingModule],
      providers: [AuthService, JwtService],
    });
    localStorage.clear();
    sessionStorage.clear();
    authService = TestBed.inject(AuthService);
  });

  afterEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('devrait être défini', () => {
    expect(executeGuard).toBeTruthy();
  });

  it('retourne true si l\'utilisateur est authentifié', () => {
    spyOn(authService, 'isAuthenticated').and.returnValue(true);
    const result = executeGuard(mockRoute, mockState);
    expect(result).toBeTrue();
  });

  it('retourne un UrlTree vers /login si non authentifié', () => {
    spyOn(authService, 'isAuthenticated').and.returnValue(false);
    const result = executeGuard(mockRoute, mockState);
    expect(result).not.toBeTrue();
    // UrlTree créé par le guard
    expect(result).toBeTruthy();
    // L'URL du tree doit cibler /login
    const urlTree = result as any;
    expect(urlTree.toString()).toContain('login');
  });

  it('inclut returnUrl dans le queryParams du UrlTree', () => {
    spyOn(authService, 'isAuthenticated').and.returnValue(false);
    const result = executeGuard(mockRoute, mockState) as any;
    expect(result.queryParams?.returnUrl).toBe('/dashboard');
  });
});
