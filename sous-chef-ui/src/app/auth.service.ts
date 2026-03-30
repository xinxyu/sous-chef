import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject } from 'rxjs';
import { tap } from 'rxjs/operators';
import { environment } from '../environments/environment';
import { AUTH_TOKEN_KEY } from './auth.interceptor';

export interface User {
  id: string;
  username: string;
  email?: string;
  /** Present when /auth/me returns it — true if the user signed in with or linked Google. */
  google_account?: boolean;
}

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private readonly apiUrl = environment.apiUrl;
  private readonly currentUserSignal = signal<User | null>(null);
  private readonly currentUserSubject = new BehaviorSubject<User | null>(null);

  /** Current user as a signal — use in templates and with effect/computed. */
  readonly currentUser = this.currentUserSignal.asReadonly();

  /** Observable for code that subscribes. */
  readonly currentUser$ = this.currentUserSubject.asObservable();

  constructor(private http: HttpClient) {
    this.applyOAuthHashIfPresent();
    this.checkAuthStatus();
  }

  private setUser(user: User | null): void {
    this.currentUserSignal.set(user);
    this.currentUserSubject.next(user);
  }

  private clearToken(): void {
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }
  }

  /** After Google OAuth redirect: token or error is in location hash; sync to storage and strip hash. */
  private applyOAuthHashIfPresent(): void {
    if (typeof window === 'undefined') return;
    const hash = window.location.hash || '';
    if (hash.startsWith('#oauth_token=')) {
      const raw = hash.slice('#oauth_token='.length);
      try {
        const token = decodeURIComponent(raw);
        localStorage.setItem(AUTH_TOKEN_KEY, token);
      } catch {
        sessionStorage.setItem('oauth_error', 'Could not read sign-in token');
      }
      window.history.replaceState({}, '', window.location.pathname + window.location.search);
      return;
    }
    if (hash.startsWith('#oauth_error=')) {
      const raw = hash.slice('#oauth_error='.length);
      try {
        sessionStorage.setItem('oauth_error', decodeURIComponent(raw));
      } catch {
        sessionStorage.setItem('oauth_error', 'Google sign-in failed');
      }
      window.history.replaceState({}, '', window.location.pathname + window.location.search);
    }
  }

  private checkAuthStatus(): void {
    this.http.get<{ user: User | null }>(`${this.apiUrl}/auth/me`).subscribe({
      next: (response) => {
        if (!response.user) this.clearToken();
        this.setUser(response.user);
      },
      error: () => {
        this.clearToken();
        this.setUser(null);
      },
    });
  }

  register(username: string, password: string, email?: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/auth/register`, { username, password, email }, { withCredentials: true }).pipe(
      tap((response: any) => {
        if (response.user) this.setUser(response.user);
      })
    );
  }

  login(username: string, password: string): Observable<any> {
    return this.http.post<{ user: User; token?: string }>(`${this.apiUrl}/auth/login`, { username, password }).pipe(
      tap((response) => {
        if (response.user) this.setUser(response.user);
        if (response.token && typeof localStorage !== 'undefined') {
          localStorage.setItem(AUTH_TOKEN_KEY, response.token);
        }
      })
    );
  }

  logout(): Observable<any> {
    return this.http.post(`${this.apiUrl}/auth/logout`, {}).pipe(
      tap(() => {
        this.clearToken();
        this.setUser(null);
      })
    );
  }

  verifyEmail(token: string): Observable<{ message?: string }> {
    return this.http.get<{ message?: string }>(
      `${this.apiUrl}/auth/verify-email?token=${encodeURIComponent(token)}`,
      { withCredentials: true }
    );
  }

  forgotPassword(email: string): Observable<{ message?: string }> {
    return this.http.post<{ message?: string }>(
      `${this.apiUrl}/auth/forgot-password`,
      { email },
      { withCredentials: true }
    );
  }

  resetPassword(token: string, newPassword: string): Observable<{ message?: string }> {
    return this.http.post<{ message?: string }>(
      `${this.apiUrl}/auth/reset-password`,
      { token, new_password: newPassword },
      { withCredentials: true }
    );
  }

  getCurrentUser(): User | null {
    return this.currentUserSignal();
  }

  /** Backend URL for browser redirect (e.g. Google OAuth). */
  getApiUrl(): string {
    return this.apiUrl;
  }
}
