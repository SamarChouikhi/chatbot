import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';
import { AuthService } from 'src/app/services/auth.service';

export const authGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (authService.isAuthenticated()) {
    return true; // utilisateur connecté → accès autorisé
  } else {
    // utilisateur non connecté → redirection vers login avec l'URL demandée
    return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
  }
};