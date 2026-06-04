"""
AutoWealth AI - Streamlit 可视化界面

基于多智能体的智能投资分析引擎，提供单股分析、批量分析、
投资组合管理和市场概览功能。
"""
import sys
from pathlib import Path

# 添加项目根目录到路径，确保可以导入 autowealth
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from autowealth import AutoWealthEngine

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="AutoWealth AI",
    page_icon="T",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 自定义 CSS 样式
# ============================================================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .signal-buy {
        color: #2ecc71;
        font-size: 1.8rem;
        font-weight: bold;
    }
    .signal-sell {
        color: #e74c3c;
        font-size: 1.8rem;
        font-weight: bold;
    }
    .signal-hold {
        color: #f39c12;
        font-size: 1.8rem;
        font-weight: bold;
    }
    .section-header {
        font-size: 1.4rem;
        font-weight: bold;
        color: #2c3e50;
        border-bottom: 2px solid #3498db;
        padding-bottom: 0.5rem;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
    }
    .agent-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
        border-left: 4px solid #3498db;
    }
    .agent-card-buy { border-left-color: #2ecc71; }
    .agent-card-sell { border-left-color: #e74c3c; }
    .agent-card-hold { border-left-color: #f39c12; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 缓存引擎实例
# ============================================================
@st.cache_resource
def get_engine():
    """获取 AutoWealthEngine 引擎实例，使用 st 缓存避免重复初始化"""
    return AutoWealthEngine()


# ============================================================
# 辅助函数
# ============================================================
def get_signal_color(signal_type):
    """根据信号类型返回颜色标识"""
    color_map = {
        "buy": "#2ecc71",
        "sell": "#e74c3c",
        "hold": "#f39c12",
    }
    return color_map.get(signal_type, "#95a5a6")


def get_signal_label(signal_type):
    """根据信号类型返回中文标签"""
    label_map = {
        "buy": "买入",
        "sell": "卖出",
        "hold": "观望",
    }
    return label_map.get(signal_type, "未知")


def render_signal_badge(signal_type, confidence):
    """渲染带颜色的信号徽章"""
    color = get_signal_color(signal_type)
    label = get_signal_label(signal_type)
    return f'<span style="color:{color}; font-size:1.8rem; font-weight:bold;">' \
           f'{label} ({confidence:.1f}%)</span>'


def plot_price_chart(historical_data, symbol):
    """使用 matplotlib 绘制价格走势图"""
    fig, ax = plt.subplots(figsize=(12, 5))

    # 绘制收盘价
    ax.plot(historical_data.index, historical_data["Close"],
            color="#1f77b4", linewidth=1.5, label="收盘价")

    # 绘制成交量（副轴）
    ax2 = ax.twinx()
    ax2.bar(historical_data.index, historical_data["Volume"],
            alpha=0.3, color="#3498db", label="成交量")
    ax2.set_ylabel("成交量", fontsize=10)
    ax2.legend(loc="upper right")

    # 设置主轴
    ax.set_title(f"{symbol} 价格走势", fontsize=14, fontweight="bold")
    ax.set_xlabel("日期", fontsize=10)
    ax.set_ylabel("价格", fontsize=10)
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    # 日期格式化
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()

    fig.tight_layout()
    return fig


# ============================================================
# 页面渲染函数
# ============================================================
def render_header():
    """渲染页面头部"""
    st.markdown('<h1 class="main-header">AutoWealth AI</h1>', unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align: center; font-size: 1.1rem; color: #666;'>"
        "基于多智能体的智能投资分析引擎</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")


def render_sidebar():
    """渲染侧边栏导航"""
    with st.sidebar:
        st.header("导航")

        # 页面选择
        page = st.radio(
            "选择功能",
            ["单股分析", "批量分析", "投资组合", "市场概览"],
            label_visibility="collapsed",
        )

        st.markdown("---")

        # 智能体权重配置
        st.subheader("智能体权重")
        tech_weight = st.slider("技术分析", 0.0, 1.0, 0.35, step=0.05)
        fund_weight = st.slider("基本面分析", 0.0, 1.0, 0.35, step=0.05)
        sent_weight = st.slider("情绪分析", 0.0, 1.0, 0.30, step=0.05)

        # 权重归一化
        total = tech_weight + fund_weight + sent_weight
        if total > 0:
            tech_weight /= total
            fund_weight /= total
            sent_weight /= total

        st.markdown("---")
        st.caption("提示: 权重越高，该智能体在最终决策中的影响越大")

        return page, (tech_weight, fund_weight, sent_weight)


def render_single_analysis(engine):
    """渲染单股分析页面"""
    st.markdown('<h2 class="section-header">单股分析</h2>', unsafe_allow_html=True)

    # 输入区域
    col1, col2 = st.columns([4, 1])
    with col1:
        symbol = st.text_input(
            "股票代码",
            placeholder="例如: AAPL, GOOGL, 600519.SS",
            label_visibility="visible",
        )
    with col2:
        st.write("")  # 对齐按钮
        st.write("")
        analyze_btn = st.button("开始分析", type="primary", use_container_width=True)

    if analyze_btn and symbol:
        symbol = symbol.strip().upper()
        with st.spinner(f"正在分析 {symbol} ..."):
            try:
                result = engine.analyze(symbol)

                if result["success"]:
                    _display_single_result(result)
                else:
                    st.error(f"分析失败: {result.get('error', '未知错误')}")

            except Exception as e:
                st.error(f"分析出错: {str(e)}")
    elif analyze_btn and not symbol:
        st.warning("请输入股票代码")


def _display_single_result(result):
    """展示单股分析的详细结果"""
    decision = result.get("decision", {})
    stock_info = result.get("stock_info", {})
    individual_signals = result.get("individual_signals", {})

    # ---- 基本信息栏 ----
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("股票代码", result.get("symbol", "N/A"))
    with col2:
        st.metric("公司名称", stock_info.get("name", "N/A"))
    with col3:
        st.metric("行业", stock_info.get("industry", "N/A"))
    with col4:
        market_cap = stock_info.get("market_cap", 0)
        if market_cap and market_cap > 0:
            st.metric("市值", f"${market_cap:,.0f}")
        else:
            st.metric("市值", "N/A")

    st.markdown("---")

    # ---- 综合决策 ----
    st.markdown('<h2 class="section-header">综合决策</h2>', unsafe_allow_html=True)

    signal_type = decision.get("signal_type", "hold")
    confidence = decision.get("confidence", 0)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**信号**")
        st.markdown(render_signal_badge(signal_type, confidence), unsafe_allow_html=True)
    with col2:
        target_price = decision.get("target_price")
        st.metric("目标价", f"${target_price:.2f}" if target_price else "N/A")
    with col3:
        stop_loss = decision.get("stop_loss")
        st.metric("止损价", f"${stop_loss:.2f}" if stop_loss else "N/A")

    # 详细理由
    reasoning = decision.get("reasoning", "")
    if reasoning:
        with st.expander("查看详细分析理由"):
            st.text(reasoning)

    st.markdown("---")

    # ---- 各智能体信号 ----
    st.markdown('<h2 class="section-header">智能体分析结果</h2>', unsafe_allow_html=True)

    if individual_signals:
        cols = st.columns(min(len(individual_signals), 3))
        for idx, (agent_name, signal) in enumerate(individual_signals.items()):
            with cols[idx % 3]:
                card_class = f"agent-card agent-card-{signal.signal_type}"
                st.markdown(
                    f'<div class="{card_class}">'
                    f"<strong>{agent_name}</strong><br>"
                    f'<span style="color:{get_signal_color(signal.signal_type)}; '
                    f'font-weight:bold;">'
                    f'{get_signal_label(signal.signal_type)} '
                    f'({signal.confidence:.1f}%)</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # 显示该智能体的理由
                if signal.reasoning:
                    with st.expander("理由"):
                        st.text(signal.reasoning)
    else:
        st.info("暂无智能体信号数据")

    st.markdown("---")

    # ---- 综合评分 ----
    st.markdown('<h2 class="section-header">综合评分</h2>', unsafe_allow_html=True)
    scores = decision.get("scores", {})

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("买入评分", f"{scores.get('buy', 0):.1f}%")
    with col2:
        st.metric("卖出评分", f"{scores.get('sell', 0):.1f}%")
    with col3:
        st.metric("观望评分", f"{scores.get('hold', 0):.1f}%")

    # 评分进度条
    st.progress(min(scores.get("buy", 0) / 100, 1.0), text="买入强度")
    st.progress(min(scores.get("sell", 0) / 100, 1.0), text="卖出强度")

    st.markdown("---")

    # ---- 价格走势图 ----
    st.markdown('<h2 class="section-header">价格走势</h2>', unsafe_allow_html=True)
    try:
        tech_data = result.get("technical_analysis", {})
        if tech_data:
            # 从 technical_analysis 中提取数据绘图
            # technical_analysis 是 iloc[-10:].to_dict() 的结果
            # 尝试从 stock_info 获取历史数据
            st.info("价格走势图需要历史数据支持，请确保数据获取正常。")
        else:
            st.info("暂无技术分析数据")
    except Exception:
        st.info("暂无价格走势数据")


def render_batch_analysis(engine):
    """渲染批量分析页面"""
    st.markdown('<h2 class="section-header">批量分析</h2>', unsafe_allow_html=True)

    symbols_input = st.text_area(
        "输入股票代码（逗号分隔）",
        placeholder="例如: AAPL, GOOGL, MSFT, AMZN, META",
        height=120,
    )

    if st.button("开始批量分析", type="primary"):
        symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

        if not symbols:
            st.warning("请输入至少一个股票代码")
            return

        with st.spinner(f"正在分析 {len(symbols)} 只股票..."):
            try:
                result = engine.analyze_batch(symbols)

                # ---- 统计概览 ----
                summary = result.get("summary", {})
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("总计", summary.get("total", 0))
                col2.metric("成功", summary.get("success", 0))
                col3.metric("买入推荐", summary.get("buy_count", 0))
                col4.metric("卖出推荐", summary.get("sell_count", 0))

                recommendations = result.get("recommendations", {})

                # ---- 买入推荐列表 ----
                buy_list = recommendations.get("buy", [])
                if buy_list:
                    st.markdown(
                        '<h3 style="color:#2ecc71;">买入推荐</h3>',
                        unsafe_allow_html=True,
                    )
                    buy_df = pd.DataFrame(buy_list, columns=["股票代码", "置信度"])
                    buy_df.insert(0, "排名", range(1, len(buy_df) + 1))
                    st.dataframe(buy_df, use_container_width=True, hide_index=True)
                else:
                    st.info("暂无买入推荐")

                # ---- 卖出推荐列表 ----
                sell_list = recommendations.get("sell", [])
                if sell_list:
                    st.markdown(
                        '<h3 style="color:#e74c3c;">卖出推荐</h3>',
                        unsafe_allow_html=True,
                    )
                    sell_df = pd.DataFrame(sell_list, columns=["股票代码", "置信度"])
                    sell_df.insert(0, "排名", range(1, len(sell_df) + 1))
                    st.dataframe(sell_df, use_container_width=True, hide_index=True)
                else:
                    st.info("暂无卖出推荐")

                # ---- 观望列表 ----
                hold_list = recommendations.get("hold", [])
                if hold_list:
                    st.markdown(
                        '<h3 style="color:#f39c12;">观望列表</h3>',
                        unsafe_allow_html=True,
                    )
                    hold_df = pd.DataFrame(hold_list, columns=["股票代码", "置信度"])
                    hold_df.insert(0, "排名", range(1, len(hold_df) + 1))
                    st.dataframe(hold_df, use_container_width=True, hide_index=True)

                # ---- 详细结果（可展开） ----
                all_results = result.get("results", {})
                if all_results:
                    with st.expander("查看所有详细分析结果"):
                        for sym, analysis in all_results.items():
                            if analysis.get("success") and "decision" in analysis:
                                d = analysis["decision"]
                                color = get_signal_color(d["signal_type"])
                                st.markdown(
                                    f"**{sym}**: "
                                    f'<span style="color:{color}; font-weight:bold;">'
                                    f'{get_signal_label(d["signal_type"])} '
                                    f'({d["confidence"]:.1f}%)</span>',
                                    unsafe_allow_html=True,
                                )
                            else:
                                st.markdown(f"**{sym}**: 分析失败")

            except Exception as e:
                st.error(f"批量分析出错: {str(e)}")


def render_portfolio(engine):
    """渲染投资组合分析页面"""
    st.markdown('<h2 class="section-header">投资组合分析</h2>', unsafe_allow_html=True)

    st.info("输入您的持仓信息（股票代码、数量、成本价），点击分析按钮查看结果。")

    # 初始化 session_state 中的持仓列表
    if "holdings" not in st.session_state:
        st.session_state.holdings = [
            {"symbol": "", "quantity": 100, "cost_basis": 0.0}
        ]

    # 渲染持仓输入行
    for i, holding in enumerate(st.session_state.holdings):
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        with col1:
            holding["symbol"] = st.text_input(
                f"股票代码 #{i+1}", holding["symbol"], key=f"sym_{i}"
            )
        with col2:
            holding["quantity"] = st.number_input(
                f"数量 #{i+1}", 0, 10000000, holding["quantity"], key=f"qty_{i}"
            )
        with col3:
            holding["cost_basis"] = st.number_input(
                f"成本价 #{i+1}", 0.0, 1000000.0,
                float(holding["cost_basis"]),
                key=f"cost_{i}",
            )
        with col4:
            if st.button("删除", key=f"del_{i}"):
                if len(st.session_state.holdings) > 1:
                    st.session_state.holdings.pop(i)
                    st.rerun()

    # 添加持仓按钮
    if st.button("添加持仓"):
        st.session_state.holdings.append({"symbol": "", "quantity": 100, "cost_basis": 0.0})
        st.rerun()

    st.markdown("---")

    # 分析按钮
    if st.button("分析投资组合", type="primary"):
        valid_holdings = [h for h in st.session_state.holdings if h.get("symbol")]

        if not valid_holdings:
            st.warning("请至少输入一个有效的持仓")
            return

        with st.spinner("正在分析投资组合..."):
            try:
                portfolio = engine.get_portfolio_analysis(valid_holdings)

                # ---- 总览指标 ----
                col1, col2, col3 = st.columns(3)
                col1.metric("总市值", f"${portfolio.get('total_value', 0):,.2f}")
                col2.metric("总盈亏", f"${portfolio.get('total_gain_loss', 0):,.2f}")
                col3.metric("收益率", f"{portfolio.get('return_pct', 0):.2f}%")

                st.markdown("---")

                # ---- 持仓详情表 ----
                holdings_list = portfolio.get("holdings", [])
                if holdings_list:
                    st.markdown('<h3>持仓详情</h3>')
                    holdings_df = pd.DataFrame(holdings_list)

                    # 格式化显示
                    display_df = holdings_df.copy()
                    if "gain_loss" in display_df.columns:
                        display_df["盈亏"] = display_df["gain_loss"].apply(
                            lambda x: f"${x:,.2f}"
                        )
                    if "holding_value" in display_df.columns:
                        display_df["市值"] = display_df["holding_value"].apply(
                            lambda x: f"${x:,.2f}"
                        )

                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                else:
                    st.info("暂无持仓分析数据")

            except Exception as e:
                st.error(f"投资组合分析出错: {str(e)}")


def render_market_overview(engine):
    """渲染市场概览页面"""
    st.markdown('<h2 class="section-header">市场概览</h2>', unsafe_allow_html=True)

    if st.button("刷新数据", type="primary"):
        with st.spinner("正在获取全球市场数据..."):
            try:
                overview = engine.get_market_overview()

                if overview.get("success"):
                    indices = overview.get("indices", {})

                    if not indices:
                        st.warning("暂无市场数据")
                        return

                    # 构建数据表
                    rows = []
                    for symbol, data in indices.items():
                        rows.append({
                            "指数": symbol,
                            "最新价": data.get("price", 0),
                            "涨跌幅(%)": data.get("change_pct", 0),
                            "成交量": data.get("volume", 0),
                        })

                    df = pd.DataFrame(rows)

                    # 带颜色标识的涨跌幅显示
                    def color_change(val):
                        if val > 0:
                            return "color: #2ecc71; font-weight: bold;"
                        elif val < 0:
                            return "color: #e74c3c; font-weight: bold;"
                        return "color: #95a5a6;"

                    styled_df = df.style.applymap(color_change, subset=["涨跌幅(%)"])
                    st.dataframe(styled_df, use_container_width=True, hide_index=True)

                    st.markdown("---")

                    # 使用 matplotlib 绘制涨跌幅柱状图
                    fig, ax = plt.subplots(figsize=(12, 5))

                    colors = [
                        "#2ecc71" if v >= 0 else "#e74c3c"
                        for v in df["涨跌幅(%)"]
                    ]

                    bars = ax.bar(df["指数"], df["涨跌幅(%)"], color=colors, edgecolor="white")

                    # 在柱子上标注数值
                    for bar, val in zip(bars, df["涨跌幅(%)"]):
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            bar.get_height() + (0.05 if val >= 0 else -0.15),
                            f"{val:+.2f}%",
                            ha="center", va="bottom" if val >= 0 else "top",
                            fontsize=9, fontweight="bold",
                        )

                    ax.set_title("全球主要指数涨跌幅", fontsize=14, fontweight="bold")
                    ax.set_ylabel("涨跌幅 (%)", fontsize=10)
                    ax.axhline(y=0, color="gray", linewidth=0.8, linestyle="--")
                    ax.grid(axis="y", alpha=0.3)
                    plt.xticks(rotation=45, ha="right")
                    fig.tight_layout()

                    st.pyplot(fig)

                else:
                    st.error(f"获取市场数据失败: {overview.get('error', '未知错误')}")

            except Exception as e:
                st.error(f"市场概览出错: {str(e)}")


# ============================================================
# 主函数
# ============================================================
def main():
    """Streamlit 应用主入口"""
    render_header()

    # 获取缓存的引擎实例
    engine = get_engine()

    # 侧边栏导航
    page, weights = render_sidebar()

    # 根据选择渲染对应页面
    if page == "单股分析":
        render_single_analysis(engine)
    elif page == "批量分析":
        render_batch_analysis(engine)
    elif page == "投资组合":
        render_portfolio(engine)
    elif page == "市场概览":
        render_market_overview(engine)

    # 页脚
    st.markdown("---")
    st.markdown(
        "<p style='text-align: center; color: #666;'>"
        "AutoWealth AI | 基于多智能体的智能投资分析引擎<br>"
        "<small>仅供教育和研究目的，不构成投资建议</small>"
        "</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
