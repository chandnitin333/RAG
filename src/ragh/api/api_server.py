"""RAGH API. High-level RAG over Book Mapping + Command Capsule corpora.

Endpoints:
  POST /v1/upload                Upload one-off files into the index.
  POST /v1/query                 Ask a question; returns answer + citations.
  POST /v1/ingest-corpus         Walk in-place corpus and ingest into vector DB.
  POST /v1/manifest/rebuild      Rebuild the corpus manifest only.
  POST /v1/bm25/rebuild          Rebuild BM25 index from current vector store.
  GET  /v1/manifest/summary      Summary of cataloged files.
  GET  /v1/stats                 Index size + backend info.
  GET  /v1/health
"""
from pathlib import Path
from typing import List, Optional, Dict, Any
import asyncio
import json
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from loguru import logger

from ragh.config import settings
from ragh.embeddings.embedder import Embedder
from ragh.vectordb.factory import get_vector_store
from ragh.retriever.retriever import Retriever
from ragh.retriever.bm25 import BM25Retriever
from ragh.retriever.reranker import Reranker
from ragh.reader.reader import Reader
from ragh.pipeline.rag_pipeline import RAGPipeline
from ragh.pipeline.chat import ChatPipeline
from ragh.reader.ollama_reader import OllamaReader
from ragh.training.feedback_store import get_feedback_store
from ragh.training.personalization import get_personalization_store
from ragh.pipeline.agents import all_agents
from ragh.ingestion.loaders import extract_text_from_bytes
from ragh.ingestion.chunker import chunk_text
from ragh.corpus.manifest import build_manifest, load_manifest, manifest_summary
from ragh.corpus.ingestor import CorpusIngestor


# ============================ bootstrap ============================
app = FastAPI(title="RAGH — High-Level RAG", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("Booting RAGH | backend={}", settings.VECTOR_DB)
embedder = Embedder()
store = get_vector_store(dim=embedder.embedding_dim)

bm25 = BM25Retriever()
if not bm25.load() and store.count() > 0:
    bm25.build(store.get_all_documents())

reranker = Reranker() if settings.USE_RERANKER else None
retriever = Retriever(embedder, store, bm25=bm25)


def _build_reader():
    """Pick a reader based on settings.READER_BACKEND.

    "auto" prefers Ollama if it's reachable, otherwise falls back to flan-t5.
    """
    from ragh.reader.ollama_reader import OllamaReader

    backend = settings.READER_BACKEND
    if backend == "auto":
        backend = "ollama" if OllamaReader.is_available(settings.OLLAMA_URL) else "flan-t5"
        logger.info("Reader backend (auto-selected): {}", backend)

    if backend == "ollama":
        return OllamaReader()
    if backend == "extractive":
        return Reader(mode="extractive")
    return Reader(mode="generative")


reader = _build_reader()
pipeline = RAGPipeline(retriever, reader, reranker=reranker)

# Chat pipeline only works when reader is Ollama (multi-turn + query rewrite).
chat_pipeline: Optional[ChatPipeline] = (
    ChatPipeline(retriever=retriever, reader=reader, reranker=reranker)
    if isinstance(reader, OllamaReader)
    else None
)
ingestor = CorpusIngestor(embedder, store)


# ============================ schemas ============================
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=settings.TOP_K, ge=1, le=50)
    subject: Optional[str] = None
    book: Optional[str] = None
    chapter: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    mode: Optional[str] = None
    citations: List[Dict[str, Any]] = []
    retrieved: List[Dict[str, Any]] = []


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    top_k: int = Field(default=settings.TOP_K, ge=1, le=20)
    subject: Optional[str] = None
    book: Optional[str] = None
    chapter: Optional[str] = None
    interaction_id: Optional[str] = None  # client-provided so feedback can be linked
    user_id: Optional[str] = None
    agent: Optional[str] = None  # solver | teacher | diagram | planner; auto if None


class ChatResponse(BaseModel):
    answer: str
    corrected_query: str
    mode: Optional[str] = None
    citations: List[Dict[str, Any]] = []
    retrieved: List[Dict[str, Any]] = []
    interaction_id: Optional[str] = None
    agent: Optional[str] = None
    agent_label: Optional[str] = None


class FeedbackRequest(BaseModel):
    interaction_id: str
    rating: int = Field(..., ge=-1, le=1)
    corrected_answer: Optional[str] = None
    note: Optional[str] = None


class IngestRequest(BaseModel):
    rebuild_manifest: bool = False
    rebuild_index: bool = False
    limit: Optional[int] = None
    subject: Optional[str] = None
    book: Optional[str] = None


# ============================ endpoints ============================
@app.get("/v1/health")
def health():
    return {"status": "ok", "backend": settings.VECTOR_DB, "indexed": store.count()}


@app.get("/v1/stats")
def stats():
    reader_label = (
        f"ollama:{settings.OLLAMA_MODEL}"
        if reader.__class__.__name__ == "OllamaReader"
        else settings.READER_MODEL
    )
    return {
        "backend": settings.VECTOR_DB,
        "indexed_chunks": store.count(),
        "bm25_records": len(bm25.records),
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dim": embedder.embedding_dim,
        "reranker_enabled": settings.USE_RERANKER,
        "reader_model": reader_label,
    }


@app.get("/v1/manifest/summary")
def manifest_summary_route():
    return manifest_summary(load_manifest())


@app.post("/v1/manifest/rebuild")
def manifest_rebuild():
    entries = build_manifest(write=True)
    return {"status": "ok", "summary": manifest_summary(entries)}


@app.post("/v1/ingest-corpus")
async def ingest_corpus(req: IngestRequest):
    if req.rebuild_manifest:
        build_manifest(write=True)
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: ingestor.ingest_manifest(
                entries=None,
                rebuild=req.rebuild_index,
                limit=req.limit,
                subject=req.subject,
                book=req.book,
            ),
        )
    except Exception as e:
        logger.exception("Corpus ingest failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

    # rebuild BM25 over the freshly populated vector store
    bm25.build(store.get_all_documents())
    return {"status": "ok", **result}


@app.post("/v1/bm25/rebuild")
def bm25_rebuild():
    bm25.build(store.get_all_documents())
    return {"status": "ok", "records": len(bm25.records)}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if chat_pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="Chat needs the Ollama reader. Install Ollama, run 'ollama serve', then restart the API.",
        )
    where: Dict[str, Any] = {}
    if req.subject:
        where["subject"] = req.subject
    if req.book:
        where["book"] = req.book
    if req.chapter:
        where["chapter"] = req.chapter
    msgs = [{"role": m.role, "content": m.content} for m in req.messages]
    interaction_id = req.interaction_id or uuid.uuid4().hex
    try:
        resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: chat_pipeline.chat(
                msgs,
                top_k=req.top_k,
                where=where or None,
                agent_override=req.agent,
            ),
        )
        latest_user = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
        try:
            get_feedback_store().log_interaction(
                interaction_id=interaction_id,
                question=latest_user,
                corrected_query=resp.get("corrected_query", ""),
                answer=resp.get("answer", ""),
                citations=resp.get("citations", []),
                user_id=req.user_id,
                subject=req.subject,
                book=req.book,
                chapter=req.chapter,
            )
            get_personalization_store().log(
                user_id=req.user_id or "anonymous",
                subject=req.subject,
                book=req.book,
                chapter=req.chapter,
                agent=resp.get("agent"),
                question=latest_user,
                corrected=resp.get("corrected_query", ""),
                interaction_id=interaction_id,
            )
        except Exception as e:
            logger.warning("interaction log failed: {}", e)
        resp["interaction_id"] = interaction_id
        return resp
    except Exception as e:
        logger.exception("Chat failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat/stream")
async def chat_stream(req: ChatRequest):
    if chat_pipeline is None:
        raise HTTPException(status_code=503, detail="Ollama not available")
    where: Dict[str, Any] = {}
    if req.subject: where["subject"] = req.subject
    if req.book: where["book"] = req.book
    if req.chapter: where["chapter"] = req.chapter
    msgs = [{"role": m.role, "content": m.content} for m in req.messages]
    interaction_id = req.interaction_id or uuid.uuid4().hex

    answer_parts: List[str] = []
    seen_corrected: Dict[str, str] = {"q": ""}
    seen_agent: Dict[str, str] = {"a": ""}
    seen_citations: List[Any] = []

    def gen():
        # send the interaction_id immediately so the client can link feedback
        yield json.dumps({"type": "interaction_id", "data": interaction_id}) + "\n"
        for ev in chat_pipeline.chat_stream(
            msgs, top_k=req.top_k, where=where or None, agent_override=req.agent
        ):
            if ev["type"] == "corrected":
                seen_corrected["q"] = ev["data"]
            elif ev["type"] == "agent":
                seen_agent["a"] = ev["data"].get("agent", "")
            elif ev["type"] == "citations":
                seen_citations.extend(ev["data"])
            elif ev["type"] == "token":
                answer_parts.append(ev["data"])
            yield json.dumps(ev) + "\n"

        # persist after streaming finishes
        try:
            latest_user = next(
                (m["content"] for m in reversed(msgs) if m["role"] == "user"), ""
            )
            full_answer = "".join(answer_parts)
            get_feedback_store().log_interaction(
                interaction_id=interaction_id,
                question=latest_user,
                corrected_query=seen_corrected["q"],
                answer=full_answer,
                citations=seen_citations,
                user_id=req.user_id,
                subject=req.subject,
                book=req.book,
                chapter=req.chapter,
            )
            get_personalization_store().log(
                user_id=req.user_id or "anonymous",
                subject=req.subject,
                book=req.book,
                chapter=req.chapter,
                agent=seen_agent["a"],
                question=latest_user,
                corrected=seen_corrected["q"],
                interaction_id=interaction_id,
            )
        except Exception as e:
            logger.warning("post-stream log failed: {}", e)

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.get("/v1/agents")
def list_agents():
    return {"agents": all_agents()}


@app.get("/v1/personal/insights")
def personal_insights(user_id: str = Query(...), days: int = Query(default=30, ge=1, le=365)):
    return get_personalization_store().insights(user_id=user_id, days=days)


@app.post("/v1/feedback")
def feedback(req: FeedbackRequest):
    fb_id = get_feedback_store().log_feedback(
        interaction_id=req.interaction_id,
        rating=req.rating,
        corrected_answer=req.corrected_answer,
        note=req.note,
    )
    return {"status": "ok", "feedback_id": fb_id, "stats": get_feedback_store().stats()}


@app.get("/v1/training/stats")
def training_stats():
    return get_feedback_store().stats()


@app.get("/v1/training/export")
def training_export(only_rated: bool = Query(default=True)):
    """Return all training examples as JSONL (one JSON per line)."""
    items = get_feedback_store().export_jsonl(only_rated=only_rated)
    body = "\n".join(json.dumps(x, ensure_ascii=False) for x in items)
    return Response(content=body, media_type="application/x-ndjson")


_OCR_CACHE_DIR = settings.INDEX_DIR / "ocr_cache"
_OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _ocr_png(png_bytes: bytes) -> str:
    """OCR a PNG via pytesseract, with on-disk content-hash cache."""
    import hashlib
    key = hashlib.sha1(png_bytes).hexdigest()
    cache_path = _OCR_CACHE_DIR / f"{key}.txt"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    try:
        from PIL import Image
        import pytesseract
        import io
        img = Image.open(io.BytesIO(png_bytes))
        # convert to RGB for tesseract reliability
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        text = pytesseract.image_to_string(img).strip()
    except Exception as e:
        logger.warning("OCR failed: {}", e)
        text = ""
    cache_path.write_text(text, encoding="utf-8")
    return text


def _resolve_page_index(doc, start_char: Optional[int], page: Optional[int]) -> int:
    """Find which page a chunk lives on. Mirrors the chunker's "\\n\\n" join."""
    if page is not None:
        return max(0, min(page - 1, doc.page_count - 1))
    if start_char is None:
        return 0
    cumulative = 0
    page_idx = doc.page_count - 1
    for i, pg in enumerate(doc):
        t = pg.get_text("text") or ""
        end = cumulative + len(t) + 2
        if start_char < end:
            page_idx = i
            break
        cumulative = end
    return page_idx


@app.get("/v1/page-figures")
def page_figures(
    source_file: str = Query(...),
    start_char: Optional[int] = Query(default=None),
    page: Optional[int] = Query(default=None),
    min_w: int = Query(default=80, ge=0, description="drop figures narrower than this"),
    min_h: int = Query(default=80, ge=0),
    ocr: bool = Query(default=True, description="run OCR on each figure for a caption"),
):
    """Return a list of *just the figures/diagrams* from the PDF page.

    Strategy:
      1. List embedded raster images on the page; for each, expose a stable
         URL to /v1/figure?xref=N.
      2. If no embedded images (vector-only diagrams, common in textbooks),
         detect drawing-rich regions on the page and expose them as cropped
         page-region URLs.
    """
    p = Path(source_file)
    if not p.exists() or p.suffix.lower() != ".pdf":
        raise HTTPException(status_code=404, detail="file not found or not a PDF")
    try:
        import fitz
        doc = fitz.open(str(p))
        page_idx = _resolve_page_index(doc, start_char, page)
        pg = doc[page_idx]

        figures: List[Dict[str, Any]] = []

        # 1. embedded raster images
        for img in pg.get_images(full=True):
            xref = img[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha > 3:  # CMYK → RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                w, h = pix.width, pix.height
                png_bytes = pix.tobytes("png") if ocr else b""
                pix = None  # release
            except Exception:
                continue
            if w < min_w or h < min_h:
                continue
            caption = _ocr_png(png_bytes) if (ocr and png_bytes) else ""
            figures.append({
                "kind": "image",
                "xref": xref,
                "width": w,
                "height": h,
                "url": f"/v1/figure?source_file={source_file}&xref={xref}",
                "caption": caption,
            })

        # 2. fallback: detect vector-drawing regions and crop them
        if not figures:
            drawings = pg.get_drawings() or []
            if drawings:
                regions = _cluster_rects([d["rect"] for d in drawings])
                for i, rect in enumerate(regions):
                    if rect.width < min_w or rect.height < min_h:
                        continue
                    caption = ""
                    if ocr:
                        mat = fitz.Matrix(2, 2)
                        crop_pix = pg.get_pixmap(matrix=mat, clip=rect)
                        caption = _ocr_png(crop_pix.tobytes("png"))
                        crop_pix = None
                    figures.append({
                        "kind": "region",
                        "index": i,
                        "width": int(rect.width),
                        "height": int(rect.height),
                        "url": (
                            f"/v1/figure?source_file={source_file}"
                            f"&page={page_idx+1}"
                            f"&x0={rect.x0:.1f}&y0={rect.y0:.1f}"
                            f"&x1={rect.x1:.1f}&y1={rect.y1:.1f}"
                        ),
                        "caption": caption,
                    })

        page_count = doc.page_count
        doc.close()
        return {"page": page_idx + 1, "page_count": page_count, "figures": figures}
    except Exception as e:
        logger.exception("page-figures failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/figure")
def figure(
    source_file: str = Query(...),
    xref: Optional[int] = Query(default=None),
    page: Optional[int] = Query(default=None),
    x0: Optional[float] = Query(default=None),
    y0: Optional[float] = Query(default=None),
    x1: Optional[float] = Query(default=None),
    y1: Optional[float] = Query(default=None),
    dpi: int = Query(default=200, ge=72, le=400),
):
    """Return a single figure from the PDF as PNG.

    - With `xref`: extract that embedded image.
    - With `page` + bbox (x0/y0/x1/y1): render only that region of the page.
    """
    p = Path(source_file)
    if not p.exists() or p.suffix.lower() != ".pdf":
        raise HTTPException(status_code=404, detail="file not found or not a PDF")
    try:
        import fitz
        doc = fitz.open(str(p))
        if xref is not None:
            pix = fitz.Pixmap(doc, xref)
            if pix.n - pix.alpha > 3:  # CMYK → RGB
                pix = fitz.Pixmap(fitz.csRGB, pix)
            png = pix.tobytes("png")
            doc.close()
            return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
        if page is not None and None not in (x0, y0, x1, y1):
            pg = doc[max(0, min(page - 1, doc.page_count - 1))]
            rect = fitz.Rect(x0, y0, x1, y1)
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = pg.get_pixmap(matrix=mat, clip=rect)
            png = pix.tobytes("png")
            doc.close()
            return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
        doc.close()
        raise HTTPException(status_code=400, detail="provide xref OR page+bbox")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("figure failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


def _cluster_rects(rects):
    """Coarse clustering of vector-drawing rects on a page → bigger regions
    likely to correspond to figures. Greedy union-of-overlapping with padding.
    """
    import fitz
    if not rects:
        return []
    pad = 6
    merged = []
    for r in rects:
        rr = fitz.Rect(r.x0 - pad, r.y0 - pad, r.x1 + pad, r.y1 + pad)
        attached = False
        for i, m in enumerate(merged):
            if rr.intersects(m):
                merged[i] = m | rr
                attached = True
                break
        if not attached:
            merged.append(rr)
    # second pass to absorb chains
    changed = True
    while changed:
        changed = False
        for i in range(len(merged)):
            for j in range(i + 1, len(merged)):
                if merged[i].intersects(merged[j]):
                    merged[i] = merged[i] | merged[j]
                    merged.pop(j)
                    changed = True
                    break
            if changed:
                break
    # drop tiny rects (probably stray lines)
    merged = [m for m in merged if m.width > 40 and m.height > 40]
    return merged


@app.get("/v1/page-image")
def page_image(
    source_file: str = Query(..., description="absolute PDF path"),
    start_char: Optional[int] = Query(default=None, description="char offset to locate the page"),
    page: Optional[int] = Query(default=None, description="explicit 1-indexed page"),
    dpi: int = Query(default=150, ge=72, le=300),
):
    """Render a PDF page as PNG. Used to show diagrams/figures inline."""
    p = Path(source_file)
    if not p.exists() or p.suffix.lower() != ".pdf":
        raise HTTPException(status_code=404, detail="file not found or not a PDF")
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(p))
        page_idx = _resolve_page_index(doc, start_char, page)
        pg = doc[page_idx]
        pix = pg.get_pixmap(dpi=dpi)
        png = pix.tobytes("png")
        page_count = doc.page_count
        doc.close()
        return Response(
            content=png,
            media_type="image/png",
            headers={
                "X-Page-Index": str(page_idx),
                "X-Page-Count": str(page_count),
                "Cache-Control": "public, max-age=86400",
            },
        )
    except Exception as e:
        logger.exception("page-image failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/query", response_model=QueryResponse)
async def query_q(req: QueryRequest):
    where: Dict[str, Any] = {}
    if req.subject:
        where["subject"] = req.subject
    if req.book:
        where["book"] = req.book
    if req.chapter:
        where["chapter"] = req.chapter

    try:
        # run blocking pipeline in a thread to keep the event loop free
        resp = await asyncio.get_event_loop().run_in_executor(
            None,
            pipeline.query,
            req.query,
            req.top_k,
            where or None,
        )
        return resp
    except Exception as e:
        logger.exception("Query failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    results = []
    for file in files:
        try:
            unique_name = f"{uuid.uuid4().hex}_{Path(file.filename).name}"
            out_path = settings.UPLOAD_DIR / unique_name
            content = await file.read()
            out_path.write_bytes(content)
            logger.info("Saved upload: {} -> {}", file.filename, out_path)

            text = await asyncio.get_event_loop().run_in_executor(
                None, extract_text_from_bytes, file.filename, content
            )
            if not text or not text.strip():
                results.append({"file": file.filename, "indexed": 0, "note": "no extractable text"})
                continue

            chunks = chunk_text(
                text,
                max_chars=settings.MAX_CHUNK_CHARS,
                overlap=settings.CHUNK_OVERLAP,
            )
            documents = [c["text"] for c in chunks]
            ids = [f"upload_{unique_name}_c{i}" for i in range(len(documents))]
            metadatas = [
                {
                    "chunk_index": i,
                    "start_char": c["start_char"],
                    "end_char": c["end_char"],
                    "source_file": str(out_path),
                    "filename": file.filename,
                    "subject": "Uploaded",
                    "book": "User Upload",
                    "chapter": Path(file.filename).stem,
                    "source": "upload",
                }
                for i, c in enumerate(chunks)
            ]
            embeddings = await asyncio.get_event_loop().run_in_executor(
                None, embedder.embed_texts, documents
            )
            store.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
            store.persist()
            results.append({"file": file.filename, "indexed": len(documents)})
        except Exception as e:
            logger.exception("Upload failed for {}: {}", file.filename, e)
            results.append({"file": file.filename, "error": str(e)})

    # refresh BM25 once after the batch
    bm25.build(store.get_all_documents())
    return {"status": "ok", "results": results}
