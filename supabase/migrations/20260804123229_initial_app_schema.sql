create extension if not exists pgcrypto with schema extensions;

create schema if not exists app;

revoke all on schema app from public, anon, authenticated;

create type app.profile_role as enum ('player', 'gm', 'admin');
create type app.member_role as enum ('player', 'gm');
create type app.asset_kind as enum ('map', 'character', 'prop', 'image');
create type app.scene_item_kind as enum ('map', 'token', 'drawing', 'text', 'fog', 'shape');
create type app.visibility_scope as enum ('everyone', 'gm_only', 'owner_only');

create table app.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null check (char_length(display_name) between 1 and 80),
  role app.profile_role not null default 'player',
  legacy_user_id bigint unique,
  legacy_password_reset_required boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table app.gm_invitations (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  invited_by uuid not null references app.profiles(user_id),
  accepted_by uuid references app.profiles(user_id),
  expires_at timestamptz not null,
  accepted_at timestamptz,
  created_at timestamptz not null default now(),
  constraint gm_invitations_email_normalized check (email = lower(trim(email))),
  constraint gm_invitations_acceptance_consistent check (
    (accepted_by is null and accepted_at is null)
    or (accepted_by is not null and accepted_at is not null)
  )
);

create unique index gm_invitations_one_open_per_email
  on app.gm_invitations (email)
  where accepted_at is null;

create table app.rooms (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references app.profiles(user_id),
  name text not null check (char_length(name) between 1 and 120),
  game_system text not null default 'neutral' check (game_system ~ '^[a-z][a-z0-9_-]{1,31}$'),
  system_config jsonb not null default '{}'::jsonb check (jsonb_typeof(system_config) = 'object'),
  legacy_table_id bigint unique,
  join_code_hash text unique,
  is_archived boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table app.room_members (
  room_id uuid not null references app.rooms(id) on delete cascade,
  user_id uuid not null references app.profiles(user_id) on delete cascade,
  role app.member_role not null default 'player',
  joined_at timestamptz not null default now(),
  primary key (room_id, user_id)
);

create table app.scenes (
  id uuid primary key default gen_random_uuid(),
  room_id uuid not null references app.rooms(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  width integer not null default 4096 check (width between 256 and 32768),
  height integer not null default 4096 check (height between 256 and 32768),
  grid_size integer not null default 64 check (grid_size between 8 and 512),
  grid_enabled boolean not null default true,
  grid_color text not null default '#64748b66' check (grid_color ~ '^#[0-9a-fA-F]{8}$'),
  background_color text not null default '#111827' check (background_color ~ '^#[0-9a-fA-F]{6}$'),
  version bigint not null default 1 check (version > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, room_id)
);

alter table app.rooms
  add column active_scene_id uuid,
  add constraint rooms_active_scene_belongs_to_room
    foreign key (active_scene_id, id)
    references app.scenes (id, room_id)
    on delete set null (active_scene_id);

create table app.assets (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references app.profiles(user_id) on delete cascade,
  name text not null check (char_length(name) between 1 and 160),
  kind app.asset_kind not null,
  object_key text not null unique check (object_key !~ '(^/|\.\.)'),
  content_type text not null check (content_type like '%/%'),
  byte_size bigint not null check (byte_size between 1 and 52428800),
  width integer check (width is null or width > 0),
  height integer check (height is null or height > 0),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table app.scene_items (
  id uuid primary key default gen_random_uuid(),
  scene_id uuid not null references app.scenes(id) on delete cascade,
  asset_id uuid references app.assets(id) on delete set null,
  legacy_token_id bigint unique,
  created_by uuid not null references app.profiles(user_id),
  kind app.scene_item_kind not null,
  name text not null default '' check (char_length(name) <= 160),
  x double precision not null default 0 check (x between -1000000 and 1000000),
  y double precision not null default 0 check (y between -1000000 and 1000000),
  width double precision not null default 64 check (width between 0.01 and 1000000),
  height double precision not null default 64 check (height between 0.01 and 1000000),
  rotation double precision not null default 0 check (rotation between -360000 and 360000),
  z_index integer not null default 0,
  visibility app.visibility_scope not null default 'everyone',
  is_locked boolean not null default false,
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  version bigint not null default 1 check (version > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index scene_items_scene_order_idx
  on app.scene_items (scene_id, z_index, created_at);

create table app.room_join_tokens (
  id uuid primary key default gen_random_uuid(),
  room_id uuid not null references app.rooms(id) on delete cascade,
  token_hash text not null unique,
  created_by uuid not null references app.profiles(user_id),
  expires_at timestamptz not null,
  max_uses integer check (max_uses is null or max_uses > 0),
  use_count integer not null default 0 check (use_count >= 0),
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  constraint room_join_tokens_usage_valid check (max_uses is null or use_count <= max_uses)
);

create index room_join_tokens_room_active_idx
  on app.room_join_tokens (room_id, expires_at)
  where revoked_at is null;

create table app.room_events (
  id bigint generated always as identity primary key,
  event_id uuid not null default gen_random_uuid() unique,
  room_id uuid not null references app.rooms(id) on delete cascade,
  scene_id uuid references app.scenes(id) on delete cascade,
  actor_user_id uuid not null references app.profiles(user_id),
  event_type text not null check (event_type ~ '^[a-z][a-z0-9_.-]{1,63}$'),
  aggregate_id uuid,
  aggregate_version bigint check (aggregate_version is null or aggregate_version > 0),
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  created_at timestamptz not null default now()
);

create index room_events_room_cursor_idx on app.room_events (room_id, id);

create table app.chat_messages (
  id uuid primary key default gen_random_uuid(),
  room_id uuid not null references app.rooms(id) on delete cascade,
  author_user_id uuid not null references app.profiles(user_id),
  body text not null check (char_length(body) between 1 and 2000),
  created_at timestamptz not null default now(),
  edited_at timestamptz,
  deleted_at timestamptz
);

create index chat_messages_room_created_idx
  on app.chat_messages (room_id, created_at desc);

create table app.turn_entries (
  id uuid primary key default gen_random_uuid(),
  room_id uuid not null references app.rooms(id) on delete cascade,
  scene_item_id uuid references app.scene_items(id) on delete cascade,
  label text not null check (char_length(label) between 1 and 120),
  initiative numeric(8, 2) not null default 0,
  position integer not null check (position >= 0),
  is_active boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (room_id, position)
);

create unique index turn_entries_one_active_per_room
  on app.turn_entries (room_id)
  where is_active;

create or replace function app.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create or replace function app.create_profile_for_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  candidate_name text;
begin
  candidate_name := coalesce(
    nullif(trim(new.raw_user_meta_data ->> 'display_name'), ''),
    nullif(split_part(coalesce(new.email, ''), '@', 1), ''),
    'Игрок'
  );

  insert into app.profiles (user_id, display_name)
  values (new.id, left(candidate_name, 80));
  return new;
end;
$$;

create trigger profiles_set_updated_at
before update on app.profiles
for each row execute function app.set_updated_at();

create trigger rooms_set_updated_at
before update on app.rooms
for each row execute function app.set_updated_at();

create trigger scenes_set_updated_at
before update on app.scenes
for each row execute function app.set_updated_at();

create trigger assets_set_updated_at
before update on app.assets
for each row execute function app.set_updated_at();

create trigger scene_items_set_updated_at
before update on app.scene_items
for each row execute function app.set_updated_at();

create trigger turn_entries_set_updated_at
before update on app.turn_entries
for each row execute function app.set_updated_at();

create trigger auth_user_created_profile
after insert on auth.users
for each row execute function app.create_profile_for_new_user();

alter table app.profiles enable row level security;
alter table app.gm_invitations enable row level security;
alter table app.rooms enable row level security;
alter table app.room_members enable row level security;
alter table app.scenes enable row level security;
alter table app.assets enable row level security;
alter table app.scene_items enable row level security;
alter table app.room_join_tokens enable row level security;
alter table app.room_events enable row level security;
alter table app.chat_messages enable row level security;
alter table app.turn_entries enable row level security;

revoke all on all tables in schema app from public, anon, authenticated;
revoke all on all sequences in schema app from public, anon, authenticated;
revoke all on all functions in schema app from public, anon, authenticated;

alter default privileges in schema app revoke all on tables from public, anon, authenticated;
alter default privileges in schema app revoke all on sequences from public, anon, authenticated;
alter default privileges in schema app revoke all on functions from public, anon, authenticated;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'vtt-assets',
  'vtt-assets',
  false,
  52428800,
  array['image/jpeg', 'image/png', 'image/webp', 'image/avif']
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;
