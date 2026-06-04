"""
AutoWealth AI FastAPI Web 服务
提供股票分析、投资组合分析、回测、组合优化等 RESTful API
"""
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from autowealth.core.backtest import BacktestEngine
from autowealth.core.engine import AutoWealthEngine
from autowealth.core.portfolio_optimizer import PortfolioOptimizer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic 请求/响应模型
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    symbol: str = Field(..., description="股票代码，如 AAPL, 600519.SS")
    include_technical: bool = Field(True, description="是否包含技术分析")
    include_fundamental: bool = Field(True, description="是否包含基本面分析")
    include_sentiment: bool = Field(True, description="是否包含情绪分析")


class AnalyzeResponse(BaseModel):
    symbol: str
    success: bool
    error: Optional[str] = None
    decision: Optional[Dict[str, Any]] = None
    individual_signals: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    technical_analysis: Optional[Dict[str, Any]] = None
    fundamental_analysis: Optional[Dict[str, Any]] = None
    stock_info: Optional[Dict[str, Any]] = None


class BatchAnalyzeRequest(BaseModel):
    symbols: List[str] = Field(..., description="股票代码列表")


class BatchAnalyzeResponse(BaseModel):
    results: Dict[str, Any]
    recommendations: Dict[str, List]
    summary: Dict[str, Any]


class Holding(BaseModel):
    symbol: str = Field(..., description="股票代码")
    quantity: float = Field(..., description="持仓数量")
    cost_basis: float = Field(0.0, description="成本价")


class PortfolioAnalyzeRequest(BaseModel):
    holdings: List[Holding] = Field(..., description="持仓列表")


class PortfolioAnalyzeResponse(BaseModel):
    holdings: List[Dict[str, Any]]
    total_value: float
    total_gain_loss: float
    return_pct: float


class MarketOverviewResponse(BaseModel):
    success: bool
    indices: Dict[str, Any]
    error: Optional[str] = None


class BacktestRequest(BaseModel):
    symbol: str = Field(..., description="股票代码")
    strategy: str = Field(..., description="策略名称，如 buy_hold, sma_cross")
    initial_capital: float = Field(100000.0, description="初始资金")


class BacktestResponse(BaseModel):
    symbol: str
    strategy: str
    metrics: Dict[str, Any]
    trade_count: int
    trades: List[Dict[str, Any]]
    equity_curve: List[float]


class OptimizeRequest(BaseModel):
    symbols: List[str] = Field(..., description="股票代码列表")
    target_return: Optional[float] = Field(None, description="目标年化收益率")


class OptimizeResponse(BaseModel):
    weights: Dict[str, float]
    expected_return: float
    volatility: float
    sharpe_ratio: float


# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

_engine: Optional[AutoWealthEngine] = None


def get_engine() -> AutoWealthEngine:
    """获取全局 AutoWealthEngine 实例（单例）"""
    global _engine
    if _engine is None:
        _engine = AutoWealthEngine()
    return _engine


# ---------------------------------------------------------------------------
# 生命周期管理
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期事件"""
    logger.info("AutoWealth API 服务启动")
    # 预热引擎
    get_engine()
    yield
    logger.info("AutoWealth API 服务关闭")


# ---------------------------------------------------------------------------
# 创建 FastAPI 应用
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用"""
    app = FastAPI(
        title="AutoWealth AI API",
        description="智能投资分析 Web API 服务",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -----------------------------------------------------------------------
    # 路由
    # -----------------------------------------------------------------------

    @app.get("/health", response_model=Dict[str, str])
    async def health_check():
        """健康检查端点"""
        return {"status": "ok", "service": "autowealth-ai"}

    @app.post("/analyze", response_model=AnalyzeResponse)
    async def analyze_stock(
        request: AnalyzeRequest,
        engine: AutoWealthEngine = Depends(get_engine),
    ):
        """分析单只股票"""
        try:
            result = engine.analyze(
                symbol=request.symbol,
                include_technical=request.include_technical,
                include_fundamental=request.include_fundamental,
                include_sentiment=request.include_sentiment,
            )
            return AnalyzeResponse(**result)
        except Exception as e:
            logger.error(f"分析 {request.symbol} 失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/analyze/batch", response_model=BatchAnalyzeResponse)
    async def analyze_batch(
        request: BatchAnalyzeRequest,
        engine: AutoWealthEngine = Depends(get_engine),
    ):
        """批量分析多只股票"""
        try:
            result = engine.analyze_batch(request.symbols)
            return BatchAnalyzeResponse(**result)
        except Exception as e:
            logger.error(f"批量分析失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/portfolio/analyze", response_model=PortfolioAnalyzeResponse)
    async def analyze_portfolio(
        request: PortfolioAnalyzeRequest,
        engine: AutoWealthEngine = Depends(get_engine),
    ):
        """投资组合分析"""
        try:
            holdings = [h.model_dump() for h in request.holdings]
            result = engine.get_portfolio_analysis(holdings)
            return PortfolioAnalyzeResponse(**result)
        except Exception as e:
            logger.error(f"投资组合分析失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/market/overview", response_model=MarketOverviewResponse)
    async def market_overview(
        engine: AutoWealthEngine = Depends(get_engine),
    ):
        """获取市场概览"""
        try:
            result = engine.get_market_overview()
            return MarketOverviewResponse(**result)
        except Exception as e:
            logger.error(f"获取市场概览失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/backtest", response_model=BacktestResponse)
    async def backtest(
        request: BacktestRequest,
        engine: AutoWealthEngine = Depends(get_engine),
    ):
        """执行回测"""
        try:
            data = engine.data_fetcher.get_stock_data(request.symbol, period="1y")
            if data.empty:
                raise ValueError(f"无法获取 {request.symbol} 的数据")

            signals = _generate_signals(data, request.strategy)

            bt = BacktestEngine(initial_capital=request.initial_capital)
            bt.run_strategy(data, signals)
            metrics = bt.get_performance_metrics()

            return BacktestResponse(
                symbol=request.symbol,
                strategy=request.strategy,
                metrics=metrics,
                trade_count=metrics.get("trade_count", 0),
                trades=bt.get_trade_history(),
                equity_curve=bt.equity_curve,
            )
        except Exception as e:
            logger.error(f"回测失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/optimize", response_model=OptimizeResponse)
    async def optimize_portfolio(
        request: OptimizeRequest,
        engine: AutoWealthEngine = Depends(get_engine),
    ):
        """投资组合优化"""
        try:
            # 获取各股票历史数据
            data_dict = engine.data_fetcher.get_multiple_stocks(request.symbols, period="1y")
            if not data_dict:
                raise ValueError("无法获取任何股票数据")

            # 构建收益率矩阵
            returns_df = pd.DataFrame()
            for symbol, df in data_dict.items():
                if not df.empty and "Close" in df.columns:
                    returns_df[symbol] = df["Close"].pct_change()

            returns_df = returns_df.dropna()

            if returns_df.empty or len(returns_df.columns) < 2:
                raise ValueError("有效股票数据不足，无法进行优化")

            optimizer = PortfolioOptimizer(returns_df)

            if request.target_return is not None:
                result = optimizer.mean_variance_optimization(target_return=request.target_return)
            else:
                result = optimizer.max_sharpe_ratio()

            return OptimizeResponse(
                weights=result["weights"],
                expected_return=result["expected_return"],
                volatility=result["volatility"],
                sharpe_ratio=result["sharpe_ratio"],
            )
        except Exception as e:
            logger.error(f"组合优化失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return app


# ---------------------------------------------------------------------------
# 策略信号生成
# ---------------------------------------------------------------------------

def _generate_signals(data: pd.DataFrame, strategy: str) -> List[str]:
    """根据策略名称生成交易信号列表"""
    prices = data["Close"].values
    n = len(prices)
    signals = ["hold"] * n

    if strategy == "buy_hold":
        signals[0] = "buy"
        signals[-1] = "sell"

    elif strategy == "sma_cross":
        if n < 60:
            return signals
        sma20 = pd.Series(prices).rolling(window=20).mean().values
        sma60 = pd.Series(prices).rolling(window=60).mean().values
        in_position = False
        for i in range(60, n):
            if sma20[i] > sma60[i] and not in_position:
                signals[i] = "buy"
                in_position = True
            elif sma20[i] < sma60[i] and in_position:
                signals[i] = "sell"
                in_position = False
        if in_position:
            signals[-1] = "sell"

    elif strategy == "rsi":
        if n < 14:
            return signals
        delta = pd.Series(prices).diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean().values
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean().values
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        in_position = False
        for i in range(14, n):
            if rsi[i] < 30 and not in_position:
                signals[i] = "buy"
                in_position = True
            elif rsi[i] > 70 and in_position:
                signals[i] = "sell"
                in_position = False
        if in_position:
            signals[-1] = "sell"

    else:
        # 默认 buy_hold
        signals[0] = "buy"
        signals[-1] = "sell"

    return signals
