# Paper Agent 使用说明

Paper Agent 是一个本地论文记忆库和 RAG 学术助手。它可以抓取论文元数据、导入本地 PDF、把论文切块写入向量库，并通过 AI 对话检索本地全文片段回答问题。

## 主要功能

- 文献检索：支持关键词、语义、混合检索。
- PDF 导入：支持单篇或批量上传本地 PDF，自动抽取文本、切块、写入本地数据库和向量库。
- 找出处 / 查证据：输入一句观点或问题，直接检索本地 PDF chunk，返回可能来源、页码和原文片段。
- RAG 问答：AI 对话优先检索本地论文全文切块，并返回结构化来源。
- AI 对话体验：支持 Markdown 样式渲染，最新回答会在网页端逐字生成，用户向上阅读时不会被强制拉到底部。
- PDF 原文跳转：点击 AI 来源、找出处结果或阅读器内证据卡片，可打开 PDF 查看器并跳到对应页。
- PDF 阅读器：支持页码跳转、缩放、原文/译文/对照阅读模式、阅读器内查出处；底层 chunk 继续用于 RAG，但不直接展示给普通用户。
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

现在支持一次选择多个 PDF。批量导入后，每个文件都会返回独立结果：

- 成功：显示论文标题、paper id、页数、chunk 数，并可直接打开原文。
- 空文件：提示 `Uploaded PDF is empty`。
- 非 PDF：提示 `Only PDF files are supported`。
- 解析失败：提示 PDF 解析失败原因。

### 2. 找出处 / 查证据

进入“探索文献”，使用“找出处 / 查证据”入口。

适合输入：

```text
RAG 可以降低大模型幻觉吗？这个结论出自哪篇论文？
```

系统会调用本地全文 chunk 检索，返回：

- 论文名
- 页码范围
- 原文片段
- 检索方式
- 打开原文页按钮

这个入口是第一阶段 MVP 的核心，不是普通搜索框。它主要回答“这句话有没有本地依据、依据在哪里”。

### 3. 搜索文献

进入“探索文献”，输入研究主题或问题。

搜索方式：

- 混合检索：推荐，结合关键词和语义结果。
- 语义检索：更适合概念性问题。
- 关键词检索：更适合精确词、标题、术语。

### 4. AI 对话

左下角有 AI 对话按钮。

AI 回答会按网页阅读体验展示：

- Markdown 会渲染成标题、列表、引用、代码块、加粗等样式。
- 最新一条助手回答会逐字生成。
- 如果用户正在向上查看历史消息，页面不会强制自动滚到底部。

现在聊天记录分两层：

- 完整聊天记录：保存在本地数据库，刷新页面后可以恢复。
- 模型上下文：只发送系统提示、历史摘要和最近 10 条用户/助手消息，避免长对话不断消耗 token。

AI 回答论文细节时会优先调用 `search_chunks` 检索本地全文片段；如果本地全文不足，再调用 `search_papers` 查询摘要和元数据。

回答来源会同时以两种形式保存：

- 文本中的“本地引用来源”。
- API 返回的结构化 `sources`。

每条 source 包含：

```json
{
  "paper_id": "...",
  "title": "...",
  "page_start": 1,
  "page_end": 2,
  "snippet": "...",
  "chunk_id": "...",
  "search_score": 0.01,
  "search_type": "hybrid_chunk",
  "chunk_index": 0,
  "evidence": {
    "confidence": "medium"
  }
}
```

如果没有本地证据，Agent 会明确说明“本地论文库没有找到可引用依据”，不会给确定结论。如果来源数量少或质量信号弱，回答会加上“证据不足，只能作为线索”。

### 5. 打开 PDF 原文

最近收录资料、找出处结果、AI 来源卡片都可以打开 PDF 查看器。

阅读器支持：

- 上一页 / 下一页
- 页码输入
- 缩放
- 点击来源跳转到 `page_start`
- 译文阅读模式：切换到“译文”后，会把当前页英文抽取出来并渲染成同阅读器尺寸的中文页面。
- 对照阅读模式：左侧保留原 PDF，右侧显示当前页译文，翻页和缩放仍共用同一套阅读器控制。
- 展开阅读区：阅读区可一键展开，隐藏右侧工具栏，让原文/译文两栏获得更大宽度。
- 可最小化翻译器：侧边栏段落翻译器可以收起，只保留标题栏；需要时再展开翻译当前页或指定段落。
- 阅读器内查出处：可在当前论文或全部资料库中检索证据。
- 底层 chunk 隐藏：用户阅读时不直接看 chunk 列表，但 RAG、找出处、引用跳转仍然使用这些切块数据。

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

当前数据概览页已经提供基础 usage 看板：

- 累计 Agent 调用、输入 token、输出 token、总 token。
- 今日 token 和今日估算成本，用于观察试用阶段的消耗。
- 最近 20 次模型调用记录，包含 Agent 对话和阅读器翻译产生的 token。
- 最近 RAG 命中记录，方便检查 Agent 是否真的在检索本地全文。

注意：页面上的成本只是按固定单价做的粗略估算，正式结算仍以模型服务商后台为准。

## 试用质量提示

为了让 MVP 更适合真实用户试用，当前界面会在关键位置显示质量状态：

- PDF 导入结果会标记“可检索 / 需 OCR / 导入失败”。
- 最近收录资料会持续显示 PDF 是否可能是扫描版或不可检索。
- AI 来源卡片和阅读器内查出处结果会显示“证据强 / 证据中 / 证据弱 / 待核验”。
- 证据不足时，Agent 会明确提示，避免把低质量检索结果包装成确定结论。

这里的证据强度基于本地检索分数和页码等信号，只表示“这条来源与问题的匹配强弱”，不等于系统已经自动完成事实验证。

## MVP 试用路线

第一阶段不要把 Paper Agent 做成 Zotero 替代品，也不要优先做自动写完整论文。

当前最应该验证的闭环是：

```text
导入 5-30 篇真实 PDF
    ↓
围绕真实任务提问或找出处
    ↓
回答显示论文名、页码、原文片段
    ↓
点击来源回到 PDF 对应页
    ↓
用户判断是否敢引用
```

试用前 checklist 在：

```text
docs/mvp_trial_checklist.md
```

第一轮试用暂时不重点测试：

- 复杂文献图谱
- 多人协作
- 自动写完整论文
- 精美笔记系统

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
node --check static\js\app.js
git status --short --branch
```

常用接口回归：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/papers?source=local_pdf&limit=6"
Invoke-RestMethod "http://127.0.0.1:8000/api/search/chunks?q=Autoregressive%20Retrieval%20Augmentation&search_type=hybrid&top_k=2"
```

引用准确性自测（不调用 LLM，不消耗 token）：

```powershell
.\.venv\Scripts\python.exe scripts\verify_evidence_flow.py
```

PDF 来源跳转自测：

```powershell
.\.venv\Scripts\python.exe scripts\smoke_pdf_source_jump.py --api-url http://127.0.0.1:8000
```

阅读器翻译接口会调用 DeepSeek，测试时会消耗少量 token：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/translate" -Method Post -ContentType "application/json" -Body '{"text":"Retrieval augmented generation improves answer grounding.","target_language":"zh-CN"}'
```

详细说明见：

```text
docs/evidence_flow_verification.md
```

## 推送到远程

```powershell
git add .
git commit -m "Update documentation"
git push origin main
```
