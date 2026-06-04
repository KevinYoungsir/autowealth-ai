import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:fl_chart/fl_chart.dart';
import '../config/theme.dart';
import '../models/stock_analysis.dart';
import '../services/api_service.dart';
import '../widgets/signal_card.dart';
import '../widgets/metric_card.dart';
import '../widgets/chart_widget.dart';

/// 单股分析页
class AnalysisScreen extends StatefulWidget {
  const AnalysisScreen({super.key});

  @override
  State<AnalysisScreen> createState() => _AnalysisScreenState();
}

class _AnalysisScreenState extends State<AnalysisScreen> {
  final TextEditingController _searchController = TextEditingController();
  final ApiService _apiService = ApiService();
  StockAnalysis? _analysis;
  bool _isLoading = false;
  String? _error;

  @override
  void dispose() {
    _searchController.dispose();
    _apiService.dispose();
    super.dispose();
  }

  Future<void> _analyzeStock(String symbol) async {
    if (symbol.trim().isEmpty) return;

    setState(() {
      _isLoading = true;
      _error = null;
      _analysis = null;
    });

    try {
      final result = await _apiService.analyze(symbol.trim().toUpperCase());
      setState(() {
        _analysis = result;
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
        child: Column(
          children: [
            _buildHeader(),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: 16),
                    _buildSearchBar(),
                    const SizedBox(height: 20),
                    if (_isLoading) _buildLoadingState(),
                    if (_error != null) _buildErrorState(),
                    if (_analysis != null) _buildAnalysisResult(),
                    if (_analysis == null && !_isLoading && _error == null)
                      _buildEmptyState(),
                    const SizedBox(height: 24),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.topRight,
          colors: [
            AppTheme.backgroundColor,
            AppTheme.surfaceColor.withOpacity(0.5),
          ],
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppTheme.primaryColor.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(
                  Icons.auto_awesome,
                  color: AppTheme.primaryColor,
                  size: 24,
                ),
              ),
              const SizedBox(width: 10),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'AutoWealth AI',
                    style: GoogleFonts.orbitron(
                      color: AppTheme.primaryColor,
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    '智能股票分析',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ],
          ),
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: AppTheme.cardColor,
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(
              Icons.settings_outlined,
              color: AppTheme.textSecondary,
              size: 20,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSearchBar() {
    return TextField(
      controller: _searchController,
      onSubmitted: _analyzeStock,
      decoration: InputDecoration(
        hintText: '输入股票代码，如 AAPL、TSLA、600519.SS',
        prefixIcon: const Icon(
          Icons.search,
          color: AppTheme.primaryColor,
        ),
        suffixIcon: IconButton(
          icon: const Icon(
            Icons.send,
            color: AppTheme.primaryColor,
          ),
          onPressed: () => _analyzeStock(_searchController.text),
        ),
      ),
    );
  }

  Widget _buildLoadingState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 60),
        child: Column(
          children: [
            const CircularProgressIndicator(
              color: AppTheme.primaryColor,
              strokeWidth: 3,
            ),
            const SizedBox(height: 20),
            Text(
              '正在分析 ${_searchController.text.toUpperCase()}...',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 8),
            Text(
              'AI智能体正在协同分析中',
              style: Theme.of(context).textTheme.bodySmall,
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
            '分析失败',
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
            onPressed: () => _analyzeStock(_searchController.text),
            child: const Text('重试'),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 80),
        child: Column(
          children: [
            Icon(
              Icons.analytics_outlined,
              size: 80,
              color: AppTheme.primaryColor.withOpacity(0.2),
            ),
            const SizedBox(height: 24),
            Text(
              '输入股票代码开始分析',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(
              '支持美股、A股、港股等市场',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 32),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: ['AAPL', 'TSLA', 'MSFT', 'GOOGL', '600519.SS']
                  .map((symbol) => ActionChip(
                        label: Text(symbol),
                        backgroundColor: AppTheme.cardColor,
                        side: BorderSide(
                          color: AppTheme.primaryColor.withOpacity(0.3),
                        ),
                        labelStyle: Theme.of(context)
                            .textTheme
                            .bodySmall
                            ?.copyWith(color: AppTheme.primaryColor),
                        onPressed: () {
                          _searchController.text = symbol;
                          _analyzeStock(symbol);
                        },
                      ))
                  .toList(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAnalysisResult() {
    final analysis = _analysis!;
    final signalColor = AppTheme.signalColor(analysis.signal);
    final signalLabel = AppTheme.signalLabel(analysis.signal);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 股票信息头部
        _buildStockHeader(analysis, signalColor, signalLabel),

        const SizedBox(height: 16),

        // 信号卡片
        SignalCard(
          signal: analysis.signal,
          confidence: analysis.confidence,
          reasoning: analysis.summary,
        ),

        const SizedBox(height: 16),

        // 价格走势图
        if (analysis.priceHistory.isNotEmpty)
          ChartWidget(
            dataPoints: analysis.priceHistory
                .asMap()
                .entries
                .map((e) => FlSpot(e.key.toDouble(), e.value.close))
                .toList(),
            title: '价格走势',
            lineColor: analysis.changePercent >= 0
                ? AppTheme.buyColor
                : AppTheme.sellColor,
            unit: 'USD',
          ),

        const SizedBox(height: 16),

        // 智能体评分
        _buildAgentScores(analysis),

        const SizedBox(height: 16),

        // 关键指标
        _buildKeyMetrics(analysis),
      ],
    );
  }

  Widget _buildStockHeader(
    StockAnalysis analysis,
    Color signalColor,
    String signalLabel,
  ) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: signalColor.withOpacity(0.2)),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    analysis.symbol,
                    style: GoogleFonts.orbitron(
                      color: AppTheme.textPrimary,
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    analysis.companyName,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    '\$${analysis.currentPrice.toStringAsFixed(2)}',
                    style: GoogleFonts.orbitron(
                      color: AppTheme.textPrimary,
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: analysis.changePercent >= 0
                          ? AppTheme.buyColor.withOpacity(0.15)
                          : AppTheme.sellColor.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      '${analysis.changePercent >= 0 ? '+' : ''}${analysis.changePercent.toStringAsFixed(2)}%',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: analysis.changePercent >= 0
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
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                '分析时间: ${analysis.analysisTime}',
                style: Theme.of(context).textTheme.labelSmall,
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: signalColor.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: signalColor.withOpacity(0.4)),
                ),
                child: Text(
                  '$signalLabel ${(analysis.confidence * 100).toStringAsFixed(0)}%',
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: signalColor,
                        fontWeight: FontWeight.bold,
                      ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildAgentScores(StockAnalysis analysis) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '智能体评分',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 12),
        ...analysis.agentScores.map((agent) {
          final agentColor = AppTheme.signalColor(agent.recommendation);
          return Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.cardColor,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: agentColor.withOpacity(0.15),
                ),
              ),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          const Icon(Icons.smart_toy_outlined,
                              size: 18, color: AppTheme.secondaryColor),
                          const SizedBox(width: 8),
                          Text(
                            agent.agentName,
                            style: Theme.of(context)
                                .textTheme
                                .titleSmall
                                ?.copyWith(fontWeight: FontWeight.w600),
                          ),
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: AppTheme.secondaryColor.withOpacity(0.1),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              agent.agentType,
                              style:
                                  Theme.of(context).textTheme.labelSmall?.copyWith(
                                        color: AppTheme.secondaryColor,
                                      ),
                            ),
                          ),
                        ],
                      ),
                      Row(
                        children: [
                          Text(
                            '${(agent.score * 100).toStringAsFixed(0)}分',
                            style: Theme.of(context)
                                .textTheme
                                .titleSmall
                                ?.copyWith(
                                  color: agentColor,
                                  fontWeight: FontWeight.bold,
                                ),
                          ),
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: agentColor.withOpacity(0.15),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Text(
                              AppTheme.signalLabel(agent.recommendation),
                              style: Theme.of(context)
                                  .textTheme
                                  .labelSmall
                                  ?.copyWith(
                                    color: agentColor,
                                    fontWeight: FontWeight.bold,
                                  ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(3),
                    child: LinearProgressIndicator(
                      value: agent.score,
                      backgroundColor: AppTheme.surfaceColor,
                      valueColor: AlwaysStoppedAnimation<Color>(agentColor),
                      minHeight: 4,
                    ),
                  ),
                ],
              ),
            ),
          );
        }).toList(),
      ],
    );
  }

  Widget _buildKeyMetrics(StockAnalysis analysis) {
    final metrics = analysis.metrics;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '关键指标',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 12),
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 10,
          crossAxisSpacing: 10,
          childAspectRatio: 1.6,
          children: [
            CompactMetricCard(
              label: '市盈率 (PE)',
              value: metrics['pe_ratio']?.toStringAsFixed(1) ?? 'N/A',
              color: AppTheme.primaryColor,
            ),
            CompactMetricCard(
              label: '市净率 (PB)',
              value: metrics['pb_ratio']?.toStringAsFixed(1) ?? 'N/A',
              color: AppTheme.secondaryColor,
            ),
            CompactMetricCard(
              label: 'ROE',
              value: metrics['roe']?.toStringAsFixed(1) ?? 'N/A',
              color: AppTheme.accentColor,
            ),
            CompactMetricCard(
              label: '营收增长',
              value: metrics['revenue_growth']?.toStringAsFixed(1) ?? 'N/A',
              color: AppTheme.buyColor,
            ),
          ],
        ),
      ],
    );
  }
}
