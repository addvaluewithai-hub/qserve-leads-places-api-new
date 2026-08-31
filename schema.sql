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

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_priority ON leads(priority);
CREATE INDEX IF NOT EXISTS idx_leads_price ON leads(price_level);
CREATE INDEX IF NOT EXISTS idx_leads_primary_type ON leads(primary_type);
CREATE INDEX IF NOT EXISTS idx_leads_rating ON leads(rating);
CREATE INDEX IF NOT EXISTS idx_leads_last_seen ON leads(last_seen_at);
