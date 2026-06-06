#!/usr/bin/env python3
# AutoWealth AI - 600545 普莱柯 实际数据分析演示

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from autowealth.core.engine import AutoWealthEngine
from autowealth.core.data_fetcher import DataFetcher
from autowealth.core.analyzer import TechnicalAnalyzer, FundamentalAnalyzer
from autowealth.agents.coordinator import AgentCoordinator
from autowealth.agents.technical_agent import TechnicalAgent
from autowealth.agents.fundamental_agent import FundamentalAgent
from autowealth.agents.sentiment_agent import SentimentAgent

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

def analyze_stock_600545():
    symbol = '600545'
    
    print()
    print('='*70)
    print('  AutoWealth AI - 600545 普莱柯 深度分析')
    print('='*70)
    
    try:
        # 使用Yahoo Finance数据源获取A股数据
        fetcher = DataFetcher(source='yfinance')
        
        print()
        print('--- 1. 数据获取 ---')
        historical_data = fetcher.get_stock_data(symbol, period='1y')
        stock_info = fetcher.get_stock_info(symbol)
        
        print('  数据状态: ✓ 成功获取')
        print('  数据范围: {} 个交易日'.format(len(historical_data)))
        print('  数据周期: 最近1年')
        
        # 获取最新数据
        latest = historical_data.iloc[-1]
        prev = historical_data.iloc[-2] if len(historical_data) > 1 else latest
        
        # 计算涨跌幅
        price_change = latest['Close'] - prev['Close']
        price_change_pct = (price_change / prev['Close']) * 100 if prev['Close'] > 0 else 0
        
        # 显示股票基本信息
        print()
        print('--- 2. 公司基本信息 ---')
        print('  股票代码: 600545.SH')
        print('  公司名称: {}'.format(stock_info.get('name', 'N/A')))
        print('  所属行业: {}'.format(stock_info.get('industry', 'N/A')))
        print('  所属板块: {}'.format(stock_info.get('sector', 'N/A')))
        print('  总市值: {:,.0f} 元'.format(stock_info.get('market_cap', 0)))
        print('  市盈率(PE): {:.2f}'.format(stock_info.get('pe_ratio', 0)))
        print('  市净率(PB): {:.2f}'.format(stock_info.get('pb_ratio', 0)))
        print('  52周最高: {:.2f} 元'.format(stock_info.get('fifty_two_week_high', 0)))
        print('  52周最低: {:.2f} 元'.format(stock_info.get('fifty_two_week_low', 0)))
        print('  最新收盘价: {:.2f} 元'.format(latest['Close']))
        print('  涨跌幅: {:+.2f} ({:+.2f}%)'.format(price_change, price_change_pct))
        print('  成交量: {:,.0f} 手'.format(latest['Volume']))
        
        # 技术分析
        print()
        print('--- 3. 技术分析 ---')
        ta = TechnicalAnalyzer()
        analyzed_data = ta.full_analysis(historical_data)
        latest_tech = analyzed_data.iloc[-1]
        
        ma5 = latest_tech.get('MA5', 0)
        ma20 = latest_tech.get('MA20', 0)
        ma60 = latest_tech.get('MA60', 0)
        ma_signal = '多头排列' if ma5 > ma20 > ma60 else '空头排列' if ma5 < ma20 < ma60 else '震荡'
        
        print('  MA5: {:.2f}'.format(ma5))
        print('  MA20: {:.2f}'.format(ma20))
        print('  MA60: {:.2f}'.format(ma60))
        print('  MA信号: {}'.format(ma_signal))
        
        macd = latest_tech.get('MACD', 0)
        macd_signal = latest_tech.get('MACD_Signal', 0)
        macd_hist = latest_tech.get('MACD_Histogram', 0)
        macd_trend = '金叉' if macd > macd_signal and macd_hist > 0 else '死叉' if macd < macd_signal else '盘整'
        
        print('  MACD: {:.4f}'.format(macd))
        print('  MACD Signal: {:.4f}'.format(macd_signal))
        print('  MACD趋势: {}'.format(macd_trend))
        
        rsi = latest_tech.get('RSI', 0)
        rsi_status = '超买' if rsi > 70 else '超卖' if rsi < 30 else '正常'
        print('  RSI(14): {:.2f} ({})'.format(rsi, rsi_status))
        
        k = latest_tech.get('K', 0)
        d = latest_tech.get('D', 0)
        j = latest_tech.get('J', 0)
        kdj_status = '金叉' if k > d else '死叉'
        print('  KDJ-K: {:.2f}'.format(k))
        print('  KDJ-D: {:.2f}'.format(d))
        print('  KDJ-J: {:.2f}'.format(j))
        print('  KDJ信号: {}'.format(kdj_status))
        
        bb_upper = latest_tech.get('BB_Upper', 0)
        bb_lower = latest_tech.get('BB_Lower', 0)
        bb_position = latest_tech.get('BB_Position', 0)
        bb_status = '上轨附近' if bb_position > 0.8 else '下轨附近' if bb_position < 0.2 else '中轨附近'
        print('  布林上轨: {:.2f}'.format(bb_upper))
        print('  布林下轨: {:.2f}'.format(bb_lower))
        print('  布林带位置: {}'.format(bb_status))
        
        vol_ratio = latest_tech.get('Volume_Ratio', 0)
        vol_status = '放量' if vol_ratio > 1.5 else '缩量' if vol_ratio < 0.8 else '正常'
        print('  量比: {:.2f} ({})'.format(vol_ratio, vol_status))
        
        # 基本面分析
        print()
        print('--- 4. 基本面分析 ---')
        fa = FundamentalAnalyzer()
        valuation = fa.analyze_valuation(stock_info)
        growth = fa.analyze_growth(historical_data)
        
        print('  估值评分: {:.1f}/100'.format(valuation['valuation_score']))
        print('  成长评分: {:.1f}/100'.format(growth['growth_score']))
        print('  1月收益率: {:.2f}%'.format(growth['return_1m']))
        print('  3月收益率: {:.2f}%'.format(growth['return_3m']))
        print('  趋势判断: {}'.format(growth['trend']))
        
        # 多智能体分析
        print()
        print('--- 5. 多智能体综合分析 ---')
        
        analysis_data = {
            'historical_data': historical_data,
            'stock_info': stock_info,
        }
        
        coordinator = AgentCoordinator()
        coordinator.register_agent(TechnicalAgent(), weight=0.35)
        coordinator.register_agent(FundamentalAgent(), weight=0.35)
        coordinator.register_agent(SentimentAgent(), weight=0.30)
        
        result = coordinator.analyze(symbol, analysis_data)
        decision = result['final_decision']
        signals = result['individual_signals']
        
        print()
        print('  各智能体信号:')
        for agent_name, signal in signals.items():
            print('    {}: {} (置信度: {}%)'.format(agent_name, signal.signal_type.upper(), signal.confidence))
        
        # 综合决策
        print()
        print('--- 6. 综合决策 ---')
        signal_type = decision.get('signal_type', 'hold')
        confidence = decision.get('confidence', 0)
        scores = decision.get('scores', {})
        
        buy_rate = scores.get('buy', 0)
        sell_rate = scores.get('sell', 0)
        hold_rate = scores.get('hold', 0)
        
        signal_text = {
            'buy': '强烈买入',
            'sell': '强烈卖出',
            'hold': '观望等待'
        }.get(signal_type, '未知')
        
        print()
        print('  综合建议: {}'.format(signal_text))
        print('  置信度: {:.1f}%'.format(confidence))
        print('  买入率: {:.1f}%'.format(buy_rate))
        print('  卖出率: {:.1f}%'.format(sell_rate))
        print('  观望率: {:.1f}%'.format(hold_rate))
        
        if decision.get('target_price'):
            print('  目标价: {:.2f} 元'.format(decision['target_price']))
        if decision.get('stop_loss'):
            print('  止损价: {:.2f} 元'.format(decision['stop_loss']))
        
        # 决策理由
        print()
        print('--- 7. 决策理由 ---')
        reasoning = decision.get('reasoning', '')
        print(reasoning)
        
        # 风险提示
        print()
        print('--- 8. 风险提示 ---')
        print('  以上分析仅供参考，不构成投资建议。')
        print('  投资有风险，入市需谨慎。')
        
        print()
        print('='*70)
        print('  分析完成')
        print('='*70)
        
    except Exception as e:
        print()
        print('错误: {}'.format(e))
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    analyze_stock_600545()
