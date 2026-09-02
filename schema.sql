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
