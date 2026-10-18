-- Current presentation state only; the existing room event history stays append-only.
create table app.ability_presentations (
  id uuid primary key default gen_random_uuid(),
  scene_id uuid not null,
  campaign_id uuid not null,
  owner_participant_id uuid not null,
  geometry jsonb not null check (jsonb_typeof(geometry)='object'),
  created_at timestamptz not null default now(),
  unique(scene_id,owner_participant_id),
  foreign key(scene_id,campaign_id) references app.scenes(id,campaign_id) on delete cascade,
  foreign key(owner_participant_id,campaign_id) references app.participants(id,campaign_id)
    deferrable initially deferred
);
create index ability_presentations_scene_idx on app.ability_presentations(scene_id,created_at,id);
alter table app.ability_presentations enable row level security;
revoke all on app.ability_presentations from public,anon,authenticated;
