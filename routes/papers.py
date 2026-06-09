import uuid
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Query, UploadFile, File, Form
from typing import Optional

from config import PDF_DIR
from rag.pdf_processor import extract_pdf_pages, chunk_pdf_pages, build_pdf_paper

router = APIRouter(prefix="/api/papers", tags=["Papers"])

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
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    db = request.app.state.db
    vs = request.app.state.vector_store

    paper_id = str(uuid.uuid4())
    safe_name = f"{paper_id}.pdf"
    file_path = PDF_DIR / safe_name

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
    resolved_title = title or Path(file.filename).stem
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
        "paper_id": saved_id,
        "title": resolved_title,
        "parse_status": paper["parse_status"],
        "pages": len(pages),
        "chunks": len(chunks),
    }

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
