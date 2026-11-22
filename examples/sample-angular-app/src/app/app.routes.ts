import { Routes } from '@angular/router';
import { authGuard } from './auth/auth.guard';
import { LoginComponent } from './pages/login.component';
import { CartComponent } from './pages/cart.component';
import { CheckoutComponent } from './pages/checkout.component';

export const routes: Routes = [
  { path: 'login', component: LoginComponent },
  { path: 'cart', component: CartComponent, canActivate: [authGuard] },
  { path: 'checkout', component: CheckoutComponent, canActivate: [authGuard] },
  { path: '', redirectTo: 'cart', pathMatch: 'full' },
];
