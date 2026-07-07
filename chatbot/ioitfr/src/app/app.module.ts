import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule, HttpClient, HTTP_INTERCEPTORS } from '@angular/common/http';
import { ReactiveFormsModule, FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { MarkdownModule } from 'ngx-markdown';
import { TranslateModule, TranslateLoader } from '@ngx-translate/core';
import { TranslateHttpLoader } from '@ngx-translate/http-loader';
import { AppRoutingModule } from './app-routing.module';

export function createTranslateLoader(http: HttpClient) {
  return new TranslateHttpLoader(http, './assets/i18n/', '.json');
}
import { AppComponent } from './app.component';
import { LoginComponent } from './login/login.component';
import { DashboardComponent } from './dashboard/dashboard.component';
import { ChatbotComponent } from './chatbot/chatbot.component';
import { AuthInterceptor } from './core/interceptors/auth.interceptor';
import { ForgotPasswordComponent } from './auth/forgot-password/forgot-password.component';
import { RecoveryService } from './services/recovery.service';
import { EspacesComponent } from './espaces/espaces.component';
import { DevicesComponent } from './devices/devices.component';
import { AlertsComponent } from './alerts/alerts.component';
import { UsersComponent } from './users/users.component';
import { RolesComponent } from './roles/roles.component';
import { ElectricityComponent } from './electricity/electricity.component';
import { GazComponent } from './gaz/gaz.component';
import { WaterComponent } from './water/water.component';
import { FuelComponent } from './fuel/fuel.component';
import { ShellComponent } from './shell/shell.component';
import { ToastContainerComponent } from './shell/toast-container/toast-container.component';
import { AlertRulesComponent } from './shell/alert-rules/alert-rules.component';
import { DynamicFormComponent } from './shared/dynamic-form/dynamic-form.component';
import { ChatChartComponent } from './chatbot/chat-chart/chat-chart.component';
import { DeviceDetailComponent } from './device-detail/device-detail.component';
import { RecommendationPanelComponent } from './shared/recommendation-panel/recommendation-panel.component';

@NgModule({
  declarations: [
    AppComponent,
    LoginComponent,
    DashboardComponent,
    ChatbotComponent,
    ForgotPasswordComponent,
    EspacesComponent,
    DevicesComponent,
    DeviceDetailComponent,
    UsersComponent,
    RolesComponent,
    AlertsComponent,
    ElectricityComponent,
    GazComponent,
    WaterComponent,
    FuelComponent,
    ShellComponent,
    ToastContainerComponent,
    AlertRulesComponent,
    DynamicFormComponent,
    ChatChartComponent,
    RecommendationPanelComponent
  ],
  imports: [
    BrowserModule,
    AppRoutingModule,
    ReactiveFormsModule,
    CommonModule,
    FormsModule,
    HttpClientModule,
    TranslateModule.forRoot({
      loader: {
        provide: TranslateLoader,
        useFactory: createTranslateLoader,
        deps: [HttpClient]
      }
    }),
    MarkdownModule.forRoot()
  ],
  providers: [
    { provide: HTTP_INTERCEPTORS, useClass: AuthInterceptor, multi: true },
    RecoveryService
  ],
  bootstrap: [AppComponent]
})
export class AppModule { }