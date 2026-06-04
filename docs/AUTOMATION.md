# AutoWealth AI - 自动化配置指南

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
| `release.yml` | 推送 `v*` tag | 运行测试、创建 Release、构建上传 Python 包 | 无（使用 GITHUB_TOKEN） |
| `publish-twitter.yml` | 新 Release 发布 | 自动发 Twitter 推文 | TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET |
| `publish-reddit.yml` | 新 Release 发布 | 自动发 Reddit 帖子 | REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD |
| `publish-devto.yml` | 新 Release 发布 | 自动交叉发布 Dev.to 文章 | DEVTO_API_KEY |
| `community-notify.yml` | Star 里程碑 / 新 Release | Discord/Slack 社区通知 | DISCORD_WEBHOOK_URL, SLACK_WEBHOOK_URL（可选） |
| `auto-tag.yml` | main 分支 CHANGELOG.md 变更 | 自动从 CHANGELOG 提取版本号并创建 tag | 无（使用 GITHUB_TOKEN） |
| `weekly-report.yml` | 每周一 UTC 0:00 | 收集指标、生成周报、发送通知 | DISCORD_WEBHOOK_URL, SLACK_WEBHOOK_URL（可选） |

### 工作流依赖关系

```
CHANGELOG.md 更新 → push 到 main
        ↓
  auto-tag.yml（自动创建 tag）
        ↓
  release.yml（推送 tag 触发）
        ↓
  ┌─── publish-twitter.yml ───┐
  ├─── publish-reddit.yml  ────┤
  ├─── publish-devto.yml   ────┤（并行执行）
  └─── community-notify.yml ──┘

weekly-report.yml（独立定时任务）
community-notify.yml（Star 里程碑独立触发）
```

---

## GitHub Secrets 配置

### 配置步骤

1. 打开 GitHub 仓库：https://github.com/Jsoned/autowealth-ai
2. 进入 **Settings** > **Secrets and variables** > **Actions**
3. 点击 **New repository secret**
4. 按照下面的指南填入对应的 Secret 名称和值

### Secrets 清单

#### 必需 Secrets（用于社交媒体发布）

| Secret 名称 | 说明 | 获取方式 |
|------------|------|---------|
| `TWITTER_API_KEY` | Twitter API Key (Consumer Key) | [Twitter Developer Portal](https://developer.twitter.com/) |
| `TWITTER_API_SECRET` | Twitter API Secret (Consumer Secret) | 同上 |
| `TWITTER_ACCESS_TOKEN` | Twitter Access Token | 同上 |
| `TWITTER_ACCESS_SECRET` | Twitter Access Token Secret | 同上 |
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
| `PYPI_API_TOKEN` | PyPI 发布 Token（可选） | [PyPI Account Settings](https://pypi.org/manage/account/token/) |

> **注意**：如果不配置某个平台的 Secrets，对应的工作流步骤会自动跳过或报错提示，不会影响其他工作流的执行。

---

## 各平台 API 密钥获取指南

### 1. Twitter API

1. 访问 [Twitter Developer Portal](https://developer.twitter.com/)
2. 创建一个 Developer Account（如果还没有）
3. 创建一个新 App（Project > Apps > Create App）
4. 在 App 设置中启用 **OAuth 1.0a**
5. 生成以下凭据：
   - **API Key** (Consumer Key) → `TWITTER_API_KEY`
   - **API Key Secret** (Consumer Secret) → `TWITTER_API_SECRET`
6. 创建 Access Token 和 Secret：
   - 进入 App 的 **Keys and Tokens** 页面
   - 在 "Authentication Tokens" 下点击 **Generate**
   - **Access Token** → `TWITTER_ACCESS_TOKEN`
   - **Access Token Secret** → `TWITTER_ACCESS_SECRET`

> **重要**：确保 App 的权限设置为 **Read and Write**，否则无法发布推文。

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

### 6. PyPI Token（可选）

1. 登录 [PyPI](https://pypi.org/)
2. 进入 [Account Settings](https://pypi.org/manage/account/)
3. 滚动到 **API tokens** 部分
4. 点击 **Add API token**
5. 复制 Token → `PYPI_API_TOKEN`

---

## 工作流详细说明

### release.yml - 自动发布 Release

**触发条件**：推送 `v*` 格式的 git tag

**执行流程**：
1. 在 Python 3.9/3.10/3.11/3.12 上运行全部测试
2. 运行 flake8 代码检查和 black 格式检查
3. 从 `CHANGELOG.md` 提取当前版本的更新内容作为 Release Notes
4. 创建 GitHub Release（如果版本号包含 rc/beta/alpha 则标记为预发布）
5. 构建 Python 包（sdist + wheel）
6. 上传包到 GitHub Release
7. 可选：发布到 PyPI

**使用方式**：
```bash
# 更新 CHANGELOG.md 后，创建并推送 tag
git tag v0.5.0
git push origin v0.5.0
```

### publish-twitter.yml - 自动发 Twitter

**触发条件**：GitHub Release 正式发布时（排除 draft 和 prerelease）

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

### publish-reddit.yml - 自动发 Reddit

**触发条件**：GitHub Release 正式发布时

**目标 Subreddits**：
- `r/Python` - 标题侧重 Python 开发者视角
- `r/algotrading` - 标题侧重量化交易功能
- `r/opensource` - 标题侧重开源项目介绍

**帖子内容**：从 `docs/marketing/reddit_post.md` 读取模板，动态替换版本号和链接。

### publish-devto.yml - 自动交叉发布 Dev.to

**触发条件**：GitHub Release 正式发布时

**文章内容**：参考 `docs/marketing/juejin_post.md` 的结构，生成英文版技术文章，包含项目架构、功能介绍、版本更新等。

### community-notify.yml - 社区通知

**触发条件**：
- Star 数达到里程碑（100/500/1000/5000/10000）
- 新 Release 发布
- 手动触发（workflow_dispatch）

**通知渠道**：Discord 和/或 Slack（至少配置一个）

### auto-tag.yml - 自动打 Tag

**触发条件**：push 到 `main` 分支且 `CHANGELOG.md` 有变更

**执行流程**：
1. 从 `CHANGELOG.md` 提取最新版本号（`## [x.x.x]` 格式）
2. 检查 tag 是否已存在
3. 如果不存在，创建带注释的 git tag
4. 推送 tag 到远程仓库，自动触发 `release.yml`

**使用方式**：
```bash
# 只需更新 CHANGELOG.md 并推送到 main 分支
# 工作流会自动创建 tag 并触发发布流程
vim CHANGELOG.md
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for v0.5.0"
git push origin main
# auto-tag.yml 自动执行 → 创建 tag → release.yml 自动执行
```

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

#### 4. auto-tag.yml 未触发

**可能原因**：
- CHANGELOG.md 没有实际变更
- Tag 已存在
- push 的不是 `main` 分支

**排查步骤**：
```bash
# 检查 CHANGELOG.md 是否有变更
git diff HEAD~1 HEAD -- CHANGELOG.md

# 检查 tag 是否已存在
git tag -l v0.5.0
```

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
- Star 数未精确达到里程碑值

**解决方案**：
- 检查 GitHub Secrets 中是否配置了 `DISCORD_WEBHOOK_URL` 或 `SLACK_WEBHOOK_URL`
- 手动触发测试：Actions > Community Notify > Run workflow

### 调试技巧

1. **查看工作流日志**：GitHub 仓库 > Actions > 选择对应的工作流运行 > 展开各步骤查看日志

2. **本地测试 Python 脚本**：将工作流中的 Python 脚本提取出来，在本地设置环境变量后运行

3. **使用 workflow_dispatch**：所有工作流都支持手动触发，可以在 GitHub Actions 页面手动运行测试

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
