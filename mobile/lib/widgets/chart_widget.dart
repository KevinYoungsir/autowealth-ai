import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../../config/theme.dart';

/// 图表组件 - 使用 fl_chart 显示价格走势
class ChartWidget extends StatelessWidget {
  final List<FlSpot> dataPoints;
  final String title;
  final ChartType chartType;
  final Color? lineColor;
  final bool showGrid;
  final bool showDots;
  final String? unit;
  final double? minY;
  final double? maxY;

  const ChartWidget({
    super.key,
    required this.dataPoints,
    required this.title,
    this.chartType = ChartType.line,
    this.lineColor,
    this.showGrid = true,
    this.showDots = false,
    this.unit,
    this.minY,
    this.maxY,
  });

  @override
  Widget build(BuildContext context) {
    final effectiveLineColor = lineColor ?? AppTheme.primaryColor;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: effectiveLineColor.withOpacity(0.15),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 标题
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                title,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: AppTheme.textPrimary,
                      fontWeight: FontWeight.w600,
                    ),
              ),
              if (unit != null)
                Text(
                  unit!,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: AppTheme.textHint,
                      ),
                ),
            ],
          ),
          const SizedBox(height: 16),

          // 图表区域
          SizedBox(
            height: 220,
            child: dataPoints.isEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.show_chart,
                          size: 48,
                          color: AppTheme.textHint.withOpacity(0.3),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          '暂无数据',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  )
                : LineChart(
                    LineChartData(
                      gridData: showGrid
                          ? FlGridData(
                              show: true,
                              drawVerticalLine: true,
                              drawHorizontalLine: true,
                              getDrawingHorizontalLine: (value) => FlLine(
                                color:
                                    AppTheme.primaryColor.withOpacity(0.06),
                                strokeWidth: 1,
                              ),
                              getDrawingVerticalLine: (value) => FlLine(
                                color:
                                    AppTheme.primaryColor.withOpacity(0.06),
                                strokeWidth: 1,
                              ),
                            )
                          : FlGridData(show: false),
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
                            reservedSize: 30,
                            interval: _calculateInterval(dataPoints.length),
                            getTitlesWidget: (value, meta) {
                              final index = value.toInt();
                              if (index >= 0 && index < dataPoints.length) {
                                return Padding(
                                  padding: const EdgeInsets.only(top: 8),
                                  child: Text(
                                    '${index + 1}',
                                    style: const TextStyle(
                                      color: AppTheme.textHint,
                                      fontSize: 10,
                                    ),
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
                            reservedSize: 50,
                            getTitlesWidget: (value, meta) {
                              return Text(
                                value.toStringAsFixed(0),
                                style: const TextStyle(
                                  color: AppTheme.textHint,
                                  fontSize: 10,
                                ),
                              );
                            },
                          ),
                        ),
                        borderData: FlBorderData(
                          show: true,
                          border: Border(
                            bottom: BorderSide(
                              color: AppTheme.primaryColor.withOpacity(0.15),
                            ),
                            left: BorderSide(
                              color: AppTheme.primaryColor.withOpacity(0.15),
                            ),
                          ),
                        ),
                      ),
                      lineBarsData: [
                        LineChartBarData(
                          spots: dataPoints,
                          isCurved: true,
                          color: effectiveLineColor,
                          barWidth: 2.5,
                          isStrokeCapRound: true,
                          dotData: FlDotData(
                            show: showDots,
                            getDotPainter: (spot, percent, barData, index) {
                              return FlDotCirclePainter(
                                radius: 4,
                                color: effectiveLineColor,
                                strokeWidth: 2,
                                strokeColor: AppTheme.backgroundColor,
                              );
                            },
                          ),
                          belowBarData: BarAreaData(
                            show: true,
                            color: effectiveLineColor.withOpacity(0.08),
                            gradient: LinearGradient(
                              begin: Alignment.topCenter,
                              end: Alignment.bottomCenter,
                              colors: [
                                effectiveLineColor.withOpacity(0.15),
                                effectiveLineColor.withOpacity(0.0),
                              ],
                            ),
                          ),
                          shadow: Shadow(
                            color: effectiveLineColor.withOpacity(0.3),
                            blurRadius: 8,
                            offset: const Offset(0, 4),
                          ),
                        ),
                      ],
                      minX: 0,
                      maxX: (dataPoints.length - 1).toDouble(),
                      minY: minY,
                      maxY: maxY,
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  double _calculateInterval(int dataLength) {
    if (dataLength <= 10) return 1;
    if (dataLength <= 20) return 2;
    if (dataLength <= 50) return 5;
    return 10;
  }
}

/// 图表类型
enum ChartType { line, area, bar }

/// 多线图表组件 - 用于对比分析
class MultiLineChartWidget extends StatelessWidget {
  final Map<String, List<FlSpot>> lineData;
  final String title;
  final Map<String, Color> lineColors;

  const MultiLineChartWidget({
    super.key,
    required this.lineData,
    required this.title,
    required this.lineColors,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
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
          // 标题
          Text(
            title,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: AppTheme.textPrimary,
                  fontWeight: FontWeight.w600,
                ),
          ),

          // 图例
          const SizedBox(height: 8),
          Wrap(
            spacing: 16,
            children: lineData.keys.map((key) {
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 12,
                    height: 3,
                    decoration: BoxDecoration(
                      color: lineColors[key] ?? AppTheme.primaryColor,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                  const SizedBox(width: 4),
                  Text(
                    key,
                    style: Theme.of(context).textTheme.labelSmall,
                  ),
                ],
              );
            }).toList(),
          ),

          const SizedBox(height: 12),

          // 图表
          SizedBox(
            height: 200,
            child: LineChart(
              LineChartData(
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  getDrawingHorizontalLine: (value) => FlLine(
                    color: AppTheme.primaryColor.withOpacity(0.06),
                    strokeWidth: 1,
                  ),
                ),
                titlesAndBorderData: FlTitlesData(
                  topTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  rightTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  bottomTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 50,
                      getTitlesWidget: (value, meta) {
                        return Text(
                          value.toStringAsFixed(0),
                          style: const TextStyle(
                            color: AppTheme.textHint,
                            fontSize: 10,
                          ),
                        );
                      },
                    ),
                  ),
                  borderData: FlBorderData(
                    show: true,
                    border: Border(
                      bottom: BorderSide(
                        color: AppTheme.primaryColor.withOpacity(0.15),
                      ),
                      left: BorderSide(
                        color: AppTheme.primaryColor.withOpacity(0.15),
                      ),
                    ),
                  ),
                ),
                lineBarsData: lineData.entries.map((entry) {
                  return LineChartBarData(
                    spots: entry.value,
                    isCurved: true,
                    color: lineColors[entry.key] ?? AppTheme.primaryColor,
                    barWidth: 2,
                    isStrokeCapRound: true,
                    dotData: FlDotData(show: false),
                    belowBarData: BarAreaData(show: false),
                  );
                }).toList(),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
