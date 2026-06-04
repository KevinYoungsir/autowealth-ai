# 安装指南

## 系统要求

- Python 3.9+
- pip 包管理器
- Git

## 安装步骤

### 1. 克隆仓库

```bash
git clone https://github.com/Jsoned/autowealth-ai.git
cd autowealth-ai
```

### 2. 创建虚拟环境（推荐）

```bash
python -m venv venv

# Windows
.\venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. 安装依赖

```bash
# 基础安装
pip install -e .

# 包含开发依赖
pip install -e ".[dev]"

# 包含应用界面
pip install -e ".[app]"

# 包含API服务
pip install -e ".[api]"
```

### 4. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入您的API密钥：

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
```

### 5. 验证安装

```bash
python -m autowealth --help
```

## 常见问题

### Q: 安装失败怎么办？

A: 确保您的Python版本 >= 3.9，并尝试：
```bash
pip install --upgrade pip
pip install -e . --no-cache-dir
```

### Q: 需要GPU吗？

A: 不需要。AutoWealth AI 主要使用CPU进行计算。如果使用本地LLM，GPU可以加速但不是必需的。

### Q: 支持哪些操作系统？

A: 支持 Windows、macOS 和 Linux。

## 下一步

查看 [使用教程](Tutorial) 了解如何使用 AutoWealth AI。
