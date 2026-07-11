# outlook.xin 部署说明

> Vercel + Railway 的生产部署、阿里云 DNS、Volume、回滚和验收步骤见
> `docs/production-deployment.md`。本文保留本地和平台中立的部署入口。

## 1. 部署边界

当前系统是 A 股长期组合研究与展示系统。部署内容包括研究 API、mock 研究实验和看板，不包含真实交易能力，不连接券商，也不启用真实 DeepSeek 调用。历史研究结果不代表未来表现，所有页面和接口仅用于研究与教育，不构成投资建议。

## 2. 推荐域名与拓扑

推荐使用两个独立子域名：

```text
浏览器
  -> https://dashboard.outlook.xin  (Next.js 看板)
  -> https://api.outlook.xin        (FastAPI 研究接口)
```

看板浏览器端默认请求自身的 `/api/research/*` 路由，再由 Next.js 服务端转发到 `NEXT_PUBLIC_API_BASE_URL`。这种结构保留了本地开发能力，也便于生产环境统一处理超时、错误和 API 地址。

## 3. 本地启动

首次安装：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,api]"
cd frontend
npm install
cd ..
```

分别启动两个终端：

```powershell
.\scripts\start_research_api.ps1
```

```powershell
.\scripts\start_dashboard.ps1
```

本地访问：

- 看板：`http://127.0.0.1:3000`
- API 健康检查：`http://127.0.0.1:8001/research/health`

## 4. 环境变量

本地默认配置：

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001
RESEARCH_API_CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000,https://dashboard.outlook.xin
RESEARCH_API_TRUSTED_HOSTS=127.0.0.1,localhost,api.outlook.xin
RESEARCH_RUNS_DIRECTORY=data/research_runs
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=
DEEPSEEK_MODEL=
```

生产环境配置：

```env
NEXT_PUBLIC_API_BASE_URL=https://api.outlook.xin
RESEARCH_API_CORS_ORIGINS=https://dashboard.outlook.xin
RESEARCH_API_TRUSTED_HOSTS=api.outlook.xin
RESEARCH_RUNS_DIRECTORY=/data/research_runs
```

`NEXT_PUBLIC_API_BASE_URL` 必须在前端执行 `npm run build` 之前配置。`RESEARCH_API_CORS_ORIGINS` 在后端运行时读取，多个来源用英文逗号分隔。仓库和部署日志中都不应写入真实密钥；当前 mock 接口不需要 DeepSeek 配置。

## 5. 前端部署建议

1. Vercel 项目的 Root Directory 设置为 `frontend`，由平台识别 Next.js。
2. 在构建环境设置 `NEXT_PUBLIC_API_BASE_URL=https://api.outlook.xin`。
3. 执行 `npm ci`、`npm run typecheck`、`npm run build`。
4. 使用 `npm run start -- --hostname 0.0.0.0 --port 3000` 启动生产服务。
5. 将平台提供的 HTTPS 域名绑定到 `dashboard.outlook.xin`。

不要把仅在本机可访问的 `127.0.0.1:8001` 固化到生产构建中。若前后端位于不同主机，前端服务必须能够通过 HTTPS 访问 `api.outlook.xin`。

## 6. 后端部署建议

1. Railway 使用根目录 `Dockerfile.api` 构建，并挂载 Volume 到 `/data`。
2. 设置 `RESEARCH_API_CORS_ORIGINS=https://dashboard.outlook.xin`。
3. 使用进程管理器或容器运行 `python -m uvicorn autowealth.api.research_server:app --host 0.0.0.0 --port 8001`。
4. 在 API 网关或反向代理终止 TLS，并将 HTTPS 请求转发到内部的 `8001` 端口。
5. 只公开研究 API 所需端口，持续检查 `/research/health`。

研究 API app 与旧的 `autowealth.api.server` 相互独立。本次 CORS 配置只作用于研究 API，不改变旧接口行为。

## 7. DNS 记录建议

- `dashboard.outlook.xin`：配置 `CNAME` 指向前端部署平台提供的目标；若平台要求固定 IP，则按平台说明使用 `A`/`AAAA` 记录。
- `api.outlook.xin`：配置 `A`/`AAAA` 指向后端服务器，或配置 `CNAME` 指向 API 网关提供的目标。

两个子域名都应启用有效的 TLS 证书。DNS 生效后，分别验证看板首页、API 健康检查和浏览器 CORS 请求。

## 8. 上线检查

- 全仓不存在错误域名拼写。
- 前端构建环境的 API 地址为 `https://api.outlook.xin`。
- 后端 CORS 精确包含 `https://dashboard.outlook.xin`，不使用 `*`。
- `/research/health` 返回 `mock_mode: true`。
- `/research/demo` 和 mock 研究报告接口不访问外部网络。
- 页面保留研究用途、历史表现限制和非交易能力说明。
- 部署配置、日志和制品中不存在真实 API Key。

更完整的本地命令见 `docs/local-development.md`。
