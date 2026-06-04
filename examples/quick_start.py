"""
AutoWealth AI 蹇€熷叆闂ㄧず渚?"""
from autowealth import AutoWealthEngine


def analyze_single_stock():
    """鍒嗘瀽鍗曞彧鑲＄エ"""
    print("=" * 60)
    print("绀轰緥1: 鍒嗘瀽鍗曞彧鑲＄エ")
    print("=" * 60)

    # 鍒濆鍖栧紩鎿?    engine = AutoWealthEngine()

    # 鍒嗘瀽鑻规灉鑲＄エ
    result = engine.analyze("AAPL")

    if result["success"]:
        print(f"\n馃搳 鑲＄エ浠ｇ爜: {result['symbol']}")
        print(f"馃搱 缁煎悎寤鸿: {result['decision']['signal_type'].upper()}")
        print(f"馃幆 缃俊搴? {result['decision']['confidence']}%")

        if result["decision"]["target_price"]:
            print(f"馃幆 鐩爣浠? ${result['decision']['target_price']}")
        if result["decision"]["stop_loss"]:
            print(f"馃洃 姝㈡崯浠? ${result['decision']['stop_loss']}")

        print(f"\n馃挕 鍐崇瓥鐞嗙敱:\n{result['decision']['reasoning']}")

        # 鎵撳嵃鍚勬櫤鑳戒綋淇″彿
        print("\n馃 鍚勬櫤鑳戒綋鍒嗘瀽缁撴灉:")
        for agent_name, signal in result["individual_signals"].items():
            emoji = "馃煝" if signal.signal_type == "buy" else "馃敶" if signal.signal_type == "sell" else "馃煛"
            print(f"  {emoji} {agent_name}: {signal.signal_type.upper()} (缃俊搴? {signal.confidence}%)")
    else:
        print(f"鉂?鍒嗘瀽澶辫触: {result['error']}")


def analyze_multiple_stocks():
    """鎵归噺鍒嗘瀽澶氬彧鑲＄エ"""
    print("\n" + "=" * 60)
    print("绀轰緥2: 鎵归噺鍒嗘瀽澶氬彧鑲＄エ")
    print("=" * 60)

    engine = AutoWealthEngine()

    # 鍒嗘瀽绉戞妧宸ㄥご
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "META"]
    batch_result = engine.analyze_batch(symbols)

    print(f"\n馃搳 鍒嗘瀽瀹屾垚: {batch_result['summary']['success']}/{batch_result['summary']['total']} 鍙偂绁?)

    # 鎵撳嵃涔板叆鎺ㄨ崘
    if batch_result["recommendations"]["buy"]:
        print("\n馃煝 涔板叆鎺ㄨ崘 (鎸夌疆淇″害鎺掑簭):")
        for symbol, confidence in batch_result["recommendations"]["buy"]:
            print(f"  鈥?{symbol}: 缃俊搴?{confidence}%")

    # 鎵撳嵃鍗栧嚭鎺ㄨ崘
    if batch_result["recommendations"]["sell"]:
        print("\n馃敶 鍗栧嚭鎺ㄨ崘 (鎸夌疆淇″害鎺掑簭):")
        for symbol, confidence in batch_result["recommendations"]["sell"]:
            print(f"  鈥?{symbol}: 缃俊搴?{confidence}%")

    # 鎵撳嵃瑙傛湜鎺ㄨ崘
    if batch_result["recommendations"]["hold"]:
        print("\n馃煛 瑙傛湜鎺ㄨ崘:")
        for symbol, confidence in batch_result["recommendations"]["hold"]:
            print(f"  鈥?{symbol}: 缃俊搴?{confidence}%")


def market_overview():
    """鑾峰彇甯傚満姒傝"""
    print("\n" + "=" * 60)
    print("绀轰緥3: 甯傚満姒傝")
    print("=" * 60)

    engine = AutoWealthEngine()
    overview = engine.get_market_overview()

    if overview["success"]:
        print("\n馃實 鍏ㄧ悆甯傚満鎸囨暟:")
        for symbol, data in overview["indices"].items():
            emoji = "馃煝" if data["change_pct"] > 0 else "馃敶"
            print(f"  {emoji} {symbol}: {data['price']:.2f} ({data['change_pct']:+.2f}%)")
    else:
        print(f"鉂?鑾峰彇甯傚満姒傝澶辫触: {overview.get('error')}")


def portfolio_analysis():
    """鎶曡祫缁勫悎鍒嗘瀽"""
    print("\n" + "=" * 60)
    print("绀轰緥4: 鎶曡祫缁勫悎鍒嗘瀽")
    print("=" * 60)

    engine = AutoWealthEngine()

    # 妯℃嫙鎸佷粨
    holdings = [
        {"symbol": "AAPL", "quantity": 100, "cost_basis": 150.0},
        {"symbol": "GOOGL", "quantity": 50, "cost_basis": 100.0},
        {"symbol": "MSFT", "quantity": 75, "cost_basis": 300.0},
    ]

    portfolio = engine.get_portfolio_analysis(holdings)

    print(f"\n馃捈 鎶曡祫缁勫悎鎬昏:")
    print(f"  鎬诲競鍊? ${portfolio['total_value']:,.2f}")
    print(f"  鎬荤泩浜? ${portfolio['total_gain_loss']:,.2f}")
    print(f"  鏀剁泭鐜? {portfolio['return_pct']:.2f}%")

    print(f"\n馃搳 鎸佷粨鍒嗘瀽:")
    for holding in portfolio["holdings"]:
        symbol = holding["symbol"]
        decision = holding["decision"]
        signal = decision.get("signal_type", "hold").upper()
        emoji = "馃煝" if signal == "BUY" else "馃敶" if signal == "SELL" else "馃煛"
        print(f"  {emoji} {symbol}: {signal} (缃俊搴? {decision.get('confidence', 0)}%)")


if __name__ == "__main__":
    print("馃殌 AutoWealth AI 蹇€熷叆闂ㄧず渚?)
    print("=" * 60)

    try:
        analyze_single_stock()
        analyze_multiple_stocks()
        market_overview()
        portfolio_analysis()

        print("\n" + "=" * 60)
        print("鉁?鎵€鏈夌ず渚嬭繍琛屽畬鎴?")
        print("=" * 60)

    except Exception as e:
        print(f"\n鉂?杩愯鍑洪敊: {e}")
        import traceback
        traceback.print_exc()
