"""Smoke test PDF source jumping contracts without calling an LLM.

This verifies the pieces behind the browser flow:
1. The app shell exposes the evidence lookup and PDF reader DOM.
2. The frontend has the source jump entrypoint and safe click wiring.
3. The chunks API returns a real paper_id and page_start/page_end.
4. The PDF endpoint serves an application/pdf response for that paper.

Run with a local server:
    python scripts/smoke_pdf_source_jump.py --api-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_PAPER_ID = "86abd4f8-ba13-4eb5-8169-2d18c798b2b2"
DEFAULT_QUERY = "Autoregressive Retrieval Augmentation"


def fetch_text(url: str, timeout: int = 30) -> str:
    with urlopen(url, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_json(url: str, timeout: int = 30) -> dict[str, Any]:
    return json.loads(fetch_text(url, timeout=timeout))


def fetch_headers(url: str, timeout: int = 30) -> tuple[int, str, int]:
    request = Request(url, method="GET")
    with urlopen(request, timeout=timeout) as response:
        response.read(1024)
        content_type = response.headers.get("content-type", "")
        length = int(response.headers.get("content-length") or 0)
        return response.status, content_type, length


def assert_contains(label: str, haystack: str, needles: list[str]) -> list[str]:
    return [f"{label} missing {needle!r}" for needle in needles if needle not in haystack]


def check_static_contracts(api_url: str) -> list[str]:
    failures: list[str] = []
    html = fetch_text(api_url.rstrip("/") + "/")
    app_js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")

    failures.extend(
        assert_contains(
            "index.html",
            html,
            [
                'id="evidenceInput"',
                'id="evidenceLookupBtn"',
                'id="view-reader"',
                'id="readerPageInput"',
                'id="readerPageCount"',
                'id="pdfCanvas"',
            ],
        )
    )
    failures.extend(
        assert_contains(
            "app.js",
            app_js,
            [
                "function normalizeSourceItem",
                "window.openPdfSource = async",
                "renderEvidenceResults",
                "reader-open-btn",
                "openPdfSource(sourceBtn.dataset.paperId",
                "{ closeChat: true }",
            ],
        )
    )
    if "item.paper_id || item.paperId || ''" not in app_js:
        failures.append("app.js should only jump when a real paper_id/paperId is present")
    return failures


def check_chunk_and_pdf(api_url: str, query: str, paper_id: str) -> list[str]:
    failures: list[str] = []
    base = api_url.rstrip("/")
    params = urlencode(
        {
            "q": query,
            "search_type": "hybrid",
            "top_k": 5,
            "paper_id": paper_id,
        }
    )
    chunks = fetch_json(f"{base}/api/search/chunks?{params}").get("results") or []
    if not chunks:
        return [f"chunks API returned no results for paper {paper_id}"]

    jumpable = []
    for chunk in chunks:
        if chunk.get("paper_id") != paper_id:
            failures.append(f"chunk has unexpected paper_id: {chunk.get('paper_id')!r}")
        page = chunk.get("page_start") or chunk.get("page")
        if not isinstance(page, int) or page < 1:
            failures.append(f"chunk has invalid page_start/page: {page!r}")
        if not chunk.get("content") and not chunk.get("snippet"):
            failures.append(f"chunk {chunk.get('id')!r} has no content/snippet")
        if chunk.get("paper_id") and isinstance(page, int) and page > 0:
            jumpable.append((chunk.get("paper_id"), page))

    if not jumpable:
        failures.append("no chunk can produce a paper_id + positive page jump")

    status, content_type, length = fetch_headers(f"{base}/api/papers/{paper_id}/pdf")
    if status != 200:
        failures.append(f"PDF endpoint returned status {status}")
    if "application/pdf" not in content_type.lower():
        failures.append(f"PDF endpoint returned content-type {content_type!r}")
    if length <= 0:
        failures.append("PDF endpoint did not report a positive content-length")

    print("first_jump:", {"paper_id": jumpable[0][0], "page": jumpable[0][1]} if jumpable else None)
    print("chunk_count:", len(chunks))
    print("pdf:", {"status": status, "content_type": content_type, "length": length})
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test PDF source jump contracts.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--paper-id", default=DEFAULT_PAPER_ID)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        failures = check_static_contracts(args.api_url)
        failures.extend(check_chunk_and_pdf(args.api_url, args.query, args.paper_id))
    except URLError as exc:
        print(f"FAILED: could not reach {args.api_url}: {exc}", file=sys.stderr)
        return 1

    if failures:
        print("FAILED:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PASSED: PDF source jump contracts look healthy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
