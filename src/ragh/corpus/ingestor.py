"""Ingest the cataloged corpus into the vector DB.

For each manifest entry: load → chunk → embed → store. State is persisted
in `ingest_state.json` so re-runs skip already-ingested files.
"""
from typing import List, Dict, Any, Optional, Iterable
from pathlib import Path
import hashlib
import json
import time
from loguru import logger

from ragh.config import settings
from ragh.corpus.manifest import build_manifest, load_manifest, manifest_summary
from ragh.ingestion.loaders import load_any
from ragh.ingestion.chunker import chunk_text
from ragh.ingestion.difficulty import classify_difficulty
from ragh.embeddings.embedder import Embedder
from ragh.vectordb.base import VectorStore


STATE_PATH = settings.INDEX_DIR / "ingest_state.json"


def _file_id(path: Path) -> str:
    h = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
    return f"{path.stem[:40]}_{h}"


def _load_state() -> Dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            return {"done": {}}
    return {"done": {}}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


class CorpusIngestor:
    def __init__(self, embedder: Embedder, store: VectorStore):
        self.embedder = embedder
        self.store = store

    def ingest_manifest(
        self,
        entries: Optional[List[Dict[str, Any]]] = None,
        rebuild: bool = False,
        limit: Optional[int] = None,
        subject: Optional[str] = None,
        book: Optional[str] = None,
    ) -> Dict[str, Any]:
        entries = entries or load_manifest()
        if not entries:
            entries = build_manifest()
        if subject:
            entries = [e for e in entries if e.get("subject") == subject]
        if book:
            entries = [e for e in entries if book.lower() in (e.get("book") or "").lower()]
        if limit:
            entries = entries[:limit]

        state = {"done": {}} if rebuild else _load_state()
        done = state.get("done", {})

        ok = skipped = failed = total_chunks = 0
        t0 = time.time()
        for i, entry in enumerate(entries, 1):
            abs_path = entry["abs_path"]
            if not rebuild and abs_path in done:
                skipped += 1
                continue
            try:
                n = self._ingest_one(entry)
                done[abs_path] = {"chunks": n, "ts": time.time()}
                total_chunks += n
                ok += 1
                if i % 10 == 0:
                    state["done"] = done
                    _save_state(state)
                    self.store.persist()
                    logger.info(
                        "Progress: {}/{} files | chunks={} | ok={} fail={} skip={}",
                        i, len(entries), total_chunks, ok, failed, skipped,
                    )
            except Exception as e:
                failed += 1
                logger.exception("Ingest failed: {} ({})", abs_path, e)

        state["done"] = done
        _save_state(state)
        self.store.persist()

        return {
            "total_files": len(entries),
            "ok": ok,
            "skipped": skipped,
            "failed": failed,
            "total_chunks": total_chunks,
            "elapsed_sec": round(time.time() - t0, 2),
            "store_count": self.store.count(),
        }

    # --------------- single file ---------------
    def _ingest_one(self, entry: Dict[str, Any]) -> int:
        path = Path(entry["abs_path"])
        text = load_any(path)
        added = 0

        if text and text.strip():
            chunks = chunk_text(
                text,
                max_chars=settings.MAX_CHUNK_CHARS,
                overlap=settings.CHUNK_OVERLAP,
            )
            if chunks:
                added += self._add_text_chunks(path, entry, chunks)

        # Index images embedded in PDFs as separate "image chunks" so a query
        # can retrieve diagrams alongside text.
        if path.suffix.lower() == ".pdf":
            added += self._add_image_chunks(path, entry)

        if added == 0:
            logger.debug("No extractable content: {}", path)
        return added

    def _add_text_chunks(
        self, path: Path, entry: Dict[str, Any], chunks: List[Dict[str, Any]]
    ) -> int:
        file_key = _file_id(path)
        ids = [f"{file_key}_c{i}" for i in range(len(chunks))]
        documents = [c["text"] for c in chunks]
        metadatas = [
            {
                "kind": "text",
                "chunk_index": i,
                "start_char": c["start_char"],
                "end_char": c["end_char"],
                "source_file": str(path),
                "filename": path.name,
                "subject": entry.get("subject", "Unknown"),
                "book": entry.get("book", ""),
                "volume": entry.get("volume", ""),
                "chapter": entry.get("chapter", ""),
                "source": entry.get("source", ""),
                "difficulty": classify_difficulty(
                    c["text"], chapter=entry.get("chapter", ""), book=entry.get("book", "")
                ),
            }
            for i, c in enumerate(chunks)
        ]
        embeddings = self.embedder.embed_texts(
            documents, batch_size=settings.INGEST_BATCH_SIZE
        )
        self.store.add(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )
        return len(ids)

    def _add_image_chunks(self, path: Path, entry: Dict[str, Any]) -> int:
        """Extract images, OCR them, embed the OCR text + provenance, store
        with metadata.kind='image' so the UI knows to render the figure."""
        try:
            import fitz
            from PIL import Image
            import pytesseract
            import io
        except Exception as e:
            logger.warning("image-chunks: deps missing: {}", e)
            return 0

        file_key = _file_id(path)
        chapter = entry.get("chapter", "")
        documents: List[str] = []
        ids: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        try:
            doc = fitz.open(str(path))
        except Exception as e:
            logger.warning("image-chunks: open failed for {}: {}", path, e)
            return 0

        try:
            for page_idx, page in enumerate(doc):
                images = page.get_images(full=True) or []
                for img in images:
                    xref = img[0]
                    try:
                        pix = fitz.Pixmap(doc, xref)
                        if pix.n - pix.alpha > 3:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        if pix.width < 80 or pix.height < 80:
                            pix = None
                            continue
                        # filter out very-wide page banners (publisher headers)
                        if pix.width / max(pix.height, 1) > 5:
                            pix = None
                            continue
                        png = pix.tobytes("png")
                        pix = None
                    except Exception:
                        continue

                    # OCR for the document text we'll embed
                    try:
                        ocr_text = pytesseract.image_to_string(
                            Image.open(io.BytesIO(png))
                        ).strip()
                    except Exception:
                        ocr_text = ""

                    # Build a description string that mixes OCR text with
                    # surrounding context so retrieval works even when OCR is
                    # empty (pure-graphical diagrams).
                    description = (
                        f"Diagram from chapter '{chapter}', page {page_idx + 1}. "
                        f"OCR text: {ocr_text or '(no readable labels)'}"
                    )
                    documents.append(description)
                    ids.append(f"{file_key}_img_p{page_idx}_x{xref}")
                    metadatas.append({
                        "kind": "image",
                        "page_index": page_idx,
                        "page": page_idx + 1,
                        "image_xref": xref,
                        "image_url": (
                            f"/v1/figure?source_file={path}&xref={xref}"
                        ),
                        "ocr_text": ocr_text[:600],
                        "source_file": str(path),
                        "filename": path.name,
                        "subject": entry.get("subject", "Unknown"),
                        "book": entry.get("book", ""),
                        "volume": entry.get("volume", ""),
                        "chapter": chapter,
                        "source": entry.get("source", ""),
                        "difficulty": classify_difficulty(
                            ocr_text or chapter, chapter=chapter, book=entry.get("book", "")
                        ),
                    })
        finally:
            doc.close()

        if not ids:
            return 0
        embeddings = self.embedder.embed_texts(
            documents, batch_size=settings.INGEST_BATCH_SIZE
        )
        self.store.add(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )
        logger.info("Indexed {} image chunks from {}", len(ids), path.name)
        return len(ids)
