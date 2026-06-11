import uuid
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from typing import Optional

from config import PDF_DIR
from rag.pdf_processor import extract_pdf_pages, chunk_pdf_pages, build_pdf_paper

router = APIRouter(prefix="/api/papers", tags=["Papers"])


async def _import_pdf_upload(
    request: Request,
    file: UploadFile,
    title: Optional[str] = None,
    authors: str = "",
    abstract: str = "",
    keywords: str = "",
) -> dict:
    filename = file.filename or "unnamed.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    db = request.app.state.db
    vs = request.app.state.vector_store

    paper_id = str(uuid.uuid4())
    file_path = PDF_DIR / f"{paper_id}.pdf"

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty")
    file_path.write_bytes(content)

    try:
        pages = extract_pdf_pages(file_path)
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {e}")

    full_text = "\n\n".join(page["text"] for page in pages)
    resolved_title = title or Path(filename).stem
    paper = build_pdf_paper(
        title=resolved_title,
        authors=authors,
        abstract=abstract,
        keywords=keywords,
        file_path=str(file_path),
        full_text=full_text,
    )
    paper["id"] = paper_id

    saved_id = await db.add_paper(paper)
    if not saved_id:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="Paper already exists or could not be inserted")

    chunks = chunk_pdf_pages(saved_id, pages) if pages else []
    if chunks:
        await db.replace_paper_chunks(saved_id, chunks)
        vs.add_chunks_batch(chunks)

    return {
        "success": True,
        "filename": filename,
        "paper_id": saved_id,
        "title": resolved_title,
        "parse_status": paper["parse_status"],
        "pages": len(pages),
        "chunks": len(chunks),
    }

@router.get("")
async def list_papers(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    source: Optional[str] = None,
    favorited: bool = False
):
    db = request.app.state.db
    offset = (page - 1) * limit
    
    result = await db.list_papers(
        offset=offset, 
        limit=limit, 
        source=source,
        favorited_only=favorited
    )
    return result

@router.post("/upload-pdf")
async def upload_pdf_paper(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    authors: str = Form(""),
    abstract: str = Form(""),
    keywords: str = Form("")
):
    return await _import_pdf_upload(
        request,
        file,
        title=title,
        authors=authors,
        abstract=abstract,
        keywords=keywords,
    )


@router.post("/upload-pdfs")
async def upload_pdf_papers(
    request: Request,
    files: list[UploadFile] = File(...),
    title: Optional[str] = Form(None),
    authors: str = Form(""),
    abstract: str = Form(""),
    keywords: str = Form("")
):
    results = []
    for file in files:
        filename = file.filename or "unnamed.pdf"
        try:
            result = await _import_pdf_upload(
                request,
                file,
                title=title if len(files) == 1 else None,
                authors=authors,
                abstract=abstract,
                keywords=keywords,
            )
            results.append(result)
        except HTTPException as e:
            results.append({
                "success": False,
                "filename": filename,
                "error": str(e.detail),
            })
        except Exception as e:
            results.append({
                "success": False,
                "filename": filename,
                "error": f"Unexpected import error: {e}",
            })

    succeeded = sum(1 for item in results if item.get("success"))
    failed = len(results) - succeeded
    return {
        "success": failed == 0,
        "total": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }


@router.get("/{paper_id}/pdf")
async def get_paper_pdf(request: Request, paper_id: str):
    db = request.app.state.db
    paper = await db.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    file_path = paper.get("file_path")
    if not file_path:
        raise HTTPException(status_code=404, detail="PDF file not found for this paper")

    resolved_pdf_dir = PDF_DIR.resolve()
    resolved_file = Path(file_path).resolve()
    try:
        resolved_file.relative_to(resolved_pdf_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="PDF path is outside the allowed directory")

    if not resolved_file.exists() or not resolved_file.is_file():
        raise HTTPException(status_code=404, detail="PDF file is missing on disk")

    filename = f"{paper.get('title') or paper_id}.pdf"
    return FileResponse(
        path=str(resolved_file),
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="inline",
    )


@router.get("/{paper_id}")
async def get_paper(request: Request, paper_id: str):
    db = request.app.state.db
    paper = await db.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # 获取标签
    tags = await db.get_tags(paper_id)
    paper["tags"] = tags
    return paper

@router.get("/{paper_id}/chunks")
async def get_paper_chunks(
    request: Request,
    paper_id: str,
    limit: int = Query(50, ge=1, le=200)
):
    db = request.app.state.db
    paper = await db.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    chunks = await db.get_paper_chunks(paper_id, limit=limit)
    return {"paper_id": paper_id, "chunks": chunks}

@router.delete("/{paper_id}")
async def delete_paper(request: Request, paper_id: str):
    db = request.app.state.db
    vs = request.app.state.vector_store
    paper = await db.get_paper(paper_id)
    
    success = await db.delete_paper(paper_id)
    if success:
        vs.delete_paper(paper_id)
        if paper and paper.get("file_path"):
            Path(paper["file_path"]).unlink(missing_ok=True)
        return {"success": True}
    raise HTTPException(status_code=404, detail="Paper not found")

@router.post("/{paper_id}/favorite")
async def toggle_favorite(request: Request, paper_id: str):
    db = request.app.state.db
    new_status = await db.toggle_favorite(paper_id)
    if new_status is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return {"success": True, "is_favorited": new_status}
