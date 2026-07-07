import { CanActivateFn, Router, ActivatedRouteSnapshot } from '@angular/router';
import { inject } from '@angular/core';
import { AuthService } from 'src/app/services/auth.service';

export const roleGuard: CanActivateFn = (route: ActivatedRouteSnapshot) => {
  const auth   = inject(AuthService);
  const router = inject(Router);

  const allowedModules: string[] = route.data['modules']     ?? [];
  const allowedRoles:   string[] = route.data['roles']       ?? [];
  const allowedPerms:   string[] = route.data['permissions'] ?? [];
  const userRole = auth.getCurrentRole();

  if (allowedRoles.length > 0 && allowedRoles.includes(userRole)) return true;
  if (allowedPerms.length > 0 && allowedPerms.some(p => auth.hasPermission(p))) return true;
  if (allowedModules.length > 0 && allowedModules.some(m => auth.hasModule(m))) return true;

  return router.createUrlTree(['/dashboard'], { queryParams: { forbidden: '1' } });
};
