# 简体中文本地化

## 定位

AutoWealth v0.15.1 面向中国大陆研究用户提供简体中文看板与真实研究报告。
本地化只改变展示文本，不修改 artifacts、研究指标、运行状态、风险等级或原始
warning。系统仍是只读研究工具，不包含真实交易能力；历史结果仅用于研究与教育，
不构成投资建议，也不代表未来表现。

## Locale 契约

真实报告接口支持两个稳定 locale：

```http
GET /research/runs/{run_id}/report?locale=zh-CN
GET /research/runs/{run_id}/report?locale=en-US
```

- 未传 `locale` 时默认 `en-US`，保证 v0.15.0 客户端兼容。
- Next.js 看板调用 `fetchResearchReport(runId, "zh-CN")`，不依赖后端默认值。
- 响应顶层包含 `locale`，HTTP 响应包含对应的 `Content-Language`。
- 其他 locale 由 FastAPI 参数校验返回 HTTP 422。
- 本地化请求失败时，真实运行页面显示中文错误，不静默回退为 mock。

## 稳定机器字段

以下字段始终保留原值：

- `run_id`、`data_source`、`generated_mode`
- `run_status`、`benchmark_status`
- 风险 `code`、`category`、`severity`
- 数值、日期、symbol、artifact 文件名
- 原始 provider 错误和原始 warning

前端为机器值增加中文标签，并在旁边以等宽字体保留技术值。例如页面显示
“部分完成”，同时保留 `partial_success`。本地化 catalog 只生成摘要、说明、
复核重点和边界文案，不参与任何研究计算。

## Warning 双轨展示

`data_quality_review.evidence.warnings` 继续按原顺序返回 `warnings.json` 的完整
字符串。报告另外提供：

```json
{
  "source_message": "original provider warning",
  "display_message": "行情数据源调用或覆盖存在异常，请结合原始技术信息复核。",
  "category": "price_provider",
  "category_label": "行情数据源"
}
```

`source_message` 不会被覆盖或在线翻译。无法可靠逐句翻译时，中文只说明已知类别，
并通过折叠区保留原始技术文本。看板首屏按类别显示总数和最多 3 条中文样本；完整
原文仍可展开查看，因此 warning 数量、顺序和严重程度均不变。

## 字体方案

项目不使用 Google Fonts、`next/font` 远程字体、`@font-face` 或字体 npm 包。
正文使用系统字体回退：

```text
"PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei",
"Noto Sans CJK SC", "Source Han Sans SC", system-ui, -apple-system,
BlinkMacSystemFont, "Segoe UI", sans-serif
```

技术字段使用：

```text
"JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", monospace
```

该方案不依赖境外字体网络，适合中国大陆部署。正文行高为 `1.7`，中文不使用
uppercase 或额外字距，长文本使用受限阅读宽度和安全换行。

## 代码结构

前端词典位于：

```text
frontend/i18n/
  index.ts
  types.ts
  machine-labels.ts
  mock-report-presenter.ts
  messages/
    zh-CN.ts
    en-US.ts
```

后端报告 catalog 位于：

```text
autowealth/i18n/
  locale.py
  warning_presenter.py
  catalogs/
    zh_cn.py
    en_us.py
```

`en-US` 继续作为报告 API 默认语言。前端当前产品界面固定为 `zh-CN`；未来增加
语言切换时，应复用现有词典和机器值映射，不得改变 API 稳定字段。
