"""
AutoWealth AI - 高端可视化界面

基于多智能体的智能投资分析引擎，提供单股分析、批量分析、
投资组合管理和市场概览功能。

设计理念：
- 深色主题，科技感十足
- 卡片式布局，信息层次清晰
- 渐变色彩，视觉冲击力
- 微交互动画，提升体验
- 数据可视化，一目了然
"""
import sys
from pathlib import Path

# 添加项目根目录到路径，确保可以导入 autowealth
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from autowealth import AutoWealthEngine

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="AutoWealth AI · 智能投资分析",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 自定义 CSS 样式 - 高端深色主题
# ============================================================
st.markdown("""
<style>
    /* 全局字体 */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* 主背景 */
    .stApp {
        background: linear-gradient(135deg, #0a0e1a 0%, #121a2e 50%, #0d1321 100%);
    }
    
    /* 侧边栏 */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f1729 0%, #1a1f3a 100%);
        border-right: 1px solid rgba(255,255,255,0.05);
    }
    
    /* 主标题 */
    .main-header {
        font-size: 3rem;
        font-weight: 700;
        background: linear-gradient(135deg, #00d4ff 0%, #7b2cbf 50%, #ff006e 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-align: center;
        margin-bottom: 0.5rem;
        letter-spacing: -1px;
    }
    
    .sub-header {
        font-size: 1.1rem;
        color: rgba(255,255,255,0.5);
        text-align: center;
        margin-bottom: 2rem;
        font-weight: 300;
    }
    
    /* 玻璃拟态卡片 */
    .glass-card {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 1.5rem;
        margin: 0.75rem 0;
        transition: all 0.3s ease;
    }
    
    .glass-card:hover {
        background: rgba(255, 255, 255, 0.06);
        border-color: rgba(255, 255, 255, 0.15);
        transform: translateY(-2px);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }
    
    /* 信号卡片 */
    .signal-card {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(20px);
        border-radius: 16px;
        padding: 1.5rem;
        margin: 0.75rem 0;
        border-left: 4px solid;
        transition: all 0.3s ease;
    }
    
    .signal-card-buy {
        border-left-color: #00f5a0;
        background: linear-gradient(135deg, rgba(0,245,160,0.05) 0%, rgba(255,255,255,0.02) 100%);
    }
    
    .signal-card-sell {
        border-left-color: #ff4757;
        background: linear-gradient(135deg, rgba(255,71,87,0.05) 0%, rgba(255,255,255,0.02) 100%);
    }
    
    .signal-card-hold {
        border-left-color: #ffa502;
        background: linear-gradient(135deg, rgba(255,165,2,0.05) 0%, rgba(255,255,255,0.02) 100%);
    }
    
    /* 指标卡片 */
    .metric-card {
        background: linear-gradient(135deg, rgba(0,212,255,0.08) 0%, rgba(123,44,191,0.05) 100%);
        border: 1px solid rgba(0,212,255,0.15);
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
        transition: all 0.3s ease;
    }
    
    .metric-card:hover {
        border-color: rgba(0,212,255,0.3);
        box-shadow: 0 0 20px rgba(0,212,255,0.1);
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #ffffff;
        margin: 0.5rem 0;
    }
    
    .metric-label {
        font-size: 0.85rem;
        color: rgba(255,255,255,0.5);
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* 信号徽章 */
    .signal-badge {
        display: inline-block;
        padding: 0.5rem 1.5rem;
        border-radius: 50px;
        font-size: 1.5rem;
        font-weight: 700;
        letter-spacing: 1px;
        text-transform: uppercase;
    }
    
    .signal-badge-buy {
        background: linear-gradient(135deg, #00f5a0 0%, #00d4aa 100%);
        color: #000;
        box-shadow: 0 0 20px rgba(0,245,160,0.3);
    }
    
    .signal-badge-sell {
        background: linear-gradient(135deg, #ff4757 0%, #ff3838 100%);
        color: #fff;
        box-shadow: 0 0 20px rgba(255,71,87,0.3);
    }
    
    .signal-badge-hold {
        background: linear-gradient(135deg, #ffa502 0%, #ff7b00 100%);
        color: #000;
        box-shadow: 0 0 20px rgba(255,165,2,0.3);
    }
    
    /* 章节标题 */
    .section-header {
        font-size: 1.3rem;
        font-weight: 600;
        color: #ffffff;
        margin: 2rem 0 1rem 0;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid rgba(255,255,255,0.1);
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    .section-icon {
        font-size: 1.5rem;
    }
    
    /* 进度条样式 */
    .progress-container {
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    /* 按钮样式覆盖 */
    .stButton > button {
        background: linear-gradient(135deg, #00d4ff 0%, #7b2cbf 100%) !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.75rem 2rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.5px !important;
        transition: all 0.3s ease !important;
        color: white !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 25px rgba(0,212,255,0.3) !important;
    }
    
    /* 输入框样式 - 使用更通用的选择器适配不同Streamlit版本 */
    .stTextInput input,
    .stTextArea textarea,
    .stNumberInput input,
    .stTextInput [class*="st-c1"] input,
    .stTextArea [class*="st-c1"] textarea,
    .stNumberInput [class*="st-c1"] input {
        background: rgba(0,212,255,0.08) !important;
        border: 2px solid rgba(0,212,255,0.5) !important;
        border-radius: 12px !important;
        color: #ffffff !important;
        padding: 0.75rem 1rem !important;
        font-size: 1rem !important;
        transition: all 0.3s ease !important;
    }

    .stTextInput input::placeholder,
    .stTextArea textarea::placeholder,
    .stNumberInput input::placeholder {
        color: rgba(255,255,255,0.5) !important;
    }

    .stTextInput input:focus,
    .stTextArea textarea:focus,
    .stNumberInput input:focus {
        border-color: #00d4ff !important;
        box-shadow: 0 0 15px rgba(0,212,255,0.3) !important;
        background: rgba(0,212,255,0.12) !important;
    }
    
    /* 滑块样式 */
    .stSlider > div > div > div {
        background: linear-gradient(90deg, #00d4ff 0%, #7b2cbf 100%) !important;
    }
    
    /* 侧边栏导航 */
    .nav-item {
        padding: 0.75rem 1rem;
        border-radius: 10px;
        margin: 0.25rem 0;
        cursor: pointer;
        transition: all 0.2s ease;
        color: rgba(255,255,255,0.6);
    }
    
    .nav-item:hover {
        background: rgba(255,255,255,0.05);
        color: white;
    }
    
    .nav-item.active {
        background: linear-gradient(135deg, rgba(0,212,255,0.2) 0%, rgba(123,44,191,0.2) 100%);
        color: white;
        border: 1px solid rgba(0,212,255,0.3);
    }
    
    /* 数据表格样式 */
    .dataframe {
        background: rgba(255,255,255,0.02) !important;
        border-radius: 12px !important;
        border: 1px solid rgba(255,255,255,0.05) !important;
    }
    
    /* 动画效果 */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .animate-in {
        animation: fadeIn 0.6s ease-out forwards;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }
    
    .pulse {
        animation: pulse 2s ease-in-out infinite;
    }
    
    @keyframes glow {
        0%, 100% { box-shadow: 0 0 5px rgba(0,212,255,0.3); }
        50% { box-shadow: 0 0 20px rgba(0,212,255,0.6); }
    }
    
    .glow-effect {
        animation: glow 3s ease-in-out infinite;
    }
    
    /* 页脚 */
    .footer {
        text-align: center;
        padding: 2rem 0;
        color: rgba(255,255,255,0.3);
        font-size: 0.85rem;
        border-top: 1px solid rgba(255,255,255,0.05);
        margin-top: 3rem;
    }
    
    /* 分隔线 */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.1) 50%, transparent 100%);
        margin: 2rem 0;
    }
    
    /* 提示框 - 适配不同Streamlit版本 */
    [data-testid="stAlert"],
    .stAlert,
    .stException {
        background: rgba(255,71,87,0.15) !important;
        border: 1px solid rgba(255,71,87,0.3) !important;
        border-radius: 12px !important;
        color: #ff6b7a !important;
    }
    [data-testid="stAlert"] p,
    .stAlert p,
    .stException p {
        color: #ff6b7a !important;
    }
    
    /* 标签页 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
        background: rgba(255,255,255,0.02);
        border-radius: 12px;
        padding: 0.5rem;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px !important;
        color: rgba(255,255,255,0.5) !important;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, rgba(0,212,255,0.2) 0%, rgba(123,44,191,0.2) 100%) !important;
        color: white !important;
    }
    
    /* 展开器 */
    .streamlit-expanderHeader {
        background: rgba(255,255,255,0.03) !important;
        border-radius: 12px !important;
        border: 1px solid rgba(255,255,255,0.05) !important;
    }
    
    /* 隐藏默认元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
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
        "buy": "#00f5a0",
        "sell": "#ff4757",
        "hold": "#ffa502",
    }
    return color_map.get(signal_type, "#95a5a6")


def get_signal_gradient(signal_type):
    """根据信号类型返回渐变色"""
    gradient_map = {
        "buy": ["#00f5a0", "#00d4aa"],
        "sell": ["#ff4757", "#ff3838"],
        "hold": ["#ffa502", "#ff7b00"],
    }
    return gradient_map.get(signal_type, ["#95a5a6", "#7f8c8d"])


def get_signal_label(signal_type):
    """根据信号类型返回中文标签"""
    label_map = {
        "buy": "强力买入",
        "sell": "建议卖出",
        "hold": "观望等待",
    }
    return label_map.get(signal_type, "未知")


def get_signal_icon(signal_type):
    """根据信号类型返回图标"""
    icon_map = {
        "buy": "🚀",
        "sell": "⚠️",
        "hold": "⏳",
    }
    return icon_map.get(signal_type, "❓")


def render_signal_badge(signal_type, confidence):
    """渲染带颜色的信号徽章"""
    badge_class = f"signal-badge signal-badge-{signal_type}"
    label = get_signal_label(signal_type)
    icon = get_signal_icon(signal_type)
    return f'<span class="{badge_class}">{icon} {label} {confidence:.1f}%</span>'


def create_gauge_chart(value, title, color):
    """创建仪表盘图表"""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": title, "font": {"size": 14, "color": "rgba(255,255,255,0.7)"}},
        number={"font": {"size": 24, "color": color, "family": "Inter"}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "rgba(255,255,255,0.2)"},
            "bar": {"color": color, "thickness": 0.75},
            "bgcolor": "rgba(255,255,255,0.05)",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 33], "color": "rgba(255,71,87,0.1)"},
                {"range": [33, 66], "color": "rgba(255,165,2,0.1)"},
                {"range": [66, 100], "color": "rgba(0,245,160,0.1)"},
            ],
            "threshold": {
                "line": {"color": color, "width": 2},
                "thickness": 0.8,
                "value": value,
            },
        },
    ))
    
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter", "color": "white"},
        margin={"t": 30, "b": 10, "l": 30, "r": 30},
        height=200,
    )
    return fig


def create_price_chart(historical_data, symbol, signals=None):
    """使用 Plotly 创建交互式价格走势图"""
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
        subplot_titles=(f"{symbol} 价格走势", "成交量"),
    )
    
    # K线图
    fig.add_trace(
        go.Candlestick(
            x=historical_data.index,
            open=historical_data["Open"],
            high=historical_data["High"],
            low=historical_data["Low"],
            close=historical_data["Close"],
            name="K线",
            increasing_line_color="#00f5a0",
            decreasing_line_color="#ff4757",
            increasing_fillcolor="rgba(0,245,160,0.3)",
            decreasing_fillcolor="rgba(255,71,87,0.3)",
        ),
        row=1, col=1,
    )
    
    # 移动平均线
    if "Close" in historical_data.columns:
        ma20 = historical_data["Close"].rolling(window=20).mean()
        ma50 = historical_data["Close"].rolling(window=50).mean()
        
        fig.add_trace(
            go.Scatter(
                x=historical_data.index,
                y=ma20,
                name="MA20",
                line={"color": "#00d4ff", "width": 1.5},
            ),
            row=1, col=1,
        )
        
        fig.add_trace(
            go.Scatter(
                x=historical_data.index,
                y=ma50,
                name="MA50",
                line={"color": "#ff006e", "width": 1.5},
            ),
            row=1, col=1,
        )
    
    # 成交量
    colors = ["#00f5a0" if historical_data["Close"].iloc[i] >= historical_data["Open"].iloc[i] 
              else "#ff4757" for i in range(len(historical_data))]
    
    fig.add_trace(
        go.Bar(
            x=historical_data.index,
            y=historical_data["Volume"],
            name="成交量",
            marker_color=colors,
            opacity=0.6,
        ),
        row=2, col=1,
    )
    
    # 布局
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter", "color": "white"},
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"t": 60, "b": 40, "l": 50, "r": 50},
        height=600,
    )
    
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="rgba(255,255,255,0.05)")
    
    return fig


def create_radar_chart(scores):
    """创建雷达图展示综合评分"""
    categories = ["买入评分", "卖出评分", "观望评分"]
    values = [
        scores.get("buy", 0),
        scores.get("sell", 0),
        scores.get("hold", 0),
    ]
    values += values[:1]  # 闭合图形
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories + [categories[0]],
        fill="toself",
        fillcolor="rgba(0,212,255,0.2)",
        line={"color": "#00d4ff", "width": 2},
        name="评分分布",
    ))
    
    fig.update_layout(
        polar={
            "radialaxis": {
                "visible": True,
                "range": [0, 100],
                "tickfont": {"color": "rgba(255,255,255,0.5)"},
                "gridcolor": "rgba(255,255,255,0.1)",
            },
            "angularaxis": {
                "tickfont": {"color": "rgba(255,255,255,0.7)", "size": 12},
                "gridcolor": "rgba(255,255,255,0.1)",
            },
            "bgcolor": "rgba(0,0,0,0)",
        },
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        margin={"t": 30, "b": 30, "l": 50, "r": 50},
        height=350,
    )
    
    return fig


def create_confidence_bar(signals):
    """创建置信度横向条形图"""
    agents = list(signals.keys())
    confidences = [signal.confidence for signal in signals.values()]
    colors_list = [get_signal_color(signal.signal_type) for signal in signals.values()]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        y=agents,
        x=confidences,
        orientation="h",
        marker_color=colors_list,
        text=[f"{c:.1f}%" for c in confidences],
        textposition="outside",
        textfont={"color": "white", "size": 12},
    ))
    
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter", "color": "white"},
        xaxis={
            "range": [0, 110],
            "gridcolor": "rgba(255,255,255,0.05)",
            "tickfont": {"color": "rgba(255,255,255,0.5)"},
        },
        yaxis={
            "gridcolor": "rgba(255,255,255,0.05)",
            "tickfont": {"color": "rgba(255,255,255,0.7)"},
        },
        showlegend=False,
        margin={"t": 20, "b": 40, "l": 120, "r": 60},
        height=200,
    )
    
    return fig


# ============================================================
# 页面渲染函数
# ============================================================
def render_header():
    """渲染页面头部"""
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown('<h1 class="main-header animate-in">🚀 AutoWealth AI</h1>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header animate-in">基于多智能体的智能投资分析引擎 · 让AI为您的投资决策赋能</p>', unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)


def render_sidebar():
    """渲染侧边栏导航"""
    with st.sidebar:
        # Logo区域
        st.markdown("""
        <div style="text-align: center; padding: 1rem 0;">
            <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🚀</div>
            <div style="font-size: 1.2rem; font-weight: 700; color: white;">AutoWealth AI</div>
            <div style="font-size: 0.8rem; color: rgba(255,255,255,0.4); margin-top: 0.25rem;">智能投资分析引擎</div>
        </div>
        <hr style="margin: 1rem 0;">
        """, unsafe_allow_html=True)
        
        # 导航
        st.markdown("<div style='font-size: 0.75rem; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 2px; margin-bottom: 0.5rem;'>功能导航</div>", unsafe_allow_html=True)
        
        page = st.radio(
            "选择功能",
            ["📊 单股分析", "📈 批量分析", "💼 投资组合", "🌍 市场概览"],
            label_visibility="collapsed",
        )
        
        st.markdown("<hr style='margin: 1.5rem 0;'>", unsafe_allow_html=True)
        
        # 智能体权重配置
        st.markdown("<div style='font-size: 0.75rem; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 2px; margin-bottom: 0.5rem;'>智能体权重配置</div>", unsafe_allow_html=True)
        
        tech_weight = st.slider(
            "🔬 技术分析",
            0.0, 1.0, 0.35, step=0.05,
            help="基于技术指标（MACD、RSI、布林带等）的分析权重",
        )
        fund_weight = st.slider(
            "📋 基本面分析",
            0.0, 1.0, 0.35, step=0.05,
            help="基于财务数据（估值、成长性等）的分析权重",
        )
        sent_weight = st.slider(
            "💭 情绪分析",
            0.0, 1.0, 0.30, step=0.05,
            help="基于市场情绪的综合评估权重",
        )
        
        # 权重归一化
        total = tech_weight + fund_weight + sent_weight
        if total > 0:
            tech_weight /= total
            fund_weight /= total
            sent_weight /= total
        
        # 显示归一化后的权重
        st.markdown(f"""
        <div style='background: rgba(255,255,255,0.03); border-radius: 8px; padding: 0.75rem; margin-top: 0.5rem;'>
            <div style='font-size: 0.75rem; color: rgba(255,255,255,0.4); margin-bottom: 0.5rem;'>实际权重分配</div>
            <div style='display: flex; gap: 0.5rem; flex-wrap: wrap;'>
                <span style='background: rgba(0,212,255,0.15); color: #00d4ff; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem;'>🔬 {tech_weight:.0%}</span>
                <span style='background: rgba(123,44,191,0.15); color: #a855f7; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem;'>📋 {fund_weight:.0%}</span>
                <span style='background: rgba(255,0,110,0.15); color: #ff006e; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem;'>💭 {sent_weight:.0%}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<hr style='margin: 1.5rem 0;'>", unsafe_allow_html=True)
        
        # 系统状态
        st.markdown("""
        <div style='background: rgba(0,245,160,0.05); border: 1px solid rgba(0,245,160,0.2); border-radius: 8px; padding: 0.75rem;'>
            <div style='display: flex; align-items: center; gap: 0.5rem;'>
                <div style='width: 8px; height: 8px; background: #00f5a0; border-radius: 50%; box-shadow: 0 0 8px rgba(0,245,160,0.5);' class='pulse'></div>
                <span style='font-size: 0.8rem; color: #00f5a0;'>系统运行正常</span>
            </div>
            <div style='font-size: 0.7rem; color: rgba(255,255,255,0.3); margin-top: 0.25rem;'>所有智能体已就绪</div>
        </div>
        """, unsafe_allow_html=True)
        
        return page, (tech_weight, fund_weight, sent_weight)


def render_single_analysis(engine, weights=(0.35, 0.35, 0.30)):
    tech_weight, fund_weight, sent_weight = weights
    """渲染单股分析页面"""
    st.markdown('<h2 class="section-header"><span class="section-icon">📊</span> 单股深度分析</h2>', unsafe_allow_html=True)
    
    # 输入区域 - 玻璃拟态卡片
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    col1, col2 = st.columns([4, 1])
    with col1:
        symbol = st.text_input(
            "股票代码",
            placeholder="例如: AAPL, GOOGL, 600519.SS, BTC-USD",
            label_visibility="visible",
            help="输入股票代码，支持美股、A股、加密货币等",
        )
    with col2:
        st.write("")
        st.write("")
        analyze_btn = st.button("🚀 开始分析", type="primary", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    if analyze_btn and symbol:
        symbol = symbol.strip().upper()
        
        # 分析进度动画
        progress_placeholder = st.empty()
        with progress_placeholder.container():
            st.markdown("""
            <div style="text-align: center; padding: 2rem;">
                <div style="font-size: 3rem; margin-bottom: 1rem;" class="pulse">🤖</div>
                <div style="font-size: 1.2rem; color: rgba(255,255,255,0.7); margin-bottom: 0.5rem;">
                    正在分析 <strong style="color: #00d4ff;">{}</strong> ...
                </div>
                <div style="font-size: 0.85rem; color: rgba(255,255,255,0.4);">
                    多智能体协同分析中 · 请稍候
                </div>
            </div>
            """.format(symbol), unsafe_allow_html=True)
        
        try:
            result = engine.analyze(symbol)
            progress_placeholder.empty()
            
            if result["success"]:
                _display_single_result(result)
            else:
                error_text = result.get('error', '未知错误')
                # 如果是限流错误，尝试用demo数据直接分析
                if "Too Many Requests" in error_text or "Rate limited" in error_text or "429" in error_text:
                    st.warning("⚠️ Yahoo Finance API限流中，正在使用模拟数据进行演示分析...")
                    try:
                        from autowealth.core.demo_data import DemoDataGenerator
                        from autowealth.core.analyzer import TechnicalAnalyzer
                        from autowealth.agents.coordinator import AgentCoordinator
                        from autowealth.agents.technical_agent import TechnicalAgent
                        from autowealth.agents.fundamental_agent import FundamentalAgent
                        from autowealth.agents.sentiment_agent import SentimentAgent
                        
                        generator = DemoDataGenerator()
                        demo_data = generator.generate_stock_data(symbol, days=365)
                        
                        if not demo_data.empty:
                            # 用demo数据重新构建分析结果
                            tech_analyzer = TechnicalAnalyzer()
                            tech_result = tech_analyzer.full_analysis(demo_data).iloc[-1].to_dict()
                            
                            coordinator = AgentCoordinator()
                            coordinator.register_agent(TechnicalAgent(), weight=tech_weight)
                            coordinator.register_agent(FundamentalAgent(), weight=fund_weight)
                            coordinator.register_agent(SentimentAgent(), weight=sent_weight)
                            
                            analysis_data = {
                                "historical_data": demo_data,
                                "stock_info": {"symbol": symbol, "name": symbol, "sector": "N/A", "market_cap": 0}
                            }
                            coord_result = coordinator.analyze(symbol, analysis_data)
                            
                            fallback_result = {
                                "symbol": symbol,
                                "success": True,
                                "decision": coord_result["final_decision"],
                                "individual_signals": coord_result["individual_signals"],
                                "summary": coord_result["analysis_summary"],
                                "technical_analysis": tech_analyzer.full_analysis(demo_data).iloc[-10:].to_dict(),
                                "stock_info": {"symbol": symbol, "name": symbol},
                                "is_demo_data": True,
                            }
                            _display_single_result(fallback_result)
                        else:
                            st.error("❌ 模拟数据生成失败，请稍后再试")
                    except Exception as demo_err:
                        st.error(f"❌ 演示分析出错: {demo_err}")
                else:
                    st.error(f"❌ 分析失败: {error_text}")
        
        except Exception as e:
            progress_placeholder.empty()
            error_msg = str(e)
            if "Too Many Requests" in error_msg or "Rate limited" in error_msg:
                st.warning("⚠️ Yahoo Finance API限流中，已自动切换到模拟数据进行演示分析。实时数据将在限流解除后恢复。")
            else:
                st.error(f"❌ 分析出错: {error_msg}")
    
    elif analyze_btn and not symbol:
        st.warning("⚠️ 请输入股票代码")


def _display_single_result(result):
    """展示单股分析的详细结果"""
    decision = result.get("decision", {})
    stock_info = result.get("stock_info", {})
    individual_signals = result.get("individual_signals", {})
    
    # ---- 基本信息栏 ----
    st.markdown('<div class="animate-in">', unsafe_allow_html=True)
    
    cols = st.columns(4)
    metrics = [
        ("股票代码", result.get("symbol", "N/A"), "📈"),
        ("公司名称", stock_info.get("name", "N/A"), "🏢"),
        ("所属行业", stock_info.get("industry", "N/A"), "🏭"),
        ("当前市值", f"${stock_info.get('market_cap', 0):,.0f}" if stock_info.get('market_cap') else "N/A", "💰"),
    ]
    
    for col, (label, value, icon) in zip(cols, metrics):
        with col:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{icon} {label}</div>
                <div class="metric-value">{value}</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # ---- 综合决策 ----
    st.markdown('<h2 class="section-header"><span class="section-icon">🎯</span> AI综合决策</h2>', unsafe_allow_html=True)
    
    signal_type = decision.get("signal_type", "hold")
    confidence = decision.get("confidence", 0)
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.markdown("<div style='margin: 1rem 0;'>", unsafe_allow_html=True)
        st.markdown(render_signal_badge(signal_type, confidence), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        # 详细理由
        reasoning = decision.get("reasoning", "")
        if reasoning:
            with st.expander("📋 查看详细分析理由"):
                st.markdown(f"<div style='color: rgba(255,255,255,0.7); line-height: 1.6;'>{reasoning}</div>", unsafe_allow_html=True)
    
    with col2:
        target_price = decision.get("target_price")
        st.markdown(f"""
        <div class="metric-card" style="border-color: rgba(0,245,160,0.3);">
            <div class="metric-label">🎯 目标价位</div>
            <div class="metric-value" style="color: #00f5a0;">{f"${target_price:.2f}" if target_price else "N/A"}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        stop_loss = decision.get("stop_loss")
        st.markdown(f"""
        <div class="metric-card" style="border-color: rgba(255,71,87,0.3);">
            <div class="metric-label">🛡️ 止损价位</div>
            <div class="metric-value" style="color: #ff4757;">{f"${stop_loss:.2f}" if stop_loss else "N/A"}</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # ---- 各智能体信号 ----
    st.markdown('<h2 class="section-header"><span class="section-icon">🤖</span> 智能体分析详情</h2>', unsafe_allow_html=True)
    
    if individual_signals:
        # 置信度条形图
        fig = create_confidence_bar(individual_signals)
        st.plotly_chart(fig, use_container_width=True, key="confidence_bar")
        
        # 智能体卡片
        cols = st.columns(min(len(individual_signals), 3))
        for idx, (agent_name, signal) in enumerate(individual_signals.items()):
            with cols[idx % 3]:
                card_class = f"signal-card signal-card-{signal.signal_type}"
                icon = get_signal_icon(signal.signal_type)
                color = get_signal_color(signal.signal_type)
                label = get_signal_label(signal.signal_type)
                
                st.markdown(f"""
                <div class="{card_class}">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <strong style="color: rgba(255,255,255,0.9); font-size: 1.1rem;">{agent_name}</strong>
                        <span style="font-size: 1.5rem;">{icon}</span>
                    </div>
                    <div style="color: {color}; font-weight: 700; font-size: 1.2rem; margin-bottom: 0.5rem;">
                        {label} {signal.confidence:.1f}%
                    </div>
                    <div style="background: rgba(255,255,255,0.05); border-radius: 6px; padding: 0.5rem;">
                        <div style="font-size: 0.75rem; color: rgba(255,255,255,0.4); margin-bottom: 0.25rem;">分析理由</div>
                        <div style="font-size: 0.85rem; color: rgba(255,255,255,0.7); line-height: 1.5;">
                            {signal.reasoning[:100] + "..." if len(signal.reasoning) > 100 else signal.reasoning}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("ℹ️ 暂无智能体信号数据")
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # ---- 综合评分 ----
    st.markdown('<h2 class="section-header"><span class="section-icon">📊</span> 综合评分分析</h2>', unsafe_allow_html=True)
    
    scores = decision.get("scores", {})
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # 雷达图
        fig = create_radar_chart(scores)
        st.plotly_chart(fig, use_container_width=True, key="radar_chart")
    
    with col2:
        # 评分指标卡
        score_items = [
            ("买入评分", scores.get("buy", 0), "#00f5a0", "🚀"),
            ("卖出评分", scores.get("sell", 0), "#ff4757", "⚠️"),
            ("观望评分", scores.get("hold", 0), "#ffa502", "⏳"),
        ]
        
        for label, value, color, icon in score_items:
            st.markdown(f"""
            <div style="margin: 0.75rem 0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
                    <span style="color: rgba(255,255,255,0.7);">{icon} {label}</span>
                    <span style="color: {color}; font-weight: 700;">{value:.1f}%</span>
                </div>
                <div style="background: rgba(255,255,255,0.05); border-radius: 6px; height: 8px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, {color}88, {color}); height: 100%; width: {min(value, 100)}%; border-radius: 6px; transition: width 1s ease;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # ---- 价格走势图 ----
    st.markdown('<h2 class="section-header"><span class="section-icon">📈</span> 价格走势分析</h2>', unsafe_allow_html=True)
    
    try:
        tech_data = result.get("technical_analysis", {})
        if tech_data and "historical_data" in result:
            hist_data = result["historical_data"]
            if isinstance(hist_data, pd.DataFrame) and not hist_data.empty:
                fig = create_price_chart(hist_data, result.get("symbol", ""))
                st.plotly_chart(fig, use_container_width=True, key="price_chart")
            else:
                st.info("ℹ️ 价格走势图需要历史数据支持")
        else:
            st.info("ℹ️ 暂无技术分析数据")
    except Exception:
        st.info("ℹ️ 暂无价格走势数据")


def render_batch_analysis(engine):
    """渲染批量分析页面"""
    st.markdown('<h2 class="section-header"><span class="section-icon">📈</span> 批量智能分析</h2>', unsafe_allow_html=True)
    
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    symbols_input = st.text_area(
        "输入股票代码（逗号分隔）",
        placeholder="例如: AAPL, GOOGL, MSFT, AMZN, META, TSLA, NVDA",
        height=120,
        help="输入多个股票代码，用逗号分隔，AI将同时分析所有股票",
    )
    st.markdown('</div>', unsafe_allow_html=True)
    
    if st.button("🚀 开始批量分析", type="primary"):
        symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]
        
        if not symbols:
            st.warning("⚠️ 请输入至少一个股票代码")
            return
        
        # 进度显示
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            result = engine.analyze_batch(symbols)
            progress_bar.empty()
            status_text.empty()
            
            # ---- 统计概览 ----
            summary = result.get("summary", {})
            
            st.markdown('<div class="animate-in">', unsafe_allow_html=True)
            cols = st.columns(4)
            stats = [
                ("📊 分析总数", summary.get("total", 0), "#00d4ff"),
                ("✅ 成功分析", summary.get("success", 0), "#00f5a0"),
                ("🚀 买入推荐", summary.get("buy_count", 0), "#00f5a0"),
                ("⚠️ 卖出推荐", summary.get("sell_count", 0), "#ff4757"),
            ]
            
            for col, (label, value, color) in zip(cols, stats):
                with col:
                    st.markdown(f"""
                    <div class="metric-card" style="border-color: {color}33;">
                        <div class="metric-label">{label}</div>
                        <div class="metric-value" style="color: {color};">{value}</div>
                    </div>
                    """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            recommendations = result.get("recommendations", {})
            
            # ---- 买入推荐列表 ----
            buy_list = recommendations.get("buy", [])
            if buy_list:
                st.markdown('<h3 style="color: #00f5a0; margin-top: 1.5rem;">🚀 买入推荐</h3>', unsafe_allow_html=True)
                buy_df = pd.DataFrame(buy_list, columns=["股票代码", "置信度"])
                buy_df.insert(0, "排名", range(1, len(buy_df) + 1))
                buy_df["信号"] = "买入"
                buy_df["置信度"] = buy_df["置信度"].apply(lambda x: f"{x:.1f}%")
                
                st.dataframe(
                    buy_df.style.set_properties(**{
                        "background-color": "rgba(0,245,160,0.05)",
                        "color": "white",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("ℹ️ 暂无买入推荐")
            
            # ---- 卖出推荐列表 ----
            sell_list = recommendations.get("sell", [])
            if sell_list:
                st.markdown('<h3 style="color: #ff4757; margin-top: 1.5rem;">⚠️ 卖出推荐</h3>', unsafe_allow_html=True)
                sell_df = pd.DataFrame(sell_list, columns=["股票代码", "置信度"])
                sell_df.insert(0, "排名", range(1, len(sell_df) + 1))
                sell_df["信号"] = "卖出"
                sell_df["置信度"] = sell_df["置信度"].apply(lambda x: f"{x:.1f}%")
                
                st.dataframe(
                    sell_df.style.set_properties(**{
                        "background-color": "rgba(255,71,87,0.05)",
                        "color": "white",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("ℹ️ 暂无卖出推荐")
            
            # ---- 观望列表 ----
            hold_list = recommendations.get("hold", [])
            if hold_list:
                st.markdown('<h3 style="color: #ffa502; margin-top: 1.5rem;">⏳ 观望列表</h3>', unsafe_allow_html=True)
                hold_df = pd.DataFrame(hold_list, columns=["股票代码", "置信度"])
                hold_df.insert(0, "排名", range(1, len(hold_df) + 1))
                hold_df["信号"] = "观望"
                hold_df["置信度"] = hold_df["置信度"].apply(lambda x: f"{x:.1f}%")
                
                st.dataframe(
                    hold_df.style.set_properties(**{
                        "background-color": "rgba(255,165,2,0.05)",
                        "color": "white",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
            
            # ---- 详细结果（可展开） ----
            all_results = result.get("results", {})
            if all_results:
                with st.expander("📋 查看所有详细分析结果"):
                    for sym, analysis in all_results.items():
                        if analysis.get("success") and "decision" in analysis:
                            d = analysis["decision"]
                            color = get_signal_color(d["signal_type"])
                            icon = get_signal_icon(d["signal_type"])
                            label = get_signal_label(d["signal_type"])
                            
                            st.markdown(f"""
                            <div style="display: flex; align-items: center; gap: 0.5rem; margin: 0.5rem 0; padding: 0.5rem; background: rgba(255,255,255,0.02); border-radius: 8px;">
                                <strong style="color: rgba(255,255,255,0.9);">{sym}</strong>
                                <span style="color: {color}; font-weight: 700;">{icon} {label} {d['confidence']:.1f}%</span>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown(f"❌ **{sym}**: 分析失败")
        
        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            error_msg = str(e)
            if "Too Many Requests" in error_msg or "Rate limited" in error_msg:
                st.warning("⚠️ Yahoo Finance API限流中，已自动切换到模拟数据进行演示分析。实时数据将在限流解除后恢复。")
            else:
                st.error(f"❌ 批量分析出错: {error_msg}")


def render_portfolio(engine):
    """渲染投资组合分析页面"""
    st.markdown('<h2 class="section-header"><span class="section-icon">💼</span> 投资组合智能分析</h2>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="glass-card">
        <div style="color: rgba(255,255,255,0.7); line-height: 1.6;">
            💡 <strong>使用说明：</strong>输入您的持仓信息（股票代码、数量、成本价），AI将分析您的投资组合风险、收益预期，并给出优化建议。
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 初始化 session_state 中的持仓列表
    if "holdings" not in st.session_state:
        st.session_state.holdings = [
            {"symbol": "", "quantity": 100, "cost_basis": 0.0}
        ]
    
    # 渲染持仓输入行
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    for i, holding in enumerate(st.session_state.holdings):
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        with col1:
            holding["symbol"] = st.text_input(
                f"股票代码 #{i+1}", holding["symbol"], key=f"sym_{i}",
                placeholder="如: AAPL",
            )
        with col2:
            holding["quantity"] = st.number_input(
                f"数量 #{i+1}", 0, 10000000, holding["quantity"], key=f"qty_{i}",
            )
        with col3:
            holding["cost_basis"] = st.number_input(
                f"成本价 #{i+1}", 0.0, 1000000.0,
                float(holding["cost_basis"]),
                key=f"cost_{i}",
            )
        with col4:
            st.write("")
            st.write("")
            if st.button("🗑️", key=f"del_{i}", help="删除该持仓"):
                if len(st.session_state.holdings) > 1:
                    st.session_state.holdings.pop(i)
                    st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 添加持仓按钮
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("➕ 添加持仓", use_container_width=True):
            st.session_state.holdings.append({"symbol": "", "quantity": 100, "cost_basis": 0.0})
            st.rerun()
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # 分析按钮
    if st.button("🚀 分析投资组合", type="primary"):
        valid_holdings = [h for h in st.session_state.holdings if h.get("symbol")]
        
        if not valid_holdings:
            st.warning("⚠️ 请至少输入一个有效的持仓")
            return
        
        with st.spinner("🤖 AI正在深度分析您的投资组合..."):
            try:
                portfolio = engine.get_portfolio_analysis(valid_holdings)
                
                # ---- 总览指标 ----
                st.markdown('<div class="animate-in">', unsafe_allow_html=True)
                cols = st.columns(3)
                metrics = [
                    ("💰 总市值", f"${portfolio.get('total_value', 0):,.2f}", "#00d4ff"),
                    ("📈 总盈亏", f"${portfolio.get('total_gain_loss', 0):,.2f}", "#00f5a0" if portfolio.get('total_gain_loss', 0) >= 0 else "#ff4757"),
                    ("📊 收益率", f"{portfolio.get('return_pct', 0):.2f}%", "#00f5a0" if portfolio.get('return_pct', 0) >= 0 else "#ff4757"),
                ]
                
                for col, (label, value, color) in zip(cols, metrics):
                    with col:
                        st.markdown(f"""
                        <div class="metric-card" style="border-color: {color}33;">
                            <div class="metric-label">{label}</div>
                            <div class="metric-value" style="color: {color};">{value}</div>
                        </div>
                        """, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
                st.markdown("<hr>", unsafe_allow_html=True)
                
                # ---- 持仓详情表 ----
                holdings_list = portfolio.get("holdings", [])
                if holdings_list:
                    st.markdown('<h3 style="color: rgba(255,255,255,0.9); margin-bottom: 1rem;">📋 持仓详情</h3>', unsafe_allow_html=True)
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
                    
                    st.dataframe(
                        display_df.style.set_properties(**{
                            "background-color": "rgba(255,255,255,0.02)",
                            "color": "white",
                        }),
                        use_container_width=True,
                        hide_index=True,
                    )
                    
                    # 持仓分布饼图
                    if "holding_value" in holdings_df.columns and "symbol" in holdings_df.columns:
                        fig = go.Figure(data=[go.Pie(
                            labels=holdings_df["symbol"],
                            values=holdings_df["holding_value"],
                            hole=0.4,
                            marker_colors=px.colors.sequential.Plasma_r,
                            textinfo="label+percent",
                            textfont={"color": "white", "size": 12},
                        )])
                        
                        fig.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            font={"family": "Inter", "color": "white"},
                            showlegend=False,
                            margin={"t": 30, "b": 30, "l": 30, "r": 30},
                            height=400,
                            annotations=[{
                                "text": "持仓分布",
                                "x": 0.5,
                                "y": 0.5,
                                "font_size": 16,
                                "font_color": "rgba(255,255,255,0.7)",
                                "showarrow": False,
                            }],
                        )
                        
                        st.plotly_chart(fig, use_container_width=True, key="portfolio_pie")
                else:
                    st.info("ℹ️ 暂无持仓分析数据")
            
            except Exception as e:
                st.error(f"❌ 投资组合分析出错: {str(e)}")


def render_market_overview(engine):
    """渲染市场概览页面"""
    st.markdown('<h2 class="section-header"><span class="section-icon">🌍</span> 全球市场概览</h2>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="glass-card">
        <div style="color: rgba(255,255,255,0.7); line-height: 1.6;">
            🌐 <strong>实时追踪：</strong>获取全球主要股指的实时数据，掌握市场脉搏，洞察投资机会。
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("🔄 刷新市场数据", type="primary"):
        with st.spinner("🌐 正在获取全球市场数据..."):
            try:
                overview = engine.get_market_overview()
                
                if overview.get("success"):
                    indices = overview.get("indices", {})
                    
                    if not indices:
                        st.warning("⚠️ 暂无市场数据")
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
                    
                    # 显示数据表格
                    st.markdown('<h3 style="color: rgba(255,255,255,0.9); margin: 1.5rem 0 1rem;">📊 主要指数行情</h3>', unsafe_allow_html=True)
                    
                    def color_change(val):
                        if val > 0:
                            return "color: #00f5a0; font-weight: bold;"
                        elif val < 0:
                            return "color: #ff4757; font-weight: bold;"
                        return "color: rgba(255,255,255,0.5);"
                    
                    styled_df = df.style.applymap(color_change, subset=["涨跌幅(%)"])
                    st.dataframe(styled_df, use_container_width=True, hide_index=True)
                    
                    st.markdown("<hr>", unsafe_allow_html=True)
                    
                    # 使用 Plotly 绘制涨跌幅柱状图
                    st.markdown('<h3 style="color: rgba(255,255,255,0.9); margin: 1.5rem 0 1rem;">📈 涨跌幅可视化</h3>', unsafe_allow_html=True)
                    
                    colors = [
                        "#00f5a0" if v >= 0 else "#ff4757"
                        for v in df["涨跌幅(%)"]
                    ]
                    
                    fig = go.Figure()
                    
                    fig.add_trace(go.Bar(
                        x=df["指数"],
                        y=df["涨跌幅(%)"],
                        marker_color=colors,
                        text=[f"{v:+.2f}%" for v in df["涨跌幅(%)"]],
                        textposition="outside",
                        textfont={"color": "white", "size": 12},
                    ))
                    
                    fig.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font={"family": "Inter", "color": "white"},
                        xaxis={
                            "gridcolor": "rgba(255,255,255,0.05)",
                            "tickfont": {"color": "rgba(255,255,255,0.7)"},
                        },
                        yaxis={
                            "gridcolor": "rgba(255,255,255,0.05)",
                            "tickfont": {"color": "rgba(255,255,255,0.5)"},
                            "title": "涨跌幅 (%)",
                        },
                        showlegend=False,
                        margin={"t": 40, "b": 60, "l": 60, "r": 40},
                        height=450,
                    )
                    
                    fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.2)")
                    
                    st.plotly_chart(fig, use_container_width=True, key="market_bar")
                else:
                    st.error(f"❌ 获取市场数据失败: {overview.get('error', '未知错误')}")
            
            except Exception as e:
                error_msg = str(e)
                if "Too Many Requests" in error_msg or "Rate limited" in error_msg:
                    st.warning("⚠️ Yahoo Finance API限流中，已自动切换到模拟数据进行演示分析。实时数据将在限流解除后恢复。")
                else:
                    st.error(f"❌ 市场概览出错: {error_msg}")


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
    if page == "📊 单股分析":
        render_single_analysis(engine, weights)
    elif page == "📈 批量分析":
        render_batch_analysis(engine)
    elif page == "💼 投资组合":
        render_portfolio(engine)
    elif page == "🌍 市场概览":
        render_market_overview(engine)
    
    # 页脚
    st.markdown("""
    <div class="footer">
        <div style="font-size: 1.2rem; margin-bottom: 0.5rem;">🚀 AutoWealth AI</div>
        <div>基于多智能体的智能投资分析引擎</div>
        <div style="margin-top: 0.5rem; font-size: 0.75rem;">
            ⚠️ 仅供教育和研究目的，不构成投资建议 · 投资有风险，决策需谨慎
        </div>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
