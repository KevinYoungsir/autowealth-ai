"""
中文自然语言解析器
将用户的中文输入解析为结构化指令，支持股票分析、批量分析、投资组合、市场概览、回测、组合优化等意图。
"""
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 中文股票名称到代码的映射（常见A股/美股）
CHINESE_NAME_TO_SYMBOL: Dict[str, str] = {
    # A股
    "茅台": "600519.SS",
    "贵州茅台": "600519.SS",
    "五粮液": "000858.SZ",
    "平安": "601318.SS",
    "中国平安": "601318.SS",
    "招行": "600036.SS",
    "招商银行": "600036.SS",
    "工行": "601398.SS",
    "工商银行": "601398.SS",
    "建行": "601939.SS",
    "建设银行": "601939.SS",
    "农行": "601288.SS",
    "农业银行": "601288.SS",
    "中行": "601988.SS",
    "中国银行": "601988.SS",
    "比亚迪": "002594.SZ",
    "宁德时代": "300750.SZ",
    "腾讯": "0700.HK",
    "阿里巴巴": "9988.HK",
    "美团": "3690.HK",
    "小米": "1810.HK",
    "京东": "9618.HK",
    "百度": "9888.HK",
    "网易": "9999.HK",
    "中石油": "601857.SS",
    "中石化": "600028.SS",
    "长江电力": "600900.SS",
    "恒瑞医药": "600276.SS",
    "迈瑞医疗": "300760.SZ",
    "海康威视": "002415.SZ",
    "美的": "000333.SZ",
    "美的集团": "000333.SZ",
    "格力": "000651.SZ",
    "格力电器": "000651.SZ",
    "伊利": "600887.SS",
    "伊利股份": "600887.SS",
    "中芯国际": "688981.SS",
    "隆基绿能": "601012.SS",
    "药明康德": "603259.SS",
    "中信证券": "600030.SS",
    "东方财富": "300059.SZ",
    "兴业证券": "601377.SS",
    "华泰证券": "601688.SS",
    "国泰君安": "601211.SS",
    "海通证券": "600837.SS",
    # 美股
    "苹果": "AAPL",
    "苹果公司": "AAPL",
    "微软": "MSFT",
    "谷歌": "GOOGL",
    "亚马逊": "AMZN",
    "特斯拉": "TSLA",
    "英伟达": "NVDA",
    "Meta": "META",
    "脸书": "META",
    "Facebook": "META",
    "奈飞": "NFLX",
    "Netflix": "NFLX",
    "英特尔": "INTC",
    "AMD": "AMD",
    "高通": "QCOM",
    "甲骨文": "ORCL",
    "思科": "CSCO",
    "波音": "BA",
    "迪士尼": "DIS",
    "沃尔玛": "WMT",
    "可口可乐": "KO",
    "百事": "PEP",
    "强生": "JNJ",
    "辉瑞": "PFE",
    "摩根大通": "JPM",
    "高盛": "GS",
    "伯克希尔": "BRK-B",
    "巴菲特": "BRK-B",
    "Visa": "V",
    "Mastercard": "MA",
    "宝洁": "PG",
    "联合健康": "UNH",
    "埃克森美孚": "XOM",
    "雪佛龙": "CVX",
    "壳牌": "SHEL",
    "丰田": "TM",
    "本田": "HMC",
    "索尼": "SONY",
    "三星": "005930.KS",
    "台积电": "TSM",
    "ASML": "ASML",
    "诺和诺德": "NVO",
    "礼来": "LLY",
    "默沙东": "MRK",
    "赛诺菲": "SNY",
    "罗氏": "ROG.SW",
    "雀巢": "NESN.SW",
    "路易威登": "MC.PA",
    "爱马仕": "RMS.PA",
}

# 非股票大写词黑名单
_NON_STOCK_WORDS = {
    "POST", "GET", "API", "NLP", "AI", "HTTP", "HTTPS", "JSON", "XML", "HTML", "CSS",
    "SQL", "URL", "USA", "UK", "EU", "UN", "NASA", "FBI", "CIA", "IBM", "CPU", "GPU",
    "RAM", "SSD", "HDD", "USB", "PDF", "DOC", "XLS", "PPT", "CSV", "TXT", "JPG", "PNG",
    "GIF", "MP3", "MP4", "AVI", "WAV", "ZIP", "RAR", "TAR", "GZ", "EXE", "DLL", "BAT",
    "CMD", "SH", "PY", "JS", "TS", "JAVA", "CPP", "GO", "RUST", "PHP", "RUBY", "PERL",
    "LUA", "SWIFT", "KOTLIN", "SCALA", "CLOJURE", "HASKELL", "ERLANG", "ELIXIR", "DART",
    "FLUTTER", "REACT", "VUE", "ANGULAR", "SVELTE", "NEXT", "NUXT", "DJANGO", "FLASK",
    "FASTAPI", "SPRING", "LARAVEL", "SYMFONY", "RAILS", "EXPRESS", "NEST", "ASPNET",
    "HK", "SS", "SZ", "KS", "SW", "PA",
}


class NLPParser:
    """中文自然语言解析器"""

    def __init__(self):
        self.name_mapping = CHINESE_NAME_TO_SYMBOL.copy()

    def parse_query(self, text: str) -> Dict[str, Any]:
        """
        解析用户输入的中文自然语言查询

        Args:
            text: 用户输入文本

        Returns:
            包含 intent 和提取实体的字典
        """
        text = text.strip()
        if not text:
            return {"intent": "unknown", "raw": text}

        # 1. 识别意图
        intent = self._detect_intent(text)

        # 2. 根据意图提取实体
        result: Dict[str, Any] = {"intent": intent, "raw": text}

        if intent == "analyze_single":
            symbol = self._extract_single_symbol(text)
            if symbol:
                result["symbol"] = symbol
            else:
                result["intent"] = "unknown"
                result["error"] = "未能识别股票代码"

        elif intent == "analyze_batch":
            symbols = self._extract_symbols(text)
            if symbols:
                result["symbols"] = symbols
            else:
                result["intent"] = "unknown"
                result["error"] = "未能识别股票代码列表"

        elif intent == "portfolio":
            holdings = self._extract_holdings(text)
            if holdings:
                result["holdings"] = holdings
            # 如果没有提取到持仓，但明确是portfolio意图，保留意图并返回空持仓

        elif intent == "market":
            # 市场概览无需额外实体
            pass

        elif intent == "backtest":
            symbol = self._extract_single_symbol(text)
            strategy = self._extract_strategy(text)
            initial_capital = self._extract_initial_capital(text)
            if symbol:
                result["symbol"] = symbol
                result["strategy"] = strategy
                result["initial_capital"] = initial_capital
            else:
                result["intent"] = "unknown"
                result["error"] = "未能识别回测股票代码"

        elif intent == "optimize":
            symbols = self._extract_symbols(text)
            target_return = self._extract_target_return(text)
            if symbols:
                result["symbols"] = symbols
                result["target_return"] = target_return
            # 如果没有提取到股票代码，但明确是optimize意图，保留意图

        return result

    # -----------------------------------------------------------------------
    # 意图识别
    # -----------------------------------------------------------------------

    def _detect_intent(self, text: str) -> str:
        """检测用户意图"""
        text_lower = text.lower()

        # 回测
        if re.search(r"回测|回檢|backtest|模拟交易|策略测试", text):
            return "backtest"

        # 组合优化
        if re.search(r"优化|優化|optimize|最优配置|资产配置|组合优化|馬科維茨|配置", text):
            return "optimize"

        # 投资组合
        if re.search(r"持仓|持倉|portfolio|我的组合|投资组合|仓位|倉位|持股|盈亏|收益如何", text):
            return "portfolio"

        # 市场概览
        if re.search(r"市场|市場|market|大盘|大盤|行情|指数|指數|overview", text):
            return "market"

        # 批量分析
        if re.search(r"批量|batch|多个|多支|多隻|一起分析|全部|所有股票", text) or self._has_multiple_symbols(text):
            return "analyze_batch"

        # 单股分析（默认）
        if re.search(r"分析|查看|评估|評估|analyz|evaluate|诊断|診斷|怎么样|怎麼樣|如何", text):
            return "analyze_single"

        # 如果包含股票代码但无明确动词，也视为单股分析
        if self._extract_single_symbol(text):
            return "analyze_single"

        return "unknown"

    # -----------------------------------------------------------------------
    # 实体提取
    # -----------------------------------------------------------------------

    def _extract_single_symbol(self, text: str) -> Optional[str]:
        """提取单个股票代码"""
        # 先尝试中文名称映射
        for name, symbol in sorted(self.name_mapping.items(), key=lambda x: -len(x[0])):
            if name in text:
                return symbol

        # 匹配常见股票代码格式（不使用\b，因其在中文文本中不工作）
        # A股: 600519.SS, 000001.SZ, 600519, 000001
        patterns = [
            r"([6]\d{5}\.SS)",
            r"([03]\d{5}\.SZ)",
            r"([68]\d{5}\.SS)",
            r"([6]\d{5})(?!\d)",
            r"([03]\d{5})(?!\d)",
            # 港股: 0700.HK, 9988.HK
            r"(\d{4}\.HK)",
            # 美股: AAPL, TSLA, BRK-B, 005930.KS
            # 要求前面是中文、空格、标点或开头，后面也是
            r"(?:^|[^A-Za-z0-9])([A-Z]{1,5}(?:-[A-Z])?)(?![A-Za-z0-9])",
            r"(\d{6}\.KS)",
            r"([A-Z]{2,5}\.[A-Z]{2})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                candidate = match.group(1) if match.lastindex == 1 else match.group(match.lastindex)
                if candidate in _NON_STOCK_WORDS:
                    continue
                return candidate

        return None

    def _extract_symbols(self, text: str) -> List[str]:
        """提取多个股票代码"""
        symbols = []

        # 先匹配中文名称
        for name, symbol in sorted(self.name_mapping.items(), key=lambda x: -len(x[0])):
            if name in text and symbol not in symbols:
                symbols.append(symbol)

        # 匹配代码格式（不使用\b）
        patterns = [
            r"([6]\d{5}\.SS)",
            r"([03]\d{5}\.SZ)",
            r"([68]\d{5}\.SS)",
            r"([6]\d{5})(?!\d)",
            r"([03]\d{5})(?!\d)",
            r"(\d{4}\.HK)",
            r"(?:^|[^A-Za-z0-9])([A-Z]{1,5}(?:-[A-Z])?)(?![A-Za-z0-9])",
            r"(\d{6}\.KS)",
            r"([A-Z]{2,5}\.[A-Z]{2})",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                candidate = match.group(1)
                if candidate in _NON_STOCK_WORDS:
                    continue
                if candidate not in symbols:
                    symbols.append(candidate)

        return symbols

    def _extract_holdings(self, text: str) -> List[Dict[str, Any]]:
        """从文本中提取持仓信息"""
        holdings = []

        # 模式1: "100股苹果成本150" / "100股AAPL成本150"
        # 注意：名称可能包含中文，用非贪婪匹配直到遇到数字或结尾
        pattern1 = re.compile(
            r"(\d+(?:\.\d+)?)\s*(?:股|股|shares?)\s*([^\d\s,，、;；]+)\s*(?:成本|cost|均价|平均成本)?\s*(\d+(?:\.\d+)?)?"
        )
        for match in pattern1.finditer(text):
            quantity = float(match.group(1))
            name_or_symbol = match.group(2).strip()
            cost_basis = float(match.group(3)) if match.group(3) else 0.0

            symbol = self._resolve_symbol(name_or_symbol)
            if symbol:
                holdings.append({
                    "symbol": symbol,
                    "quantity": quantity,
                    "cost_basis": cost_basis,
                })

        # 模式2: "持有100股AAPL" / "我有100股苹果"
        if not holdings:
            pattern2 = re.compile(
                r"(?:持有|有|持仓|持倉|买了|買了|购入|購入)?\s*(\d+(?:\.\d+)?)\s*(?:股|股|shares?)\s*([^\d\s,，、;；]+)"
            )
            for match in pattern2.finditer(text):
                quantity = float(match.group(1))
                name_or_symbol = match.group(2).strip()
                symbol = self._resolve_symbol(name_or_symbol)
                if symbol:
                    holdings.append({
                        "symbol": symbol,
                        "quantity": quantity,
                        "cost_basis": 0.0,
                    })

        # 模式3: 逗号/顿号分隔的多个持仓
        if not holdings:
            segments = re.split(r"[,，、;；]", text)
            for seg in segments:
                qty_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:股|股|shares?)", seg)
                symbol = self._extract_single_symbol(seg)
                if qty_match and symbol:
                    cost_match = re.search(r"(?:成本|cost|均价|平均成本|@|at)\s*(\d+(?:\.\d+)?)", seg)
                    holdings.append({
                        "symbol": symbol,
                        "quantity": float(qty_match.group(1)),
                        "cost_basis": float(cost_match.group(1)) if cost_match else 0.0,
                    })

        return holdings

    def _extract_strategy(self, text: str) -> str:
        """提取回测策略名称"""
        if re.search(r"买入持有|買入持有|buy.?hold|持有策略|长期持有|長期持有", text, re.IGNORECASE):
            return "buy_hold"
        if re.search(r"均线交叉|均線交叉|sma.?cross|moving.average|双均线|雙均線", text, re.IGNORECASE):
            return "sma_cross"
        if re.search(r"RSI|rsi|相对强弱|相對強弱", text):
            return "rsi"
        return "buy_hold"

    def _extract_initial_capital(self, text: str) -> float:
        """提取初始资金"""
        match = re.search(r"(?:本金|资金|資金|capital|初始资金|initial)\s*(?:为|為|是|:)?\s*(\d+(?:\.\d+)?)\s*(?:万|萬|w|万)?", text)
        if match:
            val = float(match.group(1))
            if "万" in text or "萬" in text or "w" in text.lower():
                val *= 10000
            return val
        return 100000.0

    def _extract_target_return(self, text: str) -> Optional[float]:
        """提取目标收益率"""
        # 匹配 "目标收益10%" / "target return 10%" / "10%收益"
        match = re.search(r"(?:目标|target|期望|预期)?\s*(?:收益|return|收益率|回报率|報酬率)\s*(?:为|為|是|:)?\s*(\d+(?:\.\d+)?)\s*%", text)
        if match:
            return float(match.group(1)) / 100.0
        # 匹配 "10%" 在优化语境中
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        if match:
            return float(match.group(1)) / 100.0
        return None

    def _has_multiple_symbols(self, text: str) -> bool:
        """判断文本中是否包含多个股票代码"""
        symbols = self._extract_symbols(text)
        return len(symbols) >= 2

    def _resolve_symbol(self, name_or_symbol: str) -> Optional[str]:
        """将名称或代码解析为标准股票代码"""
        if name_or_symbol in self.name_mapping:
            return self.name_mapping[name_or_symbol]
        # 如果本身就是代码格式
        if re.match(r"^[A-Z0-9\-]+(\.[A-Z]{2})?$", name_or_symbol):
            if name_or_symbol not in _NON_STOCK_WORDS:
                return name_or_symbol
        # 尝试部分匹配
        for name, symbol in self.name_mapping.items():
            if name in name_or_symbol or name_or_symbol in name:
                return symbol
        return None

    def add_name_mapping(self, name: str, symbol: str) -> None:
        """添加自定义名称映射"""
        self.name_mapping[name] = symbol

    def remove_name_mapping(self, name: str) -> None:
        """移除名称映射"""
        if name in self.name_mapping:
            del self.name_mapping[name]
