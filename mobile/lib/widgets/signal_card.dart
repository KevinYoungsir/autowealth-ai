import 'package:flutter/material.dart';
import '../../config/theme.dart';

/// 信号卡片组件 - 显示买入/卖出/观望信号
class SignalCard extends StatelessWidget {
  final String signal;
  final double confidence;
  final String? agentName;
  final String? reasoning;
  final double? targetPrice;
  final double? stopLoss;
  final VoidCallback? onTap;

  const SignalCard({
    super.key,
    required this.signal,
    required this.confidence,
    this.agentName,
    this.reasoning,
    this.targetPrice,
    this.stopLoss,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final color = AppTheme.signalColor(signal);
    final label = AppTheme.signalLabel(signal);

    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppTheme.cardColor,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: color.withOpacity(0.3),
            width: 1.5,
          ),
          boxShadow: [
            BoxShadow(
              color: color.withOpacity(0.1),
              blurRadius: 12,
              spreadRadius: 2,
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 顶部：信号标签 + 置信度
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: color.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: color.withOpacity(0.4)),
                  ),
                  child: Text(
                    label,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          color: color,
                          fontWeight: FontWeight.bold,
                        ),
                  ),
                ),
                Row(
                  children: [
                    Text(
                      '置信度',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      '${(confidence * 100).toStringAsFixed(0)}%',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: color,
                            fontWeight: FontWeight.bold,
                          ),
                    ),
                  ],
                ),
              ],
            ),

            // 置信度进度条
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: confidence,
                backgroundColor: AppTheme.surfaceColor,
                valueColor: AlwaysStoppedAnimation<Color>(color),
                minHeight: 6,
              ),
            ),

            // 智能体名称
            if (agentName != null) ...[
              const SizedBox(height: 12),
              Row(
                children: [
                  Icon(
                    Icons.smart_toy_outlined,
                    size: 16,
                    color: AppTheme.secondaryColor,
                  ),
                  const SizedBox(width: 6),
                  Text(
                    agentName!,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: AppTheme.secondaryColor,
                        ),
                  ),
                ],
              ),
            ],

            // 目标价和止损价
            if (targetPrice != null || stopLoss != null) ...[
              const SizedBox(height: 12),
              Row(
                children: [
                  if (targetPrice != null) ...[
                    _buildPriceTag(
                      context,
                      label: '目标价',
                      value: targetPrice!.toStringAsFixed(2),
                      color: AppTheme.buyColor,
                    ),
                    const SizedBox(width: 12),
                  ],
                  if (stopLoss != null)
                    _buildPriceTag(
                      context,
                      label: '止损价',
                      value: stopLoss!.toStringAsFixed(2),
                      color: AppTheme.sellColor,
                    ),
                ],
              ),
            ],

            // 分析理由
            if (reasoning != null && reasoning!.isNotEmpty) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppTheme.surfaceColor,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  reasoning!,
                  style: Theme.of(context).textTheme.bodySmall,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildPriceTag(
    BuildContext context, {
    required String label,
    required String value,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: Theme.of(context)
                .textTheme
                .labelSmall
                ?.copyWith(color: AppTheme.textHint),
          ),
          Text(
            '\$$value',
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  color: color,
                  fontWeight: FontWeight.bold,
                ),
          ),
        ],
      ),
    );
  }
}
