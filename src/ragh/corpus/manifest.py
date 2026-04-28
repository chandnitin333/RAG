"""Walk Book Mapping/ and Command Capsule/ in place; build a manifest.

Output: a list of dicts, one per file, with subject/book/chapter metadata.
No files are moved or renamed.
"""
from pathlib import Path
from typing import List, Dict, Any, Iterator
import json
import re
from loguru import logger

from ragh.config import settings
from ragh.ingestion.loaders import is_supported


SUBJECT_KEYWORDS = {
    "chem": "Chemistry",
    "math": "Maths",
    "phy": "Physics",
}


def detect_subject(path_parts: List[str]) -> str:
    joined = " ".join(path_parts).lower()
    for key, subj in SUBJECT_KEYWORDS.items():
        if key in joined:
            return subj
    return "Unknown"


# Some subjects use a wrapper directory (e.g. Chemistry has "Books" / "Excels")
# between the subject and the actual book. Unwrap them.
_WRAPPER_DIRS = {"books", "excels", "excel", "mapped books", "new folder"}


def _walk_book_mapping(root: Path) -> Iterator[Dict[str, Any]]:
    """`Book Mapping/<Subject> ref Books Mapping/[<wrapper>/]<Book>/.../<file>`"""
    if not root.exists():
        return
    for subject_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        subject = detect_subject([subject_dir.name])
        for first_level in sorted(p for p in subject_dir.iterdir() if p.is_dir()):
            book_dirs: List[Path]
            if first_level.name.strip().lower() in _WRAPPER_DIRS:
                book_dirs = sorted(p for p in first_level.iterdir() if p.is_dir())
                # also catch loose files sitting directly under the wrapper
                for file_path in first_level.iterdir():
                    if file_path.is_file() and is_supported(file_path):
                        yield {
                            "source": "book_mapping",
                            "subject": subject,
                            "book": first_level.name,
                            "chapter": file_path.stem,
                            "filename": file_path.name,
                            "abs_path": str(file_path),
                            "size_bytes": file_path.stat().st_size,
                        }
            else:
                book_dirs = [first_level]

            for book_dir in book_dirs:
                book = book_dir.name
                for file_path in book_dir.rglob("*"):
                    if not file_path.is_file() or not is_supported(file_path):
                        continue
                    rel = file_path.relative_to(book_dir)
                    chapter = _chapter_from_relative(rel)
                    yield {
                        "source": "book_mapping",
                        "subject": subject,
                        "book": book,
                        "chapter": chapter,
                        "filename": file_path.name,
                        "abs_path": str(file_path),
                        "size_bytes": file_path.stat().st_size,
                    }


def _walk_command_capsule(root: Path) -> Iterator[Dict[str, Any]]:
    """`Command Capsule/JEE Adv. <Subject> Volumes 1 to 4/Vol-N/<chapter>/<file>`"""
    if not root.exists():
        return
    for subject_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        subject = detect_subject([subject_dir.name])
        for vol_dir in sorted(p for p in subject_dir.iterdir() if p.is_dir()):
            volume = vol_dir.name
            for file_path in vol_dir.rglob("*"):
                if not file_path.is_file() or not is_supported(file_path):
                    continue
                rel = file_path.relative_to(vol_dir)
                chapter = _chapter_from_relative(rel)
                yield {
                    "source": "command_capsule",
                    "subject": subject,
                    "book": f"Command Capsule {volume}",
                    "volume": volume,
                    "chapter": chapter,
                    "filename": file_path.name,
                    "abs_path": str(file_path),
                    "size_bytes": file_path.stat().st_size,
                }


def _chapter_from_relative(rel: Path) -> str:
    """Use the top-level subdirectory under the book/volume as the chapter,
    or the filename stem if the file sits directly under the book/volume."""
    parts = rel.parts
    if len(parts) > 1:
        return parts[0]
    return Path(parts[0]).stem


def build_manifest(write: bool = True) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    entries.extend(_walk_book_mapping(settings.BOOK_MAPPING_DIR))
    entries.extend(_walk_command_capsule(settings.COMMAND_CAPSULE_DIR))

    # de-dupe by absolute path
    seen = set()
    deduped = []
    for e in entries:
        if e["abs_path"] in seen:
            continue
        seen.add(e["abs_path"])
        deduped.append(e)

    logger.info(
        "Manifest: {} files (book_mapping + command_capsule)", len(deduped)
    )
    if write:
        settings.CORPUS_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        settings.CORPUS_MANIFEST_PATH.write_text(
            json.dumps(deduped, indent=2, ensure_ascii=False)
        )
        logger.info("Manifest written: {}", settings.CORPUS_MANIFEST_PATH)
    return deduped


def load_manifest() -> List[Dict[str, Any]]:
    if not settings.CORPUS_MANIFEST_PATH.exists():
        return build_manifest(write=True)
    return json.loads(settings.CORPUS_MANIFEST_PATH.read_text())


def manifest_summary(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_subject: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    by_book: Dict[str, int] = {}
    total_bytes = 0
    for e in entries:
        by_subject[e["subject"]] = by_subject.get(e["subject"], 0) + 1
        by_source[e["source"]] = by_source.get(e["source"], 0) + 1
        by_book[e["book"]] = by_book.get(e["book"], 0) + 1
        total_bytes += e.get("size_bytes", 0)
    return {
        "total_files": len(entries),
        "total_bytes": total_bytes,
        "by_subject": by_subject,
        "by_source": by_source,
        "books": sorted(by_book.keys()),
    }
