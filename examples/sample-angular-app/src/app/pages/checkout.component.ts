import { Component } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';

@Component({ selector: 'app-checkout', template: '<button (click)="pay()">Pay</button>' })
export class CheckoutComponent {
  error = '';

  constructor(private http: HttpClient, private router: Router) {}

  pay() {
    this.http.post('/api/orders', {}).subscribe({
      next: () => this.router.navigate(['/cart']),
      error: () => {
        this.error = 'Payment failed, please try again';
      },
    });
  }
}
