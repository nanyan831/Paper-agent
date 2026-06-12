# Paper Agent 发布前清理与 Push Checklist

这份清单用于主线程在执行 `git push origin main` 前做最后确认。目标是避免把真实 key、本地数据库、PDF、向量库、问卷截图、设计文档产物等本地材料推到远程仓库。

当前原则：

- 只 push 已经明确属于项目源码、文档、配置示例的内容。
- 不 push `.env`、`data/`、本地 PDF、Chroma 向量库、SQLite 数据库、截图、问卷识别材料。
- push 前必须确认 README、MVP checklist 和当前功能保持一致。
- push 由主线程执行，本线程不 push。

## 1. Push 前必须跑的命令

在项目根目录执行：

```powershell
cd "C:\Users\11329\Desktop\paper agent\Paper-agent"
git status --short --branch
git log --oneline --decorate -10
```

代码检查：

```powershell
.\.venv\Scripts\python.exe -m compileall agent agent_tools crawlers database rag routes scheduler main.py config.py
node --check static\js\app.js
```

如果本地 8000 服务正在运行，做接口回归：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/papers?source=local_pdf&limit=6"
Invoke-RestMethod "http://127.0.0.1:8000/api/search/chunks?q=Autoregressive%20Retrieval%20Augmentation&search_type=hybrid&top_k=2"
```

如果 8000 没开，不要为了 push 强行启动服务；只需要在最终说明里写清楚“未做运行时接口回归”。如果主线程已经要求完整测试，则先启动再测。

## 2. `.env` 与真实 Key 检查

必须确认：

```powershell
git status --short -- .env .env.example
git check-ignore -v .env
Get-Content -Raw -Encoding UTF8 .env.example
```

通过标准：

- `.env` 不出现在 staged 或 tracked 文件里。
- `git check-ignore -v .env` 能显示 `.env` 被 `.gitignore` 忽略。
- `.env.example` 只能包含占位符，不能包含真实 API key。
- README 只能指导用户复制 `.env.example`，不能泄露真实 key。

不可以 push 的情况：

- `git status` 显示 `.env` 被跟踪或将被提交。
- `.env.example` 里出现真实 `DEEPSEEK_API_KEY` 或其他服务 key。
- 文档、日志或测试输出里包含真实 key。

## 3. 本地数据与向量库检查

必须确认以下内容不会进仓库：

```powershell
git check-ignore -v data/
git check-ignore -v data/pdfs/
git check-ignore -v data/chroma_db/
git check-ignore -v chroma_db/
git check-ignore -v "*.db"
git check-ignore -v "*.sqlite3"
```

通过标准：

- `data/` 被忽略。
- `data/pdfs/` 被忽略。
- `data/chroma_db/` 或项目内 Chroma 目录被忽略。
- SQLite 数据库文件被忽略。
- `git status --short` 不显示任何 PDF、数据库、向量库文件。

不可以 push 的情况：

- `data/` 下任何文件出现在 `git status`。
- `*.pdf` 是本地论文或用户资料，而不是明确要提交的项目文档。
- `papers.db`、`*.sqlite3`、Chroma collection 文件进入 staged。

## 4. 未跟踪材料与 `.gitignore` 检查

当前本地可能出现这些材料：

- `survey_receipt_*`
- `screenshots/`
- `take_screenshots.py`
- `generate_design_doc*.py`
- `generate_frontend_doc.py`
- `Frontend_UI_Analysis.pdf`
- `UI_Design_Reference.pdf`
- `UI_设计参考文档.pdf`
- `Paper_Agent_user_survey*.docx`
- `server-verify*.log`

必须确认：

```powershell
git status --short --ignored
git check-ignore -v survey_receipt_clean.txt
git check-ignore -v screenshots/
git check-ignore -v Paper_Agent_user_survey.docx
git check-ignore -v Frontend_UI_Analysis.pdf
```

通过标准：

- 这些文件要么不在工作区，要么出现在 ignored 区域。
- `git status --short` 不显示它们为 `??`。
- 如果还有 `??`，先判断是否应该加入 `.gitignore`，不要直接 `git add .`。

不可以 push 的情况：

- 问卷截图、识别文本、用户问卷 docx、UI 参考 PDF 出现在未跟踪列表。
- 主线程准备使用 `git add .`，但 `git status --short` 里还有不该提交的 `??` 文件。

建议 push 前避免使用：

```powershell
git add .
```

优先使用精确路径：

```powershell
git add README.md docs/release_checklist.md
```

或先确认 `git status --short` 没有本地材料后再全量 add。

## 5. 8000 服务状态确认

push 前需要决定是否保留本地服务给用户试用。

检查：

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
```

如果需要关闭：

```powershell
$conns = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
$pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($pid in $pids) { if ($pid) { Stop-Process -Id $pid -Force } }
```

判断标准：

- 如果用户马上要本机试用，可以保留 8000 服务，并在最终回复里给出 `http://127.0.0.1:8000`。
- 如果只是准备 push，不需要保留后台服务，建议关闭，避免后续误以为运行的是最新代码。
- 如果服务保留，必须确认它对应当前工作区最新代码，必要时重启后再回归接口。

## 6. README 与 MVP Checklist 同步检查

必须确认 README 与以下文档不冲突：

- `docs/mvp_trial_checklist.md`
- `docs/survey_findings.md`
- `docs/user_testing_plan.md`
- `docs/release_checklist.md`

重点检查：

- README 是否仍把项目说成“Zotero 替代品”。如果是，不可以 push。
- README 是否明确第一阶段是“找出处 / 查证据 / 回原文”。如果没有，先补。
- README 是否说明 `.env` 不提交、`data/` 是本地数据。若没有，先补。
- MVP checklist 是否仍要求第一轮不测复杂文献图谱、多人协作、自动写完整论文。
- README 的开发检查命令是否与当前项目能跑的命令一致。

## 7. 可以 Push 的判断标准

满足以下全部条件，主线程可以 push：

- `git status --short --branch` 只显示待推送 commits，没有意外 modified 或 untracked 文件。
- 所有要提交的改动都已经 commit。
- `.env` 被 `.gitignore` 忽略，且没有真实 key 进入 tracked 文件。
- `data/`、`data/pdfs/`、`chroma_db/`、SQLite 数据库没有进入仓库。
- 问卷、截图、UI 参考 PDF、生成脚本等本地材料被 `.gitignore` 收住。
- Python compileall 通过。
- `node --check static\js\app.js` 通过。
- 如果做了运行时回归，关键接口返回正常。
- README 与 MVP checklist 的产品路线一致。
- 当前 commit 历史里的改动都是主线程准备发布的内容。

可以 push 时执行：

```powershell
git push origin main
```

## 8. 不可以 Push 的判断标准

出现任一情况，不要 push：

- `git status --short` 显示 `.env`、`data/`、PDF、数据库、Chroma 文件、问卷截图或本地设计资料。
- `.env.example` 或文档里出现真实 key。
- `git diff --cached --name-only` 包含本地资料、截图、数据库、PDF 论文。
- Python compileall 或 JS 语法检查失败。
- README 仍描述已经被砍掉的第一轮目标，例如自动写完整论文、复杂图谱优先。
- 8000 服务回归失败，但最终回复打算告诉用户“已经可试用”。
- 工作区里有其他线程未提交的业务改动，主线程还没确认是否一起发布。

## 9. 最终发布回复模板

push 完成后主线程可以这样回复：

```text
已完成发布前检查并推送到远程 main。

检查项：
- Python compileall 通过
- static/js/app.js 语法检查通过
- .env 未提交，.env.example 无真实 key
- data/、pdfs/、chroma_db/、SQLite 数据库未进入仓库
- 本地问卷/截图/设计材料已被 .gitignore 收住
- README 与 MVP checklist 同步，第一阶段聚焦“找出处 / 查证据 / 回原文”

远程分支：origin/main
```

如果没有启动或保留服务，需要补一句：

```text
本次只做发布检查和 push，没有保留本地 8000 服务。
```
