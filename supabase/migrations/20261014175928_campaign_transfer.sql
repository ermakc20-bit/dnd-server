-- Transfer orchestration is private preparation state, never gameplay authority.
create table app.campaign_transfer_jobs (
  id uuid primary key,
  owner_user_id uuid not null references app.profiles(user_id) on delete cascade,
  kind text not null check (kind in ('import','export')),
  source_campaign_id uuid references app.campaigns(id) on delete set null,
  options jsonb not null default '{}' check (jsonb_typeof(options)='object'),
  phase text not null default 'receiving' check (phase in
    ('receiving','validating','building','storing','committing','completed',
     'cleanup_pending','failed','cancelled','expired')),
  progress integer not null default 0 check (progress between 0 and 100),
  cancel_requested boolean not null default false,
  lease_id uuid,
  lease_expires_at timestamptz,
  expires_at timestamptz not null default now()+interval '1 hour',
  archive bytea check (octet_length(archive)<=268435456),
  reserved_blob_keys jsonb not null default '[]' check (jsonb_typeof(reserved_blob_keys)='array'),
  result_campaign_id uuid references app.campaigns(id) on delete set null,
  error_code text,
  terminal_phase text check (terminal_phase in ('failed','cancelled','expired')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index campaign_transfer_owner_idx on app.campaign_transfer_jobs(owner_user_id,created_at);
create index campaign_transfer_cleanup_idx on app.campaign_transfer_jobs(phase,lease_expires_at);
alter table app.campaign_transfer_jobs enable row level security;
revoke all on app.campaign_transfer_jobs from public,anon,authenticated;
