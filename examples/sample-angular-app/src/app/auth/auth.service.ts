import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private token = signal<string | null>(null);

  constructor(private http: HttpClient) {}

  isLoggedIn(): boolean {
    return this.token() !== null;
  }

  login(email: string, password: string) {
    return this.http.post<{ token: string }>('/api/login', { email, password });
  }

  setToken(token: string) {
    this.token.set(token);
  }
}
