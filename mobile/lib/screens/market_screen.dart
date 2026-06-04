import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:fl_chart/fl_chart.dart';
import '../config/theme.dart';
import '../models/market_data.dart';
import '../services/api_service.dart';
import '../widgets/metric_card.dart';

/// 市场概览页
class MarketScreen extends StatefulWidget {
  const MarketScreen({super.key});

  @override
  State<MarketScreen> createState() => _MarketScreenState();
}

class _MarketScreenState extends State<MarketScreen> {
  final ApiService _apiService = ApiService();
  MarketData? _marketData;
  bool _isLoading = false;
  String? _error;
  String _selectedMoverTab = 'gainers';

  @override
  void initState() {
    super.initState();
    _loadMarketData();
  }

  @override
  void dispose() {
    _apiService.dispose();
    super.dispose();
  }

  Future<void> _loadMarketData() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final data = await _apiService.getMarketOverview();
      setState(() {
        _marketData = data;
        _isLoading = false;
      });
    } on Exception catch (e) {
      setState(() {
        _error = e.toString().replaceFirst('ApiException: ', '');
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          color: AppTheme.primaryColor,
          backgroundColor: AppTheme.surfaceColor,
          onRefresh: _loadMarketData,
          child: SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 12),
                _buildHeader(),
                const SizedBox(height: 16),
                if (_isLoading) _buildLoadingState(),
                if (_error != null) _buildErrorState(),
                if (_marketData != null) ...[
                  _buildSentimentGauge(),
                  const SizedBox(height: 16),
                  _buildMarketIndices(),
                  const SizedBox(height: 16),
                  _buildSectorPerformance(),
                  const SizedBox(height: 16),
                  _buildMarketMovers(),
                  const SizedBox(height: 24),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Row(
          children: [
            const Icon(Icons.show_chart, color: AppTheme.primaryColor, size: 28),
            const SizedBox(width: 10),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '市场概览',
                  style: GoogleFonts.orbitron(
                    color: AppTheme.primaryColor,
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  _marketData?.updateTime ?? '实时市场数据',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ],
        ),
        IconButton(
          onPressed: _loadMarketData,
          icon: const Icon(Icons.refresh, color: AppTheme.primaryColor),
        ),
      ],
    );
  }

  Widget _buildLoadingState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 80),
        child: Column(
          children: [
            const CircularProgressIndicator(
              color: AppTheme.primaryColor,
              strokeWidth: 3,
            ),
            const SizedBox(height: 20),
            Text(
              '加载市场数据中...',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorState() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppTheme.sellColor.withOpacity(0.1),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.sellColor.withOpacity(0.3)),
      ),
      child: Column(
        children: [
          const Icon(Icons.error_outline, color: AppTheme.sellColor, size: 36),
          const SizedBox(height: 12),
          Text(
            '加载失败',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: AppTheme.sellColor,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            _error ?? '未知错误',
            style: Theme.of(context).textTheme.bodySmall,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: _loadMarketData,
            child: const Text('重试'),
          ),
        ],
      ),
    );
  }

  Widget _buildSentimentGauge() {
    final sentiment = _marketData!.sentiment;
    final score = sentiment.score;
    final isBullish = sentiment.isBullish;
    final isBearish = sentiment.isBearish;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppTheme.cardColor,
            isBullish
                ? AppTheme.buyColor.withOpacity(0.05)
                : isBearish
                    ? AppTheme.sellColor.withOpacity(0.05)
                    : AppTheme.holdColor.withOpacity(0.05),
          ],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isBullish
              ? AppTheme.buyColor.withOpacity(0.2)
              : isBearish
                  ? AppTheme.sellColor.withOpacity(0.2)
                  : AppTheme.holdColor.withOpacity(0.2),
        ),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                '市场情绪',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: (isBullish
                          ? AppTheme.buyColor
                          : isBearish
                              ? AppTheme.sellColor
                              : AppTheme.holdColor)
                      .withOpacity(0.15),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  isBullish ? '偏多' : isBearish ? '偏空' : '中性',
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: isBullish
                            ? AppTheme.buyColor
                            : isBearish
                                ? AppTheme.sellColor
                                : AppTheme.holdColor,
                        fontWeight: FontWeight.bold,
                      ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),

          // 情绪仪表盘
          SizedBox(
            height: 120,
            child: Stack(
              alignment: Alignment.center,
              children: [
                // 背景弧
                SizedBox(
                  width: 200,
                  height: 100,
                  child: CustomPaint(
                    painter: _SentimentGaugePainter(
                      score: score / 100,
                    ),
                  ),
                ),
                // 分数
                Column(
                  children: [
                    Text(
                      score.toStringAsFixed(0),
                      style: GoogleFonts.orbitron(
                        color: isBullish
                            ? AppTheme.buyColor
                            : isBearish
                                ? AppTheme.sellColor
                                : AppTheme.holdColor,
                        fontSize: 36,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    Text(
                      '/ 100',
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                  ],
                ),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // 信号统计
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _buildSignalCount('买入', sentiment.signals['buy'] ?? 0, AppTheme.buyColor),
              _buildSignalCount('观望', sentiment.signals['hold'] ?? 0, AppTheme.holdColor),
              _buildSignalCount('卖出', sentiment.signals['sell'] ?? 0, AppTheme.sellColor),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSignalCount(String label, int count, Color color) {
    return Column(
      children: [
        Text(
          '$count',
          style: GoogleFonts.orbitron(
            color: color,
            fontSize: 20,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color),
        ),
      ],
    );
  }

  Widget _buildMarketIndices() {
    final indices = _marketData!.indices;
    if (indices.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '主要指数',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 12),
        ...indices.map((index) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: AppTheme.cardColor,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: (index.isPositive
                          ? AppTheme.buyColor
                          : AppTheme.sellColor)
                      .withOpacity(0.1),
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        index.name,
                        style: Theme.of(context)
                            .textTheme
                            .titleSmall
                            ?.copyWith(fontWeight: FontWeight.w600),
                      ),
                      Text(
                        index.symbol,
                        style: Theme.of(context).textTheme.labelSmall,
                      ),
                    ],
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        index.value.toStringAsFixed(2),
                        style: Theme.of(context)
                            .textTheme
                            .titleSmall
                            ?.copyWith(fontWeight: FontWeight.bold),
                      ),
                      Text(
                        '${index.isPositive ? '+' : ''}${index.changePercent.toStringAsFixed(2)}%',
                        style: Theme.of(context).textTheme.labelMedium?.copyWith(
                              color: index.isPositive
                                  ? AppTheme.buyColor
                                  : AppTheme.sellColor,
                              fontWeight: FontWeight.bold,
                            ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          );
        }).toList(),
      ],
    );
  }

  Widget _buildSectorPerformance() {
    final sectors = _marketData!.sectors;
    if (sectors.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '板块表现',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.cardColor,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: AppTheme.primaryColor.withOpacity(0.1),
            ),
          ),
          child: SizedBox(
            height: 200,
            child: BarChart(
              BarChartData(
                alignment: BarChartAlignment.spaceAround,
                gridData: FlGridData(show: false),
                titlesAndBorderData: FlTitlesData(
                  topTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  rightTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 60,
                      getTitlesWidget: (value, meta) {
                        final index = value.toInt();
                        if (index >= 0 && index < sectors.length) {
                          return Padding(
                            padding: const EdgeInsets.only(top: 8),
                            child: Text(
                              sectors[index].name,
                              style: const TextStyle(
                                color: AppTheme.textHint,
                                fontSize: 9,
                              ),
                              textAlign: TextAlign.center,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                          );
                        }
                        return const SizedBox.shrink();
                      },
                    ),
                  ),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 40,
                      getTitlesWidget: (value, meta) {
                        return Text(
                          '${value.toStringAsFixed(1)}%',
                          style: const TextStyle(
                            color: AppTheme.textHint,
                            fontSize: 9,
                          ),
                        );
                      },
                    ),
                  ),
                  borderData: FlBorderData(show: false),
                ),
                barGroups: sectors.asMap().entries.map((entry) {
                  final sector = entry.value;
                  final isPositive = sector.changePercent >= 0;
                  return BarChartGroupData(
                    x: entry.key,
                    barRods: [
                      BarChartRodData(
                        toY: sector.changePercent,
                        color: isPositive
                            ? AppTheme.buyColor
                            : AppTheme.sellColor,
                        width: 24,
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ],
                  );
                }).toList(),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildMarketMovers() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '涨跌排行',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 12),

        // Tab切换
        Container(
          decoration: BoxDecoration(
            color: AppTheme.surfaceColor,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            children: [
              _buildMoverTab('涨幅榜', 'gainers', AppTheme.buyColor),
              _buildMoverTab('跌幅榜', 'losers', AppTheme.sellColor),
              _buildMoverTab('活跃榜', 'active', AppTheme.primaryColor),
            ],
          ),
        ),

        const SizedBox(height: 12),

        // 列表
        ..._getSelectedMovers().map((mover) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: AppTheme.cardColor,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        mover.symbol,
                        style: Theme.of(context)
                            .textTheme
                            .titleSmall
                            ?.copyWith(fontWeight: FontWeight.bold),
                      ),
                      Text(
                        mover.name,
                        style: Theme.of(context).textTheme.labelSmall,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        '\$${mover.price.toStringAsFixed(2)}',
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: (mover.isPositive
                                  ? AppTheme.buyColor
                                  : AppTheme.sellColor)
                              .withOpacity(0.15),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          '${mover.isPositive ? '+' : ''}${mover.changePercent.toStringAsFixed(2)}%',
                          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                                color: mover.isPositive
                                    ? AppTheme.buyColor
                                    : AppTheme.sellColor,
                                fontWeight: FontWeight.bold,
                              ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          );
        }).toList(),
      ],
    );
  }

  Widget _buildMoverTab(String label, String key, Color color) {
    final isSelected = _selectedMoverTab == key;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => _selectedMoverTab = key),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            color: isSelected ? color.withOpacity(0.15) : Colors.transparent,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(
            label,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: isSelected ? color : AppTheme.textHint,
                  fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                ),
          ),
        ),
      ),
    );
  }

  List<MarketMover> _getSelectedMovers() {
    switch (_selectedMoverTab) {
      case 'gainers':
        return _marketData?.topGainers ?? [];
      case 'losers':
        return _marketData?.topLosers ?? [];
      case 'active':
        return _marketData?.mostActive ?? [];
      default:
        return [];
    }
  }
}

/// 市场情绪仪表盘绘制器
class _SentimentGaugePainter extends CustomPainter {
  final double score;

  _SentimentGaugePainter({required this.score});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height);
    final radius = size.width / 2 - 10;

    // 背景弧
    final bgPaint = Paint()
      ..color = AppTheme.surfaceColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 12
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -3.14159,
      3.14159,
      false,
      bgPaint,
    );

    // 进度弧
    final progressAngle = -3.14159 + (score * 3.14159);
    final progressColor = score > 0.55
        ? AppTheme.buyColor
        : score < 0.45
            ? AppTheme.sellColor
            : AppTheme.holdColor;

    final progressPaint = Paint()
      ..color = progressColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 12
      ..strokeCap = StrokeCap.round
      ..shader = LinearGradient(
        colors: [AppTheme.sellColor, AppTheme.holdColor, AppTheme.buyColor],
        begin: Alignment.centerLeft,
        end: Alignment.centerRight,
      ).createShader(Rect.fromCircle(center: center, radius: radius));

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -3.14159,
      progressAngle + 3.14159,
      false,
      progressPaint,
    );
  }

  @override
  bool shouldRepaint(covariant _SentimentGaugePainter oldDelegate) {
    return oldDelegate.score != score;
  }
}
