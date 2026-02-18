import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject } from 'rxjs';
import { tap } from 'rxjs/operators';

export interface User {
  id: string;
  username: string;
  email?: string;
}

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private readonly apiUrl = 'http://localhost:4100';
  private readonly currentUserSignal = signal<User | null>(null);
  private readonly currentUserSubject = new BehaviorSubject<User | null>(null);

  /** Current user as a signal — use in templates and with effect/computed. */
  readonly currentUser = this.currentUserSignal.asReadonly();

  /** Observable for code that subscribes. */
  readonly currentUser$ = this.currentUserSubject.asObservable();

  constructor(private http: HttpClient) {
    this.checkAuthStatus();
  }

  private setUser(user: User | null): void {
    this.currentUserSignal.set(user);
    this.currentUserSubject.next(user);
  }

  private checkAuthStatus(): void {
    this.http.get<{ user: User | null }>(`${this.apiUrl}/auth/me`, { withCredentials: true }).subscribe({
      next: (response) => this.setUser(response.user),
      error: () => this.setUser(null),
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
    return this.http.post(`${this.apiUrl}/auth/login`, { username, password }, { withCredentials: true }).pipe(
      tap((response: any) => {
        if (response.user) this.setUser(response.user);
      })
    );
  }

  logout(): Observable<any> {
    return this.http.post(`${this.apiUrl}/auth/logout`, {}, { withCredentials: true }).pipe(
      tap(() => this.setUser(null))
    );
  }

  getCurrentUser(): User | null {
    return this.currentUserSignal();
  }
}
