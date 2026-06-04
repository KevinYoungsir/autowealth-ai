import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/stock_analysis.dart';
import '../models/market_data.dart';

/// API 服务类 - 调用 AutoWealth AI FastAPI 后端
class ApiService {
  final String baseUrl;
  final Duration timeout;
  final http.Client _client;

  ApiService({
    this.baseUrl = 'http://localhost:8000',
    this.timeout = const Duration(seconds: 30),
    http.Client? client,
  }) : _client = client ?? http.Client();

  // ==================== 通用请求 ====================

  Future<Map<String, dynamic>> _get(String path) async {
    final uri = Uri.parse('$baseUrl$path');
    try {
      final response = await _client
          .get(uri, headers: _headers())
          .timeout(timeout);
      return _handleResponse(response);
    } catch (e) {
      throw ApiException('网络请求失败: $e');
    }
  }

  Future<Map<String, dynamic>> _post(
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    try {
      final response = await _client
          .post(
            uri,
            headers: _headers(),
            body: jsonEncode(body ?? {}),
          )
          .timeout(timeout);
      return _handleResponse(response);
    } catch (e) {
      throw ApiException('网络请求失败: $e');
    }
  }

  Map<String, String> _headers() {
    return {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
  }

  Map<String, dynamic> _handleResponse(http.Response response) {
    switch (response.statusCode) {
      case 200:
      case 201:
        try {
          return jsonDecode(response.body) as Map<String, dynamic>;
        } catch (e) {
          throw ApiException('响应数据解析失败: $e');
        }
      case 400:
        final body = _tryParseBody(response.body);
        throw ApiException('请求参数错误: ${body['detail'] ?? response.body}');
      case 401:
        throw ApiException('认证失败，请检查API密钥');
      case 403:
        throw ApiException('无权访问该资源');
      case 404:
        throw ApiException('请求的资源不存在: ${response.request?.url}');
      case 422:
        final body = _tryParseBody(response.body);
        throw ApiException('数据验证失败: ${body['detail'] ?? response.body}');
      case 429:
        throw ApiException('请求过于频繁，请稍后再试');
      case 500:
        throw ApiException('服务器内部错误，请稍后再试');
      case 502:
      case 503:
        throw ApiException('服务暂时不可用，请稍后再试');
      default:
        throw ApiException(
            '请求失败 (${response.statusCode}): ${response.body}');
    }
  }

  Map<String, dynamic> _tryParseBody(String body) {
    try {
      return jsonDecode(body) as Map<String, dynamic>;
    } catch (_) {
      return {};
    }
  }

  // ==================== 股票分析接口 ====================

  /// 分析单只股票
  /// [symbol] 股票代码，如 "AAPL", "600519.SS"
  Future<StockAnalysis> analyze(String symbol) async {
    final data = await _post('/api/v1/analyze', body: {'symbol': symbol});
    return StockAnalysis.fromJson(data);
  }

  /// 批量分析多只股票
  /// [symbols] 股票代码列表
  Future<List<StockAnalysis>> analyzeBatch(List<String> symbols) async {
    final data = await _post('/api/v1/analyze/batch', body: {
      'symbols': symbols,
    });
    final results = data['results'] ?? data['analyses'] ?? [];
    return (results as List)
        .map((e) => StockAnalysis.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // ==================== 市场数据接口 ====================

  /// 获取市场概览数据
  Future<MarketData> getMarketOverview() async {
    final data = await _get('/api/v1/market/overview');
    return MarketData.fromJson(data);
  }

  /// 获取市场情绪指数
  Future<Map<String, dynamic>> getMarketSentiment() async {
    return await _get('/api/v1/market/sentiment');
  }

  /// 获取热门股票排行
  /// [category] 排行类别: "gainers", "losers", "active"
  Future<List<Map<String, dynamic>>> getMarketMovers(
      String category) async {
    final data = await _get('/api/v1/market/movers/$category');
    final items = data['items'] ?? data['data'] ?? [];
    return (items as List).map((e) => e as Map<String, dynamic>).toList();
  }

  // ==================== 投资组合接口 ====================

  /// 分析投资组合
  /// [holdings] 持仓列表，格式: [{"symbol": "AAPL", "shares": 100, "cost": 150.0}]
  Future<Map<String, dynamic>> getPortfolioAnalysis(
      List<Map<String, dynamic>> holdings) async {
    return await _post('/api/v1/portfolio/analyze', body: {
      'holdings': holdings,
    });
  }

  /// 获取投资组合建议
  Future<Map<String, dynamic>> getPortfolioRecommendations(
      List<Map<String, dynamic>> holdings) async {
    return await _post('/api/v1/portfolio/recommendations', body: {
      'holdings': holdings,
    });
  }

  // ==================== 智能体接口 ====================

  /// 获取所有智能体列表
  Future<List<Map<String, dynamic>>> getAgents() async {
    final data = await _get('/api/v1/agents');
    final agents = data['agents'] ?? data['data'] ?? [];
    return (agents as List).map((e) => e as Map<String, dynamic>).toList();
  }

  /// 获取特定智能体的信号
  Future<List<Map<String, dynamic>>> getAgentSignals(String agentId) async {
    final data = await _get('/api/v1/agents/$agentId/signals');
    final signals = data['signals'] ?? data['data'] ?? [];
    return (signals as List).map((e) => e as Map<String, dynamic>).toList();
  }

  // ==================== 健康检查 ====================

  /// 检查后端服务是否可用
  Future<bool> healthCheck() async {
    try {
      final uri = Uri.parse('$baseUrl/health');
      final response = await _client.get(uri).timeout(const Duration(seconds: 5));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// 获取API版本信息
  Future<Map<String, dynamic>> getApiInfo() async {
    return await _get('/api/v1/info');
  }

  /// 释放资源
  void dispose() {
    _client.close();
  }
}

/// API 异常类
class ApiException implements Exception {
  final String message;
  final int? statusCode;

  ApiException(this.message, {this.statusCode});

  @override
  String toString() => 'ApiException: $message';
}
