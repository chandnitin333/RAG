# RAGH — Self-hosted RAG for JEE/NEET

A ChatGPT-like AI mentor running **entirely on your machine**. No API keys.
Index your PDFs/DOCX/images, ask questions, get streaming answers grounded
in those books — with diagrams, MathJax equations, and per-user insights.

---

## Local setup — step by step

> Tested on macOS (Apple Silicon). Linux works the same once Homebrew →
> apt-equivalent is substituted.

### 0. Prerequisites

You need **three** things on your system before the project runs:

| Tool | What for | Install (macOS) |
|---|---|---|
| **Python ≥ 3.10** | Backend (FastAPI, embeddings, retrieval) | already on macOS, or `brew install python@3.12` |
| **Node ≥ 18** | Frontend dev server | `brew install node` |
| **Tesseract** | OCR fallback for scanned PDFs and figure captions | `brew install tesseract` |

### 1. Get the code

```bash
cd /Users/nitinchandekar/Personal/AI_PROJECT/ragh
```

(If you cloned fresh, `cd` into the project's `ragh/` folder.)

### 2. Install **Ollama** (local LLM runtime)

This is what answers the questions. No external API keys, runs on Apple
Silicon Metal / NVIDIA / CPU.

```bash
brew install ollama       # one-time install

# start the Ollama daemon (leave running in a terminal, or use a launchd plist)
ollama serve

# in another terminal: pull the model the chat uses (~2 GB, one-time)
ollama pull llama3.2:3b
```

Verify:

```bash
curl -s http://127.0.0.1:11434/api/tags | jq .
```

Should list `llama3.2:3b`.

### 3. Backend — Python deps

The current code works against the system / anaconda Python that ships
with macOS, but a venv keeps things clean:

```bash
python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt
```

What gets installed: FastAPI, Uvicorn, sentence-transformers (bge-small,
bge-reranker-base), Chroma, FAISS, rank-bm25, transformers (flan-t5
fallback), pdfplumber, PyMuPDF, pytesseract, python-docx, loguru.

### 4. Start the backend API

```bash
# from /Users/nitinchandekar/Personal/AI_PROJECT/ragh
export PYTHONPATH=./src
uvicorn ragh.api.api_server:app --host 127.0.0.1 --port 8000

# or with auto-reload while developing:
uvicorn ragh.api.api_server:app --reload --host 127.0.0.1 --port 8000
```

First boot downloads the embedding model (`bge-small-en-v1.5`, ~130 MB)
and the cross-encoder reranker (`bge-reranker-base`, ~270 MB) once.

Check it's up:

```bash
curl http://127.0.0.1:8000/v1/health
# {"status":"ok","backend":"chroma","indexed":0}
```

Open the API docs at <http://127.0.0.1:8000/docs>.

### 5. Frontend — Node deps & dev server

In a **second terminal**:

```bash
cd /Users/nitinchandekar/Personal/AI_PROJECT/ragh/frontend
npm install                  # one-time
npm run dev
```

Open the UI at <http://localhost:5173>. Vite proxies `/v1/*` to
`localhost:8000` so there's nothing else to configure.

### 6. Build the corpus catalog & ingest

The catalog walks `Book Mapping/` and `Command Capsule/` (sibling
directories of `ragh/`) **in place** — files are not moved.

In the UI: open the **ingest** tab → click **rebuild manifest** → then
**Ingest corpus**. Or via curl:

```bash
# 1. catalog the files
curl -X POST http://127.0.0.1:8000/v1/manifest/rebuild

# 2. ingest everything (slow first time — PDFs + OCR + embeddings)
curl -X POST http://127.0.0.1:8000/v1/ingest-corpus \
  -H "Content-Type: application/json" \
  -d '{"rebuild_manifest": false, "rebuild_index": false}'

# Or ingest just one subject / volume to test:
curl -X POST http://127.0.0.1:8000/v1/ingest-corpus \
  -H "Content-Type: application/json" \
  -d '{"subject": "Physics", "book": "Vol-1"}'
```

Re-runs are fast — completed files are skipped via
`data/index/ingest_state.json`. Image extraction + OCR runs as part of
the same pass, so diagrams are vector-indexed alongside text.

### 7. Ask anything in the chat

Go to <http://localhost:5173>, click **+ New chat**, type a question:

| You ask | Routed to |
|---|---|
| "what is angular position" | 📚 Teacher (Definition + Formula + Example + Figure) |
| "solve: arc length π cm, radius 6 cm, find the angle" | 🧮 Solver (step-by-step) |
| "draw a vector with x and y components in 2D" | 🎨 Diagram (inline SVG) |
| "3-day study plan for trigonometry" | 📅 Planner (markdown table) |
| "5 level-1 questions on radians in JSON format" | ❓ Quizzer (strict JSON) |

Override the router from the **agent** dropdown in the chat header.

---

## What's running, in one diagram

```
                        user types question
                                 │
                                 ▼
                ┌─────────────────────────────┐
                │  Query rewrite (Ollama)     │  cleans typos / follow-ups
                └─────────────────────────────┘
                                 │
                                 ▼
                ┌─────────────────────────────┐
                │  Hybrid retrieval           │  BM25 + Chroma vector,
                │  (text + image vectors)     │  fused with RRF
                └─────────────────────────────┘
                                 │
                                 ▼
                ┌─────────────────────────────┐
                │  Cross-encoder reranker     │  BAAI/bge-reranker-base
                └─────────────────────────────┘
                                 │
                                 ▼
                ┌─────────────────────────────┐
                │  Agent router →             │  Solver / Teacher /
                │  per-agent system prompt    │  Diagram / Planner / Quizzer
                └─────────────────────────────┘
                                 │
                                 ▼
                ┌─────────────────────────────┐
                │  Ollama llama3.2:3b         │  streams tokens (NDJSON)
                │  (JSON mode for Quizzer)    │
                └─────────────────────────────┘
                                 │
                                 ▼
              UI: typewriter render → MathJax → SVG /
              feedback / copy / regenerate / ↓ PDF
                                 │
                                 ▼
       interactions logged to feedback.sqlite +
       personalization.sqlite for /v1/personal/insights
```

---

## Components

| Layer | Module | Notes |
|---|---|---|
| Corpus catalog | `ragh.corpus.manifest` | Walks `Book Mapping/`, `Command Capsule/` in place. |
| Ingestion | `ragh.corpus.ingestor` | Resumable; image chunks too. |
| Loaders | `ragh.ingestion.loaders` | PDF (pdfplumber → PyMuPDF → OCR), DOCX, images, text. |
| Symbol remap | `ragh.utils.symbol_remap` | Adobe Symbol-font glyphs → real Unicode (π θ ≤ ≥ ∑ ∫). |
| Difficulty tagger | `ragh.ingestion.difficulty` | JEE Main / Advanced / Olympiad / NEET / Unknown. |
| Embeddings | `ragh.embeddings.embedder` | `BAAI/bge-small-en-v1.5` (384-dim). |
| Vector DB | `ragh.vectordb.{chroma,faiss,milvus}` | Default **Chroma** (embedded). FAISS + Milvus optional. |
| Retriever | `ragh.retriever.retriever` | Dense + BM25, RRF fused. |
| Reranker | `ragh.retriever.reranker` | `BAAI/bge-reranker-base`. |
| Agents | `ragh.pipeline.agents` | Solver / Teacher / Diagram / Planner / Quizzer. |
| Reader | `ragh.reader.ollama_reader` | Local Llama 3.2 3B via Ollama HTTP API. Streams. |
| Pipeline | `ragh.pipeline.chat` | rewrite → route → retrieve → rerank → read. |
| API | `ragh.api.api_server` | FastAPI, NDJSON streaming. |
| Self-training | `ragh.training.feedback_store` | SQLite log of (Q, A, ±1, optional correction). |
| Personalization | `ragh.training.personalization` | Per-user history & weak-topic insights. |

---

## API quick reference

| Method & path | Purpose |
|---|---|
| `GET  /v1/health` | health check |
| `GET  /v1/stats` | index size, backend, models in use |
| `GET  /v1/agents` | list available agents |
| `POST /v1/chat` | non-streaming chat (returns full answer) |
| `POST /v1/chat/stream` | NDJSON stream (corrected → agent → citations → tokens → done) |
| `POST /v1/feedback` | thumbs ±1 + optional corrected_answer |
| `GET  /v1/training/stats` | how many interactions / +1 / -1 |
| `GET  /v1/training/export` | training JSONL for the LoRA script |
| `GET  /v1/personal/insights?user_id=…` | per-user weak-topic profile |
| `GET  /v1/manifest/summary` | files cataloged, by subject/source |
| `POST /v1/manifest/rebuild` | re-walk the corpus directories |
| `POST /v1/ingest-corpus` | ingest catalog → vectors (resumable) |
| `POST /v1/upload` | ad-hoc file upload + index |
| `GET  /v1/page-image` | render a PDF page as PNG |
| `GET  /v1/page-figures` | extract embedded figures from a PDF page (with OCR captions) |
| `GET  /v1/figure` | fetch a single figure (by xref or bbox) |
| `POST /v1/bm25/rebuild` | rebuild BM25 from current vector DB |

---

## Layout

```
ragh/
├── data/
│   ├── uploads/                       # ad-hoc files
│   └── index/
│       ├── chroma/                    # Chroma persistent store
│       ├── faiss.index                # FAISS (when VECTOR_DB=faiss)
│       ├── faiss.sqlite               # FAISS metadata sidecar
│       ├── bm25_cache.pkl
│       ├── corpus_manifest.json
│       ├── ingest_state.json
│       ├── feedback.sqlite            # ratings + corrections
│       ├── personalization.sqlite     # per-user history
│       └── ocr_cache/                 # tesseract output cache
├── frontend/                          # Vite + React + TS + Tailwind UI
├── scripts/
│   └── fine_tune_lora.py              # LoRA fine-tune from feedback
├── src/ragh/
│   ├── api/api_server.py
│   ├── config.py
│   ├── corpus/{manifest,ingestor}.py
│   ├── embeddings/embedder.py
│   ├── ingestion/{loaders,chunker,difficulty}.py
│   ├── pipeline/{chat,rag_pipeline,agents}.py
│   ├── reader/{reader,ollama_reader}.py
│   ├── retriever/{retriever,bm25,reranker}.py
│   ├── training/{feedback_store,personalization}.py
│   ├── utils/symbol_remap.py
│   └── vectordb/{base,chroma_store,faiss_store,milvus_store,factory}.py
└── requirements.txt
```

---

## Switching the vector DB

Set `VECTOR_DB` in env or `ragh/config.py`:

- `chroma` *(default)* — embedded, persists to `data/index/chroma/`. No setup.
- `faiss` — FAISS + SQLite sidecar. `data/index/faiss.index{,.sqlite}`.
- `milvus` — needs Milvus running. `docker compose up milvus`.

---

## Self-training loop

1. Use the chat. Every Q/A is auto-logged to `data/index/feedback.sqlite`.
2. Click 👍 / 👎 on answers (optionally write a corrected answer for 👎).
3. Once you have ~50+ thumbs-ups:

   ```bash
   python scripts/fine_tune_lora.py --epochs 3
   ```

   Trains a LoRA adapter on the preferred (Q, A) pairs.
4. Convert the adapter to GGUF, register a Modelfile, and:

   ```bash
   ollama create ragh-tutor -f data/lora/ragh-tutor/Modelfile
   ```

   Then set `OLLAMA_MODEL=ragh-tutor` in `ragh/config.py` and restart the API.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Address already in use` on port 8000 | `lsof -nP -iTCP:8000` to find the holder, then `kill <pid>`. |
| `ModuleNotFoundError: loguru` | You haven't activated the venv. `source venv/bin/activate`, then `pip install -r requirements.txt`. |
| Chat says "Ollama not available" | `ollama serve` isn't running, or `OLLAMA_URL` is wrong. `curl http://127.0.0.1:11434/api/tags` should return JSON. |
| Empty answers / `indexed_chunks: 0` | You haven't ingested. Hit `/v1/manifest/rebuild` then `/v1/ingest-corpus`. |
| Greek letters render as garbage in the chat | The PDF used Adobe Symbol font; the symbol remap layer normalises this on retrieve. If you still see it, restart the backend so the latest remap loads. |
| OCR very slow on big corpus | Disable on first pass: set `OCR_FALLBACK=False` in `ragh/config.py`. |

---

## Notes

- All weights download to `~/.cache/huggingface/` and `~/.ollama/` on first use; nothing leaves your machine after that.
- Conversation history is stored in browser localStorage under `ragh.conversations.v1` — no server-side accounts.
- The `Book Mapping/` and `Command Capsule/` directories are **never modified**. The corpus walker only reads.
