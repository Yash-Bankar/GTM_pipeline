/** Types mirroring the Python API responses (snake_case). */

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
  posts: Post[];
  website_pages: WebsitePage[];
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
  jobs_by_status: Record<string, number>;
  dossiers_total: number;
  outreach_total: number;
  outreach_needs_review: number;
}
