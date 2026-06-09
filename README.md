# Paper Agent 使用说明

Paper Agent 是一个本地论文记忆库和 RAG 学术助手。它可以抓取论文元数据、导入本地 PDF、把论文切块写入向量库，并通过 AI 对话检索本地全文片段回答问题。

## 主要功能

- 文献检索：支持关键词、语义、混合检索。
- PDF 导入：上传本地 PDF 后自动抽取文本、切块、写入本地数据库和向量库。
- RAG 问答：AI 对话优先检索本地论文全文切块，再补充摘要和元数据。
- 聊天记录：完整聊天记录保存在本地 SQLite，模型上下文只发送摘要和最近几轮，降低 token 消耗。
- 爬虫调度：支持 arXiv、Semantic Scholar、CrossRef 等来源的文献抓取入口。

## 环境要求

推荐使用 Python 3.11。

Windows 下使用 Python 3.11 的原因是依赖包兼容性更稳，尤其是向量库、深度学习和 PDF 解析相关依赖更容易安装，通常不需要额外安装 Visual Studio Build Tools。

## 本地安装

```powershell
git clone git@github.com:nanyan831/Paper-agent.git
cd Paper-agent

py -3.11 -m venv .venv
.\.venv\Scripts\activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 配置环境变量

复制示例配置：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`：

```env
DEEPSEEK_API_KEY="你的真实 key"
DEEPSEEK_BASE_URL="https://api.deepseek.com"
DEEPSEEK_MODEL="deepseek-chat"
```

注意：真实 `.env` 不要提交到仓库。仓库里只保留无 key 的 `.env.example`。

## 启动项目

```powershell
.\.venv\Scripts\activate
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

浏览器打开：

```text
http://127.0.0.1:8000
```

## 使用流程

### 1. 导入论文 PDF

进入“爬虫控制”页面，选择“导入本地 PDF”。

上传后系统会：

- 保存 PDF 到本地 `data/pdfs`
- 用 `pypdf` 抽取全文
- 按 chunk 切割论文
- 保存 chunk 到 SQLite
- 写入 Chroma 向量库

后续 AI 对话和全文检索都会优先使用这些 chunk。

### 2. 搜索文献

进入“探索文献”，输入研究主题或问题。

搜索方式：

- 混合检索：推荐，结合关键词和语义结果。
- 语义检索：更适合概念性问题。
- 关键词检索：更适合精确词、标题、术语。

### 3. AI 对话

左下角有 AI 对话按钮。

现在聊天记录分两层：

- 完整聊天记录：保存在本地数据库，刷新页面后可以恢复。
- 模型上下文：只发送系统提示、历史摘要和最近 10 条用户/助手消息，避免长对话不断消耗 token。

AI 回答论文细节时会优先调用 `search_chunks` 检索本地全文片段；如果本地全文不足，再调用 `search_papers` 查询摘要和元数据。

## RAG 数据结构

本项目当前的 RAG 流程是：

```text
PDF / 爬虫数据
    ↓
SQLite papers 表保存论文元数据
    ↓
PDF 文本抽取并切块
    ↓
paper_chunks 表保存全文片段
    ↓
Chroma 保存 chunk 向量
    ↓
search_chunks 混合检索
    ↓
Agent 基于检索片段回答
```

本地数据默认在：

```text
data/
  papers.db
  chroma_db/
  pdfs/
  logs/
```

## Token 消耗策略

当前已经做了基础控制：

- `search_chunks` 默认返回少量片段，避免把整篇论文塞给模型。
- `search_papers` 返回精简元数据。
- 聊天接口保存完整历史，但模型只吃压缩上下文。
- 每次模型调用会记录 token usage 到 `model_usage_logs`。

建议后续落地时继续补：

- 对不同任务设置 token 预算。
- 对 PDF chunk 做章节识别和更精确引用。
- 增加 usage 看板，统计每天/每会话 token 成本。
- 对长论文摘要做离线预处理，减少在线问答成本。

## 常见问题

### 论文在内网，爬虫抓不到怎么办？

内网论文通常需要人工下载 PDF，然后通过“导入本地 PDF”上传到系统。本系统更适合把你合法可访问的 PDF 建成本地知识库，不建议绕过权限或登录限制做爬取。

### 为什么推荐 Python 3.11？

因为当前依赖组合在 Windows + Python 3.11 下更稳定，安装成功率高。Python 3.12/3.13 可能遇到部分包 wheel 不完整或编译问题。

### Chroma 有 telemetry 报错怎么办？

如果看到 Chroma telemetry 相关警告，一般不影响向量库读写和检索。只要上传、检索和问答正常，可以先忽略。

### `.env` 怎么处理？

本地真实 `.env` 只放自己的 key，不提交。远程仓库只提交 `.env.example`。

## 开发检查命令

```powershell
.\.venv\Scripts\python.exe -m compileall agent agent_tools crawlers database rag routes scheduler main.py config.py
git status --short --branch
```

## 推送到远程

```powershell
git add .
git commit -m "Update documentation"
git push origin main
```
