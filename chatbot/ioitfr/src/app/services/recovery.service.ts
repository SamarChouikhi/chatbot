import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { environment } from 'src/environments/environment';

export interface MessageResponse      { message: string; }
export interface ResetTokenResponse   { resetToken: string; }

@Injectable({ providedIn: 'root' })
export class RecoveryService {

  private readonly apiUrl = `${environment.apiUrl}/recovery`;

  constructor(private http: HttpClient) {}

  /** Étape 1 — Envoie un code OTP par email. */
  requestRecovery(email: string): Observable<MessageResponse> {
    return this.http
      .post<MessageResponse>(`${this.apiUrl}/request`, { email })
      .pipe(catchError(err => throwError(() => err)));
  }

  /** Étape 2 — Vérifie le code OTP reçu par email. */
  verifyCode(email: string, code: string): Observable<ResetTokenResponse> {
    return this.http
      .post<ResetTokenResponse>(`${this.apiUrl}/verify`, { email, code })
      .pipe(catchError(err => throwError(() => err)));
  }

  /** Étape 3 — Réinitialise le mot de passe avec le token reçu. */
  resetPassword(resetToken: string, newPassword: string): Observable<MessageResponse> {
    return this.http
      .post<MessageResponse>(`${this.apiUrl}/reset`, { resetToken, newPassword })
      .pipe(catchError(err => throwError(() => err)));
  }
}
