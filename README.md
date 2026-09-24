# Douyin Reader

一个**自行部署（self-hosted）**的抖音视频口播提取工具。

> 本仓库只提供源代码和搭建教程，不提供公共 API、公共 Render 实例或共享的 Cloudflare 配额。
>
> 每位使用者都需要使用自己的 Render、Cloudflare 和 API Key。

## 最终工作流

```text
抖音分享
→ iPhone 快捷指令
→ 你自己的 Render
→ 你自己的 Cloudflare Workers AI Whisper
→ 自动复制文案
→ 自动打开 ChatGPT
```

当前正式跑通的平台是抖音。

## 目录

```text
.
├── Dockerfile
├── pyproject.toml
├── README.md
├── LICENSE
├── NOTICE
├── .env.example
├── .gitignore
├── .dockerignore
└── douyin_mcp_server/
    ├── __init__.py
    ├── __main__.py
    ├── media_router.py
    ├── server.py
    └── remote_server.py
```

这是一份已经精简过的远程部署版本，不再依赖旧项目中的本机
`faster-whisper`、Playwright、WebUI 或远程 MCP 入口。

## 1. 准备 Cloudflare

创建自己的 Cloudflare 账号，并准备：

```text
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
```

推荐使用 Workers AI 的 API Token。

默认模型：

```text
@cf/openai/whisper-large-v3-turbo
```

## 2. 部署 Render

在 Render 创建 Web Service：

```text
Source: 你自己的 GitHub 仓库
Runtime: Docker
Branch: main
```

设置环境变量：

```text
CLOUDFLARE_ACCOUNT_ID=你的 Account ID
CLOUDFLARE_API_TOKEN=你的 Token
SHORTCUT_API_KEY=你自己生成的随机字符串
```

可选：

```text
CLOUDFLARE_MODEL=@cf/openai/whisper-large-v3-turbo
```

部署后测试：

```text
https://YOUR-SERVICE.onrender.com/health
```

正常返回：

```json
{
  "status": "ok",
  "service": "douyin-reader-self-hosted"
}
```

## 3. 快捷指令接口

### 创建任务

```text
GET https://YOUR-SERVICE.onrender.com/shortcut/start?url=<编码后的抖音URL>
```

请求头：

```text
X-API-Key: YOUR_SHORTCUT_API_KEY
```

返回：

```json
{
  "status": "accepted",
  "job_id": "..."
}
```

### 查询状态

```text
GET https://YOUR-SERVICE.onrender.com/shortcut/status/<job_id>
```

同样携带：

```text
X-API-Key: YOUR_SHORTCUT_API_KEY
```

可能返回：

```json
{"status":"queued"}
```

```json
{"status":"processing"}
```

成功：

```json
{
  "status": "success",
  "transcript": "..."
}
```

失败：

```json
{
  "status": "failed",
  "error": "..."
}
```

**快捷指令成功判断必须使用 `success`，不是 `completed`。**

## 4. iPhone 快捷指令

建议：

```text
接收分享内容
→ 转成文本
→ 正则匹配第一个 https:// URL
→ URL 编码
→ GET /shortcut/start
   Header: X-API-Key
→ 获取 job_id
→ 循环：
   等待约 10 秒
   → GET /shortcut/status/<job_id>
      Header: X-API-Key
   → 获取 status
      success:
        获取 transcript
        复制到剪贴板
        打开 ChatGPT
        停止快捷指令
      failed:
        显示 error
        停止快捷指令
      queued / processing:
        继续下一轮
```

## 安全

- 不要把真实 Token 或 Key 写入仓库
- 不要把 Key 放在 URL 路径里
- 使用 `X-API-Key`
- `.env` 已加入 `.gitignore`
- 如果密钥曾出现在截图或公开日志里，请轮换
- 本仓库不提供作者的在线实例
- 每位用户应该部署自己的 Render 和 Cloudflare

## 已知限制

- Render 免费实例休眠后第一次请求可能较慢
- 任务状态暂存在进程内存；服务重启会丢失未完成任务
- 抖音页面结构变化后解析逻辑可能需要调整
- 唱歌、纯音乐或背景音乐过强时，Whisper 识别可能较差

## 后续扩展

`media_router.py` 已经保留平台分流结构。

以后可以新增：

- 小红书
- Bilibili
- 其他媒体平台

尽量复用后半段：

```text
Render
→ Cloudflare Whisper
→ 异步任务
→ 快捷指令轮询
→ 剪贴板
→ ChatGPT
```

## 上游来源

本项目基于以下社区项目继续修改：

- `dvdxfv/douyin-mcp-server`
- `yzfly/douyin-mcp-server`

上游项目使用 Apache License 2.0。本仓库保留相应许可证与来源说明。

## 免责声明

本项目仅供学习、研究和个人工具用途。使用者应自行遵守适用的平台规则、法律法规及内容版权要求。
