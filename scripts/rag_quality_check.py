#!/usr/bin/env python3
"""Local RAG evidence-chain quality self-check (no DeepSeek, no token cost)."""

import argparse
import json
import sys
import urllib.request
import urllib.parse
import urllib.error

QUERIES = [
    "RAG",
    "retrieval augmented generation",
    "evidence",
    "evaluation",
]


def fetch_chunks(api_url: str, query: str, top_k: int = 5) -> list[dict]:
    params = urllib.parse.urlencode({"q": query, "top_k": top_k})
    url = f"{api_url}/api/search/chunks?{params}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        print(f"  [ERROR] request failed: {exc}", file=sys.stderr)
        return []
    if isinstance(data, dict):
        return data.get("results") or data.get("chunks") or data.get("data") or []
    if isinstance(data, list):
        return data
    return []


def validate_result(result: dict) -> tuple[bool, str]:
    has_id_fields = bool(result.get("title") or result.get("paper_id"))
    has_content = bool(result.get("snippet") or result.get("content"))
    has_page = bool(result.get("page_start") is not None or result.get("page_end") is not None)
    if not has_id_fields or not has_content:
        return False, "missing title/paper_id or snippet/content"
    if not has_page:
        return False, "missing page_start/page_end"
    return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG evidence-chain quality check")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--top-k", type=int, default=5, help="Chunks per query")
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")
    all_pass = True
    scores_all: list[float] = []

    print(f"RAG Quality Check -- target: {api_url}\n")

    for q in QUERIES:
        chunks = fetch_chunks(api_url, q, args.top_k)
        print(f"Query: \"{q}\"")
        print(f"  Hits: {len(chunks)}")

        if not chunks:
            print("  FAIL: no results returned")
            all_pass = False
            print()
            continue

        first = chunks[0]
        first_title = first.get("title") or first.get("paper_id") or "(unknown)"
        first_page = first.get("page_start") or first.get("page_end") or "N/A"

        print(f"  First page: {first_page}")
        print(f"  First title: {first_title}")

        valid = 0
        invalid_reasons: list[str] = []
        query_scores: list[float] = []

        for i, chunk in enumerate(chunks):
            ok, reason = validate_result(chunk)
            if ok:
                valid += 1
            else:
                invalid_reasons.append(f"    chunk[{i}]: {reason}")
            score = chunk.get("score") or chunk.get("search_score")
            if score is not None:
                try:
                    query_scores.append(float(score))
                except (ValueError, TypeError):
                    pass

        if query_scores:
            lo, hi = min(query_scores), max(query_scores)
            print(f"  Score range: {lo:.4f} - {hi:.4f}")
            scores_all.extend(query_scores)
        else:
            print("  Score range: N/A")

        if valid < len(chunks):
            print(f"  WARN: {len(chunks) - valid}/{len(chunks)} chunks failed field check:")
            for r in invalid_reasons:
                print(r)

        if len(chunks) < 1:
            print("  FAIL: fewer than 1 result")
            all_pass = False
        elif valid < len(chunks):
            all_pass = False

        print()

    print("=" * 50)
    if all_pass:
        print("RESULT: PASS")
    else:
        print("RESULT: FAIL")
    print("=" * 50)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
