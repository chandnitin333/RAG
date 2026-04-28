export interface Citation {
  index: number;
  id: string;
  score?: number | null;
  source_file?: string | null;
  subject?: string | null;
  book?: string | null;
  chapter?: string | null;
  start_char?: number | null;
  end_char?: number | null;
  preview?: string | null;
  /** Full chunk text — rendered alongside the PDF page so the user sees
   *  exactly what's in the document. */
  content?: string | null;
  /** Indexed image chunks carry these. */
  kind?: "text" | "image" | null;
  image_url?: string | null;
  page?: number | null;
  ocr_text?: string | null;
}

export interface Retrieved {
  id: string;
  score: number;
  preview: string;
  metadata: Record<string, unknown>;
}

export interface QueryResponse {
  answer: string;
  mode?: string | null;
  citations: Citation[];
  retrieved: Retrieved[];
}

export interface Stats {
  backend: string;
  indexed_chunks: number;
  bm25_records: number;
  embedding_model: string;
  embedding_dim: number;
  reranker_enabled: boolean;
  reader_model: string;
}

export interface ManifestSummary {
  total_files: number;
  total_bytes: number;
  by_subject: Record<string, number>;
  by_source: Record<string, number>;
  books: string[];
}

export interface IngestResult {
  status: string;
  total_files: number;
  ok: number;
  skipped: number;
  failed: number;
  total_chunks: number;
  elapsed_sec: number;
  store_count: number;
}

export interface UploadResult {
  status: string;
  results: Array<{ file: string; indexed?: number; note?: string; error?: string }>;
}

export interface QueryFilters {
  subject?: string;
  book?: string;
  chapter?: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  answer: string;
  corrected_query: string;
  mode?: string | null;
  citations: Citation[];
  retrieved: Retrieved[];
  interaction_id?: string | null;
  agent?: string | null;
  agent_label?: string | null;
}

export type AgentName = "solver" | "teacher" | "diagram" | "planner" | "quizzer";

export interface InsightsResponse {
  user_id: string;
  window_days: number;
  total_questions: number;
  by_subject: Record<string, number>;
  by_agent: Record<string, number>;
  top_chapters: Record<string, number>;
  recommendations: Array<{ subject: string; chapter: string; rationale: string }>;
  recent: Array<{ query: string; agent: string; ts: number }>;
}

export interface FeedbackRequest {
  interaction_id: string;
  rating: 1 | -1;
  corrected_answer?: string | null;
  note?: string | null;
}

export interface TrainingStats {
  interactions: number;
  positive: number;
  negative: number;
}

export interface Figure {
  kind: "image" | "region";
  width: number;
  height: number;
  url: string;
  xref?: number;
  index?: number;
  /** OCR'd text caption — labels and short text inside the figure. */
  caption?: string;
}

export interface PageFiguresResponse {
  page: number;
  page_count: number;
  figures: Figure[];
}
