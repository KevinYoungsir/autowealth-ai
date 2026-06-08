"""
数据获取模块 - 负责从各种数据源获取金融数据
"""
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from autowealth.config.settings import get_settings

logger = logging.getLogger(__name__)


class EastMoneyDataSource:
    """东方财富数据源（A股数据）"""

    def __init__(self):
        try:
            import akshare as ak
            self.ak = ak
        except ImportError:
            raise ImportError("使用 EastMoneyDataSource 需要安装 akshare: pip install akshare")

    def get_stock_data(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        获取A股股票数据

        Args:
            symbol: A股代码 (如: 600519, 000001)
            period: 时间周期 (1y, 2y, 5y, 10y, ytd, max)
            interval: 时间间隔 (1d, 1wk, 1mo)

        Returns:
            DataFrame包含OHLCV数据
        """
        try:
            logger.info(f"从东方财富获取A股数据: {symbol}")

            # 去除可能的后缀
            clean_symbol = symbol.replace(".SS", "").replace(".SZ", "").replace(".BJ", "")

            # 判断市场并添加前缀
            if clean_symbol.startswith("6"):
                stock_code = f"sh{clean_symbol}"
            elif clean_symbol.startswith("0") or clean_symbol.startswith("3"):
                stock_code = f"sz{clean_symbol}"
            elif clean_symbol.startswith("8") or clean_symbol.startswith("4"):
                stock_code = f"bj{clean_symbol}"
            else:
                stock_code = clean_symbol

            # 使用akshare获取历史数据
            df = self.ak.stock_zh_a_hist(
                symbol=clean_symbol,
                period="daily",
                start_date=(datetime.now() - self._parse_period(period)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq"  # 前复权
            )

            if df.empty:
                raise ValueError(f"无法获取 {symbol} 的数据")

            # 标准化列名以匹配 yfinance 格式
            df = df.rename(columns={
                "日期": "Date",
                "开盘": "Open",
                "收盘": "Close",
                "最高": "High",
                "最低": "Low",
                "成交量": "Volume",
            })
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date")

            # 保留标准OHLCV列
            std_cols = ["Open", "High", "Low", "Close", "Volume"]
            available_cols = [c for c in std_cols if c in df.columns]
            df = df[available_cols]

            return df

        except Exception as e:
            logger.error(f"从东方财富获取 {symbol} 数据失败: {e}")
            raise

    def get_stock_info(self, symbol: str) -> Dict:
        """
        获取A股基本信息

        Args:
            symbol: A股代码

        Returns:
            股票信息字典
        """
        try:
            clean_symbol = symbol.replace(".SS", "").replace(".SZ", "").replace(".BJ", "")

            # 获取个股信息
            stock_info = self.ak.stock_individual_info_em(symbol=clean_symbol)

            if stock_info.empty:
                return {"symbol": symbol, "error": "未找到股票信息"}

            # 转换为字典
            info_dict = dict(zip(stock_info["item"], stock_info["value"]))

            return {
                "symbol": symbol,
                "name": info_dict.get("股票简称", "N/A"),
                "sector": info_dict.get("所属行业", "N/A"),
                "industry": info_dict.get("所属行业", "N/A"),
                "market_cap": info_dict.get("总市值", 0),
                "pe_ratio": info_dict.get("市盈率", 0),
                "pb_ratio": info_dict.get("市净率", 0),
                "dividend_yield": 0,  # akshare 此接口不直接提供
                "fifty_two_week_high": info_dict.get("52周最高价", 0),
                "fifty_two_week_low": info_dict.get("52周最低价", 0),
                "average_volume": 0,
                "website": "N/A",
                "description": info_dict.get("公司简介", "N/A"),
            }

        except Exception as e:
            logger.error(f"获取 {symbol} 信息失败: {e}")
            return {"symbol": symbol, "error": str(e)}

    @staticmethod
    def _parse_period(period: str) -> timedelta:
        """解析周期字符串为timedelta"""
        mapping = {
            "1d": timedelta(days=1),
            "5d": timedelta(days=5),
            "1mo": timedelta(days=30),
            "3mo": timedelta(days=90),
            "6mo": timedelta(days=180),
            "1y": timedelta(days=365),
            "2y": timedelta(days=730),
            "5y": timedelta(days=1825),
            "10y": timedelta(days=3650),
            "ytd": timedelta(days=datetime.now().timetuple().tm_yday),
            "max": timedelta(days=3650),
        }
        return mapping.get(period, timedelta(days=365))


class BinanceDataSource:
    """币安加密货币数据源"""

    def __init__(self):
        try:
            import requests
            self.requests = requests
        except ImportError:
            raise ImportError("使用 BinanceDataSource 需要安装 requests: pip install requests")
        self.base_url = "https://api.binance.com"

    def get_crypto_data(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        """
        获取加密货币K线数据

        Args:
            symbol: 交易对 (如: BTCUSDT, ETHUSDT)
            interval: K线间隔 (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M)
            limit: 返回条数，最大1000

        Returns:
            DataFrame包含OHLCV数据
        """
        try:
            logger.info(f"从币安获取加密货币数据: {symbol}")

            # 转换interval格式
            interval_map = {
                "1m": "1m", "2m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
                "60m": "1h", "90m": "1h", "1h": "1h", "1d": "1d", "5d": "1w",
                "1wk": "1w", "1mo": "1M", "3mo": "3M"
            }
            binance_interval = interval_map.get(interval, interval)

            url = f"{self.base_url}/api/v3/klines"
            params = {
                "symbol": symbol.upper(),
                "interval": binance_interval,
                "limit": limit,
            }

            response = self.requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if not data:
                raise ValueError(f"无法获取 {symbol} 的数据")

            df = pd.DataFrame(data, columns=[
                "Open time", "Open", "High", "Low", "Close", "Volume",
                "Close time", "Quote asset volume", "Number of trades",
                "Taker buy base asset volume", "Taker buy quote asset volume", "Ignore"
            ])

            df["Date"] = pd.to_datetime(df["Open time"], unit="ms")
            df = df.set_index("Date")

            # 转换数值类型
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df[["Open", "High", "Low", "Close", "Volume"]]
            return df

        except Exception as e:
            logger.error(f"从币安获取 {symbol} 数据失败: {e}")
            raise

    def get_crypto_info(self, symbol: str) -> Dict:
        """
        获取加密货币信息

        Args:
            symbol: 交易对 (如: BTCUSDT)

        Returns:
            加密货币信息字典
        """
        try:
            url = f"{self.base_url}/api/v3/ticker/24hr"
            params = {"symbol": symbol.upper()}

            response = self.requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            return {
                "symbol": symbol,
                "name": symbol,
                "sector": "Cryptocurrency",
                "industry": "Cryptocurrency",
                "market_cap": 0,
                "pe_ratio": 0,
                "pb_ratio": 0,
                "dividend_yield": 0,
                "fifty_two_week_high": float(data.get("highPrice", 0)),
                "fifty_two_week_low": float(data.get("lowPrice", 0)),
                "average_volume": float(data.get("volume", 0)),
                "website": "https://www.binance.com",
                "description": f"{symbol} 加密货币交易对",
                "last_price": float(data.get("lastPrice", 0)),
                "price_change_percent": float(data.get("priceChangePercent", 0)),
                "weighted_avg_price": float(data.get("weightedAvgPrice", 0)),
            }

        except Exception as e:
            logger.error(f"获取 {symbol} 信息失败: {e}")
            return {"symbol": symbol, "error": str(e)}


class DataFetcher:
    """金融数据获取器 - 支持多数据源"""

    def __init__(self, source: str = "auto", twelve_data_api_key: Optional[str] = None):
        """
        初始化数据获取器

        Args:
            source: 数据源 ('auto', 'twelve_data', 'yfinance', 'eastmoney', 'binance')
            twelve_data_api_key: Twelve Data API Key (免费获取: https://twelvedata.com/pricing)
        """
        self.settings = get_settings()
        self.cache_dir = Path(self.settings.data_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.source = source.lower()
        self.twelve_data_api_key = twelve_data_api_key

        # 初始化对应的数据源
        self._eastmoney = None
        self._binance = None
        self._twelve_data = None

    def _get_twelve_data(self):
        if self._twelve_data is None:
            from autowealth.core.twelve_data_source import TwelveDataSource
            self._twelve_data = TwelveDataSource(api_key=self.twelve_data_api_key)
        return self._twelve_data

    def _get_eastmoney(self) -> EastMoneyDataSource:
        if self._eastmoney is None:
            self._eastmoney = EastMoneyDataSource()
        return self._eastmoney

    def _get_binance(self) -> BinanceDataSource:
        if self._binance is None:
            self._binance = BinanceDataSource()
        return self._binance

    def _fetch_with_retry(self, func, max_retries=3, base_delay=2):
        """带重试的数据获取

        Args:
            func: 无参数的可调用对象，执行实际数据获取
            max_retries: 最大重试次数
            base_delay: 基础延迟秒数，每次重试递增

        Returns:
            func() 的返回值

        Raises:
            最后一次尝试的异常
        """
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                error_msg = str(e)
                if "Too Many Requests" in error_msg or "Rate limited" in error_msg or "429" in error_msg:
                    if attempt < max_retries - 1:
                        delay = base_delay * (attempt + 1)
                        logger.warning(f"请求被限流，{delay}秒后重试 (第{attempt + 1}/{max_retries}次)")
                        time.sleep(delay)
                        continue
                raise

    @staticmethod
    def is_a_share(symbol: str) -> bool:
        """
        判断是否为A股代码
        Args:
            symbol: 股票代码
        Returns:
            是否为A股（6位数字，上海/深圳/北京）
        """
        if not symbol or not isinstance(symbol, str):
            return False
        clean = symbol.replace(".SS", "").replace(".SZ", "").replace(".BJ", "")
        return (
            len(clean) == 6
            and clean.isdigit()
            and (clean.startswith("6") or clean.startswith("0") or clean.startswith("3"))
        )

    @staticmethod
    def is_a_share(symbol: str) -> bool:
        """判断是否为A股代码（6位数字）"""
        if not symbol or not isinstance(symbol, str):
            return False
        clean = symbol.replace(".SS", "").replace(".SZ", "").replace(".BJ", "")
        return len(clean) == 6 and clean.isdigit() and (clean.startswith("6") or clean.startswith("0") or clean.startswith("3"))

    @staticmethod
    def is_crypto_symbol(symbol: str) -> bool:
        """
        判断是否为加密货币symbol

        Args:
            symbol: 代码字符串

        Returns:
            是否为加密货币格式（如 BTCUSDT, ETHUSDT）
        """
        if not symbol or not isinstance(symbol, str):
            return False
        symbol_upper = symbol.upper()
        # 常见加密货币交易对特征：以USDT、BUSD、BTC、ETH结尾，且长度>=6
        crypto_suffixes = ("USDT", "BUSD", "BTC", "ETH", "USDC")
        return (
            symbol_upper.endswith(crypto_suffixes)
            and len(symbol) >= 6
            and "." not in symbol  # 排除股票格式如 AAPL, 600519.SS
        )

    def get_stock_data(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        获取股票数据

        Args:
            symbol: 股票代码 (如: AAPL, 600519.SS, BTCUSDT)
            period: 时间周期
            interval: 时间间隔
            use_cache: 是否使用缓存

        Returns:
            DataFrame包含OHLCV数据
        """
        # 如果是加密货币，自动路由到币安
        if self.is_crypto_symbol(symbol):
            return self.get_crypto_data(symbol, interval=interval)
        # A股自动路由到东方财富获取真实数据
        if self.is_a_share(symbol):
            try:
                logger.info(f"A股 {symbol} 路由到东方财富")
                return self._get_eastmoney().get_stock_data(symbol, period=period, interval=interval)
            except Exception as e:
                logger.warning(f"东方财富失败: {e}，回退")
        # 根据source选择数据源
        if self.source == "eastmoney":
            return self._get_eastmoney().get_stock_data(symbol, period=period, interval=interval)

        if self.source == "twelve_data":
            return self._get_twelve_data().get_stock_data(symbol, period=period, interval=interval)

        # auto模式: 优先尝试真实数据源，失败后用模拟数据
        if self.source in ("auto", "yfinance"):
            # 1. 优先尝试 Twelve Data (真实数据)
            try:
                logger.info(f"尝试从Twelve Data获取真实数据: {symbol}")
                return self._get_twelve_data().get_stock_data(symbol, period=period, interval=interval)
            except Exception as td_err:
                logger.warning(f"Twelve Data失败: {td_err}")

            # 2. 尝试 yfinance
            cache_file = self.cache_dir / f"{symbol}_{period}_{interval}.csv"
            if use_cache and cache_file.exists():
                cache_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
                if datetime.now() - cache_time < timedelta(hours=1):
                    logger.info(f"使用缓存数据: {symbol}")
                    return pd.read_csv(cache_file, index_col=0, parse_dates=True)

            try:
                logger.info(f"尝试从Yahoo Finance获取数据: {symbol}")

                def _do_fetch():
                    ticker = yf.Ticker(symbol)
                    return ticker.history(period=period, interval=interval)

                data = self._fetch_with_retry(_do_fetch)

                if data.empty:
                    raise ValueError(f"无法获取 {symbol} 的数据")

                if use_cache:
                    data.to_csv(cache_file)

                return data

            except Exception as yf_err:
                error_msg = str(yf_err)
                # 3. 限流时用模拟数据
                if "Too Many Requests" in error_msg or "Rate limited" in error_msg or "429" in error_msg:
                    logger.warning(f"所有真实数据源限流，使用模拟数据: {symbol}")
                else:
                    logger.warning(f"Yahoo Finance失败: {yf_err}，使用模拟数据")

                try:
                    from autowealth.core.demo_data import DemoDataGenerator
                    generator = DemoDataGenerator()
                    data = generator.generate_stock_data(symbol, days=365)
                    if not data.empty:
                        return data
                except ImportError:
                    pass

                logger.error(f"获取 {symbol} 数据失败: {yf_err}")
                raise

        raise ValueError(f"未知数据源: {self.source}")

    def get_crypto_data(self, symbol: str, interval: str = "1d") -> pd.DataFrame:
        """
        获取加密货币数据

        Args:
            symbol: 交易对 (如: BTCUSDT, ETHUSDT)
            interval: K线间隔

        Returns:
            DataFrame包含OHLCV数据
        """
        return self._get_binance().get_crypto_data(symbol, interval=interval)

    def get_multiple_stocks(
        self,
        symbols: List[str],
        period: str = "1y",
        interval: str = "1d",
    ) -> Dict[str, pd.DataFrame]:
        """
        批量获取多只股票数据

        Args:
            symbols: 股票代码列表
            period: 时间周期
            interval: 时间间隔

        Returns:
            字典，key为股票代码，value为DataFrame
        """
        results = {}
        for i, symbol in enumerate(symbols):
            try:
                data = self.get_stock_data(symbol, period, interval)
                results[symbol] = data
            except Exception as e:
                logger.warning(f"跳过 {symbol}: {e}")
                continue
            # 每次请求之间等待2秒，避免触发Rate Limit
            if i < len(symbols) - 1:
                time.sleep(2)

        return results

    def get_market_indices(self, region: str = "global") -> Dict[str, pd.DataFrame]:
        """
        获取主要市场指数数据

        Args:
            region: 地区 (global, us, cn, eu)

        Returns:
            指数数据字典
        """
        indices_map = {
            "global": ["^GSPC", "^DJI", "^IXIC", "^FTSE", "^N225", "000001.SS", "^HSI"],
            "us": ["^GSPC", "^DJI", "^IXIC", "^RUT"],
            "cn": ["000001.SS", "399001.SZ", "000300.SS", "000688.SH"],
            "eu": ["^FTSE", "^GDAXI", "^FCHI", "^STOXX50E"],
        }

        symbols = indices_map.get(region, indices_map["global"])

        # 市场指数请求使用独立逻辑，每次请求之间等待3秒
        results = {}
        for i, symbol in enumerate(symbols):
            try:
                data = self.get_stock_data(symbol, period="6mo")
                results[symbol] = data
            except Exception as e:
                logger.warning(f"跳过指数 {symbol}: {e}")
                continue
            # 每次请求之间等待3秒，避免触发Rate Limit
            if i < len(symbols) - 1:
                time.sleep(3)

        return results

    def get_stock_info(self, symbol: str) -> Dict:
        """
        获取股票基本信息

        Args:
            symbol: 股票代码

        Returns:
            股票信息字典
        """
        # 如果是加密货币，使用币安接口
        if self.is_crypto_symbol(symbol):
            return self._get_binance().get_crypto_info(symbol)
        # A股自动路由到东方财富获取真实公司信息
        if self.is_a_share(symbol):
            try:
                logger.info(f"A股 {symbol} 路由到东方财富获取公司信息")
                return self._get_eastmoney().get_stock_info(symbol)
            except Exception as e:
                logger.warning(f"东方财富获取信息失败: {e}")
        # 根据source选择数据源
        if self.source == "eastmoney":
            return self._get_eastmoney().get_stock_info(symbol)

        if self.source == "twelve_data":
            return self._get_twelve_data().get_stock_info(symbol)

        # auto模式: 优先Twelve Data, 失败后用yfinance
        if self.source in ("auto", "yfinance"):
            # 1. 尝试 Twelve Data
            try:
                return self._get_twelve_data().get_stock_info(symbol)
            except Exception as td_err:
                logger.warning(f"Twelve Data info失败: {td_err}")

            # 2. 尝试 yfinance
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info

                return {
                    "symbol": symbol,
                    "name": info.get("longName", "N/A"),
                    "sector": info.get("sector", "N/A"),
                    "industry": info.get("industry", "N/A"),
                    "market_cap": info.get("marketCap", 0),
                    "pe_ratio": info.get("trailingPE", 0),
                    "pb_ratio": info.get("priceToBook", 0),
                    "dividend_yield": info.get("dividendYield", 0),
                    "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0),
                    "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0),
                    "average_volume": info.get("averageVolume", 0),
                    "website": info.get("website", "N/A"),
                    "description": info.get("longBusinessSummary", "N/A"),
                }

            except Exception as e:
                logger.error(f"获取 {symbol} 信息失败: {e}")
                return {"symbol": symbol, "error": str(e)}

        return {"symbol": symbol, "name": symbol}

    def clear_cache(self):
        """清除所有缓存数据"""
        import shutil

        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("缓存已清除")
