import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: ListView(children: [
        ListTile(title: const Text('Item 1'), onTap: () => context.push('/item/1')),
      ]),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          authRepository.signOut();
          context.go('/login');
        },
      ),
    );
  }
}
