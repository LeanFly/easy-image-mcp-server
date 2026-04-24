# 基础镜像使用 Python 3.10（可替换为其他版本）
FROM python:3.10.20

# 设置工作目录
WORKDIR /app

# 安装系统依赖（比如 curl 和 ca-certificates 用于 HTTPS 请求）
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 安装 pip 依赖（mcp、fastapi、uvicorn、requests、python-multipart）
RUN pip install --no-cache-dir \
    mcp \
    fastapi \
    uvicorn \
    requests \
    python-multipart \
    && rm -rf /tmp/pip缓存

# 将当前目录下的 Python 脚本复制到镜像中
COPY easy_image_mcp_server.py /app/easy_image_mcp_server.py

# 设置环境变量（可选，仅用于构建时或运行时帮助）
ENV MCP_SERVER_NAME=easy-image-mcp \
    HOST=127.0.0.1 \
    PORT=8000

# 处理 Python 脚本运行
CMD ["python", "/app/easy_image_mcp_server.py"]
