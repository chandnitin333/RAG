from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str = "dev"
    DEBUG: bool = True

    # ---------------- paths ----------------
    # parents[2] = ragh/ (i.e., the project root for this package)
    PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
    DATA_DIR: Path = PROJECT_ROOT / "data"
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    INDEX_DIR: Path = DATA_DIR / "index"
    FAISS_INDEX_PATH: Path = INDEX_DIR / "faiss.index"
    METASTORE_PATH: Path = INDEX_DIR / "metastore.sqlite"
    CORPUS_MANIFEST_PATH: Path = INDEX_DIR / "corpus_manifest.json"

    # corpora to walk (in-place catalog, no file moves)
    BOOK_MAPPING_DIR: Path = PROJECT_ROOT.parent / "Book Mapping"
    COMMAND_CAPSULE_DIR: Path = PROJECT_ROOT.parent / "Command Capsule"

    # ---------------- vector store ----------------
    # one of: "chroma" (default, embedded), "faiss", "milvus"
    VECTOR_DB: str = "chroma"
    CHROMA_DIR: Path = INDEX_DIR / "chroma"
    CHROMA_COLLECTION: str = "ragh_corpus"
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "ragh_corpus"

    # ---------------- models ----------------
    # bge-small: 384-dim, strong retrieval, fast on CPU
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    # cross-encoder reranker
    RERANKER_MODEL: str = "BAAI/bge-reranker-base"
    # Reader: prefers Ollama (better quality, Metal-accelerated on Mac)
    # and falls back to flan-t5 if Ollama is unreachable.
    READER_BACKEND: str = "auto"  # "auto" | "ollama" | "flan-t5" | "extractive"
    READER_MODEL: str = "google/flan-t5-base"  # used only when READER_BACKEND=flan-t5
    READER_DEVICE: str = "cpu"
    OLLAMA_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"

    # ---------------- retrieval ----------------
    TOP_K: int = 5
    RETRIEVE_K_DENSE: int = 30
    RETRIEVE_K_BM25: int = 30
    RRF_K: int = 60
    RERANK_TOP_K: int = 10
    USE_RERANKER: bool = True

    # ---------------- chunking ----------------
    MAX_CHUNK_CHARS: int = 1800
    CHUNK_OVERLAP: int = 200
    MAX_DOC_SIZE_MB: int = 200

    # ---------------- ingestion ----------------
    INGEST_BATCH_SIZE: int = 32
    OCR_FALLBACK: bool = True

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()

# ensure runtime dirs exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.INDEX_DIR.mkdir(parents=True, exist_ok=True)
