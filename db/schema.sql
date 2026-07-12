CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS stocks (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  name TEXT,
  core_business TEXT,
  equity_structure TEXT,
  stock_character TEXT,
  notable_history TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (symbol, market)
);

CREATE TABLE IF NOT EXISTS markets (
  id BIGSERIAL PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  total_market_cap NUMERIC,
  category_market_cap JSONB NOT NULL DEFAULT '{}'::jsonb,
  core_companies JSONB NOT NULL DEFAULT '[]'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sectors (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  parent_id BIGINT REFERENCES sectors(id) ON DELETE SET NULL,
  description TEXT,
  recent_status TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (name, parent_id)
);

CREATE TABLE IF NOT EXISTS sources (
  id BIGSERIAL PRIMARY KEY,
  source_type TEXT NOT NULL,
  title TEXT,
  url TEXT,
  publisher TEXT,
  published_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stock_sector_relations (
  id BIGSERIAL PRIMARY KEY,
  stock_id BIGINT NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
  sector_id BIGINT NOT NULL REFERENCES sectors(id) ON DELETE CASCADE,
  relation_type TEXT NOT NULL DEFAULT 'related',
  confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.500,
  source_id BIGINT REFERENCES sources(id) ON DELETE SET NULL,
  confirmed_by_user BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (stock_id, sector_id, relation_type)
);

CREATE TABLE IF NOT EXISTS positions (
  id BIGSERIAL PRIMARY KEY,
  stock_id BIGINT NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
  quantity NUMERIC NOT NULL DEFAULT 0,
  cost_price NUMERIC,
  market_value NUMERIC,
  position_ratio NUMERIC(7, 4),
  source TEXT NOT NULL DEFAULT 'manual',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (stock_id, source)
);

CREATE TABLE IF NOT EXISTS trade_events (
  id BIGSERIAL PRIMARY KEY,
  stock_id BIGINT NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
  action_type TEXT NOT NULL,
  price NUMERIC,
  quantity NUMERIC,
  reason TEXT,
  source TEXT NOT NULL DEFAULT 'manual',
  happened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_items (
  id BIGSERIAL PRIMARY KEY,
  target_type TEXT NOT NULL,
  target_id BIGINT,
  knowledge_type TEXT NOT NULL,
  content TEXT NOT NULL,
  source_id BIGINT REFERENCES sources(id) ON DELETE SET NULL,
  confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.500,
  confirmed_by_user BOOLEAN NOT NULL DEFAULT false,
  stale_after TIMESTAMPTZ,
  embedding vector(1536),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_insights (
  id BIGSERIAL PRIMARY KEY,
  target_type TEXT NOT NULL,
  target_id BIGINT,
  insight TEXT NOT NULL,
  normalized_summary TEXT,
  tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  embedding vector(1536),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS candidate_insights (
  id BIGSERIAL PRIMARY KEY,
  target_type TEXT NOT NULL,
  target_id BIGINT,
  insight TEXT NOT NULL,
  normalized_summary TEXT,
  tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  reason TEXT,
  repeat_count INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'pending',
  confirmed_insight_id BIGINT REFERENCES user_insights(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at TIMESTAMPTZ,
  CHECK (status IN ('pending', 'confirmed', 'rejected'))
);

ALTER TABLE candidate_insights
  ADD COLUMN IF NOT EXISTS repeat_count INTEGER NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS review_reports (
  id BIGSERIAL PRIMARY KEY,
  report_date DATE NOT NULL UNIQUE,
  portfolio_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
  summary TEXT NOT NULL,
  risks JSONB NOT NULL DEFAULT '[]'::jsonb,
  opportunities JSONB NOT NULL DEFAULT '[]'::jsonb,
  new_knowledge_candidates JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS period_start DATE;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS period_end DATE;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS report_type TEXT NOT NULL DEFAULT 'daily';
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS source_status JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS highlights JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS blowups JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS holdings_table JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS next_week JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS story JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS generated_at TIMESTAMPTZ;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS refreshed_at TIMESTAMPTZ;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS token_usage JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS report_key TEXT;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'review_reports'
      AND column_name = 'report_key'
  ) THEN
    ALTER TABLE review_reports ALTER COLUMN report_key DROP DEFAULT;
    ALTER TABLE review_reports ALTER COLUMN report_key DROP NOT NULL;

    UPDATE review_reports AS reports
    SET report_key = keyed.next_key
    FROM (
      SELECT
        id,
        CASE
          WHEN row_number() OVER (
            PARTITION BY report_type, market_code, start_date, end_date
            ORDER BY id DESC
          ) = 1
          THEN base_key
          ELSE base_key || ':legacy:' || id::text
        END AS next_key
      FROM (
        SELECT
          id,
          report_type,
          COALESCE(NULLIF(portfolio_snapshot->'market'->>'code', ''), 'UNKNOWN') AS market_code,
          COALESCE(period_start::text, report_date::text) AS start_date,
          COALESCE(period_end::text, report_date::text) AS end_date,
          report_type || ':' ||
            COALESCE(NULLIF(portfolio_snapshot->'market'->>'code', ''), 'UNKNOWN') || ':' ||
            COALESCE(period_start::text, report_date::text) || ':' ||
            COALESCE(period_end::text, report_date::text) AS base_key
        FROM review_reports
        WHERE report_type = 'daily_market_brief'
      ) AS daily_keys
    ) AS keyed
    WHERE reports.id = keyed.id;

    UPDATE review_reports AS reports
    SET report_key = keyed.next_key
    FROM (
      SELECT
        id,
        CASE
          WHEN row_number() OVER (
            PARTITION BY report_type, start_date, end_date
            ORDER BY id DESC
          ) = 1
          THEN base_key
          ELSE base_key || ':legacy:' || id::text
        END AS next_key
      FROM (
        SELECT
          id,
          report_type,
          COALESCE(period_start::text, report_date::text) AS start_date,
          COALESCE(period_end::text, report_date::text) AS end_date,
          report_type || ':' ||
            COALESCE(period_start::text, report_date::text) || ':' ||
            COALESCE(period_end::text, report_date::text) AS base_key
        FROM review_reports
        WHERE report_type <> 'daily_market_brief'
          AND report_key IS NULL
      ) AS legacy_keys
    ) AS keyed
    WHERE reports.id = keyed.id;
  END IF;
END $$;

DROP INDEX IF EXISTS idx_review_reports_report_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_review_reports_report_key
  ON review_reports (report_key)
  WHERE report_key IS NOT NULL;

ALTER TABLE review_reports
  DROP CONSTRAINT IF EXISTS review_reports_report_date_key;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND indexname = 'idx_review_reports_type_period'
      AND indexdef ILIKE 'CREATE UNIQUE INDEX%'
  ) THEN
    DROP INDEX idx_review_reports_type_period;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_review_reports_type_period
  ON review_reports (report_type, period_start, period_end);

CREATE INDEX IF NOT EXISTS idx_review_reports_daily_market_brief_market_date
  ON review_reports (report_date, ((portfolio_snapshot->'market'->>'code')))
  WHERE report_type = 'daily_market_brief';

CREATE TABLE IF NOT EXISTS account_snapshots (
  id BIGSERIAL PRIMARY KEY,
  snapshot_date DATE NOT NULL,
  source TEXT NOT NULL DEFAULT 'futu',
  account_info JSONB NOT NULL DEFAULT '{}'::jsonb,
  positions JSONB NOT NULL DEFAULT '[]'::jsonb,
  fx_rates JSONB NOT NULL DEFAULT '{}'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  fetched_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (snapshot_date, source)
);

CREATE TABLE IF NOT EXISTS trade_records (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL DEFAULT 'futu',
  record_key TEXT NOT NULL,
  deal_id TEXT,
  order_id TEXT,
  code TEXT,
  stock_name TEXT,
  trd_side TEXT,
  qty NUMERIC,
  price NUMERIC,
  amount NUMERIC,
  currency TEXT,
  create_time TEXT,
  trade_date DATE,
  raw JSONB NOT NULL DEFAULT '{}'::jsonb,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source, record_key)
);

CREATE INDEX IF NOT EXISTS idx_trade_records_trade_date
  ON trade_records (trade_date);

CREATE INDEX IF NOT EXISTS idx_trade_records_code
  ON trade_records (code);

CREATE TABLE IF NOT EXISTS command_events (
  id BIGSERIAL PRIMARY KEY,
  source TEXT,
  sender TEXT,
  command TEXT NOT NULL,
  ok BOOLEAN NOT NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS task_events (
  id BIGSERIAL PRIMARY KEY,
  task_type TEXT NOT NULL,
  task_id BIGINT,
  event_type TEXT NOT NULL,
  status TEXT,
  message TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deploy_events (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL DEFAULT 'unknown',
  deploy_mode TEXT NOT NULL DEFAULT 'quick',
  commit_sha TEXT,
  branch_name TEXT,
  status TEXT NOT NULL DEFAULT 'started',
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  duration_seconds NUMERIC,
  summary TEXT,
  logs_tail TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (status IN ('started', 'succeeded', 'failed'))
);

CREATE TABLE IF NOT EXISTS coding_tasks (
  id BIGSERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  priority TEXT NOT NULL DEFAULT 'normal',
  source TEXT,
  sender TEXT,
  labels JSONB NOT NULL DEFAULT '[]'::jsonb,
  linked_issue_url TEXT,
  result TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (status IN ('pending', 'accepted', 'running', 'needs_user', 'done', 'rejected', 'cancelled')),
  CHECK (priority IN ('low', 'normal', 'high'))
);

ALTER TABLE coding_tasks ADD COLUMN IF NOT EXISTS branch_name TEXT;
ALTER TABLE coding_tasks ADD COLUMN IF NOT EXISTS commit_sha TEXT;
ALTER TABLE coding_tasks ADD COLUMN IF NOT EXISTS worker_log TEXT;
ALTER TABLE coding_tasks ADD COLUMN IF NOT EXISTS worker_started_at TIMESTAMPTZ;
ALTER TABLE coding_tasks ADD COLUMN IF NOT EXISTS worker_finished_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS worker_status (
  name TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_error TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ipo_reminder_events (
  id BIGSERIAL PRIMARY KEY,
  reminder_type TEXT NOT NULL,
  stock_code TEXT NOT NULL,
  stock_name TEXT,
  target_date DATE NOT NULL,
  scheduled_for TIMESTAMPTZ NOT NULL,
  sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (reminder_type, stock_code, target_date)
);

CREATE INDEX IF NOT EXISTS idx_stocks_symbol_market ON stocks(symbol, market);
CREATE INDEX IF NOT EXISTS idx_sectors_parent_id ON sectors(parent_id);
CREATE INDEX IF NOT EXISTS idx_stock_sector_stock_id ON stock_sector_relations(stock_id);
CREATE INDEX IF NOT EXISTS idx_stock_sector_sector_id ON stock_sector_relations(sector_id);
CREATE INDEX IF NOT EXISTS idx_positions_stock_id ON positions(stock_id);
CREATE INDEX IF NOT EXISTS idx_trade_events_stock_id_happened_at ON trade_events(stock_id, happened_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_target ON knowledge_items(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_user_insights_target ON user_insights(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_candidate_insights_status ON candidate_insights(status);
CREATE INDEX IF NOT EXISTS idx_candidate_insights_target ON candidate_insights(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_command_events_created_at ON command_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_type, task_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_events_created_at ON task_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_deploy_events_created_at ON deploy_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_deploy_events_status_created_at ON deploy_events(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_coding_tasks_status_created_at ON coding_tasks(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ipo_reminder_events_sent_at ON ipo_reminder_events(sent_at DESC);

CREATE TABLE IF NOT EXISTS research_jobs (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  name TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  priority TEXT NOT NULL DEFAULT 'normal',
  source_policy TEXT NOT NULL DEFAULT 'broad_search',
  provider TEXT NOT NULL DEFAULT 'codex',
  auto_import BOOLEAN NOT NULL DEFAULT true,
  import_needs_review BOOLEAN NOT NULL DEFAULT false,
  refresh BOOLEAN NOT NULL DEFAULT false,
  artifact_dir TEXT,
  artifacts JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_discovery JSONB NOT NULL DEFAULT '{}'::jsonb,
  result_summary TEXT,
  error TEXT,
  source TEXT,
  sender TEXT,
  execution_location TEXT NOT NULL DEFAULT 'cloud_worker',
  requested_by TEXT,
  created_from TEXT,
  artifact_location TEXT,
  worker_name TEXT,
  worker_log TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  worker_started_at TIMESTAMPTZ,
  worker_finished_at TIMESTAMPTZ,
  CHECK (status IN ('queued', 'running', 'drafted', 'needs_review', 'imported', 'failed', 'cancelled')),
  CHECK (priority IN ('low', 'normal', 'high')),
  CHECK (source_policy IN ('official_only', 'official_first', 'broad_search', 'user_sources')),
  CHECK (provider IN ('codex', 'openai', 'none')),
  CHECK (execution_location IN ('cloud_worker', 'local_codex', 'manual_import', 'import_only'))
);

DO $$
BEGIN
  ALTER TABLE research_jobs ADD COLUMN IF NOT EXISTS execution_location TEXT NOT NULL DEFAULT 'cloud_worker';
  ALTER TABLE research_jobs ADD COLUMN IF NOT EXISTS requested_by TEXT;
  ALTER TABLE research_jobs ADD COLUMN IF NOT EXISTS created_from TEXT;
  ALTER TABLE research_jobs ADD COLUMN IF NOT EXISTS artifact_location TEXT;

  ALTER TABLE research_jobs DROP CONSTRAINT IF EXISTS research_jobs_source_policy_check;
  ALTER TABLE research_jobs
    ADD CONSTRAINT research_jobs_source_policy_check
    CHECK (source_policy IN ('official_only', 'official_first', 'broad_search', 'user_sources'));

  ALTER TABLE research_jobs DROP CONSTRAINT IF EXISTS research_jobs_execution_location_check;
  ALTER TABLE research_jobs
    ADD CONSTRAINT research_jobs_execution_location_check
    CHECK (execution_location IN ('cloud_worker', 'local_codex', 'manual_import', 'import_only'));
END $$;

CREATE INDEX IF NOT EXISTS idx_research_jobs_status_created_at
  ON research_jobs(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_research_jobs_symbol_market
  ON research_jobs(symbol, market);

CREATE UNIQUE INDEX IF NOT EXISTS idx_research_jobs_active_unique
  ON research_jobs(symbol, market)
  WHERE status IN ('queued', 'running');

CREATE TABLE IF NOT EXISTS daily_market_brief_jobs (
  id BIGSERIAL PRIMARY KEY,
  request_type TEXT NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  force_refresh BOOLEAN NOT NULL DEFAULT false,
  total_count INTEGER NOT NULL DEFAULT 0,
  completed_count INTEGER NOT NULL DEFAULT 0,
  succeeded_count INTEGER NOT NULL DEFAULT 0,
  skipped_count INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  cancelled_count INTEGER NOT NULL DEFAULT 0,
  current_market TEXT,
  current_market_date DATE,
  summary TEXT,
  cancel_requested_at TIMESTAMPTZ,
  worker_heartbeat_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  CHECK (request_type IN ('single', 'batch')),
  CHECK (source IN ('web', 'command', 'scheduler_recovery', 'agent')),
  CHECK (status IN ('queued', 'running', 'completed', 'partial', 'failed', 'cancelled')),
  CHECK (total_count >= 0),
  CHECK (completed_count >= 0),
  CHECK (succeeded_count >= 0),
  CHECK (skipped_count >= 0),
  CHECK (failed_count >= 0),
  CHECK (cancelled_count >= 0)
);

CREATE TABLE IF NOT EXISTS daily_market_brief_job_items (
  id BIGSERIAL PRIMARY KEY,
  job_id BIGINT NOT NULL REFERENCES daily_market_brief_jobs(id) ON DELETE CASCADE,
  market TEXT NOT NULL,
  market_date DATE NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  report_id BIGINT REFERENCES review_reports(id) ON DELETE SET NULL,
  skip_reason TEXT,
  error_code TEXT,
  error_summary TEXT,
  worker_name TEXT,
  lease_token TEXT,
  claimed_at TIMESTAMPTZ,
  heartbeat_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (job_id, market, market_date),
  CHECK (status IN ('queued', 'running', 'completed', 'skipped', 'failed', 'cancelled')),
  CHECK (attempt_count >= 0)
);

ALTER TABLE daily_market_brief_jobs
  ADD COLUMN IF NOT EXISTS cancelled_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE daily_market_brief_job_items
  ADD COLUMN IF NOT EXISTS error_code TEXT;

ALTER TABLE daily_market_brief_job_items
  ADD COLUMN IF NOT EXISTS lease_token TEXT;

UPDATE daily_market_brief_jobs AS job
SET
  total_count = aggregates.total_count,
  completed_count = aggregates.completed_count,
  succeeded_count = aggregates.succeeded_count,
  skipped_count = aggregates.skipped_count,
  failed_count = aggregates.failed_count,
  cancelled_count = aggregates.cancelled_count
FROM (
  SELECT
    item.job_id,
    count(*)::integer AS total_count,
    count(*) FILTER (WHERE item.status IN ('completed', 'skipped', 'failed', 'cancelled'))::integer AS completed_count,
    count(*) FILTER (WHERE item.status = 'completed')::integer AS succeeded_count,
    count(*) FILTER (WHERE item.status = 'skipped')::integer AS skipped_count,
    count(*) FILTER (WHERE item.status = 'failed')::integer AS failed_count,
    count(*) FILTER (WHERE item.status = 'cancelled')::integer AS cancelled_count
  FROM daily_market_brief_job_items AS item
  GROUP BY item.job_id
) AS aggregates
WHERE job.id = aggregates.job_id;

DO $$
BEGIN
  ALTER TABLE daily_market_brief_jobs
    DROP CONSTRAINT IF EXISTS daily_market_brief_jobs_aggregate_counts_check;
  ALTER TABLE daily_market_brief_jobs
    ADD CONSTRAINT daily_market_brief_jobs_aggregate_counts_check
    CHECK (completed_count = succeeded_count + skipped_count + failed_count + cancelled_count);

  ALTER TABLE daily_market_brief_jobs
    DROP CONSTRAINT IF EXISTS daily_market_brief_jobs_completed_total_check;
  ALTER TABLE daily_market_brief_jobs
    ADD CONSTRAINT daily_market_brief_jobs_completed_total_check
    CHECK (completed_count <= total_count);

  ALTER TABLE daily_market_brief_job_items
    DROP CONSTRAINT IF EXISTS daily_market_brief_job_items_error_code_check;
  ALTER TABLE daily_market_brief_job_items
    ADD CONSTRAINT daily_market_brief_job_items_error_code_check
    CHECK (error_code IS NULL OR error_code IN ('generation_failed', 'provider_timeout', 'provider_unavailable', 'historical_data_unavailable'));
END $$;

CREATE INDEX IF NOT EXISTS idx_daily_market_brief_jobs_created_at
  ON daily_market_brief_jobs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_daily_market_brief_job_items_active
  ON daily_market_brief_job_items(status, created_at ASC)
  WHERE status IN ('queued', 'running');

CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_market_brief_job_items_active_unique
  ON daily_market_brief_job_items(market, market_date)
  WHERE status IN ('queued', 'running');
