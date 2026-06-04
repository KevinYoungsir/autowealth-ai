import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../config/theme.dart';
import '../services/api_service.dart';
import '../widgets/metric_card.dart';

/// 投资组合页
class PortfolioScreen extends StatefulWidget {
  const PortfolioScreen({super.key});

  @override
  State<PortfolioScreen> createState() => _PortfolioScreenState();
}

class _PortfolioScreenState extends State<PortfolioScreen> {
  final ApiService _apiService = ApiService();
  bool _isLoading = false;
  String? _error;
  Map<String, dynamic>? _portfolioResult;

  // 示例持仓数据
  final List<Map<String, dynamic>> _holdings = [
    {'symbol': 'AAPL', 'shares': 50, 'cost': 150.0, 'name': 'Apple Inc.'},
    {'symbol': 'MSFT', 'shares': 30, 'cost': 380.0, 'name': 'Microsoft Corp.'},
    {'symbol': 'GOOGL', 'shares': 20, 'cost': 140.0, 'name': 'Alphabet Inc.'},
  ];

  // 添加持仓的控制器
  final TextEditingController _symbolController = TextEditingController();
  final TextEditingController _sharesController = TextEditingController();
  final TextEditingController _costController = TextEditingController();

  @override
  void dispose() {
    _apiService.dispose();
    _symbolController.dispose();
    _sharesController.dispose();
    _costController.dispose();
    super.dispose();
  }

  void _addHolding() {
    final symbol = _symbolController.text.trim().toUpperCase();
    final shares = int.tryParse(_sharesController.text.trim()) ?? 0;
    final cost = double.tryParse(_costController.text.trim()) ?? 0;

    if (symbol.isEmpty || shares <= 0 || cost <= 0) return;

    setState(() {
      _holdings.add({
        'symbol': symbol,
        'shares': shares,
        'cost': cost,
        'name': symbol,
      });
    });

    _symbolController.clear();
    _sharesController.clear();
    _costController.clear();
  }

  void _removeHolding(int index) {
    setState(() {
      _holdings.removeAt(index);
    });
  }

  Future<void> _analyzePortfolio() async {
    if (_holdings.isEmpty) return;

    setState(() {
      _isLoading = true;
      _error = null;
      _portfolioResult = null;
    });

    try {
      final result = await _apiService.getPortfolioAnalysis(_holdings);
      setState(() {
        _portfolioResult = result;
        _isLoading = false;
      });
    } on Exception catch (e) {
      setState(() {
        _error = e.toString().replaceFirst('ApiException: ', '');
        _isLoading = false;
      });
    }
  }

  double _calculateTotalValue() {
    double total = 0;
    for (final h in _holdings) {
      total += (h['shares'] as int) * (h['cost'] as double);
    }
    return total;
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
                    _buildPortfolioSummary(),
                    const SizedBox(height: 16),
                    _buildHoldingsList(),
                    const SizedBox(height: 16),
                    _buildAddHoldingForm(),
                    const SizedBox(height: 20),
                    if (_isLoading) _buildLoadingState(),
                    if (_error != null) _buildErrorState(),
                    if (_portfolioResult != null)
                      _buildAnalysisResults(),
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
          const Icon(Icons.pie_chart, color: AppTheme.primaryColor, size: 28),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '投资组合',
                style: GoogleFonts.orbitron(
                  color: AppTheme.primaryColor,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Text(
                '分析你的持仓配置',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildPortfolioSummary() {
    final totalValue = _calculateTotalValue();

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppTheme.cardColor,
            AppTheme.primaryColor.withOpacity(0.05),
          ],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppTheme.primaryColor.withOpacity(0.2),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '组合总市值',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 8),
          Text(
            '\$${totalValue.toStringAsFixed(2)}',
            style: GoogleFonts.orbitron(
              color: AppTheme.primaryColor,
              fontSize: 32,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '共 ${_holdings.length} 只股票',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 16),
          if (_holdings.isNotEmpty)
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: _isLoading ? null : _analyzePortfolio,
                icon: _isLoading
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          color: AppTheme.backgroundColor,
                          strokeWidth: 2,
                        ),
                      )
                    : const Icon(Icons.auto_awesome),
                label: Text(
                  _isLoading ? '分析中...' : 'AI分析组合',
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildHoldingsList() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              '持仓列表',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            if (_holdings.isNotEmpty)
              TextButton(
                onPressed: () => setState(() => _holdings.clear()),
                child: const Text('清空'),
              ),
          ],
        ),
        const SizedBox(height: 8),
        if (_holdings.isEmpty)
          Container(
            padding: const EdgeInsets.all(24),
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
                    Icons.portrait_outlined,
                    size: 40,
                    color: AppTheme.textHint.withOpacity(0.3),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '暂无持仓，请添加股票',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          )
        else
          ..._holdings.asMap().entries.map((entry) {
            final holding = entry.value;
            final value =
                (holding['shares'] as int) * (holding['cost'] as double);
            final totalValue = _calculateTotalValue();
            final percentage =
                totalValue > 0 ? (value / totalValue * 100) : 0;

            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Dismissible(
                key: ValueKey('${holding['symbol']}_${entry.key}'),
                direction: DismissDirection.endToStart,
                background: Container(
                  alignment: Alignment.centerRight,
                  padding: const EdgeInsets.only(right: 16),
                  decoration: BoxDecoration(
                    color: AppTheme.sellColor.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.delete, color: AppTheme.sellColor),
                ),
                onDismissed: (_) => _removeHolding(entry.key),
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppTheme.cardColor,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: AppTheme.primaryColor.withOpacity(0.1),
                    ),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: AppTheme.primaryColor.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Center(
                          child: Text(
                            holding['symbol'].toString().substring(0, 2),
                            style: GoogleFonts.orbitron(
                              color: AppTheme.primaryColor,
                              fontSize: 12,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              holding['symbol'] as String,
                              style: Theme.of(context)
                                  .textTheme
                                  .titleSmall
                                  ?.copyWith(fontWeight: FontWeight.bold),
                            ),
                            Text(
                              '${holding['shares']}股 x \$${(holding['cost'] as double).toStringAsFixed(2)}',
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ],
                        ),
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(
                            '\$${value.toStringAsFixed(0)}',
                            style: Theme.of(context)
                                .textTheme
                                .titleSmall
                                ?.copyWith(
                                  color: AppTheme.primaryColor,
                                  fontWeight: FontWeight.bold,
                                ),
                          ),
                          Text(
                            '${percentage.toStringAsFixed(1)}%',
                            style: Theme.of(context).textTheme.labelSmall,
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            );
          }).toList(),
      ],
    );
  }

  Widget _buildAddHoldingForm() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '添加持仓',
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
          child: Column(
            children: [
              TextField(
                controller: _symbolController,
                decoration: InputDecoration(
                  hintText: '股票代码 (如 AAPL)',
                  prefixIcon: const Icon(
                    Icons.code,
                    color: AppTheme.primaryColor,
                    size: 20,
                  ),
                  isDense: true,
                ),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _sharesController,
                      decoration: InputDecoration(
                        hintText: '股数',
                        prefixIcon: const Icon(
                          Icons.numbers,
                          color: AppTheme.primaryColor,
                          size: 20,
                        ),
                        isDense: true,
                      ),
                      keyboardType: TextInputType.number,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: TextField(
                      controller: _costController,
                      decoration: InputDecoration(
                        hintText: '成本价',
                        prefixIcon: const Icon(
                          Icons.attach_money,
                          color: AppTheme.primaryColor,
                          size: 20,
                        ),
                        isDense: true,
                      ),
                      keyboardType: TextInputType.number,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: _addHolding,
                  icon: const Icon(Icons.add),
                  label: const Text('添加到组合'),
                ),
              ),
            ],
          ),
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
          const CircularProgressIndicator(color: AppTheme.primaryColor),
          const SizedBox(height: 16),
          Text(
            'AI正在分析你的投资组合...',
            style: Theme.of(context).textTheme.bodyMedium,
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
        ],
      ),
    );
  }

  Widget _buildAnalysisResults() {
    final result = _portfolioResult!;
    final score = (result['risk_score'] ?? result['score'] ?? 0).toDouble();
    final riskLevel = result['risk_level'] ?? result['riskLevel'] ?? '中等';
    final recommendations = result['recommendations'] ?? [];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '分析结果',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 12),

        // 风险评分
        MetricCard(
          title: '组合风险评分',
          value: score.toStringAsFixed(1),
          subtitle: '风险等级: $riskLevel',
          icon: Icons.shield_outlined,
          iconColor: score > 70
              ? AppTheme.sellColor
              : score > 40
                  ? AppTheme.holdColor
                  : AppTheme.buyColor,
          valueColor: score > 70
              ? AppTheme.sellColor
              : score > 40
                  ? AppTheme.holdColor
                  : AppTheme.buyColor,
        ),

        const SizedBox(height: 12),

        // 建议
        if (recommendations is List && recommendations.isNotEmpty)
          ...recommendations.map<Widget>((rec) {
            final text = rec is String ? rec : rec.toString();
            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppTheme.cardColor,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: AppTheme.primaryColor.withOpacity(0.1),
                  ),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.lightbulb_outline,
                        color: AppTheme.primaryColor, size: 18),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        text,
                        style: Theme.of(context).textTheme.bodySmall,
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
}
