import 'package:flutter/material.dart';
import '../../config/theme.dart';

/// 指标卡片组件 - 显示各种金融指标
class MetricCard extends StatelessWidget {
  final String title;
  final String value;
  final String? subtitle;
  final IconData icon;
  final Color? iconColor;
  final Color? valueColor;
  final VoidCallback? onTap;
  final MetricTrend? trend;
  final double? trendValue;

  const MetricCard({
    super.key,
    required this.title,
    required this.value,
    this.subtitle,
    required this.icon,
    this.iconColor,
    this.valueColor,
    this.onTap,
    this.trend,
    this.trendValue,
  });

  @override
  Widget build(BuildContext context) {
    final effectiveIconColor = iconColor ?? AppTheme.primaryColor;
    final effectiveValueColor = valueColor ?? AppTheme.textPrimary;

    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppTheme.cardColor,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: effectiveIconColor.withOpacity(0.15),
            width: 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 标题行
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: effectiveIconColor.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Icon(
                        icon,
                        size: 20,
                        color: effectiveIconColor,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Text(
                      title,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: AppTheme.textSecondary,
                          ),
                    ),
                  ],
                ),
                // 趋势指示器
                if (trend != null)
                  _buildTrendIndicator(context, trend!, trendValue),
              ],
            ),

            const SizedBox(height: 12),

            // 主要数值
            Text(
              value,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    color: effectiveValueColor,
                    fontWeight: FontWeight.bold,
                  ),
            ),

            // 副标题
            if (subtitle != null) ...[
              const SizedBox(height: 4),
              Text(
                subtitle!,
                style: Theme.of(context).textTheme.bodySmall,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildTrendIndicator(
    BuildContext context,
    MetricTrend trend,
    double? value,
  ) {
    final isUp = trend == MetricTrend.up;
    final isDown = trend == MetricTrend.down;
    final color = isUp
        ? AppTheme.buyColor
        : isDown
            ? AppTheme.sellColor
            : AppTheme.holdColor;
    final icon = isUp
        ? Icons.trending_up
        : isDown
            ? Icons.trending_down
            : Icons.trending_flat;

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: color),
        if (value != null) ...[
          const SizedBox(width: 2),
          Text(
            '${isUp ? '+' : ''}${value.toStringAsFixed(1)}%',
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: color,
                  fontWeight: FontWeight.bold,
                ),
          ),
        ],
      ],
    );
  }
}

/// 趋势枚举
enum MetricTrend { up, down, flat }

/// 紧凑型指标卡片 - 用于网格布局
class CompactMetricCard extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;
  final MetricTrend? trend;
  final double? trendValue;

  const CompactMetricCard({
    super.key,
    required this.label,
    required this.value,
    this.color,
    this.trend,
    this.trendValue,
  });

  @override
  Widget build(BuildContext context) {
    final effectiveColor = color ?? AppTheme.primaryColor;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.cardColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: effectiveColor.withOpacity(0.1),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: AppTheme.textHint,
                ),
          ),
          const SizedBox(height: 6),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                value,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: effectiveColor,
                      fontWeight: FontWeight.bold,
                    ),
              ),
              if (trend != null && trendValue != null)
                Text(
                  '${trend == MetricTrend.up ? '+' : ''}${trendValue!.toStringAsFixed(1)}%',
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                        color: trend == MetricTrend.up
                            ? AppTheme.buyColor
                            : trend == MetricTrend.down
                                ? AppTheme.sellColor
                                : AppTheme.holdColor,
                        fontWeight: FontWeight.bold,
                      ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}
