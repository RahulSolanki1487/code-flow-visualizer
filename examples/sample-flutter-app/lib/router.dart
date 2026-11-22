import 'package:go_router/go_router.dart';
import 'auth_repository.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';
import 'screens/detail_screen.dart';

GoRouter buildRouter(AuthRepository auth) {
  return GoRouter(
    initialLocation: '/',
    redirect: (context, state) {
      final loggedIn = auth.isLoggedIn;
      final goingToLogin = state.matchedLocation == '/login';
      if (!loggedIn && !goingToLogin) return '/login';
      if (loggedIn && goingToLogin) return '/';
      return null;
    },
    routes: [
      GoRoute(path: '/', builder: (context, state) => const HomeScreen()),
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      GoRoute(
        path: '/item/:id',
        builder: (context, state) => DetailScreen(id: state.pathParameters['id']!),
      ),
    ],
  );
}
