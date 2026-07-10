# 本地开发说明

## 1. 环境要求

- Python 3.9 或更高版本。
- Node.js 18.17 或更高版本。
- npm。
- Windows PowerShell 5.1 或 PowerShell 7。

当前研究 API 和看板使用本地 mock 数据，不需要真实 DeepSeek Key，不连接券商或交易接口。

## 2. 安装 Python 依赖

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,api]"
```

`api` 可选依赖包含 FastAPI、Uvicorn 和 TestClient 所需的 httpx；`dev` 包含 pytest 等开发工具。

## 3. 安装前端依赖

```powershell
cd frontend
npm install
cd ..
```

CI 或锁文件严格安装可以使用 `npm ci`。

## 4. 环境变量

可从模板创建本地文件：

```powershell
Copy-Item .env.example .env
```

研究看板本地默认值为：

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001
RESEARCH_API_CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000,https://dashboard.outlook.xin
```

Next.js 会自动读取 `frontend/.env.local`，也可以在当前 PowerShell 会话中设置：

```powershell
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8001"
```

根目录 `.env` 可由后端启动脚本传给 Uvicorn。所有 DeepSeek 字段保持为空；mock 研究报告不读取真实 Key。

## 5. 启动研究 API

推荐使用脚本：

```powershell
.\scripts\start_research_api.ps1
```

手动启动：

```powershell
python -m uvicorn autowealth.api.research_server:app --reload --host 127.0.0.1 --port 8001
```

验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/research/health
```

## 6. 启动前端

推荐使用脚本：

```powershell
.\scripts\start_dashboard.ps1
```

指定其他研究 API 地址：

```powershell
.\scripts\start_dashboard.ps1 -ApiBaseUrl "https://api.outlook.xin"
```

手动启动：

```powershell
cd frontend
npm run dev
```

打开 `http://127.0.0.1:3000`。

## 7. 运行测试

本阶段的离线验证入口：

```powershell
.\scripts\run_tests.ps1
```

该脚本依次运行研究 API 测试、前端 typecheck 和前端生产构建。也可以分别执行：

```powershell
python -m pytest tests/test_research_api.py -v --basetemp D:\pytest-tmp-autowealth -p no:cacheprovider
cd frontend
npm run typecheck
npm run build
```

Windows 下如遇 pytest 临时目录权限或清理问题，可固定使用：

```powershell
python -m pytest tests/test_research_api.py -v --basetemp D:\pytest-tmp-autowealth -p no:cacheprovider
```

完整 Python 测试集可将测试目标改为 `tests`。部分历史数据源测试可能访问公开行情源，离线开发时优先运行与当前改动相关的测试文件。

## 8. 开发边界

- 看板与研究 API 仅展示研究结果，不构成投资建议。
- 本地脚本不保存或生成真实密钥。
- mock DeepSeek 路径不访问真实服务。
- 系统不包含真实下单、券商连接或资金操作能力。
