#!/usr/bin/env python3
"""
AutoWealth AI 交互式演示脚本

命令行交互式Demo，展示所有核心功能。
使用模拟数据，无需网络连接即可运行。

功能菜单：
  1. 单股分析
  2. 批量分析
  3. 组合优化
  4. 回测
  5. 预警系统
  6. 社交情绪分析
  7. ML预测
  8. 退出
"""

import sys
import time

# 尝试导入 rich 库做美化，不可用则回退到普通 print
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box

    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from autowealth.core.demo_data import DemoDataGenerator
from autowealth.core.analyzer import TechnicalAnalyzer, FundamentalAnalyzer
from autowealth.core.backtest import BacktestEngine
from autowealth.core.portfolio_optimizer import PortfolioOptimizer
from autowealth.ml.predictor import MLPredictor
from autowealth.sentiment.social_analyzer import SocialSentimentAnalyzer
from autowealth.alerts.monitor import AlertMonitor

# ============================================================
# 美化输出工具函数
# ============================================================

def print_title(text: str):
    """打印标题"""
    if HAS_RICH:
        console.print(Panel(text, style="bold cyan", box=box.DOUBLE))
    else:
        print(f"\n{'=' * 60}")
        print(f"  {text}")
        print(f"{'=' * 60}")


def print_subtitle(text: str):
    """打印子标题"""
    if HAS_RICH:
        console.print(f"\n[bold yellow]{text}[/bold yellow]")
    else:
        print(f"\n--- {text} ---")


def print_success(text: str):
    """打印成功信息"""
    if HAS_RICH:
        console.print(f"[green]{text}[/green]")
    else:
        print(f"[OK] {text}")


def print_error(text: str):
    """打印错误信息"""
    if HAS_RICH:
        console.print(f"[red]{text}[/red]")
    else:
        print(f"[ERROR] {text}")


def print_info(text: str):
    """打印信息"""
    if HAS_RICH:
        console.print(f"[blue]{text}[/blue]")
    else:
        print(f"[INFO] {text}")


def print_table(headers: list, rows: list, title: str = ""):
    """打印表格"""
    if HAS_RICH:
        table = Table(title=title, box=box.ROUNDED)
        for header in headers:
            table.add_column(header, justify="center")
        for row in rows:
            table.add_row(*[str(v) for v in row])
        console.print(table)
    else:
        if title:
            print(f"\n  {title}")
        # 计算每列宽度
        col_widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, v in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(v)))
        # 打印表头
        header_line = " | ".join(str(h).center(col_widths[i]) for i, h in enumerate(headers))
        print(f"  {header_line}")
        print(f"  {'-+-'.join('-' * w for w in col_widths)}")
        # 打印数据行
        for row in rows:
            row_line = " | ".join(str(v).center(col_widths[i]) for i, v in enumerate(row))
            print(f"  {row_line}")


def print_key_value(pairs: list):
    """打印键值对"""
    if HAS_RICH:
        for key, value in pairs:
            console.print(f"  [cyan]{key}:[/cyan] {value}")
    else:
        for key, value in pairs:
            print(f"  {key}: {value}")


# ============================================================
# 演示功能函数
# ============================================================

def demo_single_stock_analysis(gen: DemoDataGenerator):
    """演示1: 单股分析"""
    print_title("单股分析演示")

    symbol = "AAPL"
    print_info(f"正在分析 {symbol} ...")

    # 生成模拟数据
    data = gen.generate_stock_data(symbol, days=365)
    stock_info = gen.generate_stock_info(symbol)

    # 技术分析
    print_subtitle("技术分析指标")
    ta = TechnicalAnalyzer()
    analyzed = ta.full_analysis(data)
    latest = analyzed.iloc[-1]

    tech_rows = [
        ["MA5", f"{latest.get('MA5', 0):.2f}"],
        ["MA20", f"{latest.get('MA20', 0):.2f}"],
        ["MA60", f"{latest.get('MA60', 0):.2f}"],
        ["RSI(14)", f"{latest.get('RSI', 0):.2f}"],
        ["MACD", f"{latest.get('MACD', 0):.4f}"],
        ["MACD Signal", f"{latest.get('MACD_Signal', 0):.4f}"],
        ["BB Upper", f"{latest.get('BB_Upper', 0):.2f}"],
        ["BB Lower", f"{latest.get('BB_Lower', 0):.2f}"],
        ["ATR(14)", f"{latest.get('ATR14', 0):.4f}"],
    ]
    print_table(["指标", "数值"], tech_rows, f"{symbol} 技术指标")

    # 基本面分析
    print_subtitle("基本面分析")
    fa = FundamentalAnalyzer()
    valuation = fa.analyze_valuation(stock_info)
    growth = fa.analyze_growth(data)

    print_key_value([
        ("股票名称", stock_info["name"]),
        ("行业", stock_info["sector"]),
        ("市值", f"${stock_info['market_cap']:,.0f}"),
        ("市盈率(PE)", f"{stock_info['pe_ratio']:.2f}"),
        ("市净率(PB)", f"{stock_info['pb_ratio']:.2f}"),
        ("股息率", f"{stock_info['dividend_yield']:.2%}"),
        ("估值评分", f"{valuation['valuation_score']:.1f}/100"),
        ("成长评分", f"{growth['growth_score']:.1f}/100"),
        ("趋势判断", growth["trend"]),
        ("1月收益率", f"{growth['return_1m']:.2f}%"),
        ("3月收益率", f"{growth['return_3m']:.2f}%"),
    ])

    # 综合建议
    print_subtitle("综合建议")
    overall_score = (valuation["valuation_score"] + growth["growth_score"]) / 2
    if overall_score > 60:
        signal = "买入 (BUY)"
        color = "green"
    elif overall_score < 40:
        signal = "卖出 (SELL)"
        color = "red"
    else:
        signal = "观望 (HOLD)"
        color = "yellow"

    if HAS_RICH:
        console.print(f"\n  [{color}]综合评分: {overall_score:.1f}/100  建议: {signal}[/{color}]")
    else:
        print(f"\n  综合评分: {overall_score:.1f}/100  建议: {signal}")

    print_success(f"{symbol} 分析完成!")


def demo_batch_analysis(gen: DemoDataGenerator):
    """演示2: 批量分析"""
    print_title("批量分析演示")

    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM"]
    print_info(f"正在批量分析 {len(symbols)} 只股票 ...")

    results = []
    for symbol in symbols:
        data = gen.generate_stock_data(symbol, days=365)
        stock_info = gen.generate_stock_info(symbol)

        fa = FundamentalAnalyzer()
        valuation = fa.analyze_valuation(stock_info)
        growth = fa.analyze_growth(data)
        overall = (valuation["valuation_score"] + growth["growth_score"]) / 2

        if overall > 60:
            signal = "BUY"
        elif overall < 40:
            signal = "SELL"
        else:
            signal = "HOLD"

        results.append([symbol, stock_info["name"], f"${stock_info['current_price']:.2f}",
                        f"{stock_info['pe_ratio']:.1f}", f"{overall:.1f}", signal])

    # 按评分排序
    results.sort(key=lambda x: float(x[4]), reverse=True)

    print_table(["代码", "名称", "价格", "PE", "评分", "建议"], results, "批量分析结果")

    # 统计
    buy_count = sum(1 for r in results if r[5] == "BUY")
    sell_count = sum(1 for r in results if r[5] == "SELL")
    hold_count = sum(1 for r in results if r[5] == "HOLD")

    print_subtitle("推荐汇总")
    print_key_value([
        ("买入推荐", f"{buy_count} 只"),
        ("卖出推荐", f"{sell_count} 只"),
        ("观望推荐", f"{hold_count} 只"),
    ])

    print_success("批量分析完成!")


def demo_portfolio_optimization(gen: DemoDataGenerator):
    """演示3: 组合优化"""
    print_title("投资组合优化演示")

    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "NVDA"]
    print_info(f"正在优化包含 {len(symbols)} 只股票的投资组合 ...")

    # 生成数据并计算收益率
    price_data = {}
    for symbol in symbols:
        price_data[symbol] = gen.generate_stock_data(symbol, days=365)

    returns = pd.DataFrame({
        symbol: data["Close"].pct_change().dropna()
        for symbol, data in price_data.items()
    })

    # 组合优化
    optimizer = PortfolioOptimizer(returns)

    # 最大夏普比率组合
    print_subtitle("最大夏普比率组合")
    max_sharpe = optimizer.max_sharpe_ratio()
    weight_rows = []
    for symbol, weight in max_sharpe["weights"].items():
        weight_rows.append([symbol, f"{weight:.2%}"])
    print_table(["股票", "权重"], weight_rows, "最优权重分配")

    print_key_value([
        ("预期年化收益", f"{max_sharpe['expected_return']:.2%}"),
        ("年化波动率", f"{max_sharpe['volatility']:.2%}"),
        ("夏普比率", f"{max_sharpe['sharpe_ratio']:.4f}"),
    ])

    # 最小方差组合
    print_subtitle("最小方差组合")
    min_var = optimizer.min_variance_portfolio()
    weight_rows2 = []
    for symbol, weight in min_var["weights"].items():
        weight_rows2.append([symbol, f"{weight:.2%}"])
    print_table(["股票", "权重"], weight_rows2, "最小风险权重分配")

    print_key_value([
        ("预期年化收益", f"{min_var['expected_return']:.2%}"),
        ("年化波动率", f"{min_var['volatility']:.2%}"),
        ("夏普比率", f"{min_var['sharpe_ratio']:.4f}"),
    ])

    # 资金分配
    print_subtitle("资金分配方案 (总资金: $100,000)")
    allocation = optimizer.allocate_weights(symbols, total_value=100000)
    alloc_rows = []
    for symbol, amount in allocation.items():
        alloc_rows.append([symbol, f"${amount:,.2f}"])
    print_table(["股票", "分配金额"], alloc_rows)

    print_success("组合优化完成!")


def demo_backtest(gen: DemoDataGenerator):
    """演示4: 回测"""
    print_title("策略回测演示")

    symbol = "AAPL"
    print_info(f"正在回测 {symbol} 的双均线策略 ...")

    # 生成数据
    data = gen.generate_stock_data(symbol, days=365)

    # 生成交易信号
    signals = gen.generate_trading_signals(data)

    # 运行回测
    engine = BacktestEngine(initial_capital=100000)
    engine.run_strategy(data, signals, commission=0.001)

    # 获取绩效指标
    metrics = engine.get_performance_metrics()

    print_subtitle("回测绩效指标")
    print_key_value([
        ("初始资金", f"${metrics['initial_capital']:,.2f}"),
        ("最终资金", f"${metrics['final_equity']:,.2f}"),
        ("总收益率", f"{metrics['total_return']:.2%}"),
        ("年化收益率", f"{metrics['annualized_return']:.2%}"),
        ("最大回撤", f"{metrics['max_drawdown']:.2%}"),
        ("夏普比率", f"{metrics['sharpe_ratio']:.4f}"),
        ("胜率", f"{metrics['win_rate']:.2%}"),
        ("交易次数", f"{metrics['trade_count']}"),
    ])

    # 交易历史
    trades = engine.get_trade_history()
    if trades:
        print_subtitle("交易记录 (最近10笔)")
        trade_rows = []
        for t in trades[-10:]:
            if t["type"] == "buy":
                trade_rows.append([
                    "BUY", f"${t['price']:.2f}", f"{t['shares']:.0f}",
                    "-", "-"
                ])
            else:
                pnl_str = f"${t.get('pnl', 0):,.2f}"
                ret_str = f"{t.get('return_pct', 0):.2f}%"
                trade_rows.append([
                    "SELL", f"${t['price']:.2f}", f"{t['shares']:.0f}",
                    pnl_str, ret_str
                ])
        print_table(["类型", "价格", "数量", "盈亏", "收益率"], trade_rows)

    print_success("回测完成!")


def demo_alert_system(gen: DemoDataGenerator):
    """演示5: 预警系统"""
    print_title("预警系统演示")

    symbol = "AAPL"
    print_info(f"正在设置 {symbol} 的预警规则 ...")

    # 生成数据
    data = gen.generate_stock_data(symbol, days=365)

    # 添加技术指标
    ta = TechnicalAnalyzer()
    data = ta.calculate_macd(data)
    data = ta.calculate_volume_indicators(data)

    # 创建预警监控器
    monitor = AlertMonitor()

    # 添加预警规则
    print_subtitle("添加预警规则")
    rules = [
        ("price_above", {"threshold": data["Close"].iloc[-1] * 1.1,
                         "message": f"{symbol} 价格突破上方目标价"}),
        ("price_below", {"threshold": data["Close"].iloc[-1] * 0.9,
                         "message": f"{symbol} 价格跌破支撑位"}),
        ("pct_change", {"threshold": 3.0, "direction": "any",
                        "message": f"{symbol} 单日涨跌幅超过3%"}),
        ("volume_spike", {"multiplier": 2.0,
                          "message": f"{symbol} 成交量异常放大"}),
        ("indicator_cross", {"indicator": "MACD", "cross_type": "golden",
                             "message": f"{symbol} MACD金叉信号"}),
    ]

    rule_rows = []
    for rule_type, params in rules:
        rule_id = monitor.add_rule(symbol, rule_type, params)
        rule_rows.append([rule_type, str(params.get("threshold", params.get("multiplier", "N/A"))),
                          "活跃"])

    print_table(["规则类型", "参数", "状态"], rule_rows, "预警规则列表")

    # 检查预警
    print_subtitle("检查预警触发")
    alerts = monitor.check_alerts(data)

    if alerts:
        alert_rows = []
        for alert in alerts:
            alert_rows.append([
                alert.symbol,
                alert.rule_type if hasattr(alert, 'rule_type') else "N/A",
                alert.severity,
                alert.message[:50],
            ])
        print_table(["标的", "类型", "级别", "消息"], alert_rows, "触发的预警")
    else:
        print_info("当前数据未触发任何预警规则")

    # 显示活跃规则
    active_rules = monitor.get_active_rules()
    print_key_value([("活跃规则数量", str(len(active_rules)))])

    print_success("预警系统演示完成!")


def demo_social_sentiment(gen: DemoDataGenerator):
    """演示6: 社交情绪分析"""
    print_title("社交情绪分析演示")

    symbol = "AAPL"
    print_info(f"正在分析 {symbol} 的社交情绪 ...")

    analyzer = SocialSentimentAnalyzer()

    # 分析各平台
    print_subtitle("Twitter/X 情绪分析")
    twitter_result = analyzer.analyze_twitter(symbol, count=100)
    print_key_value([
        ("分析推文数", str(twitter_result["total"])),
        ("正面情绪", f"{twitter_result['positive']} 条 ({twitter_result['positive']/twitter_result['total']:.1%})"),
        ("负面情绪", f"{twitter_result['negative']} 条 ({twitter_result['negative']/twitter_result['total']:.1%})"),
        ("中性情绪", f"{twitter_result['neutral']} 条 ({twitter_result['neutral']/twitter_result['total']:.1%})"),
        ("情绪分数", f"{twitter_result['score']:.4f}"),
    ])

    if twitter_result["top_keywords"]:
        kw_str = ", ".join(f"{kw['word']}({kw['count']})" for kw in twitter_result["top_keywords"][:5])
        print_info(f"热门关键词: {kw_str}")

    print_subtitle("微博情绪分析")
    weibo_result = analyzer.analyze_weibo("贵州茅台", count=100)
    print_key_value([
        ("分析微博数", str(weibo_result["total"])),
        ("正面情绪", f"{weibo_result['positive']} 条"),
        ("负面情绪", f"{weibo_result['negative']} 条"),
        ("中性情绪", f"{weibo_result['neutral']} 条"),
        ("情绪分数", f"{weibo_result['score']:.4f}"),
    ])

    print_subtitle("Reddit 情绪分析")
    reddit_result = analyzer.analyze_reddit(subreddit="wallstreetbets", keyword=symbol, count=100)
    print_key_value([
        ("分析帖子数", str(reddit_result["total"])),
        ("正面情绪", f"{reddit_result['positive']} 条"),
        ("负面情绪", f"{reddit_result['negative']} 条"),
        ("中性情绪", f"{reddit_result['neutral']} 条"),
        ("情绪分数", f"{reddit_result['score']:.4f}"),
    ])

    # 综合情绪
    print_subtitle("综合情绪报告")
    combined = analyzer.get_combined_sentiment([twitter_result, reddit_result, weibo_result])
    print_key_value([
        ("综合情绪分数", f"{combined['combined_score']:.4f}"),
        ("情绪标签", combined["label"]),
        ("分析平台数", str(combined["total_platforms"])),
        ("总帖子数", str(combined["total_posts"])),
        ("总正面", str(combined["total_positive"])),
        ("总负面", str(combined["total_negative"])),
    ])

    if combined["top_keywords"]:
        kw_str = ", ".join(f"{kw['word']}({kw['count']})" for kw in combined["top_keywords"][:5])
        print_info(f"综合热门关键词: {kw_str}")

    print_success("社交情绪分析完成!")


def demo_ml_prediction(gen: DemoDataGenerator):
    """演示7: ML预测"""
    print_title("机器学习预测演示")

    symbol = "AAPL"
    print_info(f"正在训练 {symbol} 的ML预测模型 ...")

    # 生成数据
    data = gen.generate_stock_data(symbol, days=500)

    # 随机森林模型
    print_subtitle("随机森林模型")
    rf_predictor = MLPredictor(model_type="random_forest")
    rf_metrics = rf_predictor.train(data, test_ratio=0.2)

    print_key_value([
        ("模型类型", "Random Forest"),
        ("均方误差(MSE)", f"{rf_metrics['MSE']:.4f}"),
        ("平均绝对误差(MAE)", f"{rf_metrics['MAE']:.4f}"),
        ("R2 决定系数", f"{rf_metrics['R2']:.4f}"),
    ])

    # 特征重要性
    importance = rf_predictor.get_feature_importance()
    if importance:
        print_subtitle("特征重要性 (Top 10)")
        sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
        feat_rows = [[f, f"{v:.4f}"] for f, v in sorted_features]
        print_table(["特征", "重要性"], feat_rows)

    # 预测
    print_subtitle("未来5日价格预测")
    predictions = rf_predictor.predict(data, steps=5)
    last_price = data["Close"].iloc[-1]
    pred_rows = []
    for i, pred in enumerate(predictions):
        change = (pred - last_price) / last_price * 100 if last_price > 0 else 0
        pred_rows.append([f"第{i+1}天", f"${pred:.2f}", f"{change:+.2f}%"])
    print_table(["日期", "预测价格", "涨跌幅"], pred_rows)

    # MLP模型
    print_subtitle("MLP神经网络模型")
    mlp_predictor = MLPredictor(model_type="lstm")
    mlp_metrics = mlp_predictor.train(data, test_ratio=0.2)

    print_key_value([
        ("模型类型", "MLP (类LSTM)"),
        ("均方误差(MSE)", f"{mlp_metrics['MSE']:.4f}"),
        ("平均绝对误差(MAE)", f"{mlp_metrics['MAE']:.4f}"),
        ("R2 决定系数", f"{mlp_metrics['R2']:.4f}"),
    ])

    print_success("ML预测演示完成!")


# ============================================================
# 主菜单
# ============================================================

def show_menu():
    """显示主菜单"""
    if HAS_RICH:
        menu_text = Text()
        menu_text.append("\n  AutoWealth AI 交互式演示\n", style="bold cyan")
        menu_text.append("  " + "-" * 40 + "\n", style="dim")
        menu_text.append("  1. 单股分析\n")
        menu_text.append("  2. 批量分析\n")
        menu_text.append("  3. 组合优化\n")
        menu_text.append("  4. 回测\n")
        menu_text.append("  5. 预警系统\n")
        menu_text.append("  6. 社交情绪\n")
        menu_text.append("  7. ML预测\n")
        menu_text.append("  8. 退出\n")
        menu_text.append("  " + "-" * 40 + "\n", style="dim")
        console.print(Panel(menu_text, title="主菜单", box=box.ROUNDED))
    else:
        print("\n" + "=" * 50)
        print("  AutoWealth AI 交互式演示")
        print("  " + "-" * 40)
        print("  1. 单股分析")
        print("  2. 批量分析")
        print("  3. 组合优化")
        print("  4. 回测")
        print("  5. 预警系统")
        print("  6. 社交情绪")
        print("  7. ML预测")
        print("  8. 退出")
        print("  " + "-" * 40)
        print("=" * 50)


def main():
    """主函数"""
    # 导入 pandas（demo_portfolio_optimization 需要）
    import pandas as pd

    print_title("AutoWealth AI 交互式演示")
    print_info("本演示使用模拟数据，无需网络连接")
    print_info("所有数据均为随机生成，不构成投资建议")

    gen = DemoDataGenerator(seed=42)

    while True:
        show_menu()
        try:
            choice = input("\n  请选择功能 (1-8): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            break

        if choice == "1":
            demo_single_stock_analysis(gen)
        elif choice == "2":
            demo_batch_analysis(gen)
        elif choice == "3":
            demo_portfolio_optimization(gen)
        elif choice == "4":
            demo_backtest(gen)
        elif choice == "5":
            demo_alert_system(gen)
        elif choice == "6":
            demo_social_sentiment(gen)
        elif choice == "7":
            demo_ml_prediction(gen)
        elif choice == "8":
            print_info("感谢使用 AutoWealth AI 演示!")
            break
        else:
            print_error("无效选择，请输入 1-8")

        try:
            input("\n  按 Enter 继续...")
        except (EOFError, KeyboardInterrupt):
            print("\n")
            break

    print_title("演示结束")


if __name__ == "__main__":
    main()
