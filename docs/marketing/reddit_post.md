# AutoWealth AI - Open-Source Multi-Agent Investment Analysis Engine

**Subreddits:** r/Python, r/algotrading, r/opensource

---

## Title (r/Python)
**I built an open-source multi-agent AI engine that analyzes stocks from 3 different perspectives**

## Title (r/algotrading)
**Open-source multi-agent system for investment analysis - technical, fundamental & sentiment agents working together**

## Title (r/opensource)
**AutoWealth AI: A multi-agent investment analysis engine built with Python**

---

## Post Body

Hi everyone,

I'd like to share a project I've been working on: **AutoWealth AI** -- an open-source, multi-agent investment analysis engine built entirely in Python.

### The Core Idea

Instead of relying on a single model or strategy, AutoWealth AI uses three specialized AI agents that analyze stocks from different perspectives, then combines their signals through a weighted voting mechanism:

- **Technical Analyst Agent (35% weight)** -- Analyzes price action using 12+ technical indicators: MACD, RSI, Bollinger Bands, KDJ, OBV, ATR, DMI (+DI/-DI/ADX), CCI, Williams %R, PSY, and moving average systems.

- **Fundamental Analyst Agent (35% weight)** -- Evaluates valuation metrics including P/E ratio, P/B ratio, dividend yield, and growth trends.

- **Sentiment Analyst Agent (30% weight)** -- Assesses market sentiment through price momentum, volume trends, and volatility patterns.

The **Agent Coordinator** collects signals from all three agents, applies confidence-weighted scoring, and produces a final buy/sell/hold decision with an overall confidence percentage.

### Key Features

**Machine Learning Predictions**
- Random Forest and MLP neural network models
- 18-dimensional feature engineering (MA, RSI, MACD, Bollinger position, volatility, momentum, etc.)
- Model persistence with pickle serialization
- Full evaluation metrics (MSE, MAE, R-squared)

**Multi-Source Data**
- Yahoo Finance -- global stocks, ETFs, indices
- East Money (akshare) -- Chinese A-share real-time data
- Binance -- cryptocurrency trading pairs
- Automatic source routing based on ticker format

**Backtesting System**
- Three built-in strategies: buy-and-hold, SMA crossover, RSI
- Performance metrics: total return, annualized return, max drawdown, Sharpe ratio, win rate
- Full equity curve and trade history

**Portfolio Optimization**
- Markowitz mean-variance optimization
- Maximum Sharpe ratio portfolio
- Minimum variance portfolio
- Implemented with pure numpy (no cvxpy dependency)

**Social Sentiment Analysis**
- Multi-platform coverage: Twitter/X, Weibo, Reddit
- 360+ financial sentiment words (Chinese and English)
- Weighted cross-platform sentiment scoring

**Real-Time Alert System**
- 5 alert rules: price breakout, price change threshold, volume anomaly, indicator crossover, custom threshold
- Notification channels: console, Webhook (DingTalk/Feishu/Slack)

**Chinese NLP Interface**
- Intent recognition via regex (zero external NLP dependencies)
- 80+ Chinese stock name to ticker mappings
- Supports natural expressions like "analyze Maotai" or "compare Apple and Microsoft"

**Web API & Mobile**
- FastAPI with 7 RESTful endpoints, Pydantic models, auto-generated OpenAPI docs
- Flutter mobile app (iOS + Android) with dark tech theme
- Streamlit visualization dashboard

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.9+ |
| Data | pandas, numpy, yfinance, akshare |
| ML | scikit-learn (RandomForest, MLP) |
| API | FastAPI, Pydantic, uvicorn |
| Mobile | Flutter (Dart) |
| UI | Streamlit |
| Testing | pytest (482 tests) |
| CI/CD | GitHub Actions |
| Container | Docker, docker-compose |

### Quick Start

```python
from autowealth import AutoWealthEngine

engine = AutoWealthEngine()

# Analyze a single stock
result = engine.analyze("AAPL")
print(result['decision']['signal_type'])   # buy / sell / hold
print(result['decision']['confidence'])   # confidence %

# Batch analysis
batch = engine.analyze_batch(["AAPL", "GOOGL", "MSFT", "AMZN"])
print(batch['recommendations']['buy'])
```

Command line:
```bash
python -m autowealth --symbol AAPL
python -m autowealth --batch AAPL GOOGL MSFT
```

Web API:
```bash
uvicorn autowealth.api.server:create_app --factory --reload
```

### Project Stats

- 482 test cases, all passing
- MIT license
- Docker support for one-click deployment
- Active development with clear roadmap

### What I'd Love Feedback On

- Additional technical indicators you'd find useful
- More data sources to integrate
- Strategy ideas for the backtesting engine
- Architecture improvements for the agent system

GitHub: https://github.com/Jsoned/autowealth-ai

---

**Disclaimer:** This project is for educational and research purposes only. It does not constitute investment advice. Always do your own research before making investment decisions.
