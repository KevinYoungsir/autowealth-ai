# 宏观经济周期与外部风险模块

## 1. 模块作用

宏观经济周期与外部风险模块用于识别经济环境、解释组合风险背景，并为后续组合仓位研究提供参考系数。该模块只输出研究状态判断和风险评分，不生成买卖信号，不执行调仓，不连接真实交易接口，也不构成投资建议。

当前阶段实现位置：

- `autowealth/macro/schema.py`
- `autowealth/macro/regime.py`
- `autowealth/macro/scoring.py`
- `autowealth/macro/position.py`
- `autowealth/macro/data_loader.py`

## 2. 数据结构

### MacroIndicator

用于描述单个宏观指标观察值：

- `name`
- `value`
- `as_of_date`
- `source`
- `warning`

### MacroRegime

用于描述宏观状态分类：

- `as_of_date`
- `regime`
- `growth_score`
- `inflation_score`
- `liquidity_score`
- `credit_score`
- `policy_score`
- `external_risk_score`
- `explanation`
- `warnings`
- `indicators`

### MacroRiskScore

用于描述完整宏观评分和研究仓位系数：

- `as_of_date`
- `growth_score`
- `inflation_score`
- `liquidity_score`
- `credit_score`
- `policy_score`
- `external_risk_score`
- `regime`
- `equity_position_multiplier`
- `explanation`
- `warnings`
- `indicators`

所有分数统一为 0-100。分数越高代表该维度越有利于权益资产；`external_risk_score` 越高代表外部风险越低。

## 3. 宏观状态

当前支持以下宏观状态：

- `expansion`：增长较强、通胀相对可控、流动性和信用环境不差。
- `slowdown`：增长放缓，流动性或信用环境偏弱。
- `recession`：增长和信用均明显偏弱。
- `recovery`：增长处于修复区间，流动性或信用条件改善。
- `stagflation`：增长偏弱，同时通胀压力较高。
- `uncertain`：数据缺失较多或状态不清晰。

这些状态只代表研究分类，不是投资建议或交易指令。

## 4. 宏观维度含义

### growth：经济增长

当前主要参考 PMI。PMI 越高，增长评分越高；PMI 明显低于荣枯线时，增长评分下降。

### inflation：通胀

当前参考 CPI 同比和 PPI 同比。通胀过高或过低都会降低评分；温和通胀环境评分较高。

### liquidity：流动性

当前参考 M2 同比和 10 年期国债收益率。货币增速较高、利率较低时，流动性评分较高。

### credit：信用周期

当前参考社融同比。社融增速较高时，信用环境评分较高；社融偏弱时评分下降。

### policy：政策环境

当前可从本地 CSV 直接输入 `policy_score`。分数越高，表示政策环境在研究假设下越友好。

### external_risk：国际政治与外部冲击

当前可从本地 CSV 直接输入 `external_risk_score`。该分数越高代表外部风险越低；分数越低代表地缘政治、贸易摩擦、海外利率、汇率、能源价格或供应链冲击等风险较高。

该字段不是新闻判断器，也不会把事件直接转换为交易动作。后续可通过官方事件源、公告、新闻标签和人工复核形成更完整的外部风险数据。

## 5. 评分方式

当前评分规则为启发式研究规则：

- PMI 映射到增长评分。
- CPI 和 PPI 与温和通胀区间的距离映射到通胀评分。
- M2 和 10 年期国债收益率共同映射到流动性评分。
- 社融同比映射到信用评分。
- `policy_score` 和 `external_risk_score` 由外部结构化数据直接输入并裁剪到 0-100。
- 缺失数据不会导致模块崩溃，会记录 warning 并降级为中性评分。

这些规则是第一版工程占位，后续需要结合历史数据、专家规则和回测检验迭代。

## 6. 仓位研究系数

`equity_position_multiplier` 输出范围限制在 0.6 到 1.2：

- `recession`：默认 0.6
- `slowdown`：默认 0.8
- `uncertain`：默认 0.9
- `stagflation`：默认 0.75
- `recovery`：默认 1.0
- `expansion`：默认 1.1
- `strong_expansion` 或极优环境预留 1.2

该 multiplier 只是研究用仓位调节系数，不直接产生交易指令，不代表最终组合仓位，也不代表风险控制承诺。

## 7. 本地 CSV 数据

当前阶段只支持从本地 CSV 读取宏观指标，不强依赖实时宏观 API。

CSV 可包含字段：

```text
date
pmi
cpi_yoy
ppi_yoy
m2_yoy
social_financing_yoy
ten_year_yield
usd_cny
policy_score
external_risk_score
```

示例：

```python
from autowealth.macro import latest_macro_indicators, score_macro_environment

indicators = latest_macro_indicators("data/macro/monthly_macro.csv")
result = score_macro_environment(indicators, as_of_date=indicators["date"])
```

## 8. 限制和未来改进

当前限制：

- 使用启发式阈值，尚未通过长期历史样本校准。
- 未区分官方发布日期和统计期，后续进入回测时必须处理发布时间滞后。
- 外部风险分数需要人工或结构化事件源输入，当前不自动抓取新闻。
- 未实现最终调仓策略、组合优化或交易执行。

未来可扩展：

- 接入国家统计局、中国人民银行、外汇交易中心等官方宏观数据源。
- 接入公告、新闻、国际政治事件和商品价格数据源。
- 增加宏观指标发布日、修订版本和数据快照。
- 增加宏观状态转移概率、压力测试和情景分析。
- 与组合回测模块联动验证仓位研究系数的有效性。

## 9. 合规边界

- 本模块仅用于研究和教育。
- 宏观状态、风险评分和仓位研究系数不构成投资建议。
- 输出不得被解释为买入、卖出、持有、加仓或减仓指令。
- 历史宏观状态与未来市场表现不存在确定关系。

