class AuthRepository {
  String? _token;

  bool get isLoggedIn => _token != null;

  Future<void> signIn(String email, String password) async {
    if (password.length < 8) {
      throw const AuthException('Password too short');
    }
    // network call omitted
    _token = 'token-for-$email';
  }

  void signOut() => _token = null;
}

class AuthException implements Exception {
  const AuthException(this.message);
  final String message;
}
