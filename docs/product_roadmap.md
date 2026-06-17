# Paper Agent 后续研发规划

更新日期：2026-06-17

## 当前定位

Paper Agent 当前已经具备 MVP 雏形：可以导入本地 PDF、切割 chunk、写入向量库、在网页中阅读论文、翻译页面、通过 Agent 对话检索论文证据，并从回答跳回原文页码。

接下来不要先堆更多功能，而要优先把一条核心链路做到稳定、便宜、可信：

```text
导入论文 -> 阅读论文 -> 提问 -> 得到带来源的回答 -> 点击来源回到原文页码
```

## 当前阶段性成果

- 本地 PDF 导入：支持上传 PDF、解析文本、生成 chunk。
- RAG 检索：支持全文 chunk 检索，返回 paper_id、标题、页码、片段和分数。
- PDF 阅读器：支持网页内打开论文、页码定位、来源跳转。
- 翻译阅读：支持阅读器翻译、译文模式和可折叠翻译工具。
- AI 对话：左下角二级入口，支持 Markdown 美化和逐字生成效果。
- 证据链：Agent 回答返回 sources，带页码、snippet 和 evidence confidence。
- Readiness 状态：显示 API key、PDF、chunk、embedding、token 预算等状态。
- 冷启动优化：embedding 模型后台预热，不阻塞服务启动。
- token 治理：`DAILY_TOKEN_BUDGET` 控制每日 token 熔断，默认 200000。
- 本地验收脚本：
  - `scripts/mvp_smoke.py`：核心服务自检，不消耗 token。
  - `scripts/rag_quality_check.py`：RAG 证据链自检，不消耗 token。
  - `scripts/agent_answer_eval.py`：Agent 回答质量评测，会消耗 DeepSeek token。

## P0：代码保存和试用基线

目标：确保当前成果可恢复、可复现、可交付给别人试用。

要做：

- 推送本地领先远程的提交。
- 确认 `.env`、`data/`、PDF、Chroma、SQLite、`reports/` 不会进入远程仓库。
- 保留 `.env.example` 作为无密钥配置模板。
- 运行两套不消耗 token 的自检：

```powershell
.\.venv\Scripts\python.exe scripts\mvp_smoke.py --api-url http://127.0.0.1:8000
.\.venv\Scripts\python.exe scripts\rag_quality_check.py --api-url http://127.0.0.1:8000
```

验收标准：

- `git status --short --branch` 干净。
- smoke 和 RAG quality 均为 PASS。
- 远程仓库不包含真实 key、本地数据库、向量库、PDF 和报告文件。

## P1：Agent token 消耗优化

目标：把 Agent 单题回答成本降下来，让真实试用不会快速耗尽预算。

现状问题：

- 单题 Agent 评测曾消耗约 35000 tokens。
- 当前 Agent 上下文可能带入过多 chunk 和过长片段。

要做：

- 限制 Agent 每次检索传给模型的 chunk 数量，优先 3-5 个。
- 对传给模型的 snippet 做长度截断。
- 区分“模型上下文”和“前端展示 sources”：模型拿短证据，前端仍可保留完整 source 信息。
- 增加单次调用预估 token 和软上限。
- 当上下文过长时，优先压缩或拒绝，而不是直接调用模型。
- 在 `agent_answer_eval.py` 报告中加入平均 token、单题最高 token。

验收标准：

- 单题 Agent 回答控制在 3000-8000 tokens 左右。
- 回答仍至少返回 1-3 个可点击来源。
- `agent_answer_eval.py --yes --limit 1` 结果不低于 WARN。

## P2：MVP 试用说明和新手路径

目标：用户不需要你在旁边解释，也能跑通完整流程。

要做：

- 新增 `docs/mvp_trial_guide.md`。
- 写清楚启动项目、配置 key、导入 PDF、打开阅读器、提问、查看来源、控制 token 的步骤。
- 首页 readiness banner 的提示继续人话化。
- 对常见失败给出明确操作：
  - 没有 API key。
  - 没有 PDF。
  - PDF 没有可解析文本。
  - token 预算耗尽。
  - embedding 正在加载。

验收标准：

- 新用户 5 分钟内能完成一次“导入论文 -> 提问 -> 回到原文”。
- 用户不需要理解 chunk 和向量库细节。

## P3：RAG 可信度提升

目标：让用户相信每个关键结论都能回到原文。

要做：

- 回答中的关键结论后面尽量绑定来源。
- 来源卡片展示标题、页码、证据强弱、短片段。
- 找不到本地依据时，Agent 必须明确说“本地论文库没有找到可引用依据”。
- 改进 evidence confidence：
  - high：有页码、分数高、片段相关。
  - medium：有页码但分数一般。
  - low：相关性弱。
  - unknown：缺少分数或页码。
- 扩展 `rag_quality_check.py` 的查询集，覆盖更多真实问题。

验收标准：

- Agent 不输出无来源的确定性结论。
- 每次回答至少有一个可点击 source。
- 来源页码能打开 PDF 对应页。

## P4：PDF 阅读器产品化

目标：让它从“能看 PDF”变成真正的论文阅读工作台。

要做：

- 文献列表增强：
  - 收藏。
  - 标签。
  - 最近阅读。
  - 本地 PDF 筛选。
- 阅读器增强：
  - 选中文本提问。
  - 问当前页。
  - 问整篇论文。
  - 高亮。
  - 笔记。
- 翻译增强：
  - 左右双栏阅读。
  - 翻译缓存。
  - 可最小化翻译面板。
- 隐藏普通用户不需要看的 chunk 信息。

验收标准：

- 用户可以把它当成日常论文阅读器使用。
- 阅读器内能自然完成“读、问、翻译、回源”。

## P5：论文获取和入库能力

目标：形成与 Zotero 的差异化：不仅管理论文，还能主动获取论文并进入 RAG。

要做：

- 稳定 arXiv、Crossref、RSS 等元数据抓取。
- 增加 PDF 自动下载能力，前提是来源允许访问。
- DOI、标题、arXiv id 去重。
- 对内网/权限论文采用合规路径：
  - 用户自己下载后上传。
  - 保存来源 URL。
  - 不绕过权限。
- 增加扫描版 PDF 检测。
- 后续接入 OCR。

验收标准：

- 同一篇论文不会重复入库。
- 有权限的 PDF 可以自动或手动进入本地库。
- 扫描版 PDF 能给出明确提示。

## P6：部署和发布

目标：让别人能独立安装和试用。

要做：

- 增加 Windows 一键启动脚本。
- 评估 Docker 版本。
- 完善 `.env.example`。
- 增加数据备份和恢复说明。
- 写 release checklist。
- 打包一个 MVP release。

验收标准：

- 新机器按文档能跑起来。
- 不泄露 key。
- 本地数据路径清晰。

## P7：用户验证

目标：让研发方向来自真实用户，而不是只凭自己判断。

要做：

- 找 5-10 个目标用户：
  - 研究生。
  - 论文写作者。
  - 科研助理。
  - 需要读英文论文的人。
- 让他们完成三件事：
  - 导入一篇论文。
  - 问一个研究问题。
  - 根据来源回到原文。
- 记录问题：
  - 哪一步卡住。
  - 回答是否可信。
  - 翻译是否有价值。
  - 是否愿意长期使用。
  - 最想要的新功能是什么。

验收标准：

- 至少收集 5 份真实试用反馈。
- 根据反馈决定下一轮重点：阅读器、爬虫、Agent、翻译或文献管理。

## 当前推荐执行顺序

```text
1. 推送远程，保存当前成果。
2. 优化 Agent token 消耗。
3. 写 MVP 试用说明。
4. 增加选中文本提问/问当前页。
5. 做 OCR 或扫描 PDF 检测。
6. 找真实用户试用。
```

## 当前核心判断

Paper Agent 现在最重要的竞争力不是“有很多功能”，而是：

```text
让每一个回答都能回到原文证据。
```

因此后续所有功能都应该围绕三个标准取舍：

- 可信：结论能回源。
- 省钱：token 消耗可控。
- 易用：用户不需要理解 RAG 细节。
