# A 股研究用组合构建模块

## 1. 模块目标

组合构建模块用于把多因子评分和宏观周期评分转换为研究用目标持仓权重。它是股票池筛选、组合回测和风险解释之间的中间层。

当前阶段只做研究用组合构建：

- 不接入真实券商或交易 API。
- 不生成买卖交易指令。
- 不做参数寻优。
- 不承诺收益。
- 不构成投资建议。
- 不接入 DeepSeek。
- 不做前端看板。

实现位置：

- `autowealth/portfolio/schema.py`
- `autowealth/portfolio/constraints.py`
- `autowealth/portfolio/ranking.py`
- `autowealth/portfolio/builder.py`
- `autowealth/portfolio/integration.py`

## 2. 数据结构

### StockCandidate

候选股票输入结构：

- `symbol`
- `score`
- `factor_scores`
- `industry`
- `explanation`
- `warnings`

`score` 通常来自综合多因子评分，统一为 0-100。该分数只代表研究排序，不代表未来涨跌判断。

### PortfolioConstraints

组合约束：

- `max_position_weight`：单股最大目标权重，默认 0.08。
- `min_position_weight`：单股最小目标权重，默认 0.01。
- `max_industry_weight`：单行业最大目标权重，默认 0.25。
- `max_holdings`：最大持仓数，默认 30。
- `min_holdings`：最小持仓数，默认 5。
- `cash_weight_min`：最低现金权重，默认 0.0。
- `cash_weight_max`：最高现金权重，默认 0.4。
- `min_score`：候选股票最低研究分数，默认 0.0。

### TargetHolding

目标持仓输出结构：

- `symbol`
- `score`
- `factor_scores`
- `industry`
- `target_weight`
- `explanation`
- `warnings`

`target_weight` 是研究目标权重，不是交易指令。

### PortfolioBuildResult

组合构建结果：

- `holdings`
- `target_weights`
- `cash_weight`
- `macro_multiplier`
- `selected_symbols`
- `rejected_symbols`
- `warnings`
- `explanation`
- `constraints`
- `equity_weight`

## 3. 因子评分如何转成目标权重

当前实现流程：

1. 输入候选股票 `StockCandidate` 列表。
2. 按 `score` 从高到低排序。
3. 过滤低于 `min_score` 的股票，并记录 `rejected_symbols`。
4. 选择排名前 `max_holdings` 的股票。
5. 根据宏观乘数计算权益目标仓位。
6. 按候选股票分数比例分配权益仓位。
7. 应用单股最大权重约束。
8. 应用行业最大权重约束。
9. 低于最小权重的股票不进入目标持仓，并记录原因。
10. 剩余未分配权重自动作为现金。

该流程只输出目标权重，不判断何时买入、卖出或调仓。

## 4. 宏观周期如何影响权益仓位

宏观模块输出 `equity_position_multiplier`，组合构建模块使用该乘数调节权益总仓位。

示例：

- `0.6`：更保守的研究权益仓位。
- `0.8`：偏低的研究权益仓位。
- `0.9`：不确定环境下的研究权益仓位。
- `1.0`：中性研究权益仓位。
- `1.1` 或 `1.2`：较积极的研究权益仓位，但当前模块不使用杠杆，权益权重不会超过 1。

现金约束会进一步限制权益仓位：

- `cash_weight_min` 会保留最低现金。
- `cash_weight_max` 会限制最高现金。
- 如果单股、行业或持仓数量约束导致无法充分配置，剩余部分仍保留为现金，并记录 warning。

## 5. 单股、行业和现金约束

### 单股约束

单只股票目标权重不能超过 `max_position_weight`。达到上限后，剩余权益预算会尝试分配给其他候选股票。

### 行业约束

同一行业合计目标权重不能超过 `max_industry_weight`。达到行业上限后，该行业候选股票不再继续分配新增权重。

### 现金约束

目标权重总和不能超过 1。未分配权重自动作为 `cash_weight`。

现金权重可能来自：

- 宏观乘数降低权益仓位。
- 候选股票不足。
- 单股上限约束。
- 行业上限约束。
- 最小权重过滤。

## 6. 使用示例

```python
from autowealth.portfolio import (
    PortfolioConstraints,
    StockCandidate,
    build_factor_portfolio,
)

candidates = [
    StockCandidate(
        symbol="600519",
        score=92,
        factor_scores={"value": 80, "quality": 95, "momentum": 88},
        industry="消费",
    ),
    StockCandidate(
        symbol="600036",
        score=86,
        factor_scores={"value": 82, "quality": 88, "momentum": 75},
        industry="金融",
    ),
]

constraints = PortfolioConstraints(
    max_position_weight=0.08,
    max_industry_weight=0.25,
    max_holdings=30,
    min_holdings=5,
    cash_weight_min=0.0,
    cash_weight_max=0.4,
    min_score=60,
)

result = build_factor_portfolio(
    candidates=candidates,
    constraints=constraints,
    macro_multiplier=0.9,
)

target_weights = result.target_weights
```

示例中的股票和权重仅用于说明接口形态，不构成投资建议。

## 7. 与回测引擎的后续衔接

后续可将 `PortfolioBuildResult.target_weights` 传入组合级回测模块：

```python
from autowealth.backtest import PortfolioBacktester

backtester = PortfolioBacktester(
    initial_capital=1_000_000,
    start_date="2009-01-01",
    end_date="2024-12-31",
    rebalance_frequency="quarterly",
)

result = backtester.run(target_weights, price_data=price_data)
```

回测仍需遵守未来函数、幸存者偏差、数据泄露、停牌、涨跌停和交易成本等规则。

## 8. DeepSeek 后续使用边界

后续可以把组合构建结果交给 DeepSeek 做研究摘要、风险复核和反方观点生成，但 DeepSeek 不能直接决定股票入选、目标权重、买卖、调仓或交易执行。

允许用途：

- 摘要组合暴露。
- 解释主要因子来源。
- 列出潜在风险。
- 生成反方观点。

禁止用途：

- 直接给出买卖建议。
- 直接决定仓位。
- 生成交易指令。
- 承诺收益或降低风险。

## 9. 当前限制和未来改进

当前限制：

- 只按综合因子分数分配权重。
- 不做均值方差优化、风险平价、最小方差或 Black-Litterman。
- 不做参数寻优。
- 未纳入个股流动性容量和交易冲击成本。
- 未直接处理停牌、涨跌停、ST、退市等交易约束。

未来可扩展：

- 接入回测引擎做组合构建规则验证。
- 加入行业中性、市值中性和风险预算。
- 加入流动性容量约束。
- 增加组合解释报告和风险复核摘要。
- 引入 DeepSeek 进行研究摘要，但不让其决定买卖或仓位。

## 10. 合规边界

- 本模块仅用于研究和教育。
- 输出只表示研究目标权重。
- 目标权重不构成投资建议、收益承诺或交易指令。
- 历史因子评分和宏观状态不代表未来表现。

