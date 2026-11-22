import { Component } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../auth/auth.service';

@Component({ selector: 'app-login', template: '<form (ngSubmit)="submit()"></form>' })
export class LoginComponent {
  error = '';
  email = '';
  password = '';

  constructor(private auth: AuthService, private router: Router, private route: ActivatedRoute) {}

  submit() {
    this.auth.login(this.email, this.password).subscribe({
      next: (res) => {
        this.auth.setToken(res.token);
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') ?? '/cart';
        this.router.navigateByUrl(returnUrl);
      },
      error: () => {
        this.error = 'Invalid email or password';
      },
    });
  }
}
