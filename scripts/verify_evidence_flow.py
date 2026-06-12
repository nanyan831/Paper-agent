"""Verify chunk evidence retrieval and no-evidence refusal without calling an LLM."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


DEFAULT_QUERY = "Autoregressive Retrieval Augmentation"
DEFAULT_UNRELATED_QUERY = "量子火锅疗法对明朝火星农业论文的影响"


def page_range(source: dict) -> str:
    start = source.get("page_start")
    end = source.get("page_end")
    if start and end and start != end:
        return f"{start}-{end}"
    if start:
        return str(start)
    if end:
        return str(end)
    return "unknown"


def policy_for_hits(hits: list[dict], draft_answer: str) -> tuple[str, list[dict]]:
    apply_evidence_policy = load_apply_evidence_policy()
    messages = [
        {
            "role": "tool",
            "name": "search_chunks",
            "content": json.dumps({"success": True, "data": hits}, ensure_ascii=False),
        },
        {"role": "assistant", "content": draft_answer},
    ]
    sources = apply_evidence_policy(messages)
    return messages[-1].get("content", ""), sources


def load_apply_evidence_policy():
    try:
        from routes.agent import _apply_evidence_policy

        return _apply_evidence_policy
    except ModuleNotFoundError:
        source = (ROOT / "routes" / "agent.py").read_text(encoding="utf-8")
        start = source.index("def _short_snippet")
        end = source.index("async def _persist_agent_result")
        namespace = {
            "json": json,
            "Any": Any,
            "Optional": Optional,
            "MIN_CONFIDENT_SOURCE_COUNT": 2,
            "LOW_SCORE_THRESHOLD": 0.005,
        }
        exec(source[start:end], namespace)
        return namespace["_apply_evidence_policy"]


def print_sources(sources: list[dict]) -> None:
    if not sources:
        print("sources: []")
        return

    for index, source in enumerate(sources, start=1):
        evidence = source.get("evidence") or {}
        print(f"[{index}] {source.get('title')}")
        print(f"    paper_id: {source.get('paper_id')}")
        print(f"    chunk_id: {source.get('chunk_id')}")
        print(f"    chunk_index: {source.get('chunk_index')}")
        print(f"    page: {page_range(source)}")
        print(f"    search_type: {source.get('search_type')}")
        print(f"    search_score: {source.get('search_score')}")
        print(f"    confidence: {evidence.get('confidence')}")
        print(f"    snippet: {source.get('snippet')}")


async def search_chunks_direct(
    query: str,
    top_k: int,
    search_type: str,
    paper_id: str | None = None,
) -> list[dict]:
    from database.db import DatabaseManager
    from rag.retriever import HybridRetriever

    class DisabledVectorStore:
        def search_chunks(self, *args, **kwargs):
            raise RuntimeError("Semantic chunk search disabled in offline verification script.")

    retriever = HybridRetriever(db=DatabaseManager(), vector_store=DisabledVectorStore())
    filters = {"paper_id": paper_id} if paper_id else None
    return await retriever.search_chunks(
        query=query,
        top_k=top_k,
        filters=filters,
        search_type=search_type,
    )


def search_chunks_http(
    api_url: str,
    query: str,
    top_k: int,
    search_type: str,
    paper_id: str | None = None,
) -> list[dict]:
    params = {"q": query, "top_k": top_k, "search_type": search_type}
    if paper_id:
        params["paper_id"] = paper_id

    base = api_url.rstrip("/")
    url = f"{base}/api/search/chunks?{urlencode(params)}"
    with urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("results") or []


async def run_check(args: argparse.Namespace) -> int:
    if args.api_url:
        search = lambda q, tk, st: search_chunks_http(args.api_url, q, tk, st, args.paper_id)
    else:
        search = lambda q, tk, st: search_chunks_direct(q, tk, st, args.paper_id)

    print("== Evidence query ==")
    print(f"query: {args.query}")
    if args.api_url:
        evidence_hits = search(args.query, args.top_k, args.search_type)
    else:
        evidence_hits = await search(args.query, args.top_k, args.search_type)

    evidence_answer, evidence_sources = policy_for_hits(
        evidence_hits,
        "根据本地 chunk，AR-RAG 的核心是检索增强。",
    )
    print_sources(evidence_sources)
    print("policy_answer:")
    print(evidence_answer)

    print("\n== No-evidence query ==")
    print(f"query: {args.unrelated_query}")
    if args.api_url:
        no_hits = search(args.unrelated_query, args.top_k, args.unrelated_search_type)
    else:
        no_hits = await search(args.unrelated_query, args.top_k, args.unrelated_search_type)

    no_answer, no_sources = policy_for_hits(no_hits, "这是一个应该被拒绝的确定回答。")
    print_sources(no_sources)
    print("policy_answer:")
    print(no_answer)

    failures = []
    if not evidence_sources:
        failures.append("evidence query returned no sources")
    if no_sources:
        failures.append("unrelated query unexpectedly returned sources")
    if "本地论文库没有找到可引用依据" not in no_answer:
        failures.append("no-evidence policy did not refuse")

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nPASSED: evidence flow and no-evidence refusal look healthy.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Paper Agent evidence retrieval without calling an LLM."
    )
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--unrelated-query", default=DEFAULT_UNRELATED_QUERY)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--search-type", default="keyword", choices=["hybrid", "semantic", "keyword"])
    parser.add_argument(
        "--unrelated-search-type",
        default="keyword",
        choices=["hybrid", "semantic", "keyword"],
        help="Use keyword by default so the no-evidence check is strict.",
    )
    parser.add_argument("--paper-id", default=None)
    parser.add_argument(
        "--api-url",
        default=None,
        help="Optional running app URL, e.g. http://127.0.0.1:8000. If omitted, uses local retriever.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_check(parse_args())))
