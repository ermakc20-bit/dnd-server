-- Gameplay remains server-authoritative; tables are not writable/readable via Data API.
alter table app.scenes add column fog jsonb not null default '{"enabled":false,"reveals":[]}'::jsonb
  check (jsonb_typeof(fog) = 'object');
create table app.scene_annotations (
  id uuid primary key default gen_random_uuid(),
  scene_id uuid not null,
  campaign_id uuid not null,
  owner_participant_id uuid not null,
  kind text not null check (kind in ('line','arrow','label')),
  points jsonb not null check (jsonb_typeof(points)='array' and jsonb_array_length(points) between 1 and 2),
  label text not null default '' check (char_length(label)<=160),
  visibility text not null default 'everyone' check (visibility in ('everyone','gm_only')),
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  foreign key(scene_id,campaign_id) references app.scenes(id,campaign_id) on delete cascade,
  foreign key(owner_participant_id,campaign_id) references app.participants(id,campaign_id) deferrable initially deferred
);
create index scene_annotations_scene_idx on app.scene_annotations(scene_id,created_at,id);
create table app.dice_rolls (
  id uuid primary key default gen_random_uuid(),
  room_id uuid not null references app.rooms(id) on delete cascade,
  actor_participant_id uuid not null,
  command_id uuid not null unique,
  expression text not null check (char_length(expression) between 3 and 40),
  results jsonb not null check (jsonb_typeof(results)='array' and jsonb_array_length(results) between 1 and 100),
  modifier integer not null check (modifier between -10000 and 10000),
  total integer not null,
  visibility text not null check (visibility in ('everyone','gm_only')),
  created_at timestamptz not null default now(),
  foreign key(actor_participant_id,room_id) references app.participants(id,room_id) deferrable initially deferred
);
alter table app.room_events add column undo_state jsonb;
-- An event or roll can only disappear as part of removing its parent room/campaign.
create function app.guard_gameplay_history() returns trigger language plpgsql
security invoker set search_path='' as $$
begin
  if TG_OP='DELETE' and not exists(select 1 from app.rooms where id=OLD.room_id) then
    return OLD;
  end if;
  raise exception 'Gameplay history is immutable' using errcode='23514';
end;
$$;
create trigger dice_rolls_immutable before update or delete on app.dice_rolls
  for each row execute function app.guard_gameplay_history();
create trigger room_events_immutable before update or delete on app.room_events
  for each row execute function app.guard_gameplay_history();
alter table app.scene_annotations enable row level security;
alter table app.dice_rolls enable row level security;
revoke all on app.scene_annotations,app.dice_rolls from public,anon,authenticated;
