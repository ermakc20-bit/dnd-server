-- Import sources and drafts are private backend-only preparation state.
create table app.import_jobs (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid not null,
  room_id uuid not null,
  creator_participant_id uuid not null,
  source_hash text not null check (source_hash ~ '^[0-9a-f]{64}$'),
  source_bytes bytea check (octet_length(source_bytes) between 1 and 5242880),
  draftset jsonb not null check (jsonb_typeof(draftset)='object'
    and draftset->'schema_version'='1'::jsonb),
  status text not null default 'draft' check (status in ('draft','confirmed','cancelled','expired')),
  version integer not null default 1 check (version >= 1),
  card_ids uuid[] not null default '{}',
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '24 hours'),
  foreign key(room_id,campaign_id) references app.rooms(id,campaign_id) on delete cascade,
  foreign key(creator_participant_id,room_id) references app.participants(id,room_id),
  check (status='draft' or source_bytes is null)
);
create index import_jobs_room_creator_idx on app.import_jobs(room_id,creator_participant_id);
create index import_jobs_source_hash_idx on app.import_jobs(room_id,creator_participant_id,source_hash);
create index import_jobs_expiry_idx on app.import_jobs(expires_at) where status='draft';
alter table app.import_jobs enable row level security;
revoke all on app.import_jobs from public, anon, authenticated;
