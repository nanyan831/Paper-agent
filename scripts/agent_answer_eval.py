"""Agent answer quality evaluation - calls /api/agent/chat, consumes DeepSeek tokens.

Run with a local server:
    python scripts/agent_answer_eval.py --api-url http://127.0.0.1:8000          # dry-run
    python scripts/agent_answer_eval.py --yes                                     # all 5 questions
    python scripts/agent_answer_eval.py --yes --limit 1                           # single-question smoke test
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

DEFAULT_API_URL = "http://127.0.0.1:8000"

QUESTIONS = [
    "RAG 为什么能降低幻觉？",
    "RAG 有哪些主要范式？",
    "RAG 评估关注哪些指标？",
    "多模态 RAG 有哪些方向？",
    "AR-RAG 解决了什么问题？",
]


def _post_json(url: str, payload: dict, timeout: int = 120) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
        return resp.status, json.loads(raw)


def _check_health(api_url: str) -> bool:
    try:
        req = Request(api_url, method="GET")
        with urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except (URLError, OSError):
        return False


def _eval_source(source: dict) -> list[str]:
    warnings: list[str] = []
    if not source.get("title") and not source.get("paper_id"):
        warnings.append("source missing title/paper_id")
    if not source.get("page_start") and not source.get("page_end"):
        warnings.append("source missing page_start/page_end")
    if not source.get("snippet"):
        warnings.append("source missing snippet")
    return warnings


def evaluate_question(api_url: str, question: str) -> dict:
    chat_url = api_url + "/api/agent/chat"
    payload = {"message": question}
    session_id = str(uuid.uuid4())

    print(f"\n{'=' * 60}")
    print(f"Q: {question}")
    print(f"  session_id: {session_id}")

    result: dict = {
        "question": question,
        "session_id": session_id,
        "status": "ERROR",
        "answer_length": 0,
        "answer_preview": "",
        "sources_count": 0,
        "sources": [],
        "confidence_stats": {},
        "warnings": [],
    }

    try:
        status_code, data = _post_json(chat_url, payload, timeout=120)
    except HTTPError as exc:
        result["warnings"].append(f"HTTP {exc.code}: {exc.reason}")
        print(f"  [ERROR] HTTP {exc.code}: {exc.reason}")
        return result
    except (URLError, OSError) as exc:
        result["warnings"].append(f"Connection error: {exc}")
        print(f"  [ERROR] Connection: {exc}")
        return result

    if status_code != 200:
        result["warnings"].append(f"HTTP {status_code}")
        print(f"  [ERROR] HTTP {status_code}")
        return result

    result["session_id"] = data.get("session_id", session_id)
    result["usage"] = data.get("usage", {})

    messages = data.get("messages") or []
    assistant_content = ""
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and (msg.get("content") or "").strip():
            assistant_content = msg["content"]
            break
    result["answer_length"] = len(assistant_content)
    result["answer_preview"] = assistant_content[:200].replace("\n", " ")
    print(f"  answer length: {result['answer_length']}")

    sources = data.get("sources") or []
    result["sources_count"] = len(sources)
    result["sources"] = sources
    print(f"  sources: {len(sources)}")

    confidence_stats: dict[str, int] = {}
    source_warnings: list[str] = []
    for idx, src in enumerate(sources):
        conf = (src.get("evidence") or {}).get("confidence", "unknown")
        confidence_stats[conf] = confidence_stats.get(conf, 0) + 1
        for w in _eval_source(src):
            source_warnings.append(f"source[{idx}]: {w}")
    result["confidence_stats"] = confidence_stats
    result["warnings"].extend(source_warnings)

    if not assistant_content.strip():
        result["warnings"].append("empty answer")
    if not sources:
        result["warnings"].append("no sources returned")

    verdict = _verdict(result)
    result["status"] = verdict
    print(f"  [{verdict}] confidence={confidence_stats}, sources={len(sources)}")
    if result["warnings"]:
        print(f"  warnings: {result['warnings']}")
    return result


def _verdict(result: dict) -> str:
    if result["sources_count"] == 0:
        return "FAIL"
    conf = result["confidence_stats"]
    if result["sources_count"] < 2 or conf.get("low", 0) > 0 or conf.get("unknown", 0) > 0:
        return "WARN"
    return "PASS"


def main() -> int:
    p = argparse.ArgumentParser(description="Agent answer quality evaluation (consumes DeepSeek tokens).")
    p.add_argument("--api-url", default=DEFAULT_API_URL, help="API base URL (default: %(default)s)")
    p.add_argument("--yes", action="store_true", help="Confirm execution; without this flag the script exits with code 2")
    p.add_argument("--limit", type=int, default=0, help="Limit number of questions to evaluate (0 = all)")
    args = p.parse_args()

    api = args.api_url.rstrip("/")

    if not args.yes:
        print("WARNING: This script calls /api/agent/chat and consumes DeepSeek tokens.\n")
        print("Questions that will be tested:")
        for i, q in enumerate(QUESTIONS, 1):
            print(f"  {i}. {q}")
        print(f"\nTotal: {len(QUESTIONS)} questions")
        print(f"API URL: {api}")
        print(f"\nRun with --yes to execute, or --yes --limit 1 for a single-question smoke test.")
        return 2

    print(f"Agent Answer Evaluation")
    print(f"API URL: {api}")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")

    if not _check_health(api):
        print(f"\nFAILED: cannot reach {api}", file=sys.stderr)
        return 1

    questions = QUESTIONS
    if args.limit > 0:
        questions = QUESTIONS[: args.limit]
    print(f"Questions to evaluate: {len(questions)}")

    results: list[dict] = []
    for q in questions:
        results.append(evaluate_question(api, q))

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    warn_count = sum(1 for r in results if r["status"] == "WARN")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")

    total_input = sum((r.get("usage") or {}).get("input_tokens", 0) for r in results)
    total_output = sum((r.get("usage") or {}).get("output_tokens", 0) for r in results)
    total_tokens = sum((r.get("usage") or {}).get("total_tokens", 0) for r in results)

    print(f"\n{'=' * 60}")
    print(f"Summary: {pass_count} PASS / {warn_count} WARN / {fail_count} FAIL")
    print(f"Total tokens: {total_tokens} (input={total_input}, output={total_output})")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "api_url": api,
        "questions_evaluated": len(results),
        "summary": {
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
        },
        "total_tokens": total_tokens,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "results": results,
    }

    reports_dir = Path(__file__).resolve().parent.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"agent_answer_eval_{ts}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to: {report_path}")

    if fail_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
