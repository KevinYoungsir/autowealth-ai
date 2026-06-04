# 🤝 贡献指南

感谢您对 AutoWealth AI 的兴趣！我们欢迎各种形式的贡献。

## 🚀 如何贡献

### 报告问题

如果您发现了bug或有功能建议，请通过 [GitHub Issues](https://github.com/Jsoned/autowealth-ai/issues) 提交。

提交问题时，请包含：
- 问题的详细描述
- 复现步骤
- 期望行为 vs 实际行为
- 环境信息（Python版本、操作系统等）
- 相关代码片段或错误日志

### 提交代码

1. **Fork 仓库**
   ```bash
   git clone https://github.com/Jsoned/autowealth-ai.git
   cd autowealth-ai
   ```

2. **创建分支**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **安装开发依赖**
   ```bash
   pip install -e ".[dev]"
   ```

4. **编写代码**
   - 遵循 PEP 8 编码规范
   - 添加必要的注释和文档
   - 确保代码通过所有测试

5. **运行测试**
   ```bash
   pytest tests/ -v
   black autowealth/
   flake8 autowealth/
   ```

6. **提交更改**
   ```bash
   git add .
   git commit -m "feat: 添加新功能描述"
   git push origin feature/your-feature-name
   ```

7. **创建 Pull Request**
   - 描述您的更改
   - 关联相关 Issue
   - 等待审核

## 📝 提交信息规范

我们使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

- `feat:` 新功能
- `fix:` 修复bug
- `docs:` 文档更新
- `style:` 代码格式调整
- `refactor:` 代码重构
- `test:` 测试相关
- `chore:` 构建/工具相关

示例：
```
feat: 添加RSI指标分析功能

- 实现RSI计算方法
- 添加超买超卖判断逻辑
- 更新文档
```

## 🎯 开发路线图

### 短期目标
- [ ] 添加更多技术指标（OBV、ATR、DMI等）
- [ ] 支持更多数据源
- [ ] 完善测试覆盖率

### 中期目标
- [ ] 添加回测系统
- [ ] 支持加密货币分析
- [ ] 开发Web API服务

### 长期目标
- [ ] 机器学习模型集成
- [ ] 实时数据流处理
- [ ] 移动端应用

## 💡 贡献者福利

- 在 README 中致谢贡献者
- 为活跃贡献者提供 Collaborator 权限
- 定期发布贡献者榜单

## 📞 联系我们

- GitHub Issues: [提交问题](https://github.com/Jsoned/autowealth-ai/issues)
- Discussions: [参与讨论](https://github.com/Jsoned/autowealth-ai/discussions)

再次感谢您的贡献！🙏
