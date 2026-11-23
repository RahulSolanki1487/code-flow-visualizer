import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class OrdersService {
  constructor(private http: HttpClient) {}

  list() {
    return this.http.get<Order[]>('/orders-svc/api/v1/orders');
  }

  get(id: number) {
    return this.http.get<Order>(`/orders-svc/api/v1/orders/${id}`);
  }

  place(order: NewOrder) {
    return this.http.post<Order>('/orders-svc/api/v1/orders', order);
  }

  invoiceFor(orderId: number) {
    return this.http.get<Invoice>(`/billing-svc/api/v1/invoices/${orderId}`);
  }

  pay(orderId: number, card: Card) {
    return this.http.post<Payment>('/billing-svc/api/v1/payments', { orderId, card });
  }

  track(orderId: number) {
    return this.http.get(`/shipping-svc/api/v1/tracking/${orderId}`);
  }
}
