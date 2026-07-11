# AutoWealth Research Dashboard

这是面向 `outlook.xin` 的 Next.js、TypeScript 和 Tailwind CSS 研究看板原型，推荐生产域名为 `dashboard.outlook.xin`。

看板只展示已落盘真实 artifacts、mock 或预计算研究结果，不连接券商、真实交易接口、实时 DeepSeek 或参数寻优流程。历史指标仅用于研究和教育，不代表未来表现，也不构成投资建议。

看板现在优先读取 `data/research_runs` 下已经完成且未被修改的真实研究
artifacts。真实数据、演示数据和 API 不可用状态会在页面顶部明确区分。

## 本地启动后端

在仓库根目录运行：

```powershell
.\scripts\start_research_api.ps1
```

等价的手动命令：

```powershell
python -m uvicorn autowealth.api.research_server:app --reload --host 127.0.0.1 --port 8001
```

健康检查地址为 `http://127.0.0.1:8001/research/health`。

真实看板启动前应确认目录存在并至少包含一个完整运行：

```text
data/research_runs/<run_id>/run_manifest.json
data/research_runs/<run_id>/metrics.json
data/research_runs/<run_id>/equity_curve.parquet
```

可通过环境变量指定部署时挂载的只读目录：

```env
RESEARCH_RUNS_DIRECTORY=data/research_runs
```

## 配置 API 地址

前端服务端转发层读取 `NEXT_PUBLIC_API_BASE_URL`。本地开发未配置时默认使用：

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001
```

生产构建应在执行 `npm run build` 之前配置：

```env
NEXT_PUBLIC_API_BASE_URL=https://api.outlook.xin
```

旧的 `RESEARCH_API_BASE_URL` 只在非生产环境保留为兼容回退。生产构建缺少
`NEXT_PUBLIC_API_BASE_URL` 时，同源代理返回清晰配置错误并显示
`api_unavailable`，不会静默连接 localhost。浏览器仍请求同源的
`/api/research/*`，由 Next.js 路由转发到上述研究 API 地址。

## 本地启动前端

在仓库根目录运行：

```powershell
cd frontend
npm install
cd ..
.\scripts\start_dashboard.ps1
```

也可以在 `frontend/` 中手动执行：

```powershell
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8001"
npm run dev
```

打开 `http://127.0.0.1:3000`。

## 页面

- Dashboard：运行状态、覆盖率、绩效、权益曲线、持仓和 warning 摘要。
- Backtest：年度/月度收益、回撤、换手率和基准状态。
- Portfolio：最近调仓持仓、现金比例和 `min_holdings` 检查。
- Factors：各因子覆盖率、缺失数量和实际复合权重。
- Macro：宏观观察数量及中性乘数状态。
- Research Notes：明确标记的 mock review，不与真实量化结果混合。
- System Status：前端/API 状态、运行目录、latest run、benchmark 和 warning 摘要。

侧栏顶部的运行选择器用于切换 `run_id`。选择后各页面同步读取同一运行。

## API 调用

Next.js 路由会转发以下研究接口：

- `GET /research/health`
- `GET /research/demo`
- `POST /research/deepseek/mock-report`
- `GET /research/runs`
- `GET /research/runs/latest`
- `GET /research/runs/{run_id}`
- `GET /research/runs/{run_id}/equity-curve`
- `GET /research/runs/{run_id}/benchmark-curve`
- `GET /research/runs/{run_id}/holdings`
- `GET /research/runs/{run_id}/trades`
- `GET /research/runs/{run_id}/factors`
- `GET /research/runs/{run_id}/warnings`

当前 DeepSeek 路径固定使用 mock 模式，不读取真实密钥，也不访问真实 DeepSeek 服务。
mock 报告只在进入 Research Notes 页面时按需加载，System Status 不调用该接口。

## 数据来源识别

- `real_artifacts`：来自配置目录中已落盘的真实研究运行。
- `mock_demo`：没有可用运行时显示的演示数据。
- `api_unavailable`：后端不可访问，页面不把任何本地占位内容标为真实。

`partial_success` 会显示“部分完成”和主要限制；`failed` 不展示绩效结论。

## 部署域名

- 看板：`https://dashboard.outlook.xin`
- 研究 API：`https://api.outlook.xin`

Vercel 导入仓库时把 Root Directory 设置为 `frontend`，无需 `vercel.json`。
Framework 使用 Next.js 自动识别，安装和构建分别执行 `npm ci`、`npm run build`，
Production 环境设置 `NEXT_PUBLIC_API_BASE_URL=https://api.outlook.xin`。该变量是
公开构建变量，禁止保存任何密钥。

生产环境的 Railway、Volume、阿里云 DNS、CORS 和 Trusted Host 说明见
`docs/production-deployment.md`。
