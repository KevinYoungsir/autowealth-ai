# A 股研究流水线

## 1. 模块作用

研究流水线模块用于把数据、因子、宏观、组合构建和回测结果编排成一次完整的离线研究实验。它负责连接已有模块并汇总结构化结果，帮助后续做研究复盘、风险解释和报告生成。

当前阶段只做研究流水线和结果汇总：

- 不接入 DeepSeek。
- 不接入真实券商或交易 API。
- 不做前端看板。
- 不做收益率参数寻优。
- 不主动访问真实网络。
- 不自动寻找最高收益组合。
- 不承诺收益。

实现位置：

- `autowealth/research/schema.py`
- `autowealth/research/pipeline.py`
- `autowealth/research/report.py`
- `autowealth/research/mock_data.py`

## 2. 如何连接已有模块

研究流水线按以下顺序连接已有能力：

1. `data`：当前阶段接收外部传入或 mock 的价格数据，不主动抓取网络数据。
2. `factors`：接收预计算的因子评分，例如 `FactorScore` 或 `CompositeFactorScore`。
3. `macro`：接收宏观状态或 `macro_multiplier`，用于研究性调节权益仓位。
4. `portfolio`：调用组合构建模块生成研究目标权重。
5. `backtest`：调用组合级回测模块计算历史研究指标。
6. `research/report`：汇总结构化研究摘要。

该流水线只是编排层，不改变上述模块的既有行为。

## 3. 当前输入

`run_research_pipeline` 接收：

- 候选股票代码列表。
- mock 或预计算因子评分。
- mock 或预计算宏观状态，或直接传入 `macro_multiplier`。
- 组合约束。
- 本地构造或外部传入的价格数据字典。
- 回测起止日期。

当前阶段不主动连接 AKShare、东方财富、券商接口或任何实时 API。

## 4. 输出结构

`ResearchPipelineResult` 包含：

- `experiment_name`
- `start_date`
- `end_date`
- `candidate_symbols`
- `selected_symbols`
- `rejected_symbols`
- `factor_summary`
- `macro_summary`
- `target_weights`
- `backtest_metrics`
- `equity_curve`
- `warnings`
- `explanation`

`ResearchSummary` 会进一步压缩为研究摘要，包括组合数量、现金仓位、因子分布、宏观状态、年化收益、最大回撤、夏普比率、卡玛比率和主要 warning。

## 5. 使用 mock 数据示例

```python
from autowealth.research import (
    mock_candidate_symbols,
    mock_factor_scores,
    mock_industries,
    mock_macro_regime,
    mock_portfolio_constraints,
    mock_price_data,
    run_research_pipeline,
    summarize_research_result,
)

result = run_research_pipeline(
    candidate_symbols=mock_candidate_symbols(),
    factor_scores=mock_factor_scores(),
    macro_regime=mock_macro_regime(),
    portfolio_constraints=mock_portfolio_constraints(),
    price_data=mock_price_data(),
    industries=mock_industries(),
    start_date="2020-01-01",
    end_date="2024-12-31",
)

summary = summarize_research_result(result)
```

示例中的股票、评分和价格数据均为 mock 数据，仅用于说明接口形态。

## 6. 不是自动交易系统

研究流水线不会：

- 生成真实交易订单。
- 调用券商接口。
- 自动提交下单请求。
- 输出买卖指令。
- 自动选择最高收益参数。

它只输出研究目标权重、回测指标和结构化摘要。

## 7. 不承诺收益

流水线中的回测指标只是历史样本下的研究结果。历史回测不代表未来表现，也不构成收益承诺。任何指标都必须结合数据区间、费用假设、样本偏差和风险约束一起解读。

## 8. 后续扩展

后续可以在保持边界的前提下扩展：

- 接入本地 parquet 数据缓存。
- 接入 FastAPI，提供研究实验接口。
- 接入可视化看板，展示净值、权重、风险和摘要。
- 接入 DeepSeek 做研究摘要、风险复核和反方观点。

DeepSeek 后续只能做辅助摘要和复核，不能直接决定股票、仓位、交易或调仓。

## 9. 合规边界

- 本模块仅用于研究和教育。
- 输出不是投资建议、交易指令或收益承诺。
- 不应把目标权重解释为实际可执行交易。
- 不应把历史回测解释为未来收益。

