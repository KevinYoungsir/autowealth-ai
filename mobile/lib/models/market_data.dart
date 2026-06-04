/// 市场数据模型
class MarketData {
  final List<MarketIndex> indices;
  final List<MarketSector> sectors;
  final List<MarketMover> topGainers;
  final List<MarketMover> topLosers;
  final List<MarketMover> mostActive;
  final MarketSentiment sentiment;
  final String updateTime;

  MarketData({
    required this.indices,
    required this.sectors,
    required this.topGainers,
    required this.topLosers,
    required this.mostActive,
    required this.sentiment,
    required this.updateTime,
  });

  factory MarketData.fromJson(Map<String, dynamic> json) {
    return MarketData(
      indices: (json['indices'] ?? [])
          .map<MarketIndex>((e) => MarketIndex.fromJson(e))
          .toList(),
      sectors: (json['sectors'] ?? [])
          .map<MarketSector>((e) => MarketSector.fromJson(e))
          .toList(),
      topGainers: (json['top_gainers'] ?? json['topGainers'] ?? [])
          .map<MarketMover>((e) => MarketMover.fromJson(e))
          .toList(),
      topLosers: (json['top_losers'] ?? json['topLosers'] ?? [])
          .map<MarketMover>((e) => MarketMover.fromJson(e))
          .toList(),
      mostActive: (json['most_active'] ?? json['mostActive'] ?? [])
          .map<MarketMover>((e) => MarketMover.fromJson(e))
          .toList(),
      sentiment: MarketSentiment.fromJson(json['sentiment'] ?? {}),
      updateTime: json['update_time'] ?? json['updateTime'] ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'indices': indices.map((e) => e.toJson()).toList(),
      'sectors': sectors.map((e) => e.toJson()).toList(),
      'top_gainers': topGainers.map((e) => e.toJson()).toList(),
      'top_losers': topLosers.map((e) => e.toJson()).toList(),
      'most_active': mostActive.map((e) => e.toJson()).toList(),
      'sentiment': sentiment.toJson(),
      'update_time': updateTime,
    };
  }
}

/// 市场指数
class MarketIndex {
  final String name;
  final String symbol;
  final double value;
  final double change;
  final double changePercent;

  MarketIndex({
    required this.name,
    required this.symbol,
    required this.value,
    required this.change,
    required this.changePercent,
  });

  factory MarketIndex.fromJson(Map<String, dynamic> json) {
    return MarketIndex(
      name: json['name'] ?? '',
      symbol: json['symbol'] ?? '',
      value: (json['value'] ?? 0).toDouble(),
      change: (json['change'] ?? 0).toDouble(),
      changePercent: (json['change_percent'] ?? json['changePercent'] ?? 0).toDouble(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'symbol': symbol,
      'value': value,
      'change': change,
      'change_percent': changePercent,
    };
  }

  bool get isPositive => changePercent >= 0;
}

/// 板块数据
class MarketSector {
  final String name;
  final double changePercent;
  final String trend; // up, down, flat

  MarketSector({
    required this.name,
    required this.changePercent,
    required this.trend,
  });

  factory MarketSector.fromJson(Map<String, dynamic> json) {
    return MarketSector(
      name: json['name'] ?? '',
      changePercent: (json['change_percent'] ?? json['changePercent'] ?? 0).toDouble(),
      trend: json['trend'] ?? 'flat',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'change_percent': changePercent,
      'trend': trend,
    };
  }
}

/// 涨跌排行
class MarketMover {
  final String symbol;
  final String name;
  final double price;
  final double change;
  final double changePercent;
  final double volume;

  MarketMover({
    required this.symbol,
    required this.name,
    required this.price,
    required this.change,
    required this.changePercent,
    required this.volume,
  });

  factory MarketMover.fromJson(Map<String, dynamic> json) {
    return MarketMover(
      symbol: json['symbol'] ?? '',
      name: json['name'] ?? '',
      price: (json['price'] ?? 0).toDouble(),
      change: (json['change'] ?? 0).toDouble(),
      changePercent: (json['change_percent'] ?? json['changePercent'] ?? 0).toDouble(),
      volume: (json['volume'] ?? 0).toDouble(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'symbol': symbol,
      'name': name,
      'price': price,
      'change': change,
      'change_percent': changePercent,
      'volume': volume,
    };
  }

  bool get isPositive => changePercent >= 0;
}

/// 市场情绪
class MarketSentiment {
  final double score; // 0-100, 50为中性
  final String label; // greedy, neutral, fearful
  final Map<String, int> signals; // buy/sell/hold count

  MarketSentiment({
    required this.score,
    required this.label,
    required this.signals,
  });

  factory MarketSentiment.fromJson(Map<String, dynamic> json) {
    return MarketSentiment(
      score: (json['score'] ?? 50).toDouble(),
      label: json['label'] ?? 'neutral',
      signals: Map<String, int>.from(json['signals'] ?? {
        'buy': 0,
        'sell': 0,
        'hold': 0,
      }),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'score': score,
      'label': label,
      'signals': signals,
    };
  }

  bool get isBullish => score > 55;
  bool get isBearish => score < 45;
}
