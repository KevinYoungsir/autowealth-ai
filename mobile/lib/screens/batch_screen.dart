import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../config/theme.dart';
import '../models/stock_analysis.dart';
import '../services/api_service.dart';
import '../widgets/signal_card.dart';

/// 批量分析页
class BatchScreen extends StatefulWidget {
  const BatchScreen({super.key});

  @override
  State<BatchScreen> createState() => _BatchScreenState();
}

class _BatchScreenState extends State<BatchScreen> {
  final TextEditingController _inputController = TextEditingController();
  final ApiService _apiService = ApiService();
  final List<String> _symbols = [];
  final List<StockAnalysis> _results = [];
  bool _isLoading = false;
  String? _error;

  // 预设的热门股票列表
  final List<String> _hotStocks = [
    'AAPL',
    'MSFT',
    'GOOGL',
    'AMZN',
    'TSLA',
    'NVDA',
    'META',
    'NFLX',
  ];

  @override
  void dispose() {
    _inputController.dispose();
    _apiService.dispose();
    super.dispose();
  }

  void _addSymbol(String symbol) {
    final trimmed = symbol.trim().toUpperCase();
    if (trimmed.isEmpty || _symbols.contains(trimmed)) return;
    setState(() {
      _symbols.add(trimmed);
    });
    _inputController.clear();
  }

  void _removeSymbol(int index) {
    setState(() {
      _symbols.removeAt(index);
    });
  }

  Future<void> _runBatchAnalysis() async {
    if (_symbols.isEmpty) return;

    setState(() {
      _isLoading = true;
      _error = null;
      _results.clear();
    });

    try {
      final results = await _apiService.analyzeBatch(_symbols);
      setState(() {
        _results.addAll(results);
        _isLoading = false;
      });
    } on Exception catch (e) {
      setState(() {
        _error = e.toString().replaceFirst('ApiException: ', '');
        _isLoading = false;
      });
    }
  }

  void _addHotStocks() {
    for (final stock in _hotStocks) {
      if (!_symbols.contains(stock)) {
        _symbols.add(stock);
      }
    }
    setState(() {});
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
                    _buildInputSection(),
                    const SizedBox(height: 16),
                    _buildSymbolChips(),
                    const SizedBox(height: 16),
                    _buildHotStocksSection(),
                    const SizedBox(height: 20),
                    if (_isLoading) _buildLoadingState(),
                    if (_error != null) _buildErrorState(),
                    if (_results.isNotEmpty) _buildResultsList(),
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
      child: Row(
        children: [
          const Icon(Icons.grid_view, color: AppTheme.primaryColor, size: 28),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '批量分析',
                style: GoogleFonts.orbitron(
                  color: AppTheme.primaryColor,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Text(
                '同时分析多只股票',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildInputSection() {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: _inputController,
            onSubmitted: _addSymbol,
            decoration: InputDecoration(
              hintText: '输入股票代码，回车添加',
              prefixIcon: const Icon(
                Icons.add_circle_outline,
                color: AppTheme.primaryColor,
              ),
            ),
          ),
        ),
        const SizedBox(width: 10),
        ElevatedButton(
          onPressed: _addSymbol,
          child: const Text('添加'),
        ),
      ],
    );
  }

  Widget _buildSymbolChips() {
    if (_symbols.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: AppTheme.cardColor,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: AppTheme.primaryColor.withOpacity(0.1),
          ),
        ),
        child: Center(
          child: Column(
            children: [
              Icon(
                Icons.add_circle_outline,
                size: 40,
                color: AppTheme.textHint.withOpacity(0.3),
              ),
              const SizedBox(height: 8),
              Text(
                '添加股票代码开始批量分析',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              '已添加 ${_symbols.length} 只股票',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            TextButton(
              onPressed: () {
                setState(() {
                  _symbols.clear();
                  _results.clear();
                });
              },
              child: const Text('清空'),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: _symbols.asMap().entries.map((entry) {
            return Chip(
              label: Text(entry.value),
              backgroundColor: AppTheme.cardColor,
              side: BorderSide(
                color: AppTheme.primaryColor.withOpacity(0.3),
              ),
              labelStyle: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: AppTheme.primaryColor,
                  ),
              deleteIcon: const Icon(
                Icons.close,
                size: 16,
                color: AppTheme.sellColor,
              ),
              onDeleted: () => _removeSymbol(entry.key),
            );
          }).toList(),
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            onPressed: _isLoading ? null : _runBatchAnalysis,
            icon: _isLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      color: AppTheme.backgroundColor,
                      strokeWidth: 2,
                    ),
                  )
                : const Icon(Icons.play_arrow),
            label: Text(
              _isLoading ? '分析中...' : '开始批量分析',
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildHotStocksSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '热门美股',
          style: Theme.of(context).textTheme.titleSmall,
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: _hotStocks.map((stock) {
            final isAdded = _symbols.contains(stock);
            return ActionChip(
              label: Text(stock),
              backgroundColor: isAdded
                  ? AppTheme.primaryColor.withOpacity(0.15)
                  : AppTheme.cardColor,
              side: BorderSide(
                color: isAdded
                    ? AppTheme.primaryColor
                    : AppTheme.primaryColor.withOpacity(0.3),
              ),
              labelStyle: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: isAdded
                        ? AppTheme.primaryColor
                        : AppTheme.textSecondary,
                  ),
              onPressed: () {
                if (!isAdded) {
                  _addSymbol(stock);
                }
              },
            );
          }).toList(),
        ),
        const SizedBox(height: 8),
        TextButton.icon(
          onPressed: _addHotStocks,
          icon: const Icon(Icons.add, size: 16),
          label: const Text('添加全部热门股'),
        ),
      ],
    );
  }

  Widget _buildLoadingState() {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppTheme.cardColor,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        children: [
          const CircularProgressIndicator(
            color: AppTheme.primaryColor,
          ),
          const SizedBox(height: 16),
          Text(
            '正在批量分析 ${_symbols.length} 只股票...',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 8),
          Text(
            '多智能体协同分析中，请耐心等待',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }

  Widget _buildErrorState() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.sellColor.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.sellColor.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: AppTheme.sellColor),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              _error ?? '分析失败',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: AppTheme.sellColor,
                  ),
            ),
          ),
          TextButton(
            onPressed: _runBatchAnalysis,
            child: const Text('重试'),
          ),
        ],
      ),
    );
  }

  Widget _buildResultsList() {
    // 统计信号分布
    int buyCount = 0;
    int sellCount = 0;
    int holdCount = 0;
    for (final r in _results) {
      final s = r.signal.toLowerCase();
      if (s == 'buy' || s == 'strong_buy') {
        buyCount++;
      } else if (s == 'sell' || s == 'strong_sell') {
        sellCount++;
      } else {
        holdCount++;
      }
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 汇总统计
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.cardColor,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: AppTheme.primaryColor.withOpacity(0.15),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '分析结果汇总',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _buildSummaryItem('买入', buyCount, AppTheme.buyColor),
                  _buildSummaryItem('观望', holdCount, AppTheme.holdColor),
                  _buildSummaryItem('卖出', sellCount, AppTheme.sellColor),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // 结果列表
        Text(
          '详细结果',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 12),
        ..._results.map((analysis) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: SignalCard(
              signal: analysis.signal,
              confidence: analysis.confidence,
              agentName: analysis.companyName,
              reasoning: analysis.summary,
              targetPrice: analysis.currentPrice,
            ),
          );
        }).toList(),
      ],
    );
  }

  Widget _buildSummaryItem(String label, int count, Color color) {
    return Column(
      children: [
        Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: color.withOpacity(0.1),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: color.withOpacity(0.3)),
          ),
          child: Center(
            child: Text(
              '$count',
              style: GoogleFonts.orbitron(
                color: color,
                fontSize: 22,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ),
        const SizedBox(height: 6),
        Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: color,
              ),
        ),
      ],
    );
  }
}
