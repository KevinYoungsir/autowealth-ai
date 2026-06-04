# 项目路线图 | Project Roadmap

> AutoWealth AI 的发展规划和里程碑。本文档描述了项目当前状态和未来方向。
>
> Development plan and milestones for AutoWealth AI. This document describes the current status and future direction of the project.

---

## 版本概览 | Version Overview

```
v0.1.0 ── v0.2.0 ── v0.3.0 ── v0.4.0 ── v1.0.0 ── v2.0.0 ── v3.0.0
  │          │          │          │          │          │          │
  初始       UI升级     扩展功能   ML/预警    稳定版     GPT/国际化  远景规划
  版本       优化       增强       社交/移动   发布       社区       生态
```

---

## v1.0.0 - 稳定版发布 | Stable Release

**目标**: 代码质量、文档完善、用户体验优化，达到生产可用状态。

**Target**: Code quality, documentation, UX optimization, production-ready.

**状态**: 开发中 | Status: In Development

### 核心目标 | Core Goals

- [ ] 代码覆盖率提升至 80%+
- [ ] 完善所有模块的类型注解（mypy 通过）
- [ ] 发布 PyPI 包 `pip install autowealth-ai`
- [ ] 完善中英文文档
- [ ] Docker 镜像发布
- [ ] CI/CD 流水线完善（自动测试、自动发布）
- [ ] 性能基准测试和优化
- [ ] 错误处理和日志系统完善

### 已完成功能 | Completed Features (v0.1.0 - v0.4.0)

| 版本 | 功能 | 状态 |
|------|------|------|
| v0.1.0 | 多智能体协作系统（技术/基本面/情绪分析） | 已完成 |
| v0.1.0 | Yahoo Finance 数据源 + 本地缓存 | 已完成 |
| v0.1.0 | 加权投票决策机制 | 已完成 |
| v0.1.0 | Streamlit 可视化界面 | 已完成 |
| v0.1.0 | 命令行工具 | 已完成 |
| v0.2.0 | UI 界面升级优化 | 已完成 |
| v0.3.0 | 12+ 扩展技术指标（OBV/ATR/DMI/CCI/WR/PSY） | 已完成 |
| v0.3.0 | 多数据源支持（东方财富/币安） | 已完成 |
| v0.3.0 | 马科维茨组合优化（有效前沿/最大夏普） | 已完成 |
| v0.3.0 | 回测系统（买入持有/均线交叉/RSI策略） | 已完成 |
| v0.3.0 | FastAPI Web API（7个RESTful端点） | 已完成 |
| v0.3.0 | 中文自然语言交互（意图识别/实体提取） | 已完成 |
| v0.4.0 | 机器学习预测（随机森林/MLP神经网络） | 已完成 |
| v0.4.0 | 实时预警系统（5种规则/多渠道通知） | 已完成 |
| v0.4.0 | 社交情绪分析（Twitter/微博/Reddit） | 已完成 |
| v0.4.0 | Flutter 移动端 App | 已完成 |

---

## v2.0.0 - 智能升级 | Intelligence Upgrade

**目标**: 引入大语言模型、多语言支持、实时数据推送、社区功能。

**Target**: Integrate LLM, multi-language support, real-time data push, community features.

**状态**: 规划中 | Status: Planned

**预计时间**: 2026 Q3-Q4 | Estimated: 2026 Q3-Q4

### GPT/LLM 集成 | GPT/LLM Integration

- [ ] GPT-4o 智能问答（自然语言投资分析对话）
- [ ] LLM 驱动的智能体分析报告生成
- [ ] 支持本地 LLM（Ollama/LM Studio）无网络分析
- [ ] AI 投资建议解释（可解释性增强）
- [ ] 多模型支持（OpenAI/Anthropic/本地模型）

### 国际化 | Internationalization (i18n)

- [ ] 多语言界面（中文/英文/日文）
- [ ] 多市场数据源适配（美股/A股/港股/日股/欧股）
- [ ] 多币种支持（USD/CNY/JPY/EUR）
- [ ] 本地化文档翻译

### 实时数据推送 | Real-time Data Push

- [ ] WebSocket 实时行情推送
- [ ] 实时预警通知推送
- [ ] 前端实时图表更新
- [ ] 订阅式数据流（按需订阅标的）

### 社区功能 | Community Features

- [ ] 策略分享与评分系统
- [ ] 跟单交易信号
- [ ] 投资组合公开分享
- [ ] 社区讨论板块
- [ ] 排行榜系统

---

## v3.0.0 - 生态扩展 | Ecosystem Expansion

**目标**: 构建完整的投资分析生态系统，支持插件化扩展。

**Target**: Build a complete investment analysis ecosystem with plugin-based extensibility.

**状态**: 远景规划 | Status: Vision

**预计时间**: 2027+ | Estimated: 2027+

### 插件系统 | Plugin System

- [ ] 第三方指标插件（自定义技术指标）
- [ ] 第三方数据源插件（自定义数据接入）
- [ ] 第三方通知渠道插件（微信/Telegram/Discord）
- [ ] 策略市场（上传/下载/评分交易策略）

### 高级分析 | Advanced Analysis

- [ ] 期权链分析
- [ ] 期货合约分析
- [ ] 宏观经济指标整合
- [ ] 行业轮动分析
- [ ] 量化因子库

### 企业级功能 | Enterprise Features

- [ ] 多用户权限管理
- [ ] 审计日志
- [ ] SaaS 部署方案
- [ ] 团队协作功能
- [ ] API 速率限制和计费

### AI 深度集成 | Deep AI Integration

- [ ] 强化学习交易策略
- [ ] 多模态分析（财报图片/新闻视频）
- [ ] 知识图谱构建
- [ ] 自动策略发现和优化
- [ ] 风险预警 AI 模型

---

## 里程碑时间线 | Milestone Timeline

```
2026 Q1
├── v0.1.0 初始版本发布
├── v0.2.0 UI 升级
├── v0.3.0 扩展功能（指标/数据源/优化/回测/加密货币/API/NLP）
└── v0.4.0 ML/预警/社交/移动端

2026 Q2
├── v1.0.0 稳定版发布
│   ├── PyPI 包发布
│   ├── Docker 镜像
│   ├── 文档完善
│   └── CI/CD 完善

2026 Q3-Q4
├── v2.0.0 智能升级
│   ├── GPT/LLM 集成
│   ├── 国际化支持
│   ├── WebSocket 实时推送
│   └── 社区功能

2027+
└── v3.0.0 生态扩展
    ├── 插件系统
    ├── 高级分析
    ├── 企业级功能
    └── AI 深度集成
```

---

## 贡献路线图 | Contributing to the Roadmap

如果您希望参与某个功能的开发，请：

If you'd like to contribute to a feature, please:

1. 在对应的 GitHub Issue 中留言表达兴趣
2. 在 [Discussions](https://github.com/Jsoned/autowealth-ai/discussions) 中讨论实现方案
3. 提交 Pull Request

标记为 `help wanted` 的 Issue 欢迎社区贡献。

Issues labeled `help wanted` are welcome for community contributions.
