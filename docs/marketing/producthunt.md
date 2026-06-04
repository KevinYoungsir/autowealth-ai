# Product Hunt Launch Page

## Tagline

**An open-source multi-agent AI engine that analyzes stocks from technical, fundamental, and sentiment perspectives.**

---

## Description

### Overview

AutoWealth AI is an open-source investment analysis engine that uses multiple AI agents to analyze stocks from different angles and produce consolidated buy/sell/hold decisions.

Instead of relying on a single model or strategy, it simulates a professional investment research team where three specialized agents -- a technical analyst, a fundamental analyst, and a sentiment analyst -- independently evaluate a stock and then vote on the final recommendation through a confidence-weighted mechanism.

### How It Works

**Three Specialized AI Agents:**

1. **Technical Analyst (35% weight)** -- Analyzes price action using 12+ technical indicators including MACD, RSI, Bollinger Bands, KDJ, OBV, ATR, DMI (+DI/-DI/ADX), CCI, Williams %R, PSY, and multiple moving average systems.

2. **Fundamental Analyst (35% weight)** -- Evaluates company valuation through P/E ratio, P/B ratio, dividend yield, and growth trend analysis.

3. **Sentiment Analyst (30% weight)** -- Assesses market conditions through price momentum, volume trends, and volatility patterns.

**Weighted Voting:** Each agent produces a signal (buy/sell/hold) with a confidence score. The coordinator multiplies confidence by weight, normalizes across all agents, and selects the highest-scoring signal as the final decision.

### Key Features

- **Machine Learning Predictions** -- Random Forest and MLP neural network models with 18-dimensional feature engineering. Full evaluation metrics (MSE, MAE, R-squared).

- **Multi-Source Data** -- Yahoo Finance (global stocks/ETFs), East Money/akshare (Chinese A-shares), Binance (cryptocurrency). Automatic source routing based on ticker format.

- **Backtesting Engine** -- Three built-in strategies (buy-and-hold, SMA crossover, RSI) with complete performance metrics: annualized return, max drawdown, Sharpe ratio, win rate, equity curve.

- **Portfolio Optimization** -- Markowitz mean-variance model supporting maximum Sharpe ratio, minimum variance, and target return optimization. Pure numpy implementation.

- **Social Sentiment Analysis** -- Multi-platform coverage (Twitter/X, Weibo, Reddit) with 360+ financial sentiment words and weighted cross-platform scoring.

- **Real-Time Alerts** -- Five alert rules (price breakout, price change threshold, volume anomaly, indicator crossover, custom threshold) with Webhook notifications (DingTalk, Feishu, Slack).

- **Chinese NLP Interface** -- Regex-based intent recognition with 80+ stock name mappings. Zero external NLP dependencies.

- **Web API** -- FastAPI with 7 RESTful endpoints, Pydantic models, auto-generated OpenAPI documentation.

- **Mobile App** -- Flutter cross-platform app (iOS + Android) with dark tech theme.

- **Visualization** -- Streamlit interactive dashboard.

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.9+ |
| Data Processing | pandas, numpy |
| Data Sources | yfinance, akshare, python-binance |
| Machine Learning | scikit-learn |
| Web Framework | FastAPI, Pydantic, uvicorn |
| Mobile | Flutter (Dart) |
| Dashboard | Streamlit |
| Testing | pytest (482 tests) |
| CI/CD | GitHub Actions |
| Containerization | Docker, docker-compose |

### Quick Start

```bash
git clone https://github.com/Jsoned/autowealth-ai.git
cd autowealth-ai
pip install -e .

# Analyze a stock
python -m autowealth --symbol AAPL

# Batch analysis
python -m autowealth --batch AAPL GOOGL MSFT

# Start web API
uvicorn autowealth.api.server:create_app --factory --reload
```

```python
from autowealth import AutoWealthEngine

engine = AutoWealthEngine()
result = engine.analyze("AAPL")
print(result['decision']['signal_type'])  # buy / sell / hold
```

### Why Open Source

- Transparency -- Every analysis decision can be traced back to individual agent signals
- Privacy -- Run locally, your data never leaves your machine
- Customization -- Modify agent weights, add indicators, integrate new data sources
- Education -- Clean, well-documented codebase for learning quantitative finance and multi-agent systems

### Project Stats

- 482 test cases, all passing
- MIT license
- Docker support
- Active development

---

## First Comment (Maker's Comment)

Hi Product Hunt community!

I'm the developer behind AutoWealth AI. I built this project because I wanted a tool that analyzes stocks from multiple perspectives -- not just technical charts or just fundamentals, but all of them together.

The multi-agent architecture was inspired by how real investment teams operate: different analysts specialize in different areas, and decisions are made through discussion and consensus. AutoWealth AI simulates this process with three AI agents that independently analyze a stock and then vote on the final recommendation.

A few things I'm particularly proud of:

- The weighted voting mechanism that considers both signal type and confidence level
- Zero-dependency Chinese NLP (pure regex implementation)
- Portfolio optimization without cvxpy (pure numpy)
- 482 tests covering every module

This is an educational and research tool. It's not designed to replace professional financial advice, but rather to help individual investors and developers explore quantitative analysis and multi-agent systems.

I'd love to hear your feedback, especially on:
- What additional indicators or data sources would you like to see?
- Any architecture improvements for the agent system?
- Strategy ideas for the backtesting engine?

Thanks for checking it out!

GitHub: https://github.com/Jsoned/autowealth-ai

---

## Topics / Tags

`open-source`, `python`, `artificial-intelligence`, `investment`, `stock-analysis`, `quantitative-trading`, `multi-agent`, `machine-learning`, `fintech`, `api`
