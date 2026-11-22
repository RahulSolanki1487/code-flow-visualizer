import 'package:flutter/material.dart';

class DetailScreen extends StatelessWidget {
  const DetailScreen({super.key, required this.id});
  final String id;

  @override
  Widget build(BuildContext context) => Scaffold(body: Text('Item $id'));
}
