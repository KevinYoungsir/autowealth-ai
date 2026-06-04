"""
AutoWealth AI - Streamlit 鍙鍖栫晫闈?"""
import sys
from pathlib import Path

# 娣诲姞椤圭洰鏍圭洰褰曞埌璺緞
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from autowealth import AutoWealthEngine


# 椤甸潰閰嶇疆
st.set_page_config(
    page_title="AutoWealth AI",
    page_icon="馃",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 鑷畾涔夋牱寮?st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .signal-buy {
        color: #2ecc71;
        font-size: 2rem;
        font-weight: bold;
    }
    .signal-sell {
        color: #e74c3c;
        font-size: 2rem;
        font-weight: bold;
    }
    .signal-hold {
        color: #f39c12;
        font-size: 2rem;
        font-weight: bold;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .confidence-high {
        color: #2ecc71;
    }
    .confidence-medium {
        color: #f39c12;
    }
    .confidence-low {
        color: #e74c3c;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_engine():
    """鑾峰彇寮曟搸瀹炰緥锛堢紦瀛橈級"""
    return AutoWealthEngine()


def render_header():
    """娓叉煋椤甸潰澶撮儴"""
    st.markdown('<h1 class="main-header">馃 AutoWealth AI</h1>', unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 1.2rem; color: #666;'>鍩轰簬澶氭櫤鑳戒綋鐨勬櫤鑳芥姇璧勫垎鏋愬紩鎿?/p>", unsafe_allow_html=True)
    st.markdown("---")


def render_sidebar():
    """娓叉煋渚ц竟鏍?""
    with st.sidebar:
        st.header("鈿欙笍 璁剧疆")

        # 鍒嗘瀽妯″紡
        analysis_mode = st.radio(
            "鍒嗘瀽妯″紡",
            ["鍗曡偂鍒嗘瀽", "鎵归噺鍒嗘瀽", "鎶曡祫缁勫悎", "甯傚満姒傝"]
        )

        st.markdown("---")

        # 鏅鸿兘浣撻厤缃?        st.subheader("馃 鏅鸿兘浣撻厤缃?)
        tech_weight = st.slider("鎶€鏈垎鏋愭潈閲?, 0.0, 1.0, 0.35)
        fund_weight = st.slider("鍩烘湰闈㈠垎鏋愭潈閲?, 0.0, 1.0, 0.35)
        sent_weight = st.slider("鎯呯华鍒嗘瀽鏉冮噸", 0.0, 1.0, 0.30)

        # 鏉冮噸褰掍竴鍖?        total = tech_weight + fund_weight + sent_weight
        if total > 0:
            tech_weight = tech_weight / total
            fund_weight = fund_weight / total
            sent_weight = sent_weight / total

        st.markdown("---")
        st.info("馃挕 鎻愮ず: 鏉冮噸瓒婇珮锛岃鏅鸿兘浣撶殑鎰忚鍦ㄦ渶缁堝喅绛栦腑鍗犳瘮瓒婂ぇ")

        return analysis_mode, (tech_weight, fund_weight, sent_weight)


def render_signal_badge(signal_type, confidence):
    """娓叉煋淇″彿寰界珷"""
    if signal_type == "buy":
        return f'<span class="signal-buy">馃煝 涔板叆 ({confidence}%)</span>'
    elif signal_type == "sell":
        return f'<span class="signal-sell">馃敶 鍗栧嚭 ({confidence}%)</span>'
    else:
        return f'<span class="signal-hold">馃煛 瑙傛湜 ({confidence}%)</span>'


def render_single_analysis(engine):
    """娓叉煋鍗曡偂鍒嗘瀽椤甸潰"""
    st.header("馃搳 鍗曡偂鍒嗘瀽")

    # 杈撳叆鑲＄エ浠ｇ爜
    col1, col2 = st.columns([3, 1])
    with col1:
        symbol = st.text_input("杈撳叆鑲＄エ浠ｇ爜", "AAPL", placeholder="渚嬪: AAPL, GOOGL, 600519.SS")
    with col2:
        analyze_btn = st.button("馃攳 寮€濮嬪垎鏋?, type="primary", use_container_width=True)

    if analyze_btn and symbol:
        with st.spinner(f"姝ｅ湪鍒嗘瀽 {symbol}..."):
            try:
                result = engine.analyze(symbol.upper())

                if result["success"]:
                    render_analysis_result(result)
                else:
                    st.error(f"鍒嗘瀽澶辫触: {result.get('error', '鏈煡閿欒')}")

            except Exception as e:
                st.error(f"鍒嗘瀽鍑洪敊: {str(e)}")


def render_analysis_result(result):
    """娓叉煋鍒嗘瀽缁撴灉"""
    decision = result["decision"]
    stock_info = result.get("stock_info", {})

    # 椤堕儴淇℃伅鏍?    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("鑲＄エ浠ｇ爜", result["symbol"])
    with col2:
        st.metric("鍏徃鍚嶇О", stock_info.get("name", "N/A"))
    with col3:
        st.metric("琛屼笟", stock_info.get("industry", "N/A"))
    with col4:
        st.metric("甯傚€?, f"${stock_info.get('market_cap', 0):,.0f}" if stock_info.get("market_cap") else "N/A")

    st.markdown("---")

    # 缁煎悎鍐崇瓥
    st.subheader("馃幆 缁煎悎鍐崇瓥")
    signal_html = render_signal_badge(decision["signal_type"], decision["confidence"])
    st.markdown(signal_html, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if decision.get("target_price"):
            st.metric("馃幆 鐩爣浠?, f"${decision['target_price']}")
    with col2:
        if decision.get("stop_loss"):
            st.metric("馃洃 姝㈡崯浠?, f"${decision['stop_loss']}")

    # 鍐崇瓥鐞嗙敱
    with st.expander("馃挕 鏌ョ湅璇︾粏鍒嗘瀽鐞嗙敱"):
        st.text(decision["reasoning"])

    st.markdown("---")

    # 鍚勬櫤鑳戒綋淇″彿
    st.subheader("馃 鏅鸿兘浣撳垎鏋愮粨鏋?)

    cols = st.columns(3)
    agent_signals = result.get("individual_signals", {})

    for idx, (agent_name, signal) in enumerate(agent_signals.items()):
        with cols[idx % 3]:
            with st.container():
                st.markdown(f"**{agent_name}**")
                signal_html = render_signal_badge(signal.signal_type, signal.confidence)
                st.markdown(signal_html, unsafe_allow_html=True)

                if signal.metadata:
                    with st.expander("璇︽儏"):
                        st.json(signal.metadata)

    st.markdown("---")

    # 缁煎悎璇勫垎
    st.subheader("馃搱 缁煎悎璇勫垎")
    scores = decision.get("scores", {})

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("涔板叆璇勫垎", f"{scores.get('buy', 0):.1f}%")
    with col2:
        st.metric("鍗栧嚭璇勫垎", f"{scores.get('sell', 0):.1f}%")
    with col3:
        st.metric("瑙傛湜璇勫垎", f"{scores.get('hold', 0):.1f}%")

    # 璇勫垎杩涘害鏉?    st.progress(scores.get("buy", 0) / 100, text="涔板叆寮哄害")
    st.progress(scores.get("sell", 0) / 100, text="鍗栧嚭寮哄害")


def render_batch_analysis(engine):
    """娓叉煋鎵归噺鍒嗘瀽椤甸潰"""
    st.header("馃搳 鎵归噺鍒嗘瀽")

    # 杈撳叆鑲＄エ浠ｇ爜
    symbols_input = st.text_area(
        "杈撳叆鑲＄エ浠ｇ爜锛堟瘡琛屼竴涓級",
        "AAPL\nGOOGL\nMSFT\nAMZN\nMETA",
        height=150
    )

    if st.button("馃攳 寮€濮嬫壒閲忓垎鏋?, type="primary"):
        symbols = [s.strip().upper() for s in symbols_input.split("\n") if s.strip()]

        if symbols:
            with st.spinner(f"姝ｅ湪鍒嗘瀽 {len(symbols)} 鍙偂绁?.."):
                try:
                    result = engine.analyze_batch(symbols)

                    # 鏄剧ず缁熻
                    summary = result["summary"]
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("鎬昏", summary["total"])
                    col2.metric("鎴愬姛", summary["success"])
                    col3.metric("涔板叆鎺ㄨ崘", summary["buy_count"])
                    col4.metric("鍗栧嚭鎺ㄨ崘", summary["sell_count"])

                    # 涔板叆鎺ㄨ崘
                    if result["recommendations"]["buy"]:
                        st.subheader("馃煝 涔板叆鎺ㄨ崘")
                        buy_df = pd.DataFrame(
                            result["recommendations"]["buy"],
                            columns=["鑲＄エ浠ｇ爜", "缃俊搴?]
                        )
                        buy_df["鎺掑悕"] = range(1, len(buy_df) + 1)
                        st.dataframe(buy_df[["鎺掑悕", "鑲＄エ浠ｇ爜", "缃俊搴?]], use_container_width=True)

                    # 鍗栧嚭鎺ㄨ崘
                    if result["recommendations"]["sell"]:
                        st.subheader("馃敶 鍗栧嚭鎺ㄨ崘")
                        sell_df = pd.DataFrame(
                            result["recommendations"]["sell"],
                            columns=["鑲＄エ浠ｇ爜", "缃俊搴?]
                        )
                        sell_df["鎺掑悕"] = range(1, len(sell_df) + 1)
                        st.dataframe(sell_df[["鎺掑悕", "鑲＄エ浠ｇ爜", "缃俊搴?]], use_container_width=True)

                    # 璇︾粏缁撴灉
                    with st.expander("鏌ョ湅璇︾粏鍒嗘瀽缁撴灉"):
                        for symbol, analysis in result["results"].items():
                            if analysis["success"]:
                                decision = analysis["decision"]
                                st.markdown(f"**{symbol}**: {decision['signal_type'].upper()} ({decision['confidence']}%)")

                except Exception as e:
                    st.error(f"鎵归噺鍒嗘瀽鍑洪敊: {str(e)}")


def render_portfolio(engine):
    """娓叉煋鎶曡祫缁勫悎椤甸潰"""
    st.header("馃捈 鎶曡祫缁勫悎鍒嗘瀽")

    st.info("馃摑 杈撳叆鎮ㄧ殑鎸佷粨淇℃伅杩涜鍒嗘瀽")

    # 鍔ㄦ€佹坊鍔犳寔浠?    if "holdings" not in st.session_state:
        st.session_state.holdings = [{"symbol": "", "quantity": 0, "cost_basis": 0.0}]

    for i, holding in enumerate(st.session_state.holdings):
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])

        with col1:
            holding["symbol"] = st.text_input(f"鑲＄エ浠ｇ爜 #{i+1}", holding["symbol"], key=f"symbol_{i}")
        with col2:
            holding["quantity"] = st.number_input(f"鏁伴噺 #{i+1}", 0, 1000000, holding["quantity"], key=f"qty_{i}")
        with col3:
            holding["cost_basis"] = st.number_input(f"鎴愭湰浠?#{i+1}", 0.0, 1000000.0, holding["cost_basis"], key=f"cost_{i}")
        with col4:
            if st.button("馃棏锔?, key=f"del_{i}") and len(st.session_state.holdings) > 1:
                st.session_state.holdings.pop(i)
                st.rerun()

    if st.button("鉃?娣诲姞鎸佷粨"):
        st.session_state.holdings.append({"symbol": "", "quantity": 0, "cost_basis": 0.0})
        st.rerun()

    if st.button("馃攳 鍒嗘瀽鎶曡祫缁勫悎", type="primary"):
        valid_holdings = [h for h in st.session_state.holdings if h["symbol"]]

        if valid_holdings:
            with st.spinner("姝ｅ湪鍒嗘瀽鎶曡祫缁勫悎..."):
                try:
                    portfolio = engine.get_portfolio_analysis(valid_holdings)

                    # 鎬昏
                    col1, col2, col3 = st.columns(3)
                    col1.metric("鎬诲競鍊?, f"${portfolio['total_value']:,.2f}")
                    col2.metric("鎬荤泩浜?, f"${portfolio['total_gain_loss']:,.2f}")
                    col3.metric("鏀剁泭鐜?, f"{portfolio['return_pct']:.2f}%")

                    # 鎸佷粨璇︽儏
                    st.subheader("馃搳 鎸佷粨璇︽儏")
                    holdings_df = pd.DataFrame(portfolio["holdings"])
                    if not holdings_df.empty:
                        st.dataframe(holdings_df, use_container_width=True)

                except Exception as e:
                    st.error(f"鎶曡祫缁勫悎鍒嗘瀽鍑洪敊: {str(e)}")
        else:
            st.warning("璇疯嚦灏戣緭鍏ヤ竴涓湁鏁堢殑鎸佷粨")


def render_market_overview(engine):
    """娓叉煋甯傚満姒傝椤甸潰"""
    st.header("馃實 甯傚満姒傝")

    if st.button("馃攧 鍒锋柊鏁版嵁", type="primary"):
        with st.spinner("姝ｅ湪鑾峰彇甯傚満鏁版嵁..."):
            try:
                overview = engine.get_market_overview()

                if overview["success"]:
                    # 鍒涘缓鏁版嵁妗?                    indices_data = []
                    for symbol, data in overview["indices"].items():
                        indices_data.append({
                            "鎸囨暟": symbol,
                            "浠锋牸": data["price"],
                            "娑ㄨ穼骞?: data["change_pct"],
                        })

                    df = pd.DataFrame(indices_data)

                    # 鏄剧ず琛ㄦ牸
                    st.dataframe(
                        df.style.apply(
                            lambda x: ['color: green' if v > 0 else 'color: red' for v in x],
                            subset=["娑ㄨ穼骞?]
                        ),
                        use_container_width=True
                    )

                    # 鍙鍖?                    fig = go.Figure()
                    colors = ["green" if x > 0 else "red" for x in df["娑ㄨ穼骞?]]

                    fig.add_trace(go.Bar(
                        x=df["鎸囨暟"],
                        y=df["娑ㄨ穼骞?],
                        marker_color=colors,
                        text=[f"{x:+.2f}%" for x in df["娑ㄨ穼骞?]],
                        textposition="auto",
                    ))

                    fig.update_layout(
                        title="鍏ㄧ悆涓昏鎸囨暟娑ㄨ穼骞?,
                        xaxis_title="鎸囨暟",
                        yaxis_title="娑ㄨ穼骞?(%)",
                        template="plotly_white",
                    )

                    st.plotly_chart(fig, use_container_width=True)

                else:
                    st.error(f"鑾峰彇甯傚満鏁版嵁澶辫触: {overview.get('error')}")

            except Exception as e:
                st.error(f"甯傚満姒傝鍑洪敊: {str(e)}")


def main():
    """涓诲嚱鏁?""
    render_header()

    # 鑾峰彇寮曟搸
    engine = get_engine()

    # 渚ц竟鏍?    analysis_mode, weights = render_sidebar()

    # 涓诲唴瀹瑰尯
    if analysis_mode == "鍗曡偂鍒嗘瀽":
        render_single_analysis(engine)
    elif analysis_mode == "鎵归噺鍒嗘瀽":
        render_batch_analysis(engine)
    elif analysis_mode == "鎶曡祫缁勫悎":
        render_portfolio(engine)
    elif analysis_mode == "甯傚満姒傝":
        render_market_overview(engine)

    # 椤佃剼
    st.markdown("---")
    st.markdown(
        "<p style='text-align: center; color: #666;'>"
        "馃 AutoWealth AI | 鍩轰簬澶氭櫤鑳戒綋鐨勬櫤鑳芥姇璧勫垎鏋愬紩鎿?br>"
        "<small>鈿狅笍 浠呬緵鏁欒偛鍜岀爺绌剁洰鐨勶紝涓嶆瀯鎴愭姇璧勫缓璁?/small>"
        "</p>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main