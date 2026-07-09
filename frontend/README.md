# AutoWealth Research Dashboard Prototype

This is a Next.js + TypeScript + Tailwind CSS prototype for the outloo.xin research dashboard.

The dashboard is research-only. It visualizes local mock research API output and does not connect to brokers, trading APIs, live DeepSeek calls, or parameter optimization workflows. Historical metrics are for analysis and education only and do not represent future results.

## Start The Backend API

From the repository root:

```bash
python -m uvicorn autowealth.api.research_server:app --reload --port 8001
```

The frontend proxy expects the research API at:

```text
http://127.0.0.1:8001
```

You can override it for the Next.js server with:

```bash
RESEARCH_API_BASE_URL=http://127.0.0.1:8001
```

## Start The Frontend

From `frontend/`:

```bash
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:3000
```

## Pages

- Dashboard: overview metrics, cash weight, allocation and equity curve.
- Backtest: annualized return, drawdown, Sharpe, Calmar and return matrix placeholders.
- Portfolio: target weights, selected symbols and rejected candidates.
- Factors: factor score distribution and ranked candidate scores.
- Macro: macro regime, equity multiplier and macro dimension scores.
- Research Notes: mock DeepSeek report, risk flags and counter-arguments.

## API Calls

The Next.js route handlers proxy to the local research API:

- `GET http://127.0.0.1:8001/research/health`
- `GET http://127.0.0.1:8001/research/demo`
- `POST http://127.0.0.1:8001/research/deepseek/mock-report`

DeepSeek is always used through the mock report endpoint in this prototype.
