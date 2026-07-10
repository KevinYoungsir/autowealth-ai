# DeepSeek Research Agent

## 角色定位

DeepSeek Research Agent 是 A 股长期投资组合研究系统中的研究助理模块。它只对研究流水线输出进行结构化摘要、风险复核、反方观点生成和数据一致性检查。

该模块不做真实交易决策，不修改组合目标权重，不生成券商指令，不承诺收益。所有输出仅用于研究和教育，不构成投资建议。

## 职责边界

- `summarize_research_result`：把研究流水线结果整理为结构化 JSON 摘要。
- `analyze_risk_flags`：检查回测指标、目标权重、现金仓位和流水线 warnings 中的研究风险点。
- `generate_counter_arguments`：生成反方观点，用于挑战因子稳定性、宏观解释和回测假设。
- `validate_research_consistency`：检查目标权重、入选标的、回测指标、权益曲线和禁止性语言。

Agent 不能直接决定买卖，不能调整 `target_weights`，不能输出真实交易指令。

## 环境变量

真实 API 模式从环境变量读取配置：

```bash
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=
DEEPSEEK_MODEL=
```

仓库中只保留空示例，不写入真实 API Key。未显式关闭 `mock_mode` 时，Agent 不会访问真实网络。

## mock_mode 测试

默认构造方式：

```python
from autowealth.agents.deepseek_research_agent import DeepSeekResearchAgent

agent = DeepSeekResearchAgent(mock_mode=True)
summary = agent.summarize_research_result(research_result)
risk_flags = agent.analyze_risk_flags(research_result)
counter_arguments = agent.generate_counter_arguments(research_result)
validation = agent.validate_research_consistency(research_result)
```

`mock_mode=True` 会使用确定性的本地规则生成 JSON，适合单元测试、示例脚本和离线研究。

## 输出格式

所有方法都返回 JSON 兼容的 `dict`，不返回自由文本。结构化对象包括：

- `ResearchNote`
- `RiskFlag`
- `CounterArgument`
- `ResearchValidationResult`
- `DeepSeekResearchReport`

输出不得包含直接买卖建议或收益保证类表达，也不得覆盖组合构建模块生成的目标权重。

## 后续接入

后续阶段可以把该 Agent 接入研究流水线报告、FastAPI 服务和 outlook.xin 可视化看板。接入时仍需保留研究边界：DeepSeek 只做摘要、复核和解释，不作为自动交易或组合权重决策来源。
