"""MVP smoke test — one-shot health check, no LLM calls, no DeepSeek tokens.

Run with a local server:
    python scripts/mvp_smoke.py --api-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_API_URL = "http://127.0.0.1:8000"


def _get(url: str, timeout: int = 15) -> tuple[int, str]:
    req = Request(url, method="GET")
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
        return resp.status, body


def _get_json(url: str, timeout: int = 15) -> tuple[int, Any]:
    status, body = _get(url, timeout=timeout)
    return status, json.loads(body)


def _check(label: str, ok: bool) -> None:
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {label}")


def check_static(api_url: str) -> bool:
    print("\n== Static assets ==")
    all_ok = True
    for path in ["/", "/js/app.js", "/css/style.css"]:
        try:
            status, _ = _get(api_url.rstrip("/") + path)
            ok = status == 200
            _check(f"GET {path} -> {status}", ok)
            if not ok:
                all_ok = False
        except Exception as exc:
            _check(f"GET {path} -> ERROR: {exc}", False)
            all_ok = False
    return all_ok


def check_readiness(api_url: str) -> tuple[bool, dict[str, Any]]:
    print("\n== Readiness ==")
    try:
        status, data = _get_json(api_url.rstrip("/") + "/api/readiness")
        if status != 200:
            _check(f"/api/readiness -> {status}", False)
            return False, {}

        required = [
            "api_key_configured", "local_pdf_count", "searchable_pdf_count",
            "chunk_count", "status", "blockers", "warnings",
        ]
        missing = [k for k in required if k not in data]
        if missing:
            _check(f"missing fields: {missing}", False)
            return False, data

        _check("all required fields present", True)
        print(f"  api_key_configured : {data['api_key_configured']}")
        print(f"  local_pdf_count    : {data['local_pdf_count']}")
        print(f"  searchable_pdf     : {data['searchable_pdf_count']}")
        print(f"  chunk_count        : {data['chunk_count']}")
        print(f"  status             : {data['status']}")
        print(f"  blockers           : {data['blockers']}")
        print(f"  warnings           : {data['warnings']}")
        return True, data
    except Exception as exc:
        _check(f"/api/readiness -> ERROR: {exc}", False)
        return False, {}


def check_stats(api_url: str) -> bool:
    print("\n== Stats ==")
    try:
        status, _ = _get_json(api_url.rstrip("/") + "/api/stats")
        ok = status == 200
        _check(f"/api/stats -> {status}", ok)
        return ok
    except Exception as exc:
        _check(f"/api/stats -> ERROR: {exc}", False)
        return False


def check_search_chunks(api_url: str) -> bool:
    print("\n== Search chunks ==")
    try:
        url = api_url.rstrip("/") + "/api/search/chunks?q=RAG&top_k=3"
        status, data = _get_json(url)
        if status != 200:
            _check(f"/api/search/chunks -> {status}", False)
            return False

        results = data.get("results")
        if not results:
            _check("results is empty", False)
            return False

        _check("results non-empty", True)
        first = results[0]
        has_location = any(k in first for k in ("paper_id", "page_start", "page_end", "title"))
        _check(f"first result has paper_id/page_start/page_end/title", has_location)
        return has_location
    except Exception as exc:
        _check(f"/api/search/chunks -> ERROR: {exc}", False)
        return False


def run_subcheck_if_exists(api_url: str) -> bool:
    print("\n== Sub-check: smoke_pdf_source_jump ==")
    from pathlib import Path
    sub = Path(__file__).resolve().parent / "smoke_pdf_source_jump.py"
    if not sub.exists():
        print("  [SKIP] smoke_pdf_source_jump.py not found")
        return True

    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(sub), "--api-url", api_url],
            capture_output=True, text=True, timeout=30,
        )
        print(result.stdout.rstrip())
        if result.returncode != 0:
            if result.stderr:
                print(result.stderr.rstrip())
            return False
        return True
    except Exception as exc:
        _check(f"sub-check failed: {exc}", False)
        return False


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MVP one-shot smoke test (no LLM tokens).")
    p.add_argument("--api-url", default=DEFAULT_API_URL)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    api = args.api_url.rstrip("/")
    results: list[bool] = []

    try:
        _get(api, timeout=5)
    except (URLError, OSError) as exc:
        print(f"FAILED: cannot reach {api}: {exc}", file=sys.stderr)
        return 1

    results.append(check_static(api))

    ok, readiness = check_readiness(api)
    results.append(ok)

    results.append(check_stats(api))

    if readiness.get("searchable_pdf_count", 0) > 0:
        results.append(check_search_chunks(api))
    else:
        print("\n== Search chunks ==")
        print("  [SKIP] searchable_pdf_count == 0, skipping chunk search")

    results.append(run_subcheck_if_exists(api))

    print("\n" + "=" * 40)
    if all(results):
        print("ALL PASSED")
        return 0
    else:
        print("SOME CHECKS FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
