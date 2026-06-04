FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY . .

# 安装Python依赖
RUN pip install --no-cache-dir -e ".[app,api]"

# 暴露端口
EXPOSE 8501 8000

# 默认运行Streamlit
CMD ["streamlit", "run", "examples/app.py", "--server.address=0.0.0.0"]
