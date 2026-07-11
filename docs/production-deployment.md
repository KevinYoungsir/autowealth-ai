# AutoWealth 生产部署

## 部署边界

本方案只部署只读研究 API 和研究看板：

```text
dashboard.outlook.xin -> Vercel (frontend/ Next.js)
api.outlook.xin       -> Railway (FastAPI + persistent Volume)
outlook.xin DNS       -> 阿里云云解析 DNS
```

本阶段不转移域名注册商、不修改 Nameserver、不修改根域名、不操作真实平台，
也不包含真实交易、真实 DeepSeek、参数寻优或完整 15 年研究任务。历史研究结果
仅用于研究和教育，不代表未来表现，也不构成投资建议。

## 推荐部署顺序

1. 先在 Railway 导入 GitHub 仓库并部署后端。
2. 使用 Railway 临时域名验证 `/research/health`。
3. 绑定 `api.outlook.xin`，完成 DNS 和 HTTPS 验证。
4. 在 Vercel 导入同一个仓库，Root Directory 设为 `frontend`。
5. 设置生产 API 地址并完成首次前端部署。
6. 绑定 `dashboard.outlook.xin`，完成 DNS 和 HTTPS 验证。
7. 运行 `scripts/verify_production_deployment.ps1` 做只读验收。

## Railway 后端

### 导入和构建

1. 从 Railway 创建项目并导入 GitHub 仓库。
2. 服务根目录保持仓库根目录。
3. 使用仓库中的 `railway.toml` 和 `Dockerfile.api`。
4. 确认构建日志显示自定义 Dockerfile 路径为 `Dockerfile.api`。
5. 不在 Railway 配置文件或仓库中保存密钥。

`railway.toml` 设置 `/research/health` 健康检查、120 秒超时和失败重启策略。
Railway 健康检查会使用平台 Host，因此应用会额外允许
`healthcheck.railway.app`，但不会使用通配 Trusted Host。

### 生产变量

在 Railway Variables 中设置：

```env
RESEARCH_RUNS_DIRECTORY=/data/research_runs
RESEARCH_API_CORS_ORIGINS=https://dashboard.outlook.xin
RESEARCH_API_TRUSTED_HOSTS=api.outlook.xin
```

`PORT` 使用 Railway 注入值，不建议手工固定。不要配置真实 DeepSeek Key；当前
研究报告接口保持 mock 模式。若使用 Railway 临时域名验收，应把该临时域名作为
一个精确值临时加入 `RESEARCH_API_TRUSTED_HOSTS`，验证后再收紧。

### Volume

1. 给 API 服务创建持久化 Volume。
2. 将 Volume 挂载到 `/data`。
3. 设置 `RESEARCH_RUNS_DIRECTORY=/data/research_runs`。
4. 空 Volume 可以启动；health 会报告目录和 latest run 的布尔状态。
5. artifacts 存储在 Volume，不依赖容器临时文件系统。
6. 启用 Railway Volume 备份，并在重要导入前另做离线备份。

镜像默认使用非 root 用户。Railway 当前将 Volume 以 root 身份挂载；如果所选
套餐或运行时导致非 root 用户无法创建 `/data/research_runs`，API 仍可启动并将
目录标记为不可用。优先通过受控的 Railway 文件管理流程预建目录并上传只读
artifacts。只有在核对 Railway 最新安全文档和权限影响后，才评估平台提供的
`RAILWAY_RUN_UID` 兼容方案，不能在仓库中默认降低容器权限。

### artifacts 导入

1. 在本地确认 `data/research_runs/<run_id>/run_manifest.json` 可解析。
2. 备份 Railway Volume，并确认目标中不存在同名 `run_id`。
3. 使用已认证的 Railway CLI/service 文件浏览功能或平台受控维护通道，将整个
   `<run_id>` 目录复制到 `/data/research_runs/<run_id>`。
4. 不覆盖已有 `run_id`，不通过公开 HTTP API 上传。
5. 上传后检查 `/research/runs`、对应 run 详情和 manifest 摘要。

artifacts 始终保持 Git 忽略，也不会进入 Docker 镜像。

## Vercel 前端

1. 从 Vercel 导入同一个 GitHub 仓库。
2. Root Directory 设置为 `frontend`。
3. Framework Preset 使用自动识别的 Next.js。
4. Install Command 使用 `npm ci`，Build Command 使用 `npm run build`。
5. 在 Production 环境设置：

```env
NEXT_PUBLIC_API_BASE_URL=https://api.outlook.xin
```

6. 完成首次部署后绑定 `dashboard.outlook.xin`。

前端不依赖仓库根目录文件。生产构建缺少 `NEXT_PUBLIC_API_BASE_URL` 时，同源代理
返回清晰的配置错误并显示 `api_unavailable`，不会静默连接 localhost。
`NEXT_PUBLIC_` 变量会进入浏览器构建产物，因此其中只能放公开 API 地址，不能
放任何密钥、Token 或内部路径。

## 阿里云 DNS 配置

域名注册和解析继续留在阿里云：

1. 不转移注册商，不修改现有 Nameserver。
2. 本阶段不修改 `outlook.xin` 根域名。
3. 不删除或覆盖现有 A、MX、TXT、邮箱验证及其他业务记录。
4. 在阿里云云解析 DNS 新增主机记录 `dashboard`。记录类型通常为 CNAME，记录
   值必须复制 Vercel Domains 页面当时提供的实际目标。
5. 新增主机记录 `api`。记录类型和目标值以 Railway Networking 页面实际提示
   为准；如要求 TXT 验证，按平台提示新增独立验证记录。
6. 不在代码或文档中硬编码可能变化的 Vercel/Railway 目标地址。

DNS 生效后验证：

```text
https://dashboard.outlook.xin
https://api.outlook.xin/research/health
```

两个域名都必须使用有效 HTTPS。HTTPS 看板不得请求 HTTP API。Vercel 和 Railway
在中国大陆的访问速度可能受跨境网络影响；未来迁移到大陆服务器前，需重新核实
ICP 备案、接入商和数据合规要求。

## CORS、Host 与 HTTPS 检查

- Railway 的 CORS 只允许 `https://dashboard.outlook.xin`，不使用 `*`。
- Trusted Hosts 至少包含 `api.outlook.xin`；平台健康检查 Host 由应用安全追加。
- Vercel Production 的 API 地址必须以 `https://` 开头。
- 浏览器 Network 面板不应出现到 localhost、HTTP API 或磁盘路径的请求。
- OPTIONS 预检应返回允许的精确 Origin，未知 Origin 不返回允许头。
- 服务器错误响应只返回稳定错误代码和通用消息，不包含堆栈、绝对路径或变量值。

## 上线验证

生产环境执行：

```powershell
.\scripts\verify_production_deployment.ps1
```

本地环境执行：

```powershell
.\scripts\verify_production_deployment.ps1 `
  -DashboardUrl http://127.0.0.1:3000 `
  -ApiUrl http://127.0.0.1:8001
```

脚本只发送 GET 请求，检查 API 和页面状态，不启动研究任务、不调用 DeepSeek、
不写入远程数据。`/research/runs/latest` 在空目录返回结构化 404 时会被记录为
“暂无运行”，而不是伪造一条运行。

## 回滚

1. 回滚前备份 Railway Volume 中的重要 artifacts。
2. 代码基线可回滚到 `v0.13.0`，但先确认该版本与当前 artifacts schema 兼容。
3. Vercel 从 Deployments 选择上一稳定前端 Deployment 回滚。
4. Railway 从 Deployments 选择上一稳定后端 Deployment 回滚。
5. Volume 与代码 Deployment 生命周期分离；代码回滚不得删除 Volume artifacts。
6. 回滚后重新验证 health、runs、最新运行、CORS、Host 和两个 HTTPS 域名。

## 风险与展示规则

- 系统仅用于研究展示，不包含真实交易能力，也不构成投资建议。
- `partial_success` 必须醒目标记并展示主要限制。
- `failed` 运行不能展示为有效绩效结论。
- benchmark unavailable 时只能展示不可用原因，不能伪造曲线或收益。
- `real_artifacts`、`mock_demo` 和 `api_unavailable` 必须明确区分。
- artifacts 的 point-in-time 和幸存者偏差限制不会因部署而消失。
