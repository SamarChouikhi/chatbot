import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { LoginComponent } from './login/login.component';
import { ShellComponent } from './shell/shell.component';
import { DashboardComponent } from './dashboard/dashboard.component';
import { authGuard } from './core/guards/auth.guard';
import { roleGuard } from './core/guards/role.guard';
import { ForgotPasswordComponent } from './auth/forgot-password/forgot-password.component';
import { AlertsComponent } from './alerts/alerts.component';
import { DevicesComponent } from './devices/devices.component';
import { UsersComponent } from './users/users.component';
import { RolesComponent } from './roles/roles.component';
import { ElectricityComponent } from './electricity/electricity.component';
import { GazComponent } from './gaz/gaz.component';
import { WaterComponent } from './water/water.component';
import { FuelComponent } from './fuel/fuel.component';
import { DeviceDetailComponent } from './device-detail/device-detail.component';

const routes: Routes = [
  { path: 'login',           component: LoginComponent },
  { path: 'forgot-password', component: ForgotPasswordComponent },
  { path: '',                redirectTo: '/dashboard', pathMatch: 'full' },

  {
    path: '',
    component: ShellComponent,
    canActivate: [authGuard],
    children: [
      {
        path: 'dashboard',
        component: DashboardComponent,
        canActivate: [roleGuard],
        data: { permissions: ['VIEW_DASHBOARD'], modules: ['dashboard'], title: 'NAV.DASHBOARD' }
      },
      {
        path: 'electricity',
        component: ElectricityComponent,
        canActivate: [roleGuard],
        data: { permissions: ['VIEW_ENERGY_DATA'], modules: ['énergie électrique'], title: 'ELEC.PAGE_TITLE' }
      },
      {
        path: 'water',
        component: WaterComponent,
        canActivate: [roleGuard],
        data: { permissions: ['VIEW_WATER_DATA'], modules: ['eau'], title: 'WATER.PAGE_TITLE' }
      },
      {
        path: 'gaz',
        component: GazComponent,
        canActivate: [roleGuard],
        data: { permissions: ['VIEW_GAS_DATA'], modules: ['gaz'], title: 'GAZ.PAGE_TITLE' }
      },
      {
        path: 'fuel',
        component: FuelComponent,
        canActivate: [roleGuard],
        data: { permissions: ['EXPORT_DATA'], modules: ['carburant'], title: 'FUEL.PAGE_TITLE' }
      },
      {
        path: 'alerts',
        component: AlertsComponent,
        canActivate: [roleGuard],
        data: { permissions: ['VIEW_ALERTS', 'MANAGE_ALERTS'], modules: ['alertes'], title: 'ALERTS_PAGE.TITLE' }
      },
      {
        path: 'device',
        component: DevicesComponent,
        canActivate: [roleGuard],
        data: { permissions: ['VIEW_DEVICES', 'MANAGE_DEVICES'], modules: ['équipements/capteurs'], title: 'NAV.DEVICES' }
      },
      {
        path: 'users',
        component: UsersComponent,
        canActivate: [roleGuard],
        data: { permissions: ['VIEW_USERS', 'MANAGE_USERS'], title: 'USERS_PAGE.TITLE' }
      },
      {
        path: 'roles',
        component: RolesComponent,
        canActivate: [roleGuard],
        data: { permissions: ['MANAGE_ROLES'], title: 'ROLES_PAGE.TITLE' }
      },
      {
        path: 'device/:id/:adresse',
        component: DeviceDetailComponent,
        canActivate: [roleGuard],
        data: { permissions: ['VIEW_DEVICES', 'MANAGE_DEVICES'], title: 'NAV.DEVICES' }
      },
    ]
  }
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
