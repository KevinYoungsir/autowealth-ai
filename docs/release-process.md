# AutoWealth 发布流程

## 1. 范围与原则

本文定义 AutoWealth 正式产品版本的人工发布流程。发布系统只负责校验代码、构建
制品和创建 GitHub Release，不改变研究数据、历史 artifacts、API/schema 契约或
生产部署。发布授权与 Git 操作授权必须显式给出。

核心原则：

- `pyproject.toml` 的 `project.version` 是产品版本权威来源。
- tag 必须由人工在已验证的 `main` SHA 上创建。
- 正式 tag 必须是 annotated tag，且严格符合 `vMAJOR.MINOR.PATCH`。
- 测试、前端、Docker、Python 包和 Release Notes 全部通过后才创建 Release。
- 正式 tag 不得删除、移动、复用或强制覆盖。
- v0.16.0 默认不发布 PyPI，也不自动执行外部宣传。

`scripts/verify_release_metadata.py` 要求 Python 3.11 或更高版本，因为它使用
Python 标准库中的 `tomllib`。本地发布检查、CI 和 Release runner 都必须使用
Python 3.11+。

## 2. 发布前 PR

### Release Prep PR

Release Prep PR 只处理产品版本、CHANGELOG、发布校验器、核心 CI/Release Workflow
和发布文档。它不得混入研究业务逻辑、契约版本或部署行为变更。

合并前至少确认：

```powershell
python scripts/verify_release_metadata.py --expected-version 0.16.0
python -m pytest tests/test_release_metadata.py -q -p no:cacheprovider
python -m compileall -q autowealth tests scripts
git diff --check
```

CI 的 backend、frontend 和 docker job 必须全部成功。

### External Publication Safety PR

Twitter、Reddit、Dev.to 和社区通知属于独立发布边界。正式 tag 创建前，必须单独
完成 External Publication Safety PR，确认这些工作流默认关闭或受明确人工审批
保护。本 Release Prep PR 不修改或调用它们。

## 3. Main 校验

Release Prep PR 与 External Publication Safety PR 合并后，在 `main` 上确认：

1. 工作区干净且 `origin` 正确。
2. 本地 `main` 与准备发布的远程 SHA 一致。
3. `main` CI 全部成功。
4. 产品版本、CHANGELOG 和前后端版本一致。
5. `## [0.16.0] - 2026-07-28` 精确存在。
6. Python wheel、sdist、前端 build 和 Docker build 均可完成。
7. 没有正在等待的发布阻断问题。

产品版本检查：

```powershell
python scripts/verify_release_metadata.py --expected-version 0.16.0
```

校验失败必须修复并重新走 PR/CI，不得跳过，也不得回退到旧 CHANGELOG 段。

## 4. 创建 Annotated Tag

只有获得明确发布授权后，发布负责人才能在已验证的 `main` SHA 上创建 tag：

```powershell
git branch --show-current
git status --short
git rev-parse HEAD
git remote get-url origin
git tag -a v0.16.0 -m "AutoWealth v0.16.0"
git show v0.16.0
```

创建本地 tag 后先暂停并再次确认：

- tag 指向预期 `main` SHA；
- tag 内容是 annotated tag；
- tag 和产品版本均为 `0.16.0`；
- CHANGELOG heading 和日期正确；
- 没有同名远程正式 tag；
- 已获得 push tag 的明确授权。

确认后才执行：

```powershell
git push origin v0.16.0
```

`main` push 和 CHANGELOG 变更不会自动创建 tag。`release.yml` 也不会创建 tag。

## 5. Release Workflow

正式 tag push 依次触发以下阶段：

1. `verify`：严格校验 tag、产品版本、CHANGELOG 和 `origin/main` 祖先关系。
2. `backend`：Black、compileall、版本校验和完整离线 pytest。
3. `frontend`：`npm ci`、测试、typecheck 和 build。
4. `docker`：构建 `Dockerfile.api`，不推送镜像。
5. `package`：构建 wheel/sdist，执行 `twine check` 和制品版本校验。
6. `release`：重新校验制品并严格提取当前版本说明，最后创建 GitHub Release。

任何阶段失败都会阻止后续 Release 创建。Release Notes 只来自精确的当前版本
CHANGELOG 区域；缺少 heading 时直接失败，不使用 0.15.1 或其他版本替代。

最终命令使用：

```text
gh release create <tag> --verify-tag
```

并上传已经校验的 wheel 和 sdist。创建 GitHub Release 是工作流最后一个写操作。

## 6. 发布失败

### Tag 尚未推送

修复问题并重新执行发布前门禁。若本地 tag 指向错误，可在未推送且获得批准后删除
本地 tag 并重新创建；不得影响任何远程正式 tag。

### Tag 已推送但 Release 未创建

保留 tag，不删除、不移动、不覆盖。修复代码后发布新的补丁版本，例如
`v0.16.1`。不得直接重推 `v0.16.0`。

### Release 已创建但部署或功能异常

回滚部署到上一稳定构建，但不移动 tag、不重写 Release artifact、不修改历史研究
artifacts。修复通过新 PR 和新补丁版本发布。

## 7. 默认关闭项

- PyPI：v0.16.0 不读取 Token，不执行 `twine upload`。
- 外部宣传：默认关闭，必须由独立安全 PR 和人工审批处理。
- 镜像发布：只验证 Docker build，不 push registry。
- 生产部署：Release Workflow 不触发 Railway、Vercel 或其他部署。
- 真实数据、DeepSeek 和交易：发布门禁不访问或调用这些能力。

## 8. 兼容性与已知限制

发布准备不修改研究计算、provider 顺序、fallback、cache、warning、`run_status`、
metrics、curves、API 响应或任何 artifact/schema/API contract version。

GitHub Release 发布事件可能被仓库中已有的外部宣传工作流监听，因此正式 tag
必须等待 External Publication Safety PR 完成。该依赖是 v0.16.0 发布前的人工
阻断条件，不能通过核心 Release Workflow 静默绕过。
