# Easy Image MCP Server

这是一个基于 Model Context Protocol (MCP) 的服务器，旨在集成 **Easy Image** 图床服务。它允许 AI 助手通过 MCP 协议上传图片到指定的图床，并获取访问链接。

## 功能概述

该 MCP Server 提供以下两个核心工具：

1. **`upload_image`**: 上传图片到 Easy Image 图床服务器。
   - 支持传入本地文件路径或网络图片 URL。
   - 返回图片访问链接及上传状态信息。
2. **`check_config`**: 检查当前 Easy Image 服务配置状态（Token 和 API URL 是否已配置）。

## 工具详情

### `upload_image`

上传图片到 Easy Image 图床服务器，支持传入本地文件路径或网络图片 URL。返回图片访问链接及上传状态信息。Token 和 API URL 已通过 Headers 预配置，调用时可选覆盖。

#### 输入参数 (Input Schema)

| 参数名 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `image_path` | string | 否 | （二选一）本地图片文件的绝对路径 |
| `image_url` | string | 否 | （二选一）图片的网络 URL 地址，程序将自动下载并上传 |
| `token` | string | 否 | （可选）覆盖 Headers 中预配置的 Token |
| `api_url` | string | 否 | （可选）覆盖 Headers 中预配置的 API 地址 |

> **注意**: `image_path` 和 `image_url` 只需提供其中一个。其他参数均为可选，用于覆盖默认配置。

### `check_config`

检查当前 Easy Image 服务配置状态（Token 和 API URL 是否已配置）。此工具无输入参数。

## 配置说明

- **预配置**: Token 和 API URL 已在服务器内部通过 Headers 预配置。
- **覆盖**: 在调用 `upload_image` 时，可以通过传入 `token` 或 `api_url` 参数来临时覆盖默认配置。

## 使用示例

### 上传本地图片

```json
{
  "name": "upload_image",
  "arguments": {
    "image_path": "/path/to/local/image.png"
  }
}
```

### 上传网络图片

```json
{
  "name": "upload_image",
  "arguments": {
    "image_url": "https://example.com/image.jpg"
  }
}
```

### 检查配置状态

```json
{
  "name": "check_config",
  "arguments": {}
}
```

## 安装与运行

1. 确保已安装 Python 3.8+。
2. 安装依赖（如有）：
   ```bash
   pip install -r requirements.txt
   ```
3. 启动 MCP Server：
   ```bash
   python easy_image_mcp_server.py
   ```

## 注意事项

- 请确保 Easy Image 图床服务的 Token 和 API URL 已正确配置在服务器代码中。
- 上传网络图片时，程序会自动下载图片并上传，请确保网络连接正常。
