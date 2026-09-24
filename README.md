# Douyin Reader

一个**自行部署（self-hosted）**的抖音口播提取工具。

> **本仓库只提供开源代码和搭建教程，不提供公共 API、公共 Render 服务或共享的 Cloudflare 配额。**
>
> 每位使用者都需要使用自己的 Render 账号、自己的 Cloudflare 账号和自己的 API Key 部署独立实例。

当前推荐流程：

**抖音分享 → iPhone 快捷指令 → 你自己的 Render → 你自己的 Cloudflare Workers AI Whisper → 自动复制文案 → 打开 ChatGPT**

项目最初尝试过让 ChatGPT 直接通过远程 MCP 读取抖音，但普通 Chat 场景下稳定性和调用限制不理想，所以目前把“提取文案”和“后续讨论”拆开：快捷指令负责提取，ChatGPT 负责继续对话。

---

## 能做什么

- 从抖音分享链接解析视频
- 下载临时视频并提取音频
- 使用 Cloudflare Workers AI Whisper 转写口播
- 长音频分段转写
- 后台异步处理，避免 iPhone 快捷指令长连接超时
- 快捷指令轮询任务状态
- 转写成功后自动复制全文
- 自动打开 ChatGPT
- 预留 `media_router.py`，方便以后扩展小红书、Bilibili 等平台

---

## 重要：这不是公共在线服务

这个仓库没有提供“直接拿来调用”的服务器地址。

你需要自己完成：

```text
GitHub 代码
   ↓
自己的 Render 账号
   ↓
自己的 Render Web Service
   ↓
自己的 Cloudflare Workers AI 凭据
   ↓
自己的 iPhone 快捷指令
```

最终得到的地址类似：

```text
https://YOUR-SERVICE.onrender.com
```

这里的 `YOUR-SERVICE` 是你自己部署后得到的地址。

**不要使用作者本人的 Render 地址、Cloudflare Token 或 Shortcut API Key。**

---

## 架构

```text
Douyin
  │
  │ 分享
  ▼
iPhone Shortcut
  │
  │ GET https://YOUR-SERVICE.onrender.com/shortcut/start?url=...
  │ Header: X-API-Key: YOUR_SHORTCUT_API_KEY
  ▼
Your Render Service
  │
  ├─ 解析抖音链接
  ├─ 下载临时视频
  ├─ FFmpeg 提取音频
  └─ Your Cloudflare Workers AI
          │
          ▼
      transcript
          │
          ▼
iPhone Shortcut
  │
  ├─ 查询任务状态
  ├─ success → 复制 transcript
  └─ 打开 ChatGPT
```

---

## 项目结构

```text
.
├── Dockerfile
├── README.md
├── .env.example
├── pyproject.toml
├── .gitignore
├── .gitattributes
└── douyin_mcp_server/
    ├── __init__.py
    ├── __main__.py
    ├── server.py
    ├── remote_server.py
    ├── media_router.py
    ├── workflow.py
    ├── asr_module.py
    └── capture_douyin.js
```

主要文件：

- `server.py`：抖音解析、下载、音频处理和 ASR
- `remote_server.py`：给 iPhone 快捷指令使用的 HTTP 接口
- `media_router.py`：为未来多平台扩展预留
- `Dockerfile`：Render Docker 部署
- `.env.example`：需要自行配置的环境变量示例

---

# 一、准备 Cloudflare Workers AI

你需要自己的 Cloudflare 账号。

准备两个值：

```text
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
```

创建 Token 时只授予完成 Workers AI 调用所需的权限。

**不要把 Token 写进 GitHub。**

---

# 二、Fork / 下载仓库

你可以 Fork 本仓库，也可以下载后放入自己的仓库。

不要把以下内容提交到公开仓库：

```text
真实 Cloudflare API Token
真实 SHORTCUT_API_KEY
.env
作者或你自己的私人服务地址
```

---

# 三、部署到自己的 Render

在 Render 创建一个新的 Web Service：

```text
Source: 你自己的仓库
Runtime: Docker
Branch: main
```

然后添加环境变量：

```text
CLOUDFLARE_ACCOUNT_ID=你的 Cloudflare Account ID
CLOUDFLARE_API_TOKEN=你的 Cloudflare Token
SHORTCUT_API_KEY=你自己生成的一段随机字符串
```

Render 会为你生成自己的公网地址，例如：

```text
https://YOUR-SERVICE.onrender.com
```

测试：

```text
GET https://YOUR-SERVICE.onrender.com/health
```

正常返回：

```json
{
  "status": "ok",
  "service": "douyin-reader-self-hosted"
}
```

---

# 四、接口鉴权

转写接口不是公共接口。

调用以下接口时，都必须带请求头：

```text
X-API-Key: YOUR_SHORTCUT_API_KEY
```

没有正确 Key 的请求不会执行转写。

API Key 不放在 URL 路径里，避免直接出现在普通访问日志的请求路径中。

---

# 五、接口

## 创建转写任务

```text
GET https://YOUR-SERVICE.onrender.com/shortcut/start?url=<URL_ENCODED_DOUYIN_URL>
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

## 查询任务状态

```text
GET https://YOUR-SERVICE.onrender.com/shortcut/status/<job_id>
```

同样带：

```text
X-API-Key: YOUR_SHORTCUT_API_KEY
```

可能返回：

### 排队

```json
{
  "status": "queued"
}
```

### 处理中

```json
{
  "status": "processing"
}
```

### 成功

```json
{
  "status": "success",
  "transcript": "..."
}
```

### 失败

```json
{
  "status": "failed",
  "error": "..."
}
```

> **注意：当前成功状态是 `success`，不是 `completed`。**
>
> iPhone 快捷指令如果判断 `completed`，即使任务已经成功，也会继续循环。

---

# 六、iPhone 快捷指令

推荐逻辑：

```text
1. 从分享菜单接收输入

2. 把快捷指令输入转成文本

3. 用正则匹配第一个 URL：
   https?://[^\s]+

4. 获取匹配结果的第一项

5. 对这个 URL 进行 URL 编码

6. 拼接：
   https://YOUR-SERVICE.onrender.com/shortcut/start?url=<编码后的URL>

7. “获取 URL 内容”
   方法：GET
   Header：
   X-API-Key = YOUR_SHORTCUT_API_KEY

8. 从返回结果获取 job_id

9. 重复若干次：
   - 等待约 10 秒
   - 请求：
     https://YOUR-SERVICE.onrender.com/shortcut/status/<job_id>
   - 方法：GET
   - Header：
     X-API-Key = YOUR_SHORTCUT_API_KEY
   - 获取 status

10. 如果 status 是 success：
    - 获取 transcript
    - 复制到剪贴板
    - 显示“转写完成”
    - 打开 ChatGPT
    - 停止快捷指令

11. 如果 status 是 failed：
    - 获取 error
    - 显示错误
    - 停止快捷指令

12. 如果是 queued / processing：
    - 不做任何事
    - 继续下一轮
```

---

# 七、为什么不用作者的服务？

因为本项目的定位是：

**提供代码 + 教程，而不是替所有用户承担服务器和 AI 调用成本。**

每个用户使用自己的：

- Render 实例
- Cloudflare Account
- Cloudflare API Token
- Shortcut API Key

这样：

- 转写次数不会消耗作者的额度
- 每个人的数据和凭据相互隔离
- 作者不需要维护公共服务
- 用户可以自行修改、停止或删除自己的实例

---

# 八、安全建议

- 不要公开真实 `SHORTCUT_API_KEY`
- 不要公开 Cloudflare Token
- 不要把 Key 写进仓库
- 不要把 Key 放进 URL
- `.env` 必须加入 `.gitignore`
- 如果 Key 曾经出现在截图或日志分享里，立即轮换
- 不需要的测试接口应删除
- 当前远程 Web 服务不需要公开 `/mcp`

Render 的服务地址本身需要公网可访问，iPhone 才能调用；安全边界依靠你自己的 `X-API-Key`，而不是依靠“别人永远猜不到地址”。

---

# 九、已知限制

- Render 免费实例长时间无请求后可能休眠，第一次请求会较慢
- 当前任务状态保存在内存中，服务重启会丢失未完成任务
- 抖音页面结构变化后，解析逻辑可能需要更新
- 主要针对普通人声口播
- 唱歌、纯音乐、背景音乐过强时识别效果可能较差
- 当前正式跑通的平台是抖音

---

# 十、未来扩展

后续可以在保持快捷指令后半段不变的情况下增加：

- 小红书
- Bilibili
- 其他支持获取媒体地址的平台

推荐将新平台接入 `media_router.py`，复用：

```text
Render
Cloudflare Whisper
异步任务
轮询
剪贴板
ChatGPT 跳转
```

---

# 关于 MCP

项目保留部分 MCP 相关代码，是因为它最初来自抖音 MCP 项目，也方便未来继续实验。

但**当前推荐的远程部署不公开 MCP 入口**。

目前稳定工作流是：

```text
快捷指令提取文案
→ 自动复制
→ 打开 ChatGPT
→ 用户粘贴文案
→ 在普通 Chat / 项目 / 插件中继续讨论
```

---

# 上游项目

本项目是在社区项目基础上继续修改和扩展。

请保留仓库原有的 LICENSE、版权声明以及上游归属信息。

---

# 当前状态

已完成 iPhone 端到端实测：

```text
抖音分享
→ 自己的 Render
→ 自己的 Cloudflare Whisper
→ 自动复制文案
→ 自动打开 ChatGPT
```

本仓库不提供公共托管实例。
