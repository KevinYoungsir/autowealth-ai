# AutoWealth AI - Twitter/X Thread

## Thread 1: Project Launch

**Tweet 1/10**
Introducing AutoWealth AI -- an open-source multi-agent investment analysis engine built with Python.

3 AI agents. 12+ technical indicators. ML predictions. Backtesting. Portfolio optimization. All in one framework.

Thread below

#OpenSource #AI #Python #QuantTrading

GitHub: https://github.com/Jsoned/autowealth-ai

---

**Tweet 2/10**
The core idea: instead of one model deciding, three specialized AI agents analyze stocks from different angles.

- Technical Analyst (35% weight)
- Fundamental Analyst (35% weight)
- Sentiment Analyst (30% weight)

They vote. A coordinator makes the final call.

#MultiAgent #AI

---

**Tweet 3/10**
The Technical Analyst Agent covers 12+ indicators:

MACD, RSI, Bollinger Bands, KDJ, OBV, ATR, DMI (+DI/-DI/ADX), CCI, Williams %R, PSY, and multiple moving averages.

All computed with pandas vectorized operations. Fast and clean.

#TechnicalAnalysis #Python

---

**Tweet 4/10**
Machine learning predictions powered by scikit-learn:

- Random Forest with feature importance analysis
- MLP Neural Network (64x32 hidden layers)
- 18-dimensional feature engineering
- Full metrics: MSE, MAE, R-squared

Train once, predict anytime.

#MachineLearning #sklearn

---

**Tweet 5/10**
Multi-source data support with automatic routing:

- Yahoo Finance (global stocks, ETFs)
- East Money / akshare (Chinese A-shares)
- Binance (crypto: BTC, ETH, SOL...)

Just pass the ticker. The system figures out the right data source.

#DataScience #Finance

---

**Tweet 6/10**
Built-in backtesting engine:

- Buy-and-hold, SMA crossover, RSI strategies
- Performance metrics: total return, max drawdown, Sharpe ratio, win rate
- Full equity curve and trade history

Test your ideas before risking real capital.

#Backtesting #AlgoTrading

---

**Tweet 7/10**
Portfolio optimization using Markowitz mean-variance model:

- Maximum Sharpe ratio portfolio
- Minimum variance portfolio
- Target return optimization
- Pure numpy implementation (no cvxpy needed)

Allocate smarter, not harder.

#PortfolioManagement #FinTech

---

**Tweet 8/10**
Real-time alert system + social sentiment analysis:

Alerts: price breakout, volume anomaly, indicator crossover
Sentiment: Twitter/X, Weibo, Reddit -- 360+ financial sentiment words

Get notified when it matters. Understand the crowd mood.

#SentimentAnalysis #Fintech

---

**Tweet 9/10**
Full-stack deployment ready:

- FastAPI web service (7 RESTful endpoints, auto OpenAPI docs)
- Flutter mobile app (iOS + Android, dark tech theme)
- Streamlit dashboard
- Docker one-click deploy
- 482 tests, all passing

#FastAPI #Flutter #Docker

---

**Tweet 10/10**
AutoWealth AI is 100% open source (MIT license).

For learning, research, and building your own analysis tools.

Star us on GitHub:
https://github.com/Jsoned/autowealth-ai

Contributions welcome. Let's build something useful together.

#OpenSource #Python #AI #Investing

---

## Thread 2: Technical Deep Dive

**Tweet 1/8**
How does AutoWealth AI's multi-agent system work? A technical deep dive.

The secret sauce: weighted voting with confidence scoring. Not simple majority vote.

Thread

#Python #AI #Architecture

GitHub: https://github.com/Jsoned/autowealth-ai

---

**Tweet 2/8**
Each agent returns an AgentSignal (Pydantic model):

- signal_type: buy / sell / hold
- confidence: 0-100
- reasoning: text explanation
- target_price & stop_loss: optional

The coordinator multiplies confidence x weight, then normalizes.

#Pydantic #DesignPatterns

---

**Tweet 3/8**
Example: Technical Agent says BUY (80% confidence, 35% weight) = 0.28 contribution
Fundamental Agent says HOLD (50% confidence, 35% weight) = 0.175
Sentiment Agent says BUY (70% confidence, 30% weight) = 0.21

BUY wins with highest weighted score.

#Math #DecisionMaking

---

**Tweet 4/8**
The 18-dimensional ML feature vector:

MA(5/10/20/60), RSI(14), MACD, MACD Signal, MACD Histogram, Bollinger Position, Volatility(20d), Volume Change, Volume MA(5), Volume Ratio, Momentum(5/10/20), Return(1d), Price Position(20d)

#FeatureEngineering

---

**Tweet 5/8**
Chinese NLP with zero external dependencies:

Intent recognition via regex patterns. 80+ stock name mappings ("Maotai" -> 600519.SS, "Apple" -> AAPL).

Supports: "analyze Maotai", "compare Apple and Microsoft", "backtest BYD"

#NLP #Python

---

**Tweet 6/8**
Portfolio optimization without cvxpy:

Pure numpy matrix operations + grid search.

Mean returns, covariance matrix, annualized Sharpe ratio -- all computed from first principles.

Clean, minimal dependencies.

#numpy #Optimization

---

**Tweet 7/8**
Testing philosophy: 482 tests covering every module.

Agents, analyzers, backtest engine, ML predictor, API endpoints, NLP parser, social sentiment, portfolio optimizer.

GitHub Actions CI runs them on every push.

#Testing #CI #Quality

---

**Tweet 8/8**
Want to explore the code?

Clean architecture, full type annotations, docstrings everywhere.

GitHub: https://github.com/Jsoned/autowealth-ai

PRs welcome -- new indicators, data sources, strategies, whatever you'd add.

#OpenSource #Python #CodeReview
