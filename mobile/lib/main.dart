import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'app.dart';
import 'services/api_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // 全局 API 服务实例
  final apiService = ApiService(
    baseUrl: 'http://localhost:8000', // 根据实际后端地址修改
    timeout: const Duration(seconds: 30),
  );

  runApp(
    MultiProvider(
      providers: [
        Provider<ApiService>.value(value: apiService),
      ],
      child: const AutoWealthApp(),
    ),
  );
}
