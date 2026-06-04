# 安全策略 | Security Policy

> AutoWealth AI 重视安全。如果您发现安全漏洞，请按照以下流程报告。
>
> AutoWealth AI takes security seriously. If you discover a security vulnerability, please report it following the process below.

---

## 支持的版本 | Supported Versions

| 版本 | 支持状态 |
|------|---------|
| [main 分支](https://github.com/Jsoned/autowealth-ai/tree/main) | 积极维护，接收安全更新 |
| v0.4.x | 安全更新（仅关键修复） |
| v0.3.x | 安全更新（仅关键修复） |
| < v0.3.0 | 不再维护 |

---

## 报告安全漏洞 | Reporting a Vulnerability

### 报告流程 | Reporting Process

1. **不要公开披露** -- 请勿在 GitHub Issues、Discussions 或其他公开渠道报告安全漏洞，以免被恶意利用。

   **Do not publicly disclose** -- Please do not report security vulnerabilities through GitHub Issues, Discussions, or any other public channels to prevent potential exploitation.

2. **通过邮件报告** -- 请发送邮件至项目维护团队，包含以下信息：

   **Report via email** -- Send an email to the project maintainers with the following information:

   - 漏洞描述 | Vulnerability description
   - 受影响的组件/模块 | Affected component/module
   - 复现步骤 | Steps to reproduce
   - 潜在影响 | Potential impact
   - 建议的修复方案（可选） | Suggested fix (optional)

3. **确认收到** -- 我们将在 **48 小时内**确认收到您的报告，并在 **7 个工作日内**提供初步评估。

   **Acknowledgment** -- We will acknowledge your report within **48 hours** and provide an initial assessment within **7 business days**.

4. **修复与披露** -- 修复完成后，我们将在发布安全补丁的同时公开致谢您的贡献（除非您要求匿名）。

   **Fix & Disclosure** -- Once the fix is complete, we will publish the security patch and publicly acknowledge your contribution (unless you prefer to remain anonymous).

### 联系方式 | Contact

- **Email**: `autowealth.security@gmail.com`
- **GitHub Security** (推荐): 使用 [GitHub Security Advisories](https://github.com/Jsoned/autowealth-ai/security/advisories/new) 提交报告

---

## 安全最佳实践 | Security Best Practices

### API 密钥管理 | API Key Management

- 切勿将 API 密钥硬编码在源代码中
- 使用 `.env` 文件管理环境变量（已在 `.gitignore` 中排除）
- 定期轮换 API 密钥

```bash
# 正确做法 | Correct
OPENAI_API_KEY=sk-xxx  # 存放在 .env 文件中

# 错误做法 | Wrong
api_key = "sk-xxx"  # 不要硬编码在代码中
```

### 本地部署安全 | Local Deployment Security

- 使用本地 LLM 时，确保 Ollama 或其他服务仅监听 localhost
- 在生产环境中使用反向代理（如 Nginx）配置 HTTPS
- 不要将服务直接暴露在公网

### 数据安全 | Data Security

- 本地缓存数据存储在 `./data/cache` 目录，定期清理
- 不要将缓存数据提交到版本控制
- 使用 Docker 部署时，确保数据卷权限正确配置

---

## 安全更新通知 | Security Update Notifications

安全更新将通过以下渠道通知：

Security updates will be notified through the following channels:

- [GitHub Security Advisories](https://github.com/Jsoned/autowealth-ai/security/advisories)
- [GitHub Releases](https://github.com/Jsoned/autowealth-ai/releases)

建议 Watch 本仓库以获取最新的安全更新通知。

We recommend watching this repository to receive the latest security update notifications.

---

## 致谢 | Acknowledgments

我们感谢所有负责任地报告安全漏洞的安全研究人员。

We thank all security researchers who responsibly disclose vulnerabilities.

如果您发现并报告了一个安全漏洞，您将获得：

If you discover and report a security vulnerability, you will receive:

- 在安全公告中的公开致谢
- 在项目贡献者列表中的署名
