# Evidence Flow Verification

Use this check before a real trial to make sure Paper Agent can retrieve local PDF evidence and refuse unsupported answers without calling an LLM.

## What It Checks

- A known evidence query returns local chunk sources.
- Each source prints title, page, snippet, search score, search type, chunk index, and confidence.
- An unrelated query triggers the no-evidence refusal policy.
- No DeepSeek/OpenAI API call is made, so no model token is consumed.

## Run With Local Retriever

```powershell
.\.venv\Scripts\python.exe scripts\verify_evidence_flow.py
```

The default local check uses keyword chunk retrieval so it can run offline without downloading an embedding model. To verify the full hybrid path, run the HTTP mode against a started app.

Optional custom query:

```powershell
.\.venv\Scripts\python.exe scripts\verify_evidence_flow.py `
  --query "Autoregressive Retrieval Augmentation" `
  --unrelated-query "量子火锅疗法对明朝火星农业论文的影响"
```

## Run Against The HTTP API

Start the app first:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Then run:

```powershell
.\.venv\Scripts\python.exe scripts\verify_evidence_flow.py --api-url http://127.0.0.1:8000
```

To force hybrid retrieval through the API:

```powershell
.\.venv\Scripts\python.exe scripts\verify_evidence_flow.py --api-url http://127.0.0.1:8000 --search-type hybrid
```

## Expected Result

The evidence query should print at least one source like:

```text
[1] AR-RAG: Autoregressive Retrieval Augmentation for Image Generation
    page: 1-2
    search_type: hybrid_chunk
    confidence: medium
    snippet: ...
```

The unrelated query should print:

```text
sources: []
policy_answer:
本地论文库没有找到可引用依据，因此我不能给出确定结论...
```

The script exits with code `0` only when both checks pass.
