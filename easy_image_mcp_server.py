"""
Easy Image MCP Server
=====================
使用 Streamable HTTP 传输模式，支持通过 Headers 传入 Token 配置。

MCP 客户端配置示例：
{
  "mcpServers": {
    "easy-image": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "X-Easy-Image-Token": "your_token_here",
        "X-Easy-Image-Api-Url": "http://your-domain.com/api/index.php"
      }
    }
  }
}
"""

import os
import requests
import uvicorn
from contextvars import ContextVar
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

# ============================================================
# 配置区（默认值，可被 Headers 覆盖）
# ============================================================
DEFAULT_API_URL = "http://127.0.0.1/api/index.php"
DEFAULT_TOKEN   = ""
MCP_SERVER_NAME = "easy-image-mcp"
HOST            = "0.0.0.0"
PORT            = 8000

# ============================================================
# 上下文变量：存储当前请求的 Headers 配置
# ============================================================
current_token: ContextVar[str]   = ContextVar("current_token", default="")
current_api_url: ContextVar[str] = ContextVar("current_api_url", default=DEFAULT_API_URL)

# ============================================================
# 创建 MCP Server 实例
# ============================================================
mcp_server = Server(MCP_SERVER_NAME)


# ============================================================
# 注册工具列表
# ============================================================
@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="upload_image",
            description=(
                "上传图片到 Easy Image 图床服务器，"
                "支持传入本地文件路径或网络图片 URL。"
                "返回图片访问链接及上传状态信息。"
                "Token 和 API URL 已通过 Headers 预配置，调用时可选覆盖。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "（二选一）本地图片文件的绝对路径"
                    },
                     "image_url": {
                        "type": "string",
                        "description": "（二选一）图片的网络 URL 地址，程序将自动下载并上传"
                    },
                    "token": {
                        "type": "string",
                        "description": "（可选）覆盖 Headers 中预配置的 Token"
                    },
                    "api_url": {
                        "type": "string",
                        "description": "（可选）覆盖 Headers 中预配置的 API 地址"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="check_config",
            description="检查当前 Easy Image 服务配置状态（Token 和 API URL 是否已配置）",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


# ============================================================
# 工具实现
# ============================================================
@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent]:
    
    # -------------------- check_config --------------------
    if name == "check_config":
        token   = current_token.get()
        api_url = current_api_url.get()
        
        token_status   = "✅ 已配置" if token else "❌ 未配置"
        api_url_status = api_url or "❌ 未配置"
        
        return [TextContent(
            type="text",
            text=(
                f"📋 Easy Image 配置状态\n"
                f"{'─' * 30}\n"
                f"🔑 Token: {token_status}\n"
                f"🌐 API URL: {api_url_status}\n"
                f"{'─' * 30}\n"
                f"💡 配置方式：在 MCP 客户端 Headers 中设置\n"
                f"   X-Easy-Image-Token: your_token\n"
                f"   X-Easy-Image-Api-Url: http://your-domain/api/index.php"
            )
        )]
    
    # -------------------- upload_image --------------------
    if name == "upload_image":
        image_path = arguments.get("image_path", "").strip()
        image_url  = arguments.get("image_url", "").strip()
        # 优先使用参数，fallback 到 Headers 配置
        token   = arguments.get("token", "").strip() or current_token.get()
        api_url = arguments.get("api_url", "").strip() or current_api_url.get()

        # ---------- 参数校验 ----------
        if not image_path and not image_url:
            return [TextContent(type="text", text="❌ 错误：必须提供 image_path 或 image_url 其中之一")]
        
        if not token:
            return [TextContent(
                type="text",
                text=(
                    "❌ 错误：Token 未配置\n\n"
                    "请在 MCP 客户端配置 Headers：\n"
                    '  "headers": {\n'
                    '    "X-Easy-Image-Token": "your_token_here"\n'
                    '  }'
                )
            )]
        
        if not api_url:
            return [TextContent(type="text", text="❌ 错误：API URL 未配置")]

        # ---------- 文件校验 ----------
        # 模式 A: 本地文件
        if image_path:
            if not os.path.isfile(image_path):
                return [TextContent(type="text", text=f"❌ 错误：文件不存在 → {image_path}")]
            
            ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
            ext = os.path.splitext(image_path)[-1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                return [TextContent(type="text", text=f"❌ 错误：不支持的文件类型 {ext}")]

            file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
            if file_size_mb > 10:
                return [TextContent(type="text", text=f"❌ 错误：文件过大（{file_size_mb:.1f} MB）")]

            with open(image_path, "rb") as f:
                file_data = f.read()
            filename = os.path.basename(image_path)
        # 模式 B: 网络 URL
        elif image_url:
            try:
                import mimetypes
                from urllib.parse import urlparse
                
                # 1. 下载图片 (使用 stream=True 节省内存)
                resp = requests.get(image_url, stream=True, timeout=15)
                resp.raise_for_status()
                
                # 2. 校验大小
                length = resp.headers.get('Content-Length')
                if length and int(length) > 10 * 1024 * 1024:
                    return [TextContent(type="text", text="❌ 错误：远程图片过大（>10MB）")]
                
                # 3. 校验类型
                content_type = resp.headers.get('Content-Type', '')
                if 'image/' not in content_type:
                    return [TextContent(type="text", text=f"❌ 错误：URL 返回的不是图片 ({content_type})")]
                
                # 4. 读取内容
                file_data = resp.content
                file_size_mb = len(file_data) / (1024 * 1024)
                
                # 5. 智能提取文件名
                parsed_path = urlparse(image_url).path
                name = os.path.basename(parsed_path)
                if name and '.' in name:
                    filename = name
                else:
                    # 如果没有后缀，根据 MIME 类型补充
                    ext = mimetypes.guess_extension(content_type) or ".jpg"
                    filename = f"image{ext}"
                    
            except requests.exceptions.RequestException as e:
                return [TextContent(type="text", text=f"❌ 错误：下载图片失败 → {str(e)}")]
            except Exception as e:
                return [TextContent(type="text", text=f"❌ 错误：处理图片 URL 失败 → {str(e)}")]




        # ---------- 上传请求 ----------
        try:
            # 直接使用 bytes 上传
            response = requests.post(
                url     = api_url,
                files   = {"image": (filename, file_data)},
                data    = {"token": token},
                timeout = 30
            )

            # ---------- 响应处理 ----------
            if response.status_code == 200:
                try:
                    data    = response.json()
                    img_url = (
                        data.get("url") or 
                        data.get("src") or 
                        data.get("path") or 
                        data.get("data", {}).get("url") or
                        "（响应中未找到URL字段）"
                    )
                    result = (
                        f"✅ 上传成功！\n"
                        f"{'─' * 30}\n"
                        f"📎 图片地址：{img_url}\n"
                        f"📁 文件名：{os.path.basename(image_path)}\n"
                        f"📦 文件大小：{file_size_mb:.2f} MB\n"
                        f"🌐 API 地址：{api_url}"
                    )
                except Exception:
                    result = (
                        f"✅ 上传成功（响应非标准JSON）\n"
                        f"📄 原始响应：{response.text[:500]}"
                    )
            else:
                result = (
                    f"❌ 上传失败\n"
                    f"📛 HTTP 状态码：{response.status_code}\n"
                    f"📄 错误信息：{response.text[:300]}"
                )

        except FileNotFoundError:
            result = f"❌ 错误：无法读取文件 → {image_path}"
        except requests.exceptions.ConnectionError:
            result = f"❌ 错误：无法连接到服务器 → {api_url}"
        except requests.exceptions.Timeout:
            result = "❌ 错误：请求超时（超过 30 秒），请检查服务器状态"
        except requests.exceptions.RequestException as e:
            result = f"❌ 请求异常：{str(e)}"
        except Exception as e:
            result = f"❌ 未知错误：{str(e)}"

        return [TextContent(type="text", text=result)]
    
    # -------------------- 未知工具 --------------------
    raise ValueError(f"未知工具: {name}")


# ============================================================
# FastAPI 应用
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    print(f"{'═' * 50}")
    print(f"✅ Easy Image MCP Server 已启动")
    print(f"📡 监听地址：http://{HOST}:{PORT}")
    print(f"🔗 MCP 端点：http://{HOST}:{PORT}/mcp")
    print(f"❤️  健康检查：http://{HOST}:{PORT}/health")
    print(f"{'═' * 50}")
    yield
    print("🛑 MCP Server 已关闭")


app = FastAPI(
    title       = "Easy Image MCP Server",
    description = "基于 MCP 协议的 Easy Image 图床上传服务",
    version     = "1.0.0",
    lifespan    = lifespan
)


# ============================================================
# 健康检查接口
# ============================================================
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "server": MCP_SERVER_NAME,
        "version": "1.0.0"
    }


# ============================================================
# MCP 端点处理（手动实现 Streamable HTTP）
# ============================================================
@app.post("/mcp")
async def handle_mcp_post(request: Request):
    """处理 MCP JSON-RPC 请求"""
    
    # 从 Headers 提取配置并存入上下文
    token   = request.headers.get("X-Easy-Image-Token", "") or DEFAULT_TOKEN
    api_url = request.headers.get("X-Easy-Image-Api-Url", "") or DEFAULT_API_URL
    
    current_token.set(token)
    current_api_url.set(api_url)
    
    # 解析 JSON-RPC 请求
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}
        )
    
    method    = body.get("method", "")
    params    = body.get("params", {})
    rpc_id    = body.get("id", 1)
    
    try:
        # ---------- initialize ----------
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False}
                },
                "serverInfo": {
                    "name": MCP_SERVER_NAME,
                    "version": "1.0.0"
                }
            }
        
        # ---------- tools/list ----------
        elif method == "tools/list":
            tools = await list_tools()
            result = {
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.inputSchema
                    }
                    for t in tools
                ]
            }
        
        # ---------- tools/call ----------
        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            
            contents = await call_tool(tool_name, arguments)
            result = {
                "content": [
                    {"type": c.type, "text": c.text} if hasattr(c, "text") else {"type": c.type}
                    for c in contents
                ]
            }
        
        # ---------- notifications/initialized ----------
        elif method == "notifications/initialized":
            # 通知类请求，无需返回结果
            return Response(status_code=204)
        
        # ---------- 未知方法 ----------
        else:
            return JSONResponse(
                status_code=200,
                content={
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                    "id": rpc_id
                }
            )
        
        return JSONResponse(
            status_code=200,
            content={"jsonrpc": "2.0", "result": result, "id": rpc_id}
        )
        
    except Exception as e:
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                "id": rpc_id
            }
        )


@app.get("/mcp")
async def handle_mcp_get():
    """MCP SSE 端点（用于服务端推送，当前返回服务信息）"""
    return JSONResponse({
        "name": MCP_SERVER_NAME,
        "version": "1.0.0",
        "description": "Easy Image MCP Server - 使用 POST /mcp 进行 JSON-RPC 调用"
    })


@app.delete("/mcp")
async def handle_mcp_delete():
    """MCP 会话关闭（无状态模式下直接返回成功）"""
    return Response(status_code=204)


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    uvicorn.run(
        app       = "easy_image_mcp_server:app",
        host      = HOST,
        port      = PORT,
        reload    = False,
        log_level = "info"
    )
