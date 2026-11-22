import { Component } from '@angular/core';
import { Router } from '@angular/router';

@Component({ selector: 'app-cart', template: '<button (click)="checkout()">Checkout</button>' })
export class CartComponent {
  items: { sku: string; qty: number }[] = [];

  constructor(private router: Router) {}

  checkout() {
    if (this.items.length === 0) {
      return;
    }
    this.router.navigate(['/checkout']);
  }
}
