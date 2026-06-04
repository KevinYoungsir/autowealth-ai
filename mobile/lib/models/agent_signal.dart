/// 智能体信号模型
class AgentSignal {
  final String id;
  final String agentName;
  final String agentType;
  final String symbol;
  final String signal; // buy, sell, hold
  final double confidence;
  final double targetPrice;
  final double stopLoss;
  final DateTime timestamp;
  final String reasoning;
  final Map<String, dynamic> metadata;

  AgentSignal({
    required this.id,
    required this.agentName,
    required this.agentType,
    required this.symbol,
    required this.signal,
    required this.confidence,
    required this.targetPrice,
    required this.stopLoss,
    required this.timestamp,
    required this.reasoning,
    required this.metadata,
  });

  factory AgentSignal.fromJson(Map<String, dynamic> json) {
    return AgentSignal(
      id: json['id'] ?? '',
      agentName: json['agent_name'] ?? json['agentName'] ?? '',
      agentType: json['agent_type'] ?? json['agentType'] ?? '',
      symbol: json['symbol'] ?? '',
      signal: json['signal'] ?? 'hold',
      confidence: (json['confidence'] ?? 0).toDouble(),
      targetPrice: (json['target_price'] ?? json['targetPrice'] ?? 0).toDouble(),
      stopLoss: (json['stop_loss'] ?? json['stopLoss'] ?? 0).toDouble(),
      timestamp: json['timestamp'] != null
          ? DateTime.parse(json['timestamp'].toString())
          : DateTime.now(),
      reasoning: json['reasoning'] ?? '',
      metadata: Map<String, dynamic>.from(json['metadata'] ?? {}),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'agent_name': agentName,
      'agent_type': agentType,
      'symbol': symbol,
      'signal': signal,
      'confidence': confidence,
      'target_price': targetPrice,
      'stop_loss': stopLoss,
      'timestamp': timestamp.toIso8601String(),
      'reasoning': reasoning,
      'metadata': metadata,
    };
  }

  /// 信号是否过期（超过24小时）
  bool get isExpired {
    return DateTime.now().difference(timestamp).inHours > 24;
  }

  /// 信号强度描述
  String get strengthLabel {
    if (confidence >= 0.8) return '强信号';
    if (confidence >= 0.6) return '中等信号';
    if (confidence >= 0.4) return '弱信号';
    return '极弱信号';
  }
}
