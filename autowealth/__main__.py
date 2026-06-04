"""
AutoWealth AI 鍛戒护琛屽伐鍏?"""
import argparse
import json
import logging
import sys

from autowealth import AutoWealthEngine

# 閰嶇疆鏃ュ織
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("autowealth.cli")


def setup_parser() -> argparse.ArgumentParser:
    """璁剧疆鍛戒护琛屽弬鏁拌В鏋愬櫒"""
    parser = argparse.ArgumentParser(
        description="AutoWealth AI - 鏅鸿兘鎶曡祫鍒嗘瀽宸ュ叿",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
绀轰緥:
  python -m autowealth --symbol AAPL          # 鍒嗘瀽鍗曞彧鑲＄エ
  python -m autowealth --batch AAPL GOOGL MSFT # 鎵归噺鍒嗘瀽
  python -m autowealth --market               # 鏌ョ湅甯傚満姒傝
  python -m autowealth --symbol AAPL --json   # 杈撳嚭JSON鏍煎紡
        """,
    )

    parser.add_argument(
        "--symbol",
        type=str,
        help="鍒嗘瀽鍗曞彧鑲＄エ (渚嬪: AAPL)",
    )

    parser.add_argument(
        "--batch",
        nargs="+",
        help="鎵归噺鍒嗘瀽澶氬彧鑲＄エ (渚嬪: AAPL GOOGL MSFT)",
    )

    parser.add_argument(
        "--market",
        action="store_true",
        help="鏌ョ湅甯傚満姒傝",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="浠SON鏍煎紡杈撳嚭缁撴灉",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="鏄剧ず璇︾粏鏃ュ織",
    )

    return parser


def print_analysis_result(result: dict, use_json: bool = False):
    """鎵撳嵃鍒嗘瀽缁撴灉"""
    if use_json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return

    if not result.get("success"):
        print(f"鉂?鍒嗘瀽澶辫触: {result.get('error', '鏈煡閿欒')}")
        return

    print("\n" + "=" * 60)
    print(f"馃搳 {result['symbol']} 鍒嗘瀽缁撴灉")
    print("=" * 60)

    # 缁煎悎鍐崇瓥
    decision = result["decision"]
    signal_emoji = "馃煝" if decision["signal_type"] == "buy" else "馃敶" if decision["signal_type"] == "sell" else "馃煛"
    print(f"\n{signal_emoji} 缁煎悎寤鸿: {decision['signal_type'].upper()}")
    print(f"馃幆 缃俊搴? {decision['confidence']}%")

    if decision.get("target_price"):
        print(f"馃幆 鐩爣浠? ${decision['target_price']}")
    if decision.get("stop_loss"):
        print(f"馃洃 姝㈡崯浠? ${decision['stop_loss']}")

    # 鍚勬櫤鑳戒綋淇″彿
    print("\n馃 鍚勬櫤鑳戒綋鍒嗘瀽缁撴灉:")
    for agent_name, signal in result.get("individual_signals", {}).items():
        emoji = "馃煝" if signal.signal_type == "buy" else "馃敶" if signal.signal_type == "sell" else "馃煛"
        print(f"  {emoji} {agent_name}: {signal.signal_type.upper()} (缃俊搴? {signal.confidence}%)")

    # 璇︾粏鐞嗙敱
    print(f"\n馃挕 鍐崇瓥鐞嗙敱:\n{decision['reasoning']}")

    print("=" * 60)


def print_batch_result(result: dict, use_json: bool = False):
    """鎵撳嵃鎵归噺鍒嗘瀽缁撴灉"""
    if use_json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return

    print("\n" + "=" * 60)
    print("馃搳 鎵归噺鍒嗘瀽缁撴灉")
    print("=" * 60)

    summary = result["summary"]
    print(f"\n鎬昏: {summary['total']} 鍙偂绁?)
    print(f"鎴愬姛: {summary['success']} 鍙?)
    print(f"涔板叆鎺ㄨ崘: {summary['buy_count']} 鍙?)
    print(f"鍗栧嚭鎺ㄨ崘: {summary['sell_count']} 鍙?)
    print(f"瑙傛湜鎺ㄨ崘: {summary['hold_count']} 鍙?)

    # 涔板叆鎺ㄨ崘
    if result["recommendations"]["buy"]:
        print("\n馃煝 涔板叆鎺ㄨ崘 (鎸夌疆淇″害鎺掑簭):")
        for symbol, confidence in result["recommendations"]["buy"]:
            print(f"  鈥?{symbol}: 缃俊搴?{confidence}%")

    # 鍗栧嚭鎺ㄨ崘
    if result["recommendations"]["sell"]:
        print("\n馃敶 鍗栧嚭鎺ㄨ崘 (鎸夌疆淇″害鎺掑簭):")
        for symbol, confidence in result["recommendations"]["sell"]:
            print(f"  鈥?{symbol}: 缃俊搴?{confidence}%")

    # 瑙傛湜鎺ㄨ崘
    if result["recommendations"]["hold"]:
        print("\n馃煛 瑙傛湜鎺ㄨ崘:")
        for symbol, confidence in result["recommendations"]["hold"]:
            print(f"  鈥?{symbol}: 缃俊搴?{confidence}%")

    print("=" * 60)


def print_market_overview(result: dict, use_json: bool = False):
    """鎵撳嵃甯傚満姒傝"""
    if use_json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return

    if not result.get("success"):
        print(f"鉂?鑾峰彇甯傚満姒傝澶辫触: {result.get('error')}")
        return

    print("\n" + "=" * 60)
    print("馃實 鍏ㄧ悆甯傚満姒傝")
    print("=" * 60)

    for symbol, data in result["indices"].items():
        emoji = "馃煝" if data["change_pct"] > 0 else "馃敶"
        print(f"{emoji} {symbol}: {data['price']:.2f} ({data['change_pct']:+.2f}%)")

    print("=" * 60)


def main():
    """涓诲嚱鏁?""
    parser = setup_parser()
    args = parser.parse_args()

    # 璁剧疆鏃ュ織绾у埆
    if args.verbose:
        logging.getLogger("autowealth").setLevel(logging.DEBUG)

    # 鍒濆鍖栧紩鎿?    engine = AutoWealthEngine()

    try:
        if args.symbol:
            # 鍗曡偂鍒嗘瀽
            result = engine.analyze(args.symbol.upper())
            print_analysis_result(result, args.json)

        elif args.batch:
            # 鎵归噺鍒嗘瀽
            symbols = [s.upper() for s in args.batch]
            result = engine.analyze_batch(symbols)
            print_batch_result(result, args.json)

        elif args.market:
            # 甯傚満姒傝
            result = engine.get_market_overview()
            print_market_overview(result, args.json)

        else:
            parser.print_help()

    except KeyboardInterrupt:
        print("\n\n鈿狅笍 鐢ㄦ埛涓柇")
        sys.exit(1)
    except Exception as e:
        logger.error(f"杩愯鍑洪敊: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
