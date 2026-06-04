"""
AutoWealth AI 命令行工具
"""
import argparse
import json
import logging
import sys

from autowealth import AutoWealthEngine

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("autowealth.cli")


def setup_parser() -> argparse.ArgumentParser:
    """设置命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="AutoWealth AI - 智能投资分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m autowealth --symbol AAPL          # 分析单只股票
  python -m autowealth --batch AAPL GOOGL MSFT # 批量分析
  python -m autowealth --market               # 查看市场概览
  python -m autowealth --symbol AAPL --json   # 输出JSON格式
        """,
    )

    parser.add_argument(
        "--symbol",
        type=str,
        help="分析单只股票 (例如: AAPL)",
    )

    parser.add_argument(
        "--batch",
        nargs="+",
        help="批量分析多只股票 (例如: AAPL GOOGL MSFT)",
    )

    parser.add_argument(
        "--market",
        action="store_true",
        help="查看市场概览",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="以JSON格式输出结果",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示详细日志",
    )

    return parser


def print_analysis_result(result: dict, use_json: bool = False):
    """打印分析结果"""
    if use_json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return

    if not result.get("success"):
        print(f"❌ 分析失败: {result.get('error', '未知错误')}")
        return

    print("\n" + "=" * 60)
    print(f"📊 {result['symbol']} 分析结果")
    print("=" * 60)

    # 综合决策
    decision = result["decision"]
    signal_emoji = "🟢" if decision["signal_type"] == "buy" else "🔴" if decision["signal_type"] == "sell" else "🟡"
    print(f"\n{signal_emoji} 综合建议: {decision['signal_type'].upper()}")
    print(f"🎯 置信度: {decision['confidence']}%")

    if decision.get("target_price"):
        print(f"🎯 目标价: ${decision['target_price']}")
    if decision.get("stop_loss"):
        print(f"🛑 止损价: ${decision['stop_loss']}")

    # 各智能体信号
    print("\n🤖 各智能体分析结果:")
    for agent_name, signal in result.get("individual_signals", {}).items():
        emoji = "🟢" if signal.signal_type == "buy" else "🔴" if signal.signal_type == "sell" else "🟡"
        print(f"  {emoji} {agent_name}: {signal.signal_type.upper()} (置信度: {signal.confidence}%)")

    # 详细理由
    print(f"\n💡 决策理由:\n{decision['reasoning']}")

    print("=" * 60)


def print_batch_result(result: dict, use_json: bool = False):
    """打印批量分析结果"""
    if use_json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return

    print("\n" + "=" * 60)
    print("📊 批量分析结果")
    print("=" * 60)

    summary = result["summary"]
    print(f"\n总计: {summary['total']} 只股票")
    print(f"成功: {summary['success']} 只")
    print(f"买入推荐: {summary['buy_count']} 只")
    print(f"卖出推荐: {summary['sell_count']} 只")
    print(f"观望推荐: {summary['hold_count']} 只")

    # 买入推荐
    if result["recommendations"]["buy"]:
        print("\n🟢 买入推荐 (按置信度排序):")
        for symbol, confidence in result["recommendations"]["buy"]:
            print(f"  • {symbol}: 置信度 {confidence}%")

    # 卖出推荐
    if result["recommendations"]["sell"]:
        print("\n🔴 卖出推荐 (按置信度排序):")
        for symbol, confidence in result["recommendations"]["sell"]:
            print(f"  • {symbol}: 置信度 {confidence}%")

    # 观望推荐
    if result["recommendations"]["hold"]:
        print("\n🟡 观望推荐:")
        for symbol, confidence in result["recommendations"]["hold"]:
            print(f"  • {symbol}: 置信度 {confidence}%")

    print("=" * 60)


def print_market_overview(result: dict, use_json: bool = False):
    """打印市场概览"""
    if use_json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return

    if not result.get("success"):
        print(f"❌ 获取市场概览失败: {result.get('error')}")
        return

    print("\n" + "=" * 60)
    print("🌍 全球市场概览")
    print("=" * 60)

    for symbol, data in result["indices"].items():
        emoji = "🟢" if data["change_pct"] > 0 else "🔴"
        print(f"{emoji} {symbol}: {data['price']:.2f} ({data['change_pct']:+.2f}%)")

    print("=" * 60)


def main():
    """主函数"""
    parser = setup_parser()
    args = parser.parse_args()

    # 设置日志级别
    if args.verbose:
        logging.getLogger("autowealth").setLevel(logging.DEBUG)

    # 初始化引擎
    engine = AutoWealthEngine()

    try:
        if args.symbol:
            # 单股分析
            result = engine.analyze(args.symbol.upper())
            print_analysis_result(result, args.json)

        elif args.batch:
            # 批量分析
            symbols = [s.upper() for s in args.batch]
            result = engine.analyze_batch(symbols)
            print_batch_result(result, args.json)

        elif args.market:
            # 市场概览
            result = engine.get_market_overview()
            print_market_overview(result, args.json)

        else:
            parser.print_help()

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"运行出错: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
