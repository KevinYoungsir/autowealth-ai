/// 股票分析结果模型
class StockAnalysis {
  final String symbol;
  final String companyName;
  final double currentPrice;
  final double changePercent;
  final String signal; // buy, sell, hold, strong_buy, strong_sell
  final double confidence;
  final List<AgentScore> agentScores;
  final List<PricePoint> priceHistory;
  final Map<String, dynamic> metrics;
  final String analysisTime;
  final String summary;

  StockAnalysis({
    required this.symbol,
    required this.companyName,
    required this.currentPrice,
    required this.changePercent,
    required this.signal,
    required this.confidence,
    required this.agentScores,
    required this.priceHistory,
    required this.metrics,
    required this.analysisTime,
    required this.summary,
  });

  factory StockAnalysis.fromJson(Map<String, dynamic> json) {
    return StockAnalysis(
      symbol: json['symbol'] ?? '',
      companyName: json['company_name'] ?? json['companyName'] ?? '',
      currentPrice: (json['current_price'] ?? json['currentPrice'] ?? 0).toDouble(),
      changePercent: (json['change_percent'] ?? json['changePercent'] ?? 0).toDouble(),
      signal: json['signal'] ?? 'hold',
      confidence: (json['confidence'] ?? 0).toDouble(),
      agentScores: (json['agent_scores'] ?? json['agentScores'] ?? [])
          .map<AgentScore>((e) => AgentScore.fromJson(e))
          .toList(),
      priceHistory: (json['price_history'] ?? json['priceHistory'] ?? [])
          .map<PricePoint>((e) => PricePoint.fromJson(e))
          .toList(),
      metrics: Map<String, dynamic>.from(json['metrics'] ?? {}),
      analysisTime: json['analysis_time'] ?? json['analysisTime'] ?? '',
      summary: json['summary'] ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'symbol': symbol,
      'company_name': companyName,
      'current_price': currentPrice,
      'change_percent': changePercent,
      'signal': signal,
      'confidence': confidence,
      'agent_scores': agentScores.map((e) => e.toJson()).toList(),
      'price_history': priceHistory.map((e) => e.toJson()).toList(),
      'metrics': metrics,
      'analysis_time': analysisTime,
      'summary': summary,
    };
  }
}

/// 智能体评分
class AgentScore {
  final String agentName;
  final String agentType;
  final double score;
  final String recommendation;
  final String reasoning;

  AgentScore({
    required this.agentName,
    required this.agentType,
    required this.score,
    required this.recommendation,
    required this.reasoning,
  });

  factory AgentScore.fromJson(Map<String, dynamic> json) {
    return AgentScore(
      agentName: json['agent_name'] ?? json['agentName'] ?? '',
      agentType: json['agent_type'] ?? json['agentType'] ?? '',
      score: (json['score'] ?? 0).toDouble(),
      recommendation: json['recommendation'] ?? '',
      reasoning: json['reasoning'] ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'agent_name': agentName,
      'agent_type': agentType,
      'score': score,
      'recommendation': recommendation,
      'reasoning': reasoning,
    };
  }
}

/// 价格数据点
class PricePoint {
  final DateTime date;
  final double open;
  final double high;
  final double low;
  final double close;
  final double volume;

  PricePoint({
    required this.date,
    required this.open,
    required this.high,
    required this.low,
    required this.close,
    required this.volume,
  });

  factory PricePoint.fromJson(Map<String, dynamic> json) {
    return PricePoint(
      date: json['date'] != null
          ? DateTime.parse(json['date'].toString())
          : DateTime.now(),
      open: (json['open'] ?? 0).toDouble(),
      high: (json['high'] ?? 0).toDouble(),
      low: (json['low'] ?? 0).toDouble(),
      close: (json['close'] ?? 0).toDouble(),
      volume: (json['volume'] ?? 0).toDouble(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'date': date.toIso8601String(),
      'open': open,
      'high': high,
      'low': low,
      'close': close,
      'volume': volume,
    };
  }
}
