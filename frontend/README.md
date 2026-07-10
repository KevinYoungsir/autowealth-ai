# AutoWealth Research Dashboard

这是面向 `outlook.xin` 的 Next.js、TypeScript 和 Tailwind CSS 研究看板原型，推荐生产域名为 `dashboard.outlook.xin`。

看板只展示 mock 或预计算研究结果，不连接券商、真实交易接口、实时 DeepSeek 或参数寻优流程。历史指标仅用于研究和教育，不代表未来表现，也不构成投资建议。

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

## 配置 API 地址

前端服务端转发层读取 `NEXT_PUBLIC_API_BASE_URL`。未配置时默认使用：

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001
```

生产构建应在执行 `npm run build` 之前配置：

```env
NEXT_PUBLIC_API_BASE_URL=https://api.outlook.xin
```

旧的 `RESEARCH_API_BASE_URL` 暂时保留为兼容回退，但新环境统一使用 `NEXT_PUBLIC_API_BASE_URL`。浏览器仍请求同源的 `/api/research/*`，由 Next.js 路由转发到上述研究 API 地址。

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

- Dashboard：组合指标、现金仓位、目标权重和权益曲线。
- Backtest：历史研究指标、权益曲线及月度/年度收益占位。
- Portfolio：研究目标权重、入选标的和过滤记录。
- Factors：因子分布和候选评分。
- Macro：宏观状态、仓位系数和宏观维度。
- Research Notes：mock DeepSeek 摘要、风险复核和反方观点。

## API 调用

Next.js 路由会转发以下研究接口：

- `GET /research/health`
- `GET /research/demo`
- `POST /research/deepseek/mock-report`

当前 DeepSeek 路径固定使用 mock 模式，不读取真实密钥，也不访问真实 DeepSeek 服务。

## 部署域名

- 看板：`https://dashboard.outlook.xin`
- 研究 API：`https://api.outlook.xin`

生产环境的 DNS、环境变量、CORS 和反向代理说明见 `docs/deployment.md`。
