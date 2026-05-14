// 与后端 _*_to_dict 对齐的 DTO。后端字段稳定后再考虑生成器；当前手写够。

export interface Journal {
  id: number
  issn: string
  name: string
  publisher: string | null
  quality_tier: number | null
  is_predatory: boolean
  oa_status: string | null
}

export interface Paper {
  id: number
  stem: string
  title: string | null
  year: number | null
  doi: string | null
  status: string
  source: string
  pdf_path: string | null
  md_path: string | null
  insight_path: string | null
  refs_path: string | null
  journal_id: number | null
  added_at: string | null
  analyzed_at: string | null
  journal?: Journal | null
}

export interface Edge {
  id: number
  from_paper_id: number | null
  to_paper_id: number | null
  direction: string
  ref_index: number | null
  ref_title: string | null
}

export interface PaperDetail {
  paper: Paper
  edges_out: Edge[]
  edges_in: Edge[]
}

export interface ReferenceEntry {
  doi: string
  title: string
  year: number | null
  authors: string
  abstract: string
  source: 'ss' | 'openalex' | 'both' | string
}

export interface ForwardTrackResult {
  doi: string
  citing_count: number
  citing_papers: ReferenceEntry[]
  cached: boolean
  fetched_at: string
}

export interface BackwardTrackResult {
  doi: string
  references_count: number
  referenced_papers: ReferenceEntry[]
  cached: boolean
  fetched_at: string
}

export interface Task {
  id: number
  type: string
  paper_id: number | null
  status: 'queued' | 'running' | 'done' | 'failed' | string
  attempt: number
  max_attempts: number
  parent_task_id: number | null
  payload: Record<string, unknown> | null
  error_log: string | null
  started_at: string | null
  finished_at: string | null
}

export interface Subscription {
  id: number
  type: 'paper_citations' | 'author_works' | 'topic_search' | string
  target: Record<string, unknown>
  cron_expr: string
  active: boolean
  last_run_at: string | null
  next_run_at: string | null
}

export interface InboxItem {
  id: number
  subscription_id: number
  paper_id: number | null
  metadata: Record<string, unknown>
  notified: boolean
  found_at: string | null
}

export interface ProgressEvent {
  task_id: string
  type: string
  ts: string
  payload?: Record<string, unknown>
}

export interface ListResponse<T> {
  items: T[]
}

export interface NetworkNode {
  id: number
  stem: string
  title: string | null
  year: number | null
  status: string
  source: string
  quality_tier: number | null
}

export interface NetworkEdge {
  id: number
  from: number
  to: number
}

export interface NetworkGraph {
  nodes: NetworkNode[]
  edges: NetworkEdge[]
}

export interface FailureItem {
  stem: string
  paper_id: number | null
  ref_index: number
  header: string
  doi: string
  pdf_url: string
  reason: string
  category: string
}

export interface FailuresResponse {
  total: number
  by_category: Record<string, number>
  items: FailureItem[]
}
