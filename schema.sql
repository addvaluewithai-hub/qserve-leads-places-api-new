CREATE TABLE IF NOT EXISTS leads (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  price_level TEXT NOT NULL DEFAULT 'PRICE_LEVEL_UNSPECIFIED',
  rating REAL,
  user_rating_count INTEGER NOT NULL DEFAULT 0,
  business_status TEXT,
  phone TEXT,
  website TEXT,
  google_maps_url TEXT,
  address TEXT,
  latitude REAL,
  longitude REAL,
  primary_type TEXT,
  types TEXT,
  opening_hours TEXT,
  source_label TEXT,
  source_query TEXT,
  source_type TEXT,
  source_area TEXT,
  status TEXT NOT NULL DEFAULT 'New',
  priority TEXT NOT NULL DEFAULT 'Medium',
  notes TEXT NOT NULL DEFAULT '',
  first_source_batch TEXT,
  latest_source_batch TEXT,
  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  crm_updated_at TEXT
);

CREATE TABLE IF NOT EXISTS campaigns (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  vertical TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  config_json TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaign_runs (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  discovered_count INTEGER NOT NULL DEFAULT 0,
  qualified_count INTEGER NOT NULL DEFAULT 0,
  summary_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS campaign_leads (
  campaign_id TEXT NOT NULL,
  lead_id TEXT NOT NULL,
  qualified INTEGER NOT NULL DEFAULT 0,
  quality_score INTEGER NOT NULL DEFAULT 0,
  qualification_reason TEXT NOT NULL DEFAULT '',
  source_area TEXT,
  source_query TEXT,
  source_term TEXT,
  status TEXT NOT NULL DEFAULT 'New',
  priority TEXT NOT NULL DEFAULT 'Medium',
  notes TEXT NOT NULL DEFAULT '',
  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_run_id TEXT,
  crm_updated_at TEXT,
  PRIMARY KEY (campaign_id, lead_id)
);

CREATE TABLE IF NOT EXISTS lead_signals (
  campaign_id TEXT NOT NULL,
  lead_id TEXT NOT NULL,
  latest_sampled_review_at TEXT,
  latest_sampled_review_age_days INTEGER,
  sampled_review_count INTEGER NOT NULL DEFAULT 0,
  recent_sampled_reviews INTEGER NOT NULL DEFAULT 0,
  sampled_review_avg REAL,
  review_signal_checked_at TEXT,
  review_signal_note TEXT NOT NULL DEFAULT '',
  website_present INTEGER NOT NULL DEFAULT 0,
  phone_present INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (campaign_id, lead_id)
);

CREATE TABLE IF NOT EXISTS lead_domains (
  lead_id TEXT PRIMARY KEY,
  website_domain TEXT NOT NULL,
  verified INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Legacy metro/market tables retained for historical runs.
CREATE TABLE IF NOT EXISTS market_coverage (
  campaign_id TEXT NOT NULL,
  market_key TEXT NOT NULL,
  market_label TEXT NOT NULL,
  state_code TEXT,
  tier INTEGER NOT NULL DEFAULT 1,
  priority INTEGER NOT NULL DEFAULT 100,
  phase TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'queued',
  search_count INTEGER NOT NULL DEFAULT 0,
  raw_places INTEGER NOT NULL DEFAULT 0,
  net_new_place_ids INTEGER NOT NULL DEFAULT 0,
  grounding_calls INTEGER NOT NULL DEFAULT 0,
  quality_passes INTEGER NOT NULL DEFAULT 0,
  net_new_domains INTEGER NOT NULL DEFAULT 0,
  last_yield_per_search REAL NOT NULL DEFAULT 0,
  first_searched_at TEXT,
  last_searched_at TEXT,
  last_run_id TEXT,
  notes TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (campaign_id, market_key)
);

CREATE TABLE IF NOT EXISTS market_run_history (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  market_key TEXT NOT NULL,
  market_label TEXT NOT NULL,
  searched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  raw_places INTEGER NOT NULL DEFAULT 0,
  net_new_place_ids INTEGER NOT NULL DEFAULT 0,
  grounding_calls INTEGER NOT NULL DEFAULT 0,
  quality_passes INTEGER NOT NULL DEFAULT 0,
  net_new_domains INTEGER NOT NULL DEFAULT 0,
  status_after TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS zip_coverage (
  campaign_id TEXT NOT NULL,
  zip_code TEXT NOT NULL,
  city TEXT,
  state_code TEXT NOT NULL,
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  phase TEXT NOT NULL DEFAULT '',
  state_priority INTEGER NOT NULL DEFAULT 100,
  city_priority INTEGER NOT NULL DEFAULT 1000,
  status TEXT NOT NULL DEFAULT 'queued',
  search_count INTEGER NOT NULL DEFAULT 0,
  page_count INTEGER NOT NULL DEFAULT 0,
  raw_places INTEGER NOT NULL DEFAULT 0,
  exact_zip_places INTEGER NOT NULL DEFAULT 0,
  quality_passes INTEGER NOT NULL DEFAULT 0,
  net_new_domains INTEGER NOT NULL DEFAULT 0,
  duplicate_place_ids INTEGER NOT NULL DEFAULT 0,
  duplicate_domains INTEGER NOT NULL DEFAULT 0,
  last_searched_at TEXT,
  last_run_id TEXT,
  notes TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (campaign_id, zip_code)
);

CREATE TABLE IF NOT EXISTS zip_run_history (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  zip_code TEXT NOT NULL,
  city TEXT,
  state_code TEXT NOT NULL,
  searched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status_after TEXT NOT NULL DEFAULT '',
  page_count INTEGER NOT NULL DEFAULT 0,
  raw_places INTEGER NOT NULL DEFAULT 0,
  exact_zip_places INTEGER NOT NULL DEFAULT 0,
  quality_passes INTEGER NOT NULL DEFAULT 0,
  net_new_domains INTEGER NOT NULL DEFAULT 0,
  duplicate_place_ids INTEGER NOT NULL DEFAULT 0,
  duplicate_domains INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS api_usage_ledger (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  sku TEXT NOT NULL,
  usage_month TEXT NOT NULL,
  request_count INTEGER NOT NULL DEFAULT 1,
  context TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lead_discovery_screening (
  campaign_id TEXT NOT NULL,
  lead_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  source_zip TEXT,
  quality_gate_passed INTEGER NOT NULL DEFAULT 0,
  screened_at TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (campaign_id, lead_id)
);

CREATE TABLE IF NOT EXISTS homepage_link_evidence (
  campaign_id TEXT NOT NULL,
  lead_id TEXT NOT NULL,
  homepage TEXT NOT NULL,
  final_url TEXT NOT NULL,
  url TEXT NOT NULL,
  anchor_text TEXT NOT NULL DEFAULT '',
  crawled_at TEXT NOT NULL,
  PRIMARY KEY (campaign_id, lead_id, url)
);

CREATE TABLE IF NOT EXISTS service_gap_evidence (
  campaign_id TEXT NOT NULL,
  lead_id TEXT NOT NULL,
  service_name TEXT NOT NULL,
  status TEXT NOT NULL,
  service_offered_evidence TEXT,
  dedicated_page_url TEXT,
  validation_method TEXT,
  notes TEXT NOT NULL DEFAULT '',
  validated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (campaign_id, lead_id, service_name)
);

CREATE TABLE IF NOT EXISTS lead_contacts (
  id TEXT PRIMARY KEY,
  lead_id TEXT NOT NULL,
  person_name TEXT NOT NULL,
  role TEXT,
  email TEXT,
  is_owner INTEGER NOT NULL DEFAULT 0,
  is_decision_maker INTEGER NOT NULL DEFAULT 0,
  is_direct_email INTEGER NOT NULL DEFAULT 0,
  is_publicly_verified INTEGER NOT NULL DEFAULT 0,
  evidence_source TEXT,
  verified_at TEXT,
  notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS outreach_suppression (
  lead_id TEXT PRIMARY KEY,
  website_domain TEXT NOT NULL,
  suppressed INTEGER NOT NULL DEFAULT 1,
  contact_status TEXT NOT NULL DEFAULT 'Contacted',
  first_contacted_at TEXT,
  last_contacted_at TEXT,
  campaign_id TEXT,
  contact_email TEXT,
  suppression_reason TEXT NOT NULL DEFAULT 'contacted_once_global_block',
  reengage_after TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_priority ON leads(priority);
CREATE INDEX IF NOT EXISTS idx_leads_price ON leads(price_level);
CREATE INDEX IF NOT EXISTS idx_leads_primary_type ON leads(primary_type);
CREATE INDEX IF NOT EXISTS idx_leads_rating ON leads(rating);
CREATE INDEX IF NOT EXISTS idx_leads_last_seen ON leads(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_campaigns_active ON campaigns(active);
CREATE INDEX IF NOT EXISTS idx_campaign_runs_campaign ON campaign_runs(campaign_id, completed_at);
CREATE INDEX IF NOT EXISTS idx_campaign_leads_campaign ON campaign_leads(campaign_id, qualified, quality_score);
CREATE INDEX IF NOT EXISTS idx_campaign_leads_status ON campaign_leads(campaign_id, status);
CREATE INDEX IF NOT EXISTS idx_campaign_leads_seen ON campaign_leads(campaign_id, last_seen_at);
CREATE INDEX IF NOT EXISTS idx_lead_signals_freshness ON lead_signals(campaign_id, latest_sampled_review_age_days);
CREATE UNIQUE INDEX IF NOT EXISTS idx_lead_domains_domain ON lead_domains(website_domain);
CREATE INDEX IF NOT EXISTS idx_market_coverage_next ON market_coverage(campaign_id, status, priority, tier, last_searched_at);
CREATE INDEX IF NOT EXISTS idx_market_coverage_state ON market_coverage(campaign_id, state_code, status);
CREATE INDEX IF NOT EXISTS idx_market_history_campaign ON market_run_history(campaign_id, searched_at);
CREATE INDEX IF NOT EXISTS idx_market_history_market ON market_run_history(campaign_id, market_key, searched_at);
CREATE INDEX IF NOT EXISTS idx_zip_coverage_next ON zip_coverage(campaign_id, status, state_priority, city_priority, zip_code);
CREATE INDEX IF NOT EXISTS idx_zip_coverage_state ON zip_coverage(campaign_id, state_code, status);
CREATE INDEX IF NOT EXISTS idx_zip_history_campaign ON zip_run_history(campaign_id, searched_at);
CREATE INDEX IF NOT EXISTS idx_zip_history_zip ON zip_run_history(campaign_id, zip_code, searched_at);
CREATE INDEX IF NOT EXISTS idx_api_usage_month ON api_usage_ledger(campaign_id, sku, usage_month);
CREATE INDEX IF NOT EXISTS idx_screening_zip ON lead_discovery_screening(campaign_id, source_zip);
CREATE INDEX IF NOT EXISTS idx_gap_status ON service_gap_evidence(campaign_id, status, service_name);
CREATE INDEX IF NOT EXISTS idx_contacts_lead ON lead_contacts(lead_id, is_decision_maker, is_direct_email);
CREATE UNIQUE INDEX IF NOT EXISTS idx_suppression_domain ON outreach_suppression(website_domain);
CREATE INDEX IF NOT EXISTS idx_suppression_status ON outreach_suppression(suppressed, contact_status, reengage_after);
