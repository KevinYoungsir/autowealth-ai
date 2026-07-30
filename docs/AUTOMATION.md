# AutoWealth AI - 自动化与发布配置指南

> 本文档说明如何配置 AutoWealth AI 项目的 GitHub Actions 自动化工作流体系。

## 目录

- [工作流概览](#工作流概览)
- [GitHub Secrets 配置](#github-secrets-配置)
- [各平台 API 密钥获取指南](#各平台-api-密钥获取指南)
- [工作流详细说明](#工作流详细说明)
- [故障排除](#故障排除)

---

## 工作流概览

| 工作流文件 | 触发条件 | 功能描述 | 所需 Secrets |
|-----------|---------|---------|-------------|
| `ci.yml` | PR 或 push 到 `main` | 后端、前端和 Docker 离线门禁 | 无 |
| `release.yml` | 人工推送严格 `vMAJOR.MINOR.PATCH` tag | 验证、测试、构建，最后创建 Release | 无（使用 GITHUB_TOKEN） |
| `publish-twitter.yml` | 手动，需 `release_tag` + `PUBLISH` | 发布 Twitter 摘要 | TWITTER_ACCESS_TOKEN |
| `publish-reddit.yml` | 手动，需 `release_tag` + `PUBLISH` | 发布 Reddit 帖子 | REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD |
| `publish-devto.yml` | 手动，需 `release_tag` + `PUBLISH` | 发布 Dev.to 文章 | DEVTO_API_KEY |
| `community-notify.yml` | 手动，需 `release_tag` + `PUBLISH` | Discord/Slack Release 通知 | DISCORD_WEBHOOK_URL, SLACK_WEBHOOK_URL（至少一个） |
| `weekly-report.yml` | 每周一 UTC 0:00 | 收集指标、生成周报、发送通知 | DISCORD_WEBHOOK_URL, SLACK_WEBHOOK_URL（可选） |

### 工作流依赖关系

```
Release Prep PR + External Publication Safety PR
        ↓
main CI 全部通过
        ↓
人工在已验证的 main SHA 创建 annotated tag
        ↓
人工确认后 push tag
        ↓
release.yml：verify → backend/frontend/docker → package → GitHub Release
        ↓
可选：人工选择已公开的 release tag，并精确输入 PUBLISH
        ↓
单独手动运行 Twitter / Reddit / Dev.to / community workflow

weekly-report.yml（独立定时任务）
```

`release.yml` 不创建或移动 tag，也不直接调用外部宣传工作流。Twitter、Reddit、
Dev.to 和社区通知均为手动工作流，不监听 Release 发布事件、不选择 latest Release，
且只接受已存在、已公开、非 prerelease 的精确 tag。

---

## GitHub Secrets 配置

### 配置步骤

1. 打开 GitHub 仓库：https://github.com/KevinYoungsir/autowealth-ai
2. 进入 **Settings** > **Secrets and variables** > **Actions**
3. 点击 **New repository secret**
4. 按照下面的指南填入对应的 Secret 名称和值

### Secrets 清单

#### 必需 Secrets（用于社交媒体发布）

| Secret 名称 | 说明 | 获取方式 |
|------------|------|---------|
| `TWITTER_ACCESS_TOKEN` | 具备发帖权限的 OAuth 2.0 用户 Access Token | [Twitter Developer Portal](https://developer.twitter.com/) |
| `REDDIT_CLIENT_ID` | Reddit App Client ID | [Reddit Preferences > Apps](https://www.reddit.com/prefs/apps) |
| `REDDIT_CLIENT_SECRET` | Reddit App Client Secret | 同上 |
| `REDDIT_USERNAME` | Reddit 用户名 | 你的 Reddit 用户名 |
| `REDDIT_PASSWORD` | Reddit 用户密码 | 你的 Reddit 密码 |
| `DEVTO_API_KEY` | Dev.to API Key | [Dev.to Settings > Account](https://dev.to/settings/account) |

#### 可选 Secrets（用于通知）

| Secret 名称 | 说明 | 获取方式 |
|------------|------|---------|
| `DISCORD_WEBHOOK_URL` | Discord 频道 Webhook URL | Discord 频道设置 > 整合 > Webhook |
| `SLACK_WEBHOOK_URL` | Slack 频道 Webhook URL | Slack App 设置 > Incoming Webhooks |
> **注意**：v0.16.0 的核心 Release Workflow 不读取 PyPI Token，也不上传 PyPI。
> 外部宣传与通知工作流的 Secret 和失败策略必须在独立安全 PR 中审查。

---

## 各平台 API 密钥获取指南

### 1. Twitter API

1. 访问 [Twitter Developer Portal](https://developer.twitter.com/)
2. 创建一个 Developer Account（如果还没有）
3. 创建一个新 App（Project > Apps > Create App）
4. 配置 OAuth 2.0 用户认证，并授予发帖所需的写权限。
5. 生成用户 Access Token，保存为 `TWITTER_ACCESS_TOKEN`。

> **重要**：该 Token 必须具有用户上下文和发帖权限；应用级只读 Bearer Token
> 无法用于发布推文。

### 2. Reddit API

1. 登录 [Reddit](https://www.reddit.com/)
2. 进入 [应用偏好设置](https://www.reddit.com/prefs/apps)
3. 滚动到底部，点击 **create another app...**
4. 填写信息：
   - **name**: `autowealth-ai-bot`（自定义）
   - **type**: 选择 **script**
   - **redirect uri**: `http://localhost:8080`
5. 创建后获取：
   - **client_id**: App 名称下方的字符串 → `REDDIT_CLIENT_ID`
   - **client_secret**: 标记为 secret 的字符串 → `REDDIT_CLIENT_SECRET`
6. 你的 Reddit 用户名和密码分别填入 `REDDIT_USERNAME` 和 `REDDIT_PASSWORD`

> **注意**：Reddit API 有速率限制（60 次/分钟）。工作流已在每次请求间添加了 5 秒延迟。

### 3. Dev.to API

1. 登录 [Dev.to](https://dev.to/)
2. 进入 [Settings > Account](https://dev.to/settings/account)
3. 找到 **DEV Community API Keys** 部分
4. 点击 **Generate new API key**
5. 复制生成的 API Key → `DEVTO_API_KEY`

### 4. Discord Webhook

1. 打开 Discord 服务器
2. 进入目标频道的设置（齿轮图标）
3. 选择 **整合** (Integrations) > **Webhook**
4. 点击 **新建 Webhook**
5. 设置名称（如 "AutoWealth AI Bot"）
6. 选择频道
7. 复制 Webhook URL → `DISCORD_WEBHOOK_URL`

### 5. Slack Webhook

1. 访问 [Slack API](https://api.slack.com/apps)
2. 创建一个新的 Slack App
3. 启用 **Incoming Webhooks**
4. 创建 Webhook 并选择目标频道
5. 复制 Webhook URL → `SLACK_WEBHOOK_URL`

### 6. PyPI 发布状态

v0.16.0 默认关闭 PyPI 发布。`release.yml` 不读取 `PYPI_API_TOKEN`，也不执行
`twine upload`。未来启用前必须通过独立安全审查，明确凭据、审批、回滚和包名
所有权。

---

## 工作流详细说明

### release.yml - 失败关闭的核心发布

**触发条件**：人工推送严格 `vMAJOR.MINOR.PATCH` annotated tag。工作流不创建 tag，
也不响应 `main` push 自动发布。

**执行流程**：
1. 验证严格 tag、产品版本、精确 CHANGELOG heading，并要求 tag commit 等于
   `origin/main` HEAD。
2. 安装 `.[dev,api]`，执行 Black、compileall 和完整离线 pytest。
3. 执行前端 `npm ci`、production audit、测试、typecheck 和 build。
4. 构建 `Dockerfile.api`，但不推送镜像。
5. 清空 `dist`，构建并严格校验唯一 wheel 与 sdist，生成 `SHA256SUMS.txt`。
6. 严格提取当前版本 CHANGELOG 段；不存在时失败，不回退旧版本。
7. 创建或恢复 draft Release，仅上传三个预期资产；验证完成后才公开。

完整人工发布顺序见 `docs/release-process.md`。v0.16.0 不上传 PyPI。

### publish-twitter.yml - 手动发 Twitter

**触发条件**：手动运行，输入已公开 Release 的精确 `release_tag`，并精确输入
`PUBLISH`。正文从 GitHub Release JSON 安全生成，不写入或执行 shell 环境文件。

**推文模板**：
```
🚀 AutoWealth AI v{version} is out!

✅ Multi-agent investment analysis engine
✅ ML predictions (Random Forest + MLP)
✅ Real-time alerts system
✅ Social sentiment analysis
✅ Flutter mobile app
✅ Backtesting & portfolio optimization

Open-source & free. Check it out 👇
{GitHub Release URL}

#Python #AI #AlgoTrading #OpenSource
```

### publish-reddit.yml - 手动发 Reddit

**触发条件**：手动 `release_tag` + `PUBLISH`；仅接受已公开、非 prerelease 的
GitHub Release。

**目标 Subreddits**：
- `r/Python` - 标题侧重 Python 开发者视角
- `r/algotrading` - 标题侧重量化交易功能
- `r/opensource` - 标题侧重开源项目介绍

**帖子内容**：通过 `jq` 将 Release body、Release URL 和权威仓库地址作为数据写入
临时正文文件，不执行正文内容。

### publish-devto.yml - 手动发布 Dev.to

**触发条件**：手动 `release_tag` + `PUBLISH`；不由 GitHub Release 自动触发。

**文章内容**：使用 `jq` 从 Release JSON 构建 API payload。Release body 始终作为
JSON 数据处理。

### community-notify.yml - 社区通知

**触发条件**：仅手动 `release_tag` + `PUBLISH`。Release 发布和 Star 事件均不会
自动发送外部 webhook。

**通知渠道**：Discord 和/或 Slack（至少配置一个）。

### 人工创建正式 Tag

仓库不存在自动 tag 工作流。Release Prep 合并到 `main` 不会自动创建 tag，也不会自动
发布。发布负责人必须在所有 CI 和发布前检查通过后，于已验证的 `main` SHA 上执行：

```bash
git tag -a v0.16.0 -m "AutoWealth v0.16.0"
git show v0.16.0
git status --short
git push origin v0.16.0
```

`git push origin v0.16.0` 是显式发布操作，必须另行获得授权。正式 tag 不得删除、
移动、复用或强制覆盖；失败后修复代码并发布新的补丁版本。

### weekly-report.yml - 每周自动报告

**触发条件**：每周一 UTC 0:00（北京时间周一 8:00），也支持手动触发

**报告内容**：
- Star/Fork 增量统计
- Issue/PR 开启和关闭统计
- 里程碑进度
- 数据亮点

**输出渠道**：
- Discord/Slack 通知（可选）
- GitHub Issue 存档（标签：`weekly-report`, `automated`）

---

## 故障排除

### 常见问题

#### 1. Twitter 推文发布失败 (403 Forbidden)

**原因**：Twitter App 权限不足。

**解决方案**：
- 进入 Twitter Developer Portal > 你的 App > User authentication settings
- 将 App permissions 改为 **Read and Write**
- 重新生成 Access Token 和 Secret
- 更新 GitHub Secrets

#### 2. Reddit 帖子发布失败 (429 Too Many Requests)

**原因**：Reddit API 速率限制。

**解决方案**：
- 工作流已在每次请求间添加了 5 秒延迟
- 如果仍然触发限制，可以增加 `time.sleep()` 的值
- Reddit 限制：60 次/分钟

#### 3. Dev.to 文章发布失败 (401 Unauthorized)

**原因**：API Key 无效或过期。

**解决方案**：
- 重新生成 Dev.to API Key
- 确认 Key 没有多余的空格或换行符
- 更新 GitHub Secret

#### 4. 推送 Tag 后 Release 未触发

**可能原因**：
- tag 不符合严格 `vMAJOR.MINOR.PATCH` 格式；
- tag 没有推送到 `origin`；
- tag commit 不等于 workflow 验证时的 `origin/main` HEAD；
- 产品版本、tag 或 CHANGELOG heading 不一致。

**排查步骤**：
```bash
git show v0.16.0
git branch -r --contains v0.16.0
python scripts/verify_release_metadata.py --expected-version 0.16.0 --tag v0.16.0
```

不要通过删除、移动或重推同名正式 tag 处理失败。

#### 5. weekly-report.yml 未执行

**可能原因**：
- 仓库在触发时间点没有新的 commit（GitHub 不活跃的仓库会暂停 cron）
- 时区理解错误（cron 使用 UTC 时间）

**解决方案**：
- 手动触发：Actions > Weekly Report > Run workflow
- 确认仓库有近期活动

#### 6. Release Notes 为空

**原因**：CHANGELOG.md 中的版本号格式不匹配。

**解决方案**：
- 确保 CHANGELOG.md 中的版本号格式为 `## [x.x.x] - YYYY-MM-DD`
- 确保 tag 中的版本号与 CHANGELOG.md 一致

#### 7. 社区通知未发送

**可能原因**：
- Webhook URL 未配置
- 未提供已公开的精确 Release tag
- confirmation 未精确输入 `PUBLISH`

**解决方案**：
- 检查 GitHub Secrets 中是否配置了 `DISCORD_WEBHOOK_URL` 或 `SLACK_WEBHOOK_URL`
- 手动触发：Actions > Community Notify > Run workflow

### 调试技巧

1. **查看工作流日志**：GitHub 仓库 > Actions > 选择对应的工作流运行 > 展开各步骤查看日志

2. **本地测试 Python 脚本**：将工作流中的 Python 脚本提取出来，在本地设置环境变量后运行

3. **核对触发条件**：核心 Release 只响应正式 tag push，不提供自动 tag 或
   `main` push 发布入口。

4. **检查 API 配额**：各平台 API 都有调用频率限制，频繁触发可能导致临时封禁

---

## 安全注意事项

1. **永远不要将 API 密钥提交到代码仓库中**，始终使用 GitHub Secrets
2. **定期轮换 API 密钥**，建议每 90 天更新一次
3. **使用最小权限原则**：例如 Twitter App 只需要 Read and Write 权限
4. **监控工作流执行日志**：确保没有敏感信息泄露到日志中
5. **Reddit 密码安全**：考虑使用专用的 Reddit 账号用于自动发布

---

## 扩展建议

- **添加更多发布渠道**：可以参考现有工作流的结构，添加 Hacker News、Product Hunt 等平台的自动发布
- **国际化支持**：为不同语言社区（中文、日文等）创建定制化的发布内容
- **A/B 测试**：为不同 Subreddit 准备不同的帖子标题和内容，对比效果
- **发布时间优化**：根据目标受众的活跃时间，调整自动发布的触发时间
