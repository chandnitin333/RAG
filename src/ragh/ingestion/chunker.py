from typing import List, Dict
import re
from dataclasses import dataclass


@dataclass
class Chunk:
    id: str
    doc_id: str
    text: str
    start_char: int
    end_char: int
    metadata: dict

def simple_chunk(text: str, max_chars: int = 2000, overlap_chars: int = 400) -> List[Chunk]:
    chunks = []
    start = 0
    doc_id = "doc-" + str(abs(hash(text)) % (10**8))
    idx = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk_text = text[start:end]
        chunk = Chunk(id=f"{doc_id}-c{idx}", doc_id=doc_id, text=chunk_text,
                      start_char=start, end_char=end, metadata={})
        chunks.append(chunk)
        idx += 1
        start = end - overlap_chars
    return chunks


def chunk_text(text: str, max_chars: int = 1800, overlap: int = 200) -> List[Dict]:
    """
    Simple paragraph-aware chunking: split by paragraphs then join to reach max_chars,
    use overlap characters between consecutive chunks.
    Returns list of dicts: {"text": ..., "start_char": int, "end_char": int}
    """
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    chunks = []
    current = ""
    start_idx = 0
    char_cursor = 0
    for p in paragraphs:
        if len(current) + len(p) + 2 <= max_chars:
            if not current:
                start_idx = char_cursor
            current = (current + "\n\n" + p).strip()
            char_cursor += len(p) + 2
        else:
            if current:
                end_idx = start_idx + len(current)
                chunks.append({"text": current, "start_char": start_idx, "end_char": end_idx})
                # setup overlap
                # pick last overlap chars to seed next chunk
                overlap_text = current[-overlap:] if overlap < len(current) else current
                current = overlap_text + "\n\n" + p
                start_idx = end_idx - len(overlap_text)
                char_cursor = start_idx + len(current)
            else:
                # single paragraph longer than max_chars: hard split
                for i in range(0, len(p), max_chars - overlap):
                    seg = p[i:i + max_chars]
                    s = char_cursor + i
                    e = s + len(seg)
                    chunks.append({"text": seg, "start_char": s, "end_char": e})
                char_cursor += len(p) + 2
                current = ""
    if current:
        end_idx = start_idx + len(current)
        chunks.append({"text": current, "start_char": start_idx, "end_char": end_idx})
    return chunks

