import re
import uuid
from pathlib import Path

from pypdf import PdfReader


MAX_CHUNK_CHARS = 2600
OVERLAP_CHARS = 300


def extract_pdf_pages(file_path: str | Path) -> list[dict]:
    """Extract text by page from a PDF."""
    reader = PdfReader(str(file_path))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = normalize_text(text)
        if text:
            pages.append({"page": index, "text": text})
    return pages


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_pdf_pages(paper_id: str, pages: list[dict]) -> list[dict]:
    """Build reading-order chunks with page metadata."""
    chunks = []
    current_parts = []
    current_len = 0
    page_start = None
    page_end = None
    chunk_index = 0

    def emit_chunk():
        nonlocal current_parts, current_len, page_start, page_end, chunk_index
        content = normalize_text("\n\n".join(current_parts))
        if not content:
            return
        chunks.append({
            "id": f"{paper_id}:chunk:{chunk_index}",
            "paper_id": paper_id,
            "chunk_index": chunk_index,
            "section": infer_section(content),
            "page_start": page_start,
            "page_end": page_end,
            "content": content,
            "token_count": estimate_tokens(content),
        })
        chunk_index += 1
        overlap = content[-OVERLAP_CHARS:] if len(content) > OVERLAP_CHARS else ""
        current_parts = [overlap] if overlap else []
        current_len = len(overlap)
        page_start = page_end if overlap else None

    for page in pages:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page["text"]) if p.strip()]
        for paragraph in paragraphs:
            if page_start is None:
                page_start = page["page"]
            page_end = page["page"]

            if current_len and current_len + len(paragraph) > MAX_CHUNK_CHARS:
                emit_chunk()
                if page_start is None:
                    page_start = page["page"]
                page_end = page["page"]

            current_parts.append(paragraph)
            current_len += len(paragraph) + 2

    emit_chunk()
    return chunks


def infer_section(content: str) -> str:
    first_line = content.splitlines()[0].strip().lower() if content else ""
    section_patterns = {
        "abstract": r"^(abstract|摘要)",
        "introduction": r"^(introduction|引言|绪论)",
        "methods": r"^(method|methods|methodology|方法|研究方法)",
        "results": r"^(result|results|结果)",
        "discussion": r"^(discussion|讨论)",
        "conclusion": r"^(conclusion|conclusions|结论)",
        "references": r"^(references|参考文献)",
    }
    for section, pattern in section_patterns.items():
        if re.search(pattern, first_line):
            return section
    return "body"


def estimate_tokens(text: str) -> int:
    # Mixed Chinese/English approximation, good enough for budgeting metadata.
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    non_cjk = re.sub(r"[\u4e00-\u9fff]", " ", text)
    words = len(re.findall(r"\S+", non_cjk))
    return max(1, cjk_chars + int(words * 1.3))


def build_pdf_paper(
    title: str,
    authors: str = "",
    abstract: str = "",
    keywords: str = "",
    file_path: str = "",
    full_text: str = "",
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "keywords": keywords,
        "source": "local_pdf",
        "file_path": file_path,
        "full_text": full_text,
        "parse_status": "full_text" if full_text else "parse_failed",
        "language": "zh",
    }
