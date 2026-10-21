/** Types mirroring the Python API responses (snake_case). */

export interface CountObservation {
  value: number | null;
  display: string;
  precision: "exact" | "approximate" | "unknown" | string;
}

export interface ProfileSnapshot {
  is_verified: boolean;
  external_urls: string[];
  followers: CountObservation | null;
  following: CountObservation | null;
  post_count: CountObservation | null;
  source_url: string;
  captured_at: string;
  parser_version: string;
  missing_fields: string[];
}

export interface Lead {
  lead_id: string;
  username: string;
  username_normalized: string;
  full_name: string;
  instagram_id: string;
  follower_count: number;
  follows_count: number;
  business_category_name: string;
  bio: string;
  business_email: string;
  business_phone_number: string;
  profile_url: string;
  external_url: string;
  all_external_urls: string;
  engagement_rate: string;
  scraped_at: string;
  status: string;
  source: string;
  created_at: string;
  updated_at: string;
  last_error: string;
  media_status: string;
  website_status: string;
  progress: string;
  progress_remedy: string;
  research_status: string;
  snapshot: ProfileSnapshot | null;
  fit_status: string;
  fit_note: string;
  fit_decided_at: string;
  decision_currency: string;
  decision_currency_reason: string;
  new_evidence_available: boolean;
}

export interface LeadList {
  items: Lead[];
  total: number;
  limit: number;
  offset: number;
}

export interface LeadSubmission {
  created: boolean;
  lead: Lead;
}

export interface Post {
  post_id: string;
  media_type: string;
  product_type: string;
  short_code: string;
  url: string;
  caption: string;
  like_count: number;
  comment_count: number;
  play_count: number;
  taken_at: string;
  fetched_at: string;
  status: string;
}

export interface WebsitePage {
  page_id: string;
  url: string;
  resolved_url: string;
  domain: string;
  title: string;
  text: string;
  links: string;
  http_status: number;
  status: string;
  error: string;
  fetched_at: string;
}

export interface Job {
  job_id: string;
  stage: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  result: string;
  last_error: string;
  run_after: string;
  created_at: string;
  updated_at: string;
}

export interface LeadDetail {
  lead: Lead;
  progress: string;
  progress_remedy: string;
  posts: Post[];
  website_pages: WebsitePage[];
  contacts: Contact[];
  contact_request: ContactRequest | null;
  jobs: Job[];
}

export interface RetryAiResult {
  lead_id: string;
  jobs: Job[];
}

export interface Dossier {
  lead_id: string;
  username: string;
  summary: string;
  topics: string[];
  audience: string;
  evidence_urls: string[];
  qualification_score: number;
  qualification_tier: string;
  rubric: string;
  criterion_scores: Record<string, number>;
  uncertainty: string;
  model: string;
  status: string;
  generated_at: string;
}

export interface DossierList {
  items: Dossier[];
  total: number;
  limit: number;
  offset: number;
}

export interface Outreach {
  lead_id: string;
  username: string;
  channel: string;
  status: string;
  subject: string;
  body: string;
  dm_body: string;
  model: string;
  generated_at: string;
}

export interface OutreachList {
  items: Outreach[];
  total: number;
  limit: number;
  offset: number;
}

export interface Stats {
  leads_total: number;
  leads_by_status: Record<string, number>;
  leads_by_progress: Record<string, number>;
  jobs_by_status: Record<string, number>;
  dossiers_total: number;
  outreach_total: number;
  outreach_needs_review: number;
}

export interface IntegrationsStatus {
  database: "healthy" | "unreachable";
  worker: "active" | "stale" | "stopped";
  gemini: "configured" | "disabled";
  hikerapi: "configured" | "disabled";
  worker_last_beat_at: string;
}

export interface OutreachRevision {
  revision_id: string;
  lead_id: string;
  channel: string;
  status: string;
  subject: string;
  body: string;
  dm_body: string;
  requested_at: string;
  created_at: string;
}

export interface OutreachRevisionList {
  items: OutreachRevision[];
  total: number;
}

export interface BriefSource {
  url: string;
  title: string;
  status: string;
  fetched_at: string;
}

export interface Contact {
  contact_id: string;
  lead_id: string;
  type: string;
  value: string;
  source_url: string;
  observed_at: string;
  method: string;
  validation_state: string;
  provenance: string;
}

export interface Brief {
  lead_id: string;
  username: string;
  full_name: string;
  bio: string;
  category: string;
  follower_count: number;
  follower_display: string;
  follower_precision: string;
  follows_count: number;
  external_urls: string[];
  captured_at: string;
  missing_fields: string[];
  is_verified: boolean;
  observed_topics: string[];
  websites: BriefSource[];
  contacts: Contact[];
  evidence_version: number;
  sources: BriefSource[];
  has_dossier: boolean;
  ai_summary: string;
  ai_status: string;
  generated_at: string;
  model: string;
}


export interface FitDecision {
  decision_id: string;
  lead_id: string;
  action: string;
  fit_status: string;
  decision_currency: string;
  evidence_version: number;
  criteria_version: number;
  note: string;
  actor: string;
  created_at: string;
}

export interface FitDecisionList {
  items: FitDecision[];
  total: number;
}

export interface ContactRequest {
  request_id: string;
  lead_id: string;
  status: string;
  note: string;
  evidence_version: number;
  searched_scope: string;
  result_count: number;
  error: string;
  requested_at: string;
  started_at: string;
  completed_at: string;
  created_at: string;
}
