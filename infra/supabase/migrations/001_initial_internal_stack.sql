-- siteaudit · schema inicial para operação interna
create extension if not exists "pgcrypto";

create table if not exists runs (
  id uuid primary key default gen_random_uuid(),
  source text not null default 'local_worker',
  config jsonb not null,
  status text not null check (status in ('queued','running','completed','failed')),
  progress text not null default '',
  leads_found int not null default 0,
  errors jsonb not null default '[]'::jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists leads (
  id uuid primary key default gen_random_uuid(),
  dedupe_key text not null unique,
  name text not null default '',
  website text not null default '',
  domain text not null default '',
  phone text not null default '',
  address text not null default '',
  city text not null default '',
  state text not null default '',
  country text not null default 'Brasil',
  category text not null default '',
  rating numeric(3,1),
  reviews int,
  maps_url text not null default '',
  source text not null default '',
  query text not null default '',
  has_website boolean not null default false,
  site_status text not null default 'not_checked'
    check (site_status in ('not_checked','website_found_unverified','website_not_located','audit_ok','audit_error')),
  outreach_status text not null default 'new'
    check (outreach_status in ('new','review','qualified','contacted','replied','won','lost','do_not_contact')),
  score int,
  priority_score int,
  priority_tier text check (priority_tier in ('P1','P2','P3','P4')),
  notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_leads_outreach on leads(outreach_status, updated_at desc);
create index if not exists idx_leads_priority on leads(priority_score desc nulls last);
create index if not exists idx_leads_site_status on leads(site_status);

create table if not exists run_leads (
  run_id uuid not null references runs(id) on delete cascade,
  lead_id uuid not null references leads(id) on delete cascade,
  source text not null default '',
  query text not null default '',
  primary key (run_id, lead_id)
);

create table if not exists audits (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references leads(id) on delete cascade,
  run_id uuid references runs(id) on delete set null,
  ok boolean not null default false,
  score int,
  opportunity text,
  opportunity_note text,
  findings jsonb not null default '[]'::jsonb,
  seo jsonb not null default '{}'::jsonb,
  perf jsonb not null default '{}'::jsonb,
  tech jsonb not null default '{}'::jsonb,
  design jsonb not null default '{}'::jsonb,
  content jsonb not null default '{}'::jsonb,
  contacts jsonb not null default '{}'::jsonb,
  links jsonb not null default '{}'::jsonb,
  media jsonb not null default '{}'::jsonb,
  forms jsonb not null default '{}'::jsonb,
  schema_data jsonb not null default '{}'::jsonb,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_audits_lead_created on audits(lead_id, created_at desc);

create table if not exists footprints (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references leads(id) on delete cascade,
  run_id uuid references runs(id) on delete set null,
  socials jsonb not null default '{}'::jsonb,
  directories jsonb not null default '[]'::jsonb,
  mentions jsonb not null default '[]'::jsonb,
  nap_consistency numeric(5,2),
  digital_footprint_score int,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists usage_events (
  id bigserial primary key,
  run_id uuid references runs(id) on delete set null,
  provider text not null,
  operation text not null,
  units int not null default 1,
  estimated_cost_usd numeric(10,4) not null default 0,
  created_at timestamptz not null default now()
);
