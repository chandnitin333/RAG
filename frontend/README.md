# RAGH Frontend

React + TypeScript + Tailwind UI for the RAGH self-hosted RAG API.

## Stack

- Vite + React 18 + TypeScript
- Tailwind CSS (dark, paneled UI)
- No state library — local component state is enough for a tool this size

## Layout

```
src/
├── api.ts                   # typed wrapper over /v1/* endpoints
├── types.ts                 # response shapes shared with backend
├── components/
│   ├── StatsBar.tsx         # live index stats (auto-refresh 8s)
│   ├── QueryPanel.tsx       # ask a question, see answer + citations
│   ├── Citations.tsx        # citation cards with subject/book/chapter
│   ├── FilterPanel.tsx      # filter by subject / book / chapter
│   ├── IngestPanel.tsx      # trigger /v1/ingest-corpus
│   └── UploadPanel.tsx      # upload ad-hoc files into the index
├── App.tsx                  # tabbed shell: ask / ingest / upload
├── main.tsx
└── index.css
```

## Run in development

```bash
# in one terminal — start the API
cd ../
export PYTHONPATH=./src
uvicorn ragh.api.api_server:app --reload --port 8000

# in another terminal — start the UI
cd frontend
npm install
npm run dev
# open http://localhost:5173
```

The dev server proxies `/v1/*` to `http://localhost:8000`, so there's no CORS
configuration to worry about during development. CORS is also enabled on the
FastAPI side for non-proxied deployments.

## Build for production

```bash
npm run build
# output → dist/
npm run preview     # serve the built bundle locally
```

When deploying, set `VITE_API_BASE` (e.g. `https://ragh.example.com`) at build
time to point the bundle at your hosted API.

```bash
VITE_API_BASE=https://ragh.example.com npm run build
```

## How it talks to the backend

Every UI action is one API call:

| UI                              | Endpoint                       |
| ------------------------------- | ------------------------------ |
| StatsBar refresh                | `GET /v1/stats`                |
| Ask                             | `POST /v1/query`               |
| Filter dropdowns (book/subject) | `GET /v1/manifest/summary`     |
| "Rebuild manifest"              | `POST /v1/manifest/rebuild`    |
| "Ingest corpus"                 | `POST /v1/ingest-corpus`       |
| Upload files                    | `POST /v1/upload`              |

Errors surface as in-card red text. There's no toast layer — everything stays
on the page where you triggered it.

## Notes

- The ingest button kicks off a long-running synchronous request; the UI shows
  a busy state until it returns. For very large corpora, consider running the
  ingestor as a CLI batch job instead.
- The reader on the backend is `flan-t5-base` by default. Generation on CPU can
  take a few seconds per query — that's the backend, not the UI.
