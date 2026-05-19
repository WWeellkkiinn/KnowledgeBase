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
  abstract: string | null
  authors_json: string[] | null
  year: number | null
  doi: string | null
  status: string
  source: string
  pdf_path: string | null
  md_path: string | null
  insight_path: string | null
  refs_path: string | null
  is_core: boolean
  journal_id: number | null
  added_at: string | null
  analyzed_at: string | null
  journal?: Journal | null
  tags: string[] | null
  ai_summary: AiSummary | null
  ai_analyzed_at: string | null
}

export interface AiSummary {
  research_question: string | null
  methodology: string | null
  key_findings: string[]
}

export interface DigestResult {
  sent: boolean
  paper_count?: number
  reason?: string
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
  venue_name?: string
}

export interface ForwardTrackResult {
  doi: string
  citing_count: number
  citing_papers: ReferenceEntry[]
  cached: boolean
  fetched_at: string
  // 分页字段（仅在切片返回时存在）
  offset?: number
  limit?: number
  has_more?: boolean
}

export interface BackwardTrackResult {
  doi: string
  references_count: number
  referenced_papers: ReferenceEntry[]
  cached: boolean
  fetched_at: string
  offset?: number
  limit?: number
  has_more?: boolean
}

// 202 异步响应：cache miss 时端点返回入队后的 task 信息
export interface TrackTaskAccepted {
  task_id: number
  status: 'queued' | 'running'
  message: string
}

export type TrackResponse<T> = T | TrackTaskAccepted

export function isTrackAccepted(r: unknown): r is TrackTaskAccepted {
  return typeof r === 'object' && r !== null && 'task_id' in r && (r as TrackTaskAccepted).task_id != null
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
  active: boolean
  description?: string | null
  generated_queries?: string[] | null
  queries_pending?: boolean
  last_filled_at?: string | null
  query_refreshed_at?: string | null
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

export interface ExploreCardData {
  pool_id: number
  title: string
  url: string | null
  title_zh: string | null
  embedding_score: number | null
  display_date: string
  authors: string
  venue_name: string | null
  rank_badges: Array<{ label: string; value: string }>
  cited_by_count: number | null
  tags: string[]
  llm_reason: string | null
  research_question: string | null
  methodology: string | null
  key_findings: string[]
}

export interface ExploreCard {
  id: number
  card: ExploreCardData
  score: number | null
  action: string | null
}

export interface ExploreCardsResponse {
  items: ExploreCard[]
  count: number
}
